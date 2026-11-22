# Rules: collaboration with the owner

How the **head session** — the one the owner attends — talks with the owner, in every role and on
every project. A hook delivers it to that session only; a delegate and an autonomous run follow
[unattended](unattended.md). Its shapes are in [templates](templates.md).

## Role declaration

- **State your role before project work and on every switch:** `🧭 role: <name> — <focus>`, picked by
  operation ([roles/](../roles/README.md)); `🧭 agent:` is read as an alias for one release.

Runtime check: role.declaration — subset (a switch is not observable); detail in [hooks/README.md](../hooks/README.md).

## Analysis before mutation — with the owner

- **An analysis-only turn produces words, not edits:** asked to analyze, explain, review, compare or
  say what remains (*why, how, what's left, which is better, take a look, assess*), report findings
  and a recommendation **in chat first**. The go-ahead the
  [guardrail](../guardrails/_common.md#analysis-before-mutation) requires is the owner's, and a
  consequential choice is put to the owner as a decision request.

## Language of a reply

- **Reply in the language of the owner's last message** — never in the language of your own
  reasoning. A prompt the owner carries to another session is chat too.
- **Structure stays English:** a reply's section headings (`Findings`, `Options`, `Recommendation`),
  the block heading `Needed from you`, its groups `Decide` and `Act`, and an item's labels — the
  standard's own checks count them. The prose under them follows the owner's language.

## Codes

- **Every request to the owner carries a stable code** in bold uppercase: **D-** for a decision (a
  question, a choice, a confirmation), **G-** for an action (a go-ahead to write, commit, run, supply);
  **D-C139-TOPIC** when it belongs to a task. A code names one bounded choice, not a position, stays
  while the request is open, and is never given to another open choice; a material change of scope
  gets a new code.
- **A code in a reply carries its gist:** a task id or a code is followed by 3–5 words (up to 10 for
  a complex task), and a verdict is stated as the action to take, not as a label.

## Writing a request

- **Write for the owner, not for yourself.** A term, abbreviation or code the owner has not used is
  spelled out in plain words where it first appears; a choice about a shape, a name or a data layout
  carries one concrete example per option. A request the owner calls unclear is asked again with an
  example, not argued.
- **A proposal from another agent or session is an option** to weigh, not a decision; one that departs
  from an accepted decision block names which of that block's reasons no longer holds.
- A question that needs the owner's own knowledge may stay open rather than gain invented options.

## The closing block

- **Every reply that asks for, or leaves pending, an owner action ends with one `Needed from you`
  block** and nothing after it, grouped under `Decide` (decisions) and `Act` (actions). It says when
  nothing is needed.
- **Each request is one numbered item that decides correctly when read alone**, in short plain
  sentences, in the [item shape](templates.md#owner-request-item). Each option carries its cost and
  its weak spot, the recommended one above all; a weighed and rejected one is kept with `rejected` and
  its reason; a reason is never cut short unmarked — a main reason given short is marked
  `(short — full reasoning above under D-…)`.
- **The body argues a question only when needed:** its reasoning does not fit the item, or it is asked
  again in a later message than the first. Such a passage is headed by the question's code and gist,
  and the item sums it up rather than copying it. Otherwise a question stands in the block alone.

## The owner's answers

- **No default.** An unanswered request stays pending. Answers are matched by code, not position, in
  any order and for any subset; a bare code identifies a request but does not accept it; plain,
  unambiguous acceptance without a code stays valid. Codes add no approval gate.
- **`all as recommended`** — read by its meaning in any language — **accepts decisions only:** each
  design or code choice in the block that carries a recommendation. **It never permits an action**;
  each action is closed only by an answer with its own code. An item with no recommendation stays
  pending. The owner names the exceptions by code, and an answer by code overrides the general one.
- Where a request is kept and an answer recorded: [design-flow](../pipelines/design-flow.md#decision-requests).
