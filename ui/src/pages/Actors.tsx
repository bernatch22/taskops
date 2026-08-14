/* The fourth view — who has been on this board, what they carried, how long.
 *
 * ── A page about DEVS. An agent is a LINE inside one ──────────────────────
 *
 * The first version of this screen drew one tile per ACTOR. On the session that
 * built it that was SIXTY-SEVEN tiles: one human and sixty-six ephemeral
 * sub-agents that had already died with their cards, each wearing the human's
 * layout. It contradicted this chapter's own goal — an actor is a name bound to
 * the RUN of a card, and `w1` today is not `w1` yesterday.
 *
 * So the top level is the DEV, the durable identity (`core/types.py::role_of`;
 * an `agent:<dev>/<name>` carries its dev in the name, `format.ts::ownerOf`,
 * which is the relation `http/auth.py::authorize` enforces on the wire). A dev
 * card says what the person did over the window and how many of its agents are
 * on a card RIGHT NOW — unexpanded, because that is the question somebody opens
 * this tab to answer. It never lists sixty-eight ids: a count, the most recent
 * few, and the rest inside the detail.
 *
 * A board with SEVERAL devs is the case this shape exists for, and is why the
 * top level is a dev rather than "the current user". Two devs are two cards,
 * each with its own agents; this board has one.
 *
 * ── The refusal this view is built around ─────────────────────────────────
 *
 * Nova draws this screen with a WORKER SLOTS panel — a roster of held / free /
 * lapsed slots, read as a pool with a capacity that taskops fills and frees.
 * There is no such pool. taskops allocates no worker: `workers=[…]` on
 * `taskops_assign` is a label chosen at the call, a sub-agent dies with its card,
 * and `w1` today is not `w1` yesterday. So the roster is not built, and it is not
 * rebuilt under another name — anything shaped like a fixed capacity is the thing
 * this chapter refuses (`panels.ts`, the `ActorRow`/`DevRow` seam, says the same
 * in the type).
 *
 * Nothing replaces it ON THIS PAGE. An `Hours worked today` panel of BARS stood
 * here for one wave and is deleted, not restyled: a bar chart exists to compare
 * things against each other, and the things it compared were ephemeral agents —
 * comparing two labels. The hours are still drawn, and drawn better, inside the
 * dev's own panel, grouped by the one axis that is a fact: the calendar day.
 *
 * ── A dev opens into a full overlay ───────────────────────────────────────
 *
 * `components/actors/DevPanel.tsx`, which reuses `shared/Overlay` — the same
 * portal, the same scrim, the same ONE `overlayStack` that owns Escape. Inside
 * it `Daysheet` is a pane per calendar day, newest first, with an hour that
 * folds open — a document that does not fit in a 300px grid cell, which is why
 * the earlier "reveal in place" is gone. What did NOT happen is a second copy of
 * the overlay plumbing.
 *
 * ── Where every figure comes from ─────────────────────────────────────────
 *
 * No verb, no payload key, no second fetch. Four slices the board already sends
 * (`ActorsProps`): `team` — presence over the last 24h (`verbs/pulse.py::_team`)
 * — plus `doing`, `reviewing` and `stalled`, and `board.hours`, the SAME field
 * Throughput reads, off the same snapshot (`useBoard` asks every `board` call for
 * `window=`).
 *
 * `closed` and `commits` are counts OVER THAT WINDOW (`verbs/report.py::_by_actor`
 * — the same pass over the same events as the hours), never lifetime figures. The
 * grid says so ONCE, in its subtitle, rather than qualifying every card. An
 * absent figure draws an em dash and never `0` — a board one version behind sends
 * `ActorHours` without those two keys (types.ts), and `0` would be an assertion
 * nothing made. A dev's totals are dev + agents, and when one member cannot say
 * its own the sum is refused rather than quietly taken over the rest.
 *
 * ── The ordering, which is this view's design decision ────────────────────
 *
 * Devs: most agents on a card right now first, then most time worked, then by
 * name so two renders of one payload agree. Agents inside a dev keep
 * `actorRows()`' rank — a live work lease, then a live review lease, then a
 * lapsed assignment, then history, most recently seen first within each. */
import { useEffect, useState } from "react";

