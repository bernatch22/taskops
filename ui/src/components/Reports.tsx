/* The reports, ON SCREEN.
 *
 * A daily report is the one artefact taskops produces for a HUMAN to read: it is long, it is
 * prose, and it has been printed as ASCII into a terminal since the day it was written — which is
 * the worst possible surface for it. Nobody scrolls a terminal to read yesterday.
 *
 * Two panes. Left: which reports exist, newest first. Right: the one you picked, rendered — that
 * is the whole point of the view, so the narration gets its own panel above the facts even though
 * the file keeps it last (the file puts facts first so the prose is read as a reading of them; on
 * screen the prose is what you came for, and the facts are one scroll away). */

import { useCallback, useEffect, useState } from "react";
import { api, ApiFailure } from "../api";
import type { ReportEntry, ReportFile } from "../contracts";
import { Markdown } from "./Markdown";
import { split } from "../markdown";

export function Reports({ readonly }: { readonly: boolean }): JSX.Element {
  const [list, setList] = useState<ReportEntry[] | null>(null);
  const [picked, setPicked] = useState("");
  const [file, setFile] = useState<ReportFile | null>(null);
  const [failed, setFailed] = useState("");
  const [busy, setBusy] = useState(false);

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
    let live = true;
    setFile(null);
    api.report(picked)
      .then((found) => { if (live) { setFile(found); setFailed(""); } })
      .catch((error: unknown) => { if (live) setFailed(message(error)); });
    return () => { live = false; };
  }, [picked]);

  const narrate = async (force: boolean) => {
    setBusy(true);
    setFailed("");
    try {
      setFile(await api.digest(picked, force));
      await reload();
    } catch (error: unknown) {
      /* Verbatim. `claude` not installed, or not logged in, is something the reader can fix in a
       * minute — and only if the message reaches the screen instead of becoming "failed". */
      setFailed(message(error));
    } finally {
      setBusy(false);
    }
  };

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
                  {!entry.exists ? <span>not written yet</span> : <span>{size(entry.bytes)}</span>}
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
                        : "runs `claude` over the dossier; takes about half a minute"}
                      onClick={() => void narrate(!parts.pending)}>
                {busy ? "Narrating…" : parts.pending ? "Generate" : "Regenerate"}
              </button>
            </header>

            {busy ? (
              <p className="dim narrating">
                <span className="spinner" /> Claude is reading the day. This takes about
                thirty seconds — the page stays usable.
              </p>
            ) : null}

            <div className={`narration${parts.pending ? " pending" : ""}`}>
              <h3>Narration</h3>
              {parts.pending
                ? <p className="dim">Nobody has written this one up yet.</p>
                : <Markdown source={parts.narration} />}
            </div>

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
