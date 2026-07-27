"""Layer 6 — the surfaces. Thin by construction: CLI, MCP and HTTP all call the same
use cases, and `tests/architecture` forbids any of them from importing storage or engine
directly. That rule is what stops a fourth place where a decision lives.
"""

from __future__ import annotations
