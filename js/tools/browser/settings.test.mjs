import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import { delimiter, posix } from "node:path";

import {
  BrowserError,
  DEFAULT_REDACT,
  EXTENSIONS_ENV,
  DEFAULT_VIEWPORTS,
  defaultPort,
  extensionsProblemLine,
  parseViewportSize,
  portOf,
  projectAt,
  readSettings,
  requireExtensions,
  ROOT_ENV,
} from "./settings.mjs";
import { tempProject } from "./support.test.mjs";

test("the derived port is 9300 + sha1(root) % 600, stable per root and spread over roots", () => {
  const expected = 9300 + (createHash("sha1").update("/work/acme").digest().readUInt16BE(0) % 600);
  assert.equal(defaultPort("/work/acme"), expected);
  assert.equal(defaultPort("/work/acme"), defaultPort("/work/acme"));
  const ports = new Set(["/a", "/b", "/c", "/d", "/e", "/f"].map(defaultPort));
  assert.ok(ports.size > 1);
  for (const port of ports) {
    assert.ok(port >= 9300 && port < 9900, String(port));
  }
});

test("the project is the one at or above the start, its browser state under the local layer", () => {
  const { root, dispose } = tempProject();
  try {
    const project = projectAt(posix.join(root, "_aitna"), {});
    assert.equal(project.root, root);
    assert.equal(project.name, posix.basename(root));
    assert.equal(project.browserDir, posix.join(root, "_aitna", ".local", ".browser"));
  } finally {
    dispose();
  }
});

test("outside a project the run is refused with one line", () => {
  assert.throws(
    () => projectAt("/", {}),
    (error) => error instanceof BrowserError && /no akmon project/.test(error.message),
  );
});

test("[browser] of the record gives the settings and the environment overrides each key", () => {
  const { root, dispose } = tempProject(
    '[browser]\nchrome = "/opt/c/chrome"\nport = 9444\nprofile = "prof"\nproxy = "direct"\n',
  );
  try {
    const project = projectAt(root, {});
    assert.deepEqual(readSettings(project, {}), {
      chrome: "/opt/c/chrome",
      port: 9444,
      profile: posix.join(root, "prof"),
      proxy: "direct",
      viewports: DEFAULT_VIEWPORTS,
      redact: DEFAULT_REDACT,
      extensions: [],
      extensionsProblem: null,
    });
    const overridden = readSettings(project, {
      AKMON_BROWSER_CHROME: "/usr/bin/chromium",
      AKMON_BROWSER_PORT: "9555",
      AKMON_BROWSER_PROFILE: "/tmp/p",
      AKMON_BROWSER_PROXY: "http://proxy:3128",
    });
    assert.deepEqual(overridden, {
      chrome: "/usr/bin/chromium",
      port: 9555,
      profile: "/tmp/p",
      proxy: "http://proxy:3128",
      viewports: DEFAULT_VIEWPORTS,
      redact: DEFAULT_REDACT,
      extensions: [],
      extensionsProblem: null,
    });
    assert.equal(portOf(project, overridden), 9555);
  } finally {
    dispose();
  }
});

test("with no setting the port is derived and the rest is unset; an empty variable is no override", () => {
  const { root, dispose } = tempProject();
  try {
    const project = projectAt(root, {});
    const settings = readSettings(project, { AKMON_BROWSER_PORT: "" });
    assert.deepEqual(settings, {
      chrome: null,
      port: null,
      profile: null,
      proxy: null,
      viewports: DEFAULT_VIEWPORTS,
      redact: DEFAULT_REDACT,
      extensions: [],
      extensionsProblem: null,
    });
    assert.equal(portOf(project, settings), defaultPort(root));
  } finally {
    dispose();
  }
});

test("a port that is not a port is refused naming the value", () => {
  const { root, dispose } = tempProject();
  try {
    const project = projectAt(root, {});
    for (const bad of ["abc", "0", "70000", "93.5"]) {
      assert.throws(
        () => readSettings(project, { AKMON_BROWSER_PORT: bad }),
        (error) => error instanceof BrowserError && error.message.includes(JSON.stringify(bad)),
      );
    }
  } finally {
    dispose();
  }
});

test("[browser].viewports joins and overrides the presets, [browser].redact adds to the defaults", () => {
  const { root, dispose } = tempProject(
    '[browser]\nredact = ["ssn", "password"]\n\n[browser.viewports]\nphone = "360x740"\nwide = "1920X1080"\n',
  );
  try {
    const settings = readSettings(projectAt(root, {}), {});
    assert.deepEqual(settings.viewports["phone"], { width: 360, height: 740 });
    assert.deepEqual(settings.viewports["wide"], { width: 1920, height: 1080 });
    assert.deepEqual(settings.viewports["desktop"], { width: 1440, height: 900 });
    assert.deepEqual(settings.redact, [...DEFAULT_REDACT, "ssn"]);
  } finally {
    dispose();
  }
});

