import { test } from "node:test";
import assert from "node:assert/strict";

import {
  describeTarget,
  eventsAround,
  locatorOf,
  markAt,
  marksOf,
  playwrightDraft,
  sortedEvents,
  summaryLines,
  timelineLines,
} from "./record-export.mjs";
import { summaryOf } from "./record-store.mjs";
import { BrowserError } from "./settings.mjs";

/**
 * A descriptor with the given parts.
 * @param {Partial<import("./record-events.mjs").Descriptor>} parts
 * @returns {import("./record-events.mjs").Descriptor}
 */
function target(parts) {
  return {
    tag: "",
    role: "",
    name: "",
    testid: "",
    id: "",
    nameAttr: "",
    label: "",
    text: "",
    css: "",
    type: "",
    sensitive: false,
    ...parts,
  };
}

const EMAIL = target({
  tag: "input",
  role: "textbox",
  name: "Email",
  label: "Email",
  nameAttr: "email",
  type: "email",
  css: "#email",
});

/** @type {import("./record-events.mjs").RecordedEvent[]} */
const SESSION = [
  { t: 0, kind: "page", page: "p1", url: "https://shop.example/login", title: "Login" },
  { t: 20, kind: "start", name: "rec-1" },
  { t: 1000, kind: "click", page: "p1", target: EMAIL },
  { t: 1500, kind: "input", page: "p1", target: EMAIL, length: 3 },
  { t: 2100, kind: "input", page: "p1", target: EMAIL, length: 15 },
  { t: 2200, kind: "change", page: "p1", target: EMAIL, length: 15 },
  {
    t: 3000,
    kind: "input",
    page: "p1",
    target: target({
      tag: "input",
      label: "Password",
      name: "Password",
      nameAttr: "password",
      type: "password",
      css: "#pw",
      sensitive: true,
    }),
    length: null,
  },
  {
    t: 4000,
    kind: "click",
    page: "p1",
    target: target({ tag: "button", role: "button", name: "Sign in", text: "Sign in", css: "form > button" }),
  },
  { t: 4100, kind: "submit", page: "p1", method: "post", target: target({ tag: "form", id: "login", css: "#login" }) },
  {
    t: 4120,
    kind: "net",
    page: "p1",
    method: "POST",
    url: "https://shop.example/api/login?x=1",
    status: 200,
    type: "XHR",
    ms: 90,
    failure: null,
  },
  {
    t: 4130,
    kind: "net",
    page: "p1",
    method: "GET",
    url: "https://cdn.other.example/a.js",
    status: 200,
    type: "Script",
    ms: 10,
    failure: null,
  },
  { t: 4400, kind: "navigation", page: "p1", url: "https://shop.example/account" },
  {
    t: 6000,
    kind: "click",
    page: "p1",
    target: target({ tag: "a", role: "link", name: "Orders", text: "Orders", css: "nav > a:nth-of-type(2)" }),
  },
  {
    t: 6050,
    kind: "net",
    page: "p1",
    method: "GET",
    url: "https://shop.example/api/orders",
    status: 502,
    type: "Fetch",
    ms: 300,
    failure: null,
  },
  { t: 6400, kind: "exception", page: "p1", text: "TypeError: orders is undefined" },
  { t: 7000, kind: "mark", note: "orders list is empty" },
  { t: 8000, kind: "click", page: "p1", target: target({ tag: "div", css: "main > div:nth-of-type(3)" }) },
  {
    t: 9000,
    kind: "change",
    page: "p1",
    target: target({
      tag: "input",
      role: "checkbox",
      type: "checkbox",
      label: "Remember me",
      name: "Remember me",
      nameAttr: "rm",
      css: "#rm",
    }),
    checked: true,
    length: null,
  },
  {
    t: 9500,
    kind: "click",
    page: "p1",
    target: target({ tag: "button", testid: "export-btn", role: "button", name: "Export", text: "Export" }),
  },
  {
    t: 10000,
    kind: "keydown",
    page: "p1",
    key: "Enter",
    target: target({ tag: "input", role: "searchbox", label: "Search", name: "Search", type: "search", css: "#q" }),
  },
  { t: 10100, kind: "page", page: "p2", url: "https://pop.example/" },
];

test("events are read in time order, a request written when it ends sorting by when it began", () => {
  const shuffled = [SESSION[9], SESSION[2], SESSION[0]];
  assert.deepEqual(
    sortedEvents(shuffled).map((event) => event.t),
    [0, 1000, 4120],
  );
});

