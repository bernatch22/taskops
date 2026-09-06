"""The listing answer — one scan, worded for the page. Split out of
`editor.py` when the working set arrived and that door reached its budget;
this is the cohesive cut, because everything here is the SHAPE of one answer
and nothing here routes or refuses.

`files` carries every state `gitwork/scan.py` knows, `committed` and
`deleted` included: the page's working set — the folders it opens by default,
the rows it highlights — is every file whose state is not `clean`, and that
definition lives in ONE place on each side (`scan.py`, `tree.ts::working`).
`base` says which sha the branch's own changes were read against, so the
screen can name it beside the count."""

from __future__ import annotations

from typing import Any
from pathlib import Path

from .. import _clock
from ..gitwork import scan, reading, inhabited
from .treewatch import Held


def answer(name: str, tree: Path, held: Held, base: reading.Base | None) -> dict[str, Any]:
    described = inhabited.describe(name, tree, "")
    return {
        "tree": name,
        "branch": described.branch,
        "head": described.head,
        "base": {"ref": base.ref, "sha": base.sha} if base is not None else None,
        "files": [
            {"path": e.path, "size": e.size, "mtime": e.mtime, "state": e.state}
            for e in held.scan.files.values()
        ],
        "capped": held.scan.capped,
        "total": held.scan.total,
        "cap": scan.FILE_CAP,
        "seq": held.seq,
        "at": _clock.now(),
    }