import { PaneRow } from "../components/monitor/Pane";
import { Segmented } from "../components/shared/Segmented";
import { DEFAULT_HOURS_CHOICE, choicesFor, snapped } from "../hoursWindow";
import { DevPanel } from "../components/actors/DevPanel";
import { span } from "../components/actors/Daysheet";
import { TONE_BG, TONE_FG } from "../components/board/CardTile";
import { ago, initials, ownerOf, shortActor } from "../format";
import type {
  ActorRole,
  ActorRow,
  ActorState,
  ActorsProps,
  DevRow,
  Tone,
} from "../components/monitor/panels";
import type { ActorHours, ReportPayload } from "../types";

export type { ActorsProps };

/** The standing spelling for not-knowable in this UI (Throughput uses the same
 *  one). Never `0`: zero is a measurement, absence is not. */
const DASH = "—";

/** Agent names printed on the dev CARD. The rest are a stated remainder and are
 *  drawn as rows in the detail. */
export const RECENT = 4;

const TONE_OF: Record<ActorState, Tone> = {
  online: "ok",
  doing: "accent",
  reviewing: "warn",
  lapsed: "danger",
};

/** An actor's role, from its own name and the lease it holds. `dev:` is the
 *  orchestrator — the one node the registry refuses `take` to — and a verifier
 *  is an agent holding the REVIEW mutex, which is a different claim from the
 *  work lease and not a shade of it (`store/reviews.py`). */
function roleOf(actor: string, state: ActorState | null): ActorRole {
  if (!actor.startsWith("agent:")) return "orchestrator";
  return state === "reviewing" ? "verifier" : "worker";
}

/** The rank agents sort on inside their dev — the ordering rule above, as one
 *  function, so there is one place it can be read and one place it can change. */
export function rank(row: ActorRow): number {
  if (row.role === "orchestrator") return 0;
  if (row.state === "doing") return 1;
  if (row.state === "reviewing") return 2;
  if (row.state === "lapsed") return 3;
  return 4;
}

/** Payload → one row per ACTOR, ordered by what it is on. Still exported and
 *  still pure: it is what `devRows()` folds, and no handler fires under
 *  `react-dom/server`, so a rule left in a render closure would have no test. */
export function actorRows(props: ActorsProps): ActorRow[] {
  const { team, doing, reviewing, stalled, report } = props;

  /* WHO IS ON WHAT. A holder may appear in both lease maps — an agent holding
   * one card's work lease and another's review lease — and the work lease wins,
   * exactly as `Swarm.topology` resolves it: the first kind an actor is drawn
   * under is the one it keeps, so it is one row and not two. */
  const working = new Map<string, { id: string; title: string }>();
  const checking = new Map<string, { id: string; title: string }>();
  const lapsed = new Map<string, { id: string; title: string }>();
  for (const row of doing) if (row.holder) working.set(row.holder, row);
  for (const row of reviewing) if (row.holder) checking.set(row.holder, row);
  for (const row of stalled) if (row.assignee) lapsed.set(row.assignee, row);

  /* Presence is the ONLY source of "last seen", and it spans 24h. An actor the
   * report knows and presence does not has not been seen in that span — which is
   * a fact, and is what the row says. */
  const seen = new Map(team.map((m) => [m.actor, m.ago]));
  const hours: Record<string, ActorHours> = report?.by_actor ?? {};

  /* Every actor this board can name at all, from the four slices. A Set, because
   * the same name arrives from several of them and an actor is one row. */
  const names = new Set<string>([
    ...seen.keys(),
    ...working.keys(),
    ...checking.keys(),
    ...lapsed.keys(),
    ...Object.keys(hours),
  ]);
  names.delete("");

  const rows = [...names].map((actor) => {
    const card = working.get(actor) ?? checking.get(actor) ?? lapsed.get(actor) ?? null;
    const state: ActorState | null = working.has(actor)
      ? "doing"
      : checking.has(actor)
        ? "reviewing"
        : lapsed.has(actor)
          ? "lapsed"
          : seen.has(actor)
            ? "online"
            : null;
    const worked = hours[actor];
    const since = seen.get(actor);
    return {
      actor,
      glyph: initials(actor),
      role: roleOf(actor, state),
      presence: since === undefined ? "not seen in 24h" : `seen ${ago(since)}`,
      state,
      tone: state === null ? ("neutral" as Tone) : TONE_OF[state],
      card: card ? { id: card.id, title: card.title } : null,
      carried: worked?.cards ?? [],
      // `?? null` and not `?? 0`: the keys are optional on the wire and absent
      // is not zero (types.ts::ActorHours).
      closed: worked?.closed ?? null,
      commits: worked?.commits ?? null,
      worked: worked?.human ?? null,
      seconds: worked?.seconds ?? null,
    } satisfies ActorRow;
  });

  return rows.sort((a, b) => {
    const byRank = rank(a) - rank(b);
    if (byRank !== 0) return byRank;
    const bySeen = (seen.get(a.actor) ?? Infinity) - (seen.get(b.actor) ?? Infinity);
    if (bySeen !== 0) return bySeen;
    return a.actor.localeCompare(b.actor);
  });
}

