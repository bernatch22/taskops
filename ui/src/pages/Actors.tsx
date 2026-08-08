/* The fourth view — every actor, the card it carried, what it did.
 *
 * A grid of actor cards and, under them, the day's hours. It answers the one
 * question no other screen does: not "what is happening to this card" but "who
 * has been on this board, what did they carry, and for how long".
 *
 * ── The refusal this view is built around ─────────────────────────────────
 *
 * Nova draws this screen with a WORKER SLOTS panel — a roster of held / free /
 * lapsed slots, read as a pool with a capacity that taskops fills and frees.
 * There is no such pool. taskops allocates no worker: `workers=[…]` on
 * `taskops_assign` is a label chosen at the call, a sub-agent dies with its card,
 * and `w1` today is not `w1` yesterday. So the roster is not built, and it is not
 * rebuilt under another name — anything shaped like a fixed capacity is the thing
 * this chapter refuses (`panels.ts`, the ActorRow seam, says the same in the
 * type).
 *
 * What replaces it is `Hours worked today`, which is Nova's own second panel,
 * is true, and is a fold of the report the board already sends.
 *
 * AN ACTOR WITH NO CARD IS HISTORY, NOT AN EMPTY SLOT. Such a row says what it
 * carried, what it closed and when it was last seen. It never says `— free —`:
 * "free" is a claim about a slot, and the slot is the fiction.
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
 * grid says so ONCE, in its subtitle, rather than qualifying every card: a
 * qualifier repeated on twenty tiles is read on none of them. An absent figure
 * draws an em dash and never `0` — a board one version behind sends `ActorHours`
 * without those two keys (types.ts), and `0` would be an assertion nothing made.
 *
 * ── Why "today" is the last DAY and not `by_actor` ────────────────────────
 *
 * `ReportPayload.by_actor` folds the WHOLE window — fourteen days, as `useBoard`
 * asks for it. Drawing that under the heading "Hours worked today" would be the
 * exact dishonesty this chapter exists to remove. `report.days` is the same fold
 * per calendar day (`verbs/report.py::_day`, bucketed between two local
 * midnights) and its LAST entry is today, so that is what the panel reads, and
 * its heading carries the day's own label to prove it.
 *
 * ── The ordering, which is this view's design decision ────────────────────
 *
 * Not alphabetical. Who is ON something leads, because that is what a reader
 * opening this tab is looking for:
 *
 *     0  the orchestrator      always first — it never holds a card, and the
 *                              reader is usually it
 *     1  a live WORK lease
 *     2  a live REVIEW lease
 *     3  lapsed                an assignee, nothing running
 *     4  history               most recently seen first
 *
 * Within a rank, most recently seen first, then by name so the order is stable
 * between two renders of one payload. */
import { Pane, PaneButton, PaneEmpty, PaneRow } from "../components/monitor/Pane";
import { TONE_BG, TONE_FG } from "../components/board/CardTile";
import { ago, initials } from "../format";
import type {
  ActorRole,
  ActorRow,
  ActorState,
  ActorsProps,
  Tone,
} from "../components/monitor/panels";
import type { ActorHours, ReportPayload } from "../types";

export type { ActorsProps };

/** The standing spelling for not-knowable in this UI (Throughput uses the same
 *  one). Never `0`: zero is a measurement, absence is not. */
const DASH = "—";

const TONE_OF: Record<ActorState, Tone> = {
  online: "ok",
  doing: "accent",
  reviewing: "warn",
  lapsed: "danger",
};

/** What each pill MEANS, on the card itself — four short phrases, because a
 *  coloured word is not self-explanatory and this screen is the one place the
 *  four are drawn side by side. */
const MEANS: Record<ActorState, string> = {
  online: "seen recently, on no card",
  doing: "holds the work lease",
  reviewing: "holds the review lease",
  lapsed: "assigned, nobody running it",
};

/** An actor's role, from its own name and the lease it holds. `dev:` is the
 *  orchestrator — the one node the registry refuses `take` to — and a verifier
 *  is an agent holding the REVIEW mutex, which is a different claim from the
 *  work lease and not a shade of it (`store/reviews.py`). */
function roleOf(actor: string, state: ActorState | null): ActorRole {
  if (!actor.startsWith("agent:")) return "orchestrator";
  return state === "reviewing" ? "verifier" : "worker";
}

/** The rank the grid sorts on — the ordering rule above, as one function, so
 *  there is one place it can be read and one place it can be changed. */
