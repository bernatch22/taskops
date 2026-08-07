/* The entry point: pick the theme BEFORE the first paint, then mount.
 *
 * The attribute is written here rather than in a component because a render
 * happens after the browser has already painted the body once — writing it
 * later is a visible flash of the wrong palette. */
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { applyTheme, readTheme } from "./theme/theme";

applyTheme(readTheme());

const host = document.getElementById("root");
if (host) createRoot(host).render(<App />);
