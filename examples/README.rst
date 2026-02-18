Examples
========

After checking out the code using git you can run:

.. code-block:: console

   pip install . dnslib jinja2 starlette wsproto


HTTP/3
------

HTTP/3 server
.............

You can run the example server, which handles both HTTP/0.9 and HTTP/3:

.. code-block:: console

   python examples/http3_server.py --certificate tests/ssl_cert.pem --private-key tests/ssl_key.pem

HTTP/3 client
.............

You can run the example client to perform an HTTP/3 request:

.. code-block:: console

  python examples/http3_client.py --ca-certs tests/pycacert.pem https://localhost:4433/

To specify a local IP address for the client to bind to, use the ``--local-ip`` option.
For example, to bind to ``192.168.1.100`` (replace with your actual local IP):

.. code-block:: console

  python examples/http3_client.py --ca-certs tests/pycacert.pem --local-ip 192.168.1.100 https://localhost:4433/

The default local IP is "::" (any IPv6 or IPv4). For a full list of options, run:

.. code-block:: console

  python examples/http3_client.py --help

Alternatively you can perform an HTTP/0.9 request:

.. code-block:: console

  python examples/http3_client.py --ca-certs tests/pycacert.pem --legacy-http https://localhost:4433/

The client also supports QUIC v2. By default, the server will accept both QUIC v1 and v2.
You can instruct the client to only use QUIC v2 and fail if the server does not support it:

.. code-block:: console

  python examples/http3_client.py --ca-certs tests/pycacert.pem --strictly-v2 https://localhost:4433/

QUIC Version Negotiation (Upgrade and Downgrade)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The client and server support two distinct version negotiation mechanisms:

1. **Compatible Version Negotiation (RFC 9368)** — Version switch happens
   seamlessly inside the TLS handshake via ``version_information`` transport
   parameters. No extra round trip, no VN packet. The server accepts the
   client's Initial packet and they agree on a different version during the
   handshake.

2. **VN Packet (RFC 9000 §6)** — The server receives an Initial with a version
   it does not support at all, so it sends a Version Negotiation packet listing
   its supported versions. The client restarts the connection with a common
   version. This costs one extra round trip.

Compatible Version Negotiation (no VN packet)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Upgrade (v1 -> v2):** The client starts with QUIC v1 and negotiates to v2
inside the handshake. The server must support both versions (default).

.. code-block:: console

   # Server (default config already supports upgrade — prefers v2)
   python examples/http3_server.py --certificate tests/ssl_cert.pem --private-key tests/ssl_key.pem

   # Client: start with v1, negotiate to v2
   python examples/http3_client.py --ca-certs tests/pycacert.pem --upgrade-v2 https://localhost:4433/

**Downgrade (v2 -> v1):** The client starts with QUIC v2 and negotiates to v1
inside the handshake. The server must prefer v1.

.. code-block:: console

   # Server: prefer v1 to support downgrade
   python examples/http3_server.py --certificate tests/ssl_cert.pem --private-key tests/ssl_key.pem --prefer-v1

   # Client: start with v2, negotiate to v1
   python examples/http3_client.py --ca-certs tests/pycacert.pem --downgrade-v1 https://localhost:4433/

VN Packet-Based Version Negotiation (explicit VN packet)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In this mode, the server does **not** support the client's initial version, so
it sends a Version Negotiation packet. The client receives the VN packet, picks
a common version, and **restarts** the connection from scratch with that version.

**VN Upgrade (v1 -> v2):** The client sends an Initial with QUIC v1. The server
only supports v2, so it rejects with a VN packet listing v2. The client restarts
the connection using v2.

.. code-block:: console

   # Server: only support v2 (will send VN packet to v1 clients)
   python examples/http3_server.py --certificate tests/ssl_cert.pem --private-key tests/ssl_key.pem --only-v2

   # Client: send v1 Initial, expect VN packet, restart with v2
   python examples/http3_client.py --ca-certs tests/pycacert.pem --vn-upgrade-v2 https://localhost:4433/

**VN Downgrade (v2 -> v1):** The client sends an Initial with QUIC v2. The
server only supports v1, so it rejects with a VN packet listing v1. The client
restarts the connection using v1.

.. code-block:: console

   # Server: only support v1 (will send VN packet to v2 clients)
   python examples/http3_server.py --certificate tests/ssl_cert.pem --private-key tests/ssl_key.pem --only-v1

   # Client: send v2 Initial, expect VN packet, restart with v1
   python examples/http3_client.py --ca-certs tests/pycacert.pem --vn-downgrade-v1 https://localhost:4433/

Version Negotiation Flags Reference
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Client version flags** (mutually exclusive):

``--upgrade-v2``
    Compatible negotiation: start with QUIC v1, negotiate to v2 inside
    handshake (alias for ``--negotiate-v2``). Server must support both versions.

