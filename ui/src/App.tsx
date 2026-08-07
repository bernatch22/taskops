/* The shell: the chrome, the view state, and the three pages it renders.
 *
 * App is the SINGLE caller of useBoard — that is the whole reason this file holds
 * the tab state as well. Which view is on decides nothing about what is fetched
 * (the hook fetches the board, entire, on one clock), so a page that owned its
 * own fetch would only manage to paint a board half a second older than the rail
 * above it. Pages receive data; they never ask for it.
 *
 * Hours is the one exception, and a deliberate one: `report` is not in the board
 * payload (pulse.py only carries it when the call passed window=), and the window
 * and timezone are that page's own state — so it reads through the `client` App
 * hands it. Nothing about the board's fetch is duplicated there.
 *
 * `openCard(id)` and `openCard(null)` are the only way a page changes what is
 * open, and `comment` is the ONE write this dashboard has. The drawer is rendered
 * HERE, once, over whichever page is on: it belongs to the app's view state, not
 * to a page — the same card opens from Attention and from the Board, and two
 * drawers would be two of everything below them (two escape owners, two comment
 * boxes, two fetches of the same dossier). */
import { useState } from "react";

import { Drawer } from "./components/card/Drawer";
import { Header } from "./components/chrome/Header";
import { KpiRail } from "./components/chrome/KpiRail";
import { TABS, TabNav, type TabId } from "./components/chrome/TabNav";
import type { Client } from "./client";
import { Attention } from "./pages/Attention";
import { Board } from "./pages/Board";
import { Hours } from "./pages/Hours";
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
  const [tab, setTab] = useState<TabId>("attention");
  const { board, card, live, error, loading, openCard, openId, comment } = useBoard(client);

  function flip(): void {
    const next: Theme = theme === "dark" ? "light" : "dark";
    applyTheme(next);
    setTheme(next);
  }

  const mentions = board?.groups.mentions.length ?? 0;
  const tabs = TABS.map((t) => (t.id === "attention" && mentions ? { ...t, badge: mentions } : t));

  return (
    <div style={shell}>
      <header style={{ padding: "0 24px" }}>
        <Header
          milestone={board?.pulse.milestone ?? ""}
          chapters={board?.milestones.length ?? 0}
          live={live}
          team={board?.team ?? []}
          theme={theme}
          onToggleTheme={flip}
        >
          <TabNav tabs={tabs} active={tab} onSelect={setTab} />
        </Header>
        {board ? <KpiRail board={board} /> : null}
      </header>

      <main style={{ minHeight: 0, padding: "0 24px 26px" }}>
        {/* The refusal is shown with the server's own words: a Refused message
            NAMES the call that fixes it, and paraphrasing it here would throw
            away the only instruction the reader gets. */}
        {error ? (
          <div
            data-testid="error"
            style={{
              borderRadius: "13px",
              background: "var(--danger-soft)",
              border: "1px solid var(--hair)",
              padding: "14px 16px",
              marginBottom: "16px",
              color: "var(--danger)",
            }}
          >
            <span className="mono" style={{ fontSize: "11px", opacity: 0.8 }}>
              {error.code}
            </span>
            <div style={{ fontSize: "13px", color: "var(--text)" }}>{error.message}</div>
          </div>
        ) : null}

        {loading && !board ? (
          <div style={panel} data-testid="loading">
            reading the board…
          </div>
        ) : tab === "hours" ? (
          <Hours client={client} />
        ) : board && tab === "board" ? (
          <Board board={board} openCard={openCard} />
        ) : board ? (
          <Attention board={board} openCard={openCard} />
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
