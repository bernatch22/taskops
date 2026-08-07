/* Who is on this board, as a row of overlapping initials.
 *
 * The colour is DERIVED from the actor's own name, never assigned: two renders of
 * the same board must give the same person the same disc, and there is nowhere to
 * store an assignment. The palette is four token pairs — a literal colour here
 * would be the one thing tokens.css exists to forbid. */
import { initials } from "../../format";
import type { TeamMember } from "../../types";

/* The glyphs come from `initials()` in format.ts: the TAIL of the actor string,
 * which is the person — the head is the role, and a stack of five "A"s would say
 * nothing. Up to three glyphs, not one, for the same reason one step later: with
 * `agent:berna/w1` … `agent:berna/w8` on the board a single leading letter draws
 * eight identical "W" discs, and two would still collide `w1` with `w10` — see
 * the argument in format.ts. The upcasing is this disc's own presentation and
 * lives in `disc` below, with the rest of its typography. */

const TONES = [
  { bg: "var(--accent-soft)", fg: "var(--accent-hi)" },
  { bg: "var(--ok-soft)", fg: "var(--ok)" },
  { bg: "var(--warn-soft)", fg: "var(--warn)" },
  { bg: "var(--danger-soft)", fg: "var(--danger)" },
] as const;

function tone(actor: string): { bg: string; fg: string } {
  let hash = 0;
  for (const ch of actor) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return TONES[hash % TONES.length] ?? TONES[0];
}

const disc: React.CSSProperties = {
  width: "28px",
  height: "28px",
  borderRadius: "50%",
  border: "2px solid var(--canvas)",
  marginLeft: "-9px",
  fontSize: "10.5px",
  fontWeight: 500,
  display: "grid",
  placeItems: "center",
  letterSpacing: "-0.02em",
  textTransform: "uppercase",
};

export function AvatarStack({ team }: { team: TeamMember[] }): React.JSX.Element {
  return (
    <div style={{ display: "flex", alignItems: "center" }} data-testid="avatars">
      {team.map((member) => {
        const { bg, fg } = tone(member.actor);
        return (
          <div
            key={member.actor}
            title={member.actor}
            data-actor={member.actor}
            style={{ ...disc, background: bg, color: fg }}
          >
            {initials(member.actor)}
          </div>
        );
      })}
    </div>
  );
}
