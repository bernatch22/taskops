/* Who is on this board, as faces — and one person's whole footprint behind a click.
 *
 * It sits where the chat trigger used to, and that is not a coincidence: the sidebar was there to
 * ask a session what was going on, and this answers the same question from state. A question needs
 * somebody listening, which a shared board cannot promise; a projection needs nobody.
 *
 * **The row costs no request.** The faces come from what the board already loaded — who holds a
 * card, who is assigned one, who has stated something in the context — so the header does not pay
 * for a fetch nobody asked for. The PROFILE fetches, once, when it opens, exactly like the
 * activity view: a roll-up over a window is a scan, and one per avatar on every reload would be
 * the board taxing itself to draw decoration.
 *
 * A profile is its OWN modal and not a tab on the context one. That modal answers "what has this
 * project decided", which is about the project; this answers "what has this person done", which is
 * about a person. They looked adjacent enough to merge and are not: merging two kinds of thing
 * because they fit the same box is how a policy ended up hidden inside a decision.
 *
 * **A dev's context is theirs across the WHOLE project.** Whatever a fact is scoped to, it is not
 * a note about one card — the card's thread is where that belongs — so nothing here is drawn per
 * card, and the standing facts are shown as what this person holds while working on anything. */

import { useEffect, useState } from "react";

import { api } from "../api";
import type {
  Activity, ActorRoll, Attended, Board, ContextView, Fact, Stretch,
} from "../contracts";
import { ago, heat, spell } from "./bits";
import { Overlay } from "./Overlay";

const PAGE = 8;

/* The periods a profile can be read over. `14d` was the only one for a while and it was hardcoded,
 * so the panel could not answer "all time" or "last month" at all and the cards further back simply
 * did not exist as far as it was concerned.
 *
 * The RANGES are computed here, in the browser, and that is the point rather than an accident: a
 * month starts on the 1st at 00:00 wherever the reader is, and no server clock knows that. `from`
 * and `to` are epoch seconds; `0` for `to` means "up to now", `0` for `from` means the whole log.
 */
type Period = { key: string; label: string; range: () => [number, number] };

const START_OF_MONTH = (shift: number): Date => {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth() + shift, 1);
};

const TWO_WEEKS: Period = {
  key: "14d", label: "14 days", range: () => [seconds(new Date()) - 14 * 86400, 0],
};

/* Two weeks FIRST because it is the answer to "what is going on", which is what somebody opening a
 * profile usually wants — long enough that a Friday off still leaves a footprint. */
const PERIODS: Period[] = [
  TWO_WEEKS,
  { key: "month", label: "This month", range: () => [seconds(START_OF_MONTH(0)), 0] },
  /* The only one that needs BOTH ends, and the reason the range call exists. */
  { key: "last", label: "Last month",
    range: () => [seconds(START_OF_MONTH(-1)), seconds(START_OF_MONTH(0))] },
  { key: "all", label: "All time", range: () => [0, 0] },
];

function seconds(at: Date): number {
  return Math.floor(at.getTime() / 1000);
}


export interface Person {
  dev: string;
  /* Live lease right now: what is actually under their hands, not what is assigned to them. */
  holding: string[];
  assigned: number;
}

/* Everybody the board can see, folded to DEVS.
 *
 * `agent:ana/w1` is ana with another pair of hands, not a second person — the same fold the
 * engine makes for `reviewer: peer`, and drawing an avatar per worker would put five faces on a
 * board with one developer on it. */
