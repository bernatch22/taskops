/* The shell: the chrome, the view state, and the page it renders.
 *
 * App is the SINGLE caller of useBoard — that is the whole reason this file holds
 * the tab state as well. Which view is on decides nothing about what is fetched
 * (the hook fetches the board, entire, on one clock), so a page that owned its
 * own fetch would only manage to paint a board half a second older than the rail
 * above it. Pages receive data; they never ask for it.
 *
 * Five pages, in TabNav's order: Monitor, the Board, Actors, Worktrees and
 * Reports — the
 * tab list and the branch below it are two halves of one fact, and a tab with no
 * branch here USED to fall through to the Board, which is a dead tab that still
 * looks alive: it highlights, the view does not change, and nothing says why.
 * That is no longer expressible. `PAGES` below is a `Record<TabId, …>`, so a new
 * member of the union is a compile error in this file until its page exists —
 * the comment that warned about it is now the type. Monitor is Nova's first and
 * central section
 * and therefore the DEFAULT — including the Throughput panel that a short-lived
 * "Hours" tab wrongly promoted to a view of its own, which lives inside Monitor
 * where the design puts it.
 *
 * `<main>` carries NO padding, exactly as Nova's does not (`min-height: 0;
 * overflow: hidden`): each page owns its own `0 24px 26px`, because each page
 * also owns which axis it scrolls on — Monitor vertically, the Board
 * horizontally — and a padded scroll parent would double the gutter to 48px and
 * clip the sticky column. The error and loading blocks are not pages, so they
 * take the gutter from a wrapper of their own.
 *
 * `openCard(id)` and `openCard(null)` are the only way a page changes what is
 * open, and `comment` is the ONE write this dashboard has. The drawer is rendered
 * HERE, once, over whichever page is on: it belongs to the app's view state, not
 * to a page — the same card will open from Monitor and from the Board, and two
 * drawers would be two of everything below them (two escape owners, two comment
 * boxes, two fetches of the same dossier). */
import { useEffect, useState } from "react";

import { watching } from "./components/card/CommentBox";
import { Drawer } from "./components/card/Drawer";
import { Header } from "./components/chrome/Header";
import { KpiRail } from "./components/chrome/KpiRail";
import { TABS, TabNav, type TabId } from "./components/chrome/TabNav";
import type { Client } from "./client";
import type { ActivityPayload } from "./types";
import { Actors } from "./pages/Actors";
import { ChapterStory } from "./components/story/ChapterStory";
import { Board } from "./pages/Board";
import { Monitor } from "./pages/Monitor";
import { Reports } from "./pages/Reports";
import { Worktrees } from "./pages/Worktrees";
import { applyTheme, readTheme, type Theme } from "./theme/theme";
import { DEFAULT_HOURS_CHOICE, windowFor } from "./hoursWindow";
import type { HoursChoice } from "./hoursWindow";
import { THROUGHPUT_WINDOW } from "./components/monitor/panels";
import { ToastStack } from "./components/toasts/ToastStack";
import { useToasts } from "./components/toasts/useToasts";
import { useBoard } from "./useBoard";
import { useEvents } from "./useEvents";

const shell: React.CSSProperties = {
  minHeight: "100vh",
  display: "grid",
  gridTemplateRows: "auto 1fr",
};

const panel: React.CSSProperties = {
  borderRadius: "16px",
  background: "var(--pane)",
  border: "1px solid var(--hair)",
  padding: "40px 24px",
  display: "grid",
  gap: "8px",
  justifyItems: "center",
  color: "var(--text-3)",
  animation: "tk-fade 240ms ease",
};

