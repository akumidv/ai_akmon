# 0017 — Skill discovery and result-first delivery

- **Status:** Accepted
- **Owner:** akuminov@gmail.com
- **References:** [C79 evidence](../reviews/c79-skill-guidance-20260913.md) ·
  [C79 archive](../TASKS_ARCHIVE.md)

## Accepted decision block

### D01 — One selector description delivered to supported harnesses

`Decision-ID: ADR-0017/D01`
`Legacy-ID: D2-41`

Each skill's source frontmatter owns one `description`: expected result first, then the trigger,
within the Agent Skills limit. `owner` lives under `metadata.owner`; `when_to_use` is not a second
semantic owner. Sync delivers the same frontmatter to the supported Claude and Codex skill
locations, with generated provenance outside the YAML data. Mechanical schema and syntax limits
are checked; whether the prose names a useful result remains a review judgment.

The metadata move is a consumer-visible migration. Harness acceptance of a YAML spelling and the
project validator's accepted subset are reported separately. Revisit if supported harnesses
require incompatible selector semantics that cannot be represented by one source description.
