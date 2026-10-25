# Review — ideas from Warp's orchestration for akmon

> **Point-in-time review** (review role, findings snapshot, deliberately short). Read: the
> orchestration pages of Warp's public documentation. **Not examined:** the product itself, its
> hooks, skills, benchmarks, pricing or data handling. Product analysis proper is deferred as
> [A48](../../TASKS.md).

**Owner request.** While looking for ideas on how a worker should be launched and how its end is
known, check what Warp's documentation says about orchestration.

**A possible competitor.** The owner describes Warp as presenting itself as a software-development
factory — agents, hooks, skills, benchmarks and a web interface — which is the ground akmon covers as a
standard. That description is **not verified here**; it is why the product is listed in this folder at
all and why A48 exists.

---

## 1. What the pages say

Four orchestration traits, as the documentation states them:

1. **One level.** A parent agent has direct children; a child does not have children of its own.
2. **Approval before spawn.** The parent proposes a breakdown of the work and the user approves it
   before any child starts.
3. **A run record per child.** Each child has its own record, separate from the parent's.
4. **The parent and its children end independently.** The parent can finish while a child is still
   running or has failed.

## 2. Against akmon

| Warp trait | akmon today | Idea for akmon (owner decides) |
|---|---|---|
| One level | [ADR 0021/D06](../../../docs/adr/0021-athlos-deferred-work-packages-and-handoff.md#d06--the-head-launches-every-worker-interim): the head launches every worker; nothing nests. The tool caps do not yet say so ([A47](../../TASKS.md)) | A vendor reaching the same shape is weak support for keeping D06's interim option A; it does not settle the holder-that-spawns option, which waits on [N15](../../TASKS.md) |
| Approval before spawn | [D07](../../../docs/adr/0021-athlos-deferred-work-packages-and-handoff.md#d07--viewpoints-one-mechanism-a-catalog-of-positions-one-control): viewpoints are offered to the owner before any spend; the design-flow plan check precedes a fan-out | Same direction; no change |
| A run record per child | the delegation log has six columns and records the dispatch only — no completion, no failure | A per-child completion record is the missing half of [N4](../../TASKS.md); the idea is to give each worker a record of its own end, not only of its start |
| Independent endings | [D05](../../../docs/adr/0021-athlos-deferred-work-packages-and-handoff.md#d05--handles-and-ownership-do-not-migrate-by-implication-a-handed-off-holder-is-retired): a handed-off holder is retired; forced termination waits on N15 | N15 phase 2 asks the same question — what survives when the parent ends first — and should note that a vendor treats it as a normal case |

## 3. What this review does not establish

Whether Warp's orchestration works as documented, what it costs, and everything outside the
orchestration pages. None of the rows above is a measured fact about Warp; they are ideas read from
its documentation, to be adopted or dropped on akmon's own evidence.