``--downgrade-v1``
    Compatible negotiation: start with QUIC v2, negotiate to v1 inside
    handshake. Server must prefer v1 (``--prefer-v1``).

``--vn-upgrade-v2``
    VN packet negotiation: send v1 Initial, server rejects with VN packet,
    client restarts with v2. Server must use ``--only-v2``.

``--vn-downgrade-v1``
    VN packet negotiation: send v2 Initial, server rejects with VN packet,
    client restarts with v1. Server must use ``--only-v1``.

``--negotiate-v2``
    Same as ``--upgrade-v2``.

``--strictly-v2``
    Only use QUIC v2. Fail if the server does not support it.

**Server version flags** (mutually exclusive):

``--prefer-v2``
    Prefer QUIC v2, also support v1 (this is the default).

``--prefer-v1``
    Prefer QUIC v1, also support v2 (for compatible downgrade scenarios).

``--only-v1``
    Only support QUIC v1 (for VN-based downgrade testing).

``--only-v2``
    Only support QUIC v2 (for VN-based upgrade testing).

After the handshake completes, the client logs the negotiated QUIC version and
indicates which mechanism was used:

- Compatible negotiation: ``Version changed from ... -> ... (compatible negotiation)``
- VN packet: ``Version changed from ... -> ... (via VN packet, incompatible negotiation)``

HelloRetryRequest (HRR)
~~~~~~~~~~~~~~~~~~~~~~~

HelloRetryRequest (HRR) is a server-initiated address validation mechanism
defined in the QUIC protocol (RFC 9000 §8.1). When HRR is enabled, the server
does **not** immediately proceed with the cryptographic handshake upon receiving
a client's Initial packet. Instead, it sends a **Retry packet** containing an
encrypted token (cookie) back to the client. The client must then re-send its
Initial packet with this token attached, proving that it can actually receive
packets at its claimed source address.

HRR works with both **QUIC v1** and **QUIC v2**, and can be freely combined
with any version negotiation mode (compatible negotiation or VN packet-based).

How HRR Works
^^^^^^^^^^^^^

The HRR mechanism adds one extra round trip before the TLS handshake begins:

::

   Client                                          Server
     |                                                |
     |  1. Initial (no token)                         |
     |  --------------------------------------------> |
     |                                                |
     |         2. Retry (encrypted token/cookie)      |
     |  <-------------------------------------------- |
     |                                                |
     |  3. Initial (with token from Retry)            |
     |  --------------------------------------------> |
     |                                                |
     |         4. TLS handshake proceeds normally     |
     |  <------------------------------------------->  |
     |                                                |

**Step 1:** The client sends its first Initial packet without any token.

**Step 2:** The server receives the Initial, generates a Retry packet containing
an encrypted cookie. This cookie encodes the client's IP address, port, the
original destination connection ID, and a retry source connection ID. The server
does **not** create any connection state at this point — it remains stateless.

**Step 3:** The client receives the Retry packet, extracts the token, and
re-sends a new Initial packet with the token included. The client also updates
its peer connection ID to the one provided in the Retry packet.

**Step 4:** The server validates the token by decrypting it and checking that
the client's address matches. If valid, the server creates the connection and
proceeds with the normal TLS handshake. If the token is invalid or the address
does not match, the packet is silently dropped.

Why Use HRR
^^^^^^^^^^^

- **DoS protection:** An attacker cannot complete a connection using a spoofed
  source IP address, because the Retry token is sent to the claimed address.
  The attacker would never receive it.

- **Amplification attack mitigation:** Without address validation, a server
  might send a large TLS handshake response to a spoofed address, amplifying
  the attacker's traffic. HRR ensures the server only invests resources in
  clients that have proven their address.

- **Stateless until validated:** The server does not allocate any per-connection
  state until the client returns with a valid token, making the Retry mechanism
  itself resistant to resource exhaustion attacks.

- **Transparent to the client:** The aioquic client handles Retry packets
  automatically. No special client-side code is needed — the ``--expect-hrr``
  flag simply adds diagnostic logging.

HRR vs ``--retry``
^^^^^^^^^^^^^^^^^^^

The ``--send-hrr`` and ``--retry`` flags both enable the same underlying
mechanism: QUIC Retry packets via ``QuicRetryTokenHandler``. The difference
is in logging and intent:

.. list-table::
   :header-rows: 1
   :widths: 20 40 40

   * - Aspect
     - ``--retry``
     - ``--send-hrr``
   * - Purpose
     - General retry for new connections
     - Explicit HelloRetryRequest for address validation
   * - Mechanism
     - QUIC Retry packet with encrypted cookie
     - QUIC Retry packet with encrypted cookie (identical)
   * - Server logging
     - ``[server] Retry enabled: ...``
     - ``[server] HRR (HelloRetryRequest) enabled: ...``
   * - Logs QUIC versions
     - No
     - Yes — logs which QUIC versions are supported
   * - Can combine
     - Yes (with ``--send-hrr``, version flags)
     - Yes (with ``--retry``, version flags)

