/* Nova's milestone pill, as the button it is drawn as: a chapter, its count, a
 * `▾`, and the chapters underneath it.
 *
 * TWO sections, and the split is the point: the open chapters, then — under a
 * labelled rule, muted, each tagged `landed` — the finished ones. They arrive in
 * ONE list distinguished by `status` (`types.ts::BoardPayload.milestones`) and
 * are drawn as two, because being able to reach a landed chapter (its goal, its
 * rules, its 22 closed cards) and mistaking one for work in flight are opposite
 * things. The pill says it too: focus a landed chapter and it reads "landed —
 * history, not in flight" where it otherwise counts open chapters.
 *
 * What it picks is an ARGUMENT, not state of its own: the id travels up to App,
 * joins `window`/`tz` in `useBoard`'s one `board` call, and comes back as a whole
 * page narrowed to that chapter — rail, panes and groups together. "All chapters"
 * sends `milestone=*` (`ALL_CHAPTERS`), and that is the fix of 2026-08-18: it used
 * to send NOTHING, which does not mean "all" — it means "server, resolve it", so a
 * board with a single open chapter came back narrowed to that chapter while the ✓
 * sat on "all chapters" the whole time, unclickable because clicking it changed
 * no argument.
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

/** What "all chapters" SENDS — `core/types.py::EVERYTHING`, the same string on
 *  both sides. It is an argument and not the absence of one because absence
 *  means "server, resolve it": with a single open chapter the server narrowed to
 *  it, and this option drew a ✓ beside a scope that was never in effect. `""`
 *  still exists here and still means absence — the page's opening state, before
 *  the reader has picked anything (`App.tsx::scopeOf`). */
export const ALL_CHAPTERS = "*";

