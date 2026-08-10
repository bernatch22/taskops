/* Nova's header: who we are, what opens this board, which chapter is in scope,
 * whether the page is still connected, who else is here, and the theme switch.
 *
 * Pure presentation — everything arrives as a prop and nothing here fetches. The
 * milestone pill IS Nova's button (a `▾` and all), and it was a dead `div` until
 * this card: "this dashboard cannot switch milestone, and a dead button is worse
 * than none" stopped being true the moment `board` learned `milestone=`. With
 * several chapters open the server refuses to guess between them, so choosing one
 * from here is the ONLY way to see a chapter at all. The choice is not stored:
 * it is an ARGUMENT that App holds beside the tab and hands to the one fetcher.
 *
 * The live dot is the one piece of state the payload cannot carry: it is the feed
 * socket's own health, so it comes from useBoard's `live`, green when connected
 * and red when the page may be stale. */
import type { BoardPayload, Milestone, TeamMember } from "../../types";
import type { Theme } from "../../theme/theme";
import { AvatarStack } from "./AvatarStack";
import { MilestonePicker } from "./MilestonePicker";

export interface HeaderProps {
  /** The milestone in scope, "" when none is open. */
  milestone: string;
  /** Every chapter the board offers — open AND recently landed, in one list
   *  (`types.ts::BoardPayload.milestones`), which the server returns whole
   *  whatever the call filtered by, so the menu never shrinks to its own choice. */
  milestones: Milestone[];
  /** How many chapters landed in total, behind the list's cap. */
  landedTotal?: number | undefined;
  /** The chosen chapter's id, "" for "all chapters" (no `milestone=` is sent). */
  selected: string;
  /** Choose a chapter, or "" for all of them. */
  onSelect: (id: string) => void;
  /** The feed socket is connected. */
  live: boolean;
  /** What opens this board, when anything does — `BoardPayload.forge`, handed
   *  down whole rather than pre-formatted so the sentence is written once, here,
   *  beside the identity it belongs to. `undefined` on an invite-only board (and
   *  on a board one version behind, which says the same thing) and then NOTHING
   *  is drawn: an empty line under `nova` would read as a board that lost its
   *  forge, not as one that never declared one. */
  forge?: BoardPayload["forge"];
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
  const { milestone, milestones, landedTotal, selected, onSelect, live, team, theme } = props;
  const { onToggleTheme, children, forge } = props;
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
          {/* WHO CAN GET IN, under who we are — the one line that used to be
              invisible to everybody but the owner who declared it and the
              stranger the door refused. Drawn only when the board declared a
              forge (`types.ts::BoardPayload.forge`).

              Text and not an anchor on purpose: `links.tsx` owns every forge
              URL this dashboard draws and keys them off `BoardPayload.repo`,
              which is a DIFFERENT fact (where the code lives, not what opens
              the board) and can name a different repo. A second, hand-built
              base here would be that module's job spelled twice. The `title`
              carries the command instead, which is what a reader who wants in
              actually needs. */}
          {forge ? (
            <div
              className="mono"
              data-testid="board-forge"
              title={`${forge.need} on this repo opens this board — taskops join <board> --github`}
              style={{ fontSize: "10px", color: "var(--text-3)", marginTop: "2px" }}
            >
              {forge.host}/{forge.repo} · {forge.need}
            </div>
          ) : null}
        </div>

        <MilestonePicker
          milestone={milestone}
          milestones={milestones}
          landedTotal={landedTotal}
          selected={selected}
          onSelect={onSelect}
        />
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
