# Design: cross-agent contract v2 (skill/role surface beyond thin pointers)

> **Skeleton — parked (backlog T16, deferred).** This frames the problem and the option space
> so the task can be picked up cold; it does **not** pick a path. The choice is meant to be made
> *on evidence of real drift* (see §Leaning). Resolves the remaining part of
> [ROADMAP O3](../ROADMAP.md). Builds on the base contract locked by T1.

## Frame

keystone claims to be **LLM-agnostic**: one source of truth, vendors get generated pointers. T1
made the *base* of that real — vendor pointers import `AGENTS.md`, and `verify.py` checks the
source-to-pointer linkage. But the cross-agent surface today is **thin**: nothing single-sources
the *inventory* of skills and roles. So a new skill or role, or a changed description, can drift
out of `AGENTS.md` and the vendor surfaces without anything noticing beyond a coarse "is `skills/`
mentioned at all" check.

Good outcome:

- adding/renaming a skill or role, or editing its description, cannot silently leave `AGENTS.md`
  (and the vendor surfaces) stale;
- the **single source** is the artifact that already owns the fact — `SKILL.md` frontmatter (T2)
  for skills, `roles/*.md` for roles — never a hand-retyped copy;
- whatever mechanism is chosen does **not** weaken the T1 invariant that `AGENTS.md` is a
  hand-reviewed source document, not a generated file;
- re-run / re-check triggers are documented (after a submodule update, after a new local skill).

Non-goal: richer per-skill *schema* (inputs/outputs/eval) — that is ROADMAP O5's remaining part,
not this task. This task is about the **inventory surface**, not the skill schema.

## Current State

- `AGENTS.md` references `skills/` only as **prose** (the USAGE-layer description); it enumerates
  neither individual skills nor roles. Hand-maintained.
- `sync.py` generates **stub** pointers per vendor (`.claude/skills/<name>/SKILL.md` →
  "read the source SKILL.md") and the vendor entry files (`CLAUDE.md`, `GEMINI.md`,
  `.codex/README.md`, copilot). It does **not** write any skill/role inventory into `AGENTS.md`.
- `verify.py` (T1) checks: vendor pointers import `AGENTS.md`; `AGENTS.md` is **not** itself
  generated (errors on the whole-file `GENERATED` banner); `AGENTS.md` mentions *some* source
  skill root (coarse); warns if it points at the generated `.claude/skills` stubs.
- `SKILL.md` frontmatter (T2) is structured and validated: `name` / `description` / `when_to_use`
  / `owner`. Roles live as `roles/*.md` with a table in `roles/README.md`.

## The binding constraint

T1 locked: **`AGENTS.md` is hand-reviewed, not generated** — `verify.py` errors if the whole-file
`GENERATED` banner appears in it. Any v2 mechanism must live *within* that invariant. This is what
forces the central decision below: we cannot simply "generate AGENTS.md".

## Options

### A. Managed region inside `AGENTS.md`

A marker-delimited block (e.g. `<!-- keystone:skills:start -->` … `<!-- keystone:skills:end -->`,
likewise for roles) that `sync.py` rewrites from the single source; everything outside the markers
stays hand-owned.

- **Pros:** the inventory lives where agents already read it; one file.
- **Cons / must-solve:** `verify.py` must distinguish a *region* marker (allowed) from the
  forbidden whole-file `GENERATED` banner; the writer must never touch text outside its region;
  `sync --check` must detect region drift. Closest to "editing the source file by machine" — the
  riskiest against the T1 invariant.

### B. Verify-only (no generation into `AGENTS.md`)

Keep `AGENTS.md` fully hand-written, but make `verify.py` enforce the inventory: every `SKILL.md`
(by `name`) and every role appears, and (optionally) descriptions match the frontmatter.

- **Pros:** most faithful to "AGENTS.md is the source"; no machine writes into it; smallest blast
  radius.
- **Cons:** the human still edits `AGENTS.md` on every skill/role change — verify only tells them
  *that* it's stale, not fixes it. Description-match checks can get brittle.

### C. Separate generated include

The inventory lives in its own generated file (e.g. `_forge/keystone/…` or a project file) that
`AGENTS.md` links/points to; `AGENTS.md` stays prose-only.

- **Pros:** `AGENTS.md` untouched and hand-owned; the generated part is cleanly isolated and can
  carry the `GENERATED` banner without violating T1.
- **Cons:** one more file in the contract; agents must actually follow the link (the same
  "one hop behind a pointer" risk T1 fought for `CLAUDE.md`).

## Selection criteria (decide on these, when un-parked)

- **Where does drift actually show up?** descriptions going stale → favors generation (A/C);
  people forgetting to *list* a new skill at all → verify-only (B) may suffice.
- **How much hand-text surrounds the inventory** in real `AGENTS.md` files → more surrounding
  prose raises the clobber risk of A.
- **Do agents reliably follow a link?** if not, C's isolation costs reading reliability.
- **Cross-vendor reuse** — whichever source feeds the AGENTS surface should also feed
  `CLAUDE/GEMINI/codex`, so the same single source covers every vendor.

## Deliverable shape (when un-parked)

A design lock (this doc → an ADR) choosing A / B / C, then engineer impl tasks: `sync.py`
extension (A/C) or a `verify.py` inventory check (all three need a check), plus tests, plus
documented re-run/re-check triggers.

## Leaning

**None yet — decide on evidence.** This task stays deferred until real drift appears, because the
A↔B↔C choice is *driven* by which kind of drift bites first (criteria above). Picking now would
encode an unproven hypothesis. Un-park when a skill/role inventory actually goes stale in a way the
coarse T1 check misses.

## Open Points

- Should description-equality be enforced, or only presence? (Equality is brittle; presence is
  weak.)
- Does the same mechanism cover **roles** as well as skills, or only skills first?
- If A: what exact region-marker syntax, and how does `verify.py` tell it apart from the whole-file
  `GENERATED` banner safely?
- Should the generated inventory carry per-skill `owner` (provenance) or stay name+description?
- Is the inventory needed in `AGENTS.md` at all, or only in the per-vendor generated surfaces?
