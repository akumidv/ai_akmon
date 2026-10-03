// akmon's own development lint (owner decision 2026-09-27, C103): @eslint/js recommended
// only, no plugins, pinned devDependencies. This config is akmon-internal — it does NOT
// pre-decide the consumer ruleset (A35); the consumer-side offer ships separately.
//
// Node globals are hand-listed (the `globals` package is deliberately not a dependency):
// one entry per builtin the checked-in .mjs actually uses, `readonly` because the code
// only reads them.
import js from "@eslint/js";

export default [
  {
    // node_modules and vendor/ are not ours; the dotted scratch dirs (session tmp,
    // other lanes' checkouts, review/vendor material) carry foreign eslint
    // configs and node_modules that must never be linted or loaded; `.venv` is machine
    // state — an installed wheel whose copy of the tree must not answer for the source.
    ignores: ["node_modules/**", "js/vendor/**", ".qwen/**", ".claude/**", ".review/**", ".venv/**"],
  },
  js.configs.recommended,
  {
    languageOptions: {
      globals: {
        Buffer: "readonly",
        URL: "readonly",
        console: "readonly",
        process: "readonly",
      },
    },
  },
];
