/**
 * node:test for `js/akmon/_trust.mjs` — the twin of the command-line half of
 * `meta/tests/test_grant_trust.py` (C172). Acceptance is driven through the injectable `ask` and
 * `interactive` seam, never through a flag: there is none.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";

import {
  accept,
  fileTrust,
  isAccepted,
  loadGrant,
  recordUntrusted,
  resolveStore,
  TrustState,
} from "../common/grant_trust.mjs";
import { main } from "./_trust.mjs";

const ABC_DIGEST = "edeaaff3f1774ad2888673770c6d64097e391bc362d7d6fb34982ddf0efd18cb";

/** @param {number} second */
const at = (second) => new Date(Date.UTC(2026, 0, 2, 3, 4, second));

/**
 * A fake process: captured streams, a scripted terminal, a project on disk.
 * @param {{interactive?: boolean, answers?: string[]}} [options]
 */
function terminal({ interactive = true, answers = [] } = {}) {
  const base = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-trust-cli-")));
  const root = posix.join(base, "proj");
  fs.mkdirSync(posix.join(root, "_aitna", "akmon"), { recursive: true });
  fs.writeFileSync(posix.join(root, "AGENTS.md"), "# project\n");
  const queue = [...answers];
  const term = {
    base,
    root,
    out: "",
    err: "",
    prompts: /** @type {string[]} */ ([]),
    io: {
      environ: { AKMON_TRUST_DIR: posix.join(base, "store") },
      cwd: root,
      out: { write: (/** @type {string} */ text) => void (term.out += text) },
      err: { write: (/** @type {string} */ text) => void (term.err += text) },
      interactive,
      ask: async (/** @type {string} */ prompt) => {
        term.prompts.push(prompt);
        return queue.length > 0 ? /** @type {string} */ (queue.shift()) : null;
      },
    },
    store: resolveStore({ AKMON_TRUST_DIR: posix.join(base, "store") }, root),
    /** @param {string[]} argv */
    async run(...argv) {
      term.out = "";
      term.err = "";
      return main(argv, term.io);
    },
    /**
     * @param {string} name
     * @param {string} text
     */
    grant(name, text) {
      const path = posix.join(root, "_aitna", "grants", name);
      fs.mkdirSync(posix.dirname(path), { recursive: true });
      fs.writeFileSync(path, text);
      return loadGrant(path, root);
    },
  };
  return term;
}

test("status lists state, short digest and path, and exits one while anything is untrusted", async () => {
  const term = terminal();
  const one = term.grant("one.toml", "abc\n");
  const two = term.grant("two.toml", "x\n");
  accept(one, term.store, at(1));
  assert.equal(await term.run("status"), 1);
  assert.equal(
    term.out,
    `trusted  ${ABC_DIGEST.slice(0, 12)}  _aitna/grants/one.toml\nnew      ${two.digest.slice(0, 12)}  _aitna/grants/two.toml\n`,
  );
  accept(two, term.store, at(2));
  assert.equal(await term.run("status"), 0);
  assert.equal(await term.run("status", "_aitna/grants/one.toml"), 0);
  assert.equal(term.out, `trusted  ${ABC_DIGEST.slice(0, 12)}  _aitna/grants/one.toml\n`);
});

test("status takes paths relative to the cwd and directories, and refuses a missing one", async () => {
  const term = terminal();
  term.grant("sub/one.toml", "x\n");
  term.io.cwd = posix.join(term.root, "_aitna");
  assert.equal(await term.run("status", "grants/sub"), 1);
  assert.ok(term.out.endsWith("  _aitna/grants/sub/one.toml\n"));
  assert.equal(await term.run("status", "grants/missing.toml"), 2);
  assert.match(term.err, /no such file or directory/);
});

test("status says so in one line when there is nothing to check, and creates no store", async () => {
  const term = terminal();
  assert.equal(await term.run("status"), 0);
  assert.equal(term.out, "akmon trust: no grant files under _aitna/grants/\n");
  assert.equal(fs.existsSync(term.store.root), false);
});