If both ``--retry`` and ``--send-hrr`` are specified, the HRR logging takes
precedence (since both enable the same retry mechanism internally).

HRR with QUIC v1 and v2 — All Scenarios
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

HRR can be combined with every version configuration. Below are all supported
scenarios with full command-line examples.

**Scenario 1: HRR with default version (both v1 and v2, prefer v2)**

The server supports both versions and prefers v2 (default behavior). The client
connects without specifying a version preference. HRR adds address validation
before the handshake.

.. code-block:: console

   # Server: HRR with default version config (v1 + v2, prefers v2)
   python examples/http3_server.py \
     --certificate tests/ssl_cert.pem --private-key tests/ssl_key.pem \
     --send-hrr

   # Client: expect HRR, default version
   python examples/http3_client.py \
     --ca-certs tests/pycacert.pem \
     --expect-hrr \
     https://localhost:4433/

Expected output::

   [server] HRR (HelloRetryRequest) enabled: server will send retry packets for client address validation
   [server] Supported QUIC versions: QUIC v2, QUIC v1
   [client] Expecting HRR (HelloRetryRequest) from server: server should send retry packet for address validation
   [client] HRR (HelloRetryRequest) completed: server sent retry packet for address validation
   [client] Handshake complete. Negotiated QUIC version: QUIC v2

**Scenario 2: HRR with QUIC v1 only**

Both server and client are restricted to QUIC v1. HRR validates the client
address before the v1 handshake.

.. code-block:: console

   # Server: only v1, with HRR
   python examples/http3_server.py \
     --certificate tests/ssl_cert.pem --private-key tests/ssl_key.pem \
     --send-hrr --only-v1

   # Client: default (will use v1 since server only supports v1)
   python examples/http3_client.py \
     --ca-certs tests/pycacert.pem \
     --expect-hrr \
     https://localhost:4433/

Expected output::

   [server] Only supporting QUIC v1 (will send VN packet to v2 clients)
   [server] HRR (HelloRetryRequest) enabled: server will send retry packets for client address validation
   [client] HRR (HelloRetryRequest) completed: server sent retry packet for address validation
   [client] Handshake complete. Negotiated QUIC version: QUIC v1

**Scenario 3: HRR with QUIC v2 only**

Both server and client are restricted to QUIC v2. HRR validates the client
address before the v2 handshake.

.. code-block:: console

   # Server: only v2, with HRR
   python examples/http3_server.py \
     --certificate tests/ssl_cert.pem --private-key tests/ssl_key.pem \
     --send-hrr --only-v2

   # Client: strictly v2, expect HRR
   python examples/http3_client.py \
     --ca-certs tests/pycacert.pem \
     --expect-hrr --strictly-v2 \
     https://localhost:4433/

Expected output::

   [server] Only supporting QUIC v2 (will send VN packet to v1 clients)
   [server] HRR (HelloRetryRequest) enabled: server will send retry packets for client address validation
   [client] HRR (HelloRetryRequest) completed: server sent retry packet for address validation
   [client] Handshake complete. Negotiated QUIC version: QUIC v2

**Scenario 4: HRR + Compatible Upgrade (v1 → v2)**

The client starts with QUIC v1, negotiates to v2 inside the TLS handshake
(compatible version negotiation). HRR validates the address before negotiation
begins.

.. code-block:: console

   # Server: default (supports v1 + v2, prefers v2), with HRR
   python examples/http3_server.py \
     --certificate tests/ssl_cert.pem --private-key tests/ssl_key.pem \
     --send-hrr

   # Client: upgrade v1 -> v2, expect HRR
   python examples/http3_client.py \
     --ca-certs tests/pycacert.pem \
     --expect-hrr --upgrade-v2 \
     https://localhost:4433/

Expected output::

   [client] Upgrading (compatible): starting with QUIC v1, will negotiate to QUIC v2 (no VN packet)
   [client] Expecting HRR (HelloRetryRequest) from server: server should send retry packet for address validation
   [client] HRR (HelloRetryRequest) completed: server sent retry packet for address validation
   [client] Handshake complete. Negotiated QUIC version: QUIC v2
   [client] Version changed from QUIC v1 -> QUIC v2 (compatible negotiation, no VN packet)

**Scenario 5: HRR + Compatible Downgrade (v2 → v1)**

The client starts with QUIC v2, negotiates to v1 inside the TLS handshake.
HRR validates the address before negotiation begins.

.. code-block:: console

   # Server: prefer v1, with HRR
   python examples/http3_server.py \
     --certificate tests/ssl_cert.pem --private-key tests/ssl_key.pem \
     --send-hrr --prefer-v1

   # Client: downgrade v2 -> v1, expect HRR
   python examples/http3_client.py \
     --ca-certs tests/pycacert.pem \
     --expect-hrr --downgrade-v1 \
     https://localhost:4433/

