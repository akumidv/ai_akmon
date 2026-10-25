# 0024 — The second opinion is chosen by model priors, down one locally-prioritised ladder

- **Status:** Accepted for **D01–D14**. The owner decided each point in session — the diversity axis,
  the ladder's shape and order, same-family runs, the carriers that ship, and the gateway carrier's
  home — then **re-decided how a prior becomes known**: what this record first accepted as automatic
  discovery of the host was replaced by **D11** (declared, not snooped) and **D13**, **D12** added the
  owner-declared carrier so a harness akmon never measured can still give a second opinion, and **D14**
  separated model routing — the unit is `(provider, model)`, and the second opinion owns only the rule
  that picks a model inside a provider. None of it is implemented yet; the work is
  [C162](../../meta/TASKS.md), the prose and design sweep is [A65](../../meta/TASKS.md).
- **Owner:** akuminov@gmail.com
- **Supersedes:** [ADR 0005](0005-synthesizer-gate-audit-and-role-routing.md) item 5 (the
  two-step vendor ladder as the resolution rule) and, in part, the second-opinion rows of
  [ADR 0004](0004-model-routing-capability-tiers.md). **Retained unchanged:** 0004/D02 — the
  versioned command map stays the sole constructor of a second-opinion invocation, and D08 below
  leans on it rather than replacing it.
- **References:** [design: model routing](../design/model-routing.md) §4.6, §9.3, §9.7 ·
  [0005](0005-synthesizer-gate-audit-and-role-routing.md) ·
  [0020](0020-node-consumers-js-implementation.md) (the JavaScript twin) ·
  [0021](0021-athlos-deferred-work-packages-and-handoff.md) (a second reader of the discovered set)

The design's first statement was written against a carrier population this repository does not have,
and is not cited here as a source: every fact in Context was re-measured against this tree.

## Context

A review gate needs a second opinion from a **different mind** than the one that wrote the work. The
intent is already in the standard — 0005 item 5 says diversity is about *model* priors, not vendor
branding, and `second_opinion_fallback_model`'s own docstring repeats it
(`tools/model_routing/routing.py:392-398`). The mechanism below it never followed: it compares vendor
names (`routing.py:354-360`, `opposite_vendor`: `if candidate != vendor`), and
`resolve_second_opinion`'s first argument is the orchestrator's **vendor** (`routing.py:491`).

Measured in this tree:

| fact | where |
|---|---|
| The registry is keyed by vendor and holds exactly two: `anthropic`, `openai`. | `tools/model_routing/registry.json:2,27` |
| The order is two named steps, `["other-vendor","same-vendor-other-model"]`, `never: "same-model"` — so the choice is **binary**, not merely absolute. | `registry.json:100-105` |
| The harness-command map knows two carriers, `claude` and `codex`. | `common/runtime.json` |
| The only channel for "models present on this host" is a hand-typed `--available` list, and only for the session's own vendor. | `tools/model_routing/init.py:139-141`, `routing.py:167-186` |
| `--vendor` is refused for any vendor absent from the registry. | `init.py:159-160` |
| No code reads a model catalog: `$CODEX_HOME`/`models_cache` appear nowhere in `tools/`, `js/tools/` or `common/`. | grep, this session |
| The resolved target is already a pair `(provider, model)` and carries no family. | `routing.py:484-488` |
| A third copy of the same answer — `Binding.second_opinion_cli` — is computed at bind time. | `routing.py:148,298` |

The owner works through the **qwen** harness. That harness has no vendor block and no command row, so
today it does not receive a wrong second opinion — it cannot request one: `--vendor qwen` exits with a
usage error. Measured on this host while writing this record: `claude` 2.1.310, `codex-cli` 0.164.0 and
`qwen` 0.24.7 are installed; `gemini` and `copilot` are not.

