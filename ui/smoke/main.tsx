/* What the dashboard has to prove, run against a real board payload.
 *
 * This file is no longer the list — it is the PLUMBING and the RUN ORDER. The
 * list lives in `sections/`, one file per section, named by what it pins, and
 * this entry loads them through `sections/index.generated.ts`, which `run.mjs`
 * writes from a `readdir` in filename order and which is gitignored: a
 * generated index cannot conflict, and no card ever edits a shared list to add
 * coverage. `sections/section.ts` carries the post-mortem of the appendix this
 * replaced.
 *
 * The assertions are aimed at the modules `src/main.tsx` bundles, so every one
 * of them is about the page that actually ships — and the three seams that make
 * it runnable without a browser are used exactly as their authors designed them:
 *
 *   · `Dossier`, exported beside `Drawer`, because `Overlay` is a PORTAL and a
 *     portal renders nothing under `renderToStaticMarkup`. The document is the
 *     part worth asserting on; the portal is not.
 *   · `submit()`, the send rule as a pure function, so "the draft survives a
 *     refusal" is a claim with no DOM in it.
 *   · `overlayStack`, which holds no listener, so "Escape closes the top-most
 *     only" runs under plain node.
 *
 * The payload is the board's own answer (`tests/test_ui.py` builds it from a
 * live `LocalBoard`), never a hand-written shape: a UI that renders a fixture
 * the server would never send is a UI that renders nothing in production, and
 * that was v1's actual failure. `expect` and `expect_board` travel IN the
 * fixture for the same reason — the Python side names the strings it put on the
 * board and this side proves they reached the screen. */
import { rows } from "../src/pages/Worktrees";

import { SECTIONS } from "./sections/index.generated";
import type { Check, Fixture, Harness } from "./sections/section";

export type { Fixture };

export async function smoke(fixture: Fixture): Promise<string[]> {
  const failures: string[] = [];

  const check: Check = (name, ok, detail = "") => {
    if (ok) console.log("ok " + name);
    else failures.push(`${name}${detail ? " — " + detail : ""}`);
  };

  const harness: Harness = {
    now: Date.now() / 1000,
    opened: [],
    slice: (markup, from, to) => {
      const start = markup.indexOf(from);
      if (start < 0) return "";
      const end = markup.indexOf(to, start);
      return markup.slice(start, end < 0 ? markup.length : end);
    },
    REPO: {
      host: "github.com",
      slug: "owner/repo",
      url: "https://github.com/owner/repo",
    },
    named: rows(fixture.board.groups, fixture.board.milestones),
  };

  for (const [slug, run] of SECTIONS) {
    try {
      await run(fixture, check, harness);
    } catch (err) {
      // A section that THROWS is one failure with its name on it, and the rest
      // of the list still runs: the appendix's other failure mode was one bad
      // line hiding fifteen good sections.
      failures.push(`section ${slug} threw — ${String(err)}`);
    }
  }

  return failures;
}
