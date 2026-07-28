/* The narration a person is watching, folded out of the frames on the socket.
 *
 * A pure reducer and not a hook, because the interesting part is the folding: four kinds of
 * frame, one piece of state, and the rules for what happens when a second report starts
 * narrating while the first is still on screen. That is testable as a function and unreadable
 * as an effect.
 *
 * There is deliberately NO recovery here. The frames are ephemeral — nothing on the server
 * stores them — so a browser that reconnects has missed whatever went by, and this state simply
 * stops growing. The report FILE is the durable copy, and it is refetched when the narration
 * ends, which is what closes any gap. */

import type { WireMessage } from "./contracts";

export interface Narration {
  label: string;
  /* The prose so far, exactly as the model has written it: markdown, rendered live. */
  text: string;
  /* `2/4` while a multi-pass reading is running, empty for a single one. A whole-project
   * dossier is read in several passes over several minutes, and a progress line is the
   * difference between "it is working" and "it hung". */
  pass: string;
  state: "narrating" | "done" | "failed";
  error: string;
}

export function reduce(was: Narration | null, message: WireMessage): Narration | null {
  /* A frame for a DIFFERENT report starts over rather than appending. Two narrations can run
   * at once (different labels are different files), and interleaving their prose into one
   * buffer would produce a paragraph neither of them wrote. */
  const base: Narration = was && was.label === message.label
    ? was
    : { label: message.label, text: "", pass: "", state: "narrating", error: "" };

  switch (message.kind) {
    case "narration.delta":
      return { ...base, text: base.text + message.text, state: "narrating" };
    case "narration.pass":
      return { ...base, pass: message.text, state: "narrating" };
    case "narration.done":
      return { ...base, state: "done" };
    case "narration.failed":
      return { ...base, state: "failed", error: message.text };
    /* An unknown kind is DROPPED, never guessed at: a newer taskops on the other end of this
     * socket will send kinds this bundle has never heard of. */
    default:
      return was;
  }
}