Expected output::

   [client] Downgrading (compatible): starting with QUIC v2, will negotiate to QUIC v1 (no VN packet)
   [client] Expecting HRR (HelloRetryRequest) from server: server should send retry packet for address validation
   [client] HRR (HelloRetryRequest) completed: server sent retry packet for address validation
   [client] Handshake complete. Negotiated QUIC version: QUIC v1
   [client] Version changed from QUIC v2 -> QUIC v1 (compatible negotiation, no VN packet)

**Scenario 6: HRR + VN Packet Upgrade (v1 → v2)**

The client sends an Initial with v1 to a server that only supports v2. The
server first sends a **Version Negotiation packet** (because v1 is not
supported). The client restarts with v2, and then the server sends a **Retry
packet** (HRR) for address validation. This scenario involves two extra round
trips: one for VN and one for HRR.

::

   Client                                          Server (--only-v2 --send-hrr)
     |                                                |
     |  1. Initial (QUIC v1)                          |
     |  --------------------------------------------> |
     |                                                |
     |         2. Version Negotiation (offers v2)     |
     |  <-------------------------------------------- |
     |                                                |
     |  3. Initial (QUIC v2, no token)                |
     |  --------------------------------------------> |
     |                                                |
     |         4. Retry (encrypted token)             |
     |  <-------------------------------------------- |
     |                                                |
     |  5. Initial (QUIC v2, with token)              |
     |  --------------------------------------------> |
     |                                                |
     |         6. TLS handshake proceeds              |
     |  <------------------------------------------->  |
     |                                                |

.. code-block:: console

   # Server: only v2, with HRR
   python examples/http3_server.py \
     --certificate tests/ssl_cert.pem --private-key tests/ssl_key.pem \
     --send-hrr --only-v2

   # Client: VN upgrade v1 -> v2, expect HRR
   python examples/http3_client.py \
     --ca-certs tests/pycacert.pem \
     --expect-hrr --vn-upgrade-v2 \
     https://localhost:4433/

Expected output::

   [client] Upgrading (with VN packet): sending Initial with QUIC v1, expecting VN packet from server, will restart with QUIC v2
   [client] Expecting HRR (HelloRetryRequest) from server: server should send retry packet for address validation
   [client] HRR (HelloRetryRequest) completed: server sent retry packet for address validation
   [client] Handshake complete. Negotiated QUIC version: QUIC v2
   [client] Version changed from QUIC v1 -> QUIC v2 (via VN packet, incompatible negotiation)

**Scenario 7: HRR + VN Packet Downgrade (v2 → v1)**

The client sends an Initial with v2 to a server that only supports v1. The
server sends a VN packet, client restarts with v1, then server sends a Retry
(HRR).

.. code-block:: console

   # Server: only v1, with HRR
   python examples/http3_server.py \
     --certificate tests/ssl_cert.pem --private-key tests/ssl_key.pem \
     --send-hrr --only-v1

   # Client: VN downgrade v2 -> v1, expect HRR
   python examples/http3_client.py \
     --ca-certs tests/pycacert.pem \
     --expect-hrr --vn-downgrade-v1 \
     https://localhost:4433/

Expected output::

   [client] Downgrading (with VN packet): sending Initial with QUIC v2, expecting VN packet from server, will restart with QUIC v1
   [client] Expecting HRR (HelloRetryRequest) from server: server should send retry packet for address validation
   [client] HRR (HelloRetryRequest) completed: server sent retry packet for address validation
   [client] Handshake complete. Negotiated QUIC version: QUIC v1
   [client] Version changed from QUIC v2 -> QUIC v1 (via VN packet, incompatible negotiation)

HRR Flags Reference
^^^^^^^^^^^^^^^^^^^^

``--send-hrr`` *(server)*
    Enable HelloRetryRequest. The server sends a QUIC Retry packet containing
    an encrypted cookie (generated by ``QuicRetryTokenHandler``) for every new
    Initial packet that arrives without a valid token. The cookie encodes:

    - The client's IP address and port
    - The original destination connection ID
    - A retry source connection ID

    The client must re-send its Initial with this cookie to prove address
    ownership. Only then does the server allocate connection state and proceed
    with the TLS handshake. Works with QUIC v1, QUIC v2, or both. Can be
    combined with any version flag (``--only-v1``, ``--only-v2``,
    ``--prefer-v1``, ``--prefer-v2``) and with ``--retry``.

``--expect-hrr`` *(client)*
    Enable HRR-aware diagnostic logging. At startup, the client prints a
    message indicating it expects HRR from the server. After the handshake
    completes, the client inspects the connection's internal state to determine
    whether a Retry packet was received:

    - If HRR occurred: ``[client] HRR (HelloRetryRequest) completed: server sent retry packet for address validation``
    - If no HRR: ``[client] HRR expected but no retry packet was received from server``

    This flag is purely informational — the client always handles Retry packets
    automatically regardless of whether ``--expect-hrr`` is specified. It can
    be combined with any version flag (``--upgrade-v2``, ``--downgrade-v1``,
    ``--vn-upgrade-v2``, ``--vn-downgrade-v1``, ``--strictly-v2``).