/** The actors, folded onto their devs — the page's real top level.
 *
 *  Pure and exported for the same reason `actorRows()` is. Every dev the board
 *  can name appears, including one that only ever shows up as the OWNER of an
 *  agent: a dev whose sub-agents ran while it was quiet is still the person the
 *  work belongs to, and `self` is `null` there rather than invented. */
export function devRows(props: ActorsProps): DevRow[] {
  const all = actorRows(props);
  const groups = new Map<string, { self: ActorRow | null; agents: ActorRow[] }>();
  for (const row of all) {
    const dev = ownerOf(row.actor);
    const group = groups.get(dev) ?? { self: null, agents: [] };
    if (row.actor === dev) group.self = row;
    else group.agents.push(row);
    groups.set(dev, group);
  }

  const rows: DevRow[] = [];
  for (const [dev, { self, agents }] of groups) {
    const members = self ? [self, ...agents] : agents;
    /* ALL OR NOTHING. A member that cannot say one of its figures makes every
       total a sum over a subset, and a sum over a subset presented as a total is
       the dishonesty this chapter removes. So the sums are refused whole and the
       dev's OWN figures are drawn instead, with the panel saying which it is. */
    const partial = members.some(
      (m) => m.closed === null || m.commits === null || m.seconds === null,
    );
    const total = (pick: (m: ActorRow) => number | null): number | null =>
      partial ? null : members.reduce((n, m) => n + (pick(m) ?? 0), 0);
    const seconds = partial ? self?.seconds ?? null : total((m) => m.seconds);
    const live = agents.filter((a) => a.state === "doing" || a.state === "reviewing");

    rows.push({
      dev,
      glyph: initials(dev),
      presence: self?.presence ?? "not seen in 24h",
      self,
      agents,
      live: live.length,
      onCards: live.flatMap((a) => (a.card ? [{ actor: a.actor, ...a.card }] : [])),
      closed: partial ? self?.closed ?? null : total((m) => m.closed),
      commits: partial ? self?.commits ?? null : total((m) => m.commits),
      seconds,
      worked: seconds === null ? (partial ? self?.worked ?? null : null) : span(seconds),
      partial,
    });
  }

  return rows.sort(
    (a, b) =>
      b.live - a.live || (b.seconds ?? -1) - (a.seconds ?? -1) || a.dev.localeCompare(b.dev),
  );
}

/** Card id → title, for every card the board can name RIGHT NOW — the three
 *  lease slices, which is all `ActorsProps` carries titles in. A session on a
 *  card nobody holds any more is drawn as its id alone: the id is a fact, a
 *  title this payload never sent would be a guess.
 *
 *  Pure and exported for the same reason the two folds above are. */
export function cardTitles(props: ActorsProps): Record<string, string> {
  const out: Record<string, string> = {};
  for (const row of [...props.doing, ...props.reviewing, ...props.stalled]) {
    out[row.id] = row.title;
  }
  return out;
}

/** WHAT THE FIGURES MEASURE, in the payload's own words.
 *
 *  The page opens on the current calendar month, so the qualifier has to name a
 *  month — and the name comes back on `report.window.label` ("August 2026"),
 *  never from a client that re-derives a month from `from`/`to`. Two calendars
 *  in two languages disagree on the boundary days, and the one that owns this
 *  vocabulary is `verbs/_windows.py`.
 *
 *  A board one version behind sends no `window` at all (types.ts). Then the old
 *  sentence is still true and still drawn — the day buckets it DID send — which
 *  is what keeps this a degradation and not a blank. */
