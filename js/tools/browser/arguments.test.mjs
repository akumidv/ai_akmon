import { test } from "node:test";
import assert from "node:assert/strict";

import { helpText, parseInvocation, UsageError, VERBS } from "./arguments.mjs";

test("every verb parses, with the options it takes", () => {
  assert.deepEqual(parseInvocation(["status", "--json"]).options.json, true);
  const start = parseInvocation(["start", "--url", "https://example.org", "--headless"]);
  assert.equal(start.verb, "start");
  assert.equal(start.options.url, "https://example.org");
  assert.equal(start.options.headless, true);
  assert.deepEqual(
    [start.options.json, start.options.yes, start.options.release, start.options.endpoint, start.options.page],
    [false, false, false, null, null],
  );
  assert.equal(parseInvocation(["restart", "--url", "u"]).options.url, "u");
  assert.equal(parseInvocation(["install", "--yes"]).options.yes, true);
  for (const verb of ["stop", "init"]) {
    assert.equal(parseInvocation([verb]).verb, verb);
  }
});

test("attach takes one endpoint and detach takes --release", () => {
  const attach = parseInvocation(["attach", "test-results/akmon-browser-endpoint.json"]);
  assert.equal(attach.verb, "attach");
  assert.equal(attach.options.endpoint, "test-results/akmon-browser-endpoint.json");
  assert.equal(parseInvocation(["attach", "9333"]).options.endpoint, "9333");
  assert.equal(parseInvocation(["detach"]).options.release, false);
  assert.equal(parseInvocation(["detach", "--release"]).options.release, true);
  assert.throws(
    () => parseInvocation(["attach"]),
    (error) => error instanceof UsageError && /endpoint/.test(error.message),
  );
  assert.throws(
    () => parseInvocation(["attach", "9333", "9334"]),
    (error) => error instanceof UsageError && /unrecognized arguments: 9334/.test(error.message),
  );
  assert.throws(() => parseInvocation(["attach", "9333", "--release"]), UsageError);
  assert.throws(() => parseInvocation(["detach", "9333"]), UsageError);
});

test("no verb, -h and --help print the help; the help lists every verb", () => {
  for (const argv of [[], ["-h"], ["--help"]]) {
    assert.equal(parseInvocation(argv).verb, "help");
  }
  for (const verb of VERBS) {
    assert.ok(helpText().includes(`  ${verb}`));
  }
});

test("an unknown verb, a foreign option and an extra argument are usage errors", () => {
  assert.throws(
    () => parseInvocation(["open"]),
    (error) => error instanceof UsageError && /invalid choice: 'open'/.test(error.message),
  );
  assert.throws(() => parseInvocation(["stop", "--json"]), UsageError);
  assert.throws(
    () => parseInvocation(["start", "extra"]),
    (error) => error instanceof UsageError && /unrecognized arguments: extra/.test(error.message),
  );
  assert.throws(() => parseInvocation(["start", "--url"]), UsageError);
});

test("the inspection verbs parse their options, numbers and the eval expression", () => {
  const pages = parseInvocation(["pages", "--all", "--json"]);
  assert.deepEqual([pages.verb, pages.options.all, pages.options.json], ["pages", true, true]);
  const snapshot = parseInvocation(["snapshot", "--page", "2", "--max-nodes", "50", "--text"]);
  assert.deepEqual([snapshot.options.page, snapshot.options.maxNodes, snapshot.options.text], ["2", 50, true]);
  const shot = parseInvocation(["screenshot", "--viewport", "phone", "--scheme", "dark", "--full", "--out", "a.png"]);
  assert.deepEqual(
    [shot.options.viewport, shot.options.scheme, shot.options.full, shot.options.out],
    ["phone", "dark", true, "a.png"],
  );
  const evaluated = parseInvocation(["eval", "document.title", "--json"]);
  assert.deepEqual([evaluated.options.expression, evaluated.options.json], ["document.title", true]);
  const logs = parseInvocation(["logs", "--until", "ready|done", "--timeout", "2.5"]);
  assert.deepEqual([logs.options.until, logs.options.timeout], ["ready|done", 2.5]);
  const net = parseInvocation(["net", "--for", "3", "--failed", "--bodies", "--max-body", "100", "--out", "n/"]);
  assert.deepEqual(
    [net.options.forSeconds, net.options.failed, net.options.bodies, net.options.maxBody, net.options.out],
    [3, true, true, 100, "n/"],
  );
  assert.equal(parseInvocation(["net"]).options.forSeconds, null);
});

