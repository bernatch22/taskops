/* `useState`, except it survives a reload.
 *
 * A view preference that resets on every refresh is worse than not having the control: the person
 * sets it, the live feed brings a change, they refresh, and it is back — which reads as the toggle
 * not working. localStorage rather than the server because these belong to the reader, not to the
 * repository: two developers on one project have their own answers. */

import { useCallback, useState } from "react";

export function remembered<T>(key: string, fallback: T): [T, (value: T) => void] {
  const [value, setValue] = useState<T>(() => {
    /* Storage is unavailable in a few real browsers (private mode, third-party frames) and a
     * preference is never worth taking the app down for, so both directions swallow. */
    try {
      const found = localStorage.getItem(key);
      return found === null ? fallback : (JSON.parse(found) as T);
    } catch {
      return fallback;
    }
  });

  const remember = useCallback((next: T) => {
    setValue(next);
    try {
      localStorage.setItem(key, JSON.stringify(next));
    } catch { /* the setting is still applied for this session */ }
  }, [key]);

  return [value, remember];
}
