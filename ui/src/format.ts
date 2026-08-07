/* The presentation helpers more than one component needs.
 *
 * It exists because parallel fan-out produced `ago()` twice, in GroupRow and in
 * CardTile, with DIFFERENT output — so the same card read "5m ago" on Attention
 * and "5m" on the Board. The duplication was not the bug; it was the mechanism
 * that let the two drift. One definition, imported by both, cannot drift.
 *
 * What belongs here: a pure seconds/string → string function with no React, no
 * tokens and no board vocabulary in it. What does NOT: anything a single
 * component owns (see the note on palettes at the foot of this file).
 */

/** Seconds → the BARE magnitude: "45s", "5m", "3h", "2d". Never a word.
 *
 *  Chosen over GroupRow's "just now" / "5m ago" wording because the suffix is
 *  the CALLER's, not the quantity's: the board tile says "3h in" for a live
 *  lease and "quiet 3h" for a silent card, the Attention row says "5m ago", and
 *  a helper that had already said "ago" could serve none of them without the
 *  caller stripping words back off. So the helper answers "how long" and each
 *  site says what that duration means. ("just now" died with it — it is a
 *  wording, and under a minute "45s" is the same fact told more precisely.)
 *
 *  Rounds rather than floors, and crosses each unit late (90s, 90m, 48h) so the
 *  rounded number is never a lie by more than half a unit: 89s is "89s", not a
 *  "1m" that is 31s short. A non-finite input renders as "" — a row with no
 *  timestamp draws nothing rather than "NaNs". */
export function ago(seconds: number): string {
  if (!Number.isFinite(seconds)) return "";
  const s = Math.max(0, Math.round(seconds));
  if (s < 90) return `${s}s`;
  if (s < 5400) return `${Math.round(s / 60)}m`;
  if (s < 172800) return `${Math.round(s / 3600)}h`;
  return `${Math.round(s / 86400)}d`;
}

/** "agent:berna/w5" → "w5", "dev:berna" → "berna". The board's actor strings are
 *  role-qualified; a name drawn next to a card is not the place to re-read the
 *  role — the card already says whether somebody holds it. */
export function shortActor(actor: string): string {
  const tail = actor.split("/").pop() ?? actor;
  return tail.split(":").pop() ?? tail;
}

/** The glyphs that stand for an actor, in the actor's OWN case: "agent:berna/w5"
 *  → "w5", "agent:berna/w10" → "w10", "dev:berna" → "ber".
 *
 *  Up to THREE, not one. A single leading glyph drew eight identical "W" discs
 *  the day `agent:berna/w1` … `agent:berna/w8` ran in parallel, and the avatar
 *  row stopped naming anybody. Two would have fixed exactly that board and
 *  broken the next one: the live board already carries `w1` AND `w10`, which
 *  share their first two glyphs. The tail is short by construction (a worker
 *  name, not a sentence), so the cap only ever bites a human's given name, where
 *  three glyphs read better than two anyway ("ber", not "be").
 *
 *  The case is NOT decided here — same split as `ago`: the helper answers "which
 *  glyphs", the caller says how they are drawn. A round avatar disc wants them
 *  upcased (AvatarStack, CardTile, both via `textTransform` in their own style
 *  object, where the rest of that disc's typography already lives); the hours
 *  table sets its glyphs beside the full lowercase actor string and wants them
 *  left alone. A helper that had already upcased could serve neither without the
 *  caller casing them back down. */
export function initials(actor: string): string {
  return shortActor(actor).slice(0, 3);
}

/* On the palettes, which are NOT here on purpose.
 *
 * `Tone` + `TONE_FG`/`TONE_BG` (components/board/CardTile.tsx) and `accentInk`
 * (components/board/GroupRow.tsx) share a shape — a name mapped to a pair of
 * CSS custom properties — and are not the same idea:
 *
 *   Tone   is the TILE palette: five ways a badge, chip, spine or column dot can
 *          be coloured, `accent` (the brand blue) among them. It says "draw this
 *          element in this colour".
 *   Accent is a SEVERITY over the nine attention groups: ok / warn / danger /
 *          neutral, and deliberately no brand colour — an attention group is
 *          never "brand-coloured", it is finished, owed, wrong, or fine. Its
 *          `neutral` is one step quieter (--text-3, not --text-2) because it
 *          paints nine panes at once and must not read as nine alarms.
 *
 * Folding them would either give attention groups a fifth member that means
 * nothing there, or force one of the two `neutral`s to change colour. The
 * overlap is six token strings; the divergence is a design decision each file
 * argues for in its own docstring. Duplication of a VALUE is cheap; merging two
 * meanings is not.
 */
