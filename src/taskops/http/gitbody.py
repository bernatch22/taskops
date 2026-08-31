"""How a git request BODY reaches the door — the HTTP framing half of
`gitpack.py`, split out where the seam owns no git at all: this module sees
headers and a byte stream, never a service name or a repo.

**`rpc.MAX_BODY` does not apply here, `CAP` does.** A packfile is not a board
call — 4 MiB would refuse any real repo seed — but an unbounded body is a
memory grenade, so the cap is 256 MiB: this whole repository's history a
hundred times over and any believable card branch by three orders of
magnitude, while bounding what one hostile request can pin in RAM. Not
configurable, on purpose: a knob would be tuned upward the first time it is
hit, and a push that big is a fault to look at, not to accommodate.

Git sends large push bodies chunked (no Content-Length above http.postBuffer)
and small upload-pack bodies gzipped, so both encodings are honoured —
stdlib `http.server` decodes neither — and the cap holds on the DECODED size.
Chunked decoding is HTTP/1.1's framing, not git's: reimplementing pkt-line
stays banned (§11), this is the transport underneath it.
"""

from __future__ import annotations

import gzip
from io import BufferedIOBase
from email.message import Message

from .._errors import BadRequest

CAP = 256 * 1024 * 1024

TOO_BIG = (
    f"that push is over {CAP // (1024 * 1024)} MiB, which no card branch is — "
    "the cap bounds a hostile body, not honest work. Split the history or ask "
    "the board's owner to seed the repository on the host directly."
)


def read(headers: Message, rfile: BufferedIOBase) -> bytes:
    """The request body, whichever way git sent it, bounded by CAP throughout."""
    if headers.get("Transfer-Encoding", "").lower() == "chunked":
        data = _chunked(rfile)
    else:
        length = int(headers.get("Content-Length", "0") or 0)
        if length > CAP:
            raise BadRequest(TOO_BIG)
        data = rfile.read(length)
    if headers.get("Content-Encoding", "") == "gzip":
        data = gzip.decompress(data)
        if len(data) > CAP:
            raise BadRequest(TOO_BIG)
    return data


def _chunked(rfile: BufferedIOBase) -> bytes:
    total, parts = 0, list[bytes]()
    while True:
        line = rfile.readline(64)
        try:
            size = int(line.split(b";")[0].strip() or b"0", 16)
        except ValueError as err:
            raise BadRequest("malformed chunked body") from err
        if size == 0:
            while rfile.readline(1024) not in (b"\r\n", b"\n", b""):
                pass  # trailers, permitted and ignored
            return b"".join(parts)
        total += size
        if total > CAP:
            raise BadRequest(TOO_BIG)
        parts.append(rfile.read(size))
        rfile.read(2)  # the chunk's own CRLF
