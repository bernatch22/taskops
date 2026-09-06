/* The icon sprite and the one component that draws from it.
 *
 * INLINE SVG SYMBOLS, defined ONCE per page (`<IconSprite/>` at the top of
 * the Editor) and referenced by `<use href="#id">` from every tree row and
 * every tab: one definition, hundreds of uses, no asset and no request. A
 * glyph is a rounded badge in the family's ink at low opacity with a short
 * monogram in the ink — VS Code's idea, at a size a 14px row can carry — and
 * two folder shapes. `fill: currentColor`, so the colour is the `--icon-*`
 * token the caller sets on the `<svg>`, never a literal here. The sprite is
 * under 2 kB of markup; the whole icon feature is a few kB of bundle. */
import { FILE, FOLDER, FOLDER_OPEN, iconFor, type FileIcon } from "./icons";

/** The badge families: a monogram on a soft square in the family's ink.
 *  `size` is the monogram's font size — three letters need a smaller one. */
const BADGES: readonly [id: string, mono: string, size: number][] = [
  ["python", "py", 7],
  ["typescript", "TS", 7],
  ["javascript", "JS", 7],
  ["json", "{}", 8],
  ["yaml", "yml", 6],
  ["toml", "tml", 6],
  ["markdown", "M↓", 7],
  ["sql", "SQL", 6],
  ["shell", "$_", 8],
  ["html", "<>", 8],
  ["css", "#", 9],
  ["lock", "🔒", 8],
  ["docker", "🐳", 8],
  ["env", "env", 6],
  ["git", "git", 6],
  ["image", "img", 6],
];

const STROKE = { fill: "none", stroke: "currentColor", strokeWidth: 1.2 } as const;

/** Rendered ONCE, as React elements — never `dangerouslySetInnerHTML`, which
 *  this dashboard refuses everywhere (ARCHITECTURE.md §15), even for a
 *  constant: one exception is how the next one gets in. */
export function IconSprite(): React.JSX.Element {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" style={{ display: "none" }} aria-hidden="true" data-testid="editor-icons">
      {BADGES.map(([id, mono, size]) => (
        <symbol key={id} id={`tk-i-${id}`} viewBox="0 0 16 16">
          <rect x="1" y="1" width="14" height="14" rx="3" fill="currentColor" opacity=".18" />
          <text
            x="8"
            y="11.2"
            textAnchor="middle"
            fontFamily="ui-monospace,monospace"
            fontSize={size}
            fontWeight={700}
            fill="currentColor"
          >
            {mono}
          </text>
        </symbol>
      ))}
      <symbol id="tk-i-file" viewBox="0 0 16 16">
        <path d="M4 1.5h5l3.5 3.5v9.5H4z" {...STROKE} strokeLinejoin="round" />
        <path d="M9 1.5V5h3.5" {...STROKE} />
      </symbol>
      <symbol id="tk-i-folder" viewBox="0 0 16 16">
        <path d="M1.5 3.5h4.5l1.5 1.5h7v8h-13z" fill="currentColor" opacity=".9" />
      </symbol>
      <symbol id="tk-i-folder-open" viewBox="0 0 16 16">
        <path d="M1.5 3.5h4.5l1.5 1.5h7v2h-11l-2 6z" fill="currentColor" opacity=".55" />
        <path d="M3.5 7h11.5l-2 6h-11.5z" fill="currentColor" opacity=".95" />
      </symbol>
    </svg>
  );
}

export function Icon({ icon, size = 15 }: { icon: FileIcon; size?: number }): React.JSX.Element {
  return (
    <svg
      data-testid="editor-icon"
      data-icon={icon.symbol}
      width={size}
      height={size}
      style={{ color: icon.ink, flex: "none", verticalAlign: "-3px" }}
      aria-hidden="true"
    >
      <use href={`#${icon.symbol}`} />
    </svg>
  );
}

export function FileGlyph({ path }: { path: string }): React.JSX.Element {
  return <Icon icon={iconFor(path)} />;
}

export function FolderGlyph({ open }: { open: boolean }): React.JSX.Element {
  return <Icon icon={open ? FOLDER_OPEN : FOLDER} />;
}

export { FILE };
