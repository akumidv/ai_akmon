# Rules: collaboration with the owner

How every agent, in every role and on every project, talks with the owner — the developer whose
attention the work spends. Loaded at session start beside the [guardrails](../guardrails/_common.md),
which hold the prohibitions; the shapes these rules use are in [templates](templates.md).

## Language of a reply

- **Reply in the language of the owner's last message** — never in the language of your own
  reasoning. A prompt the owner carries to another session is chat too.
- **Structure stays English:** a reply's section headings (`Findings`, `Options`, `Recommendation`),
  the block heading `Needed from you`, its groups `Decide` and `Act`, and an item's labels — the
  standard's own checks count them. The prose under them follows the owner's language.

## Codes

- **Every request for an owner decision carries a stable code** in bold uppercase: **D-TOPIC**, or
  **D-C139-TOPIC** when it belongs to a task — a question, a decision or a confirmation alike. A code
  names one bounded choice, not a position; it stays the same across reordering, turns and resumption
  while the request is open and is never given to another open choice. A material change of scope
  gets a new code.
- **A code in a reply carries its gist.** A task id (`C138`) or a decision code is followed by 3–5
  words saying what it is — up to 10 for a complex task — and a verdict is stated as the action to
  take, not as a label.

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
  block** and nothing after it, grouped under `Decide` — decisions — and `Act` — actions: a go-ahead
  to write, a commit, a push, a release, a run, something to supply. It says when nothing is needed.
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
- Where an open request is kept and how an answer enters the record:
  [design-flow § Decision requests](../pipelines/design-flow.md#decision-requests).
