/* Is the chapter in focus FINISHED? Derived, never stored — the client-side
 * half of "derive, don't write": there is no `completed` status on the wire and
 * must never be one. The story view exists exactly when this returns true.
 *
 * Two ways a chapter reads as complete, and they are OR because they arrive by
 * different roads:
 *
 *  - the milestone LANDED (`taskops_merge milestone=` set `status: "landed"`) —
 *    the human's word, final whatever the groups say;
 *  - every group except `done` and `mentions` is empty AND something actually
 *    closed (`done_total > 0`) — all work finished, merge included, but the
 *    chapter has not been landed yet. `mentions` is excluded because it is the
 *    one group the milestone filter does not apply to (`verbs/pulse.py`): a
 *    board-wide unanswered mention says nothing about THIS chapter's state.
 *    `done_total > 0` is what keeps a freshly planned, still-empty chapter from
 *    reading as a triumph.
 *
 * No milestone in focus → false: "the whole board is complete" is not a
 * sentence this derivation is allowed to say.
 *
 * Every key is read with `?? []` / `?? 0` — the header rule of `types.ts` in
 * the concrete: a board one version behind (no `done` group, no `done_total`,
 * even no `groups`) must derive `false`, never crash. */

import type { BoardGroups, BoardPayload } from "./types";

/** The groups whose emptiness means "nothing left to do" — every group except
 *  `done` (finished work, expected to be full) and `mentions` (board-wide, not
 *  chapter state). */
const WORK_GROUPS = [
  "merge",
  "review",
  "changes",
  "stalled",
  "take",
  "doing",
  "reviewing",
  "blocked",
] as const satisfies readonly (keyof BoardGroups)[];

export function chapterComplete(board: BoardPayload): boolean {
  const stone = board.milestone;
  if (!stone) return false;
  if (stone.status === "landed") return true;
  const groups = (board.groups ?? {}) as Partial<BoardGroups>;
  const nothingInFlight = WORK_GROUPS.every((name) => (groups[name] ?? []).length === 0);
  return nothingInFlight && (board.done_total ?? 0) > 0;
}
