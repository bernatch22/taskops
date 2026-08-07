/* Attention — the landing, and the reason the board exists.
 *
 * The nine groups of `verbs/pulse.py::run`, in the payload's own order, which
 * IS the order to act in: merge leads because it is the only group about work
 * that is finished and invisible; mentions is next because a question addressed
 * to you by name usually cannot wait a turn; review and changes sit above
 * stalled because finished work nobody is checking blocks more than work nobody
 * has started. A view that reorders them is contradicting the board, so the
 * order comes from `GROUP_ORDER` and is never written out again here.
 *
 * The labels are the vanilla page's GROUPS table verbatim; the subtitles say
 * what that module's docstring says each group MEANS and what move it wants.
 *
 * An EMPTY group renders collapsed, never hidden. The absence of a merge row or
 * a stalled row is itself the answer to "what is the board waiting for" — drop
 * the pane and the reader cannot tell "nothing to merge" from "this dashboard
 * does not show merges". */
import { GROUP_ORDER, type BoardGroups, type BoardPayload, type GroupName } from "../types";
import { GroupRow, accentInk, type Accent, type GroupRowProps } from "../components/board/GroupRow";
import { ago } from "../format";

/** What the page resolves a payload row down to; the row draws it. */
type Line = Omit<GroupRowProps, "onOpen" | "accent">;

interface Meaning {
  label: string;
  subtitle: string;
  accent: Accent;
}

/* Accent semantics, carried over from the vanilla page: green is work that is
 * DONE and only needs landing, amber is somebody owes an action, red is
 * something has gone wrong and is costing time. Everything else is neutral —
 * `doing` and `reviewing` are the board working as intended. */
const MEANING: Record<GroupName, Meaning> = {
  merge: {
    label: "Merge — done, not integrated",
    subtitle: "Finished and still invisible to everybody else. taskops_merge task=.",
    accent: "ok",
  },
  mentions: {
    label: "Mentions — addressed to you, not yet answered",
    subtitle: "Answering on the card IS the clearing — there is no mark-as-read.",
    accent: "warn",
  },
  review: {
    label: "Review — handed in, nobody checking",
    subtitle: "Handed in with no verdict yet. Somebody other than its author judges it.",
    accent: "neutral",
  },
  changes: {
    label: "Changes requested",
    subtitle: "A verdict asked for changes and nobody is on it. Usually seconds, and it frees a merge.",
    accent: "danger",
  },
  stalled: {
    label: "Stalled — owned, nobody running it",
    subtitle: "It has an owner and no live lease. Hand it over with taskops_assign.",
    accent: "danger",
  },
  take: {
    label: "Ready",
    subtitle: "Open, dependencies closed, nobody holds it. taskops_assign.",
    accent: "warn",
  },
  doing: {
    label: "Doing",
    subtitle: "Somebody holds the lease right now. Nothing to do.",
    accent: "neutral",
  },
  reviewing: {
    label: "Reviewing",
    subtitle: "A verifier holds the review lease. Nothing to do.",
    accent: "neutral",
  },
  blocked: {
    label: "Blocked",
    subtitle: "Waiting on a dependency. Close the blocker and this frees itself.",
    accent: "neutral",
  },
};

/** Who a card row belongs to right now: the LIVE holder, else whoever it was
 *  handed to. That difference is the whole of `stalled`, so it is never folded. */
function owner(holder: string | null, assignee: string): string {
  return holder || assignee || "";
}

/** This page's wording for a duration: the shared magnitude plus the word that
 *  makes it a past. The suffix is the PAGE's — the tile says "3h in" over the
 *  same helper (format.ts). "" stays "", so a row with no timestamp draws
 *  nothing rather than a bare "ago". */
function elapsed(seconds: number): string {
  const magnitude = ago(seconds);
  return magnitude ? `${magnitude} ago` : "";
}

/** How long this row has been quiet. `quiet_for` is the server's own count and
 *  is preferred wherever it exists — it is immune to a browser clock that
 *  disagrees with the board's. Only a held row falls back to `since`. */
function staleness(quiet_for: number | null, since: number, now: number): string {
  return elapsed(quiet_for === null ? now - since : quiet_for);
}

