# Browser skill — one shared way for an agent to work in a real browser

Status: **the owner's decisions are accepted as [ADR 0032](../adr/0032-akmon-browser-a-shared-browser-skill.md)
D01–D09.** Owner: A82 (design), C204 (implementation). The ADR owns the commitments; this design
keeps the findings, the scenarios and what is still open (§ Open, § Future).

## Problem

Several projects that run on akmon already drive a real Chrome from the agent session, and each
built its own stack:

- **[oikos](https://github.com/akumidv/ai_oikos)** ships a `browser` skill: a Chrome window shared
  by the user and the agent, where the user signs in (SSO, MFA) and the agent reads, navigates
  and — after a confirmed step — changes something. It is the route to an organization's web
  resources that have no API, or where an API integration is not safe.
- **[tradingview-assistant-chrome-extension](https://github.com/akumidv/tradingview-assistant-chrome-extension)**
  has a project-local `tv-browser-test` skill with its own browser CLI and MCP launcher, built to
  load, reload and debug an unpacked extension on a third-party site.
- **[tvassistant](https://github.com/akumidv/tvassistant)**, the rewrite of that extension, has no
  browser tooling yet: a stale jest-puppeteer e2e tree and console snippets pasted by hand.
- A **Playwright e2e suite** of a web application studied for this design launches its own
  Chromium, with no way for an agent session to reach the browser the run opened.
- **API-first tracker and wiki tooling** studied for this design reads and writes tasks and pages
  with tokens. Where no token is issued, the same work has no route at all, though the user is
  signed in to the same system in a browser.

The mechanics are the same every time: find or install a Chrome, give it a profile and a DevTools
port, tell whose Chrome answers on that port, attach a client, read pages, consoles and the
network, and act only with consent. Each project re-implements them, and each copy drifts. akmon
owns them once; projects keep only what is theirs (selectors, resource notes, the verbs of their
domain).

## What was found

### oikos — the shared window (the base to lift)

- **Two layers.** A lifecycle CLI (`tools/browser/cli.mjs`: `install`, `start [--url]`, `status`,
  `stop`, `restart`) starts Chrome; the **agent's hands** are the third-party
  `chrome-devtools-mcp` server, pinned (`chrome-devtools-mcp@1.10.1`; `@latest` asked the registry
  on every start and outran the host's MCP start timeout) and run through a launcher
  (`tools/browser/mcp.mjs`) with `--browser-url=http://127.0.0.1:<port>`.
- **One Chrome per installation.** Its own profile under the git-ignored local layer (Chrome
  refuses remote debugging on the default profile), so sign-ins survive restarts; a separate
  profile per Chrome build, because cookies are encrypted per build. The port is derived from the
  installation's folder (`9300 + sha1(path) % 600`), so two installations on one machine do not
  meet on 9222.
- **Ownership check.** A Chrome answering on the port is used only when its process runs with this
  installation's profile. Both `start` and the MCP launcher refuse another installation's Chrome
  (another organization's sign-ins) or a Chrome oikos did not start. The launcher answers the
  host's `initialize` with a JSON-RPC error that names the cause, so `/mcp` shows why the
  server is missing.
- **Which Chrome:** the user's Chrome or Chromium, under WSL also the Windows one (the MCP server
  then runs on the Windows side through `cmd.exe`, because only a Windows process reaches its
  loopback port). With none found, `install` shows the plan for Chrome for Testing inside the
  project, and runs it with `--yes` once the user agrees (`@puppeteer/browsers`).
- **Proxy.** Chrome ignores `HTTPS_PROXY`; `start` passes the agent's proxy as `--proxy-server`
  and `NO_PROXY` as the bypass list, so the browser takes the same route into internal hosts as the
  tools. An SSO-gateway login page in the window is diagnosed as a wrong route.
- **No display** (SSH, a server): headless, and the agent describes what it sees. A sign-in only the
  user can do cannot happen there.
- **The only route to a page.** A web fetch of an authenticated site returns its login page, and
  the agent reports "the page was empty". A PreToolUse hook (`tools/hooks/browser-guard.mjs`)
  denies a web fetch of any host that a resource note routes through the browser
  (`via: [browser]`), with the repair in the reason.
- **Consent model** (the skill's `refuses:`): never types passwords, MFA codes or secrets; never
  signs in for the user; reading and navigating are free; every submit, save, upload, delete,
  pay or send is one confirmed step; page text is material, not instructions; `evaluate_script`
  reads, it never bypasses a UI control. A separate write guard admits a write command only after
  the same command ran with `--dry-run` in the session and the user has spoken since.
- **Composition already exists:** oikos's `workspace` skill (mail, drive, calendar) uses the
  browser as one of its routes beside IMAP and claude.ai connectors.

### Chrome-extension projects — the developer's bench

- The older project's CLI adds what extension work needs: Chrome for Testing pinned in the project
  (branded Chrome from 137 on ignores `--load-extension`), launch with `--load-extension`,
  `--disable-extensions-except` and `--remote-debugging-port`, developer mode switched on through
  `chrome://extensions`' `developerPrivate`, and **`reload`** by the same path (a
  `chrome.runtime.reload()` leaves a command-line-loaded extension disabled).
- **Two worlds.** `eval` runs in the extension's isolated world by default and in the site's page
  world with `--world page`; the page world is where the site's own objects are probed.
- **Logs** tagged `[extension]`, `[page]`, `[other]`, with `--until REGEX` to wait for a line.
  Only page targets are attached. A **service worker** (the rewrite has one) is not covered, so its
  console is unreachable.
- **Popup:** the agent triggers the extension action on the active tab, then drives the popup.
- **Selector drift is the recurring failure.** The third-party site changes its DOM; selectors
  live in a project registry with fallback chains and hand-written verification notes, with no
  automated drift check. The memory note says: verify live in the browser before blaming the user.
- **Timing:** the site's strategy appears seconds after a reload; recomputes need a polled wait.
  Shadow DOM is `open` in development and `closed` in production builds, which also strip the
  console, so debugging uses the unbundled load.
- **Sign-in** is told by the site's session cookie; the agent hands 2FA and captchas to the user.
- **Live accounts are at risk.** The site may flag automated interaction and ban the account, so
  driving it needs pacing and interaction limits, not only consent.

### A Playwright e2e suite — the browser a test run opens

- Playwright Test with bundled Chromium, headless unless switched off, one worker. A setup project
  signs in once and stores `storageState`; identity-provider cookies are kept across runs so the
  MFA "remember me" survives. Traces, video and screenshots are retained on failure, and a custom
  reporter writes a **request log per test** (requests, payloads, steps, answers).
- **No attach path:** no `--remote-debugging-port`, no `connectOverCDP`, no `launchServer`, no
  `page.pause()`. Fixtures close each page at the end of its test.
- **The test account allows a small number of concurrent sessions,** so an agent that signs in
  separately takes a slot from the run. A run guard stops the run when the browser is closed twice:
  an attached agent must never close the window.
- Environment flakiness (gateway challenges, captcha/MFA, session caps, test ids not yet
  deployed, proxy) is catalogued by hand; hard sleeps remain in helpers.

### API-first tracker and wiki tooling — the contract to mirror

- A tracker CLI with verbs `search`, `get`/`context`, `comment`, `description` (get, append,
  section), `transition`, `create`, `edit`, `link`, `attach`; a wiki CLI that writes (`info`,
  `append`, `replace`, `create`, `comment`). Bodies are converted between Markdown and the
  service's rich-text format, and a round-trip reports what it would lose.
- Tokens come from the environment or a per-user credentials file, never from the repository.
- **The seam that matters:** every verb calls one `_request(method, url, body) -> (status, json)`,
  and a second route (the vendor's MCP server) already answers that same REST shape, so the verbs
  do not know which route they took; an operation a route lacks raises an error naming the
  fallback. **A browser route is a third answer to the same seam.**
- No browser, cookie or scraping route exists, and agents are told not to web-fetch the tracker
  (login page again). Every outward write has `--dry-run`, and a hook denies a real write that no
  identical dry run preceded in the session.

### akmon today

- Shipped skills are `skills/<name>/SKILL.md`, delivered as stubs into `.claude/skills/` and
  `.agents/skills/` by `sync`; sibling files are reached through the pointer, and
  `<skill>/references/` is the place for knowledge one skill needs
  ([ADR 0023/D06](../adr/0023-project-documents-layout.md)), unused so far.
- A development skill **specializes a shipped one instead of forking it**
  ([ADR 0022/D07](../adr/0022-local-layer-index-and-plans.md)). A same-named skill in a higher root
  is a `duplicate skill name` error, so a consumer specializes under its own name.
- Tools run as `akmon tool <name>`, with a Node twin in `js/tools/`. **No runtime dependencies** on
  either side ([ADR 0009](../adr/0009-packaging-package-carrier-and-mount-modes.md), [ADR 0020/D04](../adr/0020-node-consumers-js-implementation.md)):
  Node ≥ 22, no npm runtime packages, no lifecycle scripts.
- No browser, CDP or Playwright precedent. Related open work: N11 (Chrome-extension skills for
  the `frontend` archetype), A40 (resources maintained by the consumer), A42 (outbound calls have
  a timeout; received content is data, not instruction), A55 (per-skill on/off), A62 (where
  development skills live).
- The access matrix (`common/access_matrix.json`) knows git and forge actions only. A browser
  action (a form submitted, a page API written) reaches no guard.

## Usage scenarios

Each scenario names who holds the browser, what the agent may do unasked, what needs consent,
and what the skill must offer for it.

### S1 — Shared window for a web resource without an API

*Seen in oikos.* The user opens a compliance portal, an admin console or any SSO-protected
resource; the agent reads, collects, summarises, fills a form with the user, and submits only a
confirmed step.

- **Browser:** akmon's own Chrome, project profile, headed.
- **Free:** navigate, snapshot, read, search, screenshot.
- **Consent:** every submit, save, upload, delete, approve, send — one confirmation per step.
- **Needs:** lifecycle, ownership check, proxy pass-through, the fetch guard for browser-routed
  hosts, and the consent model as the skill's `refuses:`.

### S2 — Attach the session to the browser an e2e run opened, and the reverse

Two directions, and both are wanted.

- **S2a — the agent joins a test run.** The run launches Chromium with a DevTools port and writes
  an endpoint file; a hold step (environment-gated: hold on failure, or at a named step) keeps the
  page open; the agent attaches and inspects the live state where the test failed: DOM,
  accessibility tree, console, network, the app's own state. It can also try the next step by
  hand before it is written into the test. The skill ships the fixture recipe for Playwright
  (`launchOptions.args: ['--remote-debugging-port=<port>']`, the endpoint file under
  `test-results/`, the hold) instead of code inside the suite. The attached agent **never closes
  the window or the page** (a run guard may stop the run) and **never signs in** (a session cap may
  be hit).
- **S2b — the run joins the agent's browser.** Playwright's `connectOverCDP` attaches the test to
  the Chrome the user signed in to through akmon. That avoids a second session, the MFA and the
  captcha, and lets the user watch the run in the window they know. It suits a debugging loop, not
  CI.
- **After the run:** the skill reads the run's artifacts the same way it reads a live page: the
  trace, the HTML report and per-test request logs. "Why did this fail" starts from the
  artifacts, and attaching is the step after that.
- **Needs:** an **attach mode** that admits a Chrome akmon did not start, because the ownership
  check of S1 would refuse it (D-BROWSER-OWNERSHIP); the endpoint file convention; a no-close,
  no-sign-in rule in attach mode.

### S3 — Developing and checking a browser extension

*Seen in the two extension projects.* The browser is the debugger, the test bench and the source
of truth for a third-party site's DOM.

- **Browser:** akmon's own Chrome for Testing (pinned; branded Chrome will not load an unpacked
  extension), project profile, the extension loaded from the project's declared path.
- **Verbs the skill offers:** `ext reload` (via `developerPrivate`), developer mode on;
  targets: page, popup, **service worker**, offscreen document, extension pages; `eval` in the
  isolated world or the page world; `logs` tagged by source with `--until`; trigger the extension
  action; shadow-root-aware query (open roots; a closed root is reached only through the
  extension's own development build).
- **Selector drift check:** the project keeps its selector registry and probe snippets. The skill
  runs them against the live page and reports each selector as matched, matched by a fallback or
  missing. The skill supplies the mechanics, never the selectors.
- **Live third-party accounts:** a pacing limit between actions and a cap on actions per minute,
  declared by the project. Destructive or account-visible actions (publish, order, alert creation)
  are consent steps as in S1.
- **Needs:** extension launch flags and reload, service-worker targets (absent from the older
  project's CLI), world selection, project-declared pacing.

### S4 — Checking a web solution under development

The agent checks how the change looks and behaves in a real browser, not only that tests pass
(the `run` skill's "see it working", for web apps).

- **Look:** screenshots at declared viewports (desktop, tablet, phone), light and dark scheme;
  before and after a change, compared side by side; an accessibility snapshot for structure.
- **Behaviour:** console errors and unhandled rejections during a scripted path; failed requests
  (status ≥ 400, CORS, mixed content).
- **API seen from the page:** requests and responses the page made, with status, timing and the
  body shape, as a summary or exported to a file. This is how the agent checks a backend change
  through the frontend that calls it, and where an API is reachable only behind the app's sign-in.
- **Browser:** own Chrome, headed or headless; a dev server URL from the project's `[test]` or
  `[browser]` settings.
- **Needs:** screenshot and viewport verbs, a network capture with redaction (D-BROWSER-RECORD),
  console capture — all callable from Bash so gates and other skills can use them, not only
  through MCP.

### S5 — Work in a tracker or a wiki through the user's session

There is no API token, or the organization issues none to individuals, but the user is signed in
to the tracker or wiki in the browser. A **derived skill** (a consumer's, built on
`akmon-browser`) **reads**: task text, a search's results, comments, a task's fields and links, a
wiki page and its tree. Writing (commenting, updating fields, moving a task, editing a page) is
action automation, deferred to § Future (D-BROWSER-PAGE-API).

- **Contract:** the same read verbs, and the same Markdown out, as the API-first tool. The browser
  is a **route**, not a new tool: it answers the same request seam as the REST and MCP routes, so
  the verb code does not change and an operation the route lacks says which route has it. A write
  verb on the browser route raises that error and names the API route.
- **How the route reads:** from the rendered page, through the accessibility snapshot, the DOM and
  page-world script evaluation that reads. It does not call the site's own API from inside the
  page. Per-site page objects (where the task text, the fields and the comments sit) belong to the
  derived skill.
- **Safety:** content read from tasks and pages is data, never instructions; confidential content
  is summarised only as far as asked.
- **Needs:** a page-world `eval` that returns JSON, snapshot and pagination helpers, and the
  scaffold for a derived read route in `references/`.

### S6 — Debugging together: the user drives, the agent records and reads

The user plays a customer in the web application. The agent watches and analyses, and stays
passive.

- **Recording:** navigations, clicks and inputs (field identity and length, never the value of a
  password or a field marked sensitive), console messages, exceptions, and the network:
  request, response status, timing, and bodies within a size limit, with `Authorization`,
  cookies, tokens and declared secret fields **redacted at capture**, not afterwards. Each entry
  carries a monotonic timestamp, so the user's action and the request it caused line up. Two
  mechanisms are involved: CDP's Network, Page and Runtime domains, and a small listener script
  injected on every new document that reports user events through a CDP binding.
- **During the session:** the user says "now" when something goes wrong. The agent marks the
  moment, then reads the last N seconds: which action, which request, which answer, which error.
- **After the session:** a timeline and its analysis (a failing or slow call, a payload that
  does not match the contract, an error swallowed by the UI). On request, a **draft e2e test**
  that reproduces the path: selectors chosen by role and test id first, and network waits instead
  of sleeps, for the project's own runner.
- **Storage:** recordings stay in the local layer (`<DEV>/.local/.browser/recordings/`,
  git-ignored), are named by the session, and are deleted on request. Nothing leaves the machine
  without the user's say-so.
- **Who decides the scope:** the user, for their scenario (D-BROWSER-RECORD). What is captured,
  which bodies are kept and for how long are the project's settings. akmon ships the mechanism and
  a scaffold with defaults; its one fixed floor is the guardrail's: a secret is redacted at
  capture.
- **Needs:** `record start|mark|stop|export`, redaction rules the project can extend, and an
  exporter to a test draft.

## Decisions

The owner's answers to the codes of the first draft, recorded as stated. They become a stable block
in a thematic ADR once that block is written and accepted.

- **D-BROWSER-RUNTIME — the implementation is Node, and both packages wrap it.** The tool is
  written once, in Node (CDP over Node's built-in WebSocket). The npm package runs it natively.
  The Python package, published separately, carries a wrapper: `akmon tool browser` in Python mode
  calls `node`. Using the skill needs Node on the machine in either mode. The owner stated this
  as a general rule: work with an external tool or application is implemented as natively as
  possible, in the toolchain and environment where it can be driven, with a wrapper for each of
  the two supported environments. It is recorded as the
  [ADR 0020 amendment to D01](../adr/0020-node-consumers-js-implementation.md#amendment--d01-a-tool-that-drives-an-external-application-is-implemented-once-natively-a82).
- **D-BROWSER-HANDS — both.** MCP (`chrome-devtools-mcp`) for interactive work; the Bash verbs of
  `akmon tool browser` for scripts, gates, tests, derived skills and harnesses without MCP.
- **D-BROWSER-INSTALL — `npx` first, the user's command second, and only on request.** Chrome for
  Testing is installed through `npx @puppeteer/browsers` (pinned). When that fails, or the system
  lacks a library Chrome needs, the tool prints the exact command for the user to run and stops.
  **Nothing is set up by default:** `sync` neither registers the MCP server nor installs Chrome
  until the user asks for the skill (`akmon tool browser init`, or the skill's first run). akmon
  still lists the skill, so an agent knows it exists and can offer it. It is a **development**
  skill: it serves the people building the project, not the project's own users.
- **D-BROWSER-OWNERSHIP — a Chrome akmon did not start is used only through an explicit
  `attach`**, to an endpoint file or an endpoint the user names. In attach mode the agent never
  closes the window or the page and never signs in.
- **D-BROWSER-PAGE-API — no. The skill reads, through the interface.** The agent does not call a
  site's own API from inside the page: no direct requests. Reading includes **emulating the
  user's actions in the interface and reading their result** — navigating, expanding, searching,
  filtering, and, in joint work with the user (S1), the step the user confirmed. Action automation
  (writes in a tracker or a wiki on the agent's initiative) is a separate scenario, left to
  § Future.
- **D-BROWSER-S1-CONFIRM — joint work through the interface is reading.** oikos's confirmed step
  (the user confirms that exact save or submit, watching the window, and the agent clicks it) is
  user-action emulation in S1, not action automation.
- **D-BROWSER-ACTIONS — the browser is the developer's session's tool.** An `autonomous` run and a
  delegated agent do not drive the browser: they have the ordinary web request. The access matrix
  gets a browser class that says so.
- **D-BROWSER-RECORD — the user decides per scenario.** akmon ships a scaffold for each scenario
  (`references/`), and the project sets what is captured, kept and for how long. The guardrail's
  floor stays: a secret is redacted at capture.
- **D-BROWSER-NAME — `akmon-browser`, a name unique to akmon.** Prefixing the name with `akmon-`
  avoids collisions: a consumer's own `browser` skill (oikos has one) can stand beside it, and the
  shipped skill is easy to find and to avoid.

## Proposed shape

Coarsest first ([plan shape](../../guardrails/_common.md)): the S1 base lifted from oikos is the
trunk, and S2–S6 are branches that each return to it working.

- **Layer 0 — the tool `akmon tool browser`**, Node, no npm runtime dependency. The npm package
  runs it, and the Python package calls it through `node` (D-BROWSER-RUNTIME). Setup: `init`
  (opt-in: registers the MCP server, finds or installs Chrome) and `install`. Lifecycle: `start`,
  `status`, `stop`, `restart`, `attach <endpoint>`. Inspection: `pages`, `snapshot`,
  `screenshot`, `eval [--world page|isolated] [--target sw|popup|page]` (reads only), `logs
  [--until]`, `net`. Extension bench: `ext reload`, `ext action`. Recording: `record …`. Every verb
  works from Bash.
- **Layer 1 — the hands over MCP:** pinned `chrome-devtools-mcp`, registered by `init` (not by
  default), started by an akmon launcher that applies the ownership check and runs on Chrome's side
  (WSL).
- **Layer 2 — the shipped skill `skills/akmon-browser/`**, a development skill: the procedure
  (status, start, hand the sign-in to the user, orient, read), the consent model as `refuses:`,
  and a scaffold per scenario in `references/` (`shared-window.md`, `e2e-attach.md`,
  `extension.md`, `web-check.md`, `read-route.md`, `recording.md`).
- **Layer 3 — the consumer's specializations**, each under its own name and linking
  `akmon-browser` ([ADR 0022/D07](../adr/0022-local-layer-index-and-plans.md)): oikos's resource
  routes and `workspace`; an extension project's selector registry, probes and pacing; a tracker or
  wiki read route; an e2e suite's fixture.
- **Configuration:** a `[browser]` table in `<DEV>/.akmon.toml`: `port`, `profile`, `chrome`,
  `extensions = [paths]`, `hosts = [...]` (browser-routed, read by the fetch guard), `proxy`,
  `pace`, `redact = [...]`, `viewports`. `AKMON_BROWSER_*` variables override it. Local state lives
  under `<DEV>/.local/.browser/` (profile, launch record, endpoint files, recordings).
  `AKMON_BROWSER_ROOT` (D-BROWSER-ROOT) names the project outright for a consumer that is not an akmon
  project: that folder replaces discovery, its state is `<root>/.local/.browser/`, no `[browser]` table is
  read, and the port formula is unchanged over its real path.
- **Guards:** the fetch guard generalised from oikos (hosts from `[browser].hosts` and, where A40
  lands, resource notes); the browser class of the access matrix (D-BROWSER-ACTIONS).
- **Isolation:** one Chrome per project. The DevTools port is bound to loopback only and never
  exposed. Attaching to a Chrome the project did not start is an explicit `attach`, never the
  side effect of a port that happens to answer.

### Migration of the consumers

- **oikos:** its `tools/browser` and `browser-guard` become calls to akmon, and `OIKOS_CHROME_*`
  map to `[browser]`; its installation, which has no akmon dev layer, sets `AKMON_BROWSER_ROOT` to the
  installation folder. Its `browser` skill stays under its own name as the specialization for the
  organization's resources, and links `akmon-browser` for the mechanics.
- **tradingview-assistant-chrome-extension:** `_aitna/tools/browser` and its `.mcp.json` entry are
  replaced; `tv-browser-test` keeps the selectors, the probes, the sign-in cookie name and the
  pacing.
- **tvassistant:** gains the bench without a local implementation; its stale e2e tree is a separate
  question for that project.
- **A Playwright suite:** takes the fixture recipe from `references/e2e-attach.md`; nothing in akmon
  imports Playwright.

## Facts to measure before they are relied on

Each one needs an `M<n>` row in `meta/MEASUREMENTS.md` before the design depends on it:

- Node 22's global `WebSocket` is enough for a CDP client (stable in the Node floor akmon declares).
- Playwright honours `--remote-debugging-port` in `launchOptions.args` beside its own pipe, on the
  version in use, and an external CDP client can attach while the test runs.
- The flags of the pinned `chrome-devtools-mcp` (`--browser-url`, the extension category), and
  whether it reaches service-worker targets.
- Codex reads a project's MCP registration only after trust (M63): the Bash route of Layer 0 is
  what Codex sessions can use until then.
- `developerPrivate` reload of an unpacked extension on the pinned Chrome for Testing.
- `npx @puppeteer/browsers` installs Chrome for Testing on Linux, macOS, Windows and WSL, and what
  it reports when a system library is missing.

## Open

- **How an opt-in skill is delivered.** D-BROWSER-INSTALL wants the skill listed but not set up,
  and a development skill kept to developers. This meets A55 (per-skill on/off) and A62 (where
  development skills live and how `sync` keeps them out of what a project's users get).
- **The wrapper in the conformance corpus.** The amendment puts the behaviour's scenarios on the
  one implementation; whether the corpus also runs one pass-through scenario per wrapper.
- **Relation to N11** (vendoring Google's Chrome-extension skills for the `frontend` archetype):
  those skills are guidance, this one is mechanics. They may ship side by side.

## Future

- **F1 — action automation.** Writes in a tracker or a wiki through the user's session, and forms
  filled and submitted on the agent's initiative rather than as a step the user confirmed in
  joint work (S1). It would mirror the API-first tool's write verbs
  and its dry-run gate, and would need a fresh answer to D-BROWSER-PAGE-API (the site's API from
  inside the page against the UI) and a write class in the access matrix. Not decided; not built.