export function rank(row: ActorRow): number {
  if (row.role === "orchestrator") return 0;
  if (row.state === "doing") return 1;
  if (row.state === "reviewing") return 2;
  if (row.state === "lapsed") return 3;
  return 4;
}

/** Payload → the cards, ordered. Pure and exported for the reason `submit()` and
 *  `topology()` are: no handler fires under `react-dom/server`, so a rule left
 *  inside the render closure would have no test at all. */
export function actorRows(props: ActorsProps): ActorRow[] {
  const { team, doing, reviewing, stalled, report } = props;

  /* WHO IS ON WHAT. A holder may appear in both lease maps — an agent holding
   * one card's work lease and another's review lease — and the work lease wins,
   * exactly as `Swarm.topology` resolves it: the first kind an actor is drawn
   * under is the one it keeps, so it is one card and not two. */
  const working = new Map<string, { id: string; title: string }>();
  const checking = new Map<string, { id: string; title: string }>();
  const lapsed = new Map<string, { id: string; title: string }>();
  for (const row of doing) if (row.holder) working.set(row.holder, row);
  for (const row of reviewing) if (row.holder) checking.set(row.holder, row);
  for (const row of stalled) if (row.assignee) lapsed.set(row.assignee, row);

  /* Presence is the ONLY source of "last seen", and it spans 24h. An actor the
   * report knows and presence does not has not been seen in that span — which is
   * a fact, and is what the card says. */
  const seen = new Map(team.map((m) => [m.actor, m.ago]));
  const hours: Record<string, ActorHours> = report?.by_actor ?? {};

  /* Every actor this board can name at all, from the four slices. A Set, because
   * the same name arrives from several of them and an actor is one card. */
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

/** One bar of `Hours worked today` — the day's own fold, never the window's. */
export interface HoursBar {
  actor: string;
  seconds: number;
  human: string;
}

/** Today's hours, by actor, longest first — `report.days`' LAST entry, which is
 *  today by construction (`core/hours.py::windows` ends at now's calendar day).
 *  `null` when the answer carried no report at all: a heading with no bars under
 *  it is a pane that failed, and this view says so in words instead. */
export function hoursToday(
  report: ReportPayload | null,
): { day: string; bars: HoursBar[] } | null {
  const day = report?.days[report.days.length - 1];
  if (!day) return null;
  const bars = Object.entries(day.by_actor)
    .map(([actor, h]) => ({ actor, seconds: h.seconds, human: h.human }))
    .filter((b) => b.seconds > 0)
    .sort((a, b) => b.seconds - a.seconds || a.actor.localeCompare(b.actor));
  return { day: day.day, bars };
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
  gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
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

/** One actor. The CARD ID is the only control on it: the actor itself is not
 *  clickable, because there is no actor page and nothing behind it. */
function Actor({ row, onOpen }: { row: ActorRow; onOpen: (id: string) => void }): React.JSX.Element {
  return (
    <section style={cardShell} data-testid="actor-card" data-actor={row.actor} data-state={row.state ?? ""}>
      <div style={{ display: "flex", gap: "11px", padding: "16px 18px 12px", alignItems: "center" }}>
        <span style={disc(row.tone)}>{row.glyph}</span>
        <div style={{ minWidth: 0, flex: "1 1 auto" }}>
          <div className="mono" style={{ ...clip, fontSize: "12px", color: "var(--text)" }}>
            {row.actor}
          </div>
          <div style={{ ...clip, fontSize: "11.5px", color: "var(--text-3)", marginTop: "3px" }}>
            {`${row.role} · ${row.presence}`}
          </div>
        </div>
        {/* No pill at all for an actor presence cannot see: four states exist
            and none of them is true of it (panels.ts::ActorState). */}
        {row.state ? (
          <span
            data-testid="actor-pill"
            title={MEANS[row.state]}
            style={{
              fontSize: "10.5px",
              padding: "3px 10px",
              borderRadius: "20px",
              background: TONE_BG[row.tone],
              color: TONE_FG[row.tone],
              whiteSpace: "nowrap",
              flex: "none",
            }}
          >
            {row.state}
          </span>
        ) : null}
      </div>

      {row.card ? (
        <PaneButton cardId={row.card.id} onOpen={onOpen} testId="actor-card-open" pad="11px 18px">
          <span className="mono" style={{ fontSize: "12px", color: "var(--accent)" }}>
            {row.card.id}
          </span>
          <span style={{ ...clip, display: "block", fontSize: "13px", marginTop: "3px" }}>
            {row.card.title}
          </span>
        </PaneButton>
      ) : (
        /* HISTORY, not a free slot. What it carried, in its own ids — each one
           the same door the rest of the dashboard opens. */
        <PaneRow pad="11px 18px">
          <div data-testid="actor-history" style={{ fontSize: "11.5px", color: "var(--text-3)" }}>
            {row.carried.length === 0
              ? "No card in this window — seen on the board, not on a card."
              : "Carried "}
            {row.carried.map((id, i) => (
              <span key={id}>
                {i > 0 ? ", " : ""}
                <button
                  type="button"
                  data-testid="actor-carried"
                  data-card={id}
                  onClick={() => onOpen(id)}
                  className="mono"
                  style={{
                    all: "unset",
                    cursor: "pointer",
                    color: "var(--accent)",
                    fontSize: "11.5px",
                  }}
                >
                  {id}
                </button>
              </span>
            ))}
          </div>
        </PaneRow>
      )}

      <PaneRow pad="11px 18px">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "8px" }}>
          <Figure value={row.closed === null ? DASH : String(row.closed)} label="closed" />
          <Figure value={row.commits === null ? DASH : String(row.commits)} label="commits" />
          <Figure value={row.worked ?? DASH} label="worked" />
        </div>
      </PaneRow>
    </section>
  );
}

