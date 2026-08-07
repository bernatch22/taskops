/* The placeholder App: enough to prove the pipeline, and nothing this card
 * cannot verify. It draws through Nova's variables only — if the tokens did not
 * load, this page is unreadable rather than subtly off, which is the failure we
 * want loud. Later cards replace the body of this file with the real chrome. */
import { useState } from "react";

import { applyTheme, readTheme, type Theme } from "./theme/theme";

const shell: React.CSSProperties = {
  minHeight: "100vh",
  display: "grid",
  placeItems: "center",
  padding: "24px",
};

const panel: React.CSSProperties = {
  background: "var(--pane)",
  border: "1px solid var(--hair)",
  borderRadius: "16px",
  padding: "28px 32px",
  display: "grid",
  gap: "14px",
  justifyItems: "center",
  animation: "tk-lift 320ms cubic-bezier(0.2,0.8,0.2,1)",
};

const button: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  padding: "8px 14px",
  borderRadius: "10px",
  background: "var(--accent-soft)",
  border: "1px solid var(--accent-line)",
  color: "var(--accent-hi)",
  fontSize: "13px",
};

export function App(): React.JSX.Element {
  const [theme, setTheme] = useState<Theme>(readTheme);

  function flip(): void {
    const next: Theme = theme === "dark" ? "light" : "dark";
    applyTheme(next);
    setTheme(next);
  }

  return (
    <div style={shell}>
      <div style={panel}>
        <div style={{ fontSize: "17px", fontWeight: 500, letterSpacing: "-0.03em" }}>taskops</div>
        <div className="mono" style={{ fontSize: "11px", color: "var(--text-3)" }}>
          nova · ui pipeline up
        </div>
        <button style={button} onClick={flip} data-testid="theme">
          theme: {theme}
        </button>
      </div>
    </div>
  );
}
