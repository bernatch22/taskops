/* Every component that draws a chapter, rendered to a string against the real fixture.
 *
 * The assertions are deliberately about BEHAVIOUR and not about markup. Markup changes every time
 * somebody improves a layout, and a test that pins class names makes the next improvement look like
 * a regression. What must not change is: the picker names the chapter, the modals draw the goal and
 * the chapter's own facts, and PICKING ONE CHANGES THE CARDS — which is the bug this file exists
 * for, and the one thing `tsc` and the API payload were both happy about.
 */

import { renderToStaticMarkup } from "react-dom/server";

import { Board } from "../src/components/Board";
import { MilestoneModal } from "../src/components/MilestoneModal";
import { peopleOf, spell } from "../src/components/People";
import { Menu, Picker } from "../src/components/Picker";
import { ProjectModal } from "../src/components/ProjectModal";
import type { Board as BoardData, ContextView } from "../src/contracts";
import fixture from "./fixture.json";

const context = fixture.context as unknown as ContextView;
const board = fixture.board as unknown as BoardData;
const chapters = [...context.active, ...context.planned];
const [first, second] = context.active;

let failed = 0;
function check(what: string, ok: boolean, saw?: unknown): void {
  if (ok) {
    console.log(`  ok   ${what}`);
    return;
  }
  failed += 1;
  console.log(`  FAIL ${what}${saw === undefined ? "" : `\n       saw: ${String(saw)}`}`);
}

/* The titles on the board, in the order they were drawn. The one thing every assertion below is
 * about, so it is read out of the markup once and by one rule. */
function titlesOn(chapter: string): string[] {
  const html = renderToStaticMarkup(
    <Board board={board} hideEmpty={false} grouping="date" chapter={chapter} chapters={chapters}
           onClear={() => {}} onGrouping={() => {}} onOpen={() => {}} />);
  return (html.match(/class="title">[^<]+/g) ?? []).map((found) => found.slice(14));
}

const picker = (picked: string): string => renderToStaticMarkup(
  <Picker context={context} board={board} picked={picked} onPick={() => {}}
          onDashboard={() => {}} onProject={() => {}} />);

console.log("picker");
check("with no filter it offers every milestone", picker("").includes("All milestones"));
check("with one picked it names THAT chapter", picker(first.id).includes(first.title));
check("and offers its dashboard", picker(first.id).includes("pill-info"));
check("the project panel is always reachable", picker("").includes("pill-project"));
/* The case a real board landed in the day it upgraded: a chapter IN FORCE whose cards are all still
 * legacy, so it has none. The row used to call that "not started" — this menu's own word for the
 * `planned` group — so a chapter with a `◆` beside it read as one nobody had opened. The fixture
 * cannot carry it (both its active chapters have cards), so the empty one is built here. */
const emptyChapter = { ...first, id: "0000emptychapter", title: "Recien abierto" };
const rowsFor = (list: typeof chapters): string => renderToStaticMarkup(
  <Menu context={context} board={board} chapters={list} loose={0} picked="" onPick={() => {}} />);
const emptyRow = rowsFor([emptyChapter]);
check("a chapter in force with no cards says `no cards`, not `not started`",
      emptyRow.includes("no cards") && !emptyRow.includes("not started"), emptyRow);
const plannedRow = rowsFor([context.planned[0]]);
check("and a PLANNED one still does say `not started`",
      plannedRow.includes("not started"), plannedRow);

console.log("the board");
const all = titlesOn("");
const mine = titlesOn(first.id);
const theirs = titlesOn(second.id);
check("unfiltered draws every card", all.length === board.total, `${all.length} of ${board.total}`);
/* THE assertion. Picking a chapter has to change the cards — every card drawn belongs to it, there
 * are fewer than the whole board, and the OTHER chapter's cards are gone rather than reordered. */
check("picking a chapter draws only its cards", mine.length > 0 && mine.length < all.length,
      `${mine.length} of ${all.length}`);
check("and the other chapter's are gone", !mine.some((title) => theirs.includes(title)),
      mine.filter((title) => theirs.includes(title)).join(", "));
check("the two chapters together are the whole board",
      mine.length + theirs.length === all.length, `${mine.length} + ${theirs.length}`);
/* The COLUMNS do not move. They are the board's vocabulary and a filter that changed them would be
 * a different board — which is what the first attempt at this did. */
