/* The one modal shell: a backdrop, a bounded panel, Escape, and a PORTAL out to `document.body`.
 *
 * The portal is not tidiness, it is the fix for a bug that had already shipped. `position: fixed`
 * is only relative to the viewport while no ancestor has taken that job — and `backdrop-filter`,
 * `filter` and `transform` all take it, silently. The profile modal was mounted inside
 * `<header class="top">`, which blurs its own backdrop, so `inset: 0` resolved against the HEADER:
 * a 40-pixel-tall "full screen" overlay, the panel squeezed into it as a flex item of the header,
 * and the whole thing reading as transparent. Nothing in the CSS was wrong.
 *
 * A portal makes an overlay's position independent of wherever its trigger happens to live, which
 * is the only arrangement that cannot break again when somebody moves a button. It also means the
 * two modals share one implementation of the three things every overlay gets wrong: Escape, a
 * backdrop click that closes, and an inside click that does NOT — the last one is only noticed
 * when somebody loses a text selection to it.
 */

import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";

export function Overlay({ label, onClose, children }: {
  label: string;
  onClose: () => void;
  children: ReactNode;
}): JSX.Element {
  /* Escape belongs to whatever is on TOP. A card drawer opens above these — routinely from one,
   * since a profile lists the cards somebody touched — so with both open, Escape is the drawer's
   * and closing the modal underneath it would leave the card floating over nothing. */
  useEffect(() => {
    const key = (e: KeyboardEvent): void => {
      if (e.key === "Escape" && !document.querySelector(".drawer")) onClose();
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose]);

  return createPortal(
    <div className="ctx-back" onClick={onClose} role="presentation">
      <div className="ctx-modal" onClick={(e) => e.stopPropagation()} role="dialog"
           aria-modal="true" aria-label={label}>
        {children}
      </div>
    </div>,
    document.body,
  );
}