export interface MilestonePickerProps {
  /** The chapter in scope as the SERVER resolved it, "" when it resolved none. */
  milestone: string;
  /** Every chapter this dashboard can reach — the open ones AND the recent
   *  landed ones, in one list, told apart by `status` (`types.ts`). The server
   *  returns them whole whatever the call filtered by. */
  milestones: Milestone[];
  /** How many chapters landed in total, behind the list's cap. `?? 0`. */
  landedTotal?: number | undefined;
  /** The scope IN EFFECT: a chapter id, `ALL_CHAPTERS` for the whole board.
   *  Never "" — App resolves its own empty opening state against what the
   *  server answered, so the ✓ marks the scope the page is actually drawn at. */
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

/** The one place this file decides what a chapter's status means, so the pill
 *  and the menu cannot drift: `open` is in flight, anything else in this list is
 *  history. Not `=== "landed"` — a status this UI has never heard of belongs
 *  with history rather than being drawn as live work. */
export function isOpen(m: Milestone): boolean {
  return m.status === "open";
}

export function MilestonePicker(props: MilestonePickerProps): React.JSX.Element {
  const { milestone, milestones, selected, onSelect, landedTotal } = props;
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement | null>(null);
  /* NOT `milestones.length`: the list carries landed chapters too since they
   * stopped being invisible, and this figure is about what is in flight. */
  const chapters = milestones.filter(isOpen).length;
  /* The chosen chapter is history — the pill has to say so, or a finished
   * chapter's empty panes read as a board where nothing is happening. */
  const history = milestones.some((m) => m.id === selected && !isOpen(m));
  /* Board-wide is a scope, not the absence of one, so the pill says so: with a
   * single open chapter it otherwise read "no open milestone" over a page
   * showing every chapter's cards. */
  const all = selected === ALL_CHAPTERS;

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
            background: history ? "var(--faint)" : "var(--accent)",
            boxShadow: history ? "none" : "0 0 0 3px var(--accent-soft)",
            flex: "none",
          }}
        />
        <div style={{ textAlign: "left", minWidth: 0 }}>
          <div style={{ fontSize: "13px", fontWeight: 500, letterSpacing: "-0.02em" }}>
            {all
              ? "all chapters"
              : milestone || (chapters > 1 ? `${chapters} chapters open` : "no open milestone")}
          </div>
          <div style={{ fontSize: "10.5px", color: "var(--text-3)" }} data-testid="pill-sub">
            {history
              ? "landed — history, not in flight"
              : `${chapters} open chapter${chapters === 1 ? "" : "s"}`}
          </div>
        </div>
        <span style={{ fontSize: "9px", color: "var(--faint)", marginLeft: "3px", flex: "none" }}>
          ▾
        </span>
      </button>

      {open ? (
        <Menu
          milestones={milestones}
          landedTotal={landedTotal}
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

/** One row of the menu. The same button for both sections — what changes is the
 *  weight it is drawn at and the tag, so the two lists cannot drift apart. */
function Entry({
  stone,
  selected,
  onSelect,
  landed = false,
}: {
  stone: Milestone;
  selected: string;
  onSelect: (id: string) => void;
  landed?: boolean;
}): React.JSX.Element {
  const on = selected === stone.id;
  return (
    <button
      style={{ ...entry(on), ...(landed ? { color: on ? "var(--text-2)" : "var(--text-3)" } : {}) }}
      role="option"
      aria-selected={on}
      data-milestone={stone.id}
      data-landed={landed ? "1" : undefined}
      onClick={() => onSelect(stone.id)}
    >
      <span style={{ width: "12px", flex: "none", color: "var(--accent)" }}>{on ? "✓" : ""}</span>
      <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>
        {stone.title}
      </span>
      {landed ? (
        <span
          style={{
            marginLeft: "auto",
            flex: "none",
            fontSize: "10px",
            padding: "2px 7px",
            borderRadius: "20px",
            background: "var(--pane-2)",
            color: "var(--text-3)",
          }}
        >
          landed
        </span>
      ) : null}
    </button>
  );
}

interface MenuProps {
  milestones: Milestone[];
  landedTotal?: number | undefined;
  selected: string;
  anchor: React.RefObject<HTMLDivElement | null>;
  onClose: () => void;
  onSelect: (id: string) => void;
}

/** Split out so the hooks below mount and unmount WITH the dropdown: the stack
 *  slot and the outside-click listener exist exactly while it is open, which is
 *  what makes "the top-most overlay" mean the dropdown and not the pill.
 *
 *  EXPORTED for the same reason `Dossier` is exported beside `Drawer`: the open
 *  menu is state behind a click, and no event handler fires under
 *  `renderToStaticMarkup`, so the smoke harness could not otherwise reach the
 *  one thing this card is about — that a landed chapter is offered, and offered
 *  as history. A seam, not an API: `MilestonePicker` is what the app renders. */
export function Menu({
  milestones,
  landedTotal,
  selected,
  anchor,
  onClose,
  onSelect,
}: MenuProps): React.JSX.Element {
  useOverlayStack(onClose);
  const live = milestones.filter(isOpen);
  const history = milestones.filter((m) => !isOpen(m));
  const total = landedTotal ?? history.length;

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
        style={entry(selected === ALL_CHAPTERS)}
        role="option"
        aria-selected={selected === ALL_CHAPTERS}
        data-milestone={ALL_CHAPTERS}
        onClick={() => onSelect(ALL_CHAPTERS)}
      >
        <span style={{ width: "12px", flex: "none", color: "var(--accent)" }}>
          {selected === ALL_CHAPTERS ? "✓" : ""}
        </span>
        <span>all chapters</span>
      </button>
      {live.map((m) => (
        <Entry key={m.id} stone={m} selected={selected} onSelect={onSelect} />
      ))}
      {/* Nothing open is not an error: the board simply has no chapter to focus. */}
      {live.length === 0 ? (
        <div style={{ padding: "8px 10px", fontSize: "12px", color: "var(--text-3)" }}>
          no open chapter
        </div>
      ) : null}
      {/* Landed chapters BELOW a labelled rule, never mixed in: they are
          reachable — that is this card — but a reader picking what to work on
          must never mistake finished for in flight. The heading, the muted
          type and the `landed` tag on every row are three separate signals
          because one of them is a colour, and a colour is not a distinction. */}
      {history.length > 0 ? (
        <div data-testid="milestone-landed">
          <div
            style={{
              padding: "9px 10px 5px",
              marginTop: "4px",
              borderTop: "1px solid var(--hair)",
              fontSize: "10.5px",
              color: "var(--text-3)",
            }}
          >
            {total > history.length
              ? `Landed — history · ${history.length} of ${total}`
              : "Landed — history"}
          </div>
          {history.map((m) => (
            <Entry key={m.id} stone={m} selected={selected} onSelect={onSelect} landed />
          ))}
        </div>
      ) : null}
    </div>
  );
}
