// The build: one bundle, one stylesheet, one page, into the Python package.
//
// The output is COMMITTED, and `npm run check` re-runs this and fails on a non-empty diff.
// That way `pip install taskops` serves the board with no node toolchain anywhere, and the
// committed bundle cannot drift from its source — the two failure modes of the alternatives,
// avoided together.
//
// React is BUNDLED, not loaded from a CDN. The UI has to work on a laptop with no network
// and behind a corporate proxy, and a board that cannot render without reaching the internet is
// not a local tool.
import { build } from "esbuild";
import { copyFile, mkdir } from "node:fs/promises";

const OUT = new URL("../src/taskops/transports/http/ui/", import.meta.url);

await mkdir(OUT, { recursive: true });

await build({
  entryPoints: ["src/main.tsx"],
  bundle: true,
  format: "esm",
  target: "es2022",
  minify: true,
  sourcemap: false,        // the source ships in this repo; a map would double the bundle
  jsx: "automatic",
  define: { "process.env.NODE_ENV": '"production"' },
  outfile: new URL("app.js", OUT).pathname,
  logLevel: "info",
});

await build({
  entryPoints: ["styles/index.css"],
  bundle: true,
  minify: true,
  outfile: new URL("style.css", OUT).pathname,
  logLevel: "info",
});

await copyFile(new URL("index.html", import.meta.url), new URL("index.html", OUT));
console.log("ui built ->", OUT.pathname);
