import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { posix } from "node:path";

import { parseInvocation } from "./arguments.mjs";
import { buildContext } from "./context.mjs";
import { recorderState, recordCommand } from "./record.mjs";
import { readEvents } from "./record-events.mjs";
import { eventsPath, readState, recordingDir } from "./record-store.mjs";
import { BrowserError } from "./settings.mjs";
import { fakeHost, tempProject } from "./support.test.mjs";

/**
 * A context over a throwaway project, and a machine whose recorder is a stand-in that writes the events the
 * real one would: `start` (or the `error` in `failWith`), and `stop` when it is signalled.
 * @param {{record?: string, failWith?: string, dies?: boolean, stubborn?: boolean, side?: "here" | "windows"}} [given]
 */
function setup(given = {}) {
  const project = tempProject(given.record ?? "");
  /** @type {string[]} */
  const said = [];
  const ctx = buildContext(project.root, { env: {}, host: fakeHost(), say: (line) => said.push(line) });
  const clock = { t: 5_000_000 };
  /** @type {Set<number>} */
  const running = new Set();
  /** @type {{pid: number, signal: string}[]} */
  const signals = [];
  let nextPid = 5000;
  /** @type {import("./record.mjs").RecordHow} */
  const how = {
    locate: async () => ({ browserURL: "http://127.0.0.1:9582", port: 9582, mode: "own", side: given.side ?? "here" }),
    launch: (configPath, logPath) => {
      const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
      const file = eventsPath(config.dir);
      const line = given.failWith
        ? { t: 1, kind: "error", text: given.failWith }
        : { t: 1, kind: "start", name: config.name, pages: ["p1"] };
      if (given.dies) {
        fs.writeFileSync(logPath, "node: some crash\nrecorder.mjs: cannot start\n");
      } else {
        fs.writeFileSync(file, `${JSON.stringify(line)}\n`);
        if (!given.failWith) {
          running.add(nextPid);
        }
      }
      return nextPid++;
    },
    alive: (pid) => running.has(pid),
    signal: (pid, signal) => {
      signals.push({ pid, signal });
      if (signal === "SIGKILL" || (signal === "SIGTERM" && !given.stubborn)) {
        running.delete(pid);
      }
    },
    now: () => clock.t,
    sleep: async () => {
      clock.t += 100;
    },
  };
  const run = (/** @type {string[]} */ ...argv) =>
    recordCommand(ctx, parseInvocation(["record", ...argv]).options, how);
  return {
    ctx,
    said,
    how,
    clock,
    running,
    signals,
    run,
    root: project.root,
    dir: ctx.project.browserDir,
    dispose: project.dispose,
  };
}

/** @param {string} dir @param {string} name */
const eventsOf = (dir, name) => readEvents(fs.readFileSync(eventsPath(recordingDir(dir, name)), "utf8")).events;

test("start launches the recorder, returns once it records, names it rec-1 and says how to mark and stop", async () => {
  const t = setup();
  try {
    assert.equal(await t.run("start"), 0);
    assert.match(t.said[0], /^recording rec-1 started \(recorder pid 5000\)/);
    assert.ok(t.said.some((line) => /record mark/.test(line)));
    assert.ok(t.said.some((line) => /record stop/.test(line)));
    const state = readState(t.dir);
    assert.deepEqual([state?.name, state?.pid, state?.startedAtMs, state?.side], ["rec-1", 5000, 5_000_000, "here"]);
    const config = JSON.parse(fs.readFileSync(posix.join(recordingDir(t.dir, "rec-1"), "recorder.json"), "utf8"));
    assert.deepEqual(config.request, {
      browserURL: "http://127.0.0.1:9582",
      page: null,
      allPages: false,
      bodies: false,
      maxBody: 65_536,
      redact: config.request.redact,
      binding: "__akmonRecord",
    });
    assert.ok(config.request.redact.includes("password"));
    assert.equal(await t.run("start").catch((error) => error.message.includes("rec-1 is running")), true);
  } finally {
    t.dispose();
  }
});

