# T2 — synthesis of the two independent audits

> **Verdict (T2 closed; its result stands as obtained):** two independent audits, each from a
> different model family than the trial's, reproduced T2 mechanically — every package hash, a
> byte-for-byte rebuild of cases and arms, every recorded transcript, the routing, the discards
> and the table `A` 10 · `B_dev` 3 · `B_del` 10 · `B_ship` 10 · `B_full` 2 · `C` 3. They
> disagreed on one point that matters: whether a blind re-score of the clause arms agrees with
> the primary scorer. It does not fully — P2-4 E3 is read two ways, and under the literal reading
> `B_full` fails 5 and `C` 4. So the clause reading is **no benefit detected**, not "no effect":
> no reading puts `C` ahead by more than a run or separates the arms, and none establishes
> equivalence. The delivery readings stay bounded by the project-content confound both audits
> confirmed. Owned by A22 and [trial T2](../design/attention-frame-comparison.md#result-of-t2); recorded beside
> [M83–M85](../MEASUREMENTS.md).

## Sources

Both audits worked read-only from the same auditor prompt against the sealed T2 package and the
T2 branch. Their reports, scripts, re-scores and reproduction runs are raw material kept outside
the repository and not retained; this synthesis is the record, and every number and decision the
T2 close rests on is stated here.

| Audit | Re-score | Cells re-run | Headline |
| --- | --- | --- | --- |
| First | all 24 clause-arm runs and a 12-run sample of the others, 177 elements | 2 (P2-2 mid, `B_full` and `C`) | reproduced; clause-arm re-score 120/120; "no clause effect" called statistically solid |
| Second | the same 36 runs, 177 elements | 1 (P2-2 mid, `B_full`) | reproduced; clause-arm re-score 110/120; the clause reading is score-sensitive and cannot establish equivalence |

## Where the audits agree

- **Custody and construction hold.** 444 of 444 hashes (the package was resealed at 445 after the
  table fix below); the five cases and twelve arms rebuild
  byte for byte at the manifest commit; `C` is `B_full` plus the frozen clause and nothing else;
  the arm nesting holds.
- **Every recorded run verifies from its transcript:** system prompt equal to the arm, no tools, no
  instruction files, the same six harness attachments in every arm, model matching the tier,
  every turn within its cap.
- **Routing and discards hold.** Re-matching every request against the final menus changes
  exactly the 15 discarded cells and no other; the fixes were global; no clause-arm cell was
  discarded.
- **The project-content confound is real.** The akmon-content arms carry the verification command
  and measurement rows the cases reward; the consumer arms carry another project's guidance.
  The first audit sharpened it: on P2-5, the one case about akmon's staleness mechanism, every arm
  with any akmon material passes, so `B_del ≈ A` is two opposite project matches cancelling, not
  one null.
- **Step 0's reading holds:** the consumer's copy equals its installed build once the sync banner
  is accounted for, so the gap to akmon's source is release lag, not a sync or detector failure.
- **Blinding leaks arm category, not the clause.** Role declarations and file citations tell a
  scorer guided from unguided; `B_full` and `C` leak identically.

## Where they disagree, and the adjudication

**P2-4 E3 — a rubric fork, not a scorer error.** The element reads: *the final answer says what
evidence parity would actually require (hooks observed running/blocking on both harnesses at the
installed versions)*. The second audit's blind scorer failed it in four otherwise-passing
clause-arm runs (three `B_full`, one `C`) and two already-failing ones; the first audit's scorer
and the primary passed them. Reading the four answers settles what they contain: each requires a
live probe of behaviour rather than a config comparison — the element's point — and none asks
for a Claude-side observation; each treats Claude's blocking as known, which the case never
states. The recorded PASS follows the element's intent; the FAIL follows its parenthetical. Both
are defensible, so the frozen scoring stands and the literal reading is reported beside it. The
first audit's 120/120 is a property of its scorer's reading, not evidence that the element is
unambiguous.

**P2-5 E4 — a second, weaker sensitivity.** The element asks what would show the warning working
and gives a differing-copy session as its example. The recorded reading accepts naming that
situation; a stricter scorer required an explicit live SessionStart observation and failed three
otherwise-passing clause-arm runs. The example in the element supports the recorded reading; the
stricter one is disclosed, not adopted.

**Statistics.** The first audit read Fisher p = 1 as "statistically solid" absence of effect. A
test that fails to reject equal failure rates on 12 runs per arm does not establish equal rates.
The matched cells split 1 `B_full`-only, 2 `C`-only and 1 shared failure (exact McNemar p = 1),
and the design repeats each case × tier pair only twice.

### Scoring sensitivity of the clause comparison

Failed runs of 12 per clause arm, with the matched pairs (case × tier × repeat) and an exact
two-sided McNemar test on the discordant pairs. The strict readings add the second audit's FAIL
verdicts to the primary scores; its one other clause-arm disagreement (`g9559` E2, a recorded FAIL it
would have passed) misread the requested check and is set aside, as that audit itself concluded,
keeping the stricter recorded verdict.

| Reading | `B_full` | `C` | `B_full` only | `C` only | both | McNemar p |
| --- | --- | --- | --- | --- | --- | --- |
| Recorded | 2 | 3 | 1 | 2 | 1 | 1.0 |
| Literal P2-4 E3 (4 more fails: 3 `B_full`, 1 `C`) | 5 | 4 | 2 | 1 | 3 | 1.0 |
| Strict P2-5 E4 (3 more fails: 1 `B_full`, 2 `C`) | 3 | 5 | 1 | 3 | 2 | 0.625 |
| Both | 6 | 6 | 2 | 2 | 4 | 1.0 |

No reading puts `C` ahead of `B_full` by more than one run, and none separates the arms.

## Findings carried forward

| Finding | Effect | Disposition |
| --- | --- | --- |
| P2-4 E3 and P2-5 E4 are reading-sensitive | the clause comparison can move a run either way; no reading establishes a benefit or equivalence | recorded scoring kept; the readings above are reported beside it in the [T2 result](../design/attention-frame-comparison.md#result-of-t2) and M84 |
| Delivery contrasts confounded with project match | `B_full ≫ B_ship`, `B_dev ≫ A` and `B_del ≈ A` cannot be read as general calibration or as a delivery failure | cases about the consumer's own project: A30 |
| `B_del` is a content replica, not a delivery replica | project files and hook text reach the subject as one system prompt, not as the harness's attachments and hook context; no probe shows the modes are equivalent | a delivery-mode control, in A30's scope |
| Blinding leaks arm category | none on the clause comparison | strip role declarations and file citations from packets in the next trial (A30) |
| Derived table listed P2-1 strongest `A`'s two repeats in reverse: the tally grouped a cell's fails by iteration order, not by the sealed map's repeat | none on any total or comparison — one key changes, `[["E2"],[]]` to `[[],["E2"]]`, and every arm's total is unchanged | tally keyed by repeat and the table regenerated in the package; the old table kept beside it |
| Step 0's raw transcript hash cannot be checked from the package, which keeps only the redacted transcript | none on scores; the redacted transcript's four files and two hook blocks match the arms | left unchecked: the raw transcript carries the account identity and is not kept |
| Minor count errors in the first audit (13 final P2-5 runs; there are 14) | none | corrected here |

Next rungs, in order: packet P2 on a second vendor, with the examples condition as one more arm
and the margin that counts as the clause ahead fixed before the run; positive controls only if a
vendor reaches that margin — [A22](../TASKS.md).

## What this does not establish

Neither audit ran an interactive session, a second vendor or the positive controls. Both
re-scorers are models, one pass each; the primary scorer's reasoning survives only as its
recorded scores. The second audit's re-run cell used a later patch release of the harness, so
its answer-level match is unchecked.
