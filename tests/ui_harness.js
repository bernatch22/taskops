// A DOM small enough to run the page's script, and strict enough to catch what
// a browser would. No jsdom, no browser: the point is to run the REAL file, so
// a typo in the card panel fails a test instead of showing an empty dialog.
//
// Usage: node tests/ui_harness.js <ui/index.html> <fixture.json>

const fs = require("fs");

const [, , pagePath, fixturePath] = process.argv;
const html = fs.readFileSync(pagePath, "utf8");
const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));

const seen = { opened: false, text: [] };

function node(tag) {
  const self = {
    tag,
    children: [],
    _text: "",
    className: "",
    style: {},
    classList: { add() {}, remove() {} },
    get textContent() {
      return self._text;
    },
    set textContent(value) {
      self._text = String(value);
      self.children = [];
      seen.text.push(String(value));
    },
    set innerHTML(value) {
      self._text = String(value);
      seen.text.push(String(value));
    },
    append(...parts) {
      for (const part of parts) {
        self.children.push(part);
        if (typeof part === "string") seen.text.push(part);
      }
    },
    addEventListener(name, fn) {
      (self.listeners ||= {})[name] = fn;
    },
    click() {
      if (self.listeners && self.listeners.click) return self.listeners.click();
    },
    showModal() {
      seen.opened = true;
    },
    close() {},
    focus() {},
  };
  return self;
}

const registry = {};
globalThis.document = {
  createElement: (tag) => node(tag),
  getElementById: (id) => (registry[id] ||= node("div")),
};
globalThis.location = { pathname: "/facturador/ui/", search: "", protocol: "http:", host: "x" };
globalThis.history = { replaceState() {} };
globalThis.localStorage = {
  store: { "taskops:/facturador": "a-token" },
  getItem(key) {
    return this.store[key] || null;
  },
  setItem(key, value) {
    this.store[key] = value;
  },
};
globalThis.URLSearchParams = class {
  get() {
    return null;
  }
};
globalThis.WebSocket = class {
  addEventListener() {}
};
globalThis.fetch = async (url, options) => {
  const verb = JSON.parse(options.body).verb;
  if (!fixture[verb]) throw new Error(`the page asked for an unknown verb: ${verb}`);
  return { json: async () => ({ ok: true, seq: 1, data: fixture[verb] }) };
};

const script = html.split("<script>")[1].split("</script>")[0];
// Run it, then reach in for the two functions the page's behaviour lives in.
const run = new Function(`${script}\nreturn { draw, open_card };`);
const page = run();

(async () => {
  page.draw(fixture.board);
  const drawn = seen.text.join("\n");
  for (const needed of fixture.expect_board || []) {
    if (!drawn.includes(needed)) throw new Error(`the board never drew: ${needed}`);
  }
  const rows = [];
  for (const group of Object.values(fixture.board.groups)) for (const row of group) rows.push(row);
  if (!rows.length) throw new Error("the fixture has no cards to click");

  // Click every card the board drew — the panel must open for each one.
  for (const row of rows) {
    seen.opened = false;
    seen.text = [];
    await page.open_card(row.id);
    if (!seen.opened) throw new Error(`clicking ${row.id} opened nothing`);
    const text = seen.text.join("\n");
    for (const needed of fixture.expect) {
      if (!text.includes(needed)) throw new Error(`the panel never showed: ${needed}`);
    }
  }
  console.log("ok: drew the board and opened", rows.length, "cards");
})().catch((err) => {
  console.error("FAILED:", err.message);
  process.exit(1);
});
