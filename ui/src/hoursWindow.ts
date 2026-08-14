/* Which span the Actors page is reading — a CHOICE on screen, a `window=`
 * spelling on the wire.
 *
 * `verbs/_windows.py::parse` is the one place that decides what a spelling
 * MEANS (`Nd` · `month` · `YYYY-MM` · `total`), and this file does not repeat a
 * word of that arithmetic: it maps four labelled options onto four of those
 * spellings and stops. Everything the screen then prints about the span — the
 * name of the month, the edges — comes back on the payload (`ReportPayload.window`),
 * because a client that re-derives "August 2026" from two epoch floats is a
 * second calendar implementation in a different language, in a different zone.
 *
 * ONE spelling is computed here and it has to be: `last` is "the month before
 * the one the READER is in", and only the browser knows that. It is a bare
 * `YYYY-MM`, which is exactly the form the server closes on both edges — so
 * the figure never moves again once the month is over, which is the whole
 * point of offering it beside a sliding window.
 *
 * Pure, and exported, for the reason every fold on the Actors page is: no
 * handler fires under `react-dom/server`, so a rule left inside a click closure
 * would have no test. */

import type { ReportPayload } from "./types";

export type HoursChoice = "7d" | "14d" | "30d" | "90d" | "month" | "last" | "total";

/** The filter, in the order it is drawn: sliding, then the anchor, then the
 *  closed month behind it, then the figure that only grows. */
export const HOURS_CHOICES: ReadonlyArray<{ id: HoursChoice; name: string }> = [
  { id: "7d", name: "7 days" },
  { id: "month", name: "This month" },
  { id: "last", name: "Last month" },
  { id: "total", name: "Total" },
];

/** The page opens on the CURRENT MONTH — the figure that only grows within it,
 *  and the one this chapter exists to put under a reader's eye. A sliding
 *  window as the default is what read as "hours being discounted". */
export const DEFAULT_HOURS_CHOICE: HoursChoice = "month";

/** THE DEGRADED VOCABULARY — what a PRE-CALENDAR host understands.
 *
 *  A 0.3.1 host's `days()` parser knows `Nd` and nothing else, and on an unknown
 *  spelling it falls back to SEVEN DAYS in silence. Shipping "month" at such a
 *  host is therefore not a graceful downgrade: it shrinks the reader's window
 *  from the old always-14d to 7d without a word, which is the regression this
 *  set exists to undo. Every spelling here is one the old parser reads exactly. */
export const LEGACY_HOURS_CHOICES: ReadonlyArray<{ id: HoursChoice; name: string }> = [
  { id: "7d", name: "last 7 days" },
  { id: "14d", name: "last 14 days" },
  { id: "30d", name: "last 30 days" },
  { id: "90d", name: "last 90 days" },
];

/** The pre-regression window: what the page showed before a calendar existed. */
export const LEGACY_DEFAULT_HOURS_CHOICE: HoursChoice = "14d";

/** WHICH FILTER THIS HOST CAN HONOUR — decided by the PAYLOAD'S SHAPE, never by
 *  a version string. `report.window` is the new host's own answer about the span
 *  it read; its ABSENCE is the feature detection (`types.ts` already has it
 *  optional, and this is that `??` branch).
 *
 *  FIRST PAINT (`report === null`, nothing has come back yet) is deterministic
 *  and optimistic: the set that CONTAINS the current selection, so the pressed
 *  option is never absent from its own control; with no selection told, the
 *  calendar set — the state the page is born in. The first payload then settles
 *  it, and `snapped()` moves the selection if that answer was a legacy one. */
export function choicesFor(
  report: ReportPayload | null | undefined,
  selected?: HoursChoice,
): ReadonlyArray<{ id: HoursChoice; name: string }> {
  if (report) return report.window ? HOURS_CHOICES : LEGACY_HOURS_CHOICES;
  const onlyLegacy =
    selected !== undefined &&
    LEGACY_HOURS_CHOICES.some((c) => c.id === selected) &&
    !HOURS_CHOICES.some((c) => c.id === selected);
  return onlyLegacy ? LEGACY_HOURS_CHOICES : HOURS_CHOICES;
}

/** The selection this payload leaves standing.
 *
 *  Only when the answered set LACKS the selection does it move — "month" on a
 *  legacy host snaps to 14d, once, and one visible refetch follows. Returning
 *  the choice unchanged in every other case is what keeps a refetch from
 *  arriving with a new selection and asking for another: no ping-pong. */
export function snapped(
  report: ReportPayload | null | undefined,
  selected: HoursChoice,
): HoursChoice {
  const options = choicesFor(report, selected);
  if (options.some((c) => c.id === selected)) return selected;
  return options === HOURS_CHOICES ? DEFAULT_HOURS_CHOICE : LEGACY_DEFAULT_HOURS_CHOICE;
}

/** choice → the `window=` the board call carries.
 *
 *  `now` is a parameter, not a call to `new Date()` inside, so the year
 *  boundary is testable: in January the previous month is December of the
 *  PREVIOUS year, and a naive `month - 1` writes `2026-00`. */
export function windowFor(choice: HoursChoice, now: Date = new Date()): string {
  if (choice === "last") return lastMonth(now);
  // the `Nd` spellings, "month" and "total" are already the server's own words
  return choice;
}

/** The previous calendar month in the BROWSER's own zone, as `YYYY-MM`. */
export function lastMonth(now: Date): string {
  const zeroBased = now.getMonth(); // 0 = January
  const year = zeroBased === 0 ? now.getFullYear() - 1 : now.getFullYear();
  const month = zeroBased === 0 ? 12 : zeroBased; // 1-based, one behind
  return `${year}-${String(month).padStart(2, "0")}`;
}
