import { renderToStaticMarkup } from "react-dom/server";

import { Dossier } from "../../src/components/card/Drawer";
import { languageOf, tokenize } from "../../src/components/editor/highlight";
import { changedSpan, filtered, folded, lastChange, linesOf, markMap } from "../../src/components/editor/tree";
import type { OpenTab } from "../../src/components/editor/useWorktree";
import { TABS } from "../../src/components/chrome/TabNav";
import { EditorView, baseFor, labelOf, type EditorViewProps } from "../../src/pages/Editor";
import { WorktreeDiff, Worktrees } from "../../src/pages/Worktrees";
import type { Check, Fixture, Harness } from "./section";

/* THE EDITOR (ARCHITECTURE.md §22), pinned from the door's OWN answers over a
 * real checkout with a real card worktree (`tests/test_ui.py::a_worktree`):
 * the tree with every git state in it, a modified file with the marks the
 * server computed, an untracked one, a binary, the patch, and the two
 * refusals the page quotes. `EditorView` is the pure half, exported beside
 * `Editor` for the reason `Dossier` is beside `Drawer` — no effect fires
 * under `react-dom/server`, and the document is what is worth asserting on.
 *
 * The LIVE half — the stream, the re-read, the flash — has no DOM here, so it
 * is pinned where it is decided: `changedSpan` on line arrays, and the view
 * handed a tab that carries a `flash` exactly as `useOpenFiles` builds one. */
