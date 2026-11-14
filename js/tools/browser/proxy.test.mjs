import { test } from "node:test";
import assert from "node:assert/strict";

import { hasCredentials, proxyPlan, recordableArguments, stripCredentials } from "./proxy.mjs";

test("the agent's proxy becomes --proxy-server, NO_PROXY the bypass list", () => {
  const plan = proxyPlan({ HTTPS_PROXY: "http://p:3128", NO_PROXY: ".corp.example, localhost,10.0.0.0/8" }, null);
  assert.deepEqual(plan.args, [
    "--proxy-server=http://p:3128",
    "--proxy-bypass-list=*.corp.example;localhost;10.0.0.0/8",
  ]);
  assert.match(plan.describe, /^http:\/\/p:3128 \(bypass: 3 rule\(s\) from NO_PROXY\)$/);
});

test("HTTPS_PROXY wins over HTTP_PROXY over ALL_PROXY, upper case over lower", () => {
  assert.deepEqual(proxyPlan({ ALL_PROXY: "a", HTTP_PROXY: "h", HTTPS_PROXY: "s" }, null).args, ["--proxy-server=s"]);
  assert.deepEqual(proxyPlan({ ALL_PROXY: "a", HTTP_PROXY: "h" }, null).args, ["--proxy-server=h"]);
  assert.deepEqual(proxyPlan({ all_proxy: "a" }, null).args, ["--proxy-server=a"]);
});

test("no proxy in the environment leaves Chrome on the system proxy", () => {
  assert.deepEqual(proxyPlan({}, null), { args: [], describe: "system proxy (none in the environment)" });
});

test("the proxy setting: system, direct or a URL overrides the environment", () => {
  const env = { HTTPS_PROXY: "http://env:1" };
  assert.deepEqual(proxyPlan(env, "system").args, []);
  assert.deepEqual(proxyPlan(env, "direct").args, ["--no-proxy-server"]);
  assert.deepEqual(proxyPlan(env, "http://set:2").args, ["--proxy-server=http://set:2"]);
});

test("credentials in a proxy URL reach Chrome but never the words describing it", () => {
  const plan = proxyPlan({ HTTPS_PROXY: "http://ann:p%40ss@proxy:3128", NO_PROXY: "localhost" }, null);
  assert.deepEqual(plan.args[0], "--proxy-server=http://ann:p%40ss@proxy:3128");
  assert.equal(plan.describe, "http://***@proxy:3128 (bypass: 1 rule(s) from NO_PROXY)");
  assert.equal(proxyPlan({}, "http://u:pw@set:2").describe, "http://***@set:2");
});

test("credentials are stripped with or without a scheme, and a plain proxy is left as it is", () => {
  assert.equal(stripCredentials("http://u:pw@h:1"), "http://***@h:1");
  assert.equal(stripCredentials("u:pw@h:1"), "***@h:1");
  assert.equal(stripCredentials("h:1"), "h:1");
  assert.equal(hasCredentials("http://u@h"), true);
  assert.equal(hasCredentials("http://h"), false);
  assert.deepEqual(recordableArguments(["--x", "--proxy-server=http://u:pw@h:1", "--proxy-bypass-list=a"]), [
    "--x",
    "--proxy-server=http://***@h:1",
    "--proxy-bypass-list=a",
  ]);
});

test("a password with an unencoded /, #, ?, @ or space is still inside the userinfo", () => {
  assert.equal(stripCredentials("http://u:p/w@h:1"), "http://***@h:1");
  assert.equal(stripCredentials("http://u:p#w@h:1"), "http://***@h:1");
  assert.equal(stripCredentials("http://u:p?w@h:1"), "http://***@h:1");
  assert.equal(stripCredentials("http://u:p w@h:1"), "http://***@h:1");
  assert.equal(stripCredentials("http://u:p@w@h:1"), "http://***@h:1");
  assert.equal(hasCredentials("http://u:p/w@h:1"), true);
});

test("Chrome's per-scheme form is stripped segment by segment", () => {
  assert.equal(stripCredentials("http://u:p@h;https=http://u2:p2@h2"), "http://***@h;https=http://***@h2");
  assert.equal(stripCredentials("http=u:p@h:1;https=u2:p/2@h2:2"), "http=***@h:1;https=***@h2:2");
  assert.equal(stripCredentials("http=h:1;https=h2:2"), "http=h:1;https=h2:2");
  assert.equal(hasCredentials("http=h:1;https=u:p@h2:2"), true);
  assert.equal(hasCredentials("http=h:1;https=h2:2"), false);
  const plan = proxyPlan({}, "http://u:p@h;https=http://u2:p2@h2");
  assert.equal(plan.describe, "http://***@h;https=http://***@h2");
  assert.deepEqual(recordableArguments(plan.args), ["--proxy-server=http://***@h;https=http://***@h2"]);
});
