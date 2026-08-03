/* The standing context: one line always on screen, and everything behind it in a modal.
 *
 * This is the one panel in the app that is not about a moment. The board says what is happening,
 * activity says what happened, reports say what it meant — all three change every few seconds and
 * all three are read by looking. The chapter and the settled decisions are the opposite: they change
 * about once a week and their whole value is being in your eye while you decide something else.
 * A worker gets its slice injected on every card; a PERSON had nowhere to see it at all.
 *
 * So the shape is a STRIP plus a MODAL, and the second half replaced an inline expansion that had
 * two problems the day a real project used it. It pushed the board down — reference material
 * shoving the work off the screen — and it was a three-column grid of one-line rows, which is a
 * layout that assumes every fact is short. An agent can state a paragraph, and did.
 *
 * It is about the PROJECT and nothing else. It had a "who is on what" tab, and that tab is gone to
 * the avatar row in the header: a person's own objective and their standing calls are about a
 * PERSON, they now have a profile of their own, and two surfaces drawing the same facts is the
 * duplication that makes one of them go stale.
 *
 * THE STRIP SHOWS THE CHAPTERS, not an objective. The project's north used to be a fact somebody
 * wrote and nobody could finish; it is a milestone now, which is a thing with an end, a horizon and
 * a count of its own cards — so the one line on screen says what is being shipped and how far along
 * it is, and several may be true at once.
 *
 * Three tabs, and the ORDER is the argument. PROJECT first: those facts are true whatever anybody
 * is working on, and printed inside a chapter they would look like they expire with it. MILESTONES
 * second: what is true until this ships. POLICIES last, and separate from both, because a DECISION
 * is prose a person weighs and a POLICY is a value the engine obeys and refuses to be wrong about —
 * they looked identical for a while, and that is exactly how a policy ended up hidden inside a
 * decision.
 */

import { useState } from "react";

import type { ContextView, Policy } from "../contracts";
import { FactBlock, Group, Waiting, countLine } from "./facts";
import { Milestones } from "./Milestones";
import { Overlay } from "./Overlay";

type Tab = "project" | "milestones" | "policies";

export function Context({ context, open, onToggle }: {
  context: ContextView | null;
  open: boolean;
  onToggle: () => void;
}): JSX.Element | null {
  /* Nothing stated at all renders NOTHING — no strip, no empty state, no nudge. A project that
   * has not opened a chapter is not doing anything wrong, and a permanent bar telling it so
   * would be the app nagging on every screen forever. */
  if (!context || !stated(context)) return null;
  /* The FIRST active chapter takes the line and the rest become a count. Not a rotation and not
   * two lines: a strip that changes height as a board opens a second milestone is the layout
   * moving under somebody's cursor, and the modal is one click away. */
  const [first, ...rest] = context.active;
  const counts = first ? countLine(context.counts[first.id]) : "";
  const enforced = settings(context);
  return (
    <>
      <section className={`context${open ? " open" : ""}`}>
        <button className="context-strip" onClick={onToggle} aria-expanded={open}
                title="the chapters in force — and what this project has already decided">
          <span className="context-mark">◎</span>
          <span className="context-milestone">
            {first ? first.text : <em className="dim">no milestone in force</em>}
          </span>
          {rest.length ? <span className="context-counts dim">+{rest.length}</span> : null}
          {first?.state === "review" ? <Waiting /> : null}
          {first?.horizon ? <span className="context-horizon">by {first.horizon}</span> : null}
          {/* Two spans and not one string: `7 cards · 3 done` is about the chapter and
            * `reviewer: peer` is a setting the engine enforces, and joining them with the same
            * separator read as one sentence in which the policy was a fourth count.
            *
            * Each one is OMITTED when empty rather than rendered blank — the strip is a flex row
            * with a 10px gap, so an empty span is a 10px hole in the middle of the line. Seen on a
            * real board with no policy set. */}
          {counts ? <span className="context-counts dim">{counts}</span> : null}
          {enforced ? <span className="context-counts dim">{enforced}</span> : null}
        </button>
      </section>
      {open ? <Modal context={context} onClose={onToggle} /> : null}
    </>
  );
}

