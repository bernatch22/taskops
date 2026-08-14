"""The schemas of the three tools only a `dev:` may call — plan, assign, merge.

Split out of `schema.py` along the seam the server already enforces: those three
are the ORCHESTRATOR's verbs (`verbs/__init__.py` declares the roles once), and
they are also the three longest schemas in the surface, because each argument of
them is a decision about somebody else's work rather than about a card.
`schema.py` merges this dict into `SCHEMAS` and stays the one name a caller
imports — the split is a line budget kept honest, not a second registry.
"""

from __future__ import annotations

from typing import Any

from .fields import CARD, _flag, _list, _text, _object

DEV_SCHEMAS: dict[str, dict[str, Any]] = {
    "taskops_plan": _object(
        {
            "milestone": _text("a title to open a chapter, or an existing ms-… id"),
            "goal": _text("WHY this milestone exists — it travels into every take"),
            "rules": _list(
                "what holds for EVERY card of this chapter, e.g. "
                '["Decimal, never float", "no migrations in this milestone"]. Shown above '
                "the spec in every take: a rule read after building is a rewrite."
            ),
            "criteria": _list(
                "what the CHAPTER is accepted against — every card can be green while the "
                "milestone is not. Shown at taskops_merge milestone=, refused until answered."
            ),
            "reviews": _flag(
                "chapter default: cards get review=true — OPTIONAL; a per-card review= wins"
            ),
            "union_files": _list(
                "the SEAM files every card of this chapter appends to — a registry, a table, "
                'an index, e.g. ["src/app/registry.py"]. Sibling conflicts in THESE paths '
                "union-merge during catch-up; every other conflict still refuses."
            ),
            "tasks": {"type": "array", "description": "the cards, in order", "items": CARD},
        },
        ["tasks"],
    ),
    "taskops_assign": _object(
        {
            "tasks": _list("the cards to hand out"),
            "workers": _list("names for them; default w1, w2, … (the free ones)"),
            "worktrees": _flag("cut one worktree per card (default true)"),
        },
        ["tasks"],
    ),
    "taskops_merge": _object(
        {
            "task": _text("a DONE card → into its milestone branch"),
            "tasks": _list(
                "integrate exactly these DONE cards, in the order given — each through the "
                "same single-card path. Stops at the first failure and reports per card."
            ),
            "done": _flag(
                "integrate every card the board groups under MERGE (done, not integrated), "
                "in that group's order. Re-run it after a stop: it continues where it left off."
            ),
            "milestone": _text(
                "ms-… → land the WHOLE milestone into the trunk. Refused while any card "
                "of it is open or unintegrated. The human's call — never do this with "
                "raw git in the shared checkout; the board must record the landing."
            ),
            "criteria_met": _flag(
                "with milestone=: the human's answer to its criteria — recorded, never "
                "judged. true, or false with note= saying which are unmet and why landing "
                "is still right (a criterion that can only be checked after the trunk "
                "moves). Omitted, a chapter with criteria is refused and shown them."
            ),
            "note": _text(
                "with milestone= criteria_met=false: REQUIRED — which criteria are unmet "
                "and why landing is still right. It lands on the record beside the answer."
            ),
        }
    ),
}
