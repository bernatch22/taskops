/* What has been done here — the event log, read as a history rather than as a feed.
 *
 * This is the view that replaced the fleet rail. "Who is free" stopped being a question the day
 * agents became disposable: you make one when you need one. What does not stop being a question is
 * what was already done, by whom, and when — and the answer to that has been in `events.jsonl` from
 * the beginning, with nobody able to look at it outside a terminal.
 *
 * Two panes over ONE fetch: the people, and the timeline. They are the same events counted two ways,
 * so clicking a person filters the timeline instead of loading a different page. */

import { useEffect, useState } from "react";
import { api, ApiFailure } from "../api";
import type { Activity as ActivityData, ActorRoll, Event } from "../contracts";
import { Actor, ago } from "./bits";

const WINDOWS = ["24h", "7d", "30d", "90d"];

export function Activity({ onOpen }: { onOpen: (id: string) => void }): JSX.Element {
  const [since, setSince] = useState("30d");
  const [data, setData] = useState<ActivityData | null>(null);
  const [failed, setFailed] = useState("");
  const [actor, setActor] = useState("");
  const [kind, setKind] = useState("");
  const [text, setText] = useState("");

  useEffect(() => {
    let live = true;
    setData(null);
    api.activity(since)
      .then((found) => { if (live) { setData(found); setFailed(""); } })
      .catch((error: unknown) => {
        if (live) setFailed(error instanceof ApiFailure ? error.message : String(error));
      });
    return () => { live = false; };
  }, [since]);

  const shown = (data?.events ?? []).filter((event) =>
    (!actor || event.actor === actor) &&
    (!kind || event.kind === kind) &&
    (!text || matches(event, data?.titles ?? {}, text.toLowerCase())));

  return (
    <div className="activity">
      <header className="activity-head">
        <h2>Activity</h2>
        <div className="windows">
          {WINDOWS.map((option) => (
            <button key={option} className={option === since ? "on" : ""}
                    onClick={() => setSince(option)}>{option}</button>
          ))}
        </div>
        <input className="filter" value={text} placeholder="Filter this history…"
               onChange={(change) => setText(change.target.value)} />
        {data ? (
          <span className="dim meta-count">
            {shown.length}/{data.events.length}
            {data.truncated ? " · truncated" : ""}
          </span>
        ) : null}
      </header>

      {failed ? <p className="failed">{failed}</p> : null}
      {!data && !failed ? <p className="dim loading">Reading the log…</p> : null}

      {data ? (
        <div className="activity-body">
          <section className="people">
            <h3>Who did it <span className="tally">{data.actors.length}</span></h3>
            {data.actors.length === 0 ? <p className="dim">Nothing in this window.</p> : null}
            <ul>
              {data.actors.map((roll) => (
                <Person key={roll.actor} roll={roll} picked={roll.actor === actor}
                        onPick={() => setActor(roll.actor === actor ? "" : roll.actor)} />
              ))}
            </ul>
          </section>

          <section className="timeline">
            <h3>
              What happened
              {/* The filters are shown as what they ARE — a removable narrowing — because a view
                * that quietly hides most of its rows is a view somebody trusts once. */}
              {actor ? <Chip label={actor} onDrop={() => setActor("")} /> : null}
              {kind ? <Chip label={kind} onDrop={() => setKind("")} /> : null}
            </h3>
            <div className="kinds">
              {data.kinds.map((option) => (
                <button key={option} className={`kind${option === kind ? " on" : ""}`}
                        onClick={() => setKind(option === kind ? "" : option)}>{option}</button>
              ))}
            </div>
            {shown.length === 0
              ? <p className="dim">Nothing matches. The window is {since}.</p>
              : <Timeline events={shown} titles={data.titles} onOpen={onOpen} />}
          </section>
        </div>
      ) : null}
    </div>
  );
}

