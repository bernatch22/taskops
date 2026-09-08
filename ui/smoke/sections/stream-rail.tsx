import { renderToStaticMarkup } from "react-dom/server";

import { EditorView, columnsFor, type EditorViewProps } from "../../src/pages/Editor";
import { Stream } from "../../src/components/stream/Stream";
import {
  arrivedAt,
  dayLabel,
  fresh,
  freshness,
  keep,
  moments,
  progressOf,
  roll,
  said,
} from "../../src/components/stream/model";
import { changed } from "../../src/components/card/Thread";
import { EMPTY_FEED } from "../../src/useEvents";
import { merge, stamp } from "../../src/useEvents";
import { workingFolders } from "../../src/components/editor/tree";
import type { OpenTab } from "../../src/components/editor/useWorktree";
import type { Event } from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

/* THE STREAM RAIL — the log beside the code (ARCHITECTURE.md §23).
 *
 * Everything this section pins is a PURE function or the pure half of a
 * component, which is the whole reason the feature was cut where it was: the
 * fold, the roll-up, the freshness tiers and the merge are `model.ts` and
 * `useEvents.ts` exports, and `Stream` renders under `react-dom/server` with no
 * client, no socket and no timer. What is NOT here — the scroll position, the
 * one interval, the catch-up walk — is exactly what a headless harness cannot
 * honestly claim to have tested, and it is left to say so rather than faked
 * with a jsdom.
 */
