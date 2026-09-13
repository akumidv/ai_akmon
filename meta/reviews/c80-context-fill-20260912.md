# C80 — how full sessions get against the recommended maximum

> **Verdict: `recommended_max: 200000` is a configurable owner policy — set from a typical
> one-task development session, not an empirical optimum — and this replay neither confirms
> nor moves it.** The replay measures habits and warning frequency, not model quality or real
> savings: transcripts show where sessions *go* and where they get compacted; they carry no
> quality signal, so they cannot show where quality *drops*. The owner's decisions taken on this evidence (bands 0.85
> and 1.0, an env override, no stored limit) are [D2-42](../D2_LEDGER.md). What the replay does
> settle: (1) 200k is not a technical limit on either harness — Claude
> main chains run to 412k, Codex to its own reported window; (2) the owner, with no akmon
> warning wired, compacts Claude sessions by hand at a median of 167,968 tokens (0.84 of 200k);
> (3) Codex writes the model's window into every `token_count` record, so on Codex the limit
> is read, not guessed; (4) the per-model samples are too small, and too dependent on when the
> owner compacts, to justify a per-model entry in `recommended_max_by_alias`.
>
> Owned by [C80](../TASKS.md). Policy context: [design §12](../design/model-routing.md),
> [D2-38](../D2_LEDGER.md).

## Environment and method

| | |
|---|---|
| date | 2026-09-12 |
| harness builds | Claude Code 2.1.270; codex-cli 0.154.0 |
| Claude corpus | every `~/.claude/projects/*/*.jsonl` on this machine: 22 main-chain transcripts (16 akmon, 6 from two other projects), 5 subagent transcripts |
| Codex corpus | every `~/.codex/sessions/**/*.jsonl`: 150 rollouts — `session_meta.source` `cli` 23, `exec` 44, subagent 83 |
| Claude fill | akmon's own `routing.context_fill` on each main-chain assistant turn (`isSidechain` and `<synthetic>` skipped), deduplicated by `message.id` — the number the C23 hook bands |
| Codex fill | `token_count.info.last_token_usage.input_tokens` (the prompt of that call, cached part included), deduplicated on `total_token_usage`; model from the preceding `turn_context` |
| compaction | Claude `system`/`compact_boundary` → `compactMetadata.trigger` + `preTokens`; Codex `event_msg`/`context_compacted` (no trigger field) → the last fill before it |
| warnings | the C23 band-rise logic (warn when the band rises; a fill below the lowest band resets) replayed over each Claude main-chain turn sequence |

The replay only reads transcripts; nothing was written outside a scratch directory.

## Claude main chain — fill per model

Session peaks, tokens. A session that switched models counts once per model.

| scope | model | sessions | turns | peak p50 | p75 | p90 | max | sessions peaking ≥134k / ≥170k / ≥200k | turns ≥170k |
|---|---|---|---|---|---|---|---|---|---|
| akmon | claude-opus-5 | 9 | 3,691 | 223,383 | 348,489 | 383,407 | 411,203 | 9 / 6 / 6 | 29.8% |
| akmon | claude-sonnet-5 | 4 | 356 | 205,655 | 205,655 | 319,730 | 319,730 | 2 / 2 / 2 | 48.9% |
| akmon | claude-fable-5 | 1 | 212 | 148,183 | — | — | 148,183 | 1 / 0 / 0 | 0.0% |
| other | claude-opus-5 | 1 | 27 | 83,311 | — | — | 83,311 | 0 / 0 / 0 | 0.0% |
| other | claude-haiku-4-5 | 1 | 1 | 36,483 | — | — | 36,483 | 0 / 0 / 0 | 0.0% |

Claude subagents stay small: 5 transcripts, 43 turns, peak 50,822 (sonnet-5) and 43,014
(haiku-4-5).

**Per-model reading.** Opus-5 and sonnet-5 peak at different levels here, but a session's peak
is set by how long the session runs and when the owner compacts, not by the model; with 9, 4
and 1 sessions per model the difference is not evidence that one model needs its own ceiling.
A per-model `recommended_max_by_alias` entry needs per-model *quality* evidence (§Published
evidence), not a fill-rate difference.

## Claude compaction — all manual

