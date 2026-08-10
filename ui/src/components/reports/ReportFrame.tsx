/* THE SANDBOX. One file, one decision: where a report's own bytes are allowed
 * to run, and it is never this origin.
 *
 * ── The boundary, stated once ──────────────────────────────────────────────
 *
 * A report is prose somebody's agent wrote, committed, and registered. The
 * dashboard fetches it from the reader's own clone through `GET
 * <board>/git/file/<rev>?path=…` and draws it. That makes it UNTRUSTED INPUT
 * with a `<script>` tag in it — the panorama reports this chapter exists to
 * render are self-contained HTML pages, charts and all — and this origin is the
 * one holding the board's token (`client.ts::tokenKey` → `localStorage`). So the
 * milestone's second rule is a security boundary, not a preference:
 *
 *     report HTML must never run in the dashboard's origin.
 *
 * The server already refuses to be the weak end of this: `http/gitdoor.py::_file`
 * sends `content_type` as a FIELD inside a JSON envelope and never as a response
 * header, so no path and no file extension can make THIS origin serve
 * `text/html`. What is left is entirely the reader's job, and it is done here.
 *
 * ── Why `srcdoc` and not `src` ─────────────────────────────────────────────
 *
 * There is no URL to point a frame at. The door answers JSON, by design (above),
 * so the bytes arrive as a string and go into `srcdoc`. That is the better half
 * of the bargain anyway: a `src` on this origin would be same-origin by
 * definition, and `srcdoc` in a frame with no `allow-same-origin` is parsed into
 * an OPAQUE origin — a origin equal to no other, including its parent's.
 *
 * ── The sandbox, token by token ────────────────────────────────────────────
 *
 * `sandbox=""` turns everything off and each token gives one thing back. This
 * frame is given exactly one:
 *
 *     allow-scripts        YES — see below
 *     allow-same-origin    NEVER, and the two together least of all
 *     allow-forms · allow-popups · allow-top-navigation ·
 *     allow-modals · allow-downloads · allow-pointer-lock    all withheld
 *
 * **`allow-scripts` + `allow-same-origin` is not two permissions, it is the
 * absence of the sandbox.** With both, the frame's document is same-origin with
 * this page: `parent.localStorage.getItem("taskops:…")` returns the token,
 * `parent.document` is readable and writable, and the frame can even remove its
 * own `sandbox` attribute from the parent's DOM and reload itself unsandboxed.
 * Nothing about that pairing is degraded — it is the unsandboxed case with extra
 * steps. It is why this attribute is a CONSTANT with one value and not a prop:
 * a caller cannot ask for a laxer frame, because there is no argument to pass.
 *
 * **Scripts DO run, and that is deliberate.** The argument for withholding
 * `allow-scripts` too is real — it is the strictest thing available — and it was
 * weighed and rejected: the reports this chapter is for are single-file HTML
 * pages that carry their own inline behaviour (folds, charts, a filter over a
 * table), and rendering them dead would quietly deliver a broken document while
 * looking like it worked. The security question is not "does script run" but
 * "what can that script reach", and with an opaque origin the answer is: its own
 * document. It cannot read `parent` (cross-origin), it cannot touch
 * `localStorage` or `document.cookie` (an opaque origin has no storage — the
 * access throws), it cannot submit a form, open a window, navigate the top
 * frame, or start a download. `fetch` inside it is same-origin-less: any request
 * it makes carries no credential of this origin, and the door it would want
 * requires the `Authorization` header this page never gave it.
 *
 * The residual risk is honestly stated rather than papered over: a script in
 * there can still consume CPU, and it can still make cross-origin network noise
 * to a host it names. Neither reaches the token, which is the boundary this file
 * owns. A page-level CSP would narrow the second one and belongs to whoever
 * serves the dashboard, not to an attribute on a frame.
 *
 * ── Why a text report is NOT drawn in a frame ──────────────────────────────
 *
 * `srcdoc` is parsed as HTML whatever it contains, so putting a `.md` report in
 * one would both execute its markup and collapse its whitespace — a rendering
 * bug and a pointless one. `text/plain` (which is every type this door does not
 * know, `gitdoor.py::_file`) goes into a `<pre>` as a React TEXT NODE: React
 * escapes it, there is no `dangerouslySetInnerHTML` anywhere in this file or
 * this dashboard, and a `<script>` inside a text report is drawn as the eight
 * characters it is.
 */
import type { GitFile } from "../../types";

/** The sandbox this dashboard gives a report, and the only one it can give.
 *
 *  Exported so the smoke section pins the STRING, not a rendering of it: the
 *  claim being tested is "`allow-same-origin` never appears beside
 *  `allow-scripts`", and that is a claim about this value. */
export const SANDBOX = "allow-scripts";

/** The one pairing that would defeat it, spelled out so a test can look for it. */
export const FORBIDDEN = "allow-same-origin";

const frame: React.CSSProperties = {
  width: "100%",
  /* The frame cannot tell us how tall it is: it is cross-origin by construction,
   * so `contentDocument` is unreachable, and the postMessage channel that would
   * ask it is a channel we deliberately do not open to untrusted script. So it
   * gets a viewport-sized box and scrolls ITSELF — which is also how a reader
   * expects a full page to behave. */
  height: "calc(100vh - 250px)",
  minHeight: "420px",
  border: "1px solid var(--hair)",
  borderRadius: "13px",
  /* White, not `--pane`: a report is a document with its own colours and a
   * transparent frame over a dark shell renders black text on black. */
  background: "#ffffff",
};

const text: React.CSSProperties = {
  margin: 0,
  padding: "18px 20px",
  borderRadius: "13px",
  border: "1px solid var(--hair)",
  background: "var(--pane)",
  color: "var(--text)",
  fontSize: "12.5px",
  lineHeight: 1.6,
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
  overflowX: "auto",
};

const cut: React.CSSProperties = {
  fontSize: "11.5px",
  color: "var(--warn, var(--text-3))",
  marginBottom: "8px",
};

export interface ReportFrameProps {
  /** The door's own answer. Nothing here re-derives its type from the path. */
  file: GitFile;
  /** For the frame's accessible name — the row's title, not the file name. */
  title: string;
}

export function ReportFrame({ file, title }: ReportFrameProps): React.JSX.Element {
  return (
    <div data-testid="report-body">
      {/* A cut report that does not say it was cut is a lie — `GitDiff`'s rule,
          and the door hands over the same two keys so it can be said once. */}
      {file.truncated ? (
        <div data-testid="report-truncated" style={cut}>
          this report is longer than {file.cap.toLocaleString()} bytes and was cut here —
          the whole of it is the file at {file.rev.slice(0, 12)}
        </div>
      ) : null}
      {file.content_type === "text/html" ? (
        <iframe
          data-testid="report-frame"
          title={title}
          /* THE BOUNDARY. See the head of this file. */
          sandbox={SANDBOX}
          srcDoc={file.text}
          /* Nothing this frame requests should carry where it came from, and no
             delegated permission (camera, geolocation, …) should reach it. Both
             are already implied by the sandbox; both are stated anyway, because
             an empty `allow` is one attribute and a regression here is silent. */
          referrerPolicy="no-referrer"
          allow=""
          style={frame}
        />
      ) : (
        <pre className="mono" data-testid="report-text" style={text}>
          {file.text}
        </pre>
      )}
    </div>
  );
}

export default ReportFrame;