export function peopleOf(board: Board | null, context: ContextView | null): Person[] {
  const found = new Map<string, Person>();
  const seen = (id: string): Person => {
    const dev = devOf(id);
    if (!found.has(dev)) found.set(dev, { dev, holding: [], assigned: 0 });
    return found.get(dev)!;
  };
  for (const column of board?.columns ?? []) {
    for (const card of column.cards) {
      /* WHO WROTE IT, always — the fact that makes this row work on a board that is not mid-sprint.
       * The three sources below are all live state: a lease is somebody's hands right now, an
       * assignment is somebody about to start, an objective is somebody having stated one. A board
       * whose open cards are all in `review` (which releases the lease) and unassigned has none of
       * the three — so a project with 63 cards and two developers' whole history in it drew ZERO
       * faces and the header vanished. The names were in the payload the row already had. */
      seen(card.task.created_by);
      if (card.lease) seen(card.lease.actor).holding.push(card.task.id);
      else if (card.task.assignee) seen(card.task.assignee).assigned += 1;
    }
  }
  /* People who have STATED something count as being on the board even with nothing in their
   * hands: a developer between cards has not left, and an avatar row that emptied out every
   * time somebody closed their last card would read as the team having gone home. */
  for (const fact of context?.objectives ?? []) if (fact.owner) seen(fact.owner);
  return [...found.values()].filter((p) => p.dev).sort((a, b) => a.dev.localeCompare(b.dev));
}

/* `dev:ana` and `agent:ana/w1` both answer `ana`; anything else answers "". Written with an
 * index rather than a destructure so a malformed id from another machine cannot be `undefined`
 * halfway through a render — an actor typed by hand elsewhere must not blank the header. */
function devOf(actor: string): string {
  const at = actor.indexOf(":");
  if (at < 0) return "";
  const kind = actor.slice(0, at);
  const rest = actor.slice(at + 1);
  if (kind === "dev") return rest;
  return kind === "agent" ? rest.split("/")[0] ?? "" : "";
}

export function People({ board, context, onOpen }: {
  board: Board | null;
  context: ContextView | null;
  onOpen: (id: string) => void;
}): JSX.Element | null {
  const [who, setWho] = useState("");
  const people = peopleOf(board, context);
  if (!people.length) return null;
  return (
    <>
      <div className="faces" role="group" aria-label="who is on this board">
        {people.map((person) => (
          <button className={`face${person.holding.length ? " busy" : ""}`} key={person.dev}
                  onClick={() => setWho(person.dev)}
                  title={`${person.dev} — ${said(person)}`}>
            {person.dev.slice(0, 2)}
          </button>
        ))}
      </div>
      {who ? (
        <Profile dev={who} person={people.find((p) => p.dev === who) ?? null}
                 context={context} onOpen={onOpen} onClose={() => setWho("")} />
      ) : null}
    </>
  );
}

function said(person: Person): string {
  const bits = [];
  if (person.holding.length) bits.push(`on ${person.holding.length}`);
  if (person.assigned) bits.push(`${person.assigned} assigned, not running`);
  return bits.join(", ") || "nothing in hand";
}

/* The title of the chapter an owned fact belongs to, or "" when it names none — a fact written
 * before this board had chapters. Resolved here because a Fact carries the id and a person reads
 * names: the slice already carries every active chapter, so this costs no request. */
function chapterOf(context: ContextView | null, id: string): string {
  if (!id) return "";
  const every = [...(context?.active ?? []), ...(context?.planned ?? [])];
  return every.find((chapter) => chapter.id === id)?.title ?? "";
}