53 `compact_boundary` records, **every one `trigger: manual`**, although
`autoCompactEnabled` is `true` in the owner's settings: in this corpus the owner always
compacted before the harness would have. akmon's own tree wires no hooks (D2-38 verify (5)), so
none of these compactions followed an akmon warning — they are an unprompted baseline.

| `preTokens` (52 records; one 1,973-token re-compaction excluded) | tokens |
|---|---|
| p10 / p25 / p50 | 93,235 / 123,125 / 167,968 |
| p75 / p90 / max | 224,758 / 321,523 / 412,072 |
| records ≥134k / ≥170k / ≥200k / ≥258,400 | 35 / 23 / 21 / 9 |

The median manual compaction, 167,968, sits at 0.84 of the recommended maximum — within a
percent of the current high band (0.85). Two in five compactions happened past 200k.

## Warnings the bands would raise

The C23 band-rise logic replayed over the Claude main-chain sessions with usage — **one corpus
snapshot for every row: 2026-09-13 07:43, 13 sessions, 4,320 turns.** It replaces a 2026-09-12
run whose corpus the continuing session has since grown, so no row compares across snapshots.

| policy | sessions warned | warnings | most in one session |
|---|---|---|---|
| **adopted** ([D2-42](../D2_LEDGER.md)): 200k × [0.85, 1.0] | 7 / 13 | 46 | 16 |
| baseline at replay (shipped before D2-42): 200k × [0.85, 0.95] | 7 / 13 | 48 | 17 |
| 200k × [0.67, 0.85, 1.0] | 10 / 13 | 85 | 30 |
| 200k × [0.67, 0.85, 0.95] | 10 / 13 | 87 | 31 |
| 200k × [0.70, 0.95] | 10 / 13 | 61 | 21 |
| 150k × [0.85, 1.0] | 10 / 13 | 75 | 26 |

A warning fires once per band rise and re-arms when the fill falls below the lowest band, so
the count tracks pressure episodes: the 16-warning session is one long session compacted many
times. The max-band warning fires once per episode — also when the fill jumps straight past
100% — and after it no further band or repeated warning fires until the episode resets. A first band at
two thirds of 200k nearly doubles the total (46 → 85).

## Codex — the window is in the transcript

Every `token_count` record carries `info.model_context_window`, and on this machine every one
reads **258,400** — for gpt-5.6-sol, gpt-5.5, gpt-5.6-luna, gpt-5.4-mini and gpt-5.6-terra
alike. Codex also compacts on its own:

| | tokens |
|---|---|
| `context_compacted` events with a prior fill | 521 |
| prior fill p10 / p50 / p90 | 77,024 / 173,794 / 223,693 |
| highest fill in the whole corpus | 239,604 (92.7% of 258,400) |

| source | model | sessions | turns | peak p50 | p90 | max | turns ≥170k |
|---|---|---|---|---|---|---|---|
| cli | gpt-5.6-sol | 8 | 3,506 | 177,551 | 224,476 | 231,051 | 15.6% |
| cli | gpt-5.5 | 13 | 1,289 | 163,380 | 232,086 | 239,604 | 14.7% |
| subagent | gpt-5.6-sol | 78 | 29,972 | 174,534 | 231,051 | 237,040 | 16.9% |
| subagent | gpt-5.6-luna | 4 | 186 | 225,595 | 227,807 | 227,807 | 12.4% |
| exec | (all) | 44 | 71 | ≤ 21,014 | — | 24,383 | 0.0% |

The event carries no trigger, so manual and automatic compactions are not separable; the
ceiling of 239,604 is the observed top. Unlike Claude subagents, Codex subagents here are long
and fill to the window.

The C23 detector does not run on Codex (D2-37: accepted Claude-only, Codex-pending); this is
the data a Codex half would read.

## Where the limit can be read

| harness | source | cost | reaches the model-routing hook |
|---|---|---|---|
| Codex | `token_count.info.model_context_window`, every turn, in the transcript the hook would already read | none | yes, if a Codex half is built (D2-37) |
| Claude | status-line stdin `context_window.context_window_size` — the owner's `~/.claude/statusline-command.sh` reads it today | none, but only the status-line command sees it | no — hook input carries no window field |
| Claude | Models API `max_input_tokens` | network, an API key the hook does not hold, a cache | only by a new fetch |
| Claude | transcript | — | no window field |

## Published evidence

Vendor documentation first. Every page was opened on 2026-09-12; quotes are verbatim.

