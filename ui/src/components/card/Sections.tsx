/* The scrolling half of the dossier: every section, in the order that IS the design.
 *
 * `mcp/dossier.py` renders a card for an agent in exactly this order — everything
 * that changes what you do before you start (the reviewer's verdict, a file
 * collision, the previous worker's note, the epic) ABOVE the spec, then what the
 * card is accepted against, then the graph, the commits and the thread. A human
 * and an agent reading the same card should be reading the same document, so the
 * order is copied rather than re-invented for a screen.
 *
 * ACCEPTANCE CRITERIA ARE ON SCREEN. They were in v1's payload from the first day
 * and no v1 screen ever drew them (`~/taskops/docs/teardown/server-and-ui.md` §6,
 * hack #1), so the half of the spec that says what "done" means was visible only
 * to agents. That is the hole `<Criteria>` closes, and the reason it is a section
 * of its own rather than a paragraph folded into the spec. */
import { shortActor } from "../../format";
import { Ext, Numstat, commitUrl, compareUrl, type GitReader, type Repo } from "../../links";
import { TONE_FG } from "../board/CardTile";
import { Markdown } from "../shared/Markdown";
import { CommitPatch, FilesChanged } from "./Patch";
import { Thread } from "./Thread";
import { STATE, label, soft } from "./tokens";
import type { CardBrief, CardPayload, CardState } from "../../types";

export function Section({ title, children }: { title: string; children: React.ReactNode }): React.JSX.Element {
  return (
    <div>
      <div style={label}>{title}</div>
      {children}
    </div>
  );
}

export function Briefs({ rows }: { rows: CardBrief[] }): React.JSX.Element {
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
export function Criteria({ criteria }: { criteria: string[] }): React.JSX.Element {
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
          {/* Inline, for the reason the chapter's rules are inline: the number
              in the first grid column IS the numbering, and the block renderer
              would move this cell off its baseline and renumber any criterion
              that opens with a digit. */}
          <span style={{ lineHeight: 1.6 }}>
            <Markdown text={text} inline />
          </span>
        </div>
      ))}
    </div>
  );
}

/** The sections themselves, in order. Nothing is rendered for a section the
 *  payload leaves empty — a card with no collisions must not draw a "Collisions"
 *  heading with nothing under it, because an empty heading reads as "checked, and
 *  fine" exactly like one that was never computed. */
export function Body({
  dossier,
  now,
  repo,
  reader,
}: {
  dossier: CardPayload;
  now: number;
  /** Where this repo lives on the web, or nothing — the whole GitHub switch
   *  (`links.tsx`). OPTIONAL so that a caller that has not been taught to pass
   *  it renders exactly the document this file rendered before. */
  repo?: Repo | null | undefined;
  /** The /git door, or nothing. OPTIONAL for the same reason and with the same
   *  consequence: with no reader the cascade falls to the forge link or the
   *  honest sentence, which is exactly what a host with no clone produces — so
   *  the headless harness, which has no wire at all, renders a real state and
   *  not a special case. */
  reader?: GitReader | null | undefined;
}): React.JSX.Element {
  const { card } = dossier;
  const stood = dossier.standing;
  /* The card AS A PULL REQUEST: base is the chapter's integration branch, head
   * is the card's own. Both are already on this payload (`_context.py::dossier`
   * sends `branch`, and `milestone` carries its own), so nothing is constructed
   * and nothing is guessed — the day a branch is named differently the link
   * follows it. `null` whenever any of the three facts is missing. */
  const pr = compareUrl(repo, dossier.branch, dossier.milestone?.branch ?? "");

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
          {/* A verdict is prose a verifier wrote — it quotes files, calls and
              test names constantly — so it reads through the one renderer, in
              blocks: nothing around it owns its shape. */}
          <div style={{ fontSize: "13.5px", lineHeight: 1.6 }}>
            <Markdown text={stood.note} />
          </div>
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
          {/* The previous worker's released note: prose, written by an agent
              handing over, and the one section a reader is asked to act on. It
              is markdown for the same reason the spec is. */}
          <div style={{ ...soft, fontSize: "14.5px", color: "var(--text-2)", lineHeight: 1.65 }}>
            <Markdown text={dossier.resume} />
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
            {/* No slug, no row: the line does not exist rather than existing
                dead, so the block is the same height it always was. */}
            {pr ? (
              <div style={{ marginTop: "7px" }}>
                <Ext
                  href={pr}
                  title={`${dossier.milestone?.branch ?? "the trunk"}...${dossier.branch}`}
                  style={{ color: "var(--accent)" }}
                >
                  <span data-testid="card-compare">compare ↗</span>
                </Ext>
              </div>
            ) : null}
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
            {dossier.commits.map((commit) => {
              const href = commitUrl(repo, commit.sha);
              const short = commit.sha.slice(0, 8);
              return (
                <div key={commit.sha} data-testid="commit" style={{ borderBottom: "1px solid var(--hair)" }}>
                <div
                  style={{
                    display: "grid",
                    // The third column is the numstat. `auto` and not a fixed
                    // width: with no numstat anywhere it collapses to nothing
                    // and the row is the two columns it always was.
                    gridTemplateColumns: "88px minmax(0,1fr) auto",
                    gap: "14px",
                    alignItems: "center",
                    padding: "12px 16px",
                  }}
                >
                  {/* The sha is the anchor when there is one and the same text
                      when there is not — never an anchor with no href. */}
                  <span className="mono" style={{ fontSize: "11.5px", color: "var(--accent)" }}>
                    {href ? (
                      <Ext href={href} title={commit.sha}>
                        <span data-testid="commit-link">{short}</span>
                      </Ext>
                    ) : (
                      short
                    )}
                  </span>
                  <span style={{ fontSize: "13.5px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {commit.subject}
                  </span>
                  <Numstat counts={commit.numstat ?? null} />
                </div>
                {/* Step ONE of the cascade is the numstat above, which is on the
                    payload and always there. This is step two, folded: the real
                    patch, from this host's own clone, only if somebody asks. */}
                <div style={{ padding: "0 16px 12px" }}>
                  <CommitPatch reader={reader} repo={repo} sha={commit.sha} />
                </div>
                </div>
              );
            })}
          </div>
        </Section>
      ) : null}

      {/* The card AS A PULL REQUEST, read from the clone instead of the forge:
          the same two branches the `compare ↗` link above is built from. No
          branch on either side, no section — there is no range to ask about. */}
      {dossier.commits.length > 0 && dossier.branch && dossier.milestone?.branch ? (
        <Section title="Files changed">
          <FilesChanged
            reader={reader}
            repo={repo}
            base={dossier.milestone.branch}
            head={dossier.branch}
          />
        </Section>
      ) : null}

      <Section title={`Thread · ${dossier.history.length}`}>
        <Thread history={dossier.history} now={now} repo={repo} reader={reader} />
      </Section>
    </>
  );
}
