/* One fact, one group of them, and the count that makes a chapter a todo-list.
 *
 * Its OWN module, and that is what the milestone tab cost: a fact is now drawn in four places —
 * the project block, a chapter's block, a person's profile and the card drawer — and the tab that
 * draws chapters cannot import from the panel that hosts it without the two modules importing each
 * other. A second renderer would drift, and the first thing a copy drops is the id, which is the
 * only part of a fact anybody can act on.
 */

import type { Fact } from "../contracts";

/* One fact as a BLOCK, not a row.
 *
 * The text gets the full width and wraps, and the metadata sits under it. The previous version
 * was a flex row with the text sharing a line with its scope and its id, which is fine until an
 * agent states a paragraph — and stating a paragraph is exactly what `taskops_context` is for. */
export function FactBlock({ fact }: { fact: Fact }): JSX.Element {
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

export function Group({ title, note, kind, children }: {
  title: string;
  note: string;
  /* An optional class on the section, for the ONE distinction worth drawing: a rule binds and a
   * decision was settled, and a reader scanning for "am I allowed to" is looking for the first. */
  kind?: string;
  children: JSX.Element[];
}): JSX.Element | null {
  /* An empty group is omitted rather than shown empty. Four headings over four "(none)"s is a
   * panel that looks like a form somebody abandoned. */
  if (!children.length) return null;
  return (
    <section className={kind ? `ctx-group ${kind}` : "ctx-group"}>
      <h4>{title} <span className="dim">{note}</span></h4>
      <ul className="ctx-list">{children}</ul>
    </section>
  );
}

/* The one chip in this UI that means "a machine cannot clear this". Amber and worded as the thing a
 * person has to do, not as a state name: `review` is what the log says, "waiting for a person" is
 * what it means to whoever is reading — and it is the one milestone state where a session must not
 * start new work under the chapter. Here rather than in the tab that draws chapters because the card
 * drawer shows it too, on a card whose own milestone is waiting. */
export function Waiting(): JSX.Element {
  return <span className="chip waiting">waiting for a person</span>;
}

/* `7 cards · 3 done · 2 review` — a chapter's cards by status, as one line.
 *
 * A COUNT and not an opinion, which is the whole reason every card belongs to a milestone: "how
 * far along is it" stops being a thing somebody estimates. Empty when the chapter has no cards
 * yet, so the caller can leave the line out rather than print a zero.
 *
 * `done` and `review` are named and the rest is not, because those two are the ones that say
 * whether the chapter is nearly over.
 *
 * A WITHDRAWN card is not one of the cards. `cancelled` comes out of the total and is reported
 * beside it when there is any, which is the server's own reasoning for counting it in the first
 * place: "3 of 9 done" and "3 of 9 done, 1 withdrawn" are two sentences and only one of them is a
 * lie. Left inside the total it would make a finished chapter read as unfinished forever.
 *
 * `total` is a KEY in that map and not a status — `usecases._contextviews.chapters` writes it
 * alongside them — so it is skipped here rather than added in. Summing the statuses instead of
 * trusting it is the same number by construction and cannot double-count, which is exactly what
 * the first version of this did against a real board: one card, `{ready: 1, total: 1}`, "2 cards". */
export function countLine(counts: Record<string, number> | undefined): string {
  if (!counts) return "";
  const of = (status: string): number => counts[status] ?? 0;
  const total = Object.entries(counts)
    .filter(([status]) => status !== "cancelled" && status !== "total")
    .reduce((sum, [, n]) => sum + n, 0);
  if (!total) return "";
  const parts = [`${total} card${total === 1 ? "" : "s"}`];
  if (of("done")) parts.push(`${of("done")} done`);
  if (of("review")) parts.push(`${of("review")} in review`);
  if (of("blocked")) parts.push(`${of("blocked")} blocked`);
  if (of("cancelled")) parts.push(`${of("cancelled")} withdrawn`);
  return parts.join(" · ");
}
