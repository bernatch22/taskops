/* Nova's header: who we are, which chapter is in scope, whether the page is
 * still connected, who else is here, and the theme switch.
 *
 * Pure presentation — everything arrives as a prop and nothing here fetches. The
 * milestone pill is a DIV and not Nova's button: switching milestone is not a
 * thing this read-only dashboard can do, and a button that does nothing is worse
 * than no button.
 *
 * The live dot is the one piece of state the payload cannot carry: it is the feed
 * socket's own health, so it comes from useBoard's `live`, green when connected
 * and red when the page may be stale. */
import type { TeamMember } from "../../types";
import type { Theme } from "../../theme/theme";
import { AvatarStack } from "./AvatarStack";

export interface HeaderProps {
  /** The milestone in scope, "" when none is open. */
  milestone: string;
  /** How many milestones are open — `board.milestones.length`. */
  chapters: number;
  /** The feed socket is connected. */
  live: boolean;
  team: TeamMember[];
  theme: Theme;
  onToggleTheme: () => void;
  /** The centre column — TabNav. */
  children?: React.ReactNode;
}

const bar: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "auto minmax(0, 1fr) auto",
  alignItems: "center",
  gap: "20px",
  minHeight: "68px",
  padding: "10px 0",
};

const mark: React.CSSProperties = {
  width: "30px",
  height: "30px",
  borderRadius: "9px",
  background: "linear-gradient(145deg, var(--accent) 0%, var(--accent-hi) 100%)",
  display: "grid",
  placeItems: "center",
  boxShadow: "0 2px 10px var(--accent-soft)",
};

const pill: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "11px",
  padding: "8px 13px 8px 11px",
  borderRadius: "11px",
  background: "var(--pane)",
  border: "1px solid var(--hair)",
  marginLeft: "10px",
  whiteSpace: "nowrap",
  flex: "none",
};

const toggle: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  width: "34px",
  height: "34px",
  flex: "none",
  display: "grid",
  placeItems: "center",
  borderRadius: "11px",
  background: "var(--pane)",
  border: "1px solid var(--hair)",
  fontSize: "13px",
  color: "var(--text-2)",
};

export function Header(props: HeaderProps): React.JSX.Element {
  const { milestone, chapters, live, team, theme, onToggleTheme, children } = props;
  const dot = live ? "var(--ok)" : "var(--danger)";
  const dotSoft = live ? "var(--ok-soft)" : "var(--danger-soft)";

  return (
    <div style={bar}>
      <div style={{ display: "flex", alignItems: "center", gap: "14px", minWidth: 0 }}>
        <div style={mark}>
          <div
            style={{
              width: "11px",
              height: "11px",
              borderRadius: "3px",
              border: "2px solid rgba(255,255,255,0.92)",
            }}
          />
        </div>
        <div>
          <div style={{ fontSize: "15px", fontWeight: 500, letterSpacing: "-0.03em" }}>taskops</div>
          <div className="mono" style={{ fontSize: "10px", color: "var(--text-3)" }}>
            nova
          </div>
        </div>

        <div style={pill} data-testid="milestone">
          <span
            style={{
              width: "7px",
              height: "7px",
              borderRadius: "50%",
              background: "var(--accent)",
              boxShadow: "0 0 0 3px var(--accent-soft)",
              flex: "none",
            }}
          />
          <div style={{ textAlign: "left", minWidth: 0 }}>
            <div style={{ fontSize: "13px", fontWeight: 500, letterSpacing: "-0.02em" }}>
              {milestone || "no open milestone"}
            </div>
            <div style={{ fontSize: "10.5px", color: "var(--text-3)" }}>
              {chapters} open chapter{chapters === 1 ? "" : "s"}
            </div>
          </div>
        </div>
      </div>

      {/* The centre column is TabNav's, handed in as children: the header owns the
          three-column geometry, the tab bar owns what a tab looks like. */}
      <div style={{ justifySelf: "center", maxWidth: "100%", minWidth: 0 }}>{children}</div>

      <div style={{ display: "flex", alignItems: "center", gap: "12px", flex: "none" }}>
        <div
          data-testid="live"
          data-live={live ? "yes" : "no"}
          title={live ? "feed connected" : "feed down — this page may be stale"}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            padding: "7px 13px",
            borderRadius: "11px",
            background: dotSoft,
            flex: "none",
          }}
        >
          <span
            style={{
              width: "6px",
              height: "6px",
              borderRadius: "50%",
              background: dot,
              animation: live ? "tk-pulse 2.2s infinite" : "none",
            }}
          />
          <span className="mono" style={{ fontSize: "11.5px", color: dot }}>
            {live ? "live" : "offline"}
          </span>
        </div>
        <AvatarStack team={team} />
        <button
          style={toggle}
          onClick={onToggleTheme}
          data-testid="theme"
          title={`theme: ${theme}`}
          aria-label="toggle theme"
        >
          {theme === "dark" ? "☾" : "☀"}
        </button>
      </div>
    </div>
  );
}
