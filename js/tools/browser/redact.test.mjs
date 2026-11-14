import { test } from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_REDACT,
  namesSecret,
  normalizedName,
  REDACTED,
  redactBody,
  redactFloor,
  redactHeaders,
  redactJson,
  redactUrl,
  scrubbedText,
  textualMime,
} from "./redact.mjs";
import { pageTabs, redactedTargets } from "./targets.mjs";

/** Names that a floor of whole-name equality missed in a probe. */
const PROBE_NAMES = ["accessToken", "client_secret", "id_token", "newPassword", "passwd", "sessionId", "jwt"];

test("secret headers are redacted by name, whatever the case, and others are kept", () => {
  const out = redactHeaders({
    Authorization: "Bearer abc",
    Cookie: "sid=1",
    "Set-Cookie": "sid=2",
    "Proxy-Authorization": "Basic x",
    "X-Api-Key": "k",
    "X-CSRF-Token": "t",
    "x-client-secret": "s",
    "Content-Type": "application/json",
    Accept: "*/*",
  });
  assert.deepEqual(out, {
    Authorization: REDACTED,
    Cookie: REDACTED,
    "Set-Cookie": REDACTED,
    "Proxy-Authorization": REDACTED,
    "X-Api-Key": REDACTED,
    "X-CSRF-Token": REDACTED,
    "x-client-secret": REDACTED,
    "Content-Type": "application/json",
    Accept: "*/*",
  });
  assert.deepEqual(redactHeaders(undefined), {});
});

test("JSON keys are redacted at any depth, in arrays too, and the rest is kept", () => {
  const body = {
    user: "ann",
    password: "p",
    nested: { items: [{ Token: "t", id: 1 }, { apiKey: "k" }], ok: true },
    n: null,
  };
  assert.deepEqual(redactJson(body, ["password", "token", "apiKey"]), {
    user: "ann",
    password: REDACTED,
    nested: { items: [{ Token: REDACTED, id: 1 }, { apiKey: REDACTED }], ok: true },
    n: null,
  });
  assert.deepEqual(redactJson([1, "a"], ["a"]), [1, "a"]);
});

test("query values named in the keys are redacted in a URL and a plain fragment is kept", () => {
  assert.equal(
    redactUrl("https://a.example/p?x=1&access_token=abc&y=2#frag", ["access_token"]),
    `https://a.example/p?x=1&access_token=${REDACTED}&y=2#frag`,
  );
  assert.equal(redactUrl("https://a.example/p", ["token"]), "https://a.example/p");
  assert.equal(redactUrl("https://a.example/p?flag&Token=1", ["token"]), `https://a.example/p?flag&Token=${REDACTED}`);
});

test("names compare as letters and digits, so api_key, apiKey and api-key are one", () => {
  assert.equal(normalizedName("API-key"), "apikey");
  assert.ok(namesSecret(["x-api_key"], ["apiKey"]));
  assert.ok(namesSecret(["csrf_token"], DEFAULT_REDACT));
  assert.equal(namesSecret(["email", "city", ""], redactFloor(["ssn"])), false);
});

test("one name rule: a JSON key holding a floor stem is redacted, at any depth, in objects and arrays", () => {
  const body = {
    ...Object.fromEntries(PROBE_NAMES.map((name) => [name, "v"])),
    kept: "yes",
    deep: { list: [{ x_goog_api_key: "k", ok: 1 }, [{ Passwd: "p" }]] },
  };
  const out = /** @type {Record<string, any>} */ (redactJson(body, []));
  for (const name of PROBE_NAMES) {
    assert.equal(out[name], REDACTED, name);
  }
  assert.equal(out["kept"], "yes");
  assert.deepEqual(out["deep"], { list: [{ x_goog_api_key: REDACTED, ok: 1 }, [{ Passwd: REDACTED }]] });
});