export function Actors(props: ActorsProps): React.JSX.Element {
  const rows = actorRows(props);
  const today = hoursToday(props.report);
  const days = props.report?.days.length ?? 0;
  const max = Math.max(1, ...(today?.bars ?? []).map((b) => b.seconds));

  return (
    <div style={page} data-testid="actors">
      <div style={head}>
        <h2 style={{ margin: 0, fontSize: "19px", fontWeight: 500, letterSpacing: "-0.035em" }}>
          Actors
        </h2>
        <span style={{ fontSize: "12.5px", color: "var(--text-3)" }}>
          A name bound to a card, not a person
        </span>
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
            {days > 0
              ? `${rows.length} ${rows.length === 1 ? "actor" : "actors"} · closed and commits are over the last ${days} ${days === 1 ? "day" : "days"}`
              : `${rows.length} ${rows.length === 1 ? "actor" : "actors"} · the answer carried no hours, so no figure is drawn`}
          </div>
          <div style={grid}>
            {rows.map((row) => (
              <Actor key={row.actor} row={row} onOpen={props.onOpen} />
            ))}
          </div>
        </>
      )}

      {/* Nova's second panel, and the one that REPLACES the worker slots: hours
          are measured (`core/hours.py`), slots are not allocated. */}
      <Pane
        testId="pane-hours-today"
        title="Hours worked today"
        subtitle={
          today
            ? `${today.day} — a gap longer than 30 minutes is dropped, never capped`
            : "no report on this answer"
        }
        aside={
          today && today.bars.length > 0 ? (
            <span className="mono" style={{ fontSize: "11px", color: "var(--text-3)" }}>
              {`${today.bars.length} ${today.bars.length === 1 ? "actor" : "actors"}`}
            </span>
          ) : undefined
        }
      >
        {today === null ? (
          <PaneEmpty>
            The answer carried no <code>hours</code>. <code>pulse.py::run</code> builds that field
            only when the <code>board</code> call passes <code>window=</code> — a missing question,
            not an empty day.
          </PaneEmpty>
        ) : today.bars.length === 0 ? (
          <PaneEmpty>Nobody has worked a measurable minute today.</PaneEmpty>
        ) : (
          <div style={{ padding: "6px 20px 18px" }}>
            {today.bars.map((bar) => (
              <div
                key={bar.actor}
                data-testid="hours-bar"
                data-actor={bar.actor}
                style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "8px", padding: "7px 0" }}
              >
                <div style={{ minWidth: 0 }}>
                  <div className="mono" style={{ ...clip, fontSize: "11.5px", color: "var(--text-2)" }}>
                    {bar.actor}
                  </div>
                  <div
                    style={{
                      marginTop: "5px",
                      height: "6px",
                      borderRadius: "4px",
                      background: "var(--accent)",
                      width: `${Math.round((bar.seconds / max) * 100)}%`,
                    }}
                  />
                </div>
                <span className="num" style={{ fontSize: "12px", color: "var(--text-2)" }}>
                  {bar.human}
                </span>
              </div>
            ))}
          </div>
        )}
      </Pane>
    </div>
  );
}

export default Actors;
