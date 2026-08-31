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
import { baseOf, bootstrapToken, createClient } from "./client";
import { applyTheme, readTheme } from "./theme/theme";

applyTheme(readTheme());

// THREE addresses, one page: the window's root (`taskops ui`, board under
// /board), the board's OWN address on a host (/<board>/ — the URL a human
// pastes), and 0.5.0's /<board>/ui/, kept for the links already out there.
// `baseOf` collapses all three to one clean base — the argument lives on it.
const base = baseOf(location.pathname);

// The token is stripped from wherever the page actually IS, not from a path
// recomputed out of `base` — at the root those two are different addresses, and
// rewriting to the computed one is what put /board/ui/ back in the bar.
bootstrapToken(base, localStorage, location.search, location.pathname, (url) =>
  history.replaceState({}, "", url),
);

const client = createClient(base, localStorage);

const host = document.getElementById("root");
if (host) createRoot(host).render(<App client={client} />);