test("one name rule: query parameters and a form body, by the same names", () => {
  for (const name of PROBE_NAMES) {
    assert.equal(
      redactUrl(`https://a.example/p?${name}=v&n=1`, []),
      `https://a.example/p?${name}=${REDACTED}&n=1`,
      name,
    );
    const form = redactBody(`${name}=v&n=1`, "application/x-www-form-urlencoded", { keys: [], maxBytes: 100 });
    assert.equal(form.text, `${name}=${REDACTED}&n=1`, name);
  }
});

test("URL userinfo is redacted, and fragment parameters by the same rule", () => {
  assert.equal(redactUrl("https://u:pw@h.example/p?a=1", []), `https://${REDACTED}@h.example/p?a=1`);
  assert.equal(redactUrl("ftp://only@h.example", []), `ftp://${REDACTED}@h.example`);
  assert.equal(redactUrl("https://h.example/a@b?x=1", []), "https://h.example/a@b?x=1");
  assert.equal(
    redactUrl("https://h.example/cb#access_token=abc&id_token=def&state=ok", []),
    `https://h.example/cb#access_token=${REDACTED}&id_token=${REDACTED}&state=ok`,
  );
  assert.equal(
    redactUrl("https://h.example/p?x=1#/route?token=zz", []),
    `https://h.example/p?x=1#/route?token=${REDACTED}`,
  );
  assert.equal(redactUrl("https://h.example/p#section", []), "https://h.example/p#section");
});

test("header names follow the same rule, and the project's keys add to it", () => {
  const out = redactHeaders(
    { "api-key": "1", "x-goog-api-key": "2", "x-auth": "3", "X-Session-Id": "4", "x-badge": "5", Accept: "*/*" },
    ["badge"],
  );
  assert.deepEqual(out, {
    "api-key": REDACTED,
    "x-goog-api-key": REDACTED,
    "x-auth": REDACTED,
    "X-Session-Id": REDACTED,
    "x-badge": REDACTED,
    Accept: "*/*",
  });
});

test("free text loses the value of a secret name, in key=value, JSON and header forms, and a bearer credential", () => {
  const keys = redactFloor(["ssn"]);
  assert.equal(scrubbedText("login failed token=abc123 user=ann", keys), `login failed token=${REDACTED} user=ann`);
  assert.equal(
    scrubbedText('payload {"password": "hunter2", "n": 1}', keys),
    `payload {"password": ${REDACTED}, "n": 1}`,
  );
  assert.equal(scrubbedText("Authorization: Bearer eyJhbGciOi.abc-def", keys), `Authorization: ${REDACTED}`);
  assert.equal(scrubbedText("ssn=078-05-1120&x=1", keys), `ssn=${REDACTED}&x=1`);
  assert.equal(scrubbedText("id_token=a&newPassword=b", keys), `id_token=${REDACTED}&newPassword=${REDACTED}`);
  assert.equal(scrubbedText("go to https://u:pw@h.example/x now", keys), `go to https://${REDACTED}@h.example/x now`);
  assert.equal(scrubbedText("a:token=abc", keys), `a:token=${REDACTED}`);
  assert.equal(scrubbedText("nothing secret here", keys), "nothing secret here");
});

test("the project's keys and its record settings can add stems but never remove one", () => {
  // The floor is applied whatever `keys` holds, even a list that does not carry the defaults.
  assert.equal(/** @type {any} */ (redactJson({ accessToken: "x" }, ["ssn"])).accessToken, REDACTED);
  assert.equal(redactUrl("https://h.example/?id_token=a", ["ssn"]), `https://h.example/?id_token=${REDACTED}`);
  assert.ok(namesSecret(["sessionId"], []));
  // A key the project adds is a stem too, and the floor stays.
  assert.deepEqual(redactFloor(["Pass-WORD", "ssn"]), [...DEFAULT_REDACT, "ssn"]);
  assert.ok(namesSecret(["user_ssn"], redactFloor(["ssn"])));
  // No stem is a bare short word that common names contain.
  assert.equal(DEFAULT_REDACT.includes("key"), false);
  assert.equal(namesSecret(["monkey", "keyboard", "primaryKey"], redactFloor([])), false);
});

