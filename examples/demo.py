#
# demo application for http3_server.py
#

import asyncio
import datetime
import os
import random
import secrets
from urllib.parse import urlencode

import aiofiles  # type: ignore
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.types import Receive, Scope, Send
from starlette.websockets import WebSocketDisconnect

ROOT = os.path.dirname(__file__)
STATIC_ROOT = os.environ.get("STATIC_ROOT", os.path.join(ROOT, "htdocs"))
STATIC_URL = "/"
LOGS_PATH = os.path.join(STATIC_ROOT, "logs")
QVIS_URL = "https://qvis.quictools.info/"

templates = Jinja2Templates(directory=os.path.join(ROOT, "templates"))

# Define UPLOAD_DIR using environment variable AIOQUIC_UPLOAD_DIR or a
# default, and create it.
UPLOAD_DIR = os.environ.get("AIOQUIC_UPLOAD_DIR", os.path.join(ROOT, "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)


async def homepage(request):
    """
    Simple homepage.
    """
    await request.send_push_promise("/style.css")
    return templates.TemplateResponse("index.html", {"request": request})


async def echo(request):
    """
    HTTP echo endpoint.
    """
    content = await request.body()
    media_type = request.headers.get("content-type")
    return Response(content, media_type=media_type)


async def logs(request):
    """
    Browsable list of QLOG files.
    """
    logs = []
    for name in os.listdir(LOGS_PATH):
        if name.endswith(".qlog"):
            s = os.stat(os.path.join(LOGS_PATH, name))
            file_url = "https://" + request.headers["host"] + "/logs/" + name
            logs.append(
                {
                    "date": datetime.datetime.utcfromtimestamp(s.st_mtime).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "file_url": file_url,
                    "name": name[:-5],
                    "qvis_url": QVIS_URL
                    + "?"
                    + urlencode({"file": file_url})
                    + "#/sequence",
                    "size": s.st_size,
                }
            )
    return templates.TemplateResponse(
        "logs.html",
        {
            "logs": sorted(logs, key=lambda x: x["date"], reverse=True),
            "request": request,
        },
    )


async def padding(request):
    """
    Dynamically generated data, maximum 50MB.
    """
    size = min(50000000, request.path_params["size"])
    return PlainTextResponse("Z" * size)


async def stream_random_data(request):
    """
    Long-lived streaming endpoint that sends random data periodically.
    Query params:
      - duration: total duration in seconds (default: 0 = infinite, until client disconnects)
      - interval: interval between chunks in seconds (default: 1.0)
      - chunk_size: size of each random data chunk in bytes (default: 1024, max: 65536)
      - chunk_min: minimum chunk size for variable mode (default: 0 = disabled)
      - chunk_max: maximum chunk size for variable mode (default: 0 = disabled)
      - binary: if "1", send raw binary data instead of hex text (default: 0)
      - max_rate: maximum bytes per second (default: 0 = unlimited)
    """
    duration = int(request.query_params.get("duration", 0))  # 0 = infinite
    interval = max(0.01, float(request.query_params.get("interval", 1.0)))
    chunk_size = min(65536, int(request.query_params.get("chunk_size", 1024)))
    chunk_min = int(request.query_params.get("chunk_min", 0))
    chunk_max = int(request.query_params.get("chunk_max", 0))
    binary_mode = request.query_params.get("binary", "0") == "1"
    max_rate = int(request.query_params.get("max_rate", 0))  # bytes per second, 0 = unlimited

    # Validate variable chunk size params
    variable_chunks = chunk_min > 0 and chunk_max > chunk_min
    if variable_chunks:
        chunk_min = min(65536, chunk_min)
        chunk_max = min(65536, chunk_max)

    async def generate():
        start_time = asyncio.get_event_loop().time()
        chunk_count = 0
        total_bytes = 0
        rate_window_start = start_time
        rate_window_bytes = 0
        
        try:
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                # Only check duration if it's set (> 0)
                if duration > 0 and elapsed >= duration:
                    if not binary_mode:
                        yield f"\n[STREAM COMPLETE] Sent {chunk_count} chunks, {total_bytes} bytes over {elapsed:.1f}s\n".encode()
                    break
                
                # Determine chunk size (variable or fixed)
                current_chunk_size = random.randint(chunk_min, chunk_max) if variable_chunks else chunk_size
                
                # Generate data (binary or hex)
                if binary_mode:
                    data = secrets.token_bytes(current_chunk_size)
                else:
                    random_data = secrets.token_hex(current_chunk_size // 2)
                    chunk_count += 1
                    timestamp = datetime.datetime.now().isoformat()
                    preview = random_data[:64] + "..." if len(random_data) > 64 else random_data
                    size_info = f" ({current_chunk_size}B)" if variable_chunks else ""
                    data = f"[{timestamp}] Chunk {chunk_count}{size_info}: {preview}\n".encode()
                
                chunk_count += 1 if binary_mode else 0  # Already incremented for text mode
                total_bytes += len(data)
                rate_window_bytes += len(data)
                
                yield data
                
                # Bandwidth throttling
                if max_rate > 0:
                    now = asyncio.get_event_loop().time()
                    window_elapsed = now - rate_window_start
                    if window_elapsed > 0:
                        current_rate = rate_window_bytes / window_elapsed
                        if current_rate > max_rate:
                            # Need to slow down - calculate required delay
                            required_time = rate_window_bytes / max_rate
                            delay = required_time - window_elapsed
                            if delay > 0:
                                await asyncio.sleep(delay)
                    # Reset window periodically
                    if window_elapsed > 1.0:
                        rate_window_start = asyncio.get_event_loop().time()
                        rate_window_bytes = 0
                
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            # Client disconnected
            pass

    from starlette.responses import StreamingResponse
    media_type = "application/octet-stream" if binary_mode else "text/plain"
    return StreamingResponse(
        generate(),
        media_type=media_type,
        headers={
            "X-Stream-Duration": "infinite" if duration == 0 else str(duration),
            "X-Stream-Interval": str(interval),
            "X-Stream-Binary": "1" if binary_mode else "0",
            "X-Stream-Variable": "1" if variable_chunks else "0",
        }
    )


async def stream_bidirectional(request):
    """
    Bidirectional streaming endpoint - echoes back data sent by client.
    Client sends POST with streaming body, server echoes each chunk back.
    Query params:
      - delay: delay before echoing each chunk in seconds (default: 0)
    """
    delay = float(request.query_params.get("delay", 0))
    
    async def generate():
        chunk_count = 0
        total_bytes = 0
        start_time = asyncio.get_event_loop().time()
        
        try:
            async for chunk in request.stream():
                chunk_count += 1
                total_bytes += len(chunk)
                
                if delay > 0:
                    await asyncio.sleep(delay)
                
                # Echo back with metadata prefix
                timestamp = datetime.datetime.now().isoformat()
                header = f"[{timestamp}] Echo {chunk_count} ({len(chunk)}B): ".encode()
                yield header + chunk + b"\n"
            
            elapsed = asyncio.get_event_loop().time() - start_time
            yield f"\n[ECHO COMPLETE] Echoed {chunk_count} chunks, {total_bytes} bytes in {elapsed:.1f}s\n".encode()
        except asyncio.CancelledError:
            pass
    
    from starlette.responses import StreamingResponse
    return StreamingResponse(
        generate(),
        media_type="application/octet-stream",
        headers={"X-Stream-Mode": "bidirectional"}
    )


async def ws(websocket):
    """
    WebSocket echo endpoint.
    """
    if "chat" in websocket.scope["subprotocols"]:
        subprotocol = "chat"
    else:
        subprotocol = None
    await websocket.accept(subprotocol=subprotocol)

    try:
        while True:
            message = await websocket.receive_text()
            await websocket.send_text(message)
    except WebSocketDisconnect:
        pass


async def handle_root_post_upload(request):
    # Local imports are removed as os, aiofiles, PlainTextResponse, HTTPException
    # are available at module level.

    filepath = request.path_params["filepath"]
    if filepath.startswith("upload/"):
        filepath = filepath[len("upload/") :]
        # Handle case where path is just "upload/".
        if not filepath:  # e.g. if original path was "upload/"
            # An empty filepath is handled by later sanitization.
            pass

    filepath = filepath.lstrip("/")  # This line remains as per instructions

    abs_upload_dir = os.path.abspath(UPLOAD_DIR)

    save_path = os.path.join(abs_upload_dir, filepath)
    abs_save_path = os.path.abspath(save_path)

    # Security Check
    if os.path.commonprefix([abs_save_path, abs_upload_dir]) != abs_upload_dir:
        raise HTTPException(
            status_code=403, detail="Forbidden: Path traversal attempt."
        )

    try:
        parent_dir = os.path.dirname(abs_save_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        async with aiofiles.open(abs_save_path, "wb") as f:
            async for chunk in request.stream():
                await f.write(chunk)

        file_size = os.path.getsize(abs_save_path)
        response_text = (
            f"File '{filepath}' uploaded successfully ({file_size} bytes).\n"
            f"Saved at: {abs_save_path}"
        )
        return PlainTextResponse(response_text, status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error during root dynamic file upload for {filepath}: {e}")  # KEEP THIS
        # Log the full traceback for server-side debugging
        import traceback  # KEEP THIS (if not already module level)

        traceback.print_exc()  # KEEP THIS
        raise HTTPException(
            status_code=500, detail=f"Error uploading file '{filepath}': {str(e)}"
        )


async def wt(scope: Scope, receive: Receive, send: Send) -> None:
    """
    WebTransport echo endpoint.
    """
    # accept connection
    message = await receive()
    assert message["type"] == "webtransport.connect"
    await send({"type": "webtransport.accept"})

    # echo back received data
    while True:
        message = await receive()
        if message["type"] == "webtransport.datagram.receive":
            await send(
                {
                    "data": message["data"],
                    "type": "webtransport.datagram.send",
                }
            )
        elif message["type"] == "webtransport.stream.receive":
            await send(
                {
                    "data": message["data"],
                    "stream": message["stream"],
                    "type": "webtransport.stream.send",
                }
            )


starlette = Starlette(
    routes=[
        Route("/", homepage),
        Route("/{size:int}", padding),
        Route("/echo", echo, methods=["POST"]),  # Specific POST
        Route("/logs", logs),
        Route("/stream", stream_random_data),  # Long-lived streaming endpoint
        Route("/stream-echo", stream_bidirectional, methods=["POST"]),  # Bidirectional streaming
        WebSocketRoute("/ws", ws),
        # Add the new root-level POST handler here
        Route("/{filepath:path}", handle_root_post_upload, methods=["POST", "PUT"]),
        # Catch-all for GET (and others if not matched)
        Mount(STATIC_URL, StaticFiles(directory=STATIC_ROOT, html=True)),
    ]
)


async def app(scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] == "webtransport" and scope["path"] == "/wt":
        await wt(scope, receive, send)
    else:
        await starlette(scope, receive, send)
