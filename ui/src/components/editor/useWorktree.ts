/* The Editor's reads — the trees, one tree's listing, the open files, one
 * file's diff — and its one stream. Every route the page speaks is spelled
 * HERE, beside the hook that asks it, the way `links.tsx::gitRoute` keeps the
 * /git door's shape next to the cascade it feeds.
 *
 * NOT `useBoard`, and not a violation of its rule. That hook owns "what the
 * board says right now"; nothing here is on the board. A worktree's files are
 * on the DISK, they move on the disk's clock, and the board payload cannot
 * carry them — so the page has its own reads and its own signal, exactly as
 * the Event stream has (`useEvents.ts`). What it borrows is the SHAPE: a
 * signal is a poke, the page refetches, and nothing a frame carries is ever
 * drawn.
 *
 * THE LIVE LOOP, in three steps and no more:
 *   1. `useListing` opens the tree's feed through `client.watch` — the same
 *      reconnect loop the board feed runs — and re-reads the listing on every
 *      frame (`hello` included, so a reconnect heals staleness).
 *   2. `useOpenFiles` compares each open tab's `mtime`/`size` with the new
 *      listing and re-reads the tabs that moved — and ONLY those. A tab whose
 *      path the listing no longer names is marked `gone`, its text kept: a
 *      reader mid-sentence is not thrown out because the file was renamed.
 *   3. A re-read computes `changedSpan` against the text it replaces and hands
 *      the rows a `Flash`, keyed on the moment, so the pane lights the lines
 *      and keeps its scroll.
 * Nothing polls the door. If the stream is down the page says so (`live`)
 * and the loop reconnects on its own. */
import { useCallback, useEffect, useRef, useState } from "react";

import type { GitReader } from "../../links";
import type { EditorDiff, EditorFile, EditorTrees, TreeListing } from "../../types";
import type { Flash } from "./CodeView";
import { changedSpan, linesOf } from "./tree";

/** What this page needs of a client: the /git-shaped GET and the second
 *  stream. `client.ts::Client` satisfies it structurally, and a caller with no
 *  wire passes null and gets every empty state. */
export interface EditorReader extends GitReader {
  watch(route: string, onSignal: () => void, onLive: (live: boolean) => void): () => void;
}

/* ── the routes, spelled once ──────────────────────────────────────────────── */

export function treesRoute(): string {
  return "editor/trees";
}

export function treeRoute(tree: string): string {
  return `editor/tree?tree=${encodeURIComponent(tree)}`;
}

export function fileRoute(tree: string, path: string, base: string): string {
  return `editor/file?tree=${encodeURIComponent(tree)}&path=${encodeURIComponent(path)}` + (base ? `&base=${encodeURIComponent(base)}` : "");
}

export function diffRoute(tree: string, path: string, base: string): string {
  return `editor/diff?tree=${encodeURIComponent(tree)}&path=${encodeURIComponent(path)}` + (base ? `&base=${encodeURIComponent(base)}` : "");
}

export function feedRoute(tree: string): string {
  return `editor/feed?tree=${encodeURIComponent(tree)}`;
}

/* ── the trees ─────────────────────────────────────────────────────────────── */

export function useTrees(reader: EditorReader | null | undefined): {
  trees: EditorTrees | null;
  refusal: string | null;
  loading: boolean;
} {
  const [trees, setTrees] = useState<EditorTrees | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let mine = true;
    if (!reader) return;
    setLoading(true);
    reader
      .git<EditorTrees>(treesRoute())
      .then((answer) => {
        if (mine) {
          setTrees(answer);
          setRefusal(null);
        }
      })
      .catch((failure: unknown) => {
        // The deployed instance has no checkout and says so in one sentence;
        // the page quotes it. Nothing here paraphrases a refusal.
        if (mine) setRefusal(failure instanceof Error ? failure.message : String(failure));
      })
      .finally(() => {
        if (mine) setLoading(false);
      });
    return () => {
      mine = false;
    };
  }, [reader]);
  return { trees, refusal, loading };
}

/* ── one tree, live ────────────────────────────────────────────────────────── */

export function useListing(
  reader: EditorReader | null | undefined,
  tree: string | null,
): { listing: TreeListing | null; refusal: string | null; live: boolean } {
  const [listing, setListing] = useState<TreeListing | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [live, setLive] = useState(false);

  useEffect(() => {
    let mine = true;
    setListing(null);
    setRefusal(null);
    if (!reader || !tree) {
      setLive(false);
      return;
    }
    const door = reader;
    const name = tree;
    function read(): void {
      door
        .git<TreeListing>(treeRoute(name))
        .then((answer) => {
          if (mine) {
            setListing(answer);
            setRefusal(null);
          }
        })
        .catch((failure: unknown) => {
          if (mine) setRefusal(failure instanceof Error ? failure.message : String(failure));
        });
    }
    read();
    // The frame is a poke: `hello` on (re)connect and `change` on a scan that
    // differed both re-read the listing, and only the listing.
    const stop = door.watch(feedRoute(name), read, (up) => {
      if (mine) setLive(up);
    });
    return () => {
      mine = false;
      stop();
    };
  }, [reader, tree]);

  return { listing, refusal, live };
}

