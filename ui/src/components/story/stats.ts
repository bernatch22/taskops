/* The story view's arithmetic — PURE, exported, no React and no tokens, so the
 * smoke section can pin the numbers without rendering a pixel (the same split
 * `markdown.ts` / `Markdown.tsx` made, for the same reason).
 *
 * Everything here is a fold over `CardStory[]` — the `activity` answer's cards
 * (`verbs/_stories.py::story`). Nothing is fetched and nothing is re-derived
 * downstream: `ChapterStory.tsx` calls these once and draws what comes back. */

import type { CardStory } from "../../types";

/** One card's diff, folded from `commits[].numstat`.
 *
 *  `numstat` is optional twice over (types.ts::CommitRef): a commit that counted
 *  nothing carries no key, and a board older than tk-dd6a9b never wrote it. A
 *  `null` per-file entry is a BINARY — git prints `-` there — and "cannot be
 *  counted" is not "nothing changed", so it counts as 0 and raises the flag the
 *  view turns into a "bin" chip instead of vanishing. */
export interface CardDiff {
  added: number;
  deleted: number;
  /** at least one file in some commit was binary (numstat entry `null`) */
  binary: boolean;
}

export function diffOf(card: CardStory): CardDiff {
  let added = 0;
  let deleted = 0;
  let binary = false;
  for (const commit of card.commits) {
    for (const counts of Object.values(commit.numstat ?? {})) {
      if (counts === null) binary = true;
      else {
        added += counts[0];
        deleted += counts[1];
      }
    }
  }
  return { added, deleted, binary };
}

/** The header's strip, folded once over the whole chapter. */
export interface ChapterStats {
  done: number;
  dropped: number;
  /** the honest totals (`commits_total`), not the capped lists' lengths */
  commits: number;
  /** distinct files across every commit's numstat — a floor, like the lists it
   *  is read from: commits behind `_stories.COMMITS_SHOWN` are not here */
  files: number;
  added: number;
  deleted: number;
  /** total worked, a floor (each card's `seconds` already is one) */
  seconds: number;
  /** first card's `since` → last card's — 0/0 when there are no cards */
  from: number;
  to: number;
}

export function chapterStats(cards: readonly CardStory[]): ChapterStats {
  const files = new Set<string>();
  const out: ChapterStats = {
    done: 0,
    dropped: 0,
    commits: 0,
    files: 0,
    added: 0,
    deleted: 0,
    seconds: 0,
    from: 0,
    to: 0,
  };
  for (const card of cards) {
    if (card.status === "dropped") out.dropped += 1;
    else if (card.status === "done") out.done += 1;
    out.commits += card.commits_total;
    out.seconds += card.seconds;
    const diff = diffOf(card);
    out.added += diff.added;
    out.deleted += diff.deleted;
    for (const commit of card.commits) {
      for (const path of Object.keys(commit.numstat ?? {})) files.add(path);
    }
    out.from = out.from === 0 ? card.since : Math.min(out.from, card.since);
    out.to = Math.max(out.to, card.since);
  }
  out.files = files.size;
  return out;
}

/** The cards, in LANDING order — ascending `since`, the closest thing the
 *  payload has to merge order: a closed card's `since` is its `updated` (no
 *  lease survives closing, `verbs/pulse.py::_row`), and the last update of a
 *  done card is the close itself. The sort is stable, so ties keep the
 *  server's own order. Pure and exported so the smoke section pins the order
 *  without reading DOM positions out of markup. */
export function landingOrder(cards: readonly CardStory[]): CardStory[] {
  return [...cards].sort((a, b) => a.since - b.since);
}

/** ONE summary line per card, first of: the reviewer's words
 *  (`standing.note`, only when a verdict was actually given), the released
 *  note (`resume`), the LAST commit's subject (`commits` is newest LAST), or
 *  nothing. First line only — these are prose fields and a tile has one line. */
export function summaryOf(card: CardStory): string {
  const verdict = card.standing?.verdict ? card.standing.note : "";
  const text = verdict || card.resume || card.commits[card.commits.length - 1]?.subject || "";
  return text.split("\n", 1)[0] ?? "";
}