test("[browser.record] sets the defaults and a flag overrides them for one recording; --page beats all_pages", async () => {
  const t = setup({ record: "[browser.record]\nbodies = true\nmax_body = 4096\nall_pages = true\n" });
  try {
    await t.run("start", "--name", "settings");
    const read = () =>
      JSON.parse(fs.readFileSync(posix.join(recordingDir(t.dir, "settings"), "recorder.json"), "utf8")).request;
    assert.deepEqual([read().bodies, read().maxBody, read().allPages, read().page], [true, 4096, true, null]);
    await t.run("stop");
    await t.run("start", "--name", "flags", "--max-body", "100", "--page", "2");
    const flags = JSON.parse(
      fs.readFileSync(posix.join(recordingDir(t.dir, "flags"), "recorder.json"), "utf8"),
    ).request;
    assert.deepEqual([flags.bodies, flags.maxBody, flags.allPages, flags.page], [true, 100, false, "2"]);
  } finally {
    t.dispose();
  }
});

test("the side Chrome is reached from goes to the recorder: windows under WSL", async () => {
  const t = setup({ side: "windows" });
  try {
    await t.run("start");
    const config = JSON.parse(fs.readFileSync(posix.join(recordingDir(t.dir, "rec-1"), "recorder.json"), "utf8"));
    assert.equal(config.side, "windows");
    assert.equal(readState(t.dir)?.side, "windows");
  } finally {
    t.dispose();
  }
});

test("a second start is refused while one runs; once its recorder is gone the stale state is cleared and the next gets the next name", async () => {
  const t = setup();
  try {
    await t.run("start");
    await assert.rejects(
      t.run("start", "--name", "other"),
      (error) =>
        error instanceof BrowserError &&
        /recording rec-1 is running \(recorder pid 5000\); one at a time/.test(error.message),
    );
    assert.equal(fs.existsSync(recordingDir(t.dir, "other")), false);
    t.running.clear();
    t.said.length = 0;
    await t.run("start");
    assert.match(t.said[0], /recording rec-1 had ended without being stopped; its events are kept/);
    assert.equal(readState(t.dir)?.name, "rec-2");
    assert.ok(fs.existsSync(recordingDir(t.dir, "rec-1")));
  } finally {
    t.dispose();
  }
});

test("a name that exists, or that is not a folder name, is refused before anything starts", async () => {
  const t = setup();
  try {
    await t.run("start", "--name", "bug");
    await t.run("stop");
    await assert.rejects(t.run("start", "--name", "bug"), /a recording named bug exists/);
    await assert.rejects(t.run("start", "--name", "../x"), /is not a recording name/);
  } finally {
    t.dispose();
  }
});

test("a recorder that cannot begin leaves nothing behind and says why in its own words", async () => {
  const failing = setup({ failWith: "the browser has no open page; open one in the window, then run the verb again" });
  try {
    await assert.rejects(failing.run("start"), /no open page/);
    assert.equal(readState(failing.dir), null);
    assert.equal(fs.existsSync(recordingDir(failing.dir, "rec-1")), false);
    assert.deepEqual(failing.signals, [], "a recorder that is gone is not signalled");
  } finally {
    failing.dispose();
  }
  const dying = setup({ dies: true });
  try {
    await assert.rejects(dying.run("start"), /exited before it began recording: recorder\.mjs: cannot start/);
    assert.equal(readState(dying.dir), null);
  } finally {
    dying.dispose();
  }
});

/**
 * A recorder that writes `start` only after `after` polls (never with `null`), and whose process the fake
 * can or cannot verify.
 * @param {ReturnType<typeof setup>} t
 * @param {{after: number | null, verifiable: boolean}} given
 */
