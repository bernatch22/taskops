/* The VISIBLE half: the stack that draws the model's answers, and the tile that
 * lights up beside it.
 *
 * `sections/comment-toasts-model.tsx` pins what a toast IS — which comments are
 * news, what a preview says, how deep the stack goes, when one leaves. Nothing
 * of that is repeated here. This section renders, and asks only the questions a
 * render can answer: is the avatar there, whose title is on the line, is the
 * trimmed text the trimmed one and the expanded one whole, does the open
 * affordance carry the task id it will hand to `openCard`, and does a commented
 * tile differ from a resting one.
 *
 * No timers and no jsdom: the stack is handed a pre-built `Toast[]` with its
 * `shown` stamps written by hand, exactly as the component receives one from
 * the hook. The hook's own arithmetic — which tiles are lit at a given instant —
 * is a pure function (`useToasts.ts::pulsing`) and is called, not awaited. */
import { renderToStaticMarkup } from "react-dom/server";

import { CardTile } from "../../src/components/board/CardTile";
import { prefersReducedMotion } from "../../src/components/board/flip";
import { ToastStack } from "../../src/components/toasts/ToastStack";
import { PULSE_MS, pulsing } from "../../src/components/toasts/useToasts";
import { TRIM_LIMIT, trim, type Toast } from "../../src/components/toasts/model";
import { hueOf } from "../../src/components/shared/Avatar";
import type { BoardRow } from "../../src/types";
import type { Check, Fixture, Harness } from "./section";

/** Long enough that `trim` has something to cut — the whole point of the two
 *  states this section separates. */
const LONG =
  /* Plain words on purpose: `renderToStaticMarkup` escapes an apostrophe to
     `&#x27;`, so a quote in here would make every text assertion below compare
     the source against the entity and fail for a reason that has nothing to do
     with the stack. */
  "the merge left the seams model untouched and the stack now draws straight " +
  "from it, which is what makes this sentence longer than the preview limit " +
  "and therefore worth expanding to read whole";

function toast(id: string, task: string, over: Partial<Toast> = {}): Toast {
  return {
    id,
    task,
    cardTitle: `the card called ${task}`,
    actor: "agent:berna/w4",
    text: LONG,
    ts: 1_760_000_000,
    shown: 100_000,
    expanded: false,
    ...over,
  };
}

