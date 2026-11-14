import { test } from "node:test";
import assert from "node:assert/strict";

import { attachToPage, CdpConnection, CdpError, connect } from "./cdp.mjs";
import { fakeChrome } from "./support.test.mjs";

test("a call carries an id, its params and its session, and resolves with the result", async () => {
  const chrome = fakeChrome({ "Browser.getVersion": () => ({ product: "Chrome/1" }) });
  const connection = new CdpConnection(chrome.transport);
  assert.deepEqual(await connection.send("Browser.getVersion", {}, { timeoutMs: 500 }), { product: "Chrome/1" });
  assert.deepEqual(chrome.calls, [{ method: "Browser.getVersion", params: {} }]);
  connection.close();
});

test("an error answer rejects with the method and the browser's words", async () => {
  const chrome = fakeChrome({
    "Page.navigate": () => {
      throw new Error("Cannot navigate to invalid URL");
    },
  });
  const connection = new CdpConnection(chrome.transport);
  await assert.rejects(
    connection.send("Page.navigate", {}, { timeoutMs: 500 }),
    (error) => error instanceof CdpError && error.message === "Page.navigate: Cannot navigate to invalid URL",
  );
  connection.close();
});

test("a call with no answer times out at the time it was given, and leaves no timer behind", async () => {
  const chrome = fakeChrome({ "Slow.call": () => new Promise(() => {}) });
  const connection = new CdpConnection(chrome.transport);
  await assert.rejects(connection.send("Slow.call", {}, { timeoutMs: 20 }), /Slow\.call: no answer within 20 ms/);
  connection.close();
});

test("events reach the handlers of their session only, until unsubscribed", async () => {
  const chrome = fakeChrome();
  const connection = new CdpConnection(chrome.transport);
  const page = await attachToPage(connection, "T1");
  /** @type {string[]} */
  const seen = [];
  const off = page.on("Runtime.consoleAPICalled", (params) => seen.push(params.type));
  /** @type {string[]} */
  const elsewhere = [];
  connection.on("Runtime.consoleAPICalled", (params) => elsewhere.push(params.type));
  chrome.emit("Runtime.consoleAPICalled", { type: "log" });
  await new Promise((resolve) => setImmediate(resolve));
  off();
  chrome.emit("Runtime.consoleAPICalled", { type: "error" });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(seen, ["log"]);
  assert.deepEqual(elsewhere, []);
  connection.close();
});

test("a page is attached with a flattened session and its calls carry the session id", async () => {
  const chrome = fakeChrome({ "Runtime.evaluate": () => ({ result: { value: 1 } }) });
  const connection = await connect("ws://fake", async () => chrome.transport);
  const page = await attachToPage(connection, "T1");
  await page.send("Runtime.evaluate", { expression: "1" });
  assert.deepEqual(chrome.calls[0], { method: "Target.attachToTarget", params: { targetId: "T1", flatten: true } });
  assert.deepEqual(chrome.calls[1], { method: "Runtime.evaluate", params: { expression: "1" }, sessionId: "S1" });
  connection.close();
});

test("a connection that ends fails the calls still waiting and tells the close handlers", async () => {
  const chrome = fakeChrome({ "Slow.call": () => new Promise(() => {}) });
  const connection = new CdpConnection(chrome.transport);
  let told = 0;
  connection.onClose(() => {
    told += 1;
  });
  const waiting = connection.send("Slow.call", {}, { timeoutMs: 5000 });
  await new Promise((resolve) => setImmediate(resolve));
  chrome.end();
  await assert.rejects(waiting, /the browser closed the connection/);
  assert.equal(told, 1);
  assert.equal(connection.closed, true);
  await assert.rejects(connection.send("X.y"), /connection is closed/);
});