test("marks are numbered from 1 in time order; --around names one by number or last, and a bad one is refused", () => {
  const events = [...SESSION, { t: 9800, kind: "mark", note: "second" }];
  assert.deepEqual(
    marksOf(events).map((mark) => mark["note"]),
    ["orders list is empty", "second"],
  );
  assert.equal(markAt(events, "1").mark["note"], "orders list is empty");
  assert.deepEqual([markAt(events, "last").number, markAt(events, "last").mark.t], [2, 9800]);
  for (const bad of ["0", "3", "x", "1.5"]) {
    assert.throws(
      () => markAt(events, bad),
      (error) => error instanceof BrowserError && /numbered from 1/.test(error.message),
      bad,
    );
  }
  assert.throws(() => markAt(SESSION.slice(0, 5), "last"), /has no mark/);
});

test("the stretch around a mark is the events within the window on both sides", () => {
  assert.deepEqual(
    eventsAround(SESSION, { t: 7000, windowSeconds: 1.5 }).map((event) => event.t),
    [6000, 6050, 6400, 7000, 8000],
  );
  assert.equal(eventsAround(SESSION, { t: 7000, windowSeconds: 15 }).length, SESSION.length);
});

test("the timeline is one line per event with relative time and kind, a request under the action that caused it", () => {
  const lines = timelineLines(SESSION, { name: "rec-1", around: null });
  assert.equal(lines[0], "recording rec-1: 21 events, 10.100s");
  assert.deepEqual(lines.slice(1, 9), [
    '   +0.000s  page        p1   https://shop.example/login "Login"',
    "   +0.020s  start            recording rec-1 began",
    '   +1.000s  click       p1   textbox "Email"',
    '   +1.500s  input       p1   textbox "Email" (3 chars)',
    '   +2.100s  input       p1   textbox "Email" (15 chars)',
    '   +2.200s  change      p1   textbox "Email" (15 chars)',
    '   +3.000s  input       p1   input "Password" (sensitive)',
    '   +4.000s  click       p1   button "Sign in"',
  ]);
  const at = lines.findIndex((line) => line.includes("api/login"));
  assert.match(lines[at - 1], /submit\s+p1\s+form #login/);
  assert.match(lines[at + 1], /^\s+after submit form #login \(\+4\.100s, 30 ms before\)$/);
  const failed = lines.findIndex((line) => line.includes("api/orders"));
  assert.match(lines[failed], /! GET 502 300 ms https:\/\/shop\.example\/api\/orders \[Fetch\]/);
  assert.match(lines[failed - 1], /click\s+p1\s+link "Orders"/);
  assert.match(lines.find((line) => line.includes("MARK")) ?? "", /\+7\.000s {2}MARK {13}orders list is empty/);
});

test("--around shows the window before and after the mark and says so; the action before the window still explains a request", () => {
  const lines = timelineLines(SESSION, { name: "rec-1", around: { ...markAt(SESSION, "last"), windowSeconds: 1.5 } });
  assert.equal(lines[0], "recording rec-1: around mark #1 at +7.000s (1.5 s each side), 5 of 21 events");
  assert.equal(lines.length, 6);
  assert.match(lines[1], /click\s+p1\s+link "Orders"/);
  assert.match(lines[5], /click\s+p1\s+div/);
  const narrow = timelineLines(SESSION, { name: "rec-1", around: { ...markAt(SESSION, "last"), windowSeconds: 0.5 } });
  assert.equal(narrow.length, 2);
  assert.match(narrow[1], /MARK/);
});

test("a failed request is flagged, a console line carries its level, and a page column appears only with several pages", () => {
  const one = timelineLines(
    SESSION.filter((event) => event.page !== "p2"),
    { name: "x", around: null },
  );
  assert.equal(one[1].includes("p1"), false);
  const failure = timelineLines(
    [
      {
        t: 5,
        kind: "net",
        method: "GET",
        url: "https://a.example/",
        status: null,
        failure: "net::ERR_FAILED",
        type: "Fetch",
        ms: null,
      },
    ],
    { name: "x", around: null },
  );
  assert.match(failure[1], /! GET FAILED net::ERR_FAILED https:\/\/a\.example\//);
  const console = timelineLines([{ t: 5, kind: "console", level: "error", text: "boom\n  at x" }], {
    name: "x",
    around: null,
  });
  assert.match(console[1], /console\s+error boom at x/);
});

test("a target is described by role and name, a test id or an id, and a secret says so", () => {
  assert.equal(
    describeTarget(target({ tag: "button", role: "button", name: "Pay", testid: "pay" })),
    'button "Pay" [testid=pay]',
  );
  assert.equal(describeTarget(target({ tag: "div", id: "x" })), "div #x");
  assert.equal(
    describeTarget(target({ tag: "input", label: "Password", sensitive: true })),
    'input "Password" (sensitive)',
  );
});

test("the summary counts what a recording holds", () => {
  const text = SESSION.map((event) => JSON.stringify(event)).join("\n");
  const lines = summaryLines("rec-1", summaryOf(text));
  assert.equal(lines[0], "recording rec-1: 21 events over 10.1 s");
  assert.match(lines[1], /click 5, /);
  assert.equal(lines[2], "  marks: 1; failed requests: 1; exceptions: 1");
});

test("locators come in order: test id, role and name, label, short text, else a CSS path that says to replace it", () => {
  assert.deepEqual(locatorOf(target({ testid: "pay", role: "button", name: "Pay" })), {
    code: "page.getByTestId('pay')",
    todo: false,
  });
  assert.deepEqual(locatorOf(target({ role: "button", name: "Pay" })), {
    code: "page.getByRole('button', { name: 'Pay' })",
    todo: false,
  });
  assert.deepEqual(locatorOf(target({ label: "Password", type: "password" })), {
    code: "page.getByLabel('Password')",
    todo: false,
  });
  assert.deepEqual(locatorOf(target({ text: "It's here" })), { code: "page.getByText('It\\'s here')", todo: false });
  assert.deepEqual(locatorOf(target({ css: "main > div" })), { code: "page.locator('main > div')", todo: true });
});

test("the draft Playwright test for a representative session", () => {
  const expected = `// A draft Playwright test generated by \`akmon tool browser record export --test playwright\` from the recording 'rec-1'.
// It is a starting point for the project's own runner, not a finished test: check each locator, fill in the
// values marked TODO and write the assertions the TODO lines ask for. A typed value was never recorded, and a
// secret field reads its value from the environment.
// Events of the other pages recorded (p2) are left out: the draft follows p1.
import { expect, test } from '@playwright/test';

test('rec-1', async ({ page }) => {
  await page.goto('https://shop.example/login');
  await page.getByRole('textbox', { name: 'Email' }).fill('TODO_VALUE'); // typed 15 characters
  await page.getByLabel('Password').fill(process.env.PASSWORD ?? ''); // sensitive field: its value was never recorded; supply it from the environment
  const response1 = page.waitForResponse((response) => response.url().includes('/api/login') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Sign in' }).click();
  expect((await response1).status()).toBe(200);
  await expect(page).toHaveURL(new RegExp('/account'));
  // TODO: expect(...) what the page should show after this navigation
  const response2 = page.waitForResponse((response) => response.url().includes('/api/orders') && response.request().method() === 'GET');
  await page.getByRole('link', { name: 'Orders' }).click();
  expect((await response2).status()).toBe(502);
  // MARK: orders list is empty
  // TODO: expect(...) what should hold at this moment
  await page.locator('main > div:nth-of-type(3)').click(); // TODO: a stable locator
  await page.getByRole('checkbox', { name: 'Remember me' }).check();
  await page.getByTestId('export-btn').click();
  await page.getByRole('searchbox', { name: 'Search' }).press('Enter');
});
`;
  assert.equal(playwrightDraft(SESSION, "rec-1"), expected);
});

test("the draft never carries a typed value, a secret field reads the environment, and a name with a quote is escaped", () => {
  const events = /** @type {import("./record-events.mjs").RecordedEvent[]} */ ([
    { t: 0, kind: "page", page: "p1", url: "https://x.example/?token=[redacted]" },
    {
      t: 10,
      kind: "input",
      page: "p1",
      target: target({
        tag: "input",
        nameAttr: "api-token",
        label: "API token",
        type: "text",
        sensitive: true,
        css: "#t",
      }),
      length: null,
    },
    {
      t: 20,
      kind: "input",
      page: "p1",
      target: target({ tag: "select", label: "Size", nameAttr: "size", css: "#s" }),
      length: 2,
    },
    { t: 30, kind: "mark", note: "it's broken\nbadly" },
  ]);
  const draft = playwrightDraft(events, "it's a test");
  assert.match(draft, /test\('it\\'s a test'/);
  assert.match(draft, /fill\(process\.env\.API_TOKEN \?\? ''\)/);
  assert.match(draft, /selectOption\('TODO_OPTION'\)/);
  assert.match(draft, /TODO: a secret in the URL was redacted at capture/);
  assert.match(draft, /\/\/ MARK: it's broken badly/);
});