test("a JSON body is redacted, then cut; a cut never leaves part of a secret", () => {
  const text = JSON.stringify({ a: "x".repeat(50), password: "hunter2hunter2", b: "y" });
  const shown = redactBody(text, "application/json; charset=utf-8", { keys: ["password"], maxBytes: 80 });
  assert.equal(shown.truncated, true);
  assert.ok(shown.text.length <= 80);
  assert.ok(!shown.text.includes("hunter2"));
  const whole = redactBody(text, "application/json", { keys: ["password"], maxBytes: 1000 });
  assert.equal(whole.truncated, false);
  assert.deepEqual(JSON.parse(whole.text), { a: "x".repeat(50), password: REDACTED, b: "y" });
});

test("JSON that does not parse is withheld, not shown unredacted", () => {
  const shown = redactBody('{"password":"hunter2"', "application/json", { keys: ["password"], maxBytes: 1000 });
  assert.equal(shown.text, "");
  assert.match(String(shown.note), /could not be redacted/);
});

test("a form body and a text body", () => {
  const form = redactBody("user=ann&password=p%40ss", "application/x-www-form-urlencoded", {
    keys: ["password"],
    maxBytes: 100,
  });
  assert.equal(form.text, `user=ann&password=${REDACTED}`);
  const html = redactBody("<p>hi</p>", "text/html", { keys: ["password"], maxBytes: 100 });
  assert.deepEqual(html, { text: "<p>hi</p>", truncated: false, note: null });
});

test("only text and JSON MIME types are textual", () => {
  for (const mime of [
    "text/html",
    "application/json",
    "application/vnd.api+json",
    "application/javascript",
    "text/plain; charset=x",
  ]) {
    assert.equal(textualMime(mime), true, mime);
  }
  for (const mime of ["image/png", "application/octet-stream", "", "font/woff2"]) {
    assert.equal(textualMime(mime), false, mime);
  }
});

test("the key floor is the defaults first, then the project's own, each once whatever its case", () => {
  assert.deepEqual(redactFloor([]), [...DEFAULT_REDACT]);
  assert.deepEqual(redactFloor(["ssn", "PASSWORD", "Ssn", "pass_word"]), [...DEFAULT_REDACT, "ssn"]);
  const shown = redactJson({ password: "x", ssn: "1", name: "n" }, redactFloor(["ssn"]));
  assert.deepEqual(shown, { password: REDACTED, ssn: REDACTED, name: "n" });
});

test("the floor holds the residual stems, in any spelling", () => {
  for (const name of [
    "X-Amz-Signature",
    "csrfmiddlewaretoken",
    "XSRF-TOKEN",
    "SAMLResponse",
    "client_assertion",
    "AccessKey",
    "Ocp-Apim-Subscription-Key",
    "PHPSESSID",
    "hmac",
    "card_cvv",
    "mfa_code",
    "verification_code",
  ]) {
    assert.equal(namesSecret([name], []), true, name);
  }
});

test("exact names are secrets only whole, so the words that contain them are kept", () => {
  for (const name of ["sig", "code", "SID", "pin", "key", "nonce", "Ticket"]) {
    assert.equal(namesSecret([name], []), true, name);
  }
  for (const name of ["monkey", "keyboard", "encode", "shipping", "state", "ticketing", "sigma"]) {
    assert.equal(namesSecret([name], []), false, name);
  }
  assert.equal(redactUrl("https://h/cb?code=abc&state=xyz&q=1", []), `https://h/cb?code=${REDACTED}&state=xyz&q=1`);
  assert.deepEqual(redactJson({ code: "c", monkey: 1 }, []), { code: REDACTED, monkey: 1 });
});

test("a path parameter and a protocol-relative userinfo are redacted", () => {
  assert.equal(redactUrl("https://h/a;jsessionid=XYZ;v=2/b?q=1", []), `https://h/a;jsessionid=${REDACTED};v=2/b?q=1`);
  assert.equal(redactUrl("//u:pw@h/p", []), `//${REDACTED}@h/p`);
  assert.equal(redactUrl("https://u:pw@h/p#access_token=t", []), `https://${REDACTED}@h/p#access_token=${REDACTED}`);
});

