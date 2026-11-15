# Rules: code

The language-agnostic principles every agent follows when it writes code, in any language and on
any project. Loaded at session start beside the [guardrails](../guardrails/_common.md), because code
is developed in every session.

## Reuse over re-implementation

- Use existing project code, akmon `tools/`, and shared skills before writing new code.
- Put repeatable mechanics into a **tool**, not an ad-hoc script.
- Match the surrounding code's conventions (naming, idiom, comment density).

## Code design — the principles every language inherits

Drawn from the Google Python Style Guide and read for any language; a language's
[profile](../profiles/) says how each reads there, and its checker enforces the mechanical half.

- **A rule a program can check lives in the checker, not in prose.** Prose holds only what no
  checker can see; where a checker enforces a rule, a document names the rule and never
  restates it.
- **Data or behaviour, never half of each.** A value type holds data and no hidden behaviour; a
  behaviour type owns its state. Validation models sit on the boundaries, where data enters.
- **A contract carries a typed object**, not a string-keyed map or a bare string.
- **Return a value or change state — not both — and let the name say which** (`sorted` vs
  `sort`).
- **Failure is raised, never returned.** No `None`, `-1` or `False` as a failure signal. Catch
  only where you can act, keep the protected region to what can fail, and keep the cause.
- **Configuration is read at the entry point and passed down;** nothing deep in the logic reads
  the environment or a file of its own accord.
- **No mutable global state.** A module-level value is a constant.
- **Plain code over power features:** no metaprogramming, reflection-driven dispatch, dynamic
  inheritance, import tricks or finalizers where ordinary code does the job.
- **Concurrency stays at the edges.** Never rely on a built-in being atomic; hand data between
  threads through a queue.
- **A resource is released by a scope** (a context manager, RAII, `defer`), never by hope.
- **Small, focused functions.** A function that has grown past a screen is split, or says why
  it is not; the language's checked rules set the number.
- **Names say what a thing is**, without abbreviations and without its type.
- **The public surface is documented; comments say why, not what.** An error message states the
  condition that failed and names the value.
- **A TODO carries a tracker link:** `TODO: <link> - <what>`.
- **Be consistent with the surrounding code** (§ Reuse over re-implementation).

## API shape — subject first, then how

- **Every callable reads as `f(subject, *rest)`:** the **first parameter is the data it acts on**
  (the *subject* — a frame/object, or a location/handle); parameters **after** it either say
  *what to do* (modifiers/options) or supply *additional data*. So a reader knows *what a call
  operates on* from position alone — applies to **design and code** (architect shapes it,
  engineer writes it).
- **By shape:** *transform* → data first · *method* → subject is `self`, an explicit data param
  comes first after `self` · *reader/loader* → the **location/handle** is the subject (location
  first) · *writer/persister* → the **data** is the subject (data first; destination is a
  modifier) · *factory* (build-from-spec) → **selector first**, exempt.
- A project may pin the specifics and exemptions as a requirement; this is the floor.

## Don't duplicate what the code already states

- Don't hand-maintain metadata that re-states a callable's own **signature or types** (its
  params, input/return kinds, schema): **derive it from the single source**. A parallel
  declaration drifts from the code. Declare only what the signature/type *cannot* express.
