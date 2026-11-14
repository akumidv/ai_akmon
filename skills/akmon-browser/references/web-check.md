# Checking a web solution under development — scaffold for the inspection verbs

Reference of [`akmon-browser`](../SKILL.md) for a project that builds a web application and wants the
agent to check how a change **looks** and **behaves** in a real browser, not only that the tests pass.
akmon owns the verbs; the project owns the settings, the viewports it cares about and the paths worth
walking. Every step is a Bash verb of `akmon tool browser`, so it works in a script, a gate or a harness
without the MCP server.

The verbs read the project's Chrome (or the attached one) and **never start a Chrome**: when none
answers they say `start` or `attach`. They read the page the user and the agent share, so the window is
the user's: a screenshot emulates a viewport only for the capture and always undoes it, and nothing
here reloads, navigates or clicks. Open the page you want checked first (`akmon tool browser start
--url <dev server>`, or ask the user to open it), then run the verbs below; `--page <n|targetId|url part>`
picks a page other than the first one `pages` lists.

## The settings

`[browser]` in `<dev root>/.akmon.toml`, beside the keys in [`shared-window.md`](shared-window.md):

```toml
[browser]
url = "http://localhost:5173"          # the dev server, if any: the address to pass to `start --url`
redact = ["ssn", "iban"]               # keys to add; the defaults are always redacted

[browser.viewports]                    # name = "WxH" in CSS pixels; each replaces or adds to a preset
phone = "390x844"
wide = "1920x1080"
```

- `url` is a note for the agent and the developer: the address the application runs on while it is
  developed. The verbs read pages from the browser; they do not open it.
- `viewports` extends the presets `desktop` (1440x900), `tablet` (834x1112) and `phone` (390x844); a
  size can also be written inline, `--viewport 1280x720`.
- `redact` lists names (JSON keys, URL query and fragment parameters, form fields, header names) a
  capture replaces with `[redacted]` **at capture**. One rule serves all of them: a name is a secret
  when, lower-cased and without `-`, `_` and `.`, it contains a stem. The floor, always applied, is
  `password`, `passwd`, `pwd`, `secret`, `token`, `apikey`, `auth`, `session`, `cookie`, `jwt`,
  `credential`, `privatekey`, `otp`, `signature`, `csrf`, `xsrf`, `saml`, `assertion`, `accesskey`,
  `subscriptionkey`, `sessid`, `hmac`, `cvv`, `mfacode` and `verificationcode`, so `accessToken`,
  `x-goog-api-key` and `newPassword` are caught; the names `sig`, `code`, `sid`, `pin`, `key`, `nonce`
  and `ticket` are secrets only as the whole name (as stems they would match `monkey` or `encode`);
  your names are added as stems; nothing in the settings can remove a stem. The userinfo of a URL
  (`user:password@host`, also `//user:password@host`) and a `;jsessionid=...` path parameter are
  redacted too, and every URL a verb prints (a page, a tab) goes through the same rule, also inside
  a percent-encoded value or separator (`redirect_uri=...%3Faccess_token%3D...`, once or twice encoded);
  a `data:` URL is content, not an address, and prints as `data:<mime>,…[<n> bytes]`. `logs` text is
  scrubbed by it: the value of a secret-named pair (`k=v`, `"k": "v"`, `'k' => 'v'`, also with escaped
  quotes), the whole value of an `Authorization` header whatever its scheme, every pair of a `Cookie`
  header, and `Bearer` and `Basic` credentials.

Everything the verbs write goes under `<dev root>/.local/.browser/` (`shots/`, `net/`), which is
git-ignored. A recording leaves the machine only on the user's word.

## The look check

A change to markup or style is checked at the sizes and in the schemes the project supports, before and
after:

```
akmon tool browser screenshot --viewport desktop --out before-desktop.png
akmon tool browser screenshot --viewport phone --scheme dark --out before-phone-dark.png
# ... make the change, let the dev server reload ...
akmon tool browser screenshot --viewport desktop --out after-desktop.png
akmon tool browser screenshot --viewport phone --scheme dark --out after-phone-dark.png
```

- A bare `--out` name lands in `<dev root>/.local/.browser/shots/`; a path is relative to the project
  root. With no `--out` the file is `shots/<host>-<viewport>[-<scheme>][-full].png`, overwritten each
  time (no dates in names). The verb prints the path.
- **Read the PNGs** (a viewer that can show an image), compare each before with its after, and say what
  differs: layout, overflow, contrast in the dark scheme, a control that moved or vanished.
  `--full` captures the whole page, not only the viewport.
- `snapshot` is the structural check: the accessibility outline (`role "name" [value]`) shows a
  missing label, a button with no name, a heading out of order. Prefer it to a picture for "is it
  there"; `--text` prints the page's visible text instead.

## The behaviour check

A scripted path, or what the user does in the window, is checked for what the page complained about:

```
akmon tool browser logs --timeout 20             # console messages, exceptions, log entries
akmon tool browser logs --until "ready" --timeout 60
akmon tool browser net --for 20 --failed         # requests with status >= 400, and failures
```

- `logs` prints what the console already holds (with a negative time), then follows. Each line is
  `[<source>] <kind>: <text>`: the source is `page` for a page, and the kind `console.<level>`,
  `exception` or `log.<source>` (network errors, CSP, deprecations); a page that runs an extension also
  shows `[extension]` and `[sw]` lines (see [`extension.md`](extension.md)). With `--until REGEX` it
  stops at the first **new** line whose printed form (`[page] console.error: ...`) matches (exit 0) and
  exits 1 when the time runs out without one; without it, it ends at the timeout (exit 0).
- `net --failed` keeps the requests that failed (CORS, mixed content, a blocked or refused request) or
  answered 400 and above. **`net` reloads nothing**: the traffic comes from the page, from a navigation
  the user asked for, or from what the user does in the window while it listens, so start it, then
  trigger the step.
- Report each finding with the page, the line or request, and the time.

## The API through the frontend

A backend change is checked through the frontend that calls it, and an API that is reachable only behind
the application's sign-in is read the way the page itself reads it:

```
akmon tool browser net --for 30 --bodies --max-body 16384 --out cart-api.json
```

- `--bodies` reads text response bodies up to `--max-body` bytes; a binary body is withheld with a
  note. A JSON body is parsed, redacted by key and written again before it is cut, so a cut never
  leaves part of a secret; a form body is redacted by field. Any other text (HTML, plain text,
  JavaScript, XML) has no names to go by, so it is only scrubbed as `logs` text is, and may still hold
  a secret that carries no name: read such a body as the user's own material.
- The summary shows method, status, resource type, MIME type, size, time and URL; `--json` and `--out`
  carry the entries in full (headers included, redacted) for comparison with the contract: a status, a
  payload shape, a field the page ignores.
- The skill **reads** through the interface. It does not call the application's API itself, from the
  shell or from `eval`; `eval` evaluates one expression in the page to read a value, the DOM or a
  computed style, and never to click, fill or fetch.

## What to put in the project's own skill

Selectors, the pages and paths worth walking, the viewports that matter and any key that is secret in
this application (add it to `redact`) belong in the project's own skill, which links this one.