test("a viewport that is not WxH and a redact that is not a list are refused naming the value", () => {
  /** @type {[string, RegExp][]} */
  const bad = [
    ['[browser.viewports]\nphone = "tall"\n', /phone = "tall"/],
    ["[browser.viewports]\nphone = 390\n", /phone = 390/],
    ['[browser]\nviewports = "x"\n', /viewports must be a table/],
    ['[browser]\nredact = "token"\n', /redact must be a list/],
    ['[browser]\nextensions = "ext"\n', /extensions must be a list/],
  ];
  for (const [record, pattern] of bad) {
    const { root, dispose } = tempProject(record);
    try {
      assert.throws(
        () => readSettings(projectAt(root, {}), {}),
        (error) => error instanceof BrowserError && pattern.test(error.message),
        record,
      );
    } finally {
      dispose();
    }
  }
});

test("a size is written WxH", () => {
  assert.deepEqual(parseViewportSize("1280x720"), { width: 1280, height: 720 });
  assert.deepEqual(parseViewportSize(" 390 X 844 "), { width: 390, height: 844 });
  for (const bad of ["", "1280", "x720", "1280x", "1x2", "wide"]) {
    assert.equal(parseViewportSize(bad), null, bad);
  }
});

test("the project's redact keys add to the defaults and nothing in the configuration can remove one", () => {
  const { root, dispose } = tempProject('[browser]\nredact = ["SSN", "Password", "ssn", "iban"]\n');
  try {
    const { redact } = readSettings(projectAt(root, {}), {});
    assert.deepEqual(redact, [...DEFAULT_REDACT, "SSN", "iban"]);
    for (const key of DEFAULT_REDACT) {
      assert.ok(redact.includes(key), key);
    }
  } finally {
    dispose();
  }
  const empty = tempProject("[browser]\nredact = []\n");
  try {
    assert.deepEqual(readSettings(projectAt(empty.root, {}), {}).redact, DEFAULT_REDACT);
  } finally {
    empty.dispose();
  }
});

/**
 * A project with unpacked extension folders under it.
 * @param {string} record the `.akmon.toml` text
 * @param {string[]} withManifest folders (relative to the root) that get a `manifest.json`
 */
function extensionProject(record, withManifest) {
  const project = tempProject(record);
  for (const folder of withManifest) {
    fs.mkdirSync(posix.join(project.root, folder), { recursive: true });
    fs.writeFileSync(posix.join(project.root, folder, "manifest.json"), "{}");
  }
  return project;
}

test("[browser].extensions are folders under the project root, each holding a manifest.json", () => {
  const { root, dispose } = extensionProject('[browser]\nextensions = ["ext/one", "./ext/two/", "ext/one"]\n', [
    "ext/one",
    "ext/two",
  ]);
  try {
    assert.deepEqual(readSettings(projectAt(root, {}), {}).extensions, [
      posix.join(root, "ext/one"),
      posix.join(root, "ext/two"),
    ]);
  } finally {
    dispose();
  }
});

test("AKMON_BROWSER_EXTENSIONS replaces the table, its paths joined by the OS path delimiter", () => {
  const { root, dispose } = extensionProject('[browser]\nextensions = ["ext/one"]\n', ["ext/one", "other"]);
  try {
    const project = projectAt(root, {});
    const joined = ["other", posix.join(root, "ext/one")].join(delimiter);
    assert.deepEqual(readSettings(project, { [EXTENSIONS_ENV]: joined }).extensions, [
      posix.join(root, "other"),
      posix.join(root, "ext/one"),
    ]);
    assert.deepEqual(readSettings(project, { [EXTENSIONS_ENV]: "" }).extensions, [posix.join(root, "ext/one")]);
  } finally {
    dispose();
  }
});