test("an Authorization header loses its whole value, whatever the scheme", () => {
  assert.equal(scrubbedText("Authorization: Token abc123", []), `Authorization: ${REDACTED}`);
  assert.equal(scrubbedText("Proxy-Authorization: Negotiate YII xyz", []), `Proxy-Authorization: ${REDACTED}`);
  assert.equal(
    scrubbedText('{"Authorization": "Token abc 123", "a": 1}', []),
    `{"Authorization": ${REDACTED}, "a": 1}`,
  );
  assert.equal(scrubbedText("authorization=Digest u=1, r=2\nnext", []), `authorization=${REDACTED}\nnext`);
});

test("a Cookie header loses the value of every pair", () => {
  assert.equal(scrubbedText("Cookie: a=b; c=d", []), `Cookie: ${REDACTED}; c=${REDACTED}`);
  assert.doesNotMatch(scrubbedText("Set-Cookie: sid=1; Path=/; HttpOnly", []), /sid=1/);
  assert.doesNotMatch(scrubbedText('"cookie": "x=1; y=2; z=3"', []), /[xyz]=\d/);
});

test("a PHP-style pair and a pair with escaped quotes lose a secret value", () => {
  assert.equal(
    scrubbedText("['password' => 'hunter2', 'user' => 'ann']", []),
    `['password' => ${REDACTED}, 'user' => 'ann']`,
  );
  assert.equal(
    scrubbedText(String.raw`{\"api_key\": \"a b c\", \"x\": 1}`, []),
    `{\\"api_key\\": ${REDACTED}, \\"x\\": 1}`,
  );
  assert.equal(scrubbedText(String.raw`{"token": "a\"b", "x": 1}`, []), `{"token": ${REDACTED}, "x": 1}`);
  assert.doesNotMatch(scrubbedText(String.raw`{\'secret\': \'s3\'}`, []), /s3/);
});

test("a text body that is neither JSON nor a form is scrubbed, then cut", () => {
  const how = { keys: [], maxBytes: 1000 };
  const html = redactBody('<script>var cfg = {"token": "abc"}; Authorization: Token zzz</script>', "text/html", how);
  assert.doesNotMatch(html.text, /abc|zzz/);
  assert.equal(html.note, null);
  assert.equal(redactBody("a".repeat(50), "text/plain", { keys: [], maxBytes: 10 }).truncated, true);
});

/** The text a live check recorded for a page whose URL was a `data:` URL (Chrome 157). */
const LIVE_LOG_TEXT =
  "Access to fetch at 'https://example.org/x?access_token=[redacted]&q=1' from origin 'null' has been blocked by CORS policy: … " +
  "(data:text/html,%3Ctitle%3Elive…console.log(%22hello%20token%3Dabc123%20ok%22)%3BsetInterval(()%3D%3Efetch(%22https%3A%2F%2Fexample.org%2Fx%3Faccess_token%3DSECRET1%26q%3D1%22)…)";

test("the live log text loses both percent-encoded secrets and keeps its readable parts", () => {
  const out = scrubbedText(LIVE_LOG_TEXT, []);
  assert.doesNotMatch(out, /abc123|SECRET1/);
  assert.match(
    out,
    /^Access to fetch at 'https:\/\/example\.org\/x\?access_token=\[redacted\]&q=1' from origin 'null'/,
  );
  assert.match(out, /has been blocked by CORS policy: … \(data:text\/html,…\[\d+ bytes\]\)$/);
});

test("secret pairs whose separators are percent-encoded, once or twice, lose their value in free text", () => {
  assert.equal(
    scrubbedText("log(%22hello%20token%3Dabc123%20ok%22)", []),
    `log(%22hello%20token%3D${REDACTED}%20ok%22)`,
  );
  assert.equal(scrubbedText("x%3Faccess_token%3DSECRET1%26q%3D1", []), `x%3Faccess_token%3D${REDACTED}%26q%3D1`);
  assert.equal(scrubbedText("a%2526code%253DZZ%2526b%253D1", []), `a%2526code%253D${REDACTED}%2526b%253D1`);
  assert.equal(scrubbedText('"token"%3A"x" next', []), `"token"%3A${REDACTED} next`);
  assert.equal(scrubbedText("%22token%22%3A%22y%22%2C%22n%22%3A1", []), `%22token%22%3A${REDACTED}%2C%22n%22%3A1`);
  assert.equal(scrubbedText("TOKEN%3dabc%26q%3d1", []), `TOKEN%3d${REDACTED}%26q%3d1`);
});

