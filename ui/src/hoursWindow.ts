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

export type HoursChoice = "7d" | "month" | "last" | "total";

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

/** choice → the `window=` the board call carries.
 *
 *  `now` is a parameter, not a call to `new Date()` inside, so the year
 *  boundary is testable: in January the previous month is December of the
 *  PREVIOUS year, and a naive `month - 1` writes `2026-00`. */
export function windowFor(choice: HoursChoice, now: Date = new Date()): string {
  if (choice === "last") return lastMonth(now);
  return choice; // "7d", "month" and "total" are already the server's spellings
}

/** The previous calendar month in the BROWSER's own zone, as `YYYY-MM`. */
export function lastMonth(now: Date): string {
  const zeroBased = now.getMonth(); // 0 = January
  const year = zeroBased === 0 ? now.getFullYear() - 1 : now.getFullYear();
  const month = zeroBased === 0 ? 12 : zeroBased; // 1-based, one behind
  return `${year}-${String(month).padStart(2, "0")}`;
}