test("an extension folder with no manifest.json, or a comma in it, is classified, not thrown, naming it", () => {
  const { root, dispose } = extensionProject('[browser]\nextensions = ["ext/one", "ext/none"]\n', ["ext/one"]);
  try {
    const settings = readSettings(projectAt(root, {}), {});
    assert.deepEqual(settings.extensions, [posix.join(root, "ext/one")]);
    assert.deepEqual(settings.extensionsProblem, { path: "ext/none", defect: "has no manifest.json" });
    assert.equal(extensionsProblemLine(settings), "ext/none has no manifest.json");
    const fromEnv = readSettings(projectAt(root, {}), { [EXTENSIONS_ENV]: "missing" });
    assert.equal(extensionsProblemLine(fromEnv), "missing has no manifest.json");
  } finally {
    dispose();
  }
  const comma = extensionProject('[browser]\nextensions = ["a,b"]\n', ["a,b"]);
  try {
    const settings = readSettings(projectAt(comma.root, {}), {});
    assert.match(String(extensionsProblemLine(settings)), /^a,b holds a comma/);
  } finally {
    comma.dispose();
  }
});

test("requireExtensions refuses in one line on a problem, and passes on none", () => {
  const { root, dispose } = extensionProject('[browser]\nextensions = ["ext/none"]\n', []);
  try {
    assert.throws(
      () => requireExtensions(readSettings(projectAt(root, {}), {})),
      (error) =>
        error instanceof BrowserError &&
        /"ext\/none" has no manifest\.json/.test(error.message) &&
        !error.message.includes("\n"),
    );
  } finally {
    dispose();
  }
  const sound = extensionProject('[browser]\nextensions = ["ext/one"]\n', ["ext/one"]);
  try {
    assert.doesNotThrow(() => requireExtensions(readSettings(projectAt(sound.root, {}), {})));
  } finally {
    sound.dispose();
  }
});

/**
 * A plain folder that is not an akmon project.
 * @returns {{root: string, dispose: () => void}}
 */
function plainFolder() {
  const root = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-browser-plain-")));
  return { root, dispose: () => fs.rmSync(root, { recursive: true, force: true }) };
}

test("AKMON_BROWSER_ROOT names a project outside any akmon project: no dev layer, state under <root>/.local/.browser", () => {
  const { root, dispose } = plainFolder();
  try {
    const project = projectAt("/", { [ROOT_ENV]: root });
    assert.equal(project.root, root);
    assert.equal(project.name, posix.basename(root));
    assert.equal(project.devRoot, null);
    assert.equal(project.browserDir, posix.join(root, ".local", ".browser"));
    assert.equal(portOf(project, readSettings(project, {})), defaultPort(root));
  } finally {
    dispose();
  }
});

test("AKMON_BROWSER_ROOT wins over discovery and over a [browser] table; the other overrides still apply", () => {
  const { root, dispose } = tempProject('[browser]\nport = 9444\nproxy = "direct"\n');
  const other = tempProject();
  try {
    const project = projectAt(other.root, { [ROOT_ENV]: root });
    assert.equal(project.root, root);
    assert.equal(project.devRoot, null);
    assert.equal(project.browserDir, posix.join(root, ".local", ".browser"));
    const settings = readSettings(project, {});
    assert.equal(settings.port, null);
    assert.equal(settings.proxy, null);
    assert.equal(portOf(project, settings), defaultPort(root));
    assert.equal(readSettings(project, { AKMON_BROWSER_PORT: "9555" }).port, 9555);
  } finally {
    dispose();
    other.dispose();
  }
});

test("an empty AKMON_BROWSER_ROOT is no override: discovery runs", () => {
  const { root, dispose } = tempProject();
  try {
    const project = projectAt(root, { [ROOT_ENV]: "" });
    assert.equal(project.devRoot, posix.join(root, "_aitna"));
  } finally {
    dispose();
  }
});

test("AKMON_BROWSER_ROOT follows a symlink to the real folder", () => {
  const { root, dispose } = plainFolder();
  try {
    const link = `${root}-link`;
    fs.symlinkSync(root, link);
    try {
      assert.equal(projectAt("/", { [ROOT_ENV]: link }).root, root);
    } finally {
      fs.rmSync(link);
    }
  } finally {
    dispose();
  }
});

test("AKMON_BROWSER_ROOT that is relative, missing or a file is refused in one line naming the value", () => {
  const { root, dispose } = plainFolder();
  try {
    const file = posix.join(root, "file");
    fs.writeFileSync(file, "");
    /** @type {[string, RegExp][]} */
    const cases = [
      ["relative/dir", /not an absolute path/],
      [posix.join(root, "missing"), /not an existing directory/],
      [file, /not an existing directory/],
    ];
    for (const [value, defect] of cases) {
      assert.throws(
        () => projectAt(root, { [ROOT_ENV]: value }),
        (error) =>
          error instanceof BrowserError &&
          error.message.includes(ROOT_ENV) &&
          error.message.includes(JSON.stringify(value)) &&
          defect.test(error.message) &&
          !error.message.includes("\n"),
      );
    }
  } finally {
    dispose();
  }
});