/** The payload → what each group actually shows. A switch and not an index, so
 *  a tenth group added to `BoardGroups` is a compile error here rather than a
 *  silently missing pane. */
function linesOf(name: GroupName, groups: BoardGroups, now: number): Line[] {
  switch (name) {
    case "mentions":
      // Not a card row: it is the comment that named you. The text IS the point,
      // and there is no priority on a sentence.
      return groups.mentions.map((m) => ({
        id: m.id,
        title: m.title || m.id,
        note: m.text,
        who: m.by,
        when: elapsed(now - m.ts),
        priority: null,
      }));
    case "blocked":
      return groups.blocked.map((r) => ({
        id: r.id,
        title: r.title,
        note: `waiting on ${r.waiting_on.join(", ")}`,
        who: owner(r.holder, r.assignee),
        when: staleness(r.quiet_for, r.since, now),
        priority: r.priority,
      }));
    case "review":
    case "changes":
      // The reason, not just the id: on `changes` the note is the reviewer's
      // words verbatim, and the holder here is the REVIEW lease, not the card's.
      return groups[name].map((r) => ({
        id: r.id,
        title: r.title,
        note: r.text,
        who: owner(r.holder, r.assignee),
        when: staleness(r.quiet_for, r.since, now),
        priority: r.priority,
      }));
    case "reviewing":
    case "merge":
    case "stalled":
    case "take":
    case "doing":
      return groups[name].map((r) => ({
        id: r.id,
        title: r.title,
        note: "",
        who: owner(r.holder, r.assignee),
        when: staleness(r.quiet_for, r.since, now),
        priority: r.priority,
      }));
  }
}

const pane: React.CSSProperties = {
  borderRadius: "16px",
  background: "var(--pane)",
  border: "1px solid var(--hair)",
  overflow: "hidden",
};

export interface AttentionProps {
  board: BoardPayload;
  openCard: (id: string) => void;
  /** Seconds since the epoch, injectable so a test can pin the wording. */
  now?: number;
}

export function Attention({ board, openCard, now }: AttentionProps): React.JSX.Element {
  const clock = now ?? Date.now() / 1000;
  return (
    <div style={{ display: "grid", gap: "14px" }} data-testid="attention">
      {GROUP_ORDER.map((name) => {
        const meaning = MEANING[name];
        const lines = linesOf(name, board.groups, clock);
        const { ink, wash } = accentInk(meaning.accent);
        return (
          <section key={name} style={pane} data-testid="group" data-group={name}>
            <div
              style={{
                padding: "16px 20px 10px",
                display: "grid",
                gridTemplateColumns: "minmax(0, 1fr) auto",
                gap: "12px",
                alignItems: "start",
              }}
            >
              <div style={{ minWidth: 0 }}>
                <h2 style={{ margin: 0, fontSize: "15px", fontWeight: 500, letterSpacing: "-0.03em" }}>
                  <span
                    style={{
                      display: "inline-block",
                      width: "8px",
                      height: "8px",
                      borderRadius: "3px",
                      background: ink,
                      marginRight: "9px",
                    }}
                  />
                  {meaning.label}
                </h2>
                <div style={{ fontSize: "12.5px", color: "var(--text-3)", marginTop: "3px" }}>
                  {meaning.subtitle}
                </div>
              </div>
              <span
                className="num"
                data-testid="group-count"
                style={{
                  fontSize: "11.5px",
                  padding: "2px 9px",
                  borderRadius: "20px",
                  background: lines.length ? wash : "var(--pane-3)",
                  color: lines.length ? ink : "var(--faint)",
                }}
              >
                {lines.length}
              </span>
            </div>
            <div style={{ padding: "0 10px 12px" }}>
              {lines.length === 0 ? (
                <div
                  data-testid="group-empty"
                  style={{ padding: "6px 10px 8px", fontSize: "12px", color: "var(--faint)" }}
                >
                  — nothing
                </div>
              ) : (
                lines.map((line) => (
                  <GroupRow key={`${name}:${line.id}:${line.note}`} {...line} accent={meaning.accent} onOpen={openCard} />
                ))
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
