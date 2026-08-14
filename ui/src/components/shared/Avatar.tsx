/* WHO is on this thing — one actor, one disc of initials, in that actor's own
 * colour.
 *
 * There were two of these before this file: the header's presence row
 * (`chrome/AvatarStack.tsx`) and the little disc at the foot of a card tile
 * (`board/CardTile.tsx`). They agreed on the glyphs — `format.ts::initials`,
 * the TAIL of the actor string, up to three of them — and on nothing else, and
 * the disagreement was visible: the header gave a person one of four token
 * tones by hash, the tile coloured by ROLE (accent when somebody holds the
 * lease, grey otherwise), so the same agent was purple in one place and grey in
 * the other. Two discs of one actor that do not match are two actors to the eye.
 *
 * So the disc is one component with two independent axes, and both are on
 * screen at once:
 *
 *   WHO   → the hue, derived from the actor string (never assigned: there is
 *           nowhere to store an assignment, and two renders of one board must
 *           give one person one colour).
 *   HOW   → `live`, the emphasis. A live disc is full strength; a merely
 *           assigned one is ghosted back. That is the tile's old distinction
 *           kept, moved off the channel that says who.
 *
 * FOUR TONES WAS NOT ENOUGH. The palette the header used holds four token
 * pairs, and this project's own board runs `agent:berna/w1` … `w8` in one wave:
 * eight agents into four tones is a guaranteed collision, and a colour that
 * collides is not identity, it is decoration. A derived hue has 24 steps here.
 *
 * And it is still not a literal colour — the rule tokens.css states. The hue is
 * a NUMBER this file computes; the saturation, the lightness and the wash's
 * alpha are `--disc-*`, declared once per theme, which is what makes 24 hues
 * read as one family and makes the disc follow the theme switch like everything
 * else. */
import { initials } from "../../format";

/** How many hues the wheel is cut into. 24 × 15° is far enough apart that two
 *  neighbours are told apart at 23px, and coarse enough that a hue is stable
 *  under the eye rather than a continuum of near-identical purples. */
export const HUES = 24;

/** The actor's own hue, in degrees.
 *
 *  The hash is the header row's — `hash * 31 + charCode`, kept unsigned — for
 *  the plain reason that it was already here and already deterministic. What
 *  changed is only what it indexes: a wheel instead of a four-entry table.
 *
 *  PURE and exported: a hue is far easier to assert on than a rendered disc,
 *  and "the same actor gets the same colour" is the whole promise this makes. */
export function hueOf(actor: string): number {
  let hash = 0;
  for (const ch of actor) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return (hash % HUES) * (360 / HUES);
}

/** The two colours of one actor's disc, as CSS. `hsl()`'s space-separated form
 *  with a `/` alpha is what lets the hue be a computed number while s/l stay
 *  `var(--disc-*)` — a comma-separated `hsl()` cannot take a custom property
 *  per channel. */
export function discColors(actor: string): {
  background: string;
  color: string;
} {
  const h = hueOf(actor);
  return {
    background: `hsl(${h} var(--disc-s) var(--disc-l) / var(--disc-bg-a))`,
    color: `hsl(${h} var(--disc-s) var(--disc-fg-l))`,
  };
}

export interface AvatarProps {
  /** the FULL actor string — `agent:berna/w2`, never the short name. It is what
   *  the hue is derived from and what the tooltip says; shortening it first
   *  would give `w2` under two different devs one colour. */
  actor: string;
  /** px. The header's row is 28, a tile's corner is 23. */
  size?: number;
  /** Is this actor actually RUNNING it, or merely the name on the card?
   *
   *  On a board row that is `holder` vs `assignee` (`verbs/pulse.py::_rows.row`:
   *  `holder` is the live lease, `assignee` is who it was handed to — a stalled
   *  card has the second and not the first, and that difference IS the stalled
   *  group). Ghosted rather than recoloured, so the identity survives. */
  live?: boolean;
  /** what the tooltip says, when the bare actor is not the whole story */
  title?: string;
  /** a count on the disc's shoulder — the header's swarm badge, nothing else */
  children?: React.ReactNode;
  /** the presence row overlaps its discs; a tile's single one does not */
  style?: React.CSSProperties;
}

export function Avatar({
  actor,
  size = 23,
  live = true,
  title,
  children,
  style,
}: AvatarProps): React.JSX.Element {
  return (
    <div
      title={title ?? actor}
      data-testid="avatar"
      data-actor={actor}
      data-live={live ? "1" : "0"}
      style={{
        ...discColors(actor),
        width: `${size}px`,
        height: `${size}px`,
        borderRadius: "50%",
        flex: "none",
        display: "grid",
        placeItems: "center",
        fontSize: `${Math.round(size * 0.41 * 10) / 10}px`,
        fontWeight: 500,
        letterSpacing: "-0.02em",
        /* `initials()` answers in the actor's own case on purpose (format.ts):
           the disc is where the upcasing decision belongs, with the rest of
           this disc's typography. */
        textTransform: "uppercase",
        position: "relative",
        /* The ghost. 0.45 and not a grey: a grey disc would be a THIRD colour
           competing with the 24, and the eye reads a faded purple as the same
           agent, quieter — which is exactly what "assigned, not running" is. */
        opacity: live ? 1 : 0.45,
        ...style,
      }}
    >
      {initials(actor)}
      {children}
    </div>
  );
}
