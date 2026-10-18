# A35 — the JS rule baseline and the tool choice

> **Question.** Which linter carries akmon's JavaScript/TypeScript rules for a Node project
> that has none, which rules, and what would they cost where they would apply?
>
> **Answer.** The candidate rules — `@eslint/js` recommended plus 29 checkable Google
> JavaScript Style Guide rules and akmon's size floor — are fully expressible only in ESLint.
> oxlint covers 27 of the 29 under the same rule names; Biome covers 19 as stable rules. On
> the one real Node project (tvassistant) the set finds 501 issues. 387 of them are
> `curly` (§4.1.1), which `--fix` resolves. Of the other 114, 64 are on rules the project
> already runs as warnings (its own config reports 62 of them); 50 are new. Zero findings on `eqeqeq`, `no-var`, `eval`, the
> primitive wrappers, `camelcase`, `throw` literals and `for-in`. On akmon's own `js/`: 88,
> of which 57 are `complexity` over 10. ESLint for TypeScript needs `typescript-eslint`, which
> today refuses TypeScript 7 (peer `<6.1.0`).
> [M127](../MEASUREMENTS.md), [M128](../MEASUREMENTS.md).

## Corpus

- **tvassistant** at `869d9de`, extracted with `git archive` into the session scratchpad, so
  nothing ran in its working tree except one read-only `eslint .` with its own config. Its
  `git status` was the same line before and after (`_forge/keystone`, a submodule). 179 linted
  files (195 tracked `*.js`, 18 387 lines; its own ignores kept), no TypeScript, no Vue
  sources, ESLint 9 flat config with `@eslint/js` recommended.
- **akmon `js/`**: the working tree with this session's uncommitted changes, `js/vendor/`
  excluded. 79 `*.mjs` files, 29 176 lines.
- **Tools**, exact versions installed in the scratchpad: eslint 10.12.0, @eslint/js 10.0.1,
  globals 17.13.0, @biomejs/biome 2.5.15, oxlint 1.87.0, @oxlint/migrate 1.87.0, typescript
  7.0.2. Node v24.21.0, Linux x64.

## Method

The candidate set is written once, as ESLint flat config (below), and carried to the other
two tools by each one's own migrator: `biome migrate eslint --include-inspired` and
`@oxlint/migrate`. Each tool then ran on the same tree, with tvassistant's ignores and
environment globals. Findings are counted by rule; `/usr/bin/time` gives wall time for one
run, cold, no cache.

`extends` was probed on a fixture project with a stand-in `akmon` package whose `exports`
map `./eslint`, `./biome` and `./oxlint`. The probe planted three findings: `var`, `==` and
an `if` without braces.

## The candidate rules

`@eslint/js` `recommended` (the bug class), then:

| Google JS Style Guide | rule |
|---|---|
| §4.1.1 braces for all control structures | `curly: all` |
| §5.1.1 `const` and `let` | `no-var`, `prefer-const` |
| §5.1.2 one variable per declaration | `one-var: never` |
| §5.2.2, §5.3.2 no `Array`/`Object` constructor | `no-array-constructor`, `no-object-constructor` |
| §5.5.3 arrow functions for nested functions | `prefer-arrow-callback` |
| §5.5.5.2, §5.5.7 rest and spread, not `arguments`/`apply` | `prefer-rest-params`, `prefer-spread` |
| §5.6.3 no line continuations | `no-multi-str` |
| §5.8.1 `for-in` only with a guard | `guard-for-in` |
| §5.8.2 throw `Error` | `no-throw-literal`, `prefer-promise-reject-errors` |
| §5.8.3.2 `default` case present, last | `default-case`, `default-case-last` |
| §5.9 `this` only in classes | `no-invalid-this` |
| §5.10, §5.10.1 `===`, `== null` allowed | `eqeqeq: always, null: ignore` |
| §5.11.2 no dynamic code | `no-eval`, `no-implied-eval`, `no-new-func` |
| §5.11.5 no primitive wrappers; `Boolean(x)` over `+`/`""+` | `no-new-wrappers`, `no-implicit-coercion` (boolean off) |
| §5.11.6 no modified builtins | `no-extend-native` |
| §6 naming | `camelcase` (properties never), `new-cap` |
| akmon floor (the ruff `C90`/`PLR` analogue) | `complexity: 10`, `max-params: 5`, `max-statements: 50`, `max-depth: 4` |

Left out on purpose:

- **Formatting.** §4 except braces, §5.11.3 semicolons, quotes and trailing commas belong
  to the project's formatter. ESLint's own formatting rules are deprecated.
- **§7 JSDoc.** No core rule; it needs `eslint-plugin-jsdoc`, one more dependency.
- **§5.4.4 static methods, §5.1.3 declared when needed, §8.2.3 narrowest suppression.** No
  rule exists in any of the three tools.

## Results — coverage by tool

| | ESLint 10 | oxlint 1.87 | Biome 2.5 |
|---|---|---|---|
| the 29 Google/floor rules | 29 | 27 — no `camelcase`, `no-invalid-this` ("superseded by TypeScript") | 19 stable; nursery: `no-extend-native`, `no-implied-eval`, `no-new-func`, `prefer-promise-reject-errors`; none: `camelcase`, `new-cap`, `no-invalid-this`, `max-statements`, `max-depth`, `no-object-constructor` |
| `recommended`'s 64 | 64 | 60 — `no-undef` and `no-useless-assignment` are nursery, `no-dupe-args` and `no-octal` superseded by strict mode | 59 by Biome's count |
| `complexity` | cyclomatic | cyclomatic | cognitive (`noExcessiveCognitiveComplexity`, "inspired") |
| `extends` by package name | `import akmon from "akmon/eslint"` — works | **refused**: "Unsupported named config … Oxlint does not support ESLint shared configs"; a path `./node_modules/akmon/oxlint.json` works | `"extends": ["akmon/biome"]` through the package `exports` — works |
| TypeScript | needs `typescript-eslint`; 8.71.2 (latest and canary) peers `typescript >=4.8.4 <6.1.0`, so `npm install` beside TypeScript 7.0.2 fails with ERESOLVE | native (a `.ts` file: 3 of 3 planted findings) | native (3 of 3) |
| install | 3 packages → 77 in `node_modules`, 15 MB; with `typescript-eslint` + TS 6: 94, 47 MB | 1 → 2, 17 MB | 1 → 2, 65 MB |
| wall time, tvassistant | 5.97 s | 0.20 s | 0.47 s |
| wall time, akmon `js/` | 7.25 s | 0.18 s | — |

