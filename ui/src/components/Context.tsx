/* The standing context: one line always on screen, and everything behind it in a modal.
 *
 * This is the one panel in the app that is not about a moment. The board says what is happening,
 * activity says what happened, reports say what it meant — all three change every few seconds and
 * all three are read by looking. The objective and the invariants are the opposite: they change
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
 * Still tabbed, because two of the questions left are genuinely different: what has this project
 * decided, and what does the engine actually enforce. A DECISION is prose a person weighs, a
 * POLICY is a value the engine obeys and refuses to be wrong about — they looked identical for a
 * while, and that is exactly how a policy ended up hidden inside a decision. */

import { useState } from "react";

import type { ContextView, Fact, Policy } from "../contracts";
import { Overlay } from "./Overlay";

type Tab = "project" | "policies";

export function Context({ context, open, onToggle }: {
  context: ContextView | null;
  open: boolean;
  onToggle: () => void;
}): JSX.Element | null {
  /* Nothing stated at all renders NOTHING — no strip, no empty state, no nudge. A project that
   * has not written an objective is not doing anything wrong, and a permanent bar telling it so
   * would be the app nagging on every screen forever. */
  if (!context || !stated(context)) return null;
  return (
    <>
      <section className={`context${open ? " open" : ""}`}>
        <button className="context-strip" onClick={onToggle} aria-expanded={open}
                title="the standing context — what this project has already decided">
          <span className="context-mark">◎</span>
          <span className="context-objective">
            {context.objective ? context.objective.text : <em className="dim">no objective set</em>}
          </span>
          {context.objective?.horizon
            ? <span className="context-horizon">by {context.objective.horizon}</span> : null}
          <span className="context-counts dim">{summarise(context)}</span>
        </button>
      </section>
      {open ? <Modal context={context} onClose={onToggle} /> : null}
    </>
  );
}

function stated(context: ContextView): boolean {
  return Boolean(context.objective) || context.objectives.length > 0
    || context.notes.length > 0 || context.invariants.length > 0
    || context.decisions.length > 0 || context.policies.length > 0;
}

/* The counts, not the contents: the strip has one line and the objective has first claim on it.
 * A number is enough to say whether opening it is worth a click. */
function summarise(context: ContextView): string {
  const parts: string[] = [];
  const owned = context.objectives.filter((o) => o.owner).length;
  if (owned) parts.push(`${owned} dev objective${plural(owned)}`);
  if (context.invariants.length) parts.push(`${context.invariants.length} invariant${plural(context.invariants.length)}`);
  if (context.decisions.length) parts.push(`${context.decisions.length} decision${plural(context.decisions.length)}`);
  for (const policy of context.policies) if (policy.value) parts.push(`${policy.name}: ${policy.value}`);
  return parts.join(" · ");
}

function plural(n: number): string {
  return n === 1 ? "" : "s";
}

function Modal({ context, onClose }: {
  context: ContextView;
  onClose: () => void;
}): JSX.Element {
  const [tab, setTab] = useState<Tab>("project");
  /* Unowned only. A fact somebody stated for THEMSELVES is theirs across the whole project and
   * belongs on their profile; mixing it in here made "the team decided" and "ana decided, for
   * ana" indistinguishable, which on a question about what is settled is the wrong answer. */
  const project = {
    invariants: context.invariants.filter((f) => !f.owner),
    decisions: context.decisions.filter((f) => !f.owner),
    notes: context.notes.filter((f) => !f.owner),
  };
  return (
    <Overlay label="the standing context" onClose={onClose}>
      <header className="ctx-head">
        <span className="context-mark">◎</span>
        <h2>Standing context</h2>
        <button className="close" onClick={onClose} title="close (Esc)">✕</button>
      </header>

      <nav className="ctx-tabs">
        <Tabs tab={tab} onTab={setTab} counts={{
          project: project.invariants.length + project.decisions.length + project.notes.length,
          policies: context.policies.length,
        }} />
      </nav>

      <div className="ctx-body">
        {tab === "project" ? <Project context={context} facts={project} /> : null}
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
  const named: [Tab, string][] = [["project", "Project"], ["policies", "Policies"]];
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

/* Everything the PROJECT has stated: what it is for, what may never break, what is settled.
 * Facts with an owner are somebody's own and live on their profile, reachable from the avatar row
 * in the header. */
function Project({ context, facts }: {
  context: ContextView;
  facts: { invariants: Fact[]; decisions: Fact[]; notes: Fact[] };
}): JSX.Element {
  return (
    <>
      <Group title="Objective" note="the north — everybody reads it, whatever they hold">
        {context.objective ? [<Line key={context.objective.id} fact={context.objective} />] : []}
      </Group>
      <Group title="Invariants" note="never broken, whatever the card says">
        {facts.invariants.map((fact) => <Line key={fact.id} fact={fact} />)}
      </Group>
      <Group title="Decisions" note="settled, so it is not re-litigated">
        {facts.decisions.map((fact) => <Line key={fact.id} fact={fact} />)}
      </Group>
      <Group title="Notes" note="standing, and neither a goal nor a rule">
        {facts.notes.map((fact) => <Line key={fact.id} fact={fact} />)}
      </Group>
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

function Group({ title, note, children }: {
  title: string;
  note: string;
  children: JSX.Element[];
}): JSX.Element | null {
  /* An empty group is omitted rather than shown empty. Four headings over four "(none)"s is a
   * panel that looks like a form somebody abandoned. */
  if (!children.length) return null;
  return (
    <section className="ctx-group">
      <h4>{title} <span className="dim">{note}</span></h4>
      <ul className="ctx-list">{children}</ul>
    </section>
  );
}

/* One fact as a BLOCK, not a row.
 *
 * The text gets the full width and wraps, and the metadata sits under it. The previous version
 * was a flex row with the text sharing a line with its scope and its id, which is fine until an
 * agent states a paragraph — and stating a paragraph is exactly what `taskops_context` is for. */
function Line({ fact }: { fact: Fact }): JSX.Element {
  const scope = [...fact.labels, ...fact.files];
  return (
    <li className="ctx-fact">
      <p className="context-text">{fact.text}</p>
      <p className="ctx-meta">
        {scope.map((where) => <code className="context-scope" key={where}>{where}</code>)}
        {fact.horizon ? <span className="context-horizon">by {fact.horizon}</span> : null}
        {/* The id is what `taskops context retire <id>` takes, so it is shown for the one action
          * this panel deliberately does not offer: retiring a standing fact from a board is a
          * decision, and it belongs where the reasoning is being typed. */}
        <code className="context-id dim">{fact.id.slice(0, 8)}</code>
      </p>
    </li>
  );
}