export function windowSaid(report: ReportPayload | null, devs: number): string {
  const who = `${devs} ${devs === 1 ? "dev" : "devs"} · an agent is a line inside its dev`;
  const span = report?.window?.label;
  if (span) return `${who} · closed and commits are over ${span}`;
  const days = report?.days.length ?? 0;
  if (days === 0) return `${devs} ${devs === 1 ? "dev" : "devs"} · the answer carried no hours, so no figure is drawn`;
  return `${who} · closed and commits are over the last ${days} ${days === 1 ? "day" : "days"}`;
}

/* ── the drawing ──────────────────────────────────────────────────────────── */

const page: React.CSSProperties = {
  height: "100%",
  overflowY: "auto",
  padding: "0 24px 26px",
};

const head: React.CSSProperties = {
  display: "flex",
  alignItems: "baseline",
  justifyContent: "space-between",
  marginBottom: "14px",
};

const grid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))",
  gap: "14px",
  marginBottom: "16px",
};

const cardShell: React.CSSProperties = {
  borderRadius: "16px",
  background: "var(--pane)",
  border: "1px solid var(--hair)",
  overflow: "hidden",
};

const clip: React.CSSProperties = {
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const disc = (tone: Tone): React.CSSProperties => ({
  width: "34px",
  height: "34px",
  borderRadius: "50%",
  background: TONE_BG[tone],
  color: TONE_FG[tone],
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  fontSize: "11px",
  letterSpacing: "-0.02em",
  textTransform: "uppercase",
  flex: "none",
});

const figure: React.CSSProperties = { fontSize: "16px", fontWeight: 500 };
const figureLabel: React.CSSProperties = {
  fontSize: "10.5px",
  color: "var(--text-3)",
  marginTop: "1px",
};

const nothing: React.CSSProperties = {
  display: "flex",
  justifyContent: "center",
  textAlign: "center",
  padding: "70px 22px",
  maxWidth: "36em",
  margin: "0 auto",
  fontSize: "13px",
  color: "var(--text-3)",
  lineHeight: 1.7,
};

/** The one sentence the view is when nobody has been seen. `pulse.py::_team`
 *  spans 24h and the report spans the window, so both being empty is a real,
 *  nameable state — a board nobody has touched — and not a failed render. */
const NOBODY =
  "Nobody has been on this board in the last 24 hours, and the report window carries no hours either. An actor appears here the moment somebody takes a card, comments on one, or commits against one.";

function Figure({ value, label }: { value: string; label: string }): React.JSX.Element {
  return (
    <div>
      <div className="num" style={figure}>
        {value}
      </div>
      <div style={figureLabel}>{label}</div>
    </div>
  );
}

/** One DEV. Everything a reader wants without opening anything: who it is, how
 *  many of its agents are on a card RIGHT NOW and which, its figures over the
 *  window, and the most recent few agent names with the rest as a count. */
function Dev({
  row,
  onOpen,
  onExpand,
}: {
  row: DevRow;
  onOpen: (id: string) => void;
  onExpand: () => void;
}): React.JSX.Element {
  const recent = row.agents.slice(0, RECENT);
  const rest = row.agents.length - recent.length;
  return (
    <section style={cardShell} data-testid="dev-card" data-dev={row.dev} data-live={row.live}>
      <div style={{ display: "flex", gap: "11px", padding: "16px 18px 12px", alignItems: "center" }}>
        <span style={disc(row.live > 0 ? "accent" : "neutral")}>{row.glyph}</span>
        <div style={{ minWidth: 0, flex: "1 1 auto" }}>
          <div className="mono" style={{ ...clip, fontSize: "12px", color: "var(--text)" }}>
            {row.dev}
          </div>
          <div style={{ ...clip, fontSize: "11.5px", color: "var(--text-3)", marginTop: "3px" }}>
            {row.presence}
          </div>
        </div>
      </div>

      {/* CRITERION: a live lease is said on the card, unopened. */}
      <PaneRow pad="11px 18px">
        <div data-testid="dev-live" style={{ fontSize: "12px", color: "var(--text-2)" }}>
          {row.live === 0
            ? "No agent of this dev is on a card right now."
            : `${row.live} ${row.live === 1 ? "agent" : "agents"} on a card right now:`}
          {row.onCards.map((on) => (
            <button
              key={on.actor}
              type="button"
              data-testid="dev-live-card"
              data-card={on.id}
              onClick={() => onOpen(on.id)}
              className="mono"
              style={{
                all: "unset",
                cursor: "pointer",
                color: "var(--accent)",
                fontSize: "11.5px",
                marginLeft: "6px",
              }}
            >
              {`${shortActor(on.actor)} → ${on.id}`}
            </button>
          ))}
        </div>
      </PaneRow>

      <PaneRow pad="11px 18px">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px" }}>
          <Figure value={row.closed === null ? DASH : String(row.closed)} label="closed" />
          <Figure value={row.commits === null ? DASH : String(row.commits)} label="commits" />
          <Figure value={row.worked ?? DASH} label="worked" />
          <Figure value={String(row.agents.length)} label="agents ran" />
        </div>
      </PaneRow>

      {/* NEVER sixty-eight ids: the most recent few, and the rest as a count. */}
      <PaneRow pad="10px 18px">
        <div style={{ ...clip, fontSize: "11.5px", color: "var(--text-3)" }} data-testid="dev-recent">
          {row.agents.length === 0
            ? "No agent ran under this dev in the window."
            : `${recent.map((a) => shortActor(a.actor)).join(" · ")}${rest > 0 ? ` · +${rest} more` : ""}`}
        </div>
      </PaneRow>

      <PaneRow pad="9px 18px">
        <button
          type="button"
          data-testid="dev-open"
          data-dev={row.dev}
          onClick={onExpand}
          style={{ all: "unset", cursor: "pointer", color: "var(--accent)", fontSize: "11.5px" }}
        >
          Open the days worked, hour by hour
        </button>
      </PaneRow>
    </section>
  );
}

export function Actors(props: ActorsProps): React.JSX.Element {
  const rows = devRows(props);
  const [open, setOpen] = useState<string | null>(null);
  const opened = rows.find((r) => r.dev === open) ?? null;
  /* The choice is App's state — it decides the `window=` of the ONE board call —
     and the page opens on the current month whether or not anybody is listening.
     The label under it is the payload's, so the two can never disagree: the
     filter says what was ASKED, the sentence says what came BACK. */
  const choice = props.choice ?? DEFAULT_HOURS_CHOICE;
  const onChoice = props.onChoice;
  /* WHICH FILTER THIS HOST CAN HONOUR. The options are the payload's own shape
     (hoursWindow.ts::choicesFor), so against a pre-calendar host the control
     offers only `Nd` spellings — the client never speaks a word that host has
     not confirmed, because its parser answers an unknown one with a silent 7d.
     And if the selection is not in the set the answer revealed, it moves ONCE:
     `snapped()` returns the choice untouched in every other case, so the
     refetch that follows cannot ask for a third. */
  const options = choicesFor(props.report, choice);
  const settled = snapped(props.report, choice);
  useEffect(() => {
    if (settled !== choice) onChoice?.(settled);
  }, [settled, choice, onChoice]);

  return (
    <div style={page} data-testid="actors">
      <div style={head}>
        <h2 style={{ margin: 0, fontSize: "19px", fontWeight: 500, letterSpacing: "-0.035em" }}>
          Actors
        </h2>
        <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          <span style={{ fontSize: "12.5px", color: "var(--text-3)" }}>
            A name bound to a card, not a person
          </span>
          <Segmented
            testid="actors-window-filter"
            name="window"
            options={options}
            active={settled}
            onSelect={(next) => onChoice?.(next)}
          />
        </div>
      </div>

      {rows.length === 0 ? (
        <div style={nothing} data-testid="actors-none">
          <span>{NOBODY}</span>
        </div>
      ) : (
        <>
          {/* The qualifier, ONCE. `closed` and `commits` are counts over the
              report's window and nothing on a card repeats it. */}
          <div
            data-testid="actors-window"
            style={{ fontSize: "12px", color: "var(--text-3)", marginBottom: "12px" }}
          >
            {windowSaid(props.report, rows.length)}
          </div>
          <div style={grid}>
            {rows.map((row) => (
              <Dev key={row.dev} row={row} onOpen={props.onOpen} onExpand={() => setOpen(row.dev)} />
            ))}
          </div>
        </>
      )}

      {opened ? (
        <DevPanel
          row={opened}
          report={props.report}
          window={props.report?.window?.label ?? null}
          titles={cardTitles(props)}
          onOpen={props.onOpen}
          onClose={() => setOpen(null)}
        />
      ) : null}
    </div>
  );
}

export default Actors;