**Quality against length**

| source | finding | kind |
|---|---|---|
| Anthropic, [Context windows](https://platform.claude.com/docs/en/build-with-claude/context-windows) | "As token count grows, accuracy and recall degrade, a phenomenon known as context rot." No numeric threshold. | vendor docs |
| Anthropic, [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | context rot as "a performance gradient rather than a hard cliff"; curate the context rather than spend the capacity. No number. | vendor engineering article |
| Anthropic, [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) | the next session starts from a progress file and git history: "write summaries of its progress in a progress file" | vendor engineering article |
| Chroma, [Context Rot](https://www.trychroma.com/research/context-rot) (2025) | 18 models incl. Claude 4: "model performance consistently degrades with increasing input length"; non-uniform across models | not vendor — research by a retrieval-database company |
| [NoLiMa](https://arxiv.org/abs/2502.05167) (ICML 2025) | needle retrieval without literal overlap: 10 of 12 models fall below 50% of their own short-context score at 32K; GPT-4o 99.3% → 69.7% | peer-reviewed |
| [Lost in the Middle](https://arxiv.org/abs/2307.03172) (TACL 2024) | accuracy depends on where the relevant text sits; worst multi-document QA case drops "by more than 20%", and the size of the effect varies by model and task | peer-reviewed |
| [RULER](https://arxiv.org/abs/2404.06654) (COLM 2024) | most models claiming ≥32K fail its threshold well before their claimed length, despite near-perfect needle scores | peer-reviewed |
| Paul Gauthier (Aider), [Hacker News comment](https://news.ycombinator.com/item?id=42831769#42834527) | "Every model seems to get confused when you feed them more than ~25-30k tokens." | practitioner remark, not a measurement |

They agree on the direction — quality falls with length, gradually and differently per model —
and on nothing else. **None measures a model this corpus runs** (claude-opus-5, sonnet-5,
fable-5, gpt-5.6), so none supplies a number to adopt.

**Harness limits and levers**

- **Claude Code** ([model configuration](https://code.claude.com/docs/en/model-config)): on the
  Anthropic API, Fable 5.1, Fable 5, Sonnet 5 and Opus 4.7 and later run with the 1M window by
  default and "compact before the window fills, at about 967K tokens by default". The
  threshold is set with `/autocompact` (saved as `autoCompactWindow`), `--autocompact`, or
  `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (100K–1M); `CLAUDE_CODE_DISABLE_1M_CONTEXT=1` treats
  native-1M models as 200K. A percent-based `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` circulates in
  third-party guides and is not in the official page.
- **Claude Code status line** ([statusline](https://code.claude.com/docs/en/statusline)):
  `context_window.context_window_size` ("200000 by default, or 1000000 for models with
  extended context"), `used_percentage`, `remaining_percentage`, `current_usage`.
  **Hook input** ([hooks](https://code.claude.com/docs/en/hooks)): the common fields and the
  SessionStart fields carry no window or usage field; the UserPromptSubmit-specific section was
  not rendered in full, so that one event is unverified.
- **Claude API** ([models](https://platform.claude.com/docs/en/api/models/list)): `ModelInfo`
  carries `max_input_tokens` — "Maximum input context window size in tokens for this model";
  the request needs an API key. [Context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)
  (beta `context-management-2025-06-27`, tool-result and thinking-block clearing) and
  [server-side compaction](https://platform.claude.com/docs/en/build-with-claude/compaction)
  (beta `compact-2026-01-12`, 4.6-and-later models) are Messages API features for
  applications that build their own requests; akmon runs inside a harness and builds none, so
  neither is a lever it holds.
- **Codex** ([openai/codex](https://github.com/openai/codex)): `TokenUsageInfo` carries
  `model_context_window` (`codex-rs/protocol/src/protocol.rs`); with
  `model_auto_compact_token_limit` unset, the effective window is 95% of it
  (`effective_context_window_percent: 95`, `codex-rs/models-manager/src/model_info.rs`). The
  observed top of 92.7% sits under that line.

Read together with the replay: on Claude the harness would compact near 967K while the owner
compacts near 168K, so the bands are the only early signal the session gets; on Codex the
harness compacts near 245K, and a 200K recommended maximum would warn at 170K and 200K —
between the owner's typical fill and the harness's own compaction.