HRR Combination Matrix
^^^^^^^^^^^^^^^^^^^^^^^

The following table summarizes all tested HRR + version combinations:

.. list-table::
   :header-rows: 1
   :widths: 30 25 25 20

   * - Scenario
     - Server Flags
     - Client Flags
     - Extra RTTs
   * - HRR only (default versions)
     - ``--send-hrr``
     - ``--expect-hrr``
     - +1 (Retry)
   * - HRR + v1 only
     - ``--send-hrr --only-v1``
     - ``--expect-hrr``
     - +1 (Retry)
   * - HRR + v2 only
     - ``--send-hrr --only-v2``
     - ``--expect-hrr --strictly-v2``
     - +1 (Retry)
   * - HRR + upgrade (v1→v2)
     - ``--send-hrr``
     - ``--expect-hrr --upgrade-v2``
     - +1 (Retry)
   * - HRR + downgrade (v2→v1)
     - ``--send-hrr --prefer-v1``
     - ``--expect-hrr --downgrade-v1``
     - +1 (Retry)
   * - HRR + VN upgrade (v1→v2)
     - ``--send-hrr --only-v2``
     - ``--expect-hrr --vn-upgrade-v2``
     - +2 (VN + Retry)
   * - HRR + VN downgrade (v2→v1)
     - ``--send-hrr --only-v1``
     - ``--expect-hrr --vn-downgrade-v1``
     - +2 (VN + Retry)

Note: Attempting to use methods like PUT or POST (e.g., for file uploads via `--upload-file`)
with the `--legacy-http` option is not supported by the example server.
The server will respond with an error message and close the stream.
HTTP/0.9 is primarily designed for simple GET requests.

You can also open a WebSocket over HTTP/3:

.. code-block:: console

  python examples/http3_client.py --ca-certs tests/pycacert.pem wss://localhost:4433/ws

The client also supports creating multiple streams for a request (if the URL scheme is HTTPS).
This can be controlled with the ``--num-streams`` argument:

.. code-block:: console

  python examples/http3_client.py --ca-certs tests/pycacert.pem https://localhost:4433/ --num-streams 10

If ``--num-streams`` is set to a value significantly higher than the server's
advertised concurrent stream limit (typically 128 by default for `aioquic`),
the client may show a warning: *"HttpClient has ... concurrent requests pending.
Further stream creations might be delayed due to peer stream limits."*
This indicates that the client is queuing requests locally until the server
increases its stream limit via ``MAX_STREAMS`` frames.

File Uploads (using PUT)
~~~~~~~~~~~~~~~~~~~~~~~~

The example client can also upload files to the server using the `PUT` method.
The server must be configured with an upload directory, and the path in the URL
will dictate where the file is saved within that directory.

First, ensure the server is running and configured with an upload directory.
For example, to save uploaded files into a directory named `my_server_uploads`
(created in your current working directory):

.. code-block:: console

   python examples/http3_server.py --certificate tests/ssl_cert.pem --private-key tests/ssl_key.pem --upload-dir ./my_server_uploads

Then, use `http3_client.py` with the `--upload-file` option to send a file.
The URL path will determine the save location and name on the server, relative
to the server's configured upload directory.

.. code-block:: console

  python examples/http3_client.py --ca-certs tests/ssl_cert.pem --upload-file ./localfile.txt https://localhost:4433/path/on_server/remote_filename.txt