/** Selecting a tab, as a decision rather than as two setters.
 *
 *  Selecting the tab you are already on RETURNS TO THE INDEX: that was the bug —
 *  `TabNav` set a tab that was already set, React re-rendered nothing, and the
 *  open tree survived a click the reader could not tell had registered. Clearing
 *  it on every tab change rather than only on the active one is the same rule
 *  said once: leaving Worktrees and coming back lands on the index too, which is
 *  what "the tab bar takes you to the tab" means.
 *
 *  Pure, and exported, for the reason `submit()` is (CLAUDE.md): no handler
 *  fires under `react-dom/server`, so a rule left inside the closure would have
 *  no test at all. `ui/smoke/sections/diff-page.tsx`.
 *
 *  `report` joins `tree` here and for the identical reason: the Reports view's
 *  second surface replaces its index, so the same click on the same pill has to
 *  bring the reader back to the list. One rule, one function, every full-width
 *  surface cleared by it — a second one clearing itself would be the first bug
 *  again, in a new view. */
export function onTab(next: TabId): { tab: TabId; tree: string | null; report: string | null } {
  return { tab: next, tree: null, report: null };
}

/** Which shape the Board tab draws — pure and exported for the reason `onTab`
 *  is: the decision lives inside App's render, where `react-dom/server` gives a
 *  section no way to reach it (useBoard's effects never fire under SSR, so the
 *  whole App renders its loading panel and nothing else). The rule it pins:
 *  `story` non-null — the chapter in focus is complete AND its `activity`
 *  answer has arrived — draws the chapter grid; null, including "complete but
 *  still in flight", draws the columns unchanged.
 *  `ui/smoke/sections/chapter-story-grid.tsx`. */
export function boardView(story: ActivityPayload | null): "story" | "columns" {
  return story ? "story" : "columns";
}

