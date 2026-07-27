/* Who is working right now. The one view that answers "is anything actually happening".
 *
 * A SILENT member is shown, never filtered: an agent that still holds a claim but has gone quiet
 * is exactly the row somebody needs to act on, and hiding it is how a board loses its credibility.
 * The Python projection makes the same choice for the same reason. */

import type { Fleet as FleetData } from "../contracts";
import { Actor, ago } from "./bits";

export function Fleet({ fleet, onOpen }: {
  fleet: FleetData;
  onOpen: (id: string) => void;
}): JSX.Element {
  if (fleet.members.length === 0) {
    return (
      <aside className="fleet">
        <h2>Fleet</h2>
        <p className="dim">No live claims. Nothing is being worked on right now.</p>
      </aside>
    );
  }
  return (
    <aside className="fleet">
      <h2>Fleet <span className="tally">{fleet.members.length}</span></h2>
      <ul>
        {fleet.members.map((member) => (
          <li className={member.alive ? "alive" : "silent"} key={member.session + member.task}>
            <div className="fleet-top">
              <span className={`dot ${member.alive ? "on" : "off"}`} />
              <Actor id={member.actor} />
              <button className="linkish" onClick={() => onOpen(member.task)}>
                {member.task}
              </button>
            </div>
            <div className="fleet-doing">
              {member.doing
                ? <code>{member.doing}</code>
                : <span className="dim">no activity reported — plugin not installed?</span>}
            </div>
            <div className="fleet-foot dim">
              {member.alive ? ago(member.last_seen) : `SILENT since ${ago(member.last_seen)}`}
              {member.branch ? <> · <code>{member.branch}</code></> : null}
            </div>
          </li>
        ))}
      </ul>
    </aside>
  );
}
