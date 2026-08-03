/* The chapters: what this board is shipping right now, what is written down next, what ended.
 *
 * A tab of the context modal and not a view of its own, because it answers the same question the
 * rest of that modal answers — what has this project decided — one level down: a milestone is a
 * decision about what the next few weeks are for.
 *
 * SEVERAL chapters are active at once on a real board, so this is a list and not a panel with one
 * subject. Each one carries its own facts and its own counts, and that pairing is the point: a
 * chapter's rules die with it, so printing them under its header is the only place they cannot be
 * mistaken for the project's. The project's own block is the tab BEFORE this one, for the same
 * reason in reverse.
 *
 * The CLOSED ones cost a request and are therefore behind a click. `/api/context` carries the
 * active chapters and the planned titles because a person deciding something needs those; a
 * reached milestone changes never again, and loading the whole history to draw a modal nobody
 * opened would be the panel taxing every page load for it.
 */

import { useState } from "react";

import { api, type MilestoneList } from "../api";
import type { ContextView, Fact, Milestone } from "../contracts";
import { FactBlock, Group, Waiting, countLine } from "./facts";

/* Reached and abandoned: everything that is no longer anybody's business, which is exactly what
 * makes it worth having a way back to. The active ones and the planned ones arrive in the slice. */
const ENDED = ["reached", "abandoned"];

export function Milestones({ context }: { context: ContextView }): JSX.Element {
  return (
    <>
      {context.active.map((chapter) => (
        <Chapter key={chapter.id} chapter={chapter} context={context} />
      ))}
      <Orphans context={context} />
      <Planned planned={context.planned} counts={context.counts} />
      <Ended />
      {!context.active.length ? (
        <p className="ctx-empty">
          No milestone in force. Planning refuses without one —{" "}
          <code>taskops milestone new "…"</code> opens the next chapter.
        </p>
      ) : null}
    </>
  );
}

/* One chapter: its header, then the facts that live and die with it, then whose objective sits
 * inside it. `review` is drawn differently and that is the one state that must be: an agent has
 * reported it finished, nothing has archived on its word, and a session must not start new work
 * under it until a person closes or returns it. */
function Chapter({ chapter, context }: {
  chapter: Milestone;
  context: ContextView;
}): JSX.Element {
  const its = (facts: Fact[]): Fact[] => facts.filter((f) => f.milestone === chapter.id);
  return (
    <section className="ctx-chapter">
      <Head chapter={chapter} counts={countLine(context.counts[chapter.id])} />
      {chapter.state === "review" ? (
        <p className="ctx-empty">
          {chapter.note ? <>Reported finished — “{chapter.note}”. </> : null}
          Nothing new starts under this chapter until a person closes or returns it.
        </p>
      ) : null}
      <Group title="Rules" note="this chapter's — they end with it">
        {its(context.rules).map((fact) => <FactBlock key={fact.id} fact={fact} />)}
      </Group>
      <Group title="Decisions" note="settled, so it is not re-litigated">
        {its(context.decisions).map((fact) => <FactBlock key={fact.id} fact={fact} />)}
      </Group>
      <Group title="Notes" note="standing, and neither a goal nor a rule">
        {its(context.notes).map((fact) => <FactBlock key={fact.id} fact={fact} />)}
      </Group>
      <Group title="Objectives" note="what each dev is chasing inside this chapter">
        {its(context.objectives).map((fact) => <FactBlock key={fact.id} fact={fact} />)}
      </Group>
    </section>
  );
}

function Head({ chapter, counts }: { chapter: Milestone; counts: string }): JSX.Element {
  return (
    <p className="ctx-chapter-head">
      <span className="context-mark">◎</span>
      <span className="ctx-chapter-text">{chapter.text}</span>
      {chapter.horizon ? <span className="context-horizon">by {chapter.horizon}</span> : null}
      {counts ? <span className="context-counts dim">{counts}</span> : null}
      {chapter.state === "review" ? <Waiting /> : null}
    </p>
  );
}

