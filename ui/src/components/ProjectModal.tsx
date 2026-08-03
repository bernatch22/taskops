/* What the PROJECT has decided — and nothing that belongs to a chapter or to a person.
 *
 * Its own modal, reached from `◎` in the picker, and that separation is the model rather than a
 * layout choice. These facts carry `level: "project"`: they outlive every milestone, so drawn
 * inside a chapter's panel they would read as expiring with it. It used to be a TAB beside
 * `Milestones`, which said the opposite of what is true — that a project fact and a chapter fact
 * are two views of one thing.
 *
 * The policies are here and are drawn apart from the decisions, because a DECISION is prose a
 * person weighs and a POLICY is a value the engine obeys and refuses to be wrong about. They looked
 * identical for a while, and that is exactly how a policy came to be hidden inside a decision,
 * silently doing nothing.
 *
 * The chapters that ENDED are here too: what a project shipped is the project's record, not any
 * open chapter's. One fetch, behind one click, because a reached milestone never changes again and
 * loading the whole history to draw a panel nobody opened would tax every page load for it.
 */

import { useState } from "react";

import { api, type MilestoneList } from "../api";
import type { ContextView, Policy } from "../contracts";
import { FactBlock, Group, countLine } from "./facts";
import { MARK } from "./Picker";
import { Overlay } from "./Overlay";

const ENDED = ["reached", "abandoned"];

export function ProjectModal({ context, repo, onClose }: {
  context: ContextView;
  repo: string;
  onClose: () => void;
}): JSX.Element {
  const nothing = !context.project_rules.length && !context.project_decisions.length;
  return (
    <Overlay label="what this project has decided" onClose={onClose}>
      <header className="ms-head">
        <span className="ms-mark">◎</span>
        <h2>{repo || "this project"}</h2>
        <span className="ms-horizon dim">what holds whatever we are shipping</span>
        <button className="close" onClick={onClose} title="close (Esc)">✕</button>
      </header>

      <div className="ms-body">
        <Group title="Rules" note="every card, every milestone, no exceptions">
          {context.project_rules.map((fact) => <FactBlock key={fact.id} fact={fact} />)}
        </Group>
        <Group title="Decisions" note="the project's — not a chapter's">
          {context.project_decisions.map((fact) => <FactBlock key={fact.id} fact={fact} />)}
        </Group>
        {nothing ? (
          <p className="ctx-empty">
            Nothing stated at project level. What is true whatever anybody is working on goes
            here — <code>taskops context rule "…" --project</code>. Everything else belongs to the
            chapter you are in.
          </p>
        ) : null}

        <Policies policies={context.policies} />
        <Ended />
      </div>
    </Overlay>
  );
}

/* Not prose. `reviewer: peer` decides who may close a card and REFUSES whoever may not, so it is
 * drawn as a setting with a value and never as a sentence somebody wrote. */
function Policies({ policies }: { policies: Policy[] }): JSX.Element {
  const set = policies.filter((policy) => policy.value);
  return (
    <section className="ctx-group">
      <h4>Engine <span className="dim">not advice — it refuses</span></h4>
      {set.length ? (
        <ul className="ctx-list">
          {set.map((policy) => (
            <li className="ctx-fact policy" key={policy.name}>
              <p className="context-text">
                <code className="context-name">{policy.name}</code> {policy.value}
              </p>
              <p className="ctx-meta"><code className="context-id dim">{policy.actor}</code></p>
            </li>
          ))}
        </ul>
      ) : <p className="ctx-empty">Nothing set — every default is off.</p>}
    </section>
  );
}

/* The record: what shipped and who signed it. Read-only, because reopening a reached chapter is a
 * decision with a reason and a reason is typed in a terminal, not clicked in a modal. */
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
      <h4>Shipped <span className="dim">the record — read-only</span></h4>
      <ul className="ctx-list">
        {ended.map((chapter) => (
          <li className="ctx-fact" key={chapter.id}>
            <p className="context-text">
              <span className="ms-mark">{MARK[chapter.state] ?? "·"}</span> {chapter.title}
            </p>
            {chapter.goal ? <p className="context-text dim">{chapter.goal}</p> : null}
            {chapter.note ? <p className="context-text dim">“{chapter.note}”</p> : null}
            <p className="ctx-meta">
              <span className="dim">{chapter.state}</span>
              {/* The VERIFIER, never the reporter: an agent's word does not close a chapter, and a
                * row showing whoever said "terminé" would say the opposite of the whole model. */}
              {chapter.closed_by
                ? <code className="context-id dim">by {chapter.closed_by}</code>
                : <code className="context-id dim">nobody on record</code>}
              {countLine(all.counts[chapter.id])
                ? <span className="context-counts dim">{countLine(all.counts[chapter.id])}</span>
                : null}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
