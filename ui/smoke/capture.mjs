/* Capture a live board's payload into `fixture.json`. See README: the fixture is real output from a
 * real server, because a hand-written one only ever asserts what its author already believed. */
const base = process.env.BOARD_URL ?? "http://127.0.0.1:2201";
const get = async (path) => (await fetch(base + path)).json();
process.stdout.write(JSON.stringify({
  context: await get("/api/context"),
  board: await get("/api/board"),
}, null, 1) + "\n");
