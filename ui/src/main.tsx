/* The entry point: pick the theme BEFORE the first paint, adopt a pasted token,
 * build the one client, then mount.
 *
 * The attribute is written here rather than in a component because a render
 * happens after the browser has already painted the body once — writing it
 * later is a visible flash of the wrong palette.
 *
 * The client is built HERE and handed to App as a prop. Everything that reads a
 * browser global — the pathname the board is mounted under, localStorage, the
 * query string — is confined to this file, which is why App can be rendered in a
 * test with a fake client and no globals patched at all. */
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { bootstrapToken, createClient } from "./client";
import { applyTheme, readTheme } from "./theme/theme";

applyTheme(readTheme());

// Two addresses, one page. A WINDOW serves it at the root — `taskops ui` hands
// out `http://127.0.0.1:<port>/`, because `board` is only the name a window
// mounts its single board under and `/ui/` was a door on a host that serves no
// page at all; neither belongs in the URL a human types. Mounted under
// /<board>/ui/ it still works, and that is where the routes hang off.
const mounted = location.pathname.replace(/\/ui\/?$/, "");
const base = mounted === "" || mounted === "/" ? "/board" : mounted;

// The token is stripped from wherever the page actually IS, not from a path
// recomputed out of `base` — at the root those two are different addresses, and
// rewriting to the computed one is what put /board/ui/ back in the bar.
bootstrapToken(base, localStorage, location.search, location.pathname, (url) =>
  history.replaceState({}, "", url),
);

const client = createClient(base, localStorage);

const host = document.getElementById("root");
if (host) createRoot(host).render(<App client={client} />);
