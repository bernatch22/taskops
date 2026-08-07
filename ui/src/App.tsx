/* The shell: the chrome, the view state, and the slots the pages plug into.
 *
 * App is the SINGLE caller of useBoard — that is the whole reason this file holds
 * the tab state as well. Which view is on decides nothing about what is fetched
 * (the hook fetches the board, entire, on one clock), so a page that owned its
 * own fetch would only manage to paint a board half a second older than the rail
 * above it. Pages receive data; they never ask for it.
 *
 * ── THE SLOTS ────────────────────────────────────────────────────────────────
 * Three sibling cards land the real pages where the placeholder panels are, and
 * a fourth the drawer. Each is handed the payload and the callbacks; none of them
 * imports client.ts:
 *
 *   tk-a7f52a  <AttentionPage board={board} onOpen={openCard} />
 *              the landing view: the nine groups of board.groups in GROUP_ORDER.
 *   tk-0d233a  <BoardPage board={board} onOpen={openCard} />
 *              the kanban: the same groups as columns.
 *   tk-38c876  <HoursPage report={…} />
 *              board.hours is null unless the call passed window=; this card owns
 *              asking for it — through the hook, not a client of its own.
 *   tk-e85ced  <CardDrawer card={card} onClose={() => openCard(null)}
 *                          onComment={comment} />
 *              the dossier for `openId`, over the whole shell. `card` is null
 *              while the dossier is in flight — that is the drawer's own spinner.
 *
 * `openCard(id)` and `openCard(null)` are the only way a page changes what is
 * open, and `comment` is the ONE write this dashboard has. */
import { useState } from "react";

import { Header } from "./components/chrome/Header";
import { KpiRail } from "./components/chrome/KpiRail";
import { TABS, TabNav, type TabId } from "./components/chrome/TabNav";
import type { Client } from "./client";
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
  const { board, live, error, loading, openCard, openId } = useBoard(client);

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
        ) : (
          <Slot tab={tab} openId={openId} onOpen={openCard} />
        )}
      </main>
    </div>
  );
}

/** The placeholder that stands where each page will. It keeps the seam honest:
 *  a tab click has to change what renders here even before a page exists. */
function Slot(props: {
  tab: TabId;
  openId: string | null;
  onOpen: (task: string | null) => void;
}): React.JSX.Element {
  const { tab, openId, onOpen } = props;
  return (
    <div style={panel} data-testid="panel" data-panel={tab}>
      <div style={{ fontSize: "13px", color: "var(--text-2)" }}>{tab}</div>
      <div className="mono" style={{ fontSize: "11px" }}>
        {openId ? `card ${openId} — drawer lands in tk-e85ced` : "page lands in a sibling card"}
      </div>
      {openId ? (
        <button
          onClick={() => onOpen(null)}
          style={{ all: "unset", cursor: "pointer", fontSize: "11px", color: "var(--accent-hi)" }}
        >
          close
        </button>
      ) : null}
    </div>
  );
}