export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { now } = h;
  const e = fixture.editor;

  /* A minute of a real board, newest first, the way the feed hands it over.
     One worker's run on one card (four events inside two minutes), then a
     different person on a different card, then that SAME person on that SAME
     card half an hour earlier — same actor, same task, so the ONLY thing that
     can split those two is the gap, which is what makes the check below a test
     of the gap and not of the actor. */
  const log: readonly Event[] = [
    { id: "e1", task: "tk-4b37dd", actor: "agent:berna/m6", kind: "edited", body: { field: "progress", to: 68 }, ts: now - 20 },
    { id: "e2", task: "tk-4b37dd", actor: "agent:berna/m6", kind: "comment", body: { text: "the fold is on (actor, task), not on actor alone" }, ts: now - 40 },
    { id: "e3", task: "tk-4b37dd", actor: "agent:berna/m6", kind: "commit", body: { sha: "aaa1111", subject: "the rail", numstat: { "ui/src/a.tsx": [30, 2], "logo.png": null } }, ts: now - 70 },
    { id: "e4", task: "tk-4b37dd", actor: "agent:berna/m6", kind: "commit", body: { sha: "bbb2222", subject: "again", numstat: { "ui/src/a.tsx": [11, 5] } }, ts: now - 130 },
    { id: "e5", task: "tk-8a2f10", actor: "dev:berna", kind: "comment", body: { text: "land the seam first" }, ts: now - 200 },
    { id: "e6", task: "tk-8a2f10", actor: "dev:berna", kind: "claimed", body: { branch: "tk-8a2f10" }, ts: now - 2000 },
  ];

  /* ── the fold: a moment is a RUN, and it never reaches over somebody else ── */

  const folded = moments(log);
  check("consecutive work by one worker on one card is one entry", folded.length === 3);
  check(
    "the run holds every event in it, newest first",
    folded[0]!.events.length === 4 && folded[0]!.events[0]!.id === "e1",
  );
  check("a different actor starts a new moment", folded[1]!.task === "tk-8a2f10");
  check(
    "a gap longer than the window starts a new moment, not a continuation",
    folded[2]!.events.length === 1 && folded[2]!.events[0]!.id === "e6",
  );
  check(
    "…and it was the GAP that split them: same actor, same card, either side",
    folded[1]!.actor === folded[2]!.actor && folded[1]!.task === folded[2]!.task,
  );
  check(
    "the moment is keyed on its newest event and dated by it",
    folded[0]!.key === "e1" && folded[0]!.ts === now - 20 && folded[0]!.from === now - 130,
  );

  /* ── the roll-up: counted, sized, and the worker's own number last ──────── */

  const headline = roll(folded[0]!);
  check("a run is counted by kind, pluralised", headline.includes("2 commits"));
  check(
    "files are counted per PATH across the run, never per commit",
    headline.includes("2 files · +41 −7 · 1 binary"),
  );
  check("the worker's own progress ends the line", headline.endsWith("progress → 68"));
  check("a run of ONE is the log's own phrase, unchanged", roll(folded[1]!) === "land the seam first");
  check("progress is read off an `edited` body, not a kind of its own", progressOf(folded[0]!.events) === 68);
  // The same fold both surfaces use — one commit is a list of one.
  check(
    "the numstat fold is shared with the Event stream",
    changed([log[2]!]) === "2 files · +30 −2 · 1 binary",
  );
  check("what was SAID is carried out of the run", said(folded[0]!, 96)[0]!.text.startsWith("the fold is on"));

  /* ── new is the CLIENT's clock, and it decays by arithmetic ─────────────── */

  const at = 1_000_000;
  const arrivals = new Map<string, number>([["e1", at], ["e2", at]]);
  check("a row that arrived just now is entering", freshness(at, at + 300, false) === "entering");
  check("a second later it is only tinted", freshness(at, at + 2_000, false) === "fresh");
  check("past the window it is at rest", freshness(at, at + 9_000, false) === "rest");
  check(
    "reduced motion keeps the mark and drops the movement",
    freshness(at, at + 300, true) === "fresh",
  );
  check("a row the feed opened with is history, never news", freshness(undefined, at, false) === "rest");
  check("a moment is as new as its newest row", arrivedAt(folded[0]!, arrivals) === at);
  check("the pill counts the same rows the tint lights", fresh(folded, arrivals, at + 1_000) === 1);

  /* ── the merge: arrivals on top, an id never twice ──────────────────────── */

  const have = [log[3]!, log[4]!];
  check("what arrived goes on top", merge(have, [log[0]!])[0]!.id === "e1");
  check("an id already held is not added twice", merge(have, [log[3]!]).length === 2);
  check("nothing arriving is the same list", merge(have, []) === have);
  const stamped = stamp(new Map([["old", 0]]), ["e1"], at, 5_000);
  check("a stamp past its window is dropped, the new one kept", !stamped.has("old") && stamped.get("e1") === at);

  /* ── narrowing: a family, or one card ──────────────────────────────────── */

  check("a family filter narrows to that family", keep(log, "code", null).length === 2);
  check("talk is the comments", keep(log, "talk", null).every((x) => x.kind === "comment"));
  check(
    "following a card narrows to it — every row on it, whoever wrote them",
    keep(log, "all", "tk-8a2f10").map((x) => x.id).join() === "e5,e6",
  );
  check("all + every card is the list itself", keep(log, "all", null) === log);

  /* ── the markup, rendered ───────────────────────────────────────────────── */

  const rail = renderToStaticMarkup(
    <Stream
      moments={folded}
      arrivals={arrivals}
      at={at + 500}
      now={now}
      total={1284}
      filter="all"
      onFilter={() => {}}
      task={null}
      onTask={() => {}}
      onOpen={() => {}}
      more={true}
      loading={false}
      onMore={() => {}}
      waiting={3}
      onTop={() => {}}
      onList={() => {}}
      onScroll={() => {}}
      reduced={false}
    />,
  );
  check("the rail draws one entry per moment", (rail.match(/data-testid="stream-entry"/g) ?? []).length === 3);
  check("an entry names the worker and its card", rail.includes("m6") && rail.includes("tk-4b37dd"));
  check("an entry draws its roll-up", rail.includes("progress → 68"));
  check("an entry quotes what was said", rail.includes("land the seam first"));
  check("what just arrived is marked", rail.includes('data-fresh="entering"'));
  check("what did not is at rest", rail.includes('data-fresh="rest"'));
  check("a day divider opens the list", rail.includes('data-testid="stream-day"') && rail.includes("today"));
  check("the counter is the LOG's length", rail.includes("1,284"));
  check("a card can be followed from its id", rail.includes('data-testid="stream-follow"'));
  check("an entry opens the card popup", rail.includes('aria-label="open tk-4b37dd"'));
  check("what arrived above the reader is offered, never forced", rail.includes("↑ 3 new"));
  check("older is reachable", rail.includes('data-testid="stream-more"'));
  check("yesterday is named, not dated", dayLabel(now - 86400, now) === "yesterday");

  /* An empty rail says WHICH empty it is: nothing asked, nothing happened, or
     nothing matches — three different facts and never a bare "0". */
  const asked = (filter: "all" | "code", task: string | null, total: number | null): string =>
    renderToStaticMarkup(
      <Stream
        moments={[]}
        arrivals={new Map()}
        at={at}
        now={now}
        total={total}
        filter={filter}
        onFilter={() => {}}
        task={task}
        onTask={() => {}}
        onOpen={() => {}}
        more={false}
        loading={false}
        onMore={() => {}}
        waiting={0}
        onTop={() => {}}
        onList={() => {}}
        onScroll={() => {}}
        reduced={false}
      />,
    );
  check("no client is said, not drawn as an empty log", asked("all", null, null).includes("no client to ask with"));
  check("an empty log is said in its own words", asked("all", null, 0).includes("Nothing has happened on this board yet"));
  check("a filter with no rows blames the filter", asked("code", "tk-1", 12).includes("Widen the filter"));

  /* ── the Editor's third column ──────────────────────────────────────────── */

  const tab: OpenTab = { path: "src/app.py", file: e.file, refusal: null, flash: null, gone: false };
  const base: EditorViewProps = {
    trees: e.trees,
    refusal: null,
    loading: false,
    tree: e.listing.tree,
    onTree: () => {},
    onBack: () => {},
    named: h.named,
    listing: e.listing,
    live: true,
    query: "",
    onQuery: () => {},
    tabs: [tab],
    active: "src/app.py",
    onOpen: () => {},
    onSelect: () => {},
    onClose: () => {},
    diff: { on: false, patch: null, loading: false, refusal: null },
    onToggleDiff: () => {},
    now,
    open: workingFolders(e.listing.files),
    onToggle: () => {},
    onCollapseAll: () => {},
    palette: null,
    onPalette: () => {},
    onPick: () => {},
    feed: EMPTY_FEED,
    stream: false,
    onStream: () => {},
    onOpenCard: () => {},
  };
  const shut = renderToStaticMarkup(<EditorView {...base} />);
  const open = renderToStaticMarkup(<EditorView {...base} stream={true} />);

  check("the Editor opens with the rail shut", !shut.includes('data-testid="editor-stream"'));
  check("the switch is on the bar either way", shut.includes('data-testid="editor-stream-toggle"'));
  check("the switch says which way it is", shut.includes(">stream<") && open.includes("stream ✕"));
  check("open draws the third column", open.includes('data-testid="editor-stream"'));
  check("and the rail inside it", open.includes('data-testid="stream"'));
  /* The width comes out of the TREE, not out of the code: a file tree reads at
     200px and a code pane does not. */
  check("the rail is a third column, taken off the tree", columnsFor(true).startsWith("minmax(190px, 250px)"));
  check("shut, the two columns are untouched", columnsFor(false) === "minmax(220px, 300px) minmax(0, 1fr)");
}
