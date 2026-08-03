/* Stands in for `Overlay` while rendering to a string.
 *
 * The real one PORTALS to `document.body`, for the reason its own docstring gives — an ancestor with
 * `backdrop-filter` becomes the containing block for `position: fixed`, which put a "full screen"
 * scrim inside a 40-pixel header. The server renderer supports no portals at all, and what these
 * renders check is the CONTENT of a modal, so the portal is the one thing faked here. */
export function Overlay({ children }: { label: string; onClose: () => void; children: unknown }) {
  return <div className="ctx-back"><div className="ctx-modal">{children as never}</div></div>;
}
