/* Bundle the render and run it under node. Two things have to be faked and both are honest:
 * `Overlay` PORTALS to `document.body` and the server renderer supports no portals at all, so it is
 * swapped for a plain element — what these renders check is the CONTENT of a modal. And `api.ts`
 * reads `document`/`localStorage` at module scope for the board token. */
import { build } from "esbuild";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

/* In the repo and not in a temp dir: a stub outside `ui/` cannot resolve `react/jsx-runtime`. */
const shim = resolve("smoke/Overlay.stub.tsx");

const out = join(await mkdtemp(join(tmpdir(), "taskops-smoke-")), "render.cjs");
await build({
  entryPoints: ["smoke/render.tsx"], bundle: true, platform: "node", format: "cjs",
  jsx: "automatic", outfile: out, logLevel: "error", loader: { ".json": "json" },
  plugins: [{
    name: "no-portal",
    setup(builder) {
      builder.onResolve({ filter: /(^|\/)Overlay$/ }, () => ({ path: shim }));
    },
  }],
});

globalThis.document = { baseURI: "http://x/", body: {}, addEventListener() {}, removeEventListener() {} };
globalThis.location = { href: "http://x/" };
globalThis.localStorage = { getItem: () => null, setItem() {} };
await import(pathToFileURL(out).href);
