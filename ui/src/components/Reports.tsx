/* The reports, ON SCREEN.
 *
 * A daily report is the one artefact taskops produces for a HUMAN to read: it is long, it is
 * prose, and it has been printed as ASCII into a terminal since the day it was written — which is
 * the worst possible surface for it. Nobody scrolls a terminal to read yesterday.
 *
 * Two panes. Left: which reports exist, newest first. Right: the one you picked, rendered — that
 * is the whole point of the view, so the narration gets its own panel above the facts even though
 * the file keeps it last (the file puts facts first so the prose is read as a reading of them; on
 * screen the prose is what you came for, and the facts are one scroll away).
 *
 * Generate does NOT wait. The POST answers "narrating" in a few milliseconds and the prose arrives
 * on the live socket, so this panel renders it AS IT IS WRITTEN — which is the whole difference
 * between "no hace nada" and watching the day get read. The frames come in through `narration`,
 * folded by `useStudio` off the one socket the app already holds; this component never opens a
 * stream of its own. */

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiFailure } from "../api";
import type { ReportEntry, ReportFile } from "../contracts";
import type { Narration } from "../narration";
import { Markdown } from "./Markdown";
import { split } from "../markdown";

export function Reports({ readonly, narration }:
                        { readonly: boolean; narration: Narration | null }): JSX.Element {
  const [list, setList] = useState<ReportEntry[] | null>(null);
  const [picked, setPicked] = useState("");
  const [file, setFile] = useState<ReportFile | null>(null);
  const [failed, setFailed] = useState("");
  /* The gap between the click and the first frame. It is milliseconds, but without it the button
   * would sit there saying "Generate" until the model produced its first token — which on a big
   * dossier is the better part of a minute, and is exactly the silence this card is about. */
  const [starting, setStarting] = useState(false);

  /* The narration on screen is the one for the report being LOOKED AT. Another report's frames
   * are still folded (a second narration can be running), they just do not render here. */
  const live = narration && narration.label === picked ? narration : null;
  const busy = live ? live.state === "narrating" : starting;

  const reload = useCallback(async () => {
    const found = await api.reports();
    setList(found);
    /* The newest report is what somebody opening this view wants; picking nothing would make the
     * first act of every visit a click on the obvious row. */
    setPicked((current) => current || found[0]?.label || "");
  }, []);

  useEffect(() => {
    reload().catch((error: unknown) => setFailed(message(error)));
  }, [reload]);

  useEffect(() => {
    if (!picked) return;
    let current = true;
    setFile(null);
    setStarting(false);
    api.report(picked)
      .then((found) => { if (current) { setFile(found); setFailed(""); } })
      .catch((error: unknown) => { if (current) setFailed(message(error)); });
    return () => { current = false; };
  }, [picked]);

  const narrate = async (force: boolean) => {
    setStarting(true);
    setFailed("");
    try {
      /* Returns as soon as the work has STARTED. Everything after this arrives on the socket. */
      await api.digest(picked, force);
    } catch (error: unknown) {
      /* Verbatim. `claude` not installed, or not logged in, is something the reader can fix in a
       * minute — and only if the message reaches the screen instead of becoming "failed". A 409
       * lands here too: one is already running, and the message says to watch it. */
      setFailed(message(error));
      setStarting(false);
    }
  };

  /* The narration ENDED. Reread the file — the socket carried the prose, but the file is the
   * durable copy and the one the stale badges and the index are computed from. A ref keyed by
   * label+state is what stops this firing again on every re-render while `done` is still on
   * screen. */
  const handled = useRef("");
  useEffect(() => {
    if (!live || live.state === "narrating") return;
    const key = `${live.label}:${live.state}`;
    if (handled.current === key) return;
    handled.current = key;
    setStarting(false);
    if (live.state === "failed") { setFailed(live.error); return; }
    api.report(live.label).then(setFile).catch(() => {});
    void reload();
  }, [live, reload]);

  /* Follow the prose as it grows, the way a terminal does. Only while it is being WRITTEN: once
   * it is finished the reader owns the scroll position, and yanking it to the bottom while they
   * read the top would be the view fighting them. */
  const tail = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (live?.state === "narrating") tail.current?.scrollIntoView({ block: "end" });
  }, [live?.text, live?.state]);

  const parts = file ? split(file.dossier_md) : null;

  return (
    <div className="reports">
      <section className="report-list">
        <h3>Reports <span className="tally">{list?.length ?? 0}</span></h3>
        {!list ? <p className="dim">Reading the directory…</p> : null}
        <ul>
          {(list ?? []).map((entry) => (
            <li key={entry.label} className={`report-row${entry.label === picked ? " on" : ""}`}>
              <button onClick={() => setPicked(entry.label)}>
                <div className="report-row-top">
                  <code>{entry.label}</code>
                  {entry.has_narration ? <span className="narr" title="narrated">✎</span> : null}
                </div>
                <div className="report-row-meta dim">
                  {/* A report being narrated says so in the LIST, not only in the panel: the
                    * person may have clicked away to another row while it runs, and a job with
                    * no visible trace is the thing this whole card exists to remove. */}
                  {narration?.label === entry.label && narration.state === "narrating"
                    ? <span className="running">narrating…</span>
                    : !entry.exists ? <span>not written yet</span> : <span>{size(entry.bytes)}</span>}
                  {/* Stale is the badge that changes what a person DOES: citing a report that was
                    * written before half the day happened is the failure this whole fingerprint
                    * exists to prevent. */}
                  {entry.stale ? (
                    <span className="stale" title={`${entry.missing_events} events since`}>
                      stale +{entry.missing_events}
                    </span>
                  ) : null}
                </div>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="report-body">
        {failed ? <p className="failed">{failed}</p> : null}
        {!file && picked && !failed ? <p className="dim loading">Reading {picked}…</p> : null}

        {file && parts ? (
          <>
            <header className="report-head">
              <h2>{picked}</h2>
              <code className="dim report-path">{file.path}</code>
              <button className="primary" disabled={readonly || busy}
                      title={readonly
                        ? "this board is read-only — start it without --readonly"
                        : "runs `claude` over the dossier; it writes into the panel as it goes"}
                      onClick={() => void narrate(!parts.pending)}>
                {busy ? "Narrating…" : parts.pending ? "Generate" : "Regenerate"}
              </button>
            </header>

            {busy ? (
              <p className="dim narrating">
                <span className="spinner" />
                {live?.pass
                  ? ` Claude is on reading ${live.pass}. `
                  : " Claude is reading the day. "}
                It appears below as it is written, and it is being saved to the file at the
                same time — closing this page does not stop it.
              </p>
            ) : null}

            {/* WHILE it is being written, the socket is the source; afterwards, the file is.
              * Never both at once: the same prose in two panels reads as a rendering bug, and
              * the file is refetched the moment the last frame lands anyway. */}
            {live && live.text && (live.state === "narrating" || parts.pending) ? (
              <div className={`narration${live.state === "narrating" ? " streaming" : ""}`}>
                <h3>Narration {live.state === "narrating" ? "— being written" : ""}</h3>
                <Markdown source={live.text} />
                <div ref={tail} />
              </div>
            ) : (
              <div className={`narration${parts.pending ? " pending" : ""}`}>
                <h3>Narration</h3>
                {parts.pending
                  ? <p className="dim">Nobody has written this one up yet.</p>
                  : <Markdown source={parts.narration} />}
              </div>
            )}

            <div className="dossier">
              <Markdown source={parts.dossier} />
            </div>
          </>
        ) : null}
      </section>
    </div>
  );
}

function message(error: unknown): string {
  return error instanceof ApiFailure ? error.message : String(error);
}

function size(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${Math.round(bytes / 1024)} kB`;
}
