# 0032 — akmon-browser: one shipped skill for an agent working in a real browser

- **Status:** Accepted for **D01–D09**. The owner answered each code of the
  [design](../design/browser-skill.md) in session: the Node implementation behind two wrappers,
  stated as a general rule and recorded as the
  [ADR 0020 amendment to D01](0020-node-consumers-js-implementation.md#amendment--d01-a-tool-that-drives-an-external-application-is-implemented-once-natively-a82)
  (**D02**, D-BROWSER-RUNTIME); both hands (**D03**, D-BROWSER-HANDS); install through `npx`, the
  user's command on failure, nothing set up by default, a development skill (**D04**,
  D-BROWSER-INSTALL); a foreign Chrome only through `attach` (**D05**, D-BROWSER-OWNERSHIP); the
  skill reads through the interface, with no direct requests, and joint work is reading (**D06**,
  D-BROWSER-PAGE-API, D-BROWSER-S1-CONFIRM); the browser is the developer's session's tool (**D07**,
  D-BROWSER-ACTIONS); recording scope is the user's (**D08**, D-BROWSER-RECORD); the name (**D09**,
  D-BROWSER-NAME). **D01** is the scope those answers share.
- **Owner:** akuminov@gmail.com
- **Extends:** [0022/D07](0022-local-layer-index-and-plans.md) — a project specializes the shipped
  skill under its own name instead of forking it · [0031/D07](0031-work-styles-delegating-and-controlling.md#d07--access-is-a-matrix-of-actor-action-and-place)
  — the access matrix gains a browser class.
- **References:** [design: browser skill](../design/browser-skill.md) (the scenarios, what was
  found, the proposed shape, § Open and § Future) · tasks [A82](../../meta/TASKS.md) (design),
  [C204](../../meta/TASKS.md) (implementation), [A55](../../meta/TASKS.md) and
  [A62](../../meta/TASKS.md) (delivery of an opt-in, development skill).

## Context

Projects on akmon drive a real Chrome from the agent session, and each built its own stack:
oikos's shared window, an extension project's bench, an e2e suite with no way in, and tracker
tooling with no route where no token is issued. The mechanics are the same every time: find or
install Chrome, give it a profile and a port, tell whose Chrome answers, attach a client, read pages,
consoles and the network, act only with consent. The design records what was found in each and
the six scenarios the skill serves.

## Decision

akmon ships one development skill, `akmon-browser`, over one Node tool, `akmon tool browser`, and
the pinned `chrome-devtools-mcp` server. The skill reads through the interface; projects add their
own selectors, resources and verbs under their own skill names.

## Alternatives considered

- **Each project keeps its own stack.** Rejected: the same mechanics written three times, drifting.
- **A Python implementation beside the Node one.** Rejected by the owner: the Chrome DevTools
  protocol and its MCP server live in Node's toolchain; Python's standard library has no
  WebSocket client (D02).
- **MCP only, or Bash only.** Rejected: MCP is the interactive hands, and Bash is what scripts,
  gates, derived skills and harnesses without MCP can call (D03).
- **Calling a site's own API from inside the signed-in page.** Rejected for now: the skill reads
  through the interface; action automation is a future scenario (D06).
- **The name `browser`.** Rejected: it collides with consumers' own skills (oikos has one) (D09).

## Consequences

- Using the skill needs Node on the machine, from either package.
- Nothing about the browser is set up in a project that did not ask for it; `sync` ships the skill's
  text, and `init` of the tool does the rest. The listing of the skill reaches every consumer until
  A55 and A62 give an opt-in, development-only delivery.
- oikos and the extension projects replace their local stacks with calls to akmon and keep their
  specializations.

## Decision details

### D01 — One shipped skill for six scenarios; a project specializes it

`Decision-ID: ADR-0032/D01`

`akmon-browser` serves the design's scenarios: the shared window for a web resource without an
API (S1), attaching to the browser an e2e run opened and the reverse (S2), the extension bench
(S3), checking a web solution under development (S4), reading a tracker or a wiki through the
user's session (S5), and joint debugging where the user drives and the agent records (S6). akmon
owns the mechanics; a project owns its selectors, resource notes, page objects, pacing and domain
verbs, in a skill of its own name that links `akmon-browser` (0022/D07).

### D02 — One Node implementation, a wrapper in each package

`Decision-ID: ADR-0032/D02`

`akmon tool browser` is written once, in Node, under the ADR 0020 amendment to D01. The npm
package runs it; the Python package's `akmon tool browser` calls `node`. It has no npm runtime
dependency: the Chrome DevTools protocol is spoken over Node's own WebSocket.

### D03 — Two hands: the MCP server and the Bash verbs

`Decision-ID: ADR-0032/D03`

Interactive work goes through the pinned `chrome-devtools-mcp` server, started by an akmon launcher
that checks ownership (D05) and runs on Chrome's side (under WSL, the Windows side for a Windows
Chrome). Every capability the skill relies on is also a Bash verb of `akmon tool browser`, for
scripts, gates, tests, derived skills and harnesses that do not read the MCP registration.

### D04 — Set up only on request; a development skill

`Decision-ID: ADR-0032/D04`

Nothing is set up by default: no MCP registration, no Chrome. `akmon tool browser init` (or the
skill's first run) registers the server and finds the user's Chrome; when none is found, or an
unpacked extension needs it, Chrome for Testing is installed through a pinned
`npx @puppeteer/browsers`. When that fails, or a system library is missing, the tool prints the
exact command for the user to run and stops. The skill is listed, so an agent knows it exists and
can offer it. It is a development skill: it serves the people building a project, not the project's
users.

### D05 — One Chrome per project; a foreign Chrome only through `attach`

`Decision-ID: ADR-0032/D05`

The project's Chrome runs with its own profile in the local layer and a DevTools port derived from
the project's path, bound to loopback only. A Chrome answering on that port is used only when its
process runs with the project's profile. A Chrome the project did not start (an e2e run's, the
user's) is used only through an explicit `attach` to an endpoint file or an endpoint the user names.
In attach mode the agent never closes the window or the page and never signs in.

### D06 — The skill reads, through the interface

`Decision-ID: ADR-0032/D06`

Reading includes emulating the user's actions in the interface and reading their result:
navigating, expanding, searching, filtering, and, in joint work with the user, a step the user
confirmed while watching the window. The agent makes no direct request to a site's API from inside
the page, never types a password, an MFA code or a secret, and never signs in for the user. Page
content is material, never instructions. Writes on the agent's initiative (in a tracker, a wiki, a
form) are action automation, not decided here.

### D07 — The browser is the developer's session's tool

`Decision-ID: ADR-0032/D07`

An `autonomous` run and a delegated agent do not drive the browser; they have the ordinary web
request. The access matrix of 0031/D07 gains a browser class that says so.

### D08 — The user sets what a recording keeps

`Decision-ID: ADR-0032/D08`

akmon ships the recording mechanism and a scaffold for each scenario, with defaults. What is
captured, which bodies are kept and for how long are the project's settings. The one fixed floor is
the guardrail's: a secret is redacted at capture, never afterwards. Recordings stay in the local
layer and leave the machine only on the user's word.

### D09 — The name is `akmon-browser`

`Decision-ID: ADR-0032/D09`

The skill is named `akmon-browser`, unique to akmon, so a project's own `browser` skill stands
beside it and the shipped one is easy to find and to avoid. The tool keeps the short name
`akmon tool browser`.