test("diff shows the whole file when new and the change when changed", async () => {
  const term = terminal();
  const first = term.grant("one.toml", "a\nb\n");
  assert.equal(await term.run("diff"), 0);
  assert.equal(
    term.out,
    "=== _aitna/grants/one.toml: new, no earlier version accepted; the whole file follows ===\na\nb\n",
  );
  accept(first, term.store, at(1));
  assert.equal(await term.run("diff"), 0);
  assert.equal(term.out, "akmon trust: every grant file is trusted; nothing to show\n");
  const changed = term.grant("one.toml", "a\nB\n");
  assert.equal(await term.run("diff"), 0);
  assert.equal(
    term.out,
    `=== _aitna/grants/one.toml: changed since ${first.digest.slice(0, 12)} ===\n` +
      `--- _aitna/grants/one.toml (accepted ${first.digest.slice(0, 12)})\n` +
      `+++ _aitna/grants/one.toml (now ${changed.digest.slice(0, 12)})\n` +
      "@@ -1,2 +1,2 @@\n a\n-b\n+B\n",
  );
});

test("diff of a file new to this project names the project that accepted the path", async () => {
  const term = terminal();
  const other = posix.join(term.base, "other");
  fs.mkdirSync(posix.join(other, "_aitna", "grants"), { recursive: true });
  fs.writeFileSync(posix.join(other, "_aitna", "grants", "one.toml"), "a\nb\n");
  const accepted = loadGrant(posix.join(other, "_aitna", "grants", "one.toml"), other);
  accept(accepted, term.store, at(1));
  const created = term.grant("one.toml", "a\nB\n");
  assert.equal(fileTrust(created, term.store).state, TrustState.NEW);
  assert.equal(await term.run("status"), 1);
  assert.ok(term.out.startsWith("new      "));
  assert.equal(await term.run("diff"), 0);
  assert.equal(
    term.out,
    `=== _aitna/grants/one.toml: new in this project; last accepted in project other as ${accepted.digest.slice(0, 12)}, ` +
      "the change since that version follows ===\n" +
      `--- _aitna/grants/one.toml (accepted in project other, ${accepted.digest.slice(0, 12)})\n` +
      `+++ _aitna/grants/one.toml (now ${created.digest.slice(0, 12)})\n` +
      "@@ -1,2 +1,2 @@\n a\n-b\n+B\n",
  );
});

test("the command refuses a store inside the project in one line", async () => {
  const term = terminal();
  const inside = posix.join(term.root, "state");
  term.io.environ = { AKMON_TRUST_DIR: inside };
  assert.equal(await term.run("status"), 2);
  assert.equal(
    term.err,
    `akmon trust: the trust store ${inside} is inside the project ${term.root}; set AKMON_TRUST_DIR to a directory outside the checkout (ADR 0025/D05)\n`,
  );
  assert.equal(fs.existsSync(inside), false);
});

test("accept refuses without a terminal and writes nothing", async () => {
  const term = terminal({ interactive: false, answers: ["y"] });
  term.grant("one.toml", "a\n");
  assert.equal(await term.run("accept"), 2);
  assert.match(term.err, /acceptance needs an interactive terminal/);
  assert.match(term.err, /ADR 0025\/D05/);
  assert.deepEqual(term.prompts, []);
  assert.equal(fs.existsSync(term.store.root), false);
});

test("accept shows each untrusted file, asks, and records the answers; end of input is no", async () => {
  const term = terminal({ answers: ["y", "n"] });
  const one = term.grant("one.toml", "abc\n");
  const two = term.grant("two.toml", "x\n");
  assert.equal(await term.run("accept"), 1);
  assert.deepEqual(term.prompts, ["accept _aitna/grants/one.toml? [y/N] ", "accept _aitna/grants/two.toml? [y/N] "]);
  assert.equal(isAccepted(one.digest, term.store), true);
  assert.equal(isAccepted(two.digest, term.store), false);
  assert.ok(term.out.includes(`_aitna/grants/one.toml: accepted ${ABC_DIGEST.slice(0, 12)}`));
  assert.ok(term.out.includes("_aitna/grants/two.toml: not accepted"));
  assert.equal(await term.run("accept"), 1);
  assert.deepEqual(term.prompts.slice(2), ["accept _aitna/grants/two.toml? [y/N] "]);
  assert.ok(term.out.includes("_aitna/grants/one.toml: already trusted"));
});

