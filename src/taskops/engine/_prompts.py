"""What the model is asked for. Prose, kept out of `narrate` so the mechanism stays readable.

The whole design of these three strings is one instruction: the narration is the DURABLE
RECORD, not a summary of it. Somebody who reads this instead of the git log has to come away
knowing what was asked, what was delivered, what was decided, and what is still owed. So the
prompt demands a paragraph per card and says out loud that length is not the problem —
because a model left to its own judgement writes three tidy paragraphs about twenty cards,
which is exactly the report this replaces.

"Invent NOTHING" survives from the first version and is the one rule that outranks the rest:
an exhaustive report that is partly fiction is worse than a short true one.
"""

from __future__ import annotations

__all__ = ["PROMPT", "CHUNK_PROMPT", "STITCH_PROMPT"]

_RULES = """Rules:
- EVERY closed card gets its own paragraph. Do not group cards together to save room, and do
  not drop a card because it looks small. If the dossier lists 24 cards, 24 cards are covered.
- Each card's paragraph says, in this order: what was ASKED (its **Pedido** block), what was
  actually DELIVERED (the commits, the files they touched, the diff size), what was DECIDED or
  DISCOVERED along the way (its comments — quote the phrase that matters), and what it cost
  (how long it was held, how many commits, how big the diff).
- Where the delivery does not match the ask — something asked for and not visible in the
  commits, or something shipped that nobody asked for — SAY SO. That gap is the single most
  valuable line this report can contain.
- Name the decisions and the surprises: the thing a reader would not guess from the titles.
- LENGTH IS NOT A PROBLEM. OMISSION IS. This document is read INSTEAD of the git log.
- Invent NOTHING. Every claim must trace to a line in the dossier. If the dossier is silent
  about something, the narration is silent about it too — do not fill a gap with a guess.
- Do not flatter anybody and do not editorialise about pace.
- Markdown. Use `###` for sub-headings; no top-level heading (the section already has one).
"""

_STRUCTURE = """Structure it in four parts, in this order:
1. **Lo que necesita un humano** — anything blocked, anything still claimed, anything that
   looks wrong (a card closed minutes after being claimed with no commits, a spec whose
   delivery you cannot find). If there is nothing, one line saying so.
2. **Por área** — one `###` section per area of the codebase the work touched (infer the areas
   from the file paths in the commits, not from card ids), and inside it the paragraph per card.
3. **Decisiones y sorpresas** — what was decided, what was discovered, what was reversed.
4. **Lo que queda abierto** — what is still owed: unfinished cards, follow-ups named in a
   comment, debts somebody wrote down and nobody closed.
"""

PROMPT = ("""You are writing the narration of an engineering report. It is the durable record of
what was done — somebody reads it a month from now INSTEAD of the git log, and it has to leave
them knowing what happened.

Below is the dossier: what closed, each card's spec, its commits with their files and diff
sizes, the whole conversation, and a roll-up per actor. It was generated from an append-only
event log, so every fact in it is true.

Write the narration in the SAME LANGUAGE the cards and comments are written in.

"""
          + _STRUCTURE + "\n" + _RULES + """
Output ONLY the narration text.

--- DOSSIER ---
""")

CHUNK_PROMPT = ("""You are writing PART of the narration of an engineering report. The dossier was
too long for one reading, so you are given one slice of it; another pass will stitch the parts
together. Cover YOUR slice completely and say nothing about what is not in it.

Write in the SAME LANGUAGE the cards and comments are written in.

"""
                + _RULES + """
Do not write an introduction, a conclusion, or a "lo que queda abierto" section — this is a
middle of a document. Start straight at the `###` sections.

Output ONLY the narration text for this slice.

--- DOSSIER SLICE ---
""")

STITCH_PROMPT = ("""Below are the parts of one engineering report's narration, written from
consecutive slices of the same dossier, in order.

Assemble them into ONE document with the structure below. KEEP EVERY CARD PARAGRAPH — merge the
`###` sections that describe the same area of the codebase, reorder them, and rewrite the
connecting sentences, but do not delete, shorten or summarise a card's paragraph. Dropping a
card here would defeat the reason the dossier was read in slices at all.

Add the parts a slice could not write: the opening "lo que necesita un humano", and the closing
"lo que queda abierto". Both must come from what the parts actually say — invent nothing.

"""
                 + _STRUCTURE + """
Write in the SAME LANGUAGE the parts are written in. Markdown, no top-level heading.

Output ONLY the assembled narration.

--- PARTS ---
""")
