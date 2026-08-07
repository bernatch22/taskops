/* Who owns Escape right now. A stack, and nothing about the DOM.
 *
 * v1 closed on Escape by reaching into the page — `document.querySelector('.drawer')`
 * and closing whatever it found (teardown hack #17). That answers "is something
 * open" with "is something on screen", two different questions the moment a
 * second overlay exists: a confirm over a drawer closed the drawer underneath
 * itself, and the class name was a dependency no component declared.
 *
 * Here ownership is mount order, which is the only order the user can see. Every
 * mounted overlay pushes its own close handler and pops it on unmount; `escape()`
 * calls the LAST one and nothing else.
 *
 * It is a plain module and not React state on purpose — pushing would re-render
 * every open overlay whenever one opens — and it holds no listener, so it runs
 * under node with no DOM at all. `Overlay.tsx` is the only thing that knows what
 * a keyboard is. */

type Close = () => void;

const stack: Close[] = [];

/** Take the top slot. The returned function frees it — call it exactly once, from
 *  the effect's own cleanup. Removal is by identity, not by depth: an overlay that
 *  unmounts out of order frees ITS slot and leaves the rest of the pile standing. */
export function push(close: Close): () => void {
  stack.push(close);
  return () => {
    const at = stack.lastIndexOf(close);
    if (at >= 0) stack.splice(at, 1);
  };
}

/** Close the top-most overlay. Returns whether there was one — the caller only
 *  swallows the key event when somebody actually handled it. */
export function escape(): boolean {
  const top = stack[stack.length - 1];
  if (!top) return false;
  top();
  return true;
}

/** How deep the pile is. For the harness, and for `Overlay` to know whether it is
 *  the one that must attach the listener. */
export function depth(): number {
  return stack.length;
}
