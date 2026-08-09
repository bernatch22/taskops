"""The ssh public-key grammar: parse a `.pub` line, name a key, name a person.

Split from `server.py` along a real seam — *what a key IS* versus *who holds
one and where that is written* — and the 200-line budget
(`tests/test_architecture.py`) is what forced the question. Everything here is
PURE: no SQL, no file, no subprocess. Naming a key with `ssh-keygen -l` would
have been a subprocess in `store/`, which the layering forbids and which would
have made the store unusable without OpenSSH on the path; the fingerprint is
the same string, computed with `hashlib`.
"""

from __future__ import annotations

from base64 import b64decode, b64encode
from hashlib import sha256
from binascii import Error as BinasciiError

from .._errors import BadRequest

KEY_TYPES = (
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "sk-ssh-ed25519@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
)

NAME_OK = set("abcdefghijklmnopqrstuvwxyz0123456789._-")


def parse_key(line: str) -> tuple[str, str]:
    """(type, base64) out of an `id_ed25519.pub`. The comment is dropped: it is
    a label on the reader's machine, not part of the identity."""
    parts = line.strip().split()
    if len(parts) < 2 or parts[0] not in KEY_TYPES:
        kinds = ", ".join(KEY_TYPES[:3])
        raise BadRequest(
            f"that is not an ssh public key ({kinds}, …) — "
            "pass the contents of ~/.ssh/id_ed25519.pub, not the private key"
        )
    try:
        b64decode(parts[1], validate=True)
    except (BinasciiError, ValueError) as err:
        raise BadRequest(f"that public key's body is not valid base64: {err}") from err
    return parts[0], parts[1]


def fingerprint(blob: str) -> str:
    """OpenSSH's own `SHA256:<base64, unpadded>` — the string `ssh-keygen -l`
    prints, computed here so no subprocess is needed to name a key."""
    digest = sha256(b64decode(blob, validate=True)).digest()
    return "SHA256:" + b64encode(digest).decode().rstrip("=")


def principal_name(name: str) -> str:
    """A principal is a person or a machine, named like an actor's own name."""
    if not name or len(name) > 40 or not set(name) <= NAME_OK:
        raise BadRequest(f"principal {name!r} must be 1-40 chars of [a-z0-9._-]")
    return name
