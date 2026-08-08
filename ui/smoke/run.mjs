/* The smoke harness: run the dashboard headlessly, with no browser and no DOM.
 *
 * WHAT IT RUNS. `smoke/main.tsx` imports the SAME modules `src/main.tsx` bundles
 * — the pages, the dossier, the pure rules — and renders them through
 * `react-dom/server`. This file only compiles that entry and calls it: esbuild
 * with the same `jsx: "automatic"` the real build uses, and `packages:
 * "external"` so React is resolved by node from `ui/node_modules` rather than
 * inlined twice.
 *
 * WHY NOT jsdom. The assertions this page needs are about MARKUP (is the pane
 * there, does the empty state say what is missing, are the criteria drawn) and
 * about PURE RULES (`submit()` — the draft survives a refusal; `overlayStack` —
 * Escape closes the top-most only). Neither needs a document, and both of those
 * seams exist precisely so this harness can run under plain node: `Dossier` is
 * exported beside `Drawer` because `Overlay` is a portal and a portal renders
 * nothing under `renderToStaticMarkup`. So no dependency is added, and the
 * dashboard stays a `npm ci` of twelve packages.
 *
 * WHAT IT DOES NOT COVER, said plainly: no event handler ever fires here, so a
 * click that silently does nothing is still out of reach. What is in reach is
 * everything that decides whether the click has anything to land on.
 *
 * The output is the compiled bundle in `node_modules/.cache/` — inside the ui
 * project on purpose, so `import` resolves React from the same tree, and
 * gitignored with the rest of `node_modules`.
 *
 *     node smoke/run.mjs [fixture.json]     # default: smoke/fixture.json
 *
 * The fixture is a REAL board payload — `tests/test_ui.py` builds one from a
 * live `LocalBoard` and passes it here, which is what makes this a test of the
 * server's actual answer and not of a shape the UI invented. `smoke/fixture.json`
 * is one such payload, captured, so `npm run smoke` runs with no Python. */
import { build } from "esbuild";
import { mkdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const here = new URL("./", import.meta.url);
const cache = new URL("../node_modules/.cache/", here);
const out = new URL("smoke.mjs", cache);

const fixturePath = process.argv[2]
  ? new URL(process.argv[2], `file://${process.cwd()}/`)
  : new URL("fixture.json", here);

await mkdir(cache, { recursive: true });

await build({
  entryPoints: [fileURLToPath(new URL("main.tsx", here))],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "es2022",
  jsx: "automatic",
  // React stays external: node resolves it from ui/node_modules, so the harness
  // runs against the very copy the real bundle is built from.
  packages: "external",
  outfile: fileURLToPath(out),
  logLevel: "warning",
});

const fixture = JSON.parse(await readFile(fixturePath, "utf-8"));
const { smoke } = await import(out.href);

const failures = await smoke(fixture);
if (failures.length > 0) {
  for (const line of failures) console.error("FAIL " + line);
  console.error(`${failures.length} smoke assertion(s) failed`);
  process.exit(1);
}
console.log("smoke ok");
