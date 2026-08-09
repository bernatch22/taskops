
import { depth, escape, push } from "../../src/components/shared/overlayStack";
import type { Check, Fixture, Harness } from "./section";

export async function run(_fixture: Fixture, check: Check, _h: Harness): Promise<void> {
  /* ── Escape closes the top-most overlay only ────────────────────────── */

  const closed: string[] = [];
  const popDrawer = push(() => closed.push("drawer"));
  const popConfirm = push(() => closed.push("confirm"));
  check("two overlays are stacked", depth() === 2);
  check("escape closes the top-most", escape() && JSON.stringify(closed) === '["confirm"]');
  popConfirm();
  check("escape then closes the one below", escape() && closed.length === 2);
  popDrawer();
  check("an empty stack swallows nothing", escape() === false && depth() === 0);
}