test("an inspection option that is not valid is a usage error naming it", () => {
  /** @type {[string[], RegExp][]} */
  const bad = [
    [["snapshot", "--max-nodes", "0"], /--max-nodes must be a positive whole number/],
    [["snapshot", "--max-nodes", "1.5"], /--max-nodes/],
    [["net", "--for", "abc"], /--for must be a positive number/],
    [["logs", "--timeout", "-3"], /logs:/],
    [["screenshot", "--scheme", "sepia"], /--scheme must be light or dark/],
    [["logs", "--until", "("], /--until "\(" is not a regular expression/],
    [["eval"], /expression/],
    [["eval", "a", "b"], /quote the expression/],
    [["pages", "--viewport", "x"], /pages:/],
    [["screenshot", "--json"], /screenshot:/],
  ];
  for (const [argv, pattern] of bad) {
    assert.throws(
      () => parseInvocation(argv),
      (error) => error instanceof UsageError && pattern.test(error.message),
      String(argv),
    );
  }
});

test("the help says that eval reads, that net reloads nothing and that secrets are redacted", () => {
  const help = helpText();
  assert.match(help, /it never changes the page/);
  assert.match(help, /reloads nothing/);
  assert.match(help, /redacted at capture/);
});

test("eval, logs and net take --target and --ext; eval also takes --world", () => {
  const evaluated = parseInvocation(["eval", "1", "--target", "sw", "--ext", "Bench"]);
  assert.deepEqual([evaluated.options.target, evaluated.options.ext, evaluated.options.world], ["sw", "Bench", null]);
  const isolated = parseInvocation(["eval", "1", "--world", "isolated", "--ext", "abc", "--page", "2"]);
  assert.deepEqual([isolated.options.world, isolated.options.page, isolated.options.target], ["isolated", "2", null]);
  assert.equal(parseInvocation(["eval", "1", "--target", "page", "--page", "1"]).options.page, "1");
  assert.equal(parseInvocation(["logs", "--target", "popup"]).options.target, "popup");
  assert.equal(parseInvocation(["net", "--target", "A1B2C3D4", "--ext", "x"]).options.ext, "x");
  assert.equal(parseInvocation(["pages"]).options.target, null);
});

test("a target, a world or an extension option that does not fit is a usage error naming it", () => {
  /** @type {[string[], RegExp][]} */
  const bad = [
    [["eval", "1", "--target", "a b"], /--target must be page, sw, popup or a target id/],
    [["eval", "1", "--world", "main"], /--world must be page or isolated/],
    [["eval", "1", "--world", "isolated", "--target", "sw"], /--world isolated .* no meaning with --target sw/],
    [["logs", "--target", "sw", "--page", "1"], /--page picks a page; it has no meaning with --target sw/],
    [["logs", "--world", "page"], /logs:/],
    [["snapshot", "--target", "sw"], /snapshot:/],
  ];
  for (const [argv, pattern] of bad) {
    assert.throws(
      () => parseInvocation(argv),
      (error) => error instanceof UsageError && pattern.test(error.message),
      String(argv),
    );
  }
});

test("selectors takes one registry file, a page and --json", () => {
  const parsed = parseInvocation(["selectors", "ext/selectors.json", "--page", "tradingview", "--json"]);
  assert.deepEqual(
    [parsed.verb, parsed.options.file, parsed.options.page, parsed.options.json],
    ["selectors", "ext/selectors.json", "tradingview", true],
  );
  assert.throws(
    () => parseInvocation(["selectors"]),
    (error) => error instanceof UsageError && /file/.test(error.message),
  );
  assert.throws(() => parseInvocation(["selectors", "a.json", "b.json"]), /unrecognized arguments: b\.json/);
});

test("ext takes list, reload or action with an optional id or name", () => {
  const list = parseInvocation(["ext", "list", "--json"]);
  assert.deepEqual([list.options.sub, list.options.ext, list.options.json], ["list", null, true]);
  const reload = parseInvocation(["ext", "reload", "Bench"]);
  assert.deepEqual([reload.options.sub, reload.options.ext], ["reload", "Bench"]);
  assert.equal(parseInvocation(["ext", "reload"]).options.ext, null);
  const action = parseInvocation(["ext", "action", "abc", "--page", "shop"]);
  assert.deepEqual([action.options.sub, action.options.ext, action.options.page], ["action", "abc", "shop"]);
  /** @type {[string[], RegExp][]} */
  const bad = [
    [["ext"], /required: list\|reload\|action/],
    [["ext", "remove"], /unknown sub-command 'remove' \(choose from 'list', 'reload', 'action'\)/],
    [["ext", "list", "Bench"], /ext list: unrecognized arguments: Bench/],
    [["ext", "reload", "--page", "1"], /--page is only for `ext action`/],
    [["ext", "action", "--json"], /--json is not offered/],
    [["ext", "reload", "a", "b"], /unrecognized arguments: b/],
  ];
  for (const [argv, pattern] of bad) {
    assert.throws(
      () => parseInvocation(argv),
      (error) => error instanceof UsageError && pattern.test(error.message),
      String(argv),
    );
  }
});