export function App({ client }: { client: Client }): React.JSX.Element {
  const [theme, setTheme] = useState<Theme>(readTheme);
  const [tab, setTab] = useState<TabId>("monitor");
  /* WHICH TREE IS OPEN — lifted out of `pages/Worktrees.tsx` and into the view
   * state, because the thing that has to clear it is the TAB BAR, which is up
   * here. Selecting "Worktrees" while a tree is open used to set a tab that was
   * already set: React re-rendered nothing, the page kept its own `useState`,
   * and the reader could not tell the click had registered. A `key` on the page
   * would remount it into the same state one render later and would still be a
   * component being reset from outside itself. The state moves to where the
   * event is. */
  const [tree, setTree] = useState<string | null>(null);
  // WHICH REPORT IS OPEN, up here for the same reason as `tree` — see `onTab`.
  // Unlike a tree it opens no card: a report belongs to a CHAPTER, not to a card,
  // so there is no dossier to fetch beside it.
  const [report, setReport] = useState<string | null>(null);
  // The chapter in focus lives HERE, next to the tab, for the same reason: it is
  // view state that decides an ARGUMENT to the one fetch, never a second fetch.
  const [milestone, setMilestone] = useState("");
  /* WHICH HOURS WINDOW, and why it is here beside the tab. The Actors page
   * anchors on a calendar month; Monitor's Throughput draws exactly
   * THROUGHPUT_DAYS bars into a viewBox cut into that many slots. One `board`
   * call carries one `window=`, so the page ON SCREEN is what decides it — and
   * Throughput's number is never taken away from it. This is still ONE fetcher
   * with one argument more (useBoard.ts), not a second fetch per tab. */
  const [hours, setHours] = useState<HoursChoice>(DEFAULT_HOURS_CHOICE);
  const { board, card, story, live, error, loading, openCard, openId, comment } = useBoard(
    client,
    milestone,
    tab === "actors" ? windowFor(hours) : THROUGHPUT_WINDOW,
  );

  /* THE LOG, read once. `useBoard` owns the board snapshot; this is the second
   * and only other read in the dashboard, and it lives HERE for the same reason
   * `useBoard` does — there are now two surfaces that need it (the Event stream
   * pane, and the comment toasts that derive their news from `feed.head`), and
   * two calls would be two clocks asking one verb. `board` is the signal: a new
   * object on every answer the one fetcher receives, so a change frame resets
   * the log to page one for free. The whole argument is in `useEvents.ts`. */
  const feed = useEvents(client, board);

  /* THE NEWS, from that same read. No second fetch, no socket and no clock of
   * its own beyond the one that retires a toast — the hook is handed the feed
   * above and derives everything else (`components/toasts/useToasts.ts`). It
   * lives here because both halves of the feature hang off it: the stack, drawn
   * once over whichever page is on, and the tiles that light up on the Board.
   * `pulse.actor` goes in so the reader's own comment does not echo back at
   * them as a notification. */
  const toasts = useToasts(feed, board?.groups, board?.pulse.actor);

  /* Opening a tree opens its CARD, through the one door the drawer uses. A
   * worktree has no identity apart from its card, so the diff page shows that
   * card's thread — and it must be the SAME dossier, arriving on the same
   * refetch clock, or the page and the drawer would disagree about one card. */
  function openTree(id: string | null): void {
    setTree(id);
    openCard(id);
  }

  function selectTab(next: TabId): void {
    const view = onTab(next);
    if (tree !== view.tree) openTree(view.tree);
    if (report !== view.report) setReport(view.report);
    setTab(view.tab);
  }

  // A filter naming a chapter nobody can see would narrow the page with no way
  // back to it from the pill, so the focus falls back to "all chapters" — the
  // honest state, not a stored correction.
  //
  // Note what this does NOT do any more: landing a chapter no longer drops it.
  // `board.milestones` carries the landed ones too, so a reader who focused a
  // chapter and watched it land keeps reading it. What still falls off is a
  // chapter that was dropped, or one aged past the list's cap — and for those
  // the fallback is the only thing that can be true.
  const chapters = board?.milestones;
  useEffect(() => {
    if (!chapters || !milestone) return;
    if (!chapters.some((m) => m.id === milestone)) setMilestone("");
  }, [chapters, milestone]);

  function flip(): void {
    const next: Theme = theme === "dark" ? "light" : "dark";
    applyTheme(next);
    setTheme(next);
  }

  return (
    <div style={shell}>
      <header style={{ padding: "0 24px" }}>
        <Header
          milestone={board?.pulse.milestone ?? ""}
          milestones={board?.milestones ?? []}
          landedTotal={board?.landed_total}
          selected={milestone}
          onSelect={setMilestone}
          live={live}
          forge={board?.forge}
          team={board?.team ?? []}
          theme={theme}
          onToggleTheme={flip}
        >
          <TabNav tabs={TABS} active={tab} onSelect={selectTab} />
        </Header>
        {board ? <KpiRail board={board} /> : null}
      </header>

      <main style={{ minHeight: 0, overflow: "hidden" }}>
        {/* The refusal is shown with the server's own words: a Refused message
            NAMES the call that fixes it, and paraphrasing it here would throw
            away the only instruction the reader gets. */}
        {error ? (
          <div style={{ padding: "0 24px 16px" }}>
            <div
              data-testid="error"
              style={{
                borderRadius: "13px",
                background: "var(--danger-soft)",
                border: "1px solid var(--hair)",
                padding: "14px 16px",
                color: "var(--danger)",
              }}
            >
              <span className="mono" style={{ fontSize: "11px", opacity: 0.8 }}>
                {error.code}
              </span>
              <div style={{ fontSize: "13px", color: "var(--text)" }}>{error.message}</div>
            </div>
          </div>
        ) : null}

        {loading && !board ? (
          <div style={{ padding: "0 24px 26px" }}>
            <div style={panel} data-testid="loading">
              reading the board…
            </div>
          </div>
        ) : board ? (
          /* EVERY tab, and the compiler counts them. A `Record<TabId, …>` is
             what makes "a tab with no page" unwritable rather than merely
             warned about: add a member to the union and this object is missing
             a key, in this file, before anything renders. */
          ({
            monitor: () => (
              <Monitor
                board={board}
                openCard={openCard}
                now={Date.now() / 1000}
                feed={feed}
                /* The SAME setter the header picker gets, not a second one: the
                   Chapter pane's `focus` action and the pill are one state. */
                onFocusChapter={setMilestone}
              />
            ),
            /* A COMPLETE chapter reads as a story, not as six columns of done
               tiles: `story` is non-null exactly when the chapter in focus is
               complete AND its `activity` answer has arrived (useBoard.ts).
               While it is still in flight — or for any open chapter — the
               columns render unchanged; there is no spinner state on purpose. */
            board: () =>
              boardView(story) === "story" && story ? (
                <ChapterStory story={story} openCard={openCard} />
              ) : (
                <Board board={board} openCard={openCard} recent={toasts.recent} />
              ),
            /* The fourth view. It is handed the same four slices Monitor's own
               panes read plus `board.hours` — the same snapshot Throughput
               draws from, because there is one fetcher (useBoard.ts). */
            actors: () => (
              <Actors
                team={board.team}
                doing={board.groups.doing}
                reviewing={board.groups.reviewing}
                stalled={board.groups.stalled}
                report={board.hours}
                choice={hours}
                onChoice={setHours}
                now={Date.now() / 1000}
                onOpen={openCard}
              />
            ),
            /* No base is passed down: `board.milestone` is the chapter IN FOCUS
               and is `null` under "All milestones", which made every tree ask
               the /git door for `compare("", tk-x)` and get nothing. Each row
               resolves its OWN chapter's branch out of `milestones`. */
            worktrees: () => (
              <Worktrees
                groups={board.groups}
                milestones={board.milestones}
                repo={board.repo}
                reader={client}
                openTree={tree}
                onOpenTree={openTree}
                dossier={card}
                team={board.team}
                onComment={comment}
                readOnly={watching(board.pulse)}
              />
            ),
            /* The fifth view. The LIST is a slice of the one board answer —
               `pulse.py::run` already scoped it to the chapter in focus, so
               there is nothing to filter here and nothing to fetch. The BYTES
               are not on the board and never will be, so the page is handed the
               same `client` the diff surface gets, and reads one report at a
               time from the reader's own clone. `?? []` / `?? 0` for a board one
               version behind, which sends neither key (types.ts). */
            reports: () => (
              <Reports
                reports={board.reports ?? []}
                total={board.reports_total ?? 0}
                chapter={board.milestone?.title ?? ""}
                reader={client}
                open={report}
                onOpen={setReport}
                now={Date.now() / 1000}
              />
            ),
          } satisfies Record<TabId, () => React.JSX.Element>)[tab]()
        ) : null}
      </main>

      {/* The drawer is NOT drawn over the diff page. Opening a tree opens its
          card — that is where the page's thread comes from — and a drawer on top
          of it would be the very bug this chapter exists to remove: the reader
          back in a 900px column about the card they are already reading at full
          width. */}
      {openId && !tree ? (
        <Drawer
          dossier={card}
          openId={openId}
          team={board?.team ?? []}
          now={Date.now() / 1000}
          onClose={() => openCard(null)}
          onComment={comment}
          readOnly={watching(board?.pulse)}
          repo={board?.repo}
          reader={client}
          /* The Worktree block sends the reader INTO this dashboard. Opening
             the tree already closes this drawer — the mount above is
             `openId && !tree` — so there is nothing to close by hand and no
             second piece of state to keep in step. */
          onOpenTree={(id) => {
            openTree(id);
            setTab("worktrees");
          }}
        />
      ) : null}

      {/* The stack sits OVER every page, once, for the same reason the drawer
          does: a comment lands on the board, not on the tab you happen to be
          reading, and a per-page stack would be five stacks with five clocks.
          Its `open` affordance is the very same `openCard` the tiles use — one
          door into the drawer, from anywhere. */}
      <ToastStack
        toasts={toasts.stack}
        onExpand={toasts.expand}
        onDismiss={toasts.dismiss}
        onOpen={openCard}
        reduced={toasts.reduced}
      />
    </div>
  );
}
