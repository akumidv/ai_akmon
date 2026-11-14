import { test } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";

import { listenerSource, recorderListener } from "./record-listener.mjs";

/**
 * A fake element: just what the listener reads.
 * @param {string} tag
 * @param {Record<string, string>} [attrs]
 * @param {{text?: string, value?: string, checked?: boolean, children?: any[], labels?: any[], editable?: boolean}} [more]
 * @returns {any}
 */
function el(tag, attrs = {}, more = {}) {
  const given = { children: [], text: "", value: "", checked: false, labels: [], editable: false, ...more };
  /** @type {any} */
  const node = {
    tagName: tag.toUpperCase(),
    parentElement: null,
    children: given.children,
    textContent: given.text,
    innerText: given.text,
    value: given.value,
    checked: given.checked,
    labels: given.labels,
    isContentEditable: given.editable,
    getAttribute: (/** @type {string} */ name) => (Object.hasOwn(attrs, name) ? attrs[name] : null),
  };
  for (const child of node.children) {
    child.parentElement = node;
  }
  return node;
}

/**
 * A fake window with a document that keeps its listeners, timers that run when told, and a binding that collects
 * the payloads.
 * @returns {{win: any, sent: any[], texts: string[], fire: (name: string, event: object) => void, tick: () => void, listeners: () => number}}
 */
function fakeWindow() {
  /** @type {Map<string, Set<(event: any) => void>>} */
  const handlers = new Map();
  /** @type {any[]} */
  const sent = [];
  /** @type {string[]} */
  const texts = [];
  /** @type {{id: number, run: () => void}[]} */
  let timers = [];
  let next = 1;
  const win = {
    document: {
      addEventListener: (/** @type {string} */ name, /** @type {any} */ fn) => {
        handlers.set(name, (handlers.get(name) ?? new Set()).add(fn));
      },
      removeEventListener: (/** @type {string} */ name, /** @type {any} */ fn) => handlers.get(name)?.delete(fn),
    },
    setTimeout: (/** @type {() => void} */ run) => {
      timers.push({ id: next, run });
      return next++;
    },
    clearTimeout: (/** @type {number} */ id) => {
      timers = timers.filter((timer) => timer.id !== id);
    },
    __rec: (/** @type {string} */ text) => {
      texts.push(text);
      sent.push(JSON.parse(text));
    },
  };
  return {
    win,
    sent,
    texts,
    fire: (name, event) => handlers.get(name)?.forEach((fn) => fn(event)),
    tick: () => {
      const due = timers;
      timers = [];
      due.forEach((timer) => timer.run());
    },
    listeners: () => [...handlers.values()].reduce((sum, set) => sum + set.size, 0),
  };
}

const CONFIG = { binding: "__rec", keys: ["password", "token", "api_key", "ssn"], flag: "__flag", debounceMs: 500 };

/** @returns {ReturnType<typeof fakeWindow>} */
function installed() {
  const page = fakeWindow();
  recorderListener(page.win, CONFIG);
  return page;
}

test("a click is reported with where it happened: role, name, test id, id and a CSS path, never a value", () => {
  const page = installed();
  const label = el("span", {}, { text: "Sign in" });
  const button = el("button", { "data-testid": "login-submit", id: "go" }, { text: "Sign in", children: [label] });
  const first = el("div", {}, { children: [el("p")] });
  const second = el("div", {}, { children: [button] });
  el("form", { id: "login" }, { children: [first, second] });
  page.fire("click", { target: label, isTrusted: true });
  assert.equal(page.sent.length, 1);
  assert.deepEqual(page.sent[0], {
    kind: "click",
    target: {
      tag: "button",
      role: "button",
      name: "Sign in",
      testid: "login-submit",
      id: "go",
      nameAttr: "",
      label: "",
      text: "Sign in",
      css: "#go",
      type: "",
      sensitive: false,
    },
  });
});

test("the CSS path climbs to an id, numbers repeated siblings and skips classes", () => {
  const page = installed();
  const target = el("a", { href: "/x", class: "btn btn-primary" }, { text: "Docs" });
  const list = el(
    "ul",
    {},
    { children: [el("li", {}, { children: [el("a", { href: "/y" })] }), el("li", {}, { children: [target] })] },
  );
  el("nav", { id: "main" }, { children: [list] });
  page.fire("click", { target, isTrusted: true });
  assert.equal(page.sent[0].target.css, "#main > ul > li:nth-of-type(2) > a");
  assert.equal(page.sent[0].target.role, "link");
  assert.equal(page.sent[0].target.name, "Docs");
});

test("a text snippet is at most 60 characters and a click on a form control carries none", () => {
  const page = installed();
  const long = el("button", {}, { text: `${"word ".repeat(30)}end` });
  page.fire("click", { target: long, isTrusted: true });
  assert.equal(page.sent[0].target.text.length, 60);
  const input = el("input", { type: "text", name: "city" }, { value: "Berlin" });
  page.fire("click", { target: input, isTrusted: true });
  assert.equal(page.sent[1].target.text, "");
  assert.equal(page.texts[1].includes("Berlin"), false);
});