function stated(context: ContextView): boolean {
  return context.active.length > 0 || context.planned.length > 0
    || context.project_rules.length > 0 || context.project_decisions.length > 0
    || context.rules.length > 0 || context.decisions.length > 0
    || context.notes.length > 0 || context.objectives.length > 0
    || context.policies.length > 0;
}

/* What the ENGINE enforces, on the strip beside the chapter — `reviewer: peer` changes who may
 * close a card, and that is worth knowing without opening anything. */
function settings(context: ContextView): string {
  return context.policies.filter((p) => p.value)
    .map((policy) => `${policy.name}: ${policy.value}`).join(" · ");
}

function Modal({ context, onClose }: {
  context: ContextView;
  onClose: () => void;
}): JSX.Element {
  const [tab, setTab] = useState<Tab>("project");
  return (
    <Overlay label="the standing context" onClose={onClose}>
      <header className="ctx-head">
        <span className="context-mark">◎</span>
        <h2>Standing context</h2>
        <button className="close" onClick={onClose} title="close (Esc)">✕</button>
      </header>

      <nav className="ctx-tabs">
        <Tabs tab={tab} onTab={setTab} counts={{
          project: context.project_rules.length + context.project_decisions.length,
          milestones: context.active.length,
          policies: context.policies.length,
        }} />
      </nav>

      <div className="ctx-body">
        {tab === "project" ? <Project context={context} /> : null}
        {tab === "milestones" ? <Milestones context={context} /> : null}
        {tab === "policies" ? <Policies policies={context.policies} /> : null}
      </div>
    </Overlay>
  );
}

function Tabs({ tab, onTab, counts }: {
  tab: Tab;
  onTab: (t: Tab) => void;
  counts: Record<Tab, number>;
}): JSX.Element {
  const named: [Tab, string][] = [
    ["project", "Project"], ["milestones", "Milestones"], ["policies", "Policies"],
  ];
  return (
    <>
      {named.map(([key, label]) => (
        <button key={key} className={`ctx-tab${tab === key ? " on" : ""}`}
                onClick={() => onTab(key)} aria-selected={tab === key} role="tab">
          {label}
          {counts[key] ? <span className="tally">{counts[key]}</span> : null}
        </button>
      ))}
    </>
  );
}

/* What the PROJECT has stated — `level: "project"`, so it outlives every chapter. Nothing here is
 * narrowed by a milestone and nothing here expires with one, which is the whole reason it is not
 * drawn inside the chapter blocks: a rule printed under a milestone reads as ending with it.
 *
 * Facts with an owner are somebody's own and live on their profile, reachable from the avatar row
 * in the header — and by construction they are not project-level, so nothing filters them out
 * here any more. */
function Project({ context }: { context: ContextView }): JSX.Element {
  return (
    <>
      <Group title="Rules" note="every card, every milestone, no exceptions">
        {context.project_rules.map((fact) => <FactBlock key={fact.id} fact={fact} />)}
      </Group>
      <Group title="Decisions" note="settled, so it is not re-litigated">
        {context.project_decisions.map((fact) => <FactBlock key={fact.id} fact={fact} />)}
      </Group>
      {!context.project_rules.length && !context.project_decisions.length ? (
        <p className="ctx-empty">
          Nothing stated at project level. What is true whatever anybody is working on goes
          here — <code>taskops context rule "…" --project</code>.
        </p>
      ) : null}
    </>
  );
}

function Policies({ policies }: { policies: Policy[] }): JSX.Element {
  if (!policies.length) {
    return <p className="ctx-empty">Nothing set — every default is off.</p>;
  }
  return (
    <ul className="ctx-list">
      {policies.map((policy) => (
        <li className="ctx-fact" key={policy.name}>
          <p className="context-text">
            <code className="context-name">{policy.name}</code>{" "}
            {policy.value || <em className="dim">(none)</em>}
          </p>
          <p className="ctx-meta"><code className="context-id dim">{policy.actor}</code></p>
        </li>
      ))}
    </ul>
  );
}