test("install takes --for-extensions, and the help names the extension bench", () => {
  assert.equal(parseInvocation(["install", "--for-extensions"]).options.forExtensions, true);
  assert.equal(parseInvocation(["install"]).options.forExtensions, false);
  const help = helpText();
  assert.match(help, /--target is page .*sw .*popup/s);
  assert.match(help, /\[page\] \[extension\] \[sw\]/);
});

test("record takes a sub-command, and each sub-command only the options it has", () => {
  const start = parseInvocation(["record", "start", "--name", "bug", "--all-pages", "--bodies", "--max-body", "2048"]);
  assert.equal(start.verb, "record");
  assert.deepEqual(
    [start.options.sub, start.options.name, start.options.allPages, start.options.bodies, start.options.maxBody],
    ["start", "bug", true, true, 2048],
  );
  assert.equal(parseInvocation(["record", "start", "--page", "docs"]).options.page, "docs");
  assert.equal(parseInvocation(["record", "stop"]).options.sub, "stop");
  assert.equal(parseInvocation(["record", "status", "--json"]).options.json, true);
  assert.equal(parseInvocation(["record", "list"]).options.sub, "list");
  assert.equal(parseInvocation(["record", "delete", "bug"]).options.name, "bug");
  const defaults = parseInvocation(["record", "start"]).options;
  assert.deepEqual(
    [defaults.name, defaults.allPages, defaults.bodies, defaults.maxBody, defaults.around],
    [null, false, false, null, null],
  );
});

test("record mark takes the rest of the line as its note, quoted or not", () => {
  assert.equal(parseInvocation(["record", "mark", "checkout fails now"]).options.note, "checkout fails now");
  assert.equal(parseInvocation(["record", "mark", "checkout", "fails", "now"]).options.note, "checkout fails now");
  assert.equal(parseInvocation(["record", "mark"]).options.note, "");
});

test("record export takes a name, --around, --window, --json, or --test playwright with --out", () => {
  const timeline = parseInvocation(["record", "export", "bug", "--around", "last", "--window", "30", "--json"]);
  assert.deepEqual(
    [
      timeline.options.name,
      timeline.options.around,
      timeline.options.window,
      timeline.options.json,
      timeline.options.testRunner,
    ],
    ["bug", "last", 30, true, null],
  );
  assert.equal(parseInvocation(["record", "export", "--around", "2"]).options.around, "2");
  const draft = parseInvocation(["record", "export", "--test", "playwright", "--out", "x.spec.ts"]);
  assert.deepEqual(
    [draft.options.name, draft.options.testRunner, draft.options.out],
    [null, "playwright", "x.spec.ts"],
  );
});

test("a record usage that is wrong is a usage error naming the option or the argument", () => {
  const usage = (/** @type {string[]} */ argv, /** @type {RegExp} */ pattern) =>
    assert.throws(
      () => parseInvocation(["record", ...argv]),
      (error) => error instanceof UsageError && pattern.test(error.message),
      argv.join(" "),
    );
  usage([], /the following arguments are required: start\|mark/);
  usage(["begin"], /unknown sub-command 'begin'/);
  usage(["stop", "--json"], /--json is not an option of record stop/);
  usage(["mark", "--bodies"], /--bodies is not an option of record mark/);
  usage(["start", "--around", "1"], /--around is not an option of record start/);
  usage(["start", "--page", "1", "--all-pages"], /exclude each other/);
  usage(["start", "extra"], /unrecognized arguments: extra/);
  usage(["delete"], /required: name/);
  usage(["delete", "a", "b"], /unrecognized arguments: b/);
  usage(["export", "a", "b"], /unrecognized arguments: b/);
  usage(["export", "--around", "0"], /--around must be a mark's number from 1, or last/);
  usage(["export", "--around", "first"], /--around must be/);
  usage(["export", "--window", "5"], /--window needs --around/);
  usage(["export", "--window", "0", "--around", "1"], /--window must be a positive number/);
  usage(["export", "--test", "cypress"], /--test must be playwright/);
  usage(["export", "--test", "playwright", "--around", "1"], /--test writes a draft test/);
  usage(["export", "--test", "playwright", "--json"], /--test writes a draft test/);
  usage(["export", "--out", "x"], /--out is for --test/);
});

test("the help names record and the rule that a typed value is never recorded", () => {
  assert.match(helpText(), /record\s+record a session the user drives/);
  assert.match(helpText(), /a typed value is never recorded/);
});
