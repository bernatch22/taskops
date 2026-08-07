/* The dossier — Nova's DOSSIER block, over either page.
 *
 * It renders what `verbs/card.py` → `_context.py::dossier` actually returns, and
 * in the ORDER `mcp/dossier.py` renders it for an agent: everything that changes
 * what you do before you start (the reviewer's verdict, a file collision, the
 * previous worker's note, the epic) sits ABOVE the spec, then the spec, then what
 * it is accepted against, then the graph, the commits and the thread. A human and
 * an agent reading the same card should be reading the same document.
 *
 * ACCEPTANCE CRITERIA ARE ON SCREEN. They were in v1's payload from the first
 * day and no v1 screen ever drew them (`~/taskops/docs/teardown/server-and-ui.md`
 * §6, hack #1), so the half of the spec that says what "done" means was visible
 * only to agents. That is the hole this file closes and the reason `<Criteria>`
 * is not folded into the spec block.
 *
 * Read-only except the foot: `CommentBox` is the one write, and there is no
 * status control anywhere in here. */
import { ago, shortActor } from "../../format";
import { TONE_BG, TONE_FG, type Tone } from "../board/CardTile";
import { Markdown } from "../shared/Markdown";
import { Overlay } from "../shared/Overlay";
import { CommentBox } from "./CommentBox";
import { Thread } from "./Thread";
import type { CardBrief, CardPayload, CardState, TeamMember } from "../../types";

/** The derived state, coloured. Same five tones as the board tiles, from the same
 *  table — a card that reads "stalled" in danger on the kanban must not read in
 *  warn here. */
const STATE: Record<CardState, Tone> = {
  open: "neutral",
  ready: "neutral",
  doing: "ok",
  done: "ok",
  dropped: "neutral",
  blocked: "danger",
  stalled: "danger",
  review: "warn",
  reviewing: "accent",
  changes: "danger",
};

const PRIORITY: Record<number, Tone> = { 0: "danger", 1: "warn", 2: "accent", 3: "neutral" };

const pill: React.CSSProperties = { fontSize: "11px", padding: "3px 11px", borderRadius: "20px" };
const soft: React.CSSProperties = { borderRadius: "13px", background: "var(--pane-2)", padding: "14px 16px" };
const label: React.CSSProperties = { fontSize: "12px", color: "var(--text-3)", marginBottom: "9px" };

function Section({ title, children }: { title: string; children: React.ReactNode }): React.JSX.Element {
  return (
    <div>
      <div style={label}>{title}</div>
      {children}
    </div>
  );
}

function Briefs({ rows }: { rows: CardBrief[] }): React.JSX.Element {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "7px" }}>
      {rows.map((row) => (
        <div key={row.id} style={{ fontSize: "13.5px", color: "var(--text-2)" }}>
          <span className="mono" style={{ color: "var(--accent)", marginRight: "9px" }}>
            {row.id}
          </span>
          <span style={{ color: TONE_FG[STATE[row.status as CardState] ?? "neutral"], marginRight: "9px" }}>
            {row.status}
          </span>
          {row.title}
        </div>
      ))}
    </div>
  );
}

/** The criteria, numbered, as a checklist — the numbering is not decoration: a
 *  close note says "1, 2 and 4 are met", and a list without numbers cannot be
 *  answered that way. Nothing is ticked, because the board stores no per-criterion
 *  verdict and inventing one on screen would be the UI claiming a fact. */
function Criteria({ criteria }: { criteria: string[] }): React.JSX.Element {
  return (
    <div data-testid="criteria" style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
      {criteria.map((text, n) => (
        <div
          key={n}
          data-testid="criterion"
          style={{
            display: "grid",
            gridTemplateColumns: "26px 1fr",
            fontSize: "14px",
            color: "var(--text-2)",
            alignItems: "baseline",
          }}
        >
          <span className="mono" style={{ fontSize: "11px", color: "var(--faint)" }}>
            {n + 1}
          </span>
          <span style={{ lineHeight: 1.6 }}>{text}</span>
        </div>
      ))}
    </div>
  );
}

export interface DrawerProps {
  dossier: CardPayload | null;
  /** The id being opened — known before the payload arrives, so the drawer can
   *  already say WHICH card is loading rather than flashing an empty panel. */
  openId: string;
  team: TeamMember[];
  now: number;
  onClose: () => void;
  onComment: (text: string, mentions: string[]) => Promise<void>;
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
  const { dossier, openId, team, now, onClose, onComment } = props;
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
        {dossier && card ? <Body dossier={dossier} now={now} /> : null}
      </div>

      <CommentBox team={team} onSend={onComment} />
    </>
  );
}