export async function run(fixture: Fixture, check: Check, h: Harness): Promise<void> {
  const stack: readonly Toast[] = [
    toast("e9", "tk-newest"),
    toast("e8", "tk-older", { expanded: true }),
  ];
  const markup = renderToStaticMarkup(
    <ToastStack toasts={stack} onExpand={() => {}} onDismiss={() => {}} onOpen={() => {}} />,
  );

  /* ── 1. What a toast SAYS: who, which card, and a preview ─────────────── */
  const first = h.slice(markup, 'data-task="tk-newest"', 'data-task="tk-older"');
  check(
    "a toast carries the author's own disc — the board's Avatar, not a second one",
    first.includes('data-testid="avatar"') &&
      first.includes('data-actor="agent:berna/w4"') &&
      first.includes(`${hueOf("agent:berna/w4")} var(--disc-s)`),
    first,
  );
  check(
    "the card's TITLE is the headline, not its id — the id is the affordance below",
    first.includes("the card called tk-newest"),
    first,
  );
  check(
    "an unexpanded toast shows the trimmed text, cut and marked as cut",
    first.includes(trim(LONG)) && !first.includes(LONG) && trim(LONG).endsWith("…"),
    trim(LONG),
  );
  check(
    "the preview is the MODEL's cut, not a second limit invented in the component",
    trim(LONG).length <= TRIM_LIMIT + 1,
  );

  /* Newest first, and that is the ORDER OF THE MARKUP: the stack sits on the
     bottom-right corner and its first child is its top edge. */
  check(
    "the newest toast is drawn above the older one",
    markup.indexOf('data-task="tk-newest"') < markup.indexOf('data-task="tk-older"'),
  );

  /* ── 2. Expanded in place: the WHOLE message, no second lookup ────────── */
  const second = markup.slice(markup.indexOf('data-task="tk-older"'));
  check(
    "an expanded toast shows the message whole",
    second.includes(LONG),
    second,
  );
  check(
    "expansion is a state the markup admits to, so the pin is not a guess",
    second.includes('data-expanded="1"') && first.includes('data-expanded="0"'),
  );

  /* ── 3. The second affordance carries the id it will open ─────────────── */
  const opener = h.slice(markup, 'data-testid="toast-open"', "</button>");
  check(
    "the open affordance names the task it hands to openCard",
    opener.includes('data-task="tk-newest"') && opener.includes("tk-newest"),
    opener,
  );
  check(
    "it is a SEPARATE target from the body — reading a message must not move the reader",
    markup.includes('data-testid="toast-body"') &&
      markup.includes('data-testid="toast-dismiss"'),
  );

  /* Nothing at all when there is nothing to say: an empty fixed box must not
     sit over the board's corner for the whole session. */
  check(
    "an empty stack renders nothing",
    renderToStaticMarkup(
      <ToastStack toasts={[]} onExpand={() => {}} onDismiss={() => {}} onOpen={() => {}} />,
    ) === "",
  );

  /* ── 4. Reduced motion drops the MOTION and keeps the content ─────────── */
  const still = renderToStaticMarkup(
    <ToastStack
      toasts={stack}
      onExpand={() => {}}
      onDismiss={() => {}}
      onOpen={() => {}}
      reduced={true}
    />,
  );
  check(
    "with less motion asked for, no transition is written onto a toast",
    !still.includes("transition"),
    still,
  );
  check(
    "…and every word is still there — the preference is about motion, never content",
    still.includes("the card called tk-newest") && still.includes(LONG),
  );
  /* The guard itself is the board's own, consulted live by its own query — the
     same one FLIP asks (`components/board/flip.ts`). */
  const asked: string[] = [];
  check(
    "the stack's preference comes from the board's one motion query, answered live",
    prefersReducedMotion({ matchMedia: (q) => (asked.push(q), { matches: true }) }) &&
      asked[0] === "(prefers-reduced-motion: reduce)",
    JSON.stringify(asked),
  );

  /* ── 5. Which tiles are lit — pure, and it decays by arithmetic ───────── */
  const lit = pulsing(stack, 100_000 + PULSE_MS - 1);
  check(
    "a card commented on inside the window is lit",
    lit.has("tk-newest") && lit.has("tk-older"),
    JSON.stringify([...lit]),
  );
  check(
    "and it goes dark on its own, with nothing stored and nothing cleared",
    pulsing(stack, 100_000 + PULSE_MS).size === 0,
  );
  check(
    "a toast the reader EXPANDED pins the message, never the tile",
    !pulsing([toast("e7", "tk-read", { expanded: true })], 100_000 + PULSE_MS).has("tk-read"),
  );

  /* ── 6. …and the tile draws that difference, without inventing a badge ── */
  const row = fixture.board.groups.take[0] as BoardRow | undefined;
  if (row) {
    const rest = renderToStaticMarkup(<CardTile row={row} onOpen={() => {}} />);
    const pulsed = renderToStaticMarkup(
      <CardTile row={row} recentComment={true} onOpen={() => {}} />,
    );
    check(
      "a commented tile lights with the board's own accent wash, never a literal colour",
      pulsed.includes("var(--accent-soft)") && !rest.includes("box-shadow"),
      pulsed,
    );
    check(
      "the highlight is a GLOW: the tile's border is not touched, hover or pulse",
      pulsed.includes("border-color:var(--hair)") && !pulsed.includes("border-color:var(--accent"),
      pulsed,
    );
    check(
      "no badge and no counter comes with it — this board has no read-receipts",
      pulsed.replace(rest, "").indexOf("unread") === -1 &&
        pulsed.length - rest.length < 60,
      `${pulsed.length - rest.length} characters of difference`,
    );
    check(
      "a tile nobody commented on is byte-identical to the one before this feature",
      renderToStaticMarkup(<CardTile row={row} recentComment={false} onOpen={() => {}} />) === rest,
    );
  } else {
    check("fixture carries a ready row to pulse", false, "cannot reach the tile highlight");
  }
}