function slowRecorder(t, given) {
  let polls = 0;
  let folder = "";
  t.how.launch = (configPath) => {
    folder = JSON.parse(fs.readFileSync(configPath, "utf8")).dir;
    if (given.verifiable) {
      t.running.add(7000);
    }
    return 7000;
  };
  t.how.unverifiable = (pid) => !given.verifiable && pid === 7000;
  t.how.sleep = async () => {
    t.clock.t += 1000;
    polls += 1;
    if (given.after !== null && polls === given.after) {
      fs.writeFileSync(
        eventsPath(folder),
        `${JSON.stringify({ t: 1, kind: "start", name: "rec-1", pages: ["p1"] })}\n`,
      );
    }
  };
}

test("where the recorder's process cannot be verified (Windows), start waits for its start event and never signals", async () => {
  const t = setup();
  try {
    slowRecorder(t, { after: 5, verifiable: false });
    assert.equal(await t.run("start"), 0);
    assert.deepEqual(t.signals, []);
    assert.equal(readState(t.dir)?.pid, 7000);
  } finally {
    t.dispose();
  }
});

test("an unverifiable recorder that never starts is reported at the timeout, not signalled, and its state is cleared", async () => {
  const t = setup();
  try {
    slowRecorder(t, { after: null, verifiable: false });
    await assert.rejects(t.run("start"), /did not begin recording within 30 s; process 7000 could not be verified/);
    assert.deepEqual(t.signals, []);
    assert.equal(readState(t.dir), null);
    assert.equal(fs.existsSync(recordingDir(t.dir, "rec-1")), false);
  } finally {
    t.dispose();
  }
});

test("a verified recorder that never starts is killed at the timeout", async () => {
  const t = setup();
  try {
    slowRecorder(t, { after: null, verifiable: true });
    await assert.rejects(t.run("start"), /did not begin recording within 30 s$/);
    assert.deepEqual(t.signals, [{ pid: 7000, signal: "SIGKILL" }]);
    assert.equal(readState(t.dir), null);
  } finally {
    t.dispose();
  }
});

test("mark appends {kind: mark, note, t} with t from the state's start time, and is refused with nothing recording", async () => {
  const t = setup();
  try {
    await assert.rejects(t.run("mark", "too early"), /no recording is running/);
    await t.run("start");
    t.clock.t = 5_012_345;
    await t.run("mark", "checkout", "fails", "now");
    t.clock.t = 5_020_000;
    await t.run("mark");
    const marks = eventsOf(t.dir, "rec-1").filter((event) => event.kind === "mark");
    assert.deepEqual(
      marks.map((mark) => [mark.t, mark["note"]]),
      [
        [12_345, "checkout fails now"],
        [20_000, ""],
      ],
    );
    assert.ok(t.said.includes("mark #1 in rec-1 at +12.345s: checkout fails now"));
  } finally {
    t.dispose();
  }
});

test("stop signals the recorder, waits for it, clears the state and prints the summary", async () => {
  const t = setup();
  try {
    await assert.rejects(t.run("stop"), /no recording is running/);
    await t.run("start");
    fs.appendFileSync(
      eventsPath(recordingDir(t.dir, "rec-1")),
      [
        { t: 10, kind: "net", status: 500, failure: null },
        { t: 20, kind: "exception", text: "x" },
        { t: 30, kind: "mark", note: "n" },
      ]
        .map((event) => `${JSON.stringify(event)}\n`)
        .join(""),
    );
    t.said.length = 0;
    assert.equal(await t.run("stop"), 0);
    assert.deepEqual(t.signals, [{ pid: 5000, signal: "SIGTERM" }]);
    assert.equal(readState(t.dir), null);
    assert.match(t.said[0], /recording rec-1: 4 events/);
    assert.ok(t.said.includes("  marks: 1; failed requests: 1; exceptions: 1"));
    assert.ok(t.said.some((line) => /kept in .*rec-1; delete it when done/.test(line)));
  } finally {
    t.dispose();
  }
});