export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const { now, named } = h;
  const e = fixture.editor;

  const tab = (path: string, file: OpenTab["file"], flash: OpenTab["flash"] = null): OpenTab => ({
    path,
    file,
    refusal: null,
    flash,
    gone: false,
  });

  const base: EditorViewProps = {
    trees: e.trees,
    refusal: null,
    loading: false,
    tree: e.listing.tree,
    onTree: () => {},
    named,
    listing: e.listing,
    live: true,
    query: "",
    onQuery: () => {},
    tabs: [tab("src/app.py", e.file)],
    active: "src/app.py",
    onOpen: () => {},
    onSelect: () => {},
    onClose: () => {},
    diff: { on: false, patch: null, loading: false, refusal: null },
    onToggleDiff: () => {},
    now,
  };
  const page = renderToStaticMarkup(<EditorView {...base} />);

  /* ── the picker, the checkout first ──────────────────────────────────── */
  check("the editor is the page", page.includes('data-testid="editor"'));
  const options = page.match(/data-testid="editor-picker-tree"/g) ?? [];
  check(
    "the picker lists every inhabited directory, the checkout first",
    options.length === e.trees.trees.length && e.trees.trees[0]!.name === "main",
  );
  check(
    "a tree the reader was sent to that is not on this disk is NAMED, disabled — never silently main",
    renderToStaticMarkup(<EditorView {...base} tree="tk-gone99" />).includes(
      'data-testid="editor-picker-missing"',
    ) && !page.includes('data-testid="editor-picker-missing"'),
  );
  check(
    "the meta line says the branch, the count, the newest change and that it is live",
    page.includes(`>${e.listing.branch}<`) &&
      page.includes(`${e.listing.files.length} files`) &&
      page.includes('data-testid="editor-last-change"') &&
      /data-testid="editor-live"[^>]*data-live="true"/.test(page),
  );
  check(
    "a listing the door cut says so, with both numbers",
    renderToStaticMarkup(
      <EditorView {...base} listing={{ ...e.listing, capped: true, total: 9000, cap: 4000 }} />,
    ).includes("of 9,000 — capped at 4,000") && !page.includes('data-testid="editor-capped-tree"'),
  );

  /* ── the tree: folders, states, the dot ──────────────────────────────── */
  const tree = h.slice(page, 'data-testid="editor-tree"', 'data-testid="editor-tabs"');
  const states = Object.fromEntries(e.listing.files.map((f) => [f.path, f.state]));
  check(
    "the fixture tree carries every git state a file can be in",
    ["clean", "modified", "added", "staged", "untracked"].every((s) => Object.values(states).includes(s as never)),
  );
  check(
    "every file is drawn wearing its git state, as text and not colour alone",
    e.listing.files.every((f) =>
      new RegExp(`data-testid="editor-file" data-path="${f.path}" data-state="${f.state}"`).test(tree),
    ) &&
      /aria-label="modified"[^>]*>M</.test(tree) &&
      /aria-label="untracked"[^>]*>U</.test(tree) &&
      /aria-label="added"[^>]*>A</.test(tree) &&
      /aria-label="staged"[^>]*>S</.test(tree),
  );
  check(
    "a folder with something changed under it carries the count and the dot; a clean one neither",
    /data-testid="editor-folder" data-path="src" data-changed="4"/.test(tree) &&
      /data-testid="editor-folder" data-path="docs" data-changed="0"/.test(tree) &&
      (tree.match(/data-testid="editor-folder-changed"/g) ?? []).length === 1,
  );
  check(
    "folders are real buttons with aria-expanded, open by default",
    /data-testid="editor-folder"[^>]*aria-expanded="true"/.test(tree),
  );
  check(
    "the open file is aria-current in the tree",
    /data-testid="editor-file" data-path="src\/app.py"[^>]*aria-current="true"/.test(tree),
  );
  const narrowed = renderToStaticMarkup(<EditorView {...base} query="new" />);
  check(
    "the filter narrows the tree to the paths that match, folders kept open",
    (narrowed.match(/data-testid="editor-file"/g) ?? []).length === 1 &&
      narrowed.includes('data-path="src/new.py"') &&
      /data-testid="editor-folder" data-path="src"[^>]*aria-expanded="true"/.test(narrowed),
  );
  check(
    "a filter that matches nothing says so, in the reader's own words",
    renderToStaticMarkup(<EditorView {...base} query="zzz" />).includes("nothing matches “zzz”"),
  );

  /* ── the tabs and the code ───────────────────────────────────────────── */
  check(
    "the open file is a selected tab with a close of its own",
    /data-testid="editor-tab" data-path="src\/app.py" aria-selected="true"/.test(page) &&
      page.includes('data-testid="editor-tab-close"'),
  );
  check(
    "the path line says the file, its state and the base the door used",
    page.includes('data-testid="editor-path"') &&
      page.includes('data-testid="editor-state">modified<') &&
      new RegExp(`data-testid="editor-base">vs <span class="mono">${e.file.base!.ref}</span>`).test(page),
  );
  const code = h.slice(page, 'data-testid="editor-code"', "</section>");
  const lines = code.match(/data-testid="editor-line"/g) ?? [];
  check(
    "the code is drawn line by line, numbered, in the file's own language",
    /data-testid="editor-code" data-lang="python"/.test(code) &&
      lines.length === linesOf(e.file.text).length &&
      code.includes('data-n="1"') &&
      code.includes(`data-n="${lines.length}"`),
  );
  check(
    "the marks the door computed sit in the gutter, line by line",
    e.file.marks.length === 2 &&
      /data-n="4" data-mark="modified"/.test(code) &&
      /data-n="5" data-mark="added"/.test(code) &&
      /data-n="7" data-mark="added"/.test(code) &&
      /data-n="1"(?! data-mark)/.test(code),
  );
  check(
    "python is coloured: keywords, and nothing spelled as a literal colour",
    /data-tok="keyword"[^>]*>import</.test(code) &&
      /data-tok="keyword"[^>]*>def</.test(code) &&
      /data-tok="keyword"[^>]*>return</.test(code) &&
      !/#[0-9a-fA-F]{3,6}/.test(code),
  );
  check(
    "a line the disk just changed is lit, keyed on the moment",
    (() => {
      const lit = renderToStaticMarkup(
        <EditorView {...base} tabs={[tab("src/app.py", e.file, { from: 4, to: 5, at: 1234 })]} />,
      );
      return (
        (lit.match(/data-flash="true"/g) ?? []).length === 2 &&
        /data-n="4" data-mark="modified" data-flash="true"/.test(lit) &&
        !/data-n="6"[^>]*data-flash/.test(lit)
      );
    })(),
  );

  /* ── an untracked file, a binary, a cut file ─────────────────────────── */
  const fresh = renderToStaticMarkup(
    <EditorView {...base} tabs={[tab("src/new.py", e.untracked)]} active="src/new.py" />,
  );
  check(
    "an untracked file is all addition in the gutter and says so above the code",
    e.untracked.tracked === false &&
      /data-n="1" data-mark="added"/.test(fresh) &&
      fresh.includes('data-testid="editor-state">untracked<'),
  );
  const binary = renderToStaticMarkup(
    <EditorView {...base} tabs={[tab("logo.png", e.binary)]} active="logo.png" />,
  );
  check(
    "a binary is named with its size and never decoded into a pane",
    e.binary.binary &&
      binary.includes(`binary, ${e.binary.size.toLocaleString()} bytes`) &&
      !binary.includes('data-testid="editor-code"'),
  );
  const cut = renderToStaticMarkup(
    <EditorView {...base} tabs={[tab("src/app.py", { ...e.file, truncated: true, cap: 10 })]} />,
  );
  check(
    "a cut file SAYS it was cut, with the cap and the size on disk",
    cut.includes('data-testid="editor-capped"') && cut.includes("cut at 10 bytes") && cut.includes("bytes on disk"),
  );
  check(
    "a tab whose file left the disk says deleted and keeps its text",
    (() => {
      const gone = renderToStaticMarkup(
        <EditorView {...base} tabs={[{ ...tab("src/app.py", e.file), gone: true }]} />,
      );
      return gone.includes('data-testid="editor-tab-gone"') && gone.includes('data-testid="editor-code"');
    })(),
  );

  /* ── diff vs base: the one patch renderer ────────────────────────────── */
  const diffOn = renderToStaticMarkup(
    <EditorView {...base} diff={{ on: true, patch: e.diff, loading: false, refusal: null }} />,
  );
  check(
    "the diff toggle draws the working copy's patch through the same renderer as the Worktrees page",
    /data-testid="editor-diff-toggle"[^>]*aria-pressed="true"/.test(diffOn) &&
      diffOn.includes('data-testid="editor-diff"') &&
      diffOn.includes('data-testid="patch"') &&
      diffOn.includes("+    return 2") &&
      !diffOn.includes('data-testid="editor-code"'),
  );
  check(
    "a file that reads as the base has it says so rather than drawing an empty pane",
    renderToStaticMarkup(
      <EditorView {...base} diff={{ on: true, patch: { ...e.diff, patch: "" }, loading: false, refusal: null }} />,
    ).includes('data-testid="editor-diff-empty"'),
  );

  /* ── the two one-sentence states ─────────────────────────────────────── */
  const hosted = renderToStaticMarkup(<EditorView {...base} trees={null} listing={null} refusal={e.no_checkout} />);
  check(
    "a host with no checkout draws the door's own sentence and no tree",
    hosted.includes('data-testid="editor-none"') &&
      hosted.includes("taskops ui") &&
      hosted.includes(e.no_checkout.slice(0, 40)) &&
      !hosted.includes('data-testid="editor-tree"'),
  );
  check(
    "the path wall's sentence is the door's, one sentence for every shape",
    e.outside.includes("not a file inside that worktree") && e.outside.includes("never `.git`"),
  );
  check(
    "nothing open yet is a sentence, not a blank pane",
    renderToStaticMarkup(<EditorView {...base} tabs={[]} active={null} />).includes('data-testid="editor-empty"'),
  );

  /* ── the pure rules the live half stands on ──────────────────────────── */
  check(
    "the tab re-read after a write lights exactly the lines that moved",
    JSON.stringify(changedSpan(["a", "b", "c"], ["a", "B", "c"])) === "[2,2]" &&
      JSON.stringify(changedSpan(["a", "b", "c"], ["a", "b", "x", "y", "c"])) === "[3,4]" &&
      JSON.stringify(changedSpan(["a", "b", "c"], ["a", "c"])) === "[2,2]" &&
      changedSpan(["a", "b"], ["a", "b"]) === null &&
      JSON.stringify(changedSpan([], ["a"])) === "[1,1]",
  );
  check(
    "a file ending in a newline has no empty last line, as git counts it",
    linesOf("a\nb\n").length === 2 && linesOf("a\nb").length === 2 && linesOf("").length === 1,
  );
  check(
    "the newest mtime is the last change, and an empty tree has none",
    lastChange(e.listing.files) !== null &&
      e.listing.files.every((f) => f.mtime <= lastChange(e.listing.files)!.mtime) &&
      lastChange([]) === null,
  );
  const nodes = folded(e.listing.files);
  check(
    "the tree folds folders first, files after, each folder counting what moved under it",
    nodes[0]?.kind === "folder" &&
      nodes.filter((n) => n.kind === "folder").length === 2 &&
      nodes.find((n) => n.kind === "folder" && n.path === "src")?.kind === "folder" &&
      (nodes.find((n) => n.path === "src") as { changed: number }).changed === 4,
  );
  check(
    "the filter is a case-insensitive substring over the whole path",
    filtered(e.listing.files, "SRC/NEW").length === 1 && filtered(e.listing.files, "").length === e.listing.files.length,
  );
  check(
    "marks fold into a line → kind map",
    markMap([[4, 4, "modified"], [5, 7, "added"]]).get(6) === "added" && markMap([]).size === 0,
  );
  check(
    "the base is the card's own chapter branch, and nothing for a tree the board cannot name",
    baseFor(named[0]!.id, named) === (named[0]!.milestone?.branch ?? "") && baseFor("main", named) === "" && baseFor(null, named) === "",
  );
  check(
    "a tree is labelled by its card's title when the board knows it, its branch otherwise",
    labelOf(named[0]!.id, named[0]!.id, named).includes(named[0]!.title) &&
      labelOf("_ms-x", "ms/x", named) === "_ms-x — ms/x" &&
      labelOf("main", "main", named) === "main",
  );

  /* ── the tokenizer: enough to read by, decided by extension ───────────── */
  check(
    "the language is decided by extension, then by whole name, and plain is a real answer",
    languageOf("a/b.py") === "python" &&
      languageOf("x.tsx") === "script" &&
      languageOf("x.yml") === "yaml" &&
      languageOf("Dockerfile") === "bash" &&
      languageOf("notes.md") === "markdown" &&
      languageOf("x.unknownext") === "plain" &&
      languageOf("LICENSE") === "plain",
  );
  const kinds = (text: string, lang: Parameters<typeof tokenize>[1]): string[] =>
    tokenize(text, lang).flatMap((l) => l.map((t) => `${t.kind}:${t.text}`));
  check(
    "a python # inside a string is a string, and outside it a comment",
    kinds('x = "a # b"  # c', "python").includes('string:"a # b"') &&
      kinds('x = "a # b"  # c', "python").includes("comment:# c"),
  );
  check(
    "a script // inside a string is a string; a template literal spans lines as one string",
    kinds('const u = "http://x"; // y', "script").includes('string:"http://x"') &&
      tokenize("const t = `a\nb`;", "script")[1]?.[0]?.kind === "string",
  );
  check(
    "a block comment spanning lines is a comment on every line it crosses",
    tokenize("/* a\nb\nc */ x", "script").slice(0, 3).every((l) => l[0]?.kind === "comment"),
  );
  check(
    "sql keywords are case-insensitive, and json's literals are keywords",
    kinds("select * FROM t", "sql").includes("keyword:select") &&
      kinds("select * FROM t", "sql").includes("keyword:FROM") &&
      kinds('{"a": true, "b": null}', "json").includes("keyword:true"),
  );
  check(
    "bash names its variables and yaml its keys",
    kinds("echo $HOME ${X}", "bash").includes("attr:$HOME") &&
      kinds("echo $HOME ${X}", "bash").includes("attr:${X}") &&
      kinds("name: value # c", "yaml").includes("attr:name") &&
      kinds("name: value # c", "yaml").includes("comment:# c"),
  );
  check(
    "markdown: headings, fences, inline code; html: tags and attributes; css: selectors and properties",
    kinds("# Title", "markdown").includes("keyword:# Title") &&
      tokenize("```py\nx = 1\n```", "markdown")[1]?.[0]?.kind === "text" &&
      kinds("say `hi`", "markdown").includes("string:`hi`") &&
      kinds('<a href="x">', "html").includes("tag:<a") &&
      kinds('<a href="x">', "html").includes("attr:href") &&
      kinds(".a { color: red; }", "css").includes("tag:.a") &&
      kinds(".a { color: red; }", "css").includes("attr:color"),
  );
  check(
    "numbers are numbers and plain text carries no token but text",
    kinds("x = 0x1F + 2.5e3", "python").includes("number:0x1F") &&
      kinds("x = 0x1F + 2.5e3", "python").includes("number:2.5e3") &&
      tokenize("def x", "plain").every((l) => l.every((t) => t.kind === "text")),
  );

  /* ── the three doors in ──────────────────────────────────────────────── */
  check("the Editor is the sixth tab, after Worktrees and before Reports", (() => {
    const ids = TABS.map((t) => t.id);
    return ids.indexOf("editor") === ids.indexOf("worktrees") + 1 && ids.indexOf("editor") < ids.indexOf("reports");
  })());
  const index = renderToStaticMarkup(
    <Worktrees groups={fixture.board.groups} milestones={fixture.board.milestones} onOpenEditor={() => {}} />,
  );
  check(
    "every worktree row carries a door into the editor, and none without one to send to",
    (index.match(/data-testid="worktree-editor"/g) ?? []).length === named.length &&
      !renderToStaticMarkup(<Worktrees groups={fixture.board.groups} milestones={fixture.board.milestones} />).includes(
        "worktree-editor",
      ),
  );
  check(
    "the diff page carries the same door",
    renderToStaticMarkup(
      <WorktreeDiff row={named[0]!} base="ms/nova" reader={null} onBack={() => {}} onOpenEditor={() => {}} />,
    ).includes('data-testid="worktree-diff-editor"'),
  );
  check(
    "the dossier's Worktree block sends the reader to the code as well as to the tree",
    renderToStaticMarkup(
      <Dossier
        dossier={fixture.card}
        openId={fixture.card.card.id}
        team={[]}
        now={now}
        onClose={() => {}}
        onComment={async () => {}}
        onOpenTree={() => {}}
        onOpenEditor={() => {}}
      />,
    ).includes('data-testid="card-open-editor"') &&
      !renderToStaticMarkup(
        <Dossier
          dossier={fixture.card}
          openId={fixture.card.card.id}
          team={[]}
          now={now}
          onClose={() => {}}
          onComment={async () => {}}
        />,
      ).includes("card-open-editor"),
  );
}
