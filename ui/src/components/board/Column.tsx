/* A kanban column: a coloured dot, a name, a count, and the tiles under it.
 *
 * It holds no data of its own — the tiles arrive as children already derived by
 * `Board.tsx`. A column that could decide what belongs in it would be a second
 * place where the mapping from board.groups lives, and the two would drift. */
import type { Tone } from "./CardTile";
import { TONE_FG } from "./CardTile";

export interface ColumnProps {
  name: string;
  tone: Tone;
  count: number;
  children: React.ReactNode;
}

const shell: React.CSSProperties = {
  display: "grid",
  gridTemplateRows: "auto 1fr",
  minHeight: 0,
  borderRadius: "16px",
  background: "var(--canvas-2)",
  border: "1px solid var(--hair)",
  overflow: "hidden",
};

const head: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "15px 16px 12px",
};

const body: React.CSSProperties = {
  overflowY: "auto",
  display: "flex",
  flexDirection: "column",
  gap: "9px",
  padding: "0 10px 12px",
};

export function Column({ name, tone, count, children }: ColumnProps): React.JSX.Element {
  return (
    <section style={shell} data-testid="column" data-column={name}>
      <header style={head}>
        <div style={{ display: "flex", alignItems: "center", gap: "9px" }}>
          <span
            style={{
              width: "7px",
              height: "7px",
              borderRadius: "50%",
              background: TONE_FG[tone],
            }}
          />
          <span style={{ fontSize: "13.5px", fontWeight: 500, letterSpacing: "-0.025em" }}>
            {name}
          </span>
        </div>
        <span
          className="num"
          data-testid="count"
          style={{
            fontSize: "11.5px",
            color: "var(--text-3)",
            padding: "2px 8px",
            borderRadius: "20px",
            background: "var(--pane)",
          }}
        >
          {count}
        </span>
      </header>
      <div style={body}>
        {count === 0 ? (
          <div
            style={{
              border: "1px dashed var(--hair-2)",
              borderRadius: "13px",
              padding: "22px 12px",
              textAlign: "center",
              color: "var(--faint)",
              fontSize: "12px",
            }}
          >
            empty
          </div>
        ) : (
          children
        )}
      </div>
    </section>
  );
}
