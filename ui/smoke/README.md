# smoke — the UI, rendered to a string, against a REAL payload

`npm run smoke` starts nothing and clicks nothing. It renders the components with `react-dom/server`
against JSON this repo's own server produced, and asserts what came out.

It exists because of one bug and its shape is that bug: picking a milestone did not change the cards
on the board. `tsc` was clean, the payload was right, the server was right — the wiring between the
picker and the columns was not, and nothing in the suite looked at it. A browser would have caught
it in a second and a browser is not something a test run can have.

So this checks the two things a payload cannot: that every component renders at all, and that
CHOOSING one thing changes what is drawn.

`fixture.json` is a captured `/api/context` + `/api/board` from a board with two active chapters,
one planned, six cards across two of them, and two workers in different chapters. Re-capture it with:

    taskops ui --port 2201 &
    node smoke/capture.mjs > smoke/fixture.json
