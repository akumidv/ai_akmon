# C194 — does the ergon/athlos/step vocabulary cost an agent work?

The owner asked whether replacing the everyday words (handoff, checkpoint, kit, job) by ADR 0029's
*ergon*, *athlos* and *step* makes an agent take extra steps, ask back, or read the documentation
before it acts — measured on the simplest model of each route — and then whether plain or standard
words would serve akmon better. The findings are [M221–M223](../MEASUREMENTS.md); the reading of
them for the design is in
[the merge record § 12](../../docs/design/ergon-athlos-merge.md#12-the-vocabulary-measured).

## Design

One standalone project (`fixture/`): a small Python package, an `AGENTS.md` (copied as `CLAUDE.md`
and `QWEN.md`, so each harness loads the same text) and a work layer with two pieces of work (C12
with two units, C9 with one). The fixtures differ **only in words and in how much definition they
carry**:

| Fixture | Piece of work | Unit | Stopping for another session | Definition |
|---|---|---|---|---|
| G | ergon, `.ergon/<id>-<name>/` | athlos (pl. aethla), `aethla/<n>-<label>/ATHLOS.md` | park, `PARK.md` | `docs/method.md`, seven lines, pointed to from `AGENTS.md` |
| H | kit, `.work/<id>-<name>/` | job, `jobs/<n>-<label>/JOB.md` | hand off, `HANDOFF.md` | the same document in these words |
| S | epic, `.epics/<id>-<name>/` | task, `tasks/<n>-<label>/TASK.md` | hand off, `HANDOFF.md` | the same document in these words |
| G0, H0, S0 | as G, H, S | | | no `docs/`; `AGENTS.md` says only "Work is tracked in `.ergon/`" (`.work/`, `.epics/`) |
| GL | as G0 | | | no `docs/`; `AGENTS.md` carries a one-sentence gloss of the four words |

The S fixture is the standard project-management vocabulary. Its *task* collides on purpose with
what a backlog already calls a task: the plan line's `tasks:` field names the backlog task a unit
serves, exactly as akmon's plans do.

**Arms** pair a fixture with a prompt: G, H, S, G0, H0, S0 and GL speak their fixture's words; X
(over G) and X0 (over G0) speak the everyday words — "job", "work package", "checkpoint" — to a
project that ships the design's words.

**Tasks** (`PROMPTS` in `runner.py`): T1 read the next step of C12.2; T2 mark a named step done; T3
add a unit to C12's plan (label, backlog task C14, zone, after C12.2, result); T4 park / hand off /
checkpoint C12.2; T5 the same for "the unit of C12 that is in progress", without its id; T6 define
the three words from the project's own files.

**Series:**

| Series | Arms × tasks | Runs per route |
|---|---|---|
| 1 | G, H, X × T1–T4 | 36 |
| 2 | G0, H0, X0 × T1–T6, and G, H, X × T5–T6 | 72 |
| 3 | S, S0, GL × T1–T6 | 54 |

3 repetitions a cell; 162 runs per route, 486 in all.

**Scoring** (`score` and `functional` in `runner.py`) reads the run's copy of the fixture and its
final answer.

- **Correct** is strict: T1 the next step only; T2 exactly that line changed; T3 the new line in
  the plan's format with id `C12.3`, no other file; T4/T5 the note in the unit's folder under the
  fixture's file name with its four sections and a `## Next` that names the row writing; T6 each
  word defined from the files, nothing changed.
- **Functional** is right in substance, file format and placement aside: T3 a plan line that keeps
  `tasks: C14` and does not take C14 as its own id (an extra unit file is allowed); T4/T5 a note
  about the rows anywhere under the piece of work; T6 the step defined and no word called
  undefined.
- From the run's event stream: tool calls, whether `docs/method.md` was read, a `?` in the final
  answer (a crude ask-back signal), wall time, total tokens.

The first T4 criterion asked for the literal "row writer" and failed six correct notes; it was
loosened to "row" in `## Next`. The functional T3 check first let a swapped id through and was
tightened. Each change re-scored every run from its kept copy (`runner.py --rescore`).

## Routes and modes

| Route | Model | Mode | Version |
|---|---|---|---|
| Claude Code | `haiku` (stream reports `claude-haiku-5-5`) | `-p --permission-mode acceptEdits --setting-sources project` | 2.1.319 |
| Codex | `gpt-5.6-luna` (`-m`, pin per M86) | `exec -s workspace-write --ephemeral --json`, stdin from `/dev/null` | codex-cli 0.164.0 |
| Qwen Code | `qwen3.8-flash-next` | `--approval-mode auto-edit -o stream-json` | 0.26.1 |

Modes that bypass sandbox and permissions were refused by the session's own safety classifier, so
the runs use the edit-allowing modes above.

## Results

Full tables per route, arm and task are in the materials (`results/summary.md`). Functional score,
mean tool calls and median tokens per arm:

| Arm | Claude `haiku` | Codex `gpt-5.6-luna` | Qwen `qwen3.8-flash-next` |
|---|---|---|---|
| G (series 1) | 12/12 · 5.0 · 81k | 12/12 · 4.7 · 195k | 12/12 · 6.8 · 190k |
| H (series 1) | 12/12 · 5.6 · 91k | 12/12 · 4.7 · 192k | 12/12 · 7.9 · 265k |
| X (series 1) | 12/12 · 5.7 · 92k | 12/12 · 4.9 · 197k | 12/12 · 7.0 · 224k |
| G0 | 18/18 · 7.8 · 103k | 16/18 · 6.3 · 247k | 18/18 · 8.3 · 294k |
| H0 | 17/18 · 7.5 · 110k | 15/18 · 5.6 · 223k | 18/18 · 8.2 · 261k |
| X0 | 18/18 · 7.1 · 90k | 18/18 · 5.7 · 214k | 18/18 · 8.0 · 266k |
| S | 15/18 · 5.4 · 72k | 17/18 · 4.4 · 161k | 18/18 · 8.4 · 256k |
| S0 | 15/18 · 7.7 · 74k | 15/18 · 5.3 · 178k | 18/18 · 9.1 · 307k |
| GL | 18/18 · 4.4 · 81k | 18/18 · 4.7 · 162k | 18/18 · 7.8 · 263k |

No run in any arm asked back before acting: a `?` closed 4 of 486 answers, each an offer or an open
question handed to the next session after the work was done (Claude S0, H0, X0; Qwen X0).

**The standard words collide.** T3 asks for a unit "for task C14". In S and S0 the model took C14
as the new unit's own id, or put C12 in the `tasks:` field, in 10 of 18 runs: Claude 6/6, Codex
4/6, Qwen 0/6 — with the definition present (S) as well as without it (S0). Over the other 63 T3
runs (G, H, X, G0, H0, X0, GL) it happened once (Codex, G0). Codex S0 T6 also read "task" as the
`tasks:` field and "step" as a plan line.

**A word with no definition is read from the structure.** Without `docs/` (G0, H0, X0, S0) every
route still did the tasks; T6 defined *ergon*, *athlos* and *step* from the folders alone in 9/9 G0
runs. On H0, Codex twice said "a kit is not defined in this project's files". What the missing
definition costs is about 1.5× the tool calls, in every vocabulary.

**The word steers placement where nothing else fixes it.** T5 without a definition: "park the
athlos" put the note in the athlos's folder in 9/9 runs; "write a handoff" or "a checkpoint" put it
at the level of the piece of work in 17 of 27 (H0, X0, S0). With any definition (G, H, X, S, GL)
every T4 and T5 note sat in the unit's folder.

**Format comes from a document, not from a word.** Without one, runs dropped the `C12.3` id, added
a unit folder beside the plan line, or left out a note section — in every vocabulary. That is what
separates *correct* from *functional* in the 0 arms and in GL.

**The one-line gloss is the cheapest arm that is fully right.** GL scored 54/54 functional at the
fewest tool calls of any arm on Claude and with the series-1 cost on Codex; T6 took 0.3–1 tool
calls and 17–57k tokens on Claude and Codex. Its strict misses are format, as above.

## Follow-up — the gloss as C189 ships it

The owner widened the GL sentence into the gloss that `AGENTS.md` and the shipped block carry
([ADR 0029/D10](../../docs/adr/0029-ergon-athlos-step-one-method-of-work.md#d10--the-words-are-glossed-in-the-entry-file-with-the-words-a-user-may-say)):
the readings of the everyday words, and *task* named as ambiguous. Fixture `GL2` (series 4) is GL
with that text and nothing else changed; the same six tasks, 3 runs a cell, the same modes and
versions (Claude Code 2.1.319, codex-cli 0.164.0), Qwen not run on the owner's word. Result
([M237](../MEASUREMENTS.md)): functional 18/18 on Claude and 18/18 on Codex, strict 10/18 and 12/18
(GL: 10/18 and 11/18), mean tool calls 5.1 and 5.1 (GL: 4.4 and 4.7); no ask-back. The wider gloss
costs no measurable work, and its misses are the format ones the gloss does not carry. The prompts
still speak the design's words; the readings of the everyday words are not exercised by them.

## Limits

- n = 3 per cell; differences of one tool call are inside the noise.
- One small fixture. A long method document, a large backlog or a session already deep in other
  work is not measured.
- The collision was measured for one wording ("for task C14"); other standard sets (story,
  ticket, milestone) were not tried.
- Qwen reads `QWEN.md`, not `AGENTS.md`, and skips the method document more often; its token totals
  are high in every arm, and its scores do not separate the vocabularies.
- In the 0 arms, "read method.md" counts an attempt: the file does not exist there, and Qwen
  looked for it in 29 of 72 such runs.
- Codex's `model_seen` is the pinned name, not read from the stream (codex's `--json` does not
  carry it); the pin rests on M86.
- Token totals include cache reads and differ in meaning between routes; compare within a route.

## Materials

The fixture (`fixture/`), the runner (`runner.py`: prompts, arms, scoring), `summarize.py` and the
486 scored runs with their final answers and changed files (`results/*.jsonl`) are the ergon's
local materials, `meta/.ergon/C194-vocabulary/materials/` ([ADR 0023/D07](../../docs/adr/0023-project-documents-layout.md#d07--an-experiment-leaves-its-results-in-the-tree-and-its-materials-in-its-ergon)).
This document stands without them. C189 re-runs the GL arm with ADR 0029/D10's widened gloss from
there.
