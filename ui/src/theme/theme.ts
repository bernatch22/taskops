/* Which theme is on, and where that lives.
 *
 * The mode is an attribute on <html>, so the whole palette turns over in one
 * write and no component has to know a theme exists. It is remembered in
 * localStorage; with nothing remembered the OS decides, which is the only
 * default that is right on a first visit. */

const KEY = "taskops.theme";

export type Theme = "dark" | "light";

function osTheme(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function readTheme(): Theme {
  const kept = window.localStorage?.getItem(KEY);
  return kept === "dark" || kept === "light" ? kept : osTheme();
}

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-tk", theme);
  try {
    window.localStorage?.setItem(KEY, theme);
  } catch {
    // a browser with storage denied still gets a themed page for this session
  }
}
