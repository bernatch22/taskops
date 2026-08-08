/* The dossier — Nova's DOSSIER block, over either page.
 *
 * It renders what `verbs/card.py` → `_context.py::dossier` actually returns, and
 * in the ORDER `mcp/dossier.py` renders it for an agent: everything that changes
 * what you do before you start (the reviewer's verdict, a file collision, the
 * previous worker's note, the epic) sits ABOVE the spec, then the spec, then what
 * it is accepted against, then the graph, the commits and the thread. A human and
 * an agent reading the same card should be reading the same document.
 *
 * Three files, one document. This one is the frame — the overlay, the identity
 * line and the header — `Sections.tsx` is everything that scrolls (and the
 * criteria v1 never drew), `CommentBox.tsx` is the foot. Split by what a reader
 * scans rather than by component kind, so each file is one part of the page.
 *
 * Read-only except the foot: `CommentBox` is the one write, and there is no
 * status control anywhere in here. */
import { ago, shortActor } from "../../format";
import { TONE_BG, TONE_FG } from "../board/CardTile";
import { Overlay } from "../shared/Overlay";
import { Body } from "./Sections";
import { CommentBox } from "./CommentBox";
import { PRIORITY, STATE, pill } from "./tokens";
import type { GitReader, Repo } from "../../links";
import type { CardPayload, TeamMember } from "../../types";

export interface DrawerProps {
  dossier: CardPayload | null;
  /** The id being opened — known before the payload arrives, so the drawer can
   *  already say WHICH card is loading rather than flashing an empty panel. */
  openId: string;
  team: TeamMember[];
  now: number;
  onClose: () => void;
  onComment: (text: string, mentions: string[]) => Promise<void>;
  /** Where the repo lives on the web — `BoardPayload.repo`, handed down from
   *  App because it is a fact about the BOARD and not about this card. Optional
   *  and nullable both, for the two reasons `links.tsx` sets out; absent, the
   *  dossier is character-for-character the document it was before. */
  repo?: Repo | null | undefined;
  /** The /git door — the client itself, narrowed to its one GET. Optional and
   *  nullable both: without it the diff panes fall through the cascade, which
   *  is a drawn state and not a missing feature (`links.tsx`). */
  reader?: GitReader | null | undefined;
}

/** The drawer: the dossier, inside the overlay that owns Escape.
 *
 *  Two components rather than one because `Overlay` is a PORTAL, and a portal has
 *  no markup of its own to assert on — under `react-dom/server` it renders
 *  nothing at all. `Dossier` is the whole document and renders anywhere, so the
 *  headless harness reads the same tree the browser draws. */
export function Drawer(props: DrawerProps): React.JSX.Element {
  const { dossier, openId, onClose } = props;
  const card = dossier?.card;
  return (
    <Overlay onClose={onClose} label={card ? `${card.id} — ${card.title}` : openId}>
      <Dossier {...props} />
    </Overlay>
  );
}

export function Dossier(props: DrawerProps): React.JSX.Element {
  const { dossier, openId, team, now, onClose, onComment, repo, reader } = props;
  const card = dossier?.card;
  const tone = dossier ? (STATE[dossier.state] ?? "neutral") : "neutral";
  const holder = dossier?.lease?.actor ?? "";

  return (
    <>
      <div
        style={{
          padding: "24px 28px 20px",
          display: "grid",
          gridTemplateColumns: "1fr auto",
          gap: "18px",
          alignItems: "start",
          borderBottom: "1px solid var(--hair)",
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "9px", marginBottom: "12px", flexWrap: "wrap" }}>
            <span className="mono" style={{ fontSize: "11.5px", color: "var(--text-3)" }}>
              {openId}
            </span>
            {dossier ? (
              <span
                data-testid="state"
                style={{ ...pill, color: TONE_FG[tone], background: TONE_BG[tone] }}
              >
                {dossier.state}
                {holder ? ` · ${shortActor(holder)}` : ""}
              </span>
            ) : null}
            {dossier?.branch ? (
              <span
                className="mono"
                style={{ ...pill, color: "var(--accent)", background: "var(--accent-soft)" }}
              >
                branch {dossier.branch}
              </span>
            ) : null}
          </div>
          <h2 style={{ margin: "0 0 12px", fontSize: "27px", fontWeight: 500, letterSpacing: "-0.04em" }}>
            {card?.title ?? "reading the card…"}
          </h2>
          {card ? (
            <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
              <span style={{ ...pill, color: TONE_FG[PRIORITY[card.priority] ?? "neutral"], background: "var(--pane-3)" }}>
                P{card.priority}
              </span>
              {card.labels.map((tag) => (
                <span key={tag} style={{ ...pill, color: "var(--text-2)", background: "var(--pane-3)" }}>
                  {tag}
                </span>
              ))}
              <span style={{ ...pill, color: "var(--text-3)", background: "var(--pane-3)" }}>
                review · {card.review ? "on" : "off"}
              </span>
              {dossier && dossier.seconds >= 60 ? (
                <span className="mono" style={{ ...pill, color: "var(--text-3)", background: "var(--pane-3)" }}>
                  {ago(dossier.seconds)} worked
                </span>
              ) : null}
            </div>
          ) : null}
        </div>
        <button
          type="button"
          data-testid="close"
          aria-label="Close"
          onClick={onClose}
          style={{
            all: "unset",
            boxSizing: "border-box",
            cursor: "pointer",
            width: "34px",
            height: "34px",
            display: "grid",
            placeItems: "center",
            borderRadius: "11px",
            color: "var(--text-3)",
            fontSize: "17px",
            background: "var(--pane-2)",
          }}
        >
          ×
        </button>
      </div>

      <div style={{ overflowY: "auto", padding: "22px 28px 26px", display: "flex", flexDirection: "column", gap: "22px" }}>
        {dossier && card ? <Body dossier={dossier} now={now} repo={repo} reader={reader} /> : null}
      </div>

      <CommentBox team={team} onSend={onComment} />
    </>
  );
}
