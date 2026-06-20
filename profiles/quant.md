# Profile: quant (numerics)

An **opt-in** domain profile for projects doing quantitative / numerical work — pricing,
Greeks, volatility surfaces, risk measures, time-series, DataFrame pipelines. Attach it by
linking it from the project's `AGENTS.md`; it is *suggested* by `package`-type numerics
projects but only applies if the project actually does numerics.

> A profile adds **domain** rules on top of language [guardrails/](../guardrails/). It does
> not replace them. Where a profile rule and a guardrail overlap, both apply.

## Correctness is owner-verified, not test-verified

Numerical code can pass tests and still be **wrong** (a sign error, a wrong convention, a
silent NaN). So, beyond the common owner-verify rule:

- **State the math.** Any pricing / Greek / risk / smile formula is written down (the
  convention, the inputs, the units) next to the code or in a design doc — not left
  implicit.
- **Owner-verifies the math**, explicitly. Green tests are necessary, not sufficient.
- **Cite the reference** for a formula or method (paper, textbook, standard) where one
  exists.

## Conventions must be explicit

- **Units & day-count.** Time in years vs days, calendar vs trading days, rate
  compounding — stated, not assumed.
- **Moneyness / strike / forward conventions** for smiles and surfaces are declared.
- **Sign & direction conventions** (long/short, call/put, buy/sell) are documented where
  they affect a result.

## DataFrame / array discipline

- **Schema is owned.** Column names/types come from the project's data dictionary; do not
  invent ad-hoc column names. A schema change is an architecture change (owner-verified).
- **No silent coercion.** Guard against unintended dtype changes, index misalignment, and
  NaN propagation; assert shape/columns at boundaries.
- **Vectorize, but verify.** Prefer vectorized pandas/numpy over Python loops — but a
  vectorized rewrite of a formula is a math change and is owner-verified.
- **Determinism.** Set/record seeds for any stochastic step; numerical results should be
  reproducible.

## Numerical robustness

- Handle edge cases explicitly: empty input, single point, extreme/zero vol, deep ITM/OTM,
  expiry, division by ~0.
- Be explicit about tolerances in comparisons and convergence (no bare `==` on floats).
- Surface non-convergence / fit failure (e.g. a smile fit) rather than returning a quietly
  wrong number.

## Tests for numerics

- **Property / invariant tests** where applicable (put-call parity, monotonicity,
  no-arbitrage bounds) — not only point examples.
- **Golden values** from a trusted reference for at least the core paths.
- **Edge-case tests** for the cases above.

## Done (numerics change)

The math is written and referenced; conventions are explicit; schema/shape is asserted;
edge cases and tolerances are handled; property + golden + edge tests pass; and the owner
has verified the math.