function Person({ roll, picked, onPick }: {
  roll: ActorRoll;
  picked: boolean;
  onPick: () => void;
}): JSX.Element {
  return (
    <li className={`person${picked ? " on" : ""}`}>
      <button onClick={onPick}>
        <div className="person-top">
          <Actor id={roll.actor} />
          <span className="dim">{ago(roll.last_seen)}</span>
        </div>
        <div className="person-counts">
          <span title="tasks touched">{roll.tasks} tasks</span>
          {roll.done ? <span className="count commits" title="moved to done">✓{roll.done}</span> : null}
          {roll.commits ? <span className="count commits" title="commits">◆{roll.commits}</span> : null}
          {roll.comments ? <span className="dim" title="comments and messages">💬{roll.comments}</span> : null}
        </div>
      </button>
    </li>
  );
}

function Chip({ label, onDrop }: { label: string; onDrop: () => void }): JSX.Element {
  return <button className="chip" onClick={onDrop} title="remove this filter">{label} ✕</button>;
}

/* Grouped by DAY. A flat list of four hundred rows has no shape, and the day is the unit people
 * remember things in ("that was Tuesday"), which no relative age can give them. */
function Timeline({ events, titles, onOpen }: {
  events: Event[];
  titles: Record<string, string>;
  onOpen: (id: string) => void;
}): JSX.Element {
  const days: [string, Event[]][] = [];
  for (const event of events) {
    const day = dayOf(event.ts);
    const last = days[days.length - 1];
    if (last && last[0] === day) last[1].push(event);
    else days.push([day, [event]]);
  }
  return (
    <>
      {days.map(([day, ofDay]) => (
        <div className="day" key={day}>
          <h4>{day} <span className="tally">{ofDay.length}</span></h4>
          <ol className="events">
            {ofDay.map((event) => (
              <li className={`event event-${event.kind}`} key={event.id}>
                <span className="when dim">{clock(event.ts)}</span>
                <span className={`kind-dot kind-${event.kind}`} title={event.kind} />
                <div className="event-body">
                  <div className="event-top">
                    <Actor id={event.actor} />
                    <button className="linkish" onClick={() => onOpen(event.task)}>{event.task}</button>
                    <span className="dim ellipsis">{titles[event.task] ?? ""}</span>
                  </div>
                  <p className="event-said">{said(event)}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      ))}
    </>
  );
}

/* What an event SAID, per kind, read defensively: `body` is open on the Python side precisely so a
 * newer taskops can write kinds this build has never heard of, and the fallback has to be a line
 * rather than a blank — an unreadable row is still evidence something happened. */
function said(event: Event): string {
  const body = event.body;
  const str = (key: string): string => String(body[key] ?? "");
  switch (event.kind) {
    case "commit": return str("subject") || str("sha").slice(0, 12);
    case "comment": case "message": return str("text");
    /* `done` and `released` are their own kinds, not a `status` with a payload — which is what lets
     * the roll-up count closes without reading bodies. Both still carry from/to. */
    case "status": case "done": return `${str("from")} → ${str("to")}`;
    case "released": return `handed back${str("from") ? ` from ${str("from")}` : ""}`;
    case "created": return str("title");
    case "claimed": return str("branch") ? `on ${str("branch")}` : "claimed";
    case "handoff": return `to ${str("assigned_to")}`;
    case "blocked": return `waiting on ${str("on")}`;
    case "branch": return str("branch") || str("name");
    case "activity": return str("summary");
    default: {
      const first = Object.entries(body).find(([, value]) => typeof value === "string" && value);
      return first ? String(first[1]) : event.kind;
    }
  }
}

function matches(event: Event, titles: Record<string, string>, needle: string): boolean {
  const hay = [event.actor, event.task, event.kind, said(event), titles[event.task] ?? ""];
  return hay.some((part) => part.toLowerCase().includes(needle));
}

function dayOf(ts: number): string {
  const when = new Date(ts * 1000);
  const midnight = new Date();
  midnight.setHours(0, 0, 0, 0);
  const days = Math.floor((midnight.getTime() / 1000 - ts) / 86400) + 1;
  if (ts >= midnight.getTime() / 1000) return "Today";
  if (days === 1) return "Yesterday";
  return when.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

function clock(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}
