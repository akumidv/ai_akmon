import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";

import { readEvents } from "./record-events.mjs";
import { eventsPath } from "./record-store.mjs";
import { decodeRecorderConfig, runRecorder } from "./recorder.mjs";

/** @returns {{dir: string, dispose: () => void}} */
function scratch() {
  const dir = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-recorder-")));
  return { dir, dispose: () => fs.rmSync(dir, { recursive: true, force: true }) };
}

/**
 * @param {string} dir
 * @returns {import("./recorder.mjs").RecorderConfig}
 */
function configIn(dir) {
  return {
    name: "rec-1",
    dir,
    startedAtMs: 1000,
    side: "here",
    request: {
      browserURL: "http://127.0.0.1:9582",
      page: null,
      allPages: false,
      bodies: true,
      maxBody: 100,
      redact: [],
      binding: "b",
    },
  };
}

/** @param {string} dir */
const eventsIn = (dir) => readEvents(fs.readFileSync(eventsPath(dir), "utf8")).events;

test("the recorder writes start once it records, the events as they come, and stop when told to", async () => {
  const { dir, dispose } = scratch();
  try {
    let clock = 1100;
    /** @type {() => void} */
    let tell = () => {};
    /** @type {(outcome: any) => void} */
    let finish = () => {};
    const ended = new Promise((resolve) => {
      finish = resolve;
    });
    const done = runRecorder(configIn(dir), {
      now: () => (clock += 10),
      start: async (_request, emit) => {
        emit({ kind: "page", page: "p1", url: "https://x.example/" });
        return { pages: ["p1"], ended, stop: async () => finish({ reason: "stopped", error: null }) };
      },
      onStop: (handler) => {
        tell = handler;
      },
    });
    await new Promise((resolve) => setImmediate(resolve));
    tell();
    assert.equal(await done, 0);
    const events = eventsIn(dir);
    assert.deepEqual(
      events.map((event) => event.kind),
      ["page", "start", "stop"],
    );
    assert.equal(events[1]["bodies"], true);
    assert.equal(events[2]["reason"], "stopped");
  } finally {
    dispose();
  }
});

test("a recorder that cannot begin writes one error event and fails", async () => {
  const { dir, dispose } = scratch();
  try {
    const code = await runRecorder(configIn(dir), {
      now: () => 2000,
      start: async () => {
        throw new Error("the browser has no open page");
      },
      onStop: () => {},
    });
    assert.equal(code, 1);
    assert.deepEqual(
      eventsIn(dir).map((event) => [event.kind, event["text"]]),
      [["error", "the browser has no open page"]],
    );
  } finally {
    dispose();
  }
});

test("Chrome closing ends the recording as closed (0); a failure of the Chrome side ends it as an error (1)", async () => {
  for (const [reason, code] of /** @type {[string, number][]} */ ([
    ["closed", 0],
    ["error", 1],
  ])) {
    const { dir, dispose } = scratch();
    try {
      const result = await runRecorder(configIn(dir), {
        now: () => 2000,
        start: async () => ({
          pages: ["p1"],
          ended: Promise.resolve(/** @type {any} */ ({ reason, error: reason === "error" ? "lost" : null })),
          stop: async () => {},
        }),
        onStop: () => {},
      });
      assert.equal(result, code);
      const last = eventsIn(dir).at(-1);
      assert.equal(last?.["reason"], reason);
      assert.equal(last?.["text"], reason === "error" ? "lost" : undefined);
    } finally {
      dispose();
    }
  }
});

test("the configuration is validated where the file enters", () => {
  const good = JSON.stringify(configIn("/x"));
  assert.equal(decodeRecorderConfig(good).name, "rec-1");
  assert.throws(() => decodeRecorderConfig(JSON.stringify({ name: "x" })), /needs name, dir/);
  assert.throws(() => decodeRecorderConfig(JSON.stringify({ ...configIn("/x"), side: "mars" })), /needs name, dir/);
  assert.throws(() => decodeRecorderConfig("{"));
});