function Profile({ dev, person, context, onOpen, onClose }: {
  dev: string;
  person: Person | null;
  context: ContextView | null;
  onOpen: (id: string) => void;
  onClose: () => void;
}): JSX.Element {
  const [activity, setActivity] = useState<Activity | null>(null);
  const [failed, setFailed] = useState(false);

  /* One fetch, on open. Not in the header and not per avatar: a roll-up over two weeks is a scan
   * of the log, and paying for one per face on every reload would be the board taxing itself to
   * draw decoration nobody clicked. */
  const [tab, setTab] = useState<"work" | "context">("work");
  const [period, setPeriod] = useState(TWO_WEEKS);

  /* Refetches when the PERIOD changes, and clears first — a stale total under a new label is the
   * one thing this control must never show. */
  useEffect(() => {
    let alive = true;
    setActivity(null);
    setFailed(false);
    const [from, to] = period.range();
    api.activityBetween(from, to)
      .then((got) => { if (alive) setActivity(got); })
      .catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [dev, period]);
  const roll = (activity?.actors ?? []).filter((a) => devOf(a.actor) === dev);
  /* Their agents' sittings, INTERLEAVED by when they happened and never merged: two of a dev's
   * agents running in parallel are two sittings, because they do not share attention — that is the
   * whole point of having several pairs of hands. */
  const sittings = roll.flatMap((r) => r.sittings).sort((a, b) => b.started - a.started);
  const own = ownFacts(context, dev);
  /* Their agents' cards, MERGED per card: a dev works through several pairs of hands and two rows for
   * one card would read as two cards. Same fold as every number in `Numbers`. */
  const on = new Map<string, Attended>();
  for (const roll_ of roll) {
    for (const each of roll_.on) {
      const into = on.get(each.task);
      on.set(each.task, into
        ? { task: each.task, seconds: into.seconds + each.seconds, events: into.events + each.events }
        : each);
    }
  }
  const hasContext = Boolean(own.objective) || own.decisions.length > 0;
  return (
    /* Through `Overlay`, which PORTALS to the body — and that is load-bearing here rather than
     * decorative: this is rendered inside the header, the header blurs its own backdrop, and an
     * ancestor with `backdrop-filter` becomes the containing block for `position: fixed`. Mounted
     * in place, `inset: 0` covered the header and nothing else. */
    <Overlay label={`${dev}'s profile`} onClose={onClose}>
      <header className="ctx-head">
        <span className="face big">{dev.slice(0, 2)}</span>
        <h2>{dev}</h2>
        <span className="dim">{person ? said(person) : ""}</span>
        <button className="close" onClick={onClose} title="close (Esc)">✕</button>
      </header>

      {/* TWO TABS, because the modal answers two questions and stacking them made the second one
        * something you scroll past: what has this person DONE, and what are they working under. The
        * `context` tab is only offered when there is any — a tab that is always empty on a board
        * where nobody writes their own facts is a control teaching people not to click. */}
      {hasContext ? (
        <div className="ctx-tabs" role="tablist">
          <button role="tab" aria-selected={tab === "work"}
                  className={tab === "work" ? "on" : ""} onClick={() => setTab("work")}>Work</button>
          <button role="tab" aria-selected={tab === "context"}
                  className={tab === "context" ? "on" : ""}
                  onClick={() => setTab("context")}>Context</button>
        </div>
      ) : null}

      <div className="ctx-body">
        {tab === "work" || !hasContext ? (
          <>
            <Numbers roll={roll} />
            <section className="ctx-group">
              <h4>Cards <span className="dim">what they touched</span>
                {/* The period sits IN the heading it qualifies, not above the tabs: it changes what
                  * these rows and the totals above them mean, and a control far from the number it
                  * governs is a control people forget is set. */}
                <span className="periods" role="group" aria-label="period">
                  {PERIODS.map((each) => (
                    <button key={each.key} className={each.key === period.key ? "on" : ""}
                            onClick={() => setPeriod(each)}>{each.label}</button>
                  ))}
                </span>
              </h4>
              {failed ? <p className="ctx-empty">could not read the log just now.</p>
                : activity === null ? <p className="ctx-empty">reading…</p>
                : <Cards sittings={sittings} titles={activity.titles}
                         holding={person?.holding ?? []} on={on} onOpen={onOpen} />}
              {/* The bound, stated where the numbers are. A window capped at 600 events makes every
                * total on this tab a partial one, and a partial number that does not say so is the
                * exact failure this project keeps paying for. */}
              {/* The TIMELINE is capped, the totals are not — they are folded over the whole period
                * server-side. Said precisely, because "partial" about the wrong half is worse than
                * saying nothing. */}
              {activity?.truncated
                ? <p className="ctx-empty">Long period — the totals cover all of it; only the raw
                  timeline is capped.</p>
                : null}
            </section>
          </>
        ) : (
          <>
            {own.objective ? (
              <section className="ctx-group">
                {/* Theirs, and INSIDE the open chapter — a change of wording and not of shape. A
                  * dev's objective used to sit beside the project's north and outlive everything;
                  * the north is a milestone now, and an objective is what this person is chasing
                  * while that chapter is open. */}
                <h4>Objective <span className="dim">theirs, inside the chapter in force</span></h4>
                <p className="ctx-goal">
                  {own.objective.text}
                  {own.objective.horizon
                    ? <span className="context-horizon"> by {own.objective.horizon}</span> : null}
                </p>
                {/* WHICH chapter, by title: an objective belongs to one, and "terminar el parser"
                  * means two different things under the importer and under invoicing. */}
                {chapterOf(context, own.objective.milestone)
                  ? <p className="ctx-meta dim">in ◆ {chapterOf(context, own.objective.milestone)}</p>
                  : null}
              </section>
            ) : null}

            {/* Their standing calls, and the framing is the point: context they hold while working
              * on ANYTHING, not a note about one card. Split by LEVEL — a project-level fact of
              * theirs is true in a year, a milestone-level one leaves every slice the day the
              * chapter closes, and one list would have the second read as the first on exactly the
              * day it stopped applying. */}
            <Standing title="Their standing calls" note="project level — they outlive every chapter"
                      facts={own.decisions.filter((f) => f.level === "project")} />
            <Standing title="In this chapter" note="theirs while it is open, and no longer"
                      facts={own.decisions.filter((f) => f.level !== "project")} />
          </>
        )}
      </div>
    </Overlay>
  );
}

function Numbers({ roll }: { roll: ActorRoll[] }): JSX.Element | null {
  if (!roll.length) return null;
  /* Summed over this dev's agents, because the fold is the whole point: a developer's output is
   * what their hands did, and they have several. */
  const total = roll.reduce((into, one) => ({
    tasks: into.tasks + one.tasks, commits: into.commits + one.commits,
    done: into.done + one.done, last_seen: Math.max(into.last_seen, one.last_seen),
    seconds: into.seconds + one.on.reduce((sum, each) => sum + each.seconds, 0),
  }), { tasks: 0, commits: 0, done: 0, last_seen: 0, seconds: 0 });
  return (
    <div className="stats">
      <span className="stat"><b>{total.tasks}</b> cards</span>
      {/* The total FIRST among the derived numbers, because it is the one somebody wants before any
        * per-card row: it had to be added up by eye. Labelled "at least" for the same reason every
        * row is — it is a floor, and a floor drawn as a total is the lie the cap exists to avoid. */}
      {spell(total.seconds)
        ? <span className={`stat ${heat(total.seconds)}`}
                 title="the sum of every card's floor, so the total is one too">
            <b>{spell(total.seconds)}</b> at least
          </span>
        : null}
      <span className="stat"><b>{total.commits}</b> commits</span>
      <span className="stat stat-good"><b>{total.done}</b> closed</span>
      <span className="stat"><b>{ago(total.last_seen)}</b> last seen</span>
    </div>
  );
}

function Standing({ title, note, facts }: {
  title: string;
  note: string;
  facts: Fact[];
}): JSX.Element | null {
  if (!facts.length) return null;
  return (
    <section className="ctx-group">
      <h4>{title} <span className="dim">{note}</span></h4>
      <ul className="ctx-list">
        {facts.map((fact) => (
          <li className="ctx-fact" key={fact.id}>
            <p className="context-text">{fact.text}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

/* The last cards they touched, newest first, deduplicated. Cards and not EVENTS: nine commits on
 * one card is one thing they worked on, and a feed would rank it above three cards they closed. */
/* Exported for the smoke, like `Menu`: the bug this section fixes was caught by a reader summing
 * the visible rows against the header, so the smoke has to be able to do the same sum. */
export function Cards({ sittings, titles, holding, on, onOpen }: {
  sittings: Stretch[];
  titles: Record<string, string>;
  holding: string[];
  on: Map<string, Attended>;
  onOpen: (id: string) => void;
}): JSX.Element {
  const [shown, setShown] = useState(PAGE);
  /* TWO sections, because they answer two different questions and a first version tried to make one
   * list do both jobs and lied doing it. The groups answer "what was open at the same time", and
   * their minutes are the SITTING's. The card list answers "where did the period's time go", and its
   * rows are period totals — it is the section that must add up to the header above, exactly,
   * because a reader summed the visible rows against the header and got one seventh of it: every
   * card that appeared in some group had lost its own row, so all its solo work was drawn nowhere. */
  const groups = sittings
    .map((s) => ({ ...s, spent: s.spent.filter((e) => e.task && e.task !== "project") }))
    .filter((s) => s.spent.length > 1);
  const totals = [...on.values()].filter((e) => e.task && e.task !== "project")
    .sort((a, b) => b.seconds - a.seconds || b.events - a.events);
  if (!totals.length) return <p className="ctx-empty">nothing in this period.</p>;
  const row = (id: string, seconds: number, events: number, note: string): JSX.Element => (
    <li key={id}>
      <button className="ctx-card" onClick={() => onOpen(id)}>
        <code className="context-id">{id}</code>
        <span className="ctx-card-title">{titles[id] ?? "…"}</span>
        {/* At least this long — the measure caps every gap, so it under-reports on purpose. The
          * tooltip says which it is: a bound drawn as if it were the answer is worse than no
          * number, since nothing in the log records when somebody stopped. */}
        {spell(seconds) ? (
          <span className={`ctx-card-time ${heat(seconds)}`}
                title={`${note}: ${events} event(s), the gaps between them each capped at 30m — `
                       + "a floor, never an estimate"}>
            {spell(seconds)}
          </span>
        ) : null}
        {holding.includes(id) ? <span className="context-horizon">now</span> : null}
      </button>
    </li>
  );
  return (
    <>
      {groups.length ? (
        <ul className="ctx-list sittings">
          {groups.map((sitting) => (
            <li key={`${sitting.started}`} className="sitting together">
              <p className="sitting-head dim">
                {sitting.spent.length} at the same time
                <span className="sitting-when"> · {when(sitting)}</span>
                {/* The span, beside rows that PARTITION it — what makes the group checkable, and
                  * how a reader caught the previous version being wrong. */}
                <span className="sitting-span"> · {spell(sitting.ended - sitting.started)}</span>
              </p>
              <ul className="ctx-list">
                {sitting.spent.map((e) => row(e.task, e.seconds, e.events, "in this sitting"))}
              </ul>
            </li>
          ))}
        </ul>
      ) : null}
      <p className="cards-head dim">Per card <span className="cards-note">whole period — these add
        up to the total above</span></p>
      <ul className="ctx-list">
        {totals.slice(0, shown).map((e) => row(e.task, e.seconds, e.events, "over the period"))}
      </ul>
      {totals.length > shown ? (
        <button className="linkish" onClick={() => setShown(shown + PAGE)}>
          {totals.length - shown} more →
        </button>
      ) : null}
    </>
  );
}

/* A sitting's span, as a person reads it: `14:20 → 15:05`. The DATE is not repeated per group — the
 * list is fourteen days at most and the profile says so above it. */
function when(sitting: Stretch): string {
  const clock = (at: number): string => new Date(at * 1000)
    .toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  return `${clock(sitting.started)} → ${clock(sitting.ended)}`;
}

function ownFacts(context: ContextView | null, dev: string): {
  objective: Fact | null;
  decisions: Fact[];
} {
  const his = (facts: Fact[]): Fact[] => facts.filter((f) => devOf(f.owner) === dev);
  return {
    objective: (context?.objectives ?? []).find((f) => devOf(f.owner) === dev) ?? null,
    /* BOTH levels, kept apart by the caller: a person's own calls exist at project level and inside
     * the chapter, and reading only one array would drop half of somebody's own context depending
     * on where they wrote it. */
    decisions: [...his(context?.project_decisions ?? []), ...his(context?.decisions ?? [])],
  };
}