/* ── the open files ────────────────────────────────────────────────────────── */

export interface OpenTab {
  path: string;
  file: EditorFile | null;
  refusal: string | null;
  flash: Flash | null;
  gone: boolean;
}

export interface OpenFiles {
  tabs: OpenTab[];
  active: string | null;
  open: (path: string) => void;
  select: (path: string) => void;
  close: (path: string) => void;
}

export function useOpenFiles(
  reader: EditorReader | null | undefined,
  tree: string | null,
  listing: TreeListing | null,
  base: string,
  clock: () => number = () => Date.now(),
): OpenFiles {
  const [tabs, setTabs] = useState<OpenTab[]>([]);
  const [active, setActive] = useState<string | null>(null);
  // Which mtime each path was last asked at — the guard that makes one change
  // one fetch, whatever number of listings arrive while it is in flight.
  const asked = useRef(new Map<string, number>());

  const fetchFile = useCallback(
    (path: string) => {
      if (!reader || !tree) return;
      const at = tree;
      reader
        .git<EditorFile>(fileRoute(at, path, base))
        .then((answer) => {
          setTabs((was) =>
            was.map((tab) => {
              if (tab.path !== path) return tab;
              const span = tab.file ? changedSpan(linesOf(tab.file.text), linesOf(answer.text)) : null;
              const flash: Flash | null = span ? { from: span[0], to: span[1], at: clock() } : null;
              return { ...tab, file: answer, refusal: null, flash: flash ?? tab.flash };
            }),
          );
        })
        .catch((failure: unknown) => {
          const said = failure instanceof Error ? failure.message : String(failure);
          setTabs((was) => was.map((tab) => (tab.path === path ? { ...tab, refusal: said } : tab)));
        });
    },
    [reader, tree, base, clock],
  );

  // A new tree is a new set of tabs: nothing from the old one carries over.
  useEffect(() => {
    setTabs([]);
    setActive(null);
    asked.current = new Map();
  }, [tree]);

  // A new listing: re-read the tabs whose file moved, mark the ones that left.
  useEffect(() => {
    if (!listing) return;
    const now = new Map(listing.files.map((f) => [f.path, f]));
    setTabs((was) => was.map((tab) => ({ ...tab, gone: !now.has(tab.path) })));
    for (const tab of tabs) {
      const entry = now.get(tab.path);
      if (!entry) continue;
      const seen = asked.current.get(tab.path);
      if (seen === entry.mtime) continue;
      asked.current.set(tab.path, entry.mtime);
      fetchFile(tab.path);
    }
    // `tabs` is read, not depended on: a tab opening already fetches itself,
    // and depending on it would re-run this on every open and close.
  }, [listing, fetchFile]);

  const open = useCallback(
    (path: string) => {
      setActive(path);
      setTabs((was) => {
        if (was.some((t) => t.path === path)) return was;
        return [...was, { path, file: null, refusal: null, flash: null, gone: false }];
      });
      const entry = listing?.files.find((f) => f.path === path);
      if (!asked.current.has(path)) {
        asked.current.set(path, entry?.mtime ?? 0);
        fetchFile(path);
      }
    },
    [fetchFile, listing],
  );

  const close = useCallback((path: string) => {
    setTabs((was) => {
      const at = was.findIndex((t) => t.path === path);
      const next = was.filter((t) => t.path !== path);
      setActive((current) => {
        if (current !== path) return current;
        const neighbour = next[Math.min(at, next.length - 1)];
        return neighbour ? neighbour.path : null;
      });
      return next;
    });
    asked.current.delete(path);
  }, []);

  return { tabs, active, open, select: setActive, close };
}

/* ── one file's diff, on demand ────────────────────────────────────────────── */

export function useDiff(
  reader: EditorReader | null | undefined,
  tree: string | null,
  path: string | null,
  base: string,
  on: boolean,
  /** anything whose identity changes when the file was re-read */
  signal: unknown,
): { patch: EditorDiff | null; loading: boolean; refusal: string | null } {
  const [patch, setPatch] = useState<EditorDiff | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let mine = true;
    if (!reader || !tree || !path || !on) {
      setPatch(null);
      setRefusal(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    reader
      .git<EditorDiff>(diffRoute(tree, path, base))
      .then((answer) => {
        if (mine) {
          setPatch(answer);
          setRefusal(null);
        }
      })
      .catch((failure: unknown) => {
        if (mine) {
          setPatch(null);
          setRefusal(failure instanceof Error ? failure.message : String(failure));
        }
      })
      .finally(() => {
        if (mine) setLoading(false);
      });
    return () => {
      mine = false;
    };
  }, [reader, tree, path, base, on, signal]);
  return { patch, loading, refusal };
}