This command will upload `./localfile.txt` from your machine, and the server
will save it as `path/on_server/remote_filename.txt` inside the
`./my_server_uploads` directory (creating subdirectories like `path/on_server/`
if they don't exist).

*Important Note on Headers:* Currently, `http3_client.py` sends no `Content-Type`
or `Content-Disposition` headers for uploads. This is a workaround for a
suspected issue in the underlying `aioquic` library's H3 header processing.
The server uses the URL path for the filename and infers the content type if needed.

You can also upload files using `curl` with the `PUT` method (which `curl -T` uses):

.. code-block:: console

  curl -T ./localfile.txt https://localhost:4433/path/on_server/remote_filename.txt --http3 -k

(The `-k` flag for `curl` allows it to work with self-signed certificates like the
example `ssl_cert.pem`.)

HTTP/3 Streaming
~~~~~~~~~~~~~~~~

The client and server support long-lived HTTP/3 streaming for continuous data
transfer testing over QUIC. This is useful for evaluating QUIC/HTTP3 behavior
under sustained load, measuring throughput, testing connection stability over
extended periods, and verifying protocol robustness with fuzz data.

There are two streaming modes:

1. **Unidirectional (``--stream``)**: The server generates and pushes random
   data chunks to the client. The client receives and optionally displays the
   data without saving to disk. This is useful for testing downstream throughput
   and server-side streaming behavior.

2. **Bidirectional (``--stream-bidi``)**: The client sends data chunks to the
   server via a POST request to the ``/stream-echo`` endpoint, and the server
   echoes each chunk back. This is useful for testing round-trip latency,
   upload/download symmetry, and full-duplex streaming behavior.

Getting Started with Streaming
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

First, start the HTTP/3 server:

.. code-block:: console

   python examples/http3_server.py --certificate tests/ssl_cert.pem --private-key tests/ssl_key.pem

**Basic unidirectional streaming** — server pushes 1024-byte chunks every second:

.. code-block:: console

  python examples/http3_client.py --insecure --stream https://localhost:4433/stream

**Basic bidirectional streaming** — client sends, server echoes back:

.. code-block:: console

  python examples/http3_client.py --insecure --stream-bidi https://localhost:4433/stream-echo

Both modes run indefinitely by default (until Ctrl+C). Use ``--stream-duration``
to limit the session length.

Streaming Options Reference
^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Mode Selection:**

``--stream``
    Enable unidirectional streaming mode. The server pushes random data chunks
    to the client continuously. The client connects to the ``/stream`` endpoint
    on the server.

``--stream-bidi``
    Enable bidirectional streaming mode. The client sends random data chunks
    to the server's ``/stream-echo`` endpoint, and the server echoes each chunk
    back to the client. Cannot be combined with ``--stream``.

**Data Control:**

``--stream-chunk-size <bytes>``
    Set the size of each data chunk in bytes. Default: ``1024``.

    .. code-block:: console

      python examples/http3_client.py --insecure --stream --stream-chunk-size 8192 https://localhost:4433/stream

``--stream-chunk-vary <min,max>``
    Use variable (randomized) chunk sizes instead of a fixed size. The actual
    chunk size for each transmission is randomly chosen between ``min`` and
    ``max`` bytes. This overrides ``--stream-chunk-size`` and is useful for
    simulating realistic traffic patterns where packet sizes vary.

    .. code-block:: console

      python examples/http3_client.py --insecure --stream --stream-chunk-vary 256,8192 https://localhost:4433/stream

``--stream-interval <seconds>``
    Set the time interval between sending/receiving data chunks, in seconds.
    Default: ``1.0``. Use smaller values for higher throughput testing.

    .. code-block:: console

      python examples/http3_client.py --insecure --stream --stream-interval 0.1 https://localhost:4433/stream

``--stream-duration <seconds>``
    Limit the streaming session to the specified number of seconds. Default:
    ``0`` (infinite — runs until Ctrl+C). For example, to stream for exactly
    5 minutes:

    .. code-block:: console

      python examples/http3_client.py --insecure --stream --stream-duration 300 https://localhost:4433/stream

``--stream-binary``
    Use raw binary mode instead of hex-encoded text output. In binary mode,
    the client displays chunk statistics (size, count) instead of decoded text.
    This provides higher throughput since there is no encoding/decoding overhead.

    .. code-block:: console

      python examples/http3_client.py --insecure --stream --stream-binary https://localhost:4433/stream

**Throughput and Parallelism:**

``--stream-max-rate <bytes/sec>``
    Throttle bandwidth to the specified maximum rate in bytes per second.
    Default: ``0`` (unlimited). The client enforces this by inserting delays
    between chunks. Useful for simulating constrained network conditions.

    Example — limit to 100 KB/s:

    .. code-block:: console

      python examples/http3_client.py --insecure --stream --stream-max-rate 102400 https://localhost:4433/stream

``--num-streams <N>``
    Open N parallel streams simultaneously over the same QUIC connection.
    Default: ``1``. Each stream operates independently, sending/receiving its
    own data. Streams are labeled ``[S1]``, ``[S2]``, etc. in the output.
    This is useful for testing multiplexing behavior and concurrent stream
    handling.

    Example — 10 parallel bidirectional streams:

    .. code-block:: console

      python examples/http3_client.py --insecure --stream-bidi --num-streams 10 https://localhost:4433/stream-echo

**Output Control:**

``--stream-quiet``
    Suppress printing of received data to the console. The client will still
    log summary statistics (total bytes, throughput) via the logger. This is
    recommended for high-throughput testing where console output becomes a
    bottleneck.

    .. code-block:: console

      python examples/http3_client.py --insecure --stream --stream-quiet https://localhost:4433/stream

**Reliability:**

``--stream-reconnect <retries>``
    Automatically reconnect if the streaming connection drops. The client will
    retry up to the specified number of times, with a 1-second delay between
    attempts. Default: ``0`` (disabled — connection errors are raised
    immediately). This is essential for long-running sessions that may
    experience intermittent network issues.

    Example — auto-reconnect up to 10 times:

    .. code-block:: console

      python examples/http3_client.py --insecure --stream --stream-reconnect 10 https://localhost:4433/stream

**Fuzz Testing:**

``--stream-fuzz``
    Send malicious/fuzz test data instead of random bytes. Only works with
    ``--stream-bidi`` mode. The fuzz data includes:

    - Invalid UTF-8 byte sequences
    - Control characters and null bytes
    - Overlong encodings
    - Boundary values and edge-case payloads
    - Mixed valid/invalid data

    This is useful for testing server robustness and ensuring the echo endpoint
    handles malformed data gracefully without crashing.

    Example — fuzz test for 60 seconds:

    .. code-block:: console

      python examples/http3_client.py --insecure \
        --stream-bidi --stream-fuzz \
        --stream-duration 60 \
        https://localhost:4433/stream-echo

Connection Stability for Long-Running Sessions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When running streaming sessions for extended periods (hours or days), connection
drops can occur due to:

- **QUIC idle timeout**: If no data is exchanged within the idle timeout window,
  the QUIC connection is closed. The default is 300 seconds (5 minutes).
- **NAT/firewall mapping expiry**: Network Address Translation (NAT) devices and
  stateful firewalls maintain mapping tables for UDP flows. These mappings
  typically expire after 30–120 seconds of inactivity, causing the connection
  to silently break.
- **Memory leaks**: Stream handler resources that are not cleaned up after
  completion can accumulate over time. The client now automatically cleans up
  stream handlers in ``finally`` blocks to prevent this.

The following options address these issues:

``--idle-timeout <seconds>``
    Set the QUIC idle timeout in seconds. Default: ``300`` (5 minutes).
    **Both the client and server must be configured with matching or compatible
    values.** For long sessions, set this to a high value such as ``86400``
    (24 hours). Note that if data is continuously flowing, the idle timer is
    reset on every packet, so the timeout only matters during periods of
    inactivity.

    Server:

    .. code-block:: console

       python examples/http3_server.py \
         --certificate tests/ssl_cert.pem --private-key tests/ssl_key.pem \
         --idle-timeout 86400

    Client:

    .. code-block:: console

      python examples/http3_client.py --insecure --idle-timeout 86400 --stream https://localhost:4433/stream

``--keepalive <seconds>``
    Send QUIC PING frames at the specified interval to keep the connection
    alive. Default: ``0`` (disabled). When enabled, the client sends a PING
    frame every N seconds in the background, which:

    - Prevents the QUIC idle timeout from firing during brief pauses in data.
    - Refreshes NAT/firewall UDP mapping tables so the connection is not
      silently dropped.
    - Has minimal bandwidth overhead (each PING is a few bytes).

    Recommended value: ``30`` seconds (well within typical NAT timeout windows).

    .. code-block:: console

      python examples/http3_client.py --insecure --keepalive 30 --stream https://localhost:4433/stream

**Recommended configuration for 24-hour streaming sessions:**

.. code-block:: console

   # Server
   python examples/http3_server.py \
     --certificate tests/ssl_cert.pem --private-key tests/ssl_key.pem \
     --idle-timeout 86400

   # Client
   python examples/http3_client.py --insecure \
     --idle-timeout 86400 \
     --keepalive 30 \
     --stream-reconnect 5 \
     --stream-bidi \
     --stream-duration 0 \
     --stream-chunk-vary 512,8192 \
     --stream-quiet \
     --num-streams 4 \
     https://localhost:4433/stream-echo

This configuration:

- Sets a 24-hour idle timeout on both ends.
- Sends keepalive PINGs every 30 seconds to maintain NAT mappings.
- Auto-reconnects up to 5 times on any connection failure.
- Uses 4 parallel bidirectional streams with variable chunk sizes.
- Suppresses data output for maximum throughput.

IPv6 Support
^^^^^^^^^^^^

All streaming features work identically over IPv4 and IPv6. The client
automatically detects and handles IPv6 addresses, including IPv4-mapped IPv6
addresses (e.g., ``::ffff:192.168.1.1``).

**Streaming over IPv6 loopback:**

.. code-block:: console

  python examples/http3_client.py --insecure --local-ip "::1" --stream https://[::1]:4433/stream

**Bidirectional streaming over IPv6:**

.. code-block:: console

  python examples/http3_client.py --insecure \
    --local-ip "::1" \
    --stream-bidi \
    https://[::1]:4433/stream-echo

The default ``--local-ip`` is ``::`` which binds to all available IPv4 and IPv6
interfaces. When connecting to an IPv6 server address, enclose the address in
square brackets in the URL (e.g., ``https://[::1]:4433/``).

Chromium and Chrome usage
.........................

Some flags are needed to allow Chrome to communicate with the demo server. Most are not necessary in a more production-oriented deployment with HTTP/2 fallback and a valid certificate, as demonstrated on https://quic.aiortc.org/

- The `--ignore-certificate-errors-spki-list`_ instructs Chrome to accept the demo TLS certificate, even though it is not signed by a known certificate authority. If you use your own valid certificate, you do not need this flag.
- The `--origin-to-force-quic-on` forces Chrome to communicate using HTTP/3. This is needed because the demo server *only* provides an HTTP/3 server. Usually Chrome will connect to an HTTP/2 or HTTP/1.1 server and "discover" the server supports HTTP/3 through an Alt-Svc header.
- The `--enable-experimental-web-platform-features`_ enables WebTransport, because the specifications and implementation are not yet finalised. For HTTP/3 itself, you do not need this flag.

To access the demo server running on the local machine, launch Chromium or Chrome as follows:

.. code:: bash

  google-chrome \
    --enable-experimental-web-platform-features \
    --ignore-certificate-errors-spki-list=BSQJ0jkQ7wwhR7KvPZ+DSNk2XTZ/MS6xCbo9qu++VdQ= \
    --origin-to-force-quic-on=localhost:4433 \
    https://localhost:4433/

The fingerprint passed to the `--ignore-certificate-errors-spki-list`_ option is obtained by running:

.. code:: bash

  openssl x509 -in tests/ssl_cert.pem -pubkey -noout | \
    openssl pkey -pubin -outform der | \
    openssl dgst -sha256 -binary | \
    openssl enc -base64

WebTransport
............

The demo server runs a :code:`WebTransport` echo service at `/wt`. You can connect by opening Developer Tools and running the following:

.. code:: javascript

  let transport = new WebTransport('https://localhost:4433/wt');
  await transport.ready;

  let stream = await transport.createBidirectionalStream();
  let reader = stream.readable.getReader();
  let writer = stream.writable.getWriter();

  await writer.write(new Uint8Array([65, 66, 67]));
  let received = await reader.read();
  await transport.close();

  console.log('received', received);

If all is well you should see:

.. image:: https://user-images.githubusercontent.com/1567624/126713050-e3c0664c-b0b9-4ac8-a393-9b647c9cab6b.png


DNS over QUIC
-------------

By default the server will use the `Google Public DNS`_ service, you can
override this with the ``--resolver`` argument.

By default the server will listen for requests on port 853, which requires
a privileged user. You can override this with the `--port` argument.

You can run the server locally using:

.. code-block:: console

    python examples/doq_server.py --certificate tests/ssl_cert.pem --private-key tests/ssl_key.pem --port 8053

You can then run the client with a specific query:

.. code-block:: console

    python examples/doq_client.py --ca-certs tests/pycacert.pem --query-type A --query-name quic.aiortc.org --port 8053

Please note that for real-world usage you will need to obtain a valid TLS certificate.

.. _Google Public DNS: https://developers.google.com/speed/public-dns
.. _--enable-experimental-web-platform-features: https://peter.sh/experiments/chromium-command-line-switches/#enable-experimental-web-platform-features
.. _--ignore-certificate-errors-spki-list: https://peter.sh/experiments/chromium-command-line-switches/#ignore-certificate-errors-spki-list


Performance Considerations for `http3_client.py`
------------------------------------------------

When using `http3_client.py` for sending a large number of requests or streams
(e.g., using `--num-streams` with a high value), be aware of the following:

*   **Python's Async Capabilities**: While `asyncio` provides excellent concurrency,
    Python's Global Interpreter Lock (GIL) means that CPU-bound work in one part
    of the client (e.g., intense data processing before sending, if added by a user)
    might still impact the overall throughput of network operations. For I/O-bound
    work like sending and receiving HTTP requests, `aioquic` and `asyncio` are
    very efficient.

*   **Stream and Connection Limits**: QUIC connections have built-in limits on
    concurrent streams (typically advertised by the server, defaulting to 128
    bidirectional streams in `aioquic` if the server doesn't specify otherwise)
    and flow control limits for data. If the client attempts to open more streams
    than the server currently allows, `aioquic` will queue these requests.
    The client's warning, *"HttpClient has ... concurrent requests pending..."*,
    can indicate that it's waiting for the server to increase stream limits via
    `MAX_STREAMS` frames.

*   **Single Client Instance**: The `http3_client.py` example runs as a single
    Python process. To fully saturate very high-bandwidth links or to maximize
    requests per second to a high-capacity server, you might need to run
    multiple instances of the client, potentially distributed across different CPU
    cores or even machines.

*   **Underlying `aioquic` Library**: `aioquic` itself is a performant library.
    Most bottlenecks in typical use cases with this example client are more likely
    to be related to application logic, Python's single-process nature for
    CPU-bound tasks, or network/server limitations rather than the core QUIC
    protocol handling in `aioquic`.

*   **Logging Verbosity**: Verbose logging (`-v`) can have a performance impact,
    especially with many concurrent streams. For performance testing, consider
    running with default (INFO) or minimal logging.

This example client is designed for demonstration and testing of `aioquic`
features rather than as a production-grade load generation tool.
