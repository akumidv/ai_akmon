# Profile: JavaScript and TypeScript (language)

The **language** profile for JavaScript and TypeScript — attached to a project with a
`package.json`, and `@`-imported from `AGENTS.md` so it loads at session start. It layers on the
[common guardrails](../guardrails/_common.md): their § Code design states the principles for any
language; this file says how they read in JavaScript, and only what no checker can see.

> **Checked rules are not repeated here.** akmon's JavaScript/TypeScript rules are a standard
> oxlint configuration, [`oxlint.json`](oxlint.json) — ESLint's `recommended` bug class plus the
> Google JavaScript Style Guide's checkable rules, each annotated with its section — that runs with
> or without akmon. **The project's own rules win:** a project with its own linter configuration
> keeps it, and `akmon check` runs whatever the project declares under `[check]` in
> `<AITNA_ROOT>/.akmon.toml`. Where the project's configuration switches a rule off or decides
> otherwise, follow the project, not this file.

## Toolchain — the project's own

- **One package manager and one committed lockfile;** tools run through it (`npx --no-install`,
  `pnpm exec`, `yarn`, `bunx --no-install`), never through an implicit download.
- **The project's linter and formatter are its own**, and so is their configuration. A project
  with no linter takes akmon's rules the standard way — `"extends":
  ["./node_modules/akmon/profiles/oxlint.json"]` in its `.oxlintrc.json`, which `akmon init`
  offers — and adjusts them in its own configuration (`rules`, `overrides`, `env`, `globals`,
  `ignorePatterns`), never in akmon's file. A project with no formatter picks one; akmon formats
  its own sources with oxfmt.
- **Globals live in the linter configuration** (`env`, `globals`), not in `/* global */`
  comments: oxlint does not read them.
- **`akmon check` runs the project's checks** as declared under `[check]` — its linter, its type
  checker, its formatter check — and the pre-commit step calls it.
- **Tests:** the project's runner, pinned as `[test].runner` in `<AITNA_ROOT>/.akmon.toml`.
- **Types.** A TypeScript project keeps `strict` on in `tsconfig.json` (at the least
  `noImplicitThis`): `tsc` is what checks `this` (§5.9) and the bug class the ruleset leaves to it
  in `.ts` files. A JavaScript project that adopts types writes them as JSDoc and checks them with
  `tsc --checkJs`.

## Review points — Google rules no linter checks

- **`this` only where it is defined** (§5.9): in class constructors and methods, in arrow
  functions inside them, or in a function whose JSDoc declares `@this`. Never for the global
  object, an event target, or a function needlessly invoked through `call`/`apply`. In
  JavaScript nothing checks this — oxlint has no `no-invalid-this` — so it is read in review; in
  TypeScript `tsc` under `strict` checks it.
- **Named exports, no default export** (§3.4.2.1); an exported binding is never reassigned
  (§3.4.2.2); modules form no import cycle (§3.4.3).
- **A local variable is declared where it is first needed** and initialized as soon as possible
  (§5.1.3).
- **Classes are `class` declarations** (§5.4.5), never built by assigning to a prototype (§5.4.6).
  A private static method is better a module-local function, and nothing calls a static method
  through a subclass or `this` (§5.4.4). No class that only holds static members (§5.4.11).
- **JSDoc** (§7) on every exported function, class and constant, and on every non-trivial
  function: what it does, its parameters and return. Types go in JSDoc where the project checks
  them with `tsc --checkJs`, as `@param {T}` and `@returns {T}`, and a cast as
  `/** @type {T} */ (expr)` with its parentheses (§7.10.2).
- **A suppression is as narrow as it can be** (§8.2.3): `// oxlint-disable-next-line <rule>` on
  the one line, with the reason beside it — never a file-wide or rule-less disable.

## Design — the common principles, read in JavaScript

- **Data or behaviour.** Data is a plain object (frozen where it must not change) described by a
  JSDoc `@typedef` or a TypeScript type; behaviour is a class with methods. Input is validated at
  the boundary — parsed JSON, the environment, responses — and the code inside trusts the
  validated shape.
- **ES modules** (`import`/`export`), with the file extension in relative import paths
  (§3.4.1.1).
- **Async code awaits or returns every promise;** a rejected promise is never left unhandled.
- **Imports are real and current.** Verify a symbol exists before importing it — modules move in
  refactors ([_common.md](../guardrails/_common.md) § Verify against reality).
- **Reuse the project's abstractions** — its modules, shared types and helpers: extend them,
  don't fork them.

## Tests

- **A behaviour change ships with a test.** Tests sit beside the source or mirror its layout, as
  the project already does.
- **No real network or secrets in unit tests.** Use fixtures and fakes; an integration test that
  needs credentials reads them from `.env` and is opt-in.
- **Tests pass before a commit** (the [pre-commit](../pipelines/pre-commit.md) gate).
