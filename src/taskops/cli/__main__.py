"""`python -m taskops.cli …` — this is what the two git hooks invoke."""

from __future__ import annotations

from .main import main

raise SystemExit(main())
