import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { posix } from "node:path";

import { buildContext } from "./context.mjs";
import { developerModeCommand, extCommand } from "./ext.mjs";
import { runRequest } from "./ops.mjs";
import { BrowserError } from "./settings.mjs";
import { extensionsPage, fakeChrome, fakeHost, SAMPLE_EXTENSION, tempProject } from "./support.test.mjs";

/**
 * A context over a throwaway project with the folder `ext` configured as an extension, an inspector over a
 * fake Chrome that has an extensions page, and what was said.
 * @param {Parameters<typeof extensionsPage>[0]} page
 * @param {{replies?: Record<string, (params: any) => unknown>, files?: Record<string, string>, configured?: boolean}} [given]
 */
function setup(page, given = {}) {
  const project = tempProject(given.configured === false ? "" : '[browser]\nextensions = ["ext"]\n');
  fs.mkdirSync(posix.join(project.root, "ext"));
  fs.writeFileSync(posix.join(project.root, "ext", "manifest.json"), "{}");
  /** @type {string[]} */
  const said = [];
  const ctx = buildContext(project.root, { env: {}, host: fakeHost(), say: (line) => said.push(line) });
  const folder = posix.join(project.root, "ext");
  const listed = (page?.list ?? [SAMPLE_EXTENSION]).map((item) => ({ ...item, path: folder }));
  const chrome = fakeChrome(
    { ...extensionsPage({ ...page, list: listed }), ...given.replies },
    { targets: [{ id: "T1", type: "page", title: "Shop", url: "https://shop.example/" }], files: given.files },
  );
  /** @type {import("./inspect.mjs").Inspector} */
  const how = {
    locate: async () => ({ browserURL: "http://127.0.0.1:9582", port: 9582, mode: "own", side: "here" }),
    targets: async () => [],
    execute: (_browser, request) => runRequest(request, chrome.deps),
  };
  return { ctx, said, how, chrome, folder, dispose: project.dispose };
}

test("ext refuses a configured extension path that cannot be loaded, in one line", async () => {
  const { ctx, how, dispose } = setup({});
  try {
    const broken = {
      ...ctx,
      settings: { ...ctx.settings, extensionsProblem: { path: "ext/none", defect: "has no manifest.json" } },
    };
    await assert.rejects(
      extCommand(broken, { sub: "list", ext: null, page: null, json: false }, how),
      (error) => error instanceof BrowserError && /"ext\/none" has no manifest\.json/.test(error.message),
    );
  } finally {
    dispose();
  }
});

test("ext list prints the loaded extensions, or as JSON with the configured flag", async () => {
  const { ctx, said, how, folder, dispose } = setup({});
  try {
    assert.equal(await extCommand(ctx, { sub: "list", ext: null, page: null, json: false }, how), 0);
    assert.equal(said[0], `${SAMPLE_EXTENSION.id}  ENABLED   Bench 1.2.3  (configured ${folder})`);
    said.length = 0;
    await extCommand(ctx, { sub: "list", ext: null, page: null, json: true }, how);
    const listed = JSON.parse(said.join("\n"));
    assert.deepEqual([listed[0].name, listed[0].configured, listed[0].unpacked], ["Bench", true, true]);
  } finally {
    dispose();
  }
});

test("ext reload exits 0 when every extension comes back running", async () => {
  const { ctx, said, how, dispose } = setup({
    reload: (ids) => ids.map((id) => ({ id, loadError: null, info: SAMPLE_EXTENSION })),
  });
  try {
    assert.equal(await extCommand(ctx, { sub: "reload", ext: null, page: null, json: false }, how), 0);
    assert.deepEqual(said, [`${SAMPLE_EXTENSION.id}  ENABLED  Bench 1.2.3`]);
  } finally {
    dispose();
  }
});

test("ext reload reports a manifest or load error and exits 1", async () => {
  const { ctx, said, how, dispose } = setup({
    reload: (ids) => ids.map((id) => ({ id, loadError: "Required value 'version' is missing.", info: null })),
  });
  try {
    assert.equal(await extCommand(ctx, { sub: "reload", ext: "Bench", page: null, json: false }, how), 1);
    assert.deepEqual(said, [
      `${SAMPLE_EXTENSION.id}  NOT LOADED`,
      "    load error: Required value 'version' is missing.",
    ]);
  } finally {
    dispose();
  }
});

test("ext reload of nothing the Chrome holds is a refusal saying how to get it loaded", async () => {
  const { ctx, how, dispose } = setup({ list: [] });
  try {
    await assert.rejects(
      extCommand(ctx, { sub: "reload", ext: null, page: null, json: false }, how),
      (error) => error instanceof BrowserError && /akmon tool browser restart/.test(error.message),
    );
  } finally {
    dispose();
  }
});

test("ext action prints the route that ran, and on the popup route the note about the missing active tab", async () => {
  const cdp = setup({}, { replies: { "Extensions.triggerAction": () => ({}) } });
  try {
    assert.equal(await extCommand(cdp.ctx, { sub: "action", ext: null, page: null, json: false }, cdp.how), 0);
    assert.match(cdp.said[0], /^triggered the action of Bench /);
  } finally {
    cdp.dispose();
  }
  const manifest = JSON.stringify({ action: { default_popup: "popup.html" } });
  const popup = setup(
    {},
    {
      replies: {
        "Extensions.triggerAction": () => {
          throw new Error("'Extensions.triggerAction' wasn't found");
        },
      },
      files: {},
    },
  );
  try {
    // The manifest is read from the extension's folder as the Chrome side sees it.
    const realRead = popup.chrome.deps.readText;
    popup.chrome.deps.readText = (path) =>
      path === posix.join(popup.folder, "manifest.json") ? manifest : realRead(path);
    assert.equal(await extCommand(popup.ctx, { sub: "action", ext: null, page: null, json: false }, popup.how), 0);
    assert.match(
      popup.said[0],
      /opened the popup of Bench .* in a new tab: chrome-extension:\/\/.*\/popup\.html \[P9\]/,
    );
    assert.match(popup.said.join(" "), /lacks the active-tab context/);
  } finally {
    popup.dispose();
  }
});

test("an unknown ext sub-command is refused", async () => {
  const { ctx, how, dispose } = setup({});
  try {
    await assert.rejects(extCommand(ctx, { sub: "remove", ext: null, page: null, json: false }, how), BrowserError);
  } finally {
    dispose();
  }
});

test("after start: developer mode is turned on and the configured extension is reported loaded", async () => {
  const { ctx, said, how, dispose } = setup({});
  try {
    assert.equal(await developerModeCommand(ctx, how, { polls: 1 }), 0);
    assert.equal(said[0], "  developer mode: on");
    assert.match(said[1], /^ {2}abcdefghijklmnopabcdefghijklmnop {2}ENABLED {3}Bench 1\.2\.3 {2}\(configured /);
  } finally {
    dispose();
  }
});

test("after start: a configured extension the Chrome did not load is a warning naming the folder, and exit 1", async () => {
  const { ctx, said, how, folder, dispose } = setup({ list: [] });
  try {
    assert.equal(await developerModeCommand(ctx, how, { polls: 1 }), 1);
    assert.equal(said[0], "  developer mode: on");
    assert.match(said[1], new RegExp(`^ {2}not loaded: ${folder}; a branded Chrome ignores --load-extension`));
  } finally {
    dispose();
  }
});
