# Pipeline: learning

The periodic cycle the [learn](../roles/learn.md) role follows. Step **3 (PROMOTE)** of the
learn loop:
the review that lifts proven local assets into keystone so every project inherits them. Where
[memory-distill](memory-distill.md) runs continuously and stays LOCAL, this runs **periodically**
and crosses the LOCAL → SHARED boundary. [release](../roles/release.md)'s periodic cadence hands
off to this cycle rather than promoting memory itself.

## When

On a cadence (e.g. end of a work cycle, or when local assets have accumulated) — not on
every change. The trigger is "enough local learning has built up to review", not a single
insight.

## Steps

1. **Review** — scan `_forge/memory/`, `_forge/skills/`, `_forge/tools/`, and recent ADRs
   for assets that might be general beyond this project.
2. **Apply the promotion test** — promote LOCAL → keystone only when the asset is **both**:
   - **general** — not tied to this project's domain or runtime, and
   - **proven** — used more than once, or clearly applicable to another project.

   If it fails either, it stays LOCAL.
3. **PROMOTE** (PR into keystone) — by kind:
   - cross-project skill / tool → `keystone/{skills,tools}/`,
   - a role requirement or pipeline change → `keystone/{roles,pipelines}/`,
   - a language or domain rule → `keystone/{guardrails,profiles}/`.
4. **PROPAGATE** — after the keystone PR merges, bump the submodule pin in consuming
   projects (`git submodule update --remote` → commit the pin). Other projects inherit it
   on their next update.
5. **Fold in provider memory** — review each assistant's private memory for durable,
   shareable learnings and distill them down into shared memory (back into
   [memory-distill](memory-distill.md) step 1) so they are not lost with the individual.

## Safety

- Promotion is a **reviewed PR**, never an automatic copy — a changed shared role or
  guardrail reaches every project, so it goes through review (and a changelog / compatibility
  signal).
- Knowledge flows **one way up** the ladder (private → shared memory → local asset →
  keystone). Never push project-specific detail up into keystone.

## Done

Proven, general local assets are promoted into keystone via PR; consuming projects' pins
are bumped; provider-private learnings are distilled into shared memory. The standard has
retuned itself by exactly what proved out — nothing more.