test("stop of a recording whose recorder is already gone still clears the state and summarises; a recorder that will not stop is killed and the line says so", async () => {
  const gone = setup();
  try {
    await gone.run("start");
    gone.running.clear();
    gone.said.length = 0;
    await gone.run("stop");
    assert.match(gone.said[0], /had already ended/);
    assert.deepEqual(gone.signals, []);
    assert.equal(readState(gone.dir), null);
  } finally {
    gone.dispose();
  }
  const stubborn = setup({ stubborn: true });
  try {
    await stubborn.run("start");
    stubborn.said.length = 0;
    await stubborn.run("stop");
    assert.deepEqual(
      stubborn.signals.map((entry) => entry.signal),
      ["SIGTERM", "SIGKILL"],
    );
    assert.ok(stubborn.said.some((line) => /did not end within 15 s and was killed/.test(line)));
    assert.equal(readState(stubborn.dir), null);
  } finally {
    stubborn.dispose();
  }
});

test("status says what runs, list shows every recording with its marks, and neither needs Chrome", async () => {
  const t = setup();
  try {
    await t.run("status");
    assert.match(t.said.at(-1) ?? "", /no recording is running; 0 kept/);
    await t.run("start", "--name", "first");
    await t.run("mark", "m");
    t.said.length = 0;
    await t.run("status");
    assert.match(t.said[0], /^recording first is running \(recorder pid 5000, 0 s, Chrome side here\)/);
    await t.run("stop");
    await t.run("start", "--name", "second");
    t.said.length = 0;
    await t.run("list");
    assert.match(t.said[0], /^first\s+2 events\s+0\.0 s\s+1 mark\(s\)$/);
    assert.match(t.said[1], /^second\s+1 events .*\(running\)$/);
    t.said.length = 0;
    await t.run("status", "--json");
    const json = JSON.parse(t.said[0]);
    assert.equal(json.running, true);
    assert.deepEqual(json.recordings, ["first", "second"]);
  } finally {
    t.dispose();
  }
});

test("delete removes that recording's folder and nothing else; a running one, an unknown one and a path are refused", async () => {
  const t = setup();
  try {
    await t.run("start", "--name", "one");
    await t.run("stop");
    await t.run("start", "--name", "two");
    await assert.rejects(t.run("delete", "two"), /is running; stop it first/);
    await t.run("stop");
    await assert.rejects(t.run("delete", "nope"), /no recording named nope/);
    await assert.rejects(t.run("delete", "../recordings"), /is not a recording name/);
    fs.writeFileSync(posix.join(t.dir, "launch.json"), "{}");
    assert.equal(await t.run("delete", "one"), 0);
    assert.equal(fs.existsSync(recordingDir(t.dir, "one")), false);
    assert.ok(fs.existsSync(recordingDir(t.dir, "two")));
    assert.ok(fs.existsSync(posix.join(t.dir, "launch.json")));
    assert.ok(t.said.includes("deleted recording one"));
  } finally {
    t.dispose();
  }
});

/**
 * A recording with a short session in it.
 * @param {ReturnType<typeof setup>} t
 * @param {string} name
 */
async function recorded(t, name) {
  await t.run("start", "--name", name);
  const events = [
    { t: 100, kind: "navigation", page: "p1", url: "https://shop.example/cart" },
    {
      t: 5000,
      kind: "click",
      page: "p1",
      target: {
        tag: "button",
        role: "button",
        name: "Pay",
        testid: "",
        id: "",
        nameAttr: "",
        label: "",
        text: "Pay",
        css: "button",
        type: "",
        sensitive: false,
      },
    },
    {
      t: 5100,
      kind: "net",
      page: "p1",
      method: "POST",
      url: "https://shop.example/api/pay",
      status: 500,
      type: "XHR",
      ms: 80,
      failure: null,
    },
    { t: 5600, kind: "mark", note: "payment fails" },
    { t: 40_000, kind: "console", page: "p1", level: "log", text: "late" },
  ];
  fs.appendFileSync(
    eventsPath(recordingDir(t.dir, name)),
    events.map((event) => `${JSON.stringify(event)}\n`).join(""),
  );
}

