/* Who is on this board, as a row of overlapping initials — one disc per PERSON.
 *
 * Agents are folded into the dev that owns them. `_team` answers with every
 * actor seen in the last 24h, which is the right answer to "who is present" and
 * the wrong one to draw: one session spawned 22 ephemeral workers and this row
 * drew 23 discs, 22 of them the same person's short-lived processes. A presence
 * row that lists processes tells you nothing about who is around. v1's People
 * row folded to devs for exactly this reason; the fold was lost in the rewrite.
 *
 * The fold is presentation, not policy, so it lives here and not in the payload:
 * Live leases needs the individual actors, and the board must keep answering
 * with them.
 *
 * The colour is DERIVED from the actor's own name, never assigned: two renders of
 * the same board must give the same person the same disc, and there is nowhere to
 * store an assignment. The palette is four token pairs — a literal colour here
 * would be the one thing tokens.css exists to forbid. */
import { initials, ownerOf, shortActor } from "../../format";
import type { TeamMember } from "../../types";

/* The glyphs come from `initials()` in format.ts: the TAIL of the actor string,
 * which is the person — the head is the role. Up to three glyphs, not one: with
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

export interface Person {
  /** The dev, e.g. `dev:berna`. */
  actor: string;
  /** Seconds since anybody under this dev was last seen — the freshest of them,
   *  because the person is present if any of their processes is. */
  ago: number;
  /** Their agents seen in the window, freshest first. Never includes the dev. */
  agents: string[];
}

/** Fold the team into people. Exported because it is the whole idea of this
 *  component and a list is far easier to assert on than a row of discs. */
export function people(team: TeamMember[]): Person[] {
  const by = new Map<string, Person>();
  for (const member of team) {
    const owner = ownerOf(member.actor);
    const found = by.get(owner) ?? { actor: owner, ago: member.ago, agents: [] };
    found.ago = Math.min(found.ago, member.ago);
    if (member.actor !== owner) found.agents.push(member.actor);
    by.set(owner, found);
  }
  return [...by.values()].sort((a, b) => a.ago - b.ago);
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
  position: "relative",
};

/** The count of live agents, on the disc's shoulder. Without it the fold would
 *  HIDE the swarm instead of summarising it — the number is the whole reason
 *  collapsing 23 discs into one is an improvement and not a loss. */
const badge: React.CSSProperties = {
  position: "absolute",
  right: "-3px",
  bottom: "-3px",
  minWidth: "13px",
  height: "13px",
  padding: "0 3px",
  borderRadius: "7px",
  background: "var(--pane-3)",
  color: "var(--text-2)",
  border: "1.5px solid var(--canvas)",
  fontSize: "8.5px",
  fontWeight: 500,
  display: "grid",
  placeItems: "center",
  letterSpacing: 0,
  textTransform: "none",
};

export function AvatarStack({ team }: { team: TeamMember[] }): React.JSX.Element {
  return (
    <div style={{ display: "flex", alignItems: "center" }} data-testid="avatars">
      {people(team).map((person) => {
        const { bg, fg } = tone(person.actor);
        const title =
          person.agents.length > 0
            ? `${person.actor} · ${person.agents.length} agents: ${person.agents
                .map(shortActor)
                .join(", ")}`
            : person.actor;
        return (
          <div
            key={person.actor}
            title={title}
            data-actor={person.actor}
            data-agents={person.agents.length}
            style={{ ...disc, background: bg, color: fg }}
          >
            {initials(person.actor)}
            {person.agents.length > 0 ? <span style={badge}>{person.agents.length}</span> : null}
          </div>
        );
      })}
    </div>
  );
}
