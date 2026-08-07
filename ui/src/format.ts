/* The presentation helpers more than one component needs.
 *
 * It exists because parallel fan-out produced `ago()` twice — once in the
 * attention rows, once in CardTile — with DIFFERENT output, so the same card
 * read "5m ago" on one screen and "5m" on the Board. The duplication was not
 * the bug; it was the mechanism that let the two drift. One definition,
 * imported by every caller, cannot drift. (The attention screen has since been
 * deleted as an invention; the lesson it paid for has not.)
 *
 * What belongs here: a pure seconds/string → string function with no React, no
 * tokens and no board vocabulary in it. What does NOT: anything a single
 * component owns (see the note on palettes at the foot of this file).
 */

/** Seconds → the BARE magnitude: "45s", "5m", "3h", "2d". Never a word.
 *
 *  Chosen over a "just now" / "5m ago" wording because the suffix is the
 *  CALLER's, not the quantity's: the board tile says "3h in" for a live lease
 *  and "quiet 3h" for a silent card, and a helper that had already said "ago"
 *  could serve neither without the caller stripping words back off. So the helper answers "how long" and each
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
 *  object, where the rest of that disc's typography already lives); a table that
 *  sets its glyphs beside the full lowercase actor string wants them left alone.
 *  A helper that had already upcased could serve neither without the caller
 *  casing them back down. */
export function initials(actor: string): string {
  return shortActor(actor).slice(0, 3);
}

/* On the palette, which is NOT here on purpose.
 *
 * `Tone` + `TONE_FG`/`TONE_BG` live in components/board/CardTile.tsx, not here:
 * they are the TILE palette — five ways a badge, chip, spine or column dot can
 * be coloured, `accent` (the brand blue) among them — and CardTile is their only
 * caller. A name → pair-of-CSS-custom-properties map is not by itself a shared
 * helper; what makes something shared is a SECOND caller, and moving it here on
 * shape alone would invite the next palette to be folded into it.
 *
 * That very folding was refused once already: an `accentInk` severity palette
 * (ok / warn / danger / neutral, deliberately no brand colour) had the identical
 * shape and a different meaning, and merging the two would have given one of
 * them a member that meant nothing there. It is gone now with the attention
 * screen it painted, but the reason it stayed out of this file is why `Tone`
 * still does. Duplication of a VALUE is cheap; merging two meanings is not.
 */