The axis is not merely imprecise, it is the wrong axis: a carrier's brand says nothing about the
weights behind it. One carrier can be pointed at another vendor's family, and one carrier can expose
several families at once — so choosing by carrier name can both *claim* diversity it did not buy and
*refuse* diversity that was available.

## Accepted decision blocks

### D01 — A provider is a pair: a carrier × a set of priors. Diversity is tested on the family

`Decision-ID: ADR-0024/D01`

The **carrier** is the program that runs the review — a harness CLI, or a tool entrypoint issuing a
bare completion. The **priors** are the model family that actually answers, a short canonical string
drawn from a **closed** vocabulary (`claude`, `gpt`, `qwen`, `gemini`) so it cannot collapse onto a
carrier name. Two providers of one family are one mind, however many carriers front them. `vendor`
keeps its present meaning — whose `selection_policy`, `harness_rungs`, `auditor_only_rungs` and
`semantic_fallback` a session binds from — and answers no diversity question.

The existing rung aliases are the same families read from the other side (`haiku/sonnet/opus/fable`
of one, `luna/terra/sol/astra` of another); this makes the family a stored field instead of an
inference from the vendor key. `SecondOpinionTarget` gains the third field it lacks:
`(provider, model, family)`.

*Rejected:* comparing concrete model ids. Ids are account- and rollout-specific, so a renamed model
reads as a different mind — the same false diversity by another route.

### D02 — One `providers` table owns every provider row; the vendor blocks keep only orchestration

`Decision-ID: ADR-0024/D02`

Each row carries the carrier kind and operation, the `model_flag` format string, the availability
declaration (`requires_command` / `requires_env`), the family (static, or derived: sources plus a
pattern), and the report directory. The per-vendor `second_opinion` sub-objects leave the vendor
blocks. Today one fact has four owners — the vendor sub-object, the `harness` name borrowed from the
command map, `Binding.second_opinion_cli`, and the local `second_opinion_provider` pin — with no
stated precedence; after this there is one read by provider id.

An operation name is **not** a binary: `common/runtime.json` remains the sole owner of the executable
and the operation prefix, and the checker that rejects a command spelled anywhere else
(`meta/checks/runtime.py:876`) keeps that true. The row names the operation; the map spells it.

### D03 — Priors resolve in one order — local pin, then project, then automatic — and an automatic answer is offered for saving

`Decision-ID: ADR-0024/D03`