## Results — tvassistant

| tool, config | findings |
|---|---|
| its own (ESLint 9, recommended, five rules as `warn`) | 62 warnings: `no-unused-vars` 46, `no-empty` 10, `no-async-promise-executor` 3, `no-unused-private-class-members` 2, `no-unreachable` 1 |
| the candidate, ESLint 10 | **501**: `curly` 387 (55 in tests), `no-unused-vars` 48, `complexity` 27, `no-empty` 10, `no-invalid-this` 8, `prefer-const` 4, `prefer-arrow-callback` 4, `no-async-promise-executor` 3, `no-useless-assignment` 2, `max-params` 2, `no-unused-private-class-members` 2, `preserve-caught-error` 2, `no-unreachable` 1, `max-depth` 1 |
| the candidate as oxlint | 518. The same rules within a few counts; +13 `no-redeclare` are the probe's globals applied project-wide (tvassistant declares `tvUtils`/`Page` in its tests) |
| the candidate as Biome | 483: `useBlockStatements` 387, cognitive complexity 32, `noEmptyBlockStatements` 23 (it counts empty functions too), `useMaxParams` 8, `noUnusedVariables` 5 (ESLint: 48), and the rest under 8 |

Zero on every other rule of the set. `no-useless-assignment` and `preserve-caught-error` are
new in `@eslint/js` 10's recommended (tvassistant runs 9). `no-invalid-this` fires on an
ES5 constructor function (`src/enum/enum.js`) and one test helper.

## Results — akmon `js/`

88 findings: `complexity` 57 (values 11–30, none in tests), `max-params` 10, `camelcase` 8
(`problems_data`, `git_repo` — names copied from the Python twin), `new-cap` 6 (tests call the
capitalized factories `TokenUsage(...)` without `new`), `no-multi-str` 4 (tests),
`max-statements` 2 (`main` of `init` and `second_opinion`), `one-var` 1.

## oxlint 1.88 by hand, and oxfmt

Owner question: can configuration close oxlint's two gaps, and how close are
oxlint and oxfmt to ESLint and Prettier? The candidate as oxlint config, plus `no-undef`
and `no-useless-assignment` enabled by name, run on both corpora and compared with ESLint's
findings by file, line and rule. [M129](../MEASUREMENTS.md), [M130](../MEASUREMENTS.md).

| gap | closed by | result |
|---|---|---|
| `camelcase` | native `id-match` with a camel/PascalCase/UPPER_SNAKE pattern, leading and trailing `_` allowed, declarations only | the same names as ESLint on both corpora; ESLint also reports every use of the name, `id-match` the declaration once |
| `no-invalid-this` | ESLint's own rule as an oxlint JS plugin | 7 of 8 on tvassistant; needs the `eslint` package (77 packages) and ~2 s of Node start; JS plugins are alpha, outside semver |
| | `tsc` `noImplicitThis` | catches it in TypeScript (part of `strict`); in JS only under `checkJs`, and it also flags ES5 constructors |
| `extends` by name | `oxlint.config.ts` importing `akmon/oxlint` | works, the JS plugin included; JS config is marked experimental |
| `no-undef` (nursery) | enabled by name | as ESLint, except that `/* global X */` comments are not read: 6 false findings in tvassistant |

Same file and line as ESLint: tvassistant 492 of 494, akmon 86 of 88. akmon's two are one
`no-multi-str` placed on the string's first line instead of its last. On tvassistant:

- ESLint only:
  - `no-unused-vars` on an unused method parameter `_data`;
  - one `no-invalid-this` in a CommonJS file that ESLint was told to parse as a module.
- oxlint only:
  - 9 `no-unreachable`, because oxlint reports each statement and ESLint the whole run;
  - 13 `no-redeclare`, from the probe's config globals that the test files redeclare;
  - 6 `no-undef` from the `/* global */` comments;
  - one `no-unexpected-multiline` on an IIFE call written on its own line, which ESLint misses.

**oxfmt against Prettier**, both at width 80 (oxfmt's default is 100): tvassistant 192 of
193 files identical, akmon 63 of 79. Every difference sits next to a JSDoc type cast or a
trailing comment. In one of them Prettier moves the cast's parentheses
(`(/** @type {string} */ (x) || "")` → `/** @type {string} */ ((x) || "")`), changing
what `tsc` reads as cast, and oxfmt keeps the source. oxfmt is 30–40 times faster. A
formatter stays the project's (out of the ruleset); this sizes the option for a project that
has none.

## Limits

- One consumer, and it already runs ESLint; it says what the set costs real code, not what a
  project that has never run a linter would see.
- No TypeScript corpus. The TS row is a parse probe and the `typescript-eslint` peer range,
  not a baseline.
- Biome's and oxlint's counts come from their migrators' mapping; a hand-tuned config could
  close part of the gap (Biome's `useNamingConvention` for `camelcase`, for example).
- Time is one cold run each.