test("export prints the timeline of the running recording, or the newest one kept; --around limits it to the mark's window", async () => {
  const t = setup();
  try {
    await assert.rejects(t.run("export"), /no recording to export/);
    await recorded(t, "bug");
    t.said.length = 0;
    await t.run("export");
    assert.match(t.said[0], /^recording bug: 6 events, 40\.000s$/);
    t.said.length = 0;
    await t.run("export", "--around", "last", "--window", "2");
    assert.equal(t.said[0], "recording bug: around mark #1 at +5.600s (2 s each side), 3 of 6 events");
    assert.equal(t.said.length, 4);
    assert.ok(t.said.some((line) => /! POST 500 80 ms https:\/\/shop\.example\/api\/pay/.test(line)));
    t.said.length = 0;
    await t.run("export", "bug", "--around", "1", "--json");
    assert.deepEqual(
      JSON.parse(t.said[0]).map((/** @type {{kind: string}} */ event) => event.kind),
      ["start", "navigation", "click", "net", "mark"],
    );
  } finally {
    t.dispose();
  }
});

test("export --test playwright writes the draft into the recording's folder, or to --out, and an unknown mark is refused", async () => {
  const t = setup();
  try {
    await recorded(t, "bug");
    await t.run("stop");
    t.said.length = 0;
    await t.run("export", "--test", "playwright");
    const draft = posix.join(recordingDir(t.dir, "bug"), "bug.spec.ts");
    assert.match(
      t.said[0],
      new RegExp(`^wrote ${draft.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}: a draft for the project's own runner`),
    );
    const text = fs.readFileSync(draft, "utf8");
    assert.match(text, /A draft Playwright test generated by/);
    assert.match(text, /getByRole\('button', \{ name: 'Pay' \}\)/);
    await t.run("export", "bug", "--test", "playwright", "--out", "drafts/pay.spec.ts");
    assert.ok(fs.existsSync(posix.join(t.root, "drafts", "pay.spec.ts")));
    await assert.rejects(t.run("export", "bug", "--around", "4"), /the recording has 1 mark/);
    await assert.rejects(t.run("export", "missing"), /no recording named missing/);
  } finally {
    t.dispose();
  }
});

test("stop never signals a process it cannot show to be the recorder, clears the state and says so", async () => {
  const t = setup();
  try {
    await t.run("start");
    t.running.clear();
    t.how.unverifiable = () => true;
    t.said.length = 0;
    await t.run("stop");
    assert.match(
      t.said[0],
      /is not shown to be the recorder of .* so it was not signalled; the recording state is cleared/,
    );
    assert.deepEqual(t.signals, []);
    assert.equal(readState(t.dir), null);
  } finally {
    t.dispose();
  }
});

/**
 * Process readers over a table of what runs.
 * @param {string} platform
 * @param {Record<number, string | null>} procs the command line of each process, `null` when it cannot be read
 * @returns {import("./record.mjs").ProcessReaders}
 */
function readers(platform, procs) {
  return {
    platform,
    exists: (pid) => pid in procs,
    procCommand: (pid) => procs[pid] ?? null,
    psCommand: (pid) => procs[pid] ?? null,
  };
}

test("a process is the recorder by its command line, on Linux and macOS", () => {
  const procs = { 1: "node\0/x/js/tools/browser/recorder.mjs\0/y/config.json\0", 2: "vim\0notes.txt\0" };
  for (const platform of ["linux", "darwin"]) {
    assert.equal(recorderState(1, readers(platform, procs)), "recorder", platform);
    assert.equal(recorderState(2, readers(platform, procs)), "other", platform);
    assert.equal(recorderState(3, readers(platform, procs)), "gone", platform);
  }
});

test("where the command line cannot be read, the process is unverifiable and so never taken for the recorder", () => {
  assert.equal(recorderState(1, readers("linux", { 1: null })), "unverifiable", "/proc missing or hidden");
  assert.equal(recorderState(1, readers("darwin", { 1: null })), "unverifiable", "ps did not answer");
  assert.equal(recorderState(1, readers("win32", { 1: "node recorder.mjs" })), "unverifiable");
  assert.equal(recorderState(1, readers("freebsd", { 1: "node recorder.mjs" })), "unverifiable");
});