**Superseded by [D11](#d11--a-prior-is-declared-not-snooped-local-overlay-project-akmons-knowledge-then-ask)**,
which the owner set after this block was first accepted. Its ordering instinct (a human statement
outranks any derivation) survives; its automatic layer — reading a carrier's own settings and model
catalogs — does not.

1. a **pin in the developer's own local overlay** — a human statement beats any derivation;
2. the **project** layer of the carrier's configuration;
3. **automatic discovery**, used only when layers 1 and 2 say nothing: the carrier's own remaining
   settings layers (user, system) and any model catalog it keeps locally, reduced to a family by the
   row's pattern;
4. otherwise **unknown** (see D07).

Nothing is fetched and no carrier is invoked to answer this. When step 3 produces the family, akmon
**offers to persist it** as the local pin, and until the owner accepts the offer the status line says
the value was auto-derived. Deriving silently and forever would make one host's answer unaccountable;
asking every session would re-create per-machine configuration the team default was meant to remove.

A row that declares derivation must declare a pattern; an undeclared one degrades to `unknown`, so the
pairing is a contract-check failure at authoring time, not a runtime surprise.

### D04 — The candidate set is discovered on the host and kept whole, because other consumers read it too

`Decision-ID: ADR-0024/D04`

Discovery answers two questions without running anything: which carriers are **present** (executable
on `PATH`, or — for a tool carrier — its declared environment variables set), and which **model ids**
each one states on disk. The result is an `environment` block in the gitignored local config, stamped
with this host and each carrier's build version: point-in-time data, never registry data.

The block records what was found **in full** — every class of model a carrier exposes, not only the one
the second opinion needs — because the same record answers the tier binding's `available` ladder today
and the model choice of a deferred work package under [ADR 0021](0021-athlos-deferred-work-packages-and-handoff.md)
next. `--available` stops being the only entry point and becomes an **override** of the discovered list
for the session's own vendor, which keeps its flag, its order check (`routing.check_ladder_order`) and
its tests meaningful.

### D05 — The ladder is one flat, locally-prioritised list of `carrier[:model]` entries

`Decision-ID: ADR-0024/D05`

```
"second_opinion_policy": { "ladder": ["claude", "codex", "qwen"], "never": "silently-same-model" }
```

A bare carrier means "that harness on its own default model"; `carrier:model` pins one discovered
model of it. Both resolve to the same `(provider, model, family)` triple, so the walk stays one rule
and no per-carrier table of alternatives exists. No slots: a slot list is a second owner of one
ordering, and the preference a slot encoded — "prefer a carrier that can read the worktree" — is
expressible by position.

The committed list is the **team default**; a developer **replaces it whole** in their local overlay
(lists replace rather than merge — existing, verified behaviour), and an id absent from the provider
table is a named error quoting the overlay file, not a silently skipped entry. A new carrier — another
harness, another vendor's CLI — joins by a row and a position; the rule does not change.

### D06 — A reviewer differs from the session in harness, in model **and** in family; every provider in a chain differs from the ones before it

`Decision-ID: ADR-0024/D06`

For a request at rank *n*, one top-down walk over the ladder skips: the session's own carrier;
a carrier not declared on this host; a carrier absent from `PATH`/environment; a family that cannot
be resolved; a family already taken; and a **concrete model already taken**. The last two together are
the owner's rule: a carrier that exposes several models must not answer with one another provider is
already going to use — otherwise the alternative is weaker while the report says it is diverse.

Rank is the position in the **resulting** chain plus two, so a skip never leaves a hole the report has
to explain. Relativity is a consequence of the self-skip, not a second rule: the ladder is absolute and
shared, and every session gets a different rotation out of it. Nothing compares ladder positions with
the session's position. A third opinion and an arbiter are `rank 3` and `rank 4` on the same walk, and
since the walk always excludes the session's own family, an arbiter is by construction neither
disputant.

### D07 — Same family is admitted only as the disclosed last resort, when the chain is empty

`Decision-ID: ADR-0024/D07`

Diversity of priors is not bought within a family, so the pass that cannot find another family does
not claim to. It still runs, and prefers **a different model of the session's own provider** — the
strongest entry of that provider's declared `models` whose concrete model differs from every model
already used in the run, read from the provider table and **not** from the tier binding's rungs (D14) —
and only if none differs, the carrier's own default in a clean context. Both are disclosed as
`kind=last-resort`, and
`never: silently-same-model` is what makes the difference visible: the policy forbids **arriving at the
same model unnoticed**, which for the first time is a computed value rather than a proxy that could not
see the collision.

### D08 — Unknown priors fail closed, in both directions, with a named reason

`Decision-ID: ADR-0024/D08`

A candidate whose family cannot be resolved is skipped, never counted as diverse. A **session** whose
own family cannot be resolved yields an empty chain and lands on D07. Either way the reason is printed
with the provider id: "the gateway was not used" without "because nothing says which model it points
at" is the same silent weakness this removes. Session start records the resolved carrier **and**
family, and the status line shows `priors=unknown` beside the command that pins it — the unasked
question surfaced where answering it is cheap.

### D09 — akmon ships three carriers; a carrier enters only with a measured review invocation, and no gateway row ships at all

`Decision-ID: ADR-0024/D09`

The first release covers **`claude`, `codex`, `qwen`** — three harnesses, the models each exposes —
which is the population present on the owner's host. `gemini` and `copilot` stay out of the shipped
table: neither is installed here, and no invocation of either has been measured. The family vocabulary
still names `gemini`, because the vocabulary is about minds and not about which rows ship.

Entry is gated by the existing rule, not by a new one: `common/runtime.json` owns how a harness is
invoked non-interactively, and the standard requires a live probe before a capability claim (which is
what [N8](../../meta/TASKS.md) and [C72](../../meta/TASKS.md) exist to do — the second-opinion matrix
rows stand at `delivered: unmeasured` until they land). So the qwen row ships **with** its probe, and a
carrier whose argv nobody ran does not ship as data.

The **gateway** carrier — a bare completion with no repository access — is a shape akmon defines and
never supplies. There is no LLM client in this repository and adding one is out of scope: the
`carrier: "tool"` kind, its `raw_model` consequence, and D10's `repo=none` all stand, while the row
itself comes from a project's own overlay, or from akmon's own local overlay when the subject is
akmon. A project supplies the row and the resolver treats it exactly like a shipped one.

### D10 — What the reviewer could see is reported, not assumed

`Decision-ID: ADR-0024/D10`

A harness carrier is launched with the worktree as its cwd; a bare completion gets no repository, so
the review pack must carry the code inline. The report header is

```
provider=… priors=… carrier=… repo=worktree|none model=… kind=… gate=… exit=…
```

and the **skip ledger** — every provider passed over with its reason — travels with it. `repo` is
derived from the carrier kind in the row, never set by a knob: a knob would let a report claim
repository access that a bare model call cannot have. **Amended by D12** for the one kind of row
whose repository access akmon genuinely cannot derive — a carrier its owner declared.

### D11 — A prior is declared, not snooped: local overlay, project, akmon's knowledge, then ask

`Decision-ID: ADR-0024/D11` · *replaces [D03](#d03--priors-resolve-in-one-order--local-pin-then-project-then-automatic--and-an-automatic-answer-is-offered-for-saving)*

A model identity comes from exactly four sources, first answer wins:

1. the developer's **local overlay** — they name the harnesses they have and the models they run; the
   strongest layer, and a human statement about one's own machine outranks anything akmon infers;
2. the **project's routing overlay** — the team's own declaration, shared through the repository;
3. **akmon's committed knowledge** — the family a provider row declares, and the vendor's committed
   rungs where a row defers to them; this is the "fill it in from what we know" layer, and it is
   *akmon's* knowledge, written down in one place, not a guess about this host;
4. otherwise **`unknown`** — and the tool then **asks**: it names the file, the key and the accepted
   shape, and stops (D08). It does not guess a family in order to keep going.

What is forbidden is the fourth kind of source the first draft of this record proposed: akmon reads
**no** carrier settings file, **no** developer dot-directory and **no** environment value to learn
which model answers, and it never invokes a carrier to ask it. One code path runs on the owner's host
and on a consumer's — a mechanism that works only where it may read somebody's configuration is not
portable, it is privileged, and a resolution that silently differs between the two machines is worse
than one that asks.

The single host fact akmon does take is **presence**: whether an executable resolves on `PATH`. That
is a yes-or-no about a binary, not an identity, and it is the rule `sync` already applies to the two
optional harnesses (C46's accepted contract). A carrier akmon cannot find is reported as *not verified
present*, never assumed present and never assumed absent-without-saying.

Consequence for the existing flag: `--available` is not a workaround, it is layer 2 or 1 in another
spelling — a declared list of this vendor's models — so it stays, keeps its order check
(`routing.check_ladder_order`), and stops being the only place a declaration can be made.

The standard path is therefore **akmon's own configuration**, and nothing else. What a carrier is
pointed at is its owner's business and their own tool's config; akmon neither reads it nor asks
permission to. A carrier whose models and invocation the owner has already configured elsewhere costs
one declaration in the layer the owner chooses — the project overlay or their own — and until that
declaration exists the resolver says `unknown` and names the key. The question "which of my files may
akmon read" is never posed, because it is never akmon's task to work out what its owner already knows.

### D12 — An owner may declare a carrier outright: an argv list, a model placeholder, a prompt channel

`Decision-ID: ADR-0024/D12` · *amends [D09](#d09--akmon-ships-three-carriers-a-carrier-enters-only-with-a-measured-review-invocation-and-no-gateway-row-ships-at-all) and [D10](#d10--what-the-reviewer-could-see-is-reported-not-assumed)*

A provider row written in either overlay may carry a **command of its own** instead of naming a
shipped harness:

```jsonc
"providers": {
  "myqwen": { "argv": ["qwen", "-m", "{model}"], "prompt": "stdin",
              "family": "qwen", "repo": "worktree" }
}
```

- **`argv` is a list, never a shell string.** akmon does not split it and never passes it through a
  shell, so the trust boundary is the config file the owner wrote — a string would make every value in
  it a candidate command, and the standard refuses that shape elsewhere (no shell indirection around a
  privileged action).
- **`{model}`** is the one placeholder: where the pin goes. A declared carrier with no placeholder is
  a carrier that cannot be pinned, and akmon then refuses to *claim* a model-diverse review rather than
  dropping the flag — the same failure mode C97 made loud for shipped rows (`UnpinnableModelError`).
- **`prompt`** says how the review pack reaches the model — `argv` (the pack as the final argument, what
  akmon does today) or `stdin`. The choice is declared, not probed: the two spellings are what the
  owner's own tool accepts, and a pack silently truncated by a length limit is exactly the silent
  weakening this record exists to remove.
- **`family`** is required of a declared carrier, because diversity is the one thing akmon cannot see
  from the outside. A declared row with no family resolves to `unknown` and is skipped with the ask
  from D11 — never counted as diverse.
- **`repo`** is optional and the honest default is `unknown`: `repo=worktree|none|unknown`, where a
  *shipped* row still derives the value from its carrier kind and a *declared* one reports what its
  owner stated. D10's no-knob rule keeps its whole force — the knob cannot manufacture a claim akmon
  would otherwise have to derive; it can only state what only the owner knows.

This is what removes the bottleneck the first draft carried. `common/runtime.json` still owns every
carrier **akmon** ships, and a shipped row still needs its measured argv (D09 unchanged on that point,
which is what N8 and C72 exist for) — but a carrier the owner declares enters as **config, not as a
release of akmon**. A new harness therefore reaches a second opinion the same day it is installed, and
the standard's shipped table stays a set of measured facts rather than a transcription of the world.

### D13 — The host record holds presence and declaration, kept whole, because other readers need it

`Decision-ID: ADR-0024/D13` · *replaces [D04](#d04--the-candidate-set-is-discovered-on-the-host-and-kept-whole-because-other-consumers-read-it-too)*

What `init` writes into the gitignored local config stays point-in-time and small: which providers are
declared, which executables were found on `PATH` with which build version, what the owner stated about
each model and family, and which of those facts came from which of D11's four layers. That last column
is the record's value — a resolution that cannot say *where* it came from cannot be questioned, and
D08's whole purpose is that the reason is always printed.

Nothing is scraped, so the record is **complete by construction**: every model class a project declares
is kept, not trimmed to the one the second opinion happens to need, because the tier binding reads the
same ladder today and a deferred work package's model choice reads it next
([ADR 0021](0021-athlos-deferred-work-packages-and-handoff.md)). Where a class is missing, the entry
says the owner has not declared it — which is an invitation to configure, not a gap to fill by
snooping.

### D14 — The routed unit is `(provider, model)`; model routing and the second opinion are separate concerns

`Decision-ID: ADR-0024/D14`

Routing answers one question for every consumer: **which provider, and which model of it**. The
provider table is the single owner of that pair. What each consumer decides for itself is the **rule
that picks the model inside a provider**:

- the **second opinion** takes the **strongest declared model** — it exists to be the best available
  mind — `"model_rule": "max"` over the provider's declared `models`;
- the **tier binding** keeps its own policy untouched (`selection_policy`, per-kind floors, the
  auditor's opt-in rung): a `worker` delegate must not climb a provider's list because the second
  opinion's rule says to;
- a ladder entry `carrier:model` (D05) **overrides the rule** for that provider — the owner's pin.

So the walk selects the provider and the consumer's rule selects the model; neither function decides
both. Two tangles are retired by this: `second_opinion_fallback_model` ranks the *reviewer's* model on
the **session vendor's** rungs — a different consumer's ladder, silently borrowed — and
`Binding.second_opinion_cli` stores the second opinion's answer inside the tier binding at all.

A provider that declares no `models` yields `model=None`, meaning "the carrier's own default" — the one
honest answer left. *Rejected:* letting the second opinion's rule read the binding's rungs; that is how
a reviewer quietly inherits a `worker`'s model list, the same coupling class this record removes
elsewhere.

## Consequences

- **Retired**, each raising a named error that quotes the file that carries it — the same discipline
  akmon already applies to the `cli`/`invoke` pair (`routing.retired_second_opinion_keys`,
  `routing.py:362-370`, mirrored in `bin/verify.py` and both test suites): `diversity_ladder`, the
  per-vendor `second_opinion` sub-objects, `opposite_vendor`, `Binding.second_opinion_cli`, the
  vendor-equality resolver, and the two local keys `second_opinion_provider` and
  `second_opinion_fallback_model`. A deep-merged stale key looks usable and silently means something
  else, which is why it is refused rather than ignored.
- **Consumer-facing breakage.** Every consumer's local config carries at least one of those keys, so
  the upgrade step ships in the changelog, not only in code; `verify` names the file and the key.
- **`--vendor qwen` becomes valid** the moment the qwen vendor block and command row exist — the
  defect this record was written for.
- **Both implementations change together** (ADR 0020): `tools/model_routing/{routing,second_opinion,init}.py`
  and their twins in `js/tools/model_routing/`, with the conformance rows and seeded violations added
  in the same change, and each new behaviour observed red before it is green.
- **Existing chain tests re-pin loudly.** They pin today's absolute two-step order and mutate the
  provider table by name; that re-pin is the intended evidence, not collateral. Two functions this
  makes load-bearing — availability and the different-model fallback — carry no test today and gain
  one.
- **Relations kept honest:** the per-family concrete-slug rule stays with
  [C148](../../meta/TASKS.md) (D03 reads the catalog, it does not decide what a family's newest slug
  is); the vendor-specific directories a `report_dir` names stay with
  [A25](../../meta/TASKS.md); the gate run that calls this tool stays with
  [C96](../../meta/TASKS.md). This record changes none of them, and the row that reads the catalog is
  written so C148's owner decision remains the single source.
- **A developer who reorders the ladder chooses their own diversity.** The team default is a starting
  order, not an enforced policy: the resolver enforces priors and leaves priority to the list it was
  given.

## Rejected alternatives

- **Keep vendor equality and add the missing family to the list.** Cheapest, and fixes only the
  visible symptom: a carrier pointed at another vendor's weights still reports success.
- **Slots over one flat ladder.** Only meaningful if "a second opinion must be a harness" were a rule
  rather than a preference. As a preference, position says it; slots cost a collapse rule and a second
  owner of the order.
- **Ask the developer for their priors at every session start.** Correct where they exist,
  unanswerable where they do not, and it re-creates per-machine configuration as the team default.
  Kept as the pin in D03 step 1, rejected as the primary path.
- **A gateway client inside akmon so the row can ship.** Rejected by D09: a standard's repository is
  not where a project's internal endpoint belongs.
- **Derive the family by calling the carrier and asking it what it is.** Slower, paid, and a model's
  self-report of its own identity is not evidence. Rejected; D03 reads configuration files only.
