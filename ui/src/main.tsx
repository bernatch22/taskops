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

// The page is served at /<board>/ui/; the board's own routes hang off /<board>.
const base = location.pathname.replace(/\/ui\/?$/, "");

bootstrapToken(base, localStorage, location.search, (url) => history.replaceState({}, "", url));

const client = createClient(base, localStorage);

const host = document.getElementById("root");
if (host) createRoot(host).render(<App client={client} />);