test("typing is reported as a debounced input with its length and never its value", () => {
  const page = installed();
  const label = el("label", {}, { text: "Email" });
  const field = el("input", { type: "email", name: "email", id: "email" }, { labels: [label] });
  for (const value of ["a", "an", "ann@example.org"]) {
    field.value = value;
    page.fire("input", { target: field });
  }
  assert.equal(page.sent.length, 0);
  page.tick();
  assert.equal(page.sent.length, 1);
  assert.deepEqual(
    { kind: page.sent[0].kind, length: page.sent[0].length, sensitive: page.sent[0].target.sensitive },
    { kind: "input", length: 15, sensitive: false },
  );
  assert.equal(page.sent[0].target.label, "Email");
  assert.equal(page.sent[0].target.role, "textbox");
  assert.equal(page.sent[0].target.name, "Email");
  field.value = "ann@example.org";
  page.fire("change", { target: field });
  assert.equal(page.sent[1].kind, "change");
  assert.equal(
    page.texts.some((text) => text.includes("ann@example.org")),
    false,
  );
});

test("a pending input is flushed before the next action, so the order is the user's", () => {
  const page = installed();
  const field = el("input", { type: "text", name: "q" }, { value: "boots" });
  const button = el("button", {}, { text: "Search" });
  page.fire("input", { target: field });
  page.fire("click", { target: button, isTrusted: true });
  assert.deepEqual(
    page.sent.map((event) => event.kind),
    ["input", "click"],
  );
});

test("a secret field is marked sensitive and reports no length: a password, a one-time code, a name on the redact list", () => {
  const cases = [
    el("input", { type: "password", name: "pw" }, { value: "hunter2" }),
    el("input", { type: "text", name: "otp", autocomplete: "one-time-code" }, { value: "123456" }),
    el("input", { type: "text", autocomplete: "current-password" }, { value: "hunter2" }),
    el("input", { type: "text", name: "csrf_token" }, { value: "abc123" }),
    el("input", { type: "text", id: "ssn" }, { value: "078-05-1120" }),
    el("input", { type: "text", name: "k" }, { value: "sk-live", labels: [el("label", {}, { text: "API key" })] }),
  ];
  for (const field of cases) {
    const page = installed();
    page.fire("input", { target: field });
    page.tick();
    page.fire("change", { target: field });
    assert.equal(page.sent.length, 2);
    for (const event of page.sent) {
      assert.equal(event.target.sensitive, true, JSON.stringify(event));
      assert.equal(event.length, null);
    }
    assert.equal(page.texts.join("").includes(field.value), false);
  }
});

test("a checkbox change reports its state; a radio and a select report a change too", () => {
  const page = installed();
  const box = el("input", { type: "checkbox", name: "terms" }, { checked: true });
  page.fire("change", { target: box });
  assert.equal(page.sent[0].checked, true);
  assert.equal(page.sent[0].target.role, "checkbox");
  const select = el("select", { name: "size" }, { value: "xl" });
  page.fire("change", { target: select });
  assert.equal(page.sent[1].target.role, "combobox");
});

test("only Enter, Escape and Tab are reported as keys; the keys of a text are not", () => {
  const page = installed();
  const field = el("input", { type: "text", name: "q" });
  for (const key of ["a", "Enter", "Shift", "Escape", "Tab", "1"]) {
    page.fire("keydown", { target: field, key });
  }
  assert.deepEqual(
    page.sent.map((event) => event.key),
    ["Enter", "Escape", "Tab"],
  );
});

test("a submit reports the form, not its action URL", () => {
  const page = installed();
  const form = el("form", { id: "login", method: "post", action: "https://x.example/?token=SECRET" });
  page.fire("submit", { target: form });
  assert.equal(page.sent[0].kind, "submit");
  assert.equal(page.sent[0].method, "post");
  assert.equal(page.sent[0].target.id, "login");
  assert.equal(page.texts[0].includes("SECRET"), false);
});

test("a click a script made is not the user's and is not reported", () => {
  const page = installed();
  page.fire("click", { target: el("button"), isTrusted: false });
  assert.equal(page.sent.length, 0);
});

test("installing twice changes nothing, and dispose removes every listener and the flag", () => {
  const page = fakeWindow();
  recorderListener(page.win, CONFIG);
  const held = page.listeners();
  recorderListener(page.win, CONFIG);
  assert.equal(page.listeners(), held);
  assert.ok(page.win.__flag);
  page.win.__flag.dispose();
  assert.equal(page.listeners(), 0);
  assert.equal(page.win.__flag, undefined);
});

test("the injected source installs the same listener when it is run as text", () => {
  const page = fakeWindow();
  const source = listenerSource(CONFIG);
  vm.runInNewContext(source, { window: page.win });
  page.fire("click", { target: el("button", {}, { text: "Pay" }), isTrusted: true });
  assert.equal(page.sent[0].target.name, "Pay");
});
