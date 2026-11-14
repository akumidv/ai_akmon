/**
 * The `ext` verb of `akmon tool browser` and the step after `start` that serves it: the extensions the
 * project's Chrome holds (`ext list`), a reload of the configured unpacked ones from disk (`ext reload`) and
 * the action of an extension on a page (`ext action`). This side does the project's part (the settings, the
 * words, the exit status); the Chrome side is `extension-cdp.mjs` through `ops.mjs`, run here or on the
 * Windows side like the inspection verbs. A verb never starts a Chrome.
 */

import { samePath } from "./extension-cdp.mjs";
import { realInspector, runOperations } from "./inspect.mjs";
import { actionLines, extensionLines, reloadLines, reloadSucceeded } from "./render.mjs";
import { BrowserError, requireExtensions } from "./settings.mjs";

/** How often `start` looks for the configured extensions to appear, and how long between looks, in milliseconds. */
const _LOAD_POLLS = 6;
const _LOAD_POLL_MS = 500;

/**
 * @typedef {import("./context.mjs").Context} Context
 * @typedef {import("./inspect.mjs").Inspector} Inspector
 */

/**
 * The value of the one operation a run was asked for, or the failure it ended in.
 * @param {import("./protocol.mjs").Outcome | undefined} outcome
 * @returns {any}
 * @throws {BrowserError} when the operation failed
 */
function _valueOf(outcome) {
  if (outcome === undefined) {
    throw new BrowserError("the browser run returned no result");
  }
  if (!outcome.ok) {
    throw new BrowserError(outcome.error);
  }
  return outcome.value;
}

/**
 * `ext list [--json]`: the loaded extensions, with id, name, version, state, folder and whether they are the
 * project's configured ones.
 * @param {Context} ctx
 * @param {{json: boolean}} options
 * @param {Inspector} [how]
 * @returns {Promise<number>}
 */
async function _list(ctx, options, how = realInspector()) {
  const { results } = await runOperations(ctx, how, { page: null, operations: [{ op: "ext-list" }] });
  const { extensions } = _valueOf(results[0]);
  if (options.json) {
    ctx.say(JSON.stringify(extensions, null, 2));
  } else {
    extensionLines(extensions).forEach(ctx.say);
  }
  return 0;
}

/**
 * `ext reload [<id|name>] [--json]`: the configured unpacked extensions (or the one named) reloaded from disk
 * through `chrome://extensions`' own API, then each one's state and any load error, which is where a
 * manifest error shows. Exit 1 when one is not running afterwards.
 * @param {Context} ctx
 * @param {{ext: string | null, json: boolean}} options
 * @param {Inspector} how
 * @returns {Promise<number>}
 */
async function _reload(ctx, options, how) {
  const { results } = await runOperations(ctx, how, {
    page: null,
    ext: options.ext,
    operations: [{ op: "ext-reload" }],
  });
  const reloaded = _valueOf(results[0]);
  if (options.json) {
    ctx.say(JSON.stringify(reloaded, null, 2));
  } else {
    reloadLines(reloaded).forEach(ctx.say);
  }
  return reloadSucceeded(reloaded) ? 0 : 1;
}

/**
 * `ext action [<id|name>] [--page P]`: the action of the extension on the selected page, as its toolbar
 * button does, or, when this Chrome does not offer that over the DevTools port, its popup page in a new tab.
 * @param {Context} ctx
 * @param {{ext: string | null, page: string | null}} options
 * @param {Inspector} how
 * @returns {Promise<number>}
 */
async function _action(ctx, options, how) {
  const { results } = await runOperations(ctx, how, {
    page: options.page,
    ext: options.ext,
    operations: [{ op: "ext-action" }],
  });
  actionLines(_valueOf(results[0])).forEach(ctx.say);
  return 0;
}

/**
 * `ext list|reload|action`.
 * @param {Context} ctx
 * @param {{sub: string | null, ext: string | null, page: string | null, json: boolean}} options
 * @param {Inspector} [how]
 * @returns {Promise<number>}
 * @throws {BrowserError} for a sub-command that does not exist (the parser takes only the three)
 */
export async function extCommand(ctx, options, how = realInspector()) {
  requireExtensions(ctx.settings);
  switch (options.sub) {
    case "list":
      return _list(ctx, options, how);
    case "reload":
      return _reload(ctx, options, how);
    case "action":
      return _action(ctx, options, how);
    default:
      throw new BrowserError(`ext: unknown sub-command ${JSON.stringify(options.sub)}`);
  }
}

/**
 * Sleep.
 * @param {number} ms
 * @returns {Promise<void>}
 */
function _sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * What the browser says now about developer mode and the configured extensions.
 * @typedef {object} Observed
 * @property {boolean} developerMode developer mode is on
 * @property {any[]} extensions every extension the browser lists
 * @property {string[]} missing the configured folders no listed extension has
 */

/**
 * Turn developer mode on and look at what the browser loaded.
 * @param {Context} ctx
 * @param {Inspector} how
 * @returns {Promise<Observed>}
 */
async function _observe(ctx, how) {
  const run = await runOperations(ctx, how, { page: null, operations: [{ op: "ext-devmode" }, { op: "ext-list" }] });
  const { extensions } = /** @type {{extensions: any[]}} */ (_valueOf(run.results[1]));
  return {
    developerMode: _valueOf(run.results[0]).inDeveloperMode === true,
    extensions,
    missing: ctx.settings.extensions.filter(
      (_path, at) =>
        !extensions.some((item) => item.path !== null && samePath(run.extensionPaths[at], String(item.path))),
    ),
  };
}

/**
 * The step after `start` for a project that configures extensions: developer mode on (Chrome keeps an
 * unpacked extension enabled only in it), then what the Chrome loaded, with a warning for a configured
 * extension it did not load. The extensions may take a moment to appear, so it looks a few times.
 * @param {Context} ctx
 * @param {Inspector} [how]
 * @param {{polls?: number}} [options] how many times to look for the extensions to load, `_LOAD_POLLS` by default
 * @returns {Promise<number>} 0 when developer mode is on and every configured extension is loaded
 * @throws {BrowserError} when the browser cannot be asked
 */
export async function developerModeCommand(ctx, how = realInspector(), options = {}) {
  let seen = await _observe(ctx, how);
  for (let poll = 1; poll < (options.polls ?? _LOAD_POLLS) && seen.missing.length > 0; poll += 1) {
    await _sleep(_LOAD_POLL_MS);
    seen = await _observe(ctx, how);
  }
  ctx.say(seen.developerMode ? "  developer mode: on" : "  developer mode: could not be turned on");
  const loaded = seen.extensions.filter((item) => item.configured);
  if (loaded.length > 0) {
    extensionLines(loaded).forEach((line) => ctx.say(`  ${line}`));
  }
  seen.missing.forEach((path) =>
    ctx.say(
      `  not loaded: ${path}; a branded Chrome ignores --load-extension (akmon tool browser install gives Chrome for Testing), or the manifest has an error`,
    ),
  );
  return seen.developerMode && seen.missing.length === 0 ? 0 : 1;
}
