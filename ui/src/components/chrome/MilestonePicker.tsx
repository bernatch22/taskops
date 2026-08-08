/* Nova's milestone pill, as the button it is drawn as: a chapter, its count, a
 * `▾`, and the open chapters underneath it.
 *
 * What it picks is an ARGUMENT, not state of its own: the id travels up to App,
 * joins `window`/`tz` in `useBoard`'s one `board` call, and comes back as a whole
 * page narrowed to that chapter — rail, panes and groups together. "All chapters"
 * sends no `milestone=` at all, which is the behaviour the dashboard had before
 * this existed and must keep having.
 *
 * The CLOSED label keeps a distinction that cost a bug to find: `board.milestone`
 * is null both when NOTHING is open and when SEVERAL are (the server refuses to
 * guess), and only the count tells them apart. "no open milestone" over a board
 * with two chapters was the visible contradiction that exposed it, so the count —
 * not the null — decides what the pill says.
 *
 * Escape goes through `overlayStack`, the same pile the dossier drawer is on, so
 * a dropdown opened over the drawer closes the DROPDOWN. A popover also dies on a
 * click elsewhere, which no modal overlay needs and which is not Escape's job. */
import { useEffect, useRef, useState } from "react";

import type { Milestone } from "../../types";
import { useOverlayStack } from "../shared/Overlay";

export interface MilestonePickerProps {
  /** The chapter in scope as the SERVER resolved it, "" when it resolved none. */
  milestone: string;
  /** Every open chapter — the server returns them whole whatever the call filtered by. */
  milestones: Milestone[];
  /** The chosen id, "" for "all chapters". */
  selected: string;
  onSelect: (id: string) => void;
}

const pill: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
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

const menu: React.CSSProperties = {
  position: "absolute",
  top: "calc(100% + 6px)",
  left: "10px",
  zIndex: 50,
  minWidth: "230px",
  maxHeight: "320px",
  overflowY: "auto",
  padding: "6px",
  borderRadius: "13px",
  background: "var(--pane)",
  border: "1px solid var(--hair-2)",
  boxShadow: "0 22px 60px rgba(0,0,0,0.35)",
  display: "grid",
  gap: "2px",
  animation: "tk-fade 140ms ease-out",
};

function entry(active: boolean): React.CSSProperties {
  return {
    all: "unset",
    boxSizing: "border-box",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    gap: "9px",
    padding: "8px 10px",
    borderRadius: "10px",
    fontSize: "13px",
    letterSpacing: "-0.02em",
    color: active ? "var(--text)" : "var(--text-2)",
    background: active ? "var(--accent-soft)" : "transparent",
  };
}

export function MilestonePicker(props: MilestonePickerProps): React.JSX.Element {
  const { milestone, milestones, selected, onSelect } = props;
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement | null>(null);
  const chapters = milestones.length;

  return (
    <div ref={box} style={{ position: "relative", display: "flex" }}>
      <button
        style={pill}
        data-testid="milestone"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
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
            {milestone || (chapters > 1 ? `${chapters} chapters open` : "no open milestone")}
          </div>
          <div style={{ fontSize: "10.5px", color: "var(--text-3)" }}>
            {chapters} open chapter{chapters === 1 ? "" : "s"}
          </div>
        </div>
        <span style={{ fontSize: "9px", color: "var(--faint)", marginLeft: "3px", flex: "none" }}>
          ▾
        </span>
      </button>

      {open ? (
        <Menu
          milestones={milestones}
          selected={selected}
          anchor={box}
          onClose={() => setOpen(false)}
          onSelect={(id) => {
            setOpen(false);
            onSelect(id);
          }}
        />
      ) : null}
    </div>
  );
}

interface MenuProps {
  milestones: Milestone[];
  selected: string;
  anchor: React.RefObject<HTMLDivElement | null>;
  onClose: () => void;
  onSelect: (id: string) => void;
}

/** Split out so the hooks below mount and unmount WITH the dropdown: the stack
 *  slot and the outside-click listener exist exactly while it is open, which is
 *  what makes "the top-most overlay" mean the dropdown and not the pill. */
function Menu({ milestones, selected, anchor, onClose, onSelect }: MenuProps): React.JSX.Element {
  useOverlayStack(onClose);

  useEffect(() => {
    if (typeof document === "undefined") return;
    function away(event: MouseEvent): void {
      const at = event.target;
      if (at instanceof Node && anchor.current?.contains(at)) return;
      onClose();
    }
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [anchor, onClose]);

  return (
    <div style={menu} role="listbox" data-testid="milestone-menu">
      <button
        style={entry(selected === "")}
        role="option"
        aria-selected={selected === ""}
        data-milestone=""
        onClick={() => onSelect("")}
      >
        <span style={{ width: "12px", flex: "none", color: "var(--accent)" }}>
          {selected === "" ? "✓" : ""}
        </span>
        <span>all chapters</span>
      </button>
      {milestones.map((m) => (
        <button
          key={m.id}
          style={entry(selected === m.id)}
          role="option"
          aria-selected={selected === m.id}
          data-milestone={m.id}
          onClick={() => onSelect(m.id)}
        >
          <span style={{ width: "12px", flex: "none", color: "var(--accent)" }}>
            {selected === m.id ? "✓" : ""}
          </span>
          <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>
            {m.title}
          </span>
        </button>
      ))}
      {/* Nothing open is not an error: the board simply has no chapter to focus. */}
      {milestones.length === 0 ? (
        <div style={{ padding: "8px 10px", fontSize: "12px", color: "var(--text-3)" }}>
          no open chapter
        </div>
      ) : null}
    </div>
  );
}
