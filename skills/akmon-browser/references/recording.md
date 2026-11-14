# Recording a session — scaffold for debugging together

Reference of [`akmon-browser`](../SKILL.md) for the scenario where **the user plays the customer in the
web application and the agent watches**: the user drives the shared Chrome, the agent records what
happens and, when the user says "now", reads the moment that went wrong. akmon owns the mechanics; the
project owns the settings below. The agent stays passive: recording only listens. It clicks nothing,
types nothing and sends nothing to the site.

The agent does not run this itself when it is a delegated agent or an `autonomous` run (see
[the skill](../SKILL.md)): the developer's main session does, or the user runs the commands.

## The loop

1. **Start.** `akmon tool browser record start [--name NAME]` launches a recorder that **outlives the
   command** and returns at once, printing the recording's name and how to mark and stop. The name
   defaults to `rec-<n>`. One recording runs at a time per project; a second `start` is refused and
   names the one that runs. Chrome must already run (`start`) or be attached (`attach`).
2. **The user drives.** They work through the scenario in the window. The agent does not touch the
   page; it can read the recording as it grows.
3. **"Now."** When something goes wrong the user says so, and the agent runs
   `akmon tool browser record mark "what happened"`. The mark is stamped on the recording's own clock
   (the recording's start time is kept in `<dev root>/.local/.browser/recording.json`), so it lines up
   with the actions and requests around it.
4. **Read the moment.** `akmon tool browser record export --around last` prints the timeline from 15
   seconds before the mark to 15 seconds after (`--window SECONDS`, `--around N` for the Nth mark,
   numbered from 1). Each line is a relative time, a kind and one line of text. A request is shown under
   the action that preceded it, so the click, the request it caused, the answer and the error read as one
   story. `--json` prints the same events as data.
5. **Stop.** `akmon tool browser record stop` ends the recorder, takes the listener out of the page where
   it can, and prints a summary: events by kind, marks, failed requests and exceptions. `record status`
   says what runs; `record list` shows the recordings that are kept.
6. **Analyse.** What to look for: the failing or slow call, a payload that does not match what the
   screen shows, an error the UI swallowed, a request the action should have caused and did not.
   Report the evidence with the time and the line it came from.
7. **Delete when done.** `akmon tool browser record delete <name>` removes that recording's folder and
   nothing else.

## What is captured

| Kind | What it holds |
|---|---|
| `page`, `navigation` | the page and its URL, each navigation of the main frame (and same-document ones such as a route change); query values whose names are on the redact list are replaced |
| `click`, `submit`, `keydown` | **where** it happened: the element's tag, role, accessible name, `data-testid` / `data-test` / `data-qa`, `id`, `name`, label, a text snippet of at most 60 characters and a CSS path; `keydown` only for Enter, Escape and Tab |
| `input`, `change` | the field's identity, its type and the **length** of what was typed; for a checkbox or radio, whether it is checked; a field marked `sensitive` has no length either |
| `console`, `exception`, `log` | what the page's console, uncaught exceptions and browser log say, with secret-looking `key=value` pairs and bearer credentials replaced |
| `net` | method, URL, status, type, timing, failure, and request and response headers; **bodies only with `--bodies`** |
| `mark`, `start`, `stop`, `warning`, `error` | the user's marks, and the recording's own beginning, end and problems |

Every event carries `t`, the milliseconds from the start of the recording at which the thing began (a
request is written when it ends, stamped when it began, so the file is not in time order and `export`
sorts it), and `page`, a label (`p1`, `p2` …) for the page it happened on.

## What is never captured

- **A typed value.** Not the text of a field, not a password, not a one-time code, not the content of a
  rich-text editor. Only the field and how much was typed.
- **A secret field at all:** a password field, a field whose `autocomplete` holds `password` or
  `one-time-code`, and a field whose name, id or label matches the redact list is marked `sensitive`,
  and its length is dropped too.
- **A secret in a header, a URL or a body.** `Authorization`, cookies and token-like headers, and the
  keys of the redact list in query strings, JSON bodies and form bodies, are replaced **at capture**,
  before an event is written, never afterwards. A body that is neither JSON nor a form (HTML, multipart,
  plain text) is not kept, because it cannot be redacted reliably; a note says so.
- **Anything from outside the page's own traffic:** no screenshots, no cookies, no storage.

The redaction floor (names containing `password`, `passwd`, `pwd`, `secret`, `token`, `apikey`, `auth`,
`session`, `cookie`, `jwt`, `credential`, `privatekey`, `otp`, `signature`, `csrf`, `xsrf`, `saml`,
`assertion`, `accesskey`, `subscriptionkey`, `sessid`, `hmac`, `cvv`, `mfacode` or `verificationcode`,
or exactly `sig`, `code`, `sid`, `pin`, `key`, `nonce` or `ticket`, for JSON keys, query and fragment
parameters, form fields and header names alike, and the userinfo and `;jsessionid=` parameters of a
URL) is fixed. `[browser] redact`
adds names; nothing, including `[browser.record]`, lowers it.

## Settings — the project decides

`[browser.record]` in `<dev root>/.akmon.toml` sets what a recording keeps by default. The user decides
this for their scenario; akmon ships these defaults.

| Key | Default | Meaning |
|---|---|---|
| `bodies` | `false` | keep request and response bodies (JSON and forms only, redacted, capped) |
| `max_body` | `65536` | the cap of one body, in bytes |
| `all_pages` | `false` | record every page, and pages that open later, instead of the one |

```toml
[browser.record]
bodies = true
max_body = 16384
```

A flag of `record start` overrides a setting for one recording: `--bodies`, `--max-body BYTES`,
`--all-pages`, or `--page <index|targetId|URL part>` for one page (which beats `all_pages`). Add the
project's own secret field names to `[browser] redact`, for example `ssn`, so they are redacted in
URLs and bodies and recognised as sensitive fields.

## Where recordings live, and who sees them

A recording is a folder, `<dev root>/.local/.browser/recordings/<name>/`, holding `events.jsonl` (one
JSON event per line), the recorder's log and any draft test exported from it. It is in the project's
local layer, which is git-ignored. It stays on this machine. **Nothing leaves the machine without the
user's say-so**: do not paste a recording into a ticket, a chat or a pull request, and do not send it to
a service, unless the user asked for that. It is deleted on request, or when the user says it is done.

Even redacted, a recording shows what a person did and saw: treat it as the user's own material.

## A draft end-to-end test

`akmon tool browser record export [NAME] --test playwright [--out PATH]` writes a draft `*.spec.ts`,
by default into the recording's folder, with one `test()` that follows the first page:

- locators in this order: `getByTestId`, `getByRole` with its name, `getByLabel`, `getByText` for a
  short text, else `locator('<css path>')` with a `// TODO: a stable locator` comment;
- `fill` with a placeholder for typed values (never the value), and `process.env.<NAME>` for a
  sensitive field;
- `waitForResponse` for the first request each action caused (an XHR or fetch to the page's own origin
  within two seconds, before the next action), with its recorded status;
- `expect(...)` placeholders after navigations and at marks.

It is a **draft for the project's own runner**: check each locator, fill in the values, write the
assertions the TODO lines ask for, and run it with the project's test command. The recording says what
the user did; the draft cannot know what they expected.

## Under WSL with a Windows Chrome

Only a Windows process reaches a Windows Chrome's DevTools port, so the Chrome side of the recorder
runs through Windows `node` (the same helper the inspection verbs use) and streams its events back to
the recorder, which stamps and appends them; the redaction has happened before they leave Windows. A
missing Windows `node` is one line naming it.

## Failure modes

- **`record start` says no Chrome answers.** Start or attach one first.
- **The recorder ended by itself.** Chrome was closed, or the page was. `record stop` still prints the
  summary and clears the state; `record start` also clears a stale state by itself.
- **No actions are recorded, but requests are.** The page blocks the listener (a strict page) or the
  document was replaced; a `warning` event says so. Navigations, console and network are still
  recorded.
- **A recorder that does not stop** is killed after 15 seconds and the line says so; the listener
  stays in the open page until it reloads and reports to nothing.
