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
import type { Activity, Attended, Board, ContextView, Event, Fact } from "../contracts";
import { ago } from "./bits";
import { Overlay } from "./Overlay";

/* How far back a profile looks. Long enough that somebody who took Friday off still has a
 * footprint, short enough that it is a picture of NOW rather than of the project's history —
 * which is what the activity view is for, and it is one click away. */
const WINDOW = "14d";
const CARDS = 6;

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
  useEffect(() => {
    let alive = true;
    api.activity(WINDOW)
      .then((got) => { if (alive) setActivity(got); })
      .catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [dev]);

  const [tab, setTab] = useState<"work" | "context">("work");
  const mine = (activity?.events ?? []).filter((e) => devOf(e.actor) === dev);
  const roll = (activity?.actors ?? []).filter((a) => devOf(a.actor) === dev);
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
              <h4>Cards <span className="dim">what they touched, last {WINDOW}</span></h4>
              {failed ? <p className="ctx-empty">could not read the log just now.</p>
                : activity === null ? <p className="ctx-empty">reading…</p>
                : <Cards events={mine} titles={activity.titles} holding={person?.holding ?? []}
                         on={on} onOpen={onOpen} />}
              {/* The bound, stated where the numbers are. A window capped at 600 events makes every
                * total on this tab a partial one, and a partial number that does not say so is the
                * exact failure this project keeps paying for. */}
              {activity?.truncated
                ? <p className="ctx-empty">The window hit its limit, so these totals are partial.</p>
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

function Numbers({ roll }: { roll: { tasks: number; commits: number; done: number;
                                     last_seen: number }[] }): JSX.Element | null {
  if (!roll.length) return null;
  /* Summed over this dev's agents, because the fold is the whole point: a developer's output is
   * what their hands did, and they have several. */
  const total = roll.reduce((into, one) => ({
    tasks: into.tasks + one.tasks, commits: into.commits + one.commits,
    done: into.done + one.done, last_seen: Math.max(into.last_seen, one.last_seen),
  }), { tasks: 0, commits: 0, done: 0, last_seen: 0 });
  return (
    <div className="stats">
      <span className="stat"><b>{total.tasks}</b> cards</span>
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
/* `5400` -> `1h 30m`, `240` -> `4m`, `0` -> "". Zero prints NOTHING rather than `0m`: a card touched
 * once has no span between its one event and nothing, and `0m` beside it reads as a measurement that
 * came out empty instead of a question that cannot be asked. */
export function spell(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  if (!minutes) return "";
  const hours = Math.floor(minutes / 60);
  return hours ? `${hours}h${minutes % 60 ? ` ${minutes % 60}m` : ""}` : `${minutes}m`;
}

function Cards({ events, titles, holding, on, onOpen }: {
  events: Event[];
  titles: Record<string, string>;
  holding: string[];
  on: Map<string, Attended>;
  onOpen: (id: string) => void;
}): JSX.Element {
  const order: string[] = [];
  for (const event of events) {
    if (event.task && event.task !== "project" && !order.includes(event.task)) {
      order.push(event.task);
    }
  }
  if (!order.length) return <p className="ctx-empty">nothing in the last {WINDOW}.</p>;
  return (
    <ul className="ctx-list">
      {order.slice(0, CARDS).map((id) => (
        <li key={id}>
          <button className="ctx-card" onClick={() => onOpen(id)}>
            <code className="context-id">{id}</code>
            <span className="ctx-card-title">{titles[id] ?? "…"}</span>
            {/* At least this long — the measure caps every gap, so it under-reports on purpose. The
              * title says which it is, because a bound drawn as if it were the answer is worse than
              * no number: nothing in the log records when somebody stopped. */}
            {spell(on.get(id)?.seconds ?? 0) ? (
              <span className="ctx-card-time"
                    title={`at least this long: the gaps between ${on.get(id)?.events} events, `
                           + "each capped at 30m, so it under-reports rather than guessing"}>
                {spell(on.get(id)?.seconds ?? 0)}
              </span>
            ) : null}
            {holding.includes(id) ? <span className="context-horizon">now</span> : null}
          </button>
        </li>
      ))}
    </ul>
  );
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
