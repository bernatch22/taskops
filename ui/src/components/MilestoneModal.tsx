/* The dashboard of ONE chapter: what it is for, how far along, and the facts that live and die
 * with it.
 *
 * INFO ONLY — no card list, deliberately. The board is three inches below this modal and already
 * draws them, filtered to this very chapter, so a list here would be the same rows rendered twice
 * with two different sets of bugs. What cannot be seen anywhere else is the goal, the rules that
 * end with the chapter, and who is chasing what inside it. That is what this is.
 *
 * The order is the reading order and it is an argument: the GOAL first, because everything below it
 * exists to serve it; then who is on it; then the rules, which constrain; then the decisions, which
 * are settled; then the notes, which are neither. Same order as the injected prompt — a person and
 * an agent should not have to learn two shapes for one chapter.
 */

import type { ContextView, Fact, Milestone } from "../contracts";
import { FactBlock, Group } from "./facts";
import { MARK, Progress, countOf, short, whoIsWhere } from "./Picker";
import { Overlay } from "./Overlay";
import type { Board } from "../contracts";

export function MilestoneModal({ chapter, context, board, onClose }: {
  chapter: Milestone;
  context: ContextView;
  board: Board | null;
  onClose: () => void;
}): JSX.Element {
  const counts = countOf(context, chapter.id);
  const its = (facts: Fact[]): Fact[] => facts.filter((f) => f.milestone === chapter.id);
  const actors = whoIsWhere(board).get(chapter.id) ?? [];
  return (
    <Overlay label={chapter.title} onClose={onClose}>
      <header className="ms-head">
        <span className={`ms-mark ms-${chapter.state}`}>{MARK[chapter.state] ?? "·"}</span>
        <h2>{chapter.title}</h2>
        {chapter.horizon ? <span className="ms-horizon">by {chapter.horizon}</span> : null}
        <button className="close" onClick={onClose} title="close (Esc)">✕</button>
      </header>

      {/* The GOAL, in the largest text in the modal and above everything. A chapter whose goal is
        * a line of small print is a chapter people navigate past — and it is the one field that
        * says when the work is over. Absent on a chapter nobody has written one for, which is the
        * normal state of one just opened, so it says so and names the command. */}
      {chapter.goal
        ? <p className="ms-goal">{chapter.goal}</p>
        : <p className="ms-goal ms-goal-empty">
            No goal written yet — what does <em>done</em> mean, and what is out of scope?{" "}
            <code>taskops milestone edit {chapter.id.slice(0, 8)} --goal "…"</code>
          </p>}

      <div className="ms-facts">
        {counts.total ? <Progress done={counts.done} total={counts.total} /> : null}
        {counts.review ? <span className="dim">{counts.review} in review</span> : null}
        {counts.ready ? <span className="dim">{counts.ready} ready</span> : null}
        {counts.blocked ? <span className="dim">{counts.blocked} blocked</span> : null}
        {actors.length ? <span className="ms-who">{actors.map(short).join(" · ")}</span> : null}
        <Scopes chapter={chapter} board={board} />
        <code className="context-id dim">{chapter.id.slice(0, 8)}</code>
      </div>

      {/* `review` is the one state that must be drawn differently: an agent reported it finished,
        * nothing has archived on its word, and NOTHING NEW starts under it until a person acts.
        * Both ways out are named — a reader told only "waiting" has to guess whether they are meant
        * to verify or to reject. */}
      {chapter.state === "review" ? (
        <section className="ms-waiting">
          <p className="ms-waiting-head">Reported finished — a person has to close it</p>
          {chapter.note ? <p className="ms-note">“{chapter.note}”</p> : null}
          <p className="ms-how">
            <code>taskops milestone done {chapter.id.slice(0, 8)}</code> to verify, or{" "}
            <code>taskops milestone reject {chapter.id.slice(0, 8)} -m "…"</code> to send it back.
            Nothing new starts under this chapter until then.
          </p>
        </section>
      ) : null}

      <div className="ms-body">
        <Group title="Objectives" note="what each dev is chasing inside this chapter">
          {its(context.objectives).map((fact) => <FactBlock key={fact.id} fact={fact} />)}
        </Group>
        <Group title="Rules" note="this chapter's — they end with it">
          {its(context.rules).map((fact) => <FactBlock key={fact.id} fact={fact} />)}
        </Group>
        <Group title="Decisions" note="settled, so it is not re-litigated">
          {its(context.decisions).map((fact) => <FactBlock key={fact.id} fact={fact} />)}
        </Group>
        <Group title="Notes" note="standing, and neither a goal nor a rule">
          {its(context.notes).map((fact) => <FactBlock key={fact.id} fact={fact} />)}
        </Group>
        {!its(context.objectives).length && !its(context.rules).length
          && !its(context.decisions).length && !its(context.notes).length ? (
          <p className="ctx-empty">
            Nothing stated under this chapter yet. What gets decided here dies with it —{" "}
            <code>taskops context decision "…"</code>. What must outlive it belongs to the project
            (<code>--project</code>), which is the ◎ panel.
          </p>
        ) : null}
      </div>
    </Overlay>
  );
}

/* What this chapter TOUCHES, from the labels of its own cards. Derived rather than a field: a
 * chapter groups cards of several scopes and that is the point of one, but a `scopes` column
 * somebody had to maintain would be wrong the first week. */
function Scopes({ chapter, board }: { chapter: Milestone; board: Board | null }): JSX.Element | null {
  const labels = new Set<string>();
  for (const column of board?.columns ?? []) {
    for (const card of column.cards) {
      if (card.task.milestone === chapter.id) card.task.labels.forEach((l) => labels.add(l));
    }
  }
  if (!labels.size) return null;
  return <span className="ms-scopes dim">touches {[...labels].sort().join(" · ")}</span>;
}