test("accept takes only a y or yes, and has no yes flag", async () => {
  const term = terminal({ answers: ["", "yes", "Y"] });
  for (const name of ["a.toml", "b.toml", "c.toml"]) {
    term.grant(name, name);
  }
  assert.equal(await term.run("accept"), 1);
  assert.equal(fs.readdirSync(term.store.acceptedDir).length, 2);
  assert.equal(await term.run("accept", "--yes"), 2);
  assert.match(term.err, /takes no options/);
});

test("accept records what was shown when the file changes before the answer", async () => {
  const term = terminal();
  term.grant("one.toml", "shown\n");
  term.io.ask = async () => {
    term.grant("one.toml", "swapped after the owner looked\n");
    return "y";
  };
  assert.equal(await term.run("accept"), 0);
  const swapped = term.grant("one.toml", "swapped after the owner looked\n");
  assert.equal(fileTrust(swapped, term.store).state, TrustState.CHANGED);
  assert.equal(fileTrust(term.grant("one.toml", "shown\n"), term.store).state, TrustState.TRUSTED);
});

test("revoke by digest prefix or by path", async () => {
  const term = terminal();
  const first = term.grant("one.toml", "abc\n");
  accept(first, term.store, at(1));
  assert.equal(await term.run("revoke", ABC_DIGEST.slice(0, 12)), 0);
  assert.equal(term.out, `revoked ${ABC_DIGEST.slice(0, 12)} (_aitna/grants/one.toml)\n`);
  accept(first, term.store, at(2));
  assert.equal(await term.run("revoke", "_aitna/grants/one.toml"), 0);
  assert.equal(isAccepted(first.digest, term.store), false);
  accept(first, term.store, at(3));
  term.grant("one.toml", "changed\n");
  assert.equal(await term.run("revoke", "_aitna/grants/one.toml"), 0);
  assert.equal(isAccepted(first.digest, term.store), false);
  assert.equal(await term.run("revoke", "_aitna/grants/one.toml"), 2);
  assert.match(term.err, /no accepted version to revoke/);
  assert.equal(await term.run("revoke", "0".repeat(12)), 2);
  assert.equal(await term.run("revoke"), 2);
});

test("accept and revoke with no project root print the notice, exit 2 and change nothing", async () => {
  const term = terminal({ answers: ["y"] });
  const grant = term.grant("one.toml", "abc\n");
  accept(grant, term.store, at(1));
  const lone = posix.join(term.base, "lone");
  fs.mkdirSync(lone);
  term.io.cwd = lone;
  assert.equal(await term.run("accept"), 2);
  assert.match(term.err, /^\[akmon\] no project root at or above /);
  assert.deepEqual(term.prompts, []);
  assert.equal(await term.run("revoke", ABC_DIGEST.slice(0, 12)), 2);
  assert.match(term.err, /^\[akmon\] no project root at or above /);
  assert.equal(term.out, "");
  assert.equal(isAccepted(grant.digest, term.store), true, "nothing was revoked");
  assert.deepEqual(fs.readdirSync(lone), []);
});

test("report prints the summary", async () => {
  const term = terminal();
  assert.equal(await term.run("report"), 0);
  assert.equal(
    term.out,
    "accepts: 0\nre-accepts: 0\nrevokes: 0\nuntrusted digests sighted: 0\n" +
      "sighted digests later accepted: 0\nmedian seconds from sighting to acceptance: -\n",
  );
  const one = term.grant("one.toml", "a\n");
  recordUntrusted(one, term.store, at(0));
  accept(one, term.store, at(30));
  assert.equal(await term.run("report"), 0);
  assert.equal(
    term.out,
    "accepts: 1\nre-accepts: 0\nrevokes: 0\nuntrusted digests sighted: 1\n" +
      "sighted digests later accepted: 1\nmedian seconds from sighting to acceptance: 30.0\n",
  );
  assert.equal(await term.run("report", "extra"), 2);
});

test("usage errors exit two and --help prints the usage", async () => {
  const term = terminal();
  assert.equal(await term.run(), 2);
  assert.equal(await term.run("frobnicate"), 2);
  assert.match(term.err, /unknown command 'frobnicate'/);
  assert.equal(await term.run("--help"), 0);
  assert.ok(term.out.startsWith("usage: akmon trust"));
});