const columnsIn = (chapter: string): number => (renderToStaticMarkup(
  <Board board={board} hideEmpty={false} grouping="date" chapter={chapter} chapters={chapters}
         onClear={() => {}} onGrouping={() => {}} onOpen={() => {}} />).match(/class="column /g) ?? []
).length;
check("the columns stay put", columnsIn("") === columnsIn(first.id) && columnsIn("") > 1);
const html = renderToStaticMarkup(
  <Board board={board} hideEmpty={false} grouping="date" chapter="" chapters={chapters}
         onClear={() => {}} onGrouping={() => {}} onOpen={() => {}} />);
check("unfiltered, a card says which chapter it is in", html.includes(`◆ ${first.title}`));
check("filtered, it does not repeat the picker", !titlesOn(first.id).length
  || !renderToStaticMarkup(
      <Board board={board} hideEmpty={false} grouping="date" chapter={first.id} chapters={chapters}
             onClear={() => {}} onGrouping={() => {}} onOpen={() => {}} />).includes("card-chapter"));

console.log("the milestone dashboard");
const dash = renderToStaticMarkup(
  <MilestoneModal chapter={first} context={context} board={board} onClose={() => {}} />);
check("the goal is drawn whole", dash.includes(first.goal.slice(0, 60)));
/* A goal arrives in PARAGRAPHS, and a `<p>` collapsed every newline in it — a real one came out as
 * twenty unbroken lines. It goes through the same reader the reports use, so its own shape survives:
 * two paragraphs and a list must draw more than one block. */
const shaped = { ...first, goal: "Primero, la maquina.\n\nDespues el menu:\n\n- #120 espera veredicto\n- #121 es el ultimo slot" };
const shapedDash = renderToStaticMarkup(
  <MilestoneModal chapter={shaped} context={context} board={board} onClose={() => {}} />);
check("a goal with paragraphs and a list is not one wall of text",
      (shapedDash.match(/class="md-p"/g) ?? []).length >= 2 && shapedDash.includes("<li>"),
      shapedDash.slice(shapedDash.indexOf("ms-goal"), shapedDash.indexOf("ms-goal") + 320));
check("its own facts are under it",
      context.rules.filter((f) => f.milestone === first.id).every((f) => dash.includes(f.text)));
check("a fact of the OTHER chapter is not",
      !context.rules.some((f) => f.milestone === second.id && dash.includes(f.text)));
check("no card list — the board is right underneath", !dash.includes('class="card'));
/* Everything below the header lives inside ONE scroller. The goal used to sit outside it, so a long
 * one grew the panel past the viewport and took the progress bar and the chapter's facts somewhere
 * no scroll reached — measured on a live board with a real goal. */
const scrolled = shapedDash.slice(shapedDash.indexOf('class="ms-scroll"'));
check("the goal and the facts are both inside the one scroller",
      shapedDash.includes('class="ms-scroll"')
      && scrolled.indexOf("ms-goal") < scrolled.indexOf("ms-body")
      && scrolled.includes("ms-body"),
      shapedDash.slice(0, 200));

console.log("who is on the board");
/* The shape a real board is in most of the time, and the one the fixture is not: every open card
 * sits in `review` (which releases the lease) or is unassigned, so there is no live state to derive
 * anybody from. Measured on axion: 0 leases, 0 assignees, 63 cards, two developers — and the header
 * drew nothing. The names were in `created_by` all along. */
const quiet = {
  ...board,
  columns: board.columns.map((column) => ({
    ...column,
    cards: column.cards.map((card) => ({
      ...card, lease: null, task: { ...card.task, assignee: "" },
    })),
  })),
} as unknown as BoardData;
const creators = new Set(quiet.columns.flatMap(
  (column) => column.cards.map((card) => card.task.created_by)));
const quietFaces = peopleOf(quiet, { ...context, objectives: [] } as unknown as ContextView);
check("with nothing in anybody's hands, the board still names who is on it",
      quietFaces.length > 0, `${quietFaces.length} faces from ${creators.size} creators`);
check("and it is the developers, folded from their agents",
      quietFaces.every((person) => [...creators].some((id) => id.includes(person.dev))),
      quietFaces.map((p) => p.dev).join(", "));

/* The time on a card is folded server-side (see tests/engine/test_timespent.py); what this pins is
 * how it READS. Zero prints nothing on purpose: a card touched once has no span between its one event
 * and nothing, and `0m` beside it reads as a measurement that came out empty. */
check("time reads as hours and minutes", spell(5400) === "1h 30m" && spell(3600) === "1h"
      && spell(240) === "4m", `${spell(5400)} · ${spell(3600)} · ${spell(240)}`);
check("and zero prints NOTHING rather than 0m", spell(0) === "" && spell(20) === "", `"${spell(20)}"`);

console.log("the project panel");
const proj = renderToStaticMarkup(
  <ProjectModal context={context} repo="/tmp/px" onClose={() => {}} />);
check("the project's rules are here",
      context.project_rules.every((f) => proj.includes(f.text)));
check("and a CHAPTER's rule is not — it dies with its chapter",
      !context.rules.some((f) => proj.includes(f.text)));
check("what the engine enforces is drawn apart", proj.includes("Engine"));

console.log(failed ? `\n${failed} failed` : "\nall good");
process.exit(failed ? 1 : 0);
