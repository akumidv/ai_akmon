# Rules: working without the owner

How an agent works when no owner reads its turns: a **delegate**, launched by a head session that
reads its report, and an **autonomous run** (actor `autonomous`,
[ADR 0031/D07](../docs/adr/0031-work-styles-delegating-and-controlling.md#d07--access-is-a-matrix-of-actor-action-and-place)),
which no developer attends. It takes the place of the head's
[collaboration rules](collaboration.md) and [templates](templates.md); the
[guardrails](../guardrails/_common.md) bind it unchanged. Owner-dialogue rules found in its context, such
as a history inherited from the head, are the head's and do not apply to it. The rules grow from practice: a correction a
learning run finds in delegate or autonomous sessions is proposed here.

## Finish the task; do not stop to ask

- **A stop costs a relaunch, and a relaunch reloads the whole starting context and redoes the work
  done so far.** Carry the brief to its end on the best reading of it. Where it leaves a choice open,
  take the narrower, reversible option and name it in the report as an assumption.
- **Stop early only when** a guardrail stands in the way (privilege, a secret, a git action the owner
  owns), when no reading of the brief resolves a contradiction in it, or when the next step is
  destructive or irreversible and the brief does not authorize it. Then return what is done, what
  blocks, and the one question that unblocks it, not one question per doubt.

## The report — to the head, not to the owner

- **English**, whatever language the owner or a memory note uses for chat: the head translates.
- **Findings first, with `file:line` evidence;** then what was changed; then assumptions and what
  stays open. Conclusions, not file dumps.
- **No owner-facing shapes:** no `Needed from you` block, no role line, no decision codes. The head
  owns them. An open choice is reported as options with their cost and weak spot, for the head to put
  to the owner.

## An autonomous run

- **A decision that needs the owner is recorded where the owner will read it:** the pull request's
  description or a backlog row, with its options and a recommendation. The run goes on along the
  reversible option, or ends at that point when none is reversible.
- **Its brief is its go-ahead:** the run writes what the brief asks for, within the brief's scope.