test("a non-secret encoded parameter stays readable", () => {
  assert.equal(scrubbedText("a%3Fq%3D1%26page%3D2", []), "a%3Fq%3D1%26page%3D2");
  assert.equal(
    redactUrl("https://a.example/p?next=%2Fhome%3Fq%3D1%26page%3D2", []),
    "https://a.example/p?next=%2Fhome%3Fq%3D1%26page%3D2",
  );
});

test("an OAuth redirect_uri that carries an encoded access_token is redacted inside the encoding", () => {
  assert.equal(
    redactUrl("https://idp.example/auth?redirect_uri=https%3A%2F%2Fapp%2Fcb%3Faccess_token%3DX9%26q%3D1&n=2", []),
    `https://idp.example/auth?redirect_uri=https%3A%2F%2Fapp%2Fcb%3Faccess_token%3D${REDACTED}%26q%3D1&n=2`,
  );
  assert.equal(
    redactUrl("https://idp.example/auth?returnTo=https%253A%252F%252Fapp%252Fcb%253Faccess_token%253DX9", []),
    `https://idp.example/auth?returnTo=https%253A%252F%252Fapp%252Fcb%253Faccess_token%253D${REDACTED}`,
  );
  assert.equal(
    redactUrl("https://app.example/#state=%7B%22token%22%3A%22z9%22%7D", []),
    `https://app.example/#state=%7B%22token%22%3A${REDACTED}%7D`,
  );
  assert.doesNotMatch(redactUrl("https://a/p?next=%2Fcb%3Fsid%3DABC", []), /ABC/);
});

test("a data: URL is shown as its MIME type and size, never its payload", () => {
  assert.equal(redactUrl("data:text/html,%3Ctitle%3Ex", []), "data:text/html,…[12 bytes]");
  assert.equal(redactUrl("data:text/html;base64,PGI+", []), "data:text/html,…[4 bytes]");
  assert.equal(redactUrl("data:,token=abc", []), "data:,…[9 bytes]");
  assert.equal(redactUrl("data:text/html,…[12 bytes]", []), "data:text/html,…[12 bytes]");
  assert.equal(redactUrl("blob:https://a.example/id?token=1", []), `blob:https://a.example/id?token=${REDACTED}`);
  assert.equal(
    scrubbedText("see (data:text/html,%3Ctitle%3Ex%3C%2Ftitle%3E) done", []),
    "see (data:text/html,…[26 bytes]) done",
  );
  assert.equal(scrubbedText("{data: 1} metadata:x/y", []), "{data: 1} metadata:x/y");
  const once = scrubbedText("(data:text/html,abc)", []);
  assert.equal(scrubbedText(once, []), once);
});

test("a tab and a target whose URL is a data: URL or an encoded nested URL list without the payload or secret", () => {
  const list = [
    { id: "T1", type: "page", title: "live", url: "data:text/html,%3Ctitle%3Elive%3C%2Ftitle%3Etoken%3Dabc123" },
    {
      id: "T2",
      type: "page",
      title: "idp",
      url: "https://idp.example/a?redirect_uri=https%3A%2F%2Fapp%2Fcb%3Faccess_token%3DX9",
    },
  ];
  assert.deepEqual(pageTabs(list, []), [
    { title: "live", url: "data:text/html,…[43 bytes]" },
    { title: "idp", url: `https://idp.example/a?redirect_uri=https%3A%2F%2Fapp%2Fcb%3Faccess_token%3D${REDACTED}` },
  ]);
  assert.equal(redactedTargets(list, [])[0].url, "data:text/html,…[43 bytes]");
});
