/* The shell: the chrome, the view state, and the page it renders.
 *
 * App is the SINGLE caller of useBoard — that is the whole reason this file holds
 * the tab state as well. Which view is on decides nothing about what is fetched
 * (the hook fetches the board, entire, on one clock), so a page that owned its
 * own fetch would only manage to paint a board half a second older than the rail
 * above it. Pages receive data; they never ask for it.
 *
 * Three pages, in TabNav's order: Monitor, the Board and Worktrees — the tab list
 * and the branch below it are two halves of one fact, and a tab with no branch
 * here silently falls through to the Board, which is a dead tab that still looks
 * alive. Monitor is Nova's first and central section
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

import { Drawer } from "./components/card/Drawer";
import { Header } from "./components/chrome/Header";
import { KpiRail } from "./components/chrome/KpiRail";
import { TABS, TabNav, type TabId } from "./components/chrome/TabNav";
import type { Client } from "./client";
import { Board } from "./pages/Board";
import { Monitor } from "./pages/Monitor";
import { Worktrees } from "./pages/Worktrees";
import { applyTheme, readTheme, type Theme } from "./theme/theme";
import { useBoard } from "./useBoard";

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

export function App({ client }: { client: Client }): React.JSX.Element {
  const [theme, setTheme] = useState<Theme>(readTheme);
  const [tab, setTab] = useState<TabId>("monitor");
  // The chapter in focus lives HERE, next to the tab, for the same reason: it is
  // view state that decides an ARGUMENT to the one fetch, never a second fetch.
  const [milestone, setMilestone] = useState("");
  const { board, card, live, error, loading, openCard, openId, comment } = useBoard(
    client,
    milestone,
  );

  // A chapter that closes stops being pickable, and a filter naming a chapter
  // nobody can see would narrow the page with no way back to it from the pill.
  // Falling back to "all chapters" is the honest state, not a stored correction.
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
          selected={milestone}
          onSelect={setMilestone}
          live={live}
          team={board?.team ?? []}
          theme={theme}
          onToggleTheme={flip}
        >
          <TabNav tabs={TABS} active={tab} onSelect={setTab} />
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
          tab === "monitor" ? (
            <Monitor board={board} openCard={openCard} now={Date.now() / 1000} />
          ) : tab === "worktrees" ? (
            <Worktrees groups={board.groups} onOpen={openCard} />
          ) : (
            <Board board={board} openCard={openCard} />
          )
        ) : null}
      </main>

      {openId ? (
        <Drawer
          dossier={card}
          openId={openId}
          team={board?.team ?? []}
          now={Date.now() / 1000}
          onClose={() => openCard(null)}
          onComment={comment}
        />
      ) : null}
    </div>
  );
}
