/* Which icon a path wears, by extension or by whole name — ONE table, so a
 * new file type is one line. A symbol id names a glyph in `Icon.tsx`'s sprite
 * and a token names its ink in `theme/tokens.css` (`--icon-*`); nothing here
 * is a colour, and the sprite ships inside the bundle — no asset, no CDN. */

export interface FileIcon {
  /** the `<symbol id>` in the sprite, `tk-i-<family>` */
  symbol: string;
  /** the `--icon-*` token, as a `var()` */
  ink: string;
}

const family = (name: string): FileIcon => ({ symbol: `tk-i-${name}`, ink: `var(--icon-${name})` });

/** By whole file name first — a lock file or a Dockerfile has no useful
 *  extension — then by extension, then the generic file. */
export const BY_NAME: Record<string, FileIcon> = {
  "uv.lock": family("lock"),
  "pnpm-lock.yaml": family("lock"),
  "package-lock.json": family("lock"),
  "yarn.lock": family("lock"),
  "Cargo.lock": family("lock"),
  "poetry.lock": family("lock"),
  Dockerfile: family("docker"),
  ".dockerignore": family("docker"),
  ".env": family("env"),
  ".env.example": family("env"),
  ".gitignore": family("git"),
  ".gitattributes": family("git"),
  ".gitmodules": family("git"),
};

export const BY_EXT: Record<string, FileIcon> = {
  py: family("python"),
  pyi: family("python"),
  ts: family("typescript"),
  tsx: family("typescript"),
  mts: family("typescript"),
  js: family("javascript"),
  mjs: family("javascript"),
  cjs: family("javascript"),
  jsx: family("javascript"),
  json: family("json"),
  jsonc: family("json"),
  yaml: family("yaml"),
  yml: family("yaml"),
  toml: family("toml"),
  md: family("markdown"),
  markdown: family("markdown"),
  sql: family("sql"),
  sh: family("shell"),
  bash: family("shell"),
  zsh: family("shell"),
  html: family("html"),
  htm: family("html"),
  css: family("css"),
  png: family("image"),
  jpg: family("image"),
  jpeg: family("image"),
  gif: family("image"),
  svg: family("image"),
  webp: family("image"),
  ico: family("image"),
  lock: family("lock"),
  env: family("env"),
};

export const FOLDER: FileIcon = family("folder");
export const FOLDER_OPEN: FileIcon = family("folder-open");
export const FILE: FileIcon = family("file");

export function iconFor(path: string): FileIcon {
  const name = path.split("/").pop() ?? path;
  const named = BY_NAME[name];
  if (named) return named;
  if (path.startsWith(".github/") || name === ".github") return family("git");
  if (name.startsWith(".env.")) return family("env");
  const dot = name.lastIndexOf(".");
  const ext = dot >= 0 ? name.slice(dot + 1).toLowerCase() : "";
  return BY_EXT[ext] ?? FILE;
}

/** A middle ellipsis past `max` characters — the tab keeps both the stem and
 *  the extension, which is what tells `index.ts` from `index.test.ts`. */
export function shorten(name: string, max = 22): string {
  if (name.length <= max) return name;
  const head = Math.ceil((max - 1) / 2);
  return `${name.slice(0, head)}…${name.slice(name.length - (max - 1 - head))}`;
}