/** The scrolling half, split out only to keep each file readable — the section
 *  order is the design and lives here, whole. */
function Body({ dossier, now }: { dossier: CardPayload; now: number }): React.JSX.Element {
  const { card } = dossier;
  const stood = dossier.standing;

  return (
    <>
      {stood && stood.verdict === "changes" ? (
        <div
          data-testid="verdict"
          style={{ padding: "14px 16px", borderRadius: "13px", background: "var(--danger-soft)" }}
        >
          <div style={{ fontSize: "12px", color: "var(--danger)", marginBottom: "6px", fontWeight: 500 }}>
            Changes requested · {shortActor(stood.reviewed_by)}
          </div>
          <div style={{ fontSize: "13.5px", lineHeight: 1.6 }}>{stood.note}</div>
        </div>
      ) : null}

      {dossier.collisions.map((other) => (
        <div
          key={other.id}
          data-testid="collision"
          style={{ padding: "14px 16px", borderRadius: "13px", background: "var(--danger-soft)" }}
        >
          <div style={{ fontSize: "12px", color: "var(--danger)", marginBottom: "6px", fontWeight: 500 }}>
            Collision
          </div>
          <div style={{ fontSize: "13.5px", lineHeight: 1.6 }}>
            <span className="mono">{other.id}</span> ({shortActor(other.holder)}
            {other.started ? "" : ", not started"}) also claims{" "}
            <span className="mono">{other.files.join(", ")}</span>
          </div>
        </div>
      ))}

      {dossier.resume ? (
        <Section title="Resume note · previous worker">
          <div style={{ ...soft, fontSize: "14.5px", color: "var(--text-2)", lineHeight: 1.65 }}>
            {dossier.resume}
          </div>
        </Section>
      ) : null}

      <div style={{ display: "grid", gridTemplateColumns: dossier.epic ? "1fr 1fr" : "1fr", gap: "12px" }}>
        {dossier.epic ? (
          <Section title="Epic">
            <div style={soft}>
              <div className="mono" style={{ fontSize: "11px", color: "var(--accent)", marginBottom: "5px" }}>
                {dossier.epic.id}
              </div>
              <div style={{ fontSize: "13.5px" }}>{dossier.epic.title}</div>
            </div>
          </Section>
        ) : null}
        <Section title="Worktree">
          <div className="mono" style={{ ...soft, fontSize: "11.5px" }}>
            <div style={{ color: "var(--accent)" }}>{dossier.branch}</div>
            <div style={{ color: "var(--text-2)", wordBreak: "break-all", marginTop: "3px" }}>
              {dossier.worktree || "—"}
            </div>
          </div>
        </Section>
      </div>

      <Section title="Spec">
        {card.spec ? (
          <Markdown text={card.spec} />
        ) : (
          <div style={{ fontSize: "14px", color: "var(--text-3)" }}>
            (no spec — the board says nothing about this one yet)
          </div>
        )}
      </Section>

      {card.criteria.length > 0 ? (
        <Section title={`Criteria · ${card.criteria.length}`}>
          <Criteria criteria={card.criteria} />
        </Section>
      ) : null}

      {dossier.blockers.length > 0 ? (
        <Section title="Waiting on">
          <Briefs rows={dossier.blockers} />
        </Section>
      ) : null}

      {dossier.blocks.length > 0 ? (
        <Section title={`Blocking · ${dossier.blocks.length}`}>
          <Briefs rows={dossier.blocks} />
        </Section>
      ) : null}

      {dossier.subtasks.length > 0 ? (
        <Section title="Subtasks">
          <Briefs rows={dossier.subtasks} />
        </Section>
      ) : null}

      {dossier.commits.length > 0 ? (
        <Section title={`Commits · ${dossier.commits.length}${dossier.merged_into ? ` · merged into ${dossier.merged_into}` : ""}`}>
          <div style={{ borderRadius: "13px", background: "var(--pane-2)", overflow: "hidden" }}>
            {dossier.commits.map((commit) => (
              <div
                key={commit.sha}
                data-testid="commit"
                style={{
                  display: "grid",
                  gridTemplateColumns: "88px minmax(0,1fr)",
                  gap: "14px",
                  alignItems: "center",
                  padding: "12px 16px",
                  borderBottom: "1px solid var(--hair)",
                }}
              >
                <span className="mono" style={{ fontSize: "11.5px", color: "var(--accent)" }}>
                  {commit.sha.slice(0, 8)}
                </span>
                <span style={{ fontSize: "13.5px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {commit.subject}
                </span>
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      <Section title={`Thread · ${dossier.history.length}`}>
        <Thread history={dossier.history} now={now} />
      </Section>
    </>
  );
}