/* Cards and facts that name no chapter — everything written before this model existed.
 *
 * SHOWN, not hidden. They are real: those cards are in somebody's queue and those facts were true
 * enough for somebody to write down. Hiding them would make a board look emptier than it is on the
 * one day somebody upgrades. */
function Orphans({ context }: { context: ContextView }): JSX.Element | null {
  const live = new Set(context.active.map((m) => m.id));
  const loose = (facts: Fact[]): Fact[] => facts.filter((f) => !live.has(f.milestone));
  const facts = [...loose(context.rules), ...loose(context.decisions), ...loose(context.notes)];
  const counts = countLine(context.counts[""]);
  if (!facts.length && !counts) return null;
  return (
    <section className="ctx-chapter">
      <p className="ctx-chapter-head">
        <span className="ctx-chapter-text dim">(sin milestone)</span>
        {counts ? <span className="context-counts dim">{counts}</span> : null}
      </p>
      <Group title="Standing" note="written before this board had chapters">
        {facts.map((fact) => <FactBlock key={fact.id} fact={fact} />)}
      </Group>
    </section>
  );
}

/* Titles only, and that is deliberate: a planned chapter has no facts and no cards, so a title is
 * everything there is — and anything more would let it read as something to work on. */
function Planned({ planned, counts }: {
  planned: Milestone[];
  counts: Record<string, Record<string, number>>;
}): JSX.Element | null {
  if (!planned.length) return null;
  return (
    <section className="ctx-group">
      <h4>Next <span className="dim">written down, not started</span></h4>
      <ul className="ctx-list">
        {planned.map((chapter) => (
          <li className="ctx-fact" key={chapter.id}>
            <p className="context-text">{chapter.text}</p>
            <p className="ctx-meta">
              {chapter.horizon
                ? <span className="context-horizon">by {chapter.horizon}</span> : null}
              {countLine(counts[chapter.id])
                ? <span className="context-counts dim">{countLine(counts[chapter.id])}</span>
                : null}
              <code className="context-id dim">{chapter.id.slice(0, 8)}</code>
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

/* The chapters that ended, read-only, behind one click and ONE fetch. Read-only because a reached
 * milestone is a record: reopening one is a decision with a reason, and a reason is typed in a
 * terminal, not clicked in a modal. */
function Ended(): JSX.Element {
  const [all, setAll] = useState<MilestoneList | null>(null);
  const [reading, setReading] = useState(false);
  const [failed, setFailed] = useState("");

  function load(): void {
    setReading(true);
    setFailed("");
    api.milestones()
      .then(setAll)
      .catch((problem: unknown) => {
        setFailed(problem instanceof Error ? problem.message : String(problem));
      })
      .finally(() => setReading(false));
  }

  if (all === null) {
    return (
      <section className="ctx-group">
        <button className="linkish" disabled={reading} onClick={load}>
          {reading ? "reading…" : "the chapters that ended →"}
        </button>
        {failed ? <p className="failed">{failed}</p> : null}
      </section>
    );
  }
  const ended = all.milestones.filter((m) => ENDED.includes(m.state));
  if (!ended.length) return <p className="ctx-empty">No chapter has ended yet.</p>;
  return (
    <section className="ctx-group">
      <h4>Ended <span className="dim">read-only — the record of what shipped</span></h4>
      <ul className="ctx-list">
        {ended.map((chapter) => (
          <li className="ctx-fact" key={chapter.id}>
            <p className="context-text">{chapter.text}</p>
            {chapter.note ? <p className="context-text dim">“{chapter.note}”</p> : null}
            <p className="ctx-meta">
              <span className="dim">{chapter.state}</span>
              {/* The VERIFIER, never the reporter — an agent's word does not close a chapter, and
                * a row that showed whoever said "terminé" would say the opposite. */}
              {chapter.closed_by
                ? <code className="context-id dim">by {chapter.closed_by}</code> : null}
              {countLine(all.counts[chapter.id])
                ? <span className="context-counts dim">{countLine(all.counts[chapter.id])}</span>
                : null}
              <code className="context-id dim">{chapter.id.slice(0, 8)}</code>
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
