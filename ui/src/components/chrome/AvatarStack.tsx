/* Who is on this board, as a row of overlapping initials.
 *
 * The colour is DERIVED from the actor's own name, never assigned: two renders of
 * the same board must give the same person the same disc, and there is nowhere to
 * store an assignment. The palette is four token pairs — a literal colour here
 * would be the one thing tokens.css exists to forbid. */
import type { TeamMember } from "../../types";

/** `dev:berna` → "B", `agent:berna/w3` → "W". The tail is the person; the head is
 *  the role, and a stack of five "A"s would say nothing. */
export function initial(actor: string): string {
  const tail = actor.split("/").pop() ?? actor;
  const name = tail.includes(":") ? (tail.split(":").pop() ?? tail) : tail;
  return (name.trim()[0] ?? "?").toUpperCase();
}

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
            {initial(member.actor)}
          </div>
        );
      })}
    </div>
  );
}
