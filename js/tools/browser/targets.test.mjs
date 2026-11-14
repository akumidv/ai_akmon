import { test } from "node:test";
import assert from "node:assert/strict";

import { CdpError } from "./cdp.mjs";
import { REDACTED } from "./redact.mjs";
import { fetchTargets, pageTabs, pageTargets, redactedTargets, selectPage } from "./targets.mjs";

const TARGETS = [
  { id: "W1", type: "service_worker", title: "sw", url: "https://shop.example/sw.js" },
  { id: "T1", type: "page", title: "Shop", url: "https://shop.example/cart" },
  { id: "T2", type: "page", title: "Docs", url: "https://docs.example/start" },
];

test("the default page is the first page target, not the first target", () => {
  assert.equal(selectPage(TARGETS, null).id, "T1");
  assert.deepEqual(
    pageTargets(TARGETS).map((target) => target.id),
    ["T1", "T2"],
  );
});

test("--page takes an index among the pages, a target id or part of a URL", () => {
  assert.equal(selectPage(TARGETS, "1").id, "T2");
  assert.equal(selectPage(TARGETS, "T2").id, "T2");
  assert.equal(selectPage(TARGETS, "docs.example").id, "T2");
  assert.equal(selectPage(TARGETS, "shop").id, "T1");
});

test("a selector that matches no page, and a browser with no page, are one-line failures", () => {
  assert.throws(
    () => selectPage(TARGETS, "9"),
    (error) =>
      error instanceof CdpError && /no page matches --page "9"; pages are 0: https:\/\/shop/.test(error.message),
  );
  assert.throws(() => selectPage(TARGETS, "sw.js"), /no page matches/);
  assert.throws(() => selectPage([], null), /no open page/);
});

test("targets are read from /json/list and a non-list answer is refused", async () => {
  /** @type {string[]} */
  const seen = [];
  const targets = await fetchTargets("http://127.0.0.1:9", async (url) => {
    seen.push(url);
    return [{ id: "A", type: "page", title: "t", url: "u", extra: 1 }];
  });
  assert.deepEqual(seen, ["http://127.0.0.1:9/json/list"]);
  assert.deepEqual(targets, [{ id: "A", type: "page", title: "t", url: "u" }]);
  await assert.rejects(
    fetchTargets("http://127.0.0.1:9", async () => ({})),
    CdpError,
  );
});

const CALLBACK = "https://app.example/cb#access_token=SECRET&state=s";

test("every URL a verb prints is redacted: targets, tabs and the list in a failed --page", () => {
  const targets = [{ id: "T", type: "page", title: "App", url: CALLBACK }, ...TARGETS];
  assert.equal(redactedTargets(targets, [])[0].url, `https://app.example/cb#access_token=${REDACTED}&state=s`);
  assert.equal(targets[0].url, CALLBACK, "the listing itself is not changed");
  assert.deepEqual(pageTabs(targets, []), [
    { title: "App", url: `https://app.example/cb#access_token=${REDACTED}&state=s` },
    { title: "Shop", url: "https://shop.example/cart" },
    { title: "Docs", url: "https://docs.example/start" },
  ]);
  assert.throws(
    () => selectPage(targets, "nope"),
    (error) => error instanceof CdpError && !error.message.includes("SECRET") && error.message.includes(REDACTED),
  );
});
