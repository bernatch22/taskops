"""SSHSIG: sign a challenge with an ssh key, verify one against `allowed_signers`.

The same mechanism git uses for signed commits, run the same way — OpenSSH's
own `ssh-keygen -Y sign` / `-Y verify`. That is the whole reason this file sits
in `gitwork/`: it is a SUBPROCESS capability of the client's machine, and
`gitwork/run.py` is the one module allowed to start a process
(`tests/test_architecture.py::test_subprocess_only_in_gitwork_run`).

    client:  ssh-keygen -Y sign   -f ~/.ssh/id_ed25519 -n taskops -    < payload
    server:  ssh-keygen -Y verify -f <root>/allowed_signers -I <who> -n taskops -s <sig>

ZERO pip dependencies and no hand-rolled crypto — that is the milestone's first
rule. What the payload IS lives in `core/scope.py`'s neighbour
`core/challenge.py`, pure, so both sides compute the identical bytes.

KNOWN LIMIT, stated and not solved: `-Y sign` wants the private key FILE, so a
setup whose key exists only inside a running ssh-agent cannot sign yet
(`NO_KEYFILE` below is that sentence). Teaching taskops the agent protocol is a
different card; refusing clearly is this one.

A passphrase-protected key does not hang either: stdin is the payload, so
`ssh-keygen` has nowhere to read one from and fails with its own words.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .run import tool
from .._errors import Refused, TaskopsError

NAMESPACE = "taskops"
"""The SSHSIG namespace. A signature made for taskops can never be replayed as
a git commit signature, and vice versa — that separation is the field's job."""

NO_SSHKEYGEN = (
    "ssh-keygen is not on PATH — taskops signs a login with OpenSSH itself "
    "(install openssh-client; there is no pip package to add)"
)

NO_KEYFILE = (
    "no private key file at {path} — `ssh-keygen -Y sign` needs the key ON DISK, so an "
    "agent-only setup cannot sign a taskops login yet; pass --key <path to a key file>"
)


def sign(payload: str, key: Path) -> str:
    """The armored SSHSIG for `payload`, made with the private key at `key`."""
    if not key.is_file():
        raise Refused(NO_KEYFILE.format(path=key))
    result = tool(
        "ssh-keygen",
        "-Y",
        "sign",
        "-f",
        str(key),
        "-n",
        NAMESPACE,
        "-q",
        "-",
        stdin=payload,
        missing=NO_SSHKEYGEN,
    )
    if not result.ok or not result.out.startswith("-----BEGIN SSH SIGNATURE-----"):
        raise Refused(
            f"ssh-keygen could not sign with {key}\n  ssh-keygen said: "
            f"{result.err or result.out or f'exit {result.code}'}"
        )
    return result.out


def verify(signers: Path, principal: str, payload: str, signature: str) -> None:
    """Refuse unless `signature` is `principal`'s over `payload`, by a key that
    `allowed_signers` lists RIGHT NOW — the file `store/server.py` regenerates
    from its own truth, so a revoked key stops verifying without a second rule."""
    if not signers.is_file():
        raise Refused(
            f"this host has no {signers.name} — no key has been registered on it yet; "
            "the owner registers one: taskops server key add <name> --key <path.pub>"
        )
    if "-----BEGIN SSH SIGNATURE-----" not in signature:
        raise Refused("that is not an SSHSIG signature — send what `ssh-keygen -Y sign` printed")
    with tempfile.TemporaryDirectory(prefix="taskops-sig-") as folder:
        blob = Path(folder) / "signature"
        try:
            blob.write_text(signature if signature.endswith("\n") else signature + "\n")
        except OSError as err:  # pragma: no cover — a full or read-only /tmp
            raise TaskopsError(f"cannot stage a signature for verification: {err}") from err
        result = tool(
            "ssh-keygen",
            "-Y",
            "verify",
            "-f",
            str(signers),
            "-I",
            principal,
            "-n",
            NAMESPACE,
            "-s",
            str(blob),
            stdin=payload,
            missing=NO_SSHKEYGEN,
        )
    if not result.ok:
        raise Refused(
            f"that signature is not {principal}'s — ssh-keygen said: "
            f"{result.err or result.out or f'exit {result.code}'}"
        )
