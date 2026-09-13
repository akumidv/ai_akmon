# Attention and human–agent collaboration

## Task brief and direction

This is a living research concept for improving the whole collaboration between a
project owner and development agents. It preserves the problem statement, evidence,
candidate approaches, disagreements, and questions for a later design decision.
It is not an accepted contract, implementation specification, or D2 approval.

The objective is to spend the owner's time and thinking where their experience,
knowledge, judgment, and understanding of future use can improve the product.
Routine investigation, evidence assembly, comparison, and authorized repair belong
in agent-led work; the orchestrator retains integration, final synthesis, and owner
dialogue. Communication should help both parties develop and retain an accurate
shared understanding. Shorter output is useful only when it preserves that
understanding.

The scope includes discovering the problem, eliciting experience and future-use
scenarios, planning, exploring alternatives, deciding, implementing, reviewing,
reporting limitations, following up problems, and returning in a later session.
The difficult D2 walkthrough is a concrete case study, not the scope boundary.

### Owner requirements captured from the discussion

These are attributed English paraphrases of the owner's instructions, not additional
rules inferred from the research:

1. Treat human attention as a central development resource. Explain the plan before
   work and provide a useful account of the result afterwards.
2. Investigate reasonable report size, human information processing during a task,
   and the cost of keeping the task in mind across a stream of messages.
3. Put truthfulness first: do not conceal problems, limitations, or automatically
   adopted decisions. Increase structure as the amount of information grows.
4. Preserve a comprehensible sequence: task, possible solutions, selected solution,
   reasons alternatives lost, implementation, limitations, and problems that became
   tasks or require owner attention.
5. Study other people's findings and competing views, including internet research
   and existing akmon sessions in Codex and Claude. Delegate session inspection to
   simple subagents; do not launch the external applications to obtain summaries.
6. Cover the whole joint thinking process, including system design and future use.
   Improve the transfer of the owner's knowledge and experience into descriptions
   and decisions, not merely the mechanics of D2 acceptance.
7. Sometimes compress the output; sometimes investigate, delegate additional work,
   or research the answer instead of handing routine problems to the owner. Sometimes
   ask an open question about the actual problem or experience, rather than confining
   the owner to options framed by the agent.
8. Preserve the task summary and direction so this design can be revisited. Record
   research in this separate design file; leave other project files unchanged.
9. Account for limited working memory, meaningful chunks, paragraphs and sections,
   and cognitive and emotional biases relevant to design. Investigate confirmation,
   anchoring, attachment to past decisions and experience, and rejection of new ideas.
10. Make challenge symmetrical: neither agree automatically with the owner nor treat
    the agent's proposals as authoritative. Advocate credible alternatives, examine
    counterarguments, and resolve disagreements through evidence and explicit owner
    priorities. Improve product outcomes, not merely functionality; preserve goals
    and exclude work outside the project's purpose.
11. Develop a refinement and implementation plan, including further improvements
    grounded in human cognitive capabilities and limits and in agents' tendency to
    accommodate a position instead of examining its grounds. Distinguish useful
    interaction adaptation from agreement-seeking and unnecessary repeated approval.
12. Present the two connected priorities as the project's mission: human attention
    and joint decision quality; token efficiency for quality through subagents,
    model selection, roles, skills, and controls. Document the reasoning path so
    people and other models can recheck premises and later implementation. The owner
    explicitly extended the original file-only scope to mission/priority updates in
    README and upper-level documents and requested an implementation task. Exact
    decisions and their realization will be verified separately afterwards.
13. Treat this as an economic model of effective resource allocation, not simply
    economy. Additional design time can avoid much larger implementation and rework
    costs; high-leverage analysis and synthesis can justify the most capable model
    at its highest reasoning effort instead of repeated mechanical cheap-model trials.

### Research questions

- What information must be shared to make progress, and what work can an agent absorb?
- How can an agent discover tacit knowledge without turning the owner into its analyst?
- When is an open question, a bounded clarification, a recommendation, or independent
  investigation the right next action?
- What makes a plan, progress message, decision explanation, and final report truthful,
  useful, proportionate, and easy to resume from?
- How should communication change between exploration, execution, and acceptance?
- Which parts need shared principles, role/pipeline guidance, a skill, or mechanical
  support? Would a D2 walkthrough skill be a useful first application?
- How can improvement be measured without rewarding fast but uninformed approvals,
  hiding defects, or creating another reporting burden?
- How can useful disagreement expose faulty assumptions without becoming ritual
  opposition, an emotional contest, or an endless reopening of settled decisions?

## How to resume

Start with this task brief, then the evidence synthesis and open questions below.
Treat numerical budgets as hypotheses unless a cited study directly supports the
specific population and activity. Re-read current source documents and ledger state
before relying on repository observations; historical session excerpts explain
friction but do not establish current implementation or acceptance state.

The next design pass should select a small pilot across problem discovery,
implementation reporting, and D2 review, then settle the interaction contract from
observed usefulness. It should not reopen the entire subject as a D2-only problem,
replace open discovery with a menu, or equate fewer words with better collaboration.

The [refinement and implementation plan](#refinement-and-implementation-plan) now
gives a proposed sequence, concrete evaluation cases, dependencies, and exit
conditions. Resume at AP0 using the already collected episodes; do not restart a
broad literature or transcript survey unless a material gap remains.

The mission direction and the request to record work come from the owner; the
proposed interaction architecture is not locked here. A22 tracks refinement, C86
tracks the gated implementation, and D2-44 isolates verification of the mission
wording. Those records do not authorize unaccepted contracts, new skills, automatic
approval, or consumer changes. See [tracked work](#tracked-work-and-acceptance-boundaries).

## Working synthesis

The design direction is **attention-aware joint problem solving**, not a shorter
report template. The agent should carry routine search, comparison, checking, and
state reconstruction; the owner should retain meaningful control over purpose,
experience-based constraints, consequential trade-offs, and acceptance. Saving a
minute by inducing uninformed agreement is not an improvement.

Five candidate principles organize the findings:

1. Reduce avoidable reconstruction and coordination, not all thinking. Keep the goal,
   current decision, evidence boundary, and next action visible outside human memory.
2. Compress repetition and mechanics, not material uncertainty, dissent, autonomous
   decisions, or failures. A summary must remain true when read without its appendix.
3. Discover the problem before narrowing solutions. Open questions recover knowledge
   the repository cannot contain; investigation answers questions the agent can settle.
4. Make proposals contestable in both directions. Test facts, expose assumptions,
   ask the owner about values, and record what would change the recommendation.
5. Prefer the smallest intervention that improves the intended outcome. A skill,
   report, review round, or feature also has an attention and maintenance cost.

These are research-derived proposals, not accepted akmon rules. Evidence below is
labelled as published findings, repository observations, historical episodes, or
design hypotheses. The literature does not establish an optimal word count, number
of options, streaming speed, or interruption interval for akmon.

### Reading paths

- For the human factors: [memory and attention](#memory-attention-and-information-structure)
  and [bias and disagreement](#cognitive-and-emotional-biases).
- For an interaction proposal: [dialogue routing](#knowledge-transfer-and-dialogue-routing),
  [reports](#truthful-and-proportionate-reports), and
  [arbitration](#symmetrical-challenge-and-arbitration).
- For project fit and later work: [existing foundations](#akmon-foundations-and-gaps),
  [D2 candidate](#d2-walkthrough-as-a-candidate-skill), and
  [pilot and open decisions](#pilot-and-open-decisions).
- For independent checking: [session evidence](#historical-session-evidence) and
  [sources](#sources).
- For the proposed next work: [refinement and implementation plan](#refinement-and-implementation-plan).
- For why that direction was chosen and how to challenge it:
  [mission premises and decision trace](#mission-premises-and-decision-trace).

## Memory, attention, and information structure

### Memory capacity is not a report-length rule

Miller's 1956 paper distinguished several kinds of capacity and emphasized recoding
information into familiar chunks. Its famous seven-plus-or-minus-two formulation is
not a universal limit on reasoning, words, interface options, or report bullets.[^1]
Cowan's later synthesis argues for roughly three to five chunks, averaging about
four, under conditions intended to isolate central capacity from rehearsal and
other memory support. The conditions and meaning of a chunk matter.[^2]

Remembering a short sequence of unrelated digits is not the same task as reading
a persistent report, understanding a design, or checking a claim against a source.

Design inference: do not ask the owner to hold a goal, six opaque task IDs, three
alternatives, and their exceptions in memory while interpreting the next message.
Use recognizable semantic units and put related evidence beside the claim it
qualifies. An expert's familiar subsystem can function as a useful unit; an
unexplained acronym cannot be assumed to do so. Neither seven nor four justifies
truncating a list of real risks.

Paragraphs should answer one local question; sections should group related
questions; a decision should remain attached to its purpose and consequences.
This is a semantic organization proposal, not a prescription for a fixed number of
sentences. Fragmenting every sentence into a bullet can make relationships harder
to reconstruct even when the page looks less dense.

### Headings influence what survives compression

Experiments on expository text found that headings and mental outlines improved
memory for topic organization.[^3] Related experiments found effects varied with
topic familiarity and recall versus summarization tasks.[^33] A particularly
relevant experiment found that selectively heading
only some topics increased their representation in summaries while reducing the
representation of unheaded topics.[^4]

Design inference: truthfulness has a presentation dimension. Large success headings
with limitations buried in an unlabelled paragraph can produce a misleading overall
impression without deleting a single fact. Give material risks, incomplete evidence,
and owner decisions visibility comparable to the claimed result. Headings are
navigation aids, not proof that the report is understandable.

### External state and returning to a task

Cognitive offloading research examines how external actions and representations can
reduce internal processing demands.[^5] A developer study examined about 10,000
programming sessions from 85 programmers. Among analyzed sessions with editing
activity, only 10% began editing within a minute; navigation commonly preceded edits.
This indicates reconstruction work, not a universal estimate of minutes lost per
interruption.[^6]

Four studies of a ready-to-resume intervention found benefits when interrupted
workers anticipated time pressure on returning to unfinished work.[^7] For akmon,
a candidate checkpoint is: intended outcome, current position, settled rationale,
unresolved issue, relevant evidence/artifacts, and exact next action. It should help
the owner and the next agent resume without replaying the conversation. It does not
replace a decision record or prove the owner understands the result.

### Interruptions have multiple costs, not one constant penalty

Mark and colleagues' controlled email-task study found that interrupted participants
compensated by doing the primary task faster, but experienced more stress,
frustration, time pressure, and effort; quality did not significantly differ in that
setting.[^8] Research on notification timing instead investigates task breakpoints
as opportunities for less disruptive delivery.[^9]

Therefore, elapsed completion time alone can conceal increased workload. Batch
routine updates around meaningful results, preserve urgent warnings and real
authorization gates, and accommodate a requested joint walkthrough. Silence can
also be costly when the owner cannot tell whether work is progressing. No reviewed
study supplies an akmon-wide rule such as a message every N seconds.

### Reading, streaming, understanding, and verification differ

A meta-analysis of 190 studies, with 18,573 participants, estimated average adult
silent reading of English nonfiction at 238 words per minute, with substantial
variation.[^10] At that mean, 600 words would take about 2.5 minutes merely to read.
That arithmetic is not an estimate of Russian technical review, understanding an
unfamiliar design, checking sources, or deciding whether to approve it.

An exploratory LLM streaming preprint uses self-reported comfortable rates and
satisfaction proxies to optimize serving, not to establish a general comprehension
limit. Its initial cohort selection excluded some preference patterns, and its
stated scope excludes code generation.[^11] It is a useful research lead, not a
basis for hard token-per-second limits in akmon.

Candidate stream behavior: deliver complete, meaningful progress units; make the
claim and its important qualification available together; retain a stable final
report; never require the owner to watch every token to catch a material change.
Prefer a compact update about changed understanding over a narration of every
search or tool result. A final answer must remain self-contained even when progress
messages are collapsed or were never read.

## Knowledge transfer and dialogue routing

### Shared understanding is a joint accomplishment

Clark and Brennan describe communication as establishing enough common ground for
the current joint activity, with effort distributed across participants.[^12]
Horvitz's mixed-initiative framework considers uncertainty about goals alongside
the costs of acting, asking, and deferring.[^13] Together they support a broader
objective than minimizing the agent's output: minimize avoidable collective work
while preserving understanding and control. Conversational grounding is not formal
permission to change a contract or external state.

The owner's experience should become usable evidence without being silently
converted into an agent-authored requirement. A candidate transfer sequence is:

1. Recover a concrete episode or future-use scenario: who was doing what, what made
   it difficult, what workaround existed, and what success would have looked like.
2. Separate the owner's observation from the agent's interpretation. Preserve a
   surprising exception instead of prematurely generalizing it away.
3. Offer a short interpretation with a concrete consequence and an invitation to
   correct it. Ask about the missing distinction, not for blanket approval of a page.
4. Translate the agreed understanding into a constraint, acceptance example, or
   decision rationale; retain attribution and any remaining uncertainty.
5. Check the proposed result against that scenario after implementation, rather
   than testing only whether the requested feature exists.

Open, neutral questions and accounts of real events are recommended in practical
user-research guidance.[^14] This does not mean conducting a long interview for
every edit. Often one well-placed question is enough. Constructed example:
"When you returned to the last D2 discussion, what did you have to reconstruct
before you could judge the next item?" This can expose a problem that an initial
"short report or long report?" menu would miss.

### Route the missing knowledge, not every uncertainty to the owner

The following is a candidate routing policy, not new authority to mutate files.

| Information or work needed | Agent's next move | Owner-facing content |
| --- | --- | --- |
| Observable repository or external fact | Inspect, search, or delegate a bounded check | Finding, evidence, remaining uncertainty |
| Routine defect inside an authorized implementation | Repair and verify within scope | Material change, effect, verification and residual risk |
| Defect found during review-only work | Diagnose and report; propose a scoped follow-up | Problem and requested authority, not an unrequested fix |
| Lived experience, intended use, priority, or unacceptable outcome | Ask a focused open question, using known context | Why this knowledge changes the design |
| Clear goal but a consequential trade-off remains | Compare credible options against explicit criteria | Recommendation, downside, and a revisable choice |
| Small reversible implementation assumption inside authority | State it and continue when proportionate | Assumption and material consequence, not a needless approval gate |
| Unclear scope, irreversible effect, privacy issue, or missing authority | Stop the affected action and ask | Exact boundary and why owner input is necessary |
| Repeated disagreement without new evidence | Reframe the disputed premise or propose a bounded test | What is unresolved and how it can be resolved |

The agent should not ask the owner to locate an inspectable file, reproduce a check
it can run, reconcile raw subagent outputs, or research an accessible standard.
Conversely, a larger model or more searching cannot determine what the owner values
in future use. Delegation transfers routine work, not accountability for the
synthesis; contradictory or weak subagent evidence still needs checking.

### Exploration and choice are different modes

Use open discovery when the frame is uncertain. Use a bounded comparison when the
frame and criteria are sufficiently understood. Use an execution update when the
decision is already settled. Use an acceptance packet when the owner needs to judge
a particular claim. These modes may alternate within one task.

A provisional convergence check is whether the agent can state a concrete use
scenario, the intended outcome, a decisive constraint or criterion, and the material
unknowns without inventing owner preferences. Reuse what is already known; do not
ask ritual confirmation. If a missing input could change the comparison, ask about
that input. Otherwise offer a recommendation with a revisable frame and stop
open-ended questioning that no longer changes the decision.

Do not ban option menus: a meta-analysis found a near-zero average choice-overload
effect with considerable variation, while a later synthesis identified complexity,
task difficulty, uncertain preferences, and decision goals as moderators.[^15][^16]
There is no supported universal maximum of three options. Offer the meaningful
frontier, distinguish dominated alternatives briefly, and keep the frame revisable.

Conversely, early generated examples can constrain exploration. A controlled study
of 60 participants doing visual ideation found more fixation and less divergent
output with AI image support.[^17] Transfer to text-based architecture menus is a
hypothesis, not a demonstrated effect. A practical safeguard is to elicit the
owner's scenario and decisive criteria before displaying a strongly recommended
solution when those inputs are still unknown.

## Cognitive and emotional biases

### Evidence and limits of the vocabulary

A systematic mapping study identified 65 software-engineering papers concerning
37 cognitive biases. It also found inconsistent definitions, weakly supported
causal explanations, and a shortage of well-established mitigation techniques.[^18]
A catalogue of bias names is therefore not a validated diagnostic instrument or
proof that a particular owner or agent is reasoning badly.

Experiments on the affect heuristic show that overall favorable or unfavorable
reactions can shape judgments of risks and benefits, with time pressure affecting
that relationship.[^19] Frustration, attachment, enthusiasm, and fear of rework
deserve consideration in collaboration, but an agent should not infer a person's
emotional state from a terse message or dismiss their priorities as emotional.
Values and lived experience are inputs to a good decision, not noise to eliminate.

Kahneman and Klein identify conditions for reliable intuitive expertise: an
environment with sufficiently regular cues and opportunities to learn them through
feedback. Subjective confidence alone is not enough.[^20] Thus the correct response
to prior experience is neither automatic deference nor automatic rejection. Ask
which past conditions also hold now, and which have changed. Novelty is not evidence
of superiority either.

### Design-relevant failure patterns and candidate checks

The examples and checks below are constructed proposals for akmon, not measured
bias diagnoses of the sampled sessions. Labels overlap; the useful object of review
is the unsupported inference, not the label.[^18]

| Pattern | Constructed design failure | Candidate check for either party's proposal |
| --- | --- | --- |
| Confirmation: favoring supporting evidence | A passing happy-path test is treated as sufficient because it fits the preferred design | Seek a counterexample; state what evidence would reverse the recommendation |
| Anchoring and design fixation | The first architecture or generated menu defines every later option | Reframe from the actual goal; consider a materially different or smaller approach before convergence |
| Availability and recency | The last vivid incident becomes a universal requirement | Check frequency, affected scenarios, counterexamples, and the cost of designing for a rare event |
| Status quo and belief perseverance | A settled ADR is defended after its premises change | Compare current premises with recorded rationale and revisit conditions |
| Sunk effort and attachment to one's own work | Weeks already spent justify further investment regardless of future value | Compare remaining benefits and costs; preserve useful work without treating past expenditure as a reason to continue |
| Overconfidence and planning optimism | Familiar implementation details obscure unknown integration work | Separate observed facts from estimates; identify an unknown boundary and a test or range |
| Framing, loss emphasis, and affect | A migration is described only as losing control, or a new feature only as an exciting gain | Present both gains and losses for each option; make reversibility and the real feared outcome explicit |
| Authority, automation reliance, and conformity | Owner confidence or polished agent prose substitutes for evidence | Keep an independent objection possible; attach cheap-to-check evidence and expose uncertainty |
| Premature closure and solution accumulation | Agreement or a larger backlog is mistaken for progress toward the product goal | Revisit the success criterion; consider no change, deletion, reuse, or a smaller experiment |

An emotionally safer challenge targets the claim: "This depends on assumption X;
the current evidence is Y; scenario Z could change the choice." It avoids "you are
biased" and does not manufacture a confession or agreement. Acknowledging a concern
is compatible with rejecting an unsupported conclusion. The agent should also
acknowledge its own introduced defects plainly, without using an apology to replace
repair, evidence, or a scope-appropriate follow-up.

Respond to observable communication needs, not presumed emotions. If the owner says
the packet is too much, asks what an item means again, requests joint review, or
states time pressure, briefly restate the point and adapt the mode: one decision,
a concrete example, a shorter overview, or a checkpoint for later. Ask only if the
preferred adjustment is unclear. Check whether the missing distinction is now
clear; do not infer an emotional diagnosis or treat reduced engagement as consent.

### Agent outputs need the same scrutiny

Research on five then-current assistants found sycophantic behavior across several
tasks and evidence that preference judgments could reward agreement with a person's
beliefs over truthfulness.[^21] This supports a real concern, not a capability claim
about today's installed Codex or Claude. It also does not mean language models have
human emotions or that every agreement is sycophancy.

A recent software-engineering preprint studies paired biased and neutral prompts.
It reports limited success for common debiasing instructions and better aggregate
results from making background assumptions explicit. Its open-ended follow-up used
a selected subset where the proposed method had already helped in forced choice,
so that follow-up cannot establish general open-ended effectiveness.[^22] The useful
design lead is to check assumptions and sensitivity to framing, not to install a
purported universal debiasing prompt.

Candidate symmetric check: would the evidence-based recommendation change if the
same facts were presented without knowing which option the owner or author favors?
If it changes, identify whether new information or only social framing explains
the change. An agent-generated critique remains another fallible output; a second
model's confidence or majority vote is not an independent truth criterion.

## Symmetrical challenge and arbitration

### Challenge should change understanding, not perform opposition

In two social-judgment experiments, considering the opposite produced more
correction than instructions merely to be fair or unbiased.[^23] However, work
comparing authentic dissent with assigned devil's advocacy found advantages for
authentic dissent in solution quantity and a combined quantity/quality measure;
quality alone did not significantly differ in the reported comparison.[^24]
These are human experimental findings, not proof that prompting a subagent to
argue the opposite improves architecture decisions.

Candidate rule: request the strongest credible alternative and the evidence that
could make it win. Do not reward the production of objections, inflate a weak
alternative to create symmetry, or require opposition to a trivial edit. Preserve
genuine disagreement found during independent examination instead of forcing
reviewers to converge before the owner sees it.

### A bounded decision challenge

For a material, uncertain, or disputed decision, a proposed packet contains:

1. The intended outcome, scope, and strongest current recommendation, including
   its main assumption and cost.
2. The strongest credible alternative, including status quo or a smaller change
   where viable, with the criterion under which it would be preferable.
3. A disconfirming case for the preferred option and the evidence already available.
4. The unresolved disagreement, its resolution route, and a clear stopping condition.

Invite the owner to contribute knowledge or challenge the argument, not just select
a letter. Constructed prompts include: "Which real use case makes this trade-off
unacceptable?" and "What consequence is missing from my comparison?" A bounded
priority question is also useful after framing: "If these criteria conflict in
your workflow, which should take precedence, and why?" The owner can reject the
criteria or frame rather than choosing among agent-defined values.

### Arbitration is not always another opinion

| Kind of disagreement | Suitable resolution | What remains in the record |
| --- | --- | --- |
| Factual: behavior, compatibility, source claim | Inspect primary evidence, reproduce, or commission an independent bounded check | Claim, result, limitations, and whether the conclusion changed |
| Goal or value: convenience versus control, current versus future use | Elicit the owner's scenario and priorities; make the consequence concrete | Owner's reason and accepted trade-off, not an invented factual consensus |
| Unmeasured prediction: performance, adoption, comprehension | A proportionate experiment, reversible trial, or explicitly provisional choice | Assumption, success/failure observation, and revisit trigger |
| Product boundary: useful feature but outside purpose | Compare against non-goals; reject, defer, or request a separate scope decision | Why it is outside the current task and whether any follow-up was actually created |
| Contract or authority conflict | Follow existing ownership and approval rules; ask for the missing decision | Exact unresolved boundary and permitted next action |

Use one bounded evidence/rebuttal round as an initial pilot default, then stop if
there is no new evidence or request owner direction. This is not a prohibition on
a requested full review or on investigating a newly found serious defect. The
existing review pipeline already has a bounded reround mechanism; a future design
should integrate with it, not create a competing loop.

If the owner knowingly chooses a value trade-off, record it and proceed within
authority. Preserve residual risk and the condition for reconsideration; do not
keep litigating the same preference. If a factual assertion remains unsupported,
owner choice does not make it established fact. Likewise, the agent cannot use
"arbitration" to overrule owner-controlled product choices or grant itself approval.

### Useful friction versus bureaucratic friction

In an experiment with 199 participants, cognitive-forcing interventions reduced
overreliance on AI, but the strongest interventions were evaluated less favorably
and benefits varied with participants' motivation for effortful thinking.[^25]
Other experiments found that explanations can help when they make checking an
answer worthwhile and affordable; explanation presence alone is insufficient.[^26]

Design inference: put effort into a consequential assumption, a counterexample,
or a clear acceptance boundary. Remove effort spent opening unrelated files,
reconciling statuses, or approving routine steps. A mandatory challenge, confidence
rating, and quiz on every message would create a new burden and could encourage
ceremonial answers. The aim is appropriate reliance and correction, not either
maximum trust or maximum skepticism.

## Truthful and proportionate reports

### Candidate requirements

These requirements translate the task brief into reviewable properties. They are
proposals for a later contract, not a new mandatory schema.

| ID | Property | Practical acceptance question |
| --- | --- | --- |
| R1 | Truth and scope of claims | Does each material claim say what was actually established, on which subject, and with what limits? |
| R2 | No material concealment | Are unresolved problems, missing checks, consequential autonomous choices, and dissent visible rather than buried? |
| R3 | Evidence calibration | Are observation, inference, assumption, proposed action, and owner acceptance distinguishable? |
| R4 | Coherent causal account | Can the reader connect the task and criteria to the choice, implementation, result, and remaining work? |
| R5 | Proportional structure | Do meaningful sections grow with complexity without turning a small edit into a formal essay? |
| R6 | Low verification cost | Can the owner inspect the decisive evidence without reconstructing raw logs or the entire repository? |
| R7 | Status precision | Are implemented, tested, reviewed, owner-approved, landed, and D2 Verified kept distinct? |
| R8 | Decision provenance | Is it clear what the owner chose, what the agent assumed within authority, and what remains undecided? |
| R9 | Actionable residuals | Does every material unresolved issue have a clear disposition, without claiming an uncreated task exists? |
| R10 | Goal and scope fit | Does the report assess the intended outcome, including non-goals and important costs, not just feature completion? |
| R11 | Resumability | Can a later reader recover the current state, rationale, open issue, and next step without the live stream? |
| R12 | Contestability | Is it possible to challenge the premise, evidence, criteria, or conclusion without accepting the agent's menu? |

"Material" should include anything that could change acceptance, intended behavior,
scope, risk, compatibility, verification confidence, or significant future cost.
Consequential autonomous decisions deserve individual treatment. Routine local
choices can be grouped by effect, with a link to the change; an exhaustive account
of every keystroke is not transparency. Neither a word budget nor grouping permits
hiding a real problem.

Truthful rationale means evidence-based reasons, not a claim to expose every inner
reasoning step. Do not invent alternatives after implementation and present them
as if they were evaluated beforehand. A retrospective comparison can be useful if
labelled as such. When a prior report overstated completion, explicitly correct the
earlier claim and its practical consequence.

### The account and its layers

The full substantive account follows the requested sequence: task and success
criteria; viable solutions; choice and rejected alternatives; implementation and
deviations; verification and limitations; problems, routing, and next decisions.
The opening can still be result-first: it is an accurate orientation to that
account, not a substitute for it. For an already locked design, link its rationale
and explain only new decisions or deviations instead of reopening every option.

Use a short overview plus an accessible full record when needed. Keep decisive
evidence directly reachable rather than behind several levels of summaries.
Progressive disclosure is an established interaction-design technique, but its
usefulness depends on putting important material in the first layer and making the
rest discoverable.[^27] Human–AI interaction guidelines similarly emphasize limits,
context, correction, and support for understanding behavior.[^28]

A compact report can combine fields in prose. A larger one should separate decisions
and verification boundaries; it need not repeat an empty template under every
heading. One significant decision per durable record has a useful precedent in
architecture decision records. Nygard emphasizes context and consequences, including
negative ones; MADR also captures drivers, options, outcomes, and confirmation.[^29][^30]
Reuse those records rather than creating a second source of truth in chat.

### Plans, updates, and final reports serve different jobs

An upfront plan makes the agent's interpretation and intended boundary inspectable:
goal, relevant steps, evidence strategy, important assumption, and any real owner
gate. It is not a request to approve routine mechanics. When the plan changes
materially, show what changed and why.

A progress update reports a meaningful delta: what was learned or completed, what
changed in the plan or confidence, and whether owner attention is needed now.
Separate "no action needed" from a question that blocks a scoped action. Avoid
requesting approval through a passive progress statement.

A final report includes the achieved result, evidence boundary, material choices,
remaining problems, and exact next action or absence of one. Failed checks need
scope and cause where established; an environment-confounded failure is neither a
product failure nor a passing check. Historical or pre-existing failures must be
identified, not silently attributed to the current change or silently excluded.

Before closing a substantial report, reconcile the scoped evidence: relevant check
results, subagent findings, implementation deviations, and unresolved owner points.
Give each material finding a disposition: supported and addressed with evidence,
supported and unresolved, contradicted with evidence, duplicate of a retained
finding, or outside scope and routed. Preserve consequential disagreement and the
reason for exclusion in the full record; do not silently discard negative evidence.
Compare the opening completion claim with those dispositions. A request for brevity
does not authorize making that claim stronger than the evidence.

### Lifecycle handoffs

This candidate map covers transitions beyond D2; the pilot below samples only
some of them. A checkpoint is a compact handoff in an appropriate existing record,
not a requirement to create a document at every transition.

| Transition | State that should survive | Meaningful owner involvement |
| --- | --- | --- |
| Discovery to design | Scenario, intended outcome, attributed constraints, unknowns | Correct a consequential misunderstanding |
| Design to implementation | Chosen scope, rationale, acceptance examples, unresolved gates | Make the value or authority decision that cannot be delegated |
| Implementation to review | Actual delta, autonomous choices, deviations, evidence subject | Supply a missing real-use consequence, not repeat mechanical tests |
| Review to acceptance | Ranked issues and dispositions, coverage limits, exact acceptance boundary | Judge the consequential trade-off and acceptance scope |
| Acceptance to follow-up | Precise status, residual risk, task actually filed or only proposed, ownership | Decide new scope or accept an explicitly described residual |
| Pause to later resumption | Goal, settled rationale, current cursor, open issue, next action, stale-evidence warning | Restore context and revise intent if it has changed |

### Size as an explicit pilot hypothesis

The following English word ranges are deliberately provisional editorial starting
points. They are not scientific limits, acceptance thresholds, Russian-language
norms, or reasons to omit required information. Complexity, unfamiliarity, coupled
decisions, risk, and the owner's requested mode take precedence.

| Communication | Initial pilot range | When to expand or change form |
| --- | --- | --- |
| Ordinary multi-step plan | 60–120 words | Unsettled purpose, high-risk boundary, or several independent decisions |
| Meaningful progress update | 30–70 words | New blocker or premise requiring an explanation now |
| Small implementation result | 80–180 words | Material deviation, failed verification, or unfamiliar effect |
| Substantial final overview | 200–400 words | Use a linked full record for separate decisions and evidence, while keeping all material caveats visible |
| Research or architectural record | No hard total cap | Add a reading map, coherent sections, source boundaries, and an independent short overview |

Compare total reconstruction and verification effort, not words alone. Prefer a
little repeated goal context over forcing a reader to remember an old message;
remove repeated boilerplate that adds no new meaning. A requested one-item-at-a-time
walkthrough should keep a visible cursor and settled context, not require the owner
to reconstruct the whole discussion at each step.

### Constructed report example

This example is fictional and does not describe a current task or D2 row:

> The draft walkthrough now separates design acceptance from implementation evidence;
> it is ready for discussion, not implementation approval. The goal is to reduce
> repeated context reconstruction without weakening owner control. Of a fixed short
> template, a layered packet, and an interactive walkthrough, the draft favors the
> layered packet with an optional walkthrough: it preserves inspection detail, but
> creates a record-maintenance cost. The fixed cap risks hiding material caveats;
> a mandatory walkthrough risks unnecessary interruptions. No runtime behavior or
> acceptance status changed. The format has been checked for internal consistency,
> not tested for comprehension. The unresolved question is whether the owner can
> recover the decision and its largest risk after a pause. A pilot is proposed;
> no task has been filed and no benefit has yet been measured.

The example states its scope, alternatives, limitations, and follow-up status. It
does not imply that supplying those fields alone makes the underlying claim true.

## Akmon foundations and gaps

The repository already treats owner attention as scarce and contains substantial
pieces of this design. The gap is their integration across the whole interaction,
not an absence of planning, alternatives, or owner control. These are checkout
observations, not claims that every session followed the documents.

| Existing foundation | Source location | Implication for this design |
| --- | --- | --- |
| Quality relative to token and owner-attention costs | [README](../../README.md), lines 70–78; [MODEL](../../MODEL.md), lines 103–109 and 163–177 | Strengthen an existing product objective rather than introduce a competing one |
| Frame, survey alternatives, align, and record | [Design flow](../../pipelines/design-flow.md), lines 21–91 | Place elicitation and goal checking before premature solution convergence |
| Essence, current state, proposal, alternatives, recommendation; preserve owner rationale and revisit conditions | [Architect role](../../roles/architect.md), lines 91–131 and 149–157 | Reuse the narrative and decision-record structure; improve its application in live dialogue |
| Delegation of mechanical work | [Common guardrails](../../guardrails/_common.md), lines 105–114 | Keep extraction/checking below the owner-facing synthesis layer |
| Evidence-based findings, adversarial review, bounded reround, owner resolution | [Review flow](../../pipelines/review-flow.md), lines 20–60 | Integrate factual challenge without an unlimited review loop |
| Advisory second opinion at selected gates | [Model-routing design](model-routing.md), lines 365–385 | A second opinion can expose disagreement; it is not a neutral final arbiter |
| Pending, Approved, and Verified distinct from task lifecycle | [D2 design](d2-ledger.md), lines 20–40 and 67–81; [ledger](../D2_LEDGER.md), lines 3–7 | Preserve explicit acceptance and landing evidence in every compact report |
| Attention metrics deferred; current statistics cover other process data | [Tasks](../TASKS.md), C19; [model-routing design](model-routing.md), lines 329–347 and 666–677; [stats implementation](../../tools/model_routing/stats.py), lines 471–525 | Token/delegation counts do not establish comprehension, active attention, or decision quality |

The existing [D2 design](d2-ledger.md), lines 8–16, explicitly addresses owner
remarks disappearing in chat and rejects a new verifier agent as the solution to
that tracking problem. A walkthrough skill would address a different need:
comprehension and dialogue around the tracked decision. It should not reinvent the
ledger or introduce another top-level role.

The synthesis gap is an explicit policy connecting knowledge elicitation, ask-versus-
investigate routing, truthful proportional reporting, symmetric challenge, and
outcome-based evaluation. Existing conformance checks can establish whether a
change matches a named contract; the owner and agent must still examine whether
the contract addresses the right problem. No current capability parity, enforcement,
or effectiveness claim is inferred from these source documents.

## Historical session evidence

### Sample and interpretation

The bounded qualitative sample consists of two related Codex threads and five
Claude episodes relevant to akmon design, review, reporting, or delegation. Records
span August 21 through September 13, 2026. They were selected for relevance, not
randomly; the sample is neither a census nor an independent comparison of vendors.
Session inspection was delegated, using existing local logs without launching the
external applications. The observations below are English paraphrases of selected
direct messages and responses, not a verbatim transcript.

Serialized logs include tools, duplicate representations, compaction summaries,
and background events. Message counts, turn durations, and timestamp gaps cannot
be treated as active human attention or proof of cognitive overload. The evidence
supports concrete friction patterns and candidate remedies, not causal estimates
of time saved. Historical assistant claims are claims made in those sessions,
not independent verification of all the underlying code or current state.

| Episode and trace | Observation | Bounded interpretation |
| --- | --- | --- |
| D2-20, X1:657, 676, 748, 783, 840; August 23–24 | After a large verification enumeration, the owner asked the agent to prepare a brief and checks, summarize, and start with the first item; separate confirmations followed | Small sequential packets were explicitly wanted. They need stable context so subdivision does not create repeated reconstruction |
| Stage-1/A17, C1:506, 750, 753, 845; August 21 | The owner described the work as mechanical and requested joint item-by-item review. Later the assistant acknowledged introducing ten defects while writing the ADR | Do not transfer bulk mechanics to the owner; explicitly distinguish introduced defects from inherited issues |
| Parser review, C2:1958, 2155, 2292, 2295; August 28–31 | The owner requested further full reviews; an assistant report described another parser pass finding four defects before eventual closure instructions | Repetition can uncover real defects. Do not treat every reround as waste or substitute a delta-only review for a requested full review |
| Lifecycle checks, X2:318–319, 397–398, 1366–1367, 1497–1498, 1773–1774, 1798–1799; August 27–September 2 | Reports separated independently acceptable decisions, approval from landing, missing tracked material from local behavior, and completion claims from active follow-up defects | Status reconciliation is part of trustworthy synthesis, not clerical detail that brevity may remove |
| C66, X1:4793–4794, 4814–4815, 4831–4832, 4840–4841, 4847–4848; August 25 | After an option choice and a claim of completed evidence, the assistant challenged missing corpus/probe prerequisites; the owner restated choice separately from verification requirements | A useful instance of challenging an owner-supplied factual claim while preserving owner authority over the choice |
| Practical adoption and scope, X1:4867, 4870–4871, 5545, 5549–5550; August 25 | The owner supplied practical-use priorities and separated less relevant work; the assistant changed prioritization and grouping | Future-use priorities cannot be read from backlog status alone |
| Comprehension and rationale, X1:9087, 9090–9091, 10549, 12488, 12493; September 8–13 | The owner requested one-to-two-line explanations of what each item concerned, alternatives with recommendations where uncertain, and reconstruction from original problem through implementation/tasks | Concise orientation and a coherent causal account are complementary requirements |
| C37/N7, C3:530, 788; August 25 | An initial green-check report was followed by an assistant report reproducing and fixing ten owner-review findings, while identifying pre-existing test failures separately | Green checks are bounded evidence, not semantic completeness or approval |
| Delegated backfill, C4:1760, 2033; September 13 | The assistant reported delegated extraction followed by checking, finding four errors and then a fifth through another check | Delegation still needs synthesis and verification; the number of dispatched agents is not an accuracy measure |
| Statusline, C5:26–27, 47, 51–66; September 12 | A subagent execution limitation was disclosed; the parent performed checks and did not invent access to unavailable prompt text | Explicit limits plus in-scope recovery can be more helpful than either silence or dumping the failure on the owner |

### Candidate lessons, not causal conclusions

The sample suggests that the owner often needed meaning, acceptance boundaries,
and checked evidence rather than more raw status entries. It also contains positive
examples of candid correction, delegation with checking, and useful disagreement.
The design should preserve those strengths.

An attractive but unsafe shortcut would be "only review the delta from now on."
A better hypothesis is to preserve coverage already established, identify what
changed or became stale, and match the new review to risk and the requested scope.
New parser classes, changed contracts, incomplete earlier evidence, or an explicit
full-review request can justify broad review. Repeated questions caused by lost
context and repeated investigation caused by new defects are different phenomena.

## D2 walkthrough as a candidate skill

### Purpose and boundaries

A D2 walkthrough is a promising first application because the sessions expose
repeated reconstruction and lifecycle confusion. It is not a substitute for
whole-lifecycle collaboration and should not be created merely because a skill is
an available extension mechanism.

Candidate purpose: assemble a current, evidence-linked decision packet, help the
owner understand and challenge it, preserve discussion position and rationale,
and hand the exact next authorized action to the existing process. Use the
existing architect/review roles. Default preparation is read-only; no autonomous
approval, ledger transition, implementation, landing, or task creation is implied.

### Proposed behavior

1. Read the current task, ADR/design, relevant ledger clauses, unstaged and staged
   subjects, and verification evidence. Identify the exact decision and its
   dependencies; do not reuse historical session status as current truth.
2. Prepare an orientation: original problem and future-use consequence; what is
   accepted now; what is outside this acceptance; what is already established;
   what still needs owner knowledge, a value choice, or technical evidence.
3. Delegate independent mechanical checks and consolidate their disagreements.
   Present the decisive evidence and unknowns, not all raw outputs.
4. Walk one meaningful decision at a time when useful or requested. Keep a visible
   cursor and short settled-context recap. Related items may share background,
   but independently acceptable choices must remain distinguishable.
5. Reuse the strongest alternative and arbitration pattern above. Ask about lived
   consequences when the problem is uncertain, not just whether to approve A or B.
6. Record the owner's rationale and exact scope of acceptance when recording is
   authorized. Silence, discussion, or acceptance of a recommendation is not
   automatically approval of implementation correctness or a wider clause set.
7. Hand off only the action permitted by existing rules and explicit owner wording.
   Approved and Verified remain distinct; existing D2 verification requires the
   landing commit. Preserve unresolved findings and a clear next step.

A packet needs stable references to the evidence subject so that a changed diff
or clause does not inherit stale approval. How to represent that subject and
invalidate only affected evidence is an open design question, not a new hashing,
automation, or storage requirement. Checkpoint persistence should reuse an
appropriate existing record; do not create a parallel acceptance database.

### Placement alternatives

The dispositions below are research recommendations only; no option has owner
acceptance and no formal ADR rejection is recorded by this note.

| Candidate | Advantage | Cost or failure mode | Current research leaning |
| --- | --- | --- | --- |
| Fixed universal report template and length cap | Easy to remember and lint | Can hide exceptions, induce boilerplate, and ignore discovery | Not suitable as the whole solution; test small editorial defaults only |
| One comprehensive collaboration skill for every task | Centralized guidance | Always-on overhead; risks duplicating roles and pipelines | Keep open, but avoid making every interaction a ceremony |
| Small shared principles plus pipeline guidance and an on-demand D2 walkthrough | Reuses current architecture; places extra effort at difficult decisions | Boundaries and invocation need careful design | Best current pilot candidate, not a settled architecture |
| Dedicated arbitrator/verifier agent | Additional review perspective | Correlated errors, unclear authority, new role and coordination cost | Do not make it an acceptance authority; use bounded advisory checks where justified |
| Tool-generated packet and status display | Reduces assembly and stale-status errors | Can certify syntax while missing a wrong goal or misleading claim | Consider after the useful packet and evidence boundaries are demonstrated |
| No new mechanism; tighten use of existing architect/review guidance | Minimal maintenance and conceptual cost | Existing pieces may still fail to guide live dialogue | Include as the pilot baseline, not a straw-man alternative |

## Product-goal and scope discipline

A feature can be implemented correctly and still make the product worse. Before
adopting a report rule, extra agent, skill, or runtime feature, connect it to an
intended outcome and a concrete current or future-use scenario. Include the cost
of future interpretation, review, maintenance, dependency, and repeated approvals.

Candidate goal-fit questions are: what outcome improves, for whom and in which
scenario; what observation would show the change did not help; what simpler
alternative exists; and what is explicitly outside this decision? These questions
are not a mandatory questionnaire. Use them to expose a material gap rather than
ask the owner to restate already known goals.

Keep no change, deletion, consolidation, reuse, and a reversible experiment in the
solution space. Future use matters, but a speculative possibility is not by itself
a requirement to build now. Equally, a local optimization that saves chat words
but loses the owner's important constraint is not a product improvement.

For this topic specifically, the intended outcome is better joint decisions with
less avoidable owner effort. "More skills," "more reports," "more approvals per
hour," and "fewer questions" are not substitutes for that outcome.

## Pilot and open decisions

### A proportionate evaluation

No pilot, comprehension test, new harness measurement, or implementation is claimed
here. A next design pass could compare the current practice with a layered packet
and with a packet plus bounded goal/alternative challenge. Include at least one
discovery case, one implementation handoff, and one D2 acceptance case so the design
does not collapse back into a ledger-only workflow.

Use comparable cases or counterbalance order where feasible; re-reading the same
case creates learning effects. Seed realistic ambiguities and limitations in
fictional evaluation material, never hide known defects in real work to test the
owner. A small local pilot can reveal usability failures but cannot establish
population-wide effect sizes.

| Dimension | Candidate observation | Misleading proxy to avoid |
| --- | --- | --- |
| Understanding | Can the owner recover the task, decisive trade-off, largest limitation, and next action after a pause? | Reading completion or a bare "approved" |
| Decision quality | Important defects found, unsupported assumptions corrected, unnecessary work avoided, later rework | Number of features, arguments, or approvals |
| Knowledge transfer | A consequential owner insight appears accurately in the constraint, rationale, and acceptance example | Number of questions asked |
| Attention cost | Consented active review time, repeated context questions, avoidable interruptions, short optional effort feedback | Session duration, serialized messages, tokens alone |
| Truth and calibration | Material claims trace to evidence; limitations and autonomous choices are visible; false closure is caught | Headings present or tests green |
| Agency and emotional cost | The owner can correct the frame, express disagreement, and choose a known trade-off without repeated pressure | Satisfaction alone or absence of disagreement |
| Resumption | Correct recovery of state and rationale without replaying the conversation | Existence of a checkpoint file |

NASA-TLX provides an established multidimensional workload instrument.[^31] A
single informal effort question may be lighter for a pilot, but must not be labelled
a validated TLX score. Broader developer-productivity work similarly warns against
replacing a multidimensional outcome with a single activity metric.[^32]

Guardrails should include no known undisclosed material risk, no unsupported
completion or acceptance claim, and no unauthorized action. Automated checks can
test links, status combinations, and missing fields; they cannot establish truth,
goal fit, or human understanding. Keep observed quality, effort, and token cost
separate before considering any combined score with explicit value weights.

### Decision register for the next pass

| Open point | Current leaning | Evidence or owner knowledge still needed |
| --- | --- | --- |
| What owner effort should be reduced first? | Reconstructing context and reconciling evidence/status before meaningful judgment | A concrete recent episode and the owner's account of what felt routine versus useful |
| Shared guidance versus a skill | Minimal shared principles plus an on-demand walkthrough; baseline existing guidance remains viable | Pilot evidence that a distinct invocation adds value |
| Report size and structure | Layered, complexity-sensitive; no hard truncation | Actual comprehension and review effort across task types and language |
| When to challenge | Consequential uncertainty, changed premise, unsupported confidence, or goal/scope risk | Whether a bounded challenge improves decisions without becoming repetitive |
| How to preserve state without duplicate truth | Stable links, settled rationale, open issue and cursor in existing appropriate records | Which existing artifact can carry that state without growing the ledger into a transcript |
| How to prevent stale evidence reuse | Explicit subject and affected coverage | A design for changes to coupled clauses, staged/unstaged subjects, and review scope |
| How much workload measurement is tolerable? | Lightweight, consented observations; no passive inference about emotions | Owner preference and the cost of the measurement itself |

These are not questions that must all be answered before this research note is
useful. On return, first recover one concrete interaction and the desired outcome;
then select the smallest pilot. Revise or discard the proposed mechanism if it
adds ceremony without improving understanding, decisions, or resumption.

### Explicit non-decisions and limitations

No report schema, numerical budget, automatic challenge policy, skill placement,
new role, metric, or tooling change is accepted here. The owner's later request
created A22/C86 for refinement and gated implementation, plus D2-44 for the narrow
mission-framing verification point. Recording those items does not accept the
proposed operational policies; they still require the existing design process.

The research combines older cognitive experiments, text-comprehension studies,
human–AI decision-support experiments, practitioner methods, and recent preprints.
Their populations and activities differ from long-running akmon development;
transfer claims are explicitly hypotheses. The session sample is small, purposive,
and retrospective. Report-length ranges and the proposed challenge/routing policy
are design judgments, not empirically validated treatment effects.

The important unresolved question is not "how short can an agent answer?" It is
"what must the owner understand, contribute, or decide now, and what work should
the agent complete before asking for that attention?"

## Refinement and implementation plan

### Outcome and the two meanings of adaptation

This is a proposed work sequence, not authorization to implement it. AP0–AP5 are
local planning labels, not TASKS or D2 identifiers. Existing accepted decisions stay
accepted; this plan neither approves new contracts nor reruns their acceptance.

Two different failures must be prevented. An agent can ignore the person's needs
by repeating explanations, demanding context again, or handing over raw evidence.
It can also accommodate the person's apparent preferred answer by changing its
factual assessment without grounds. Better collaboration requires adaptation of
presentation and workflow together with independence of evidence assessment.

The distinction is not "always stand by the first answer." New owner experience,
constraints, goals, or priorities may legitimately change a recommendation, even
when technical facts are unchanged. New counterevidence must also be allowed to
overturn the agent's own confident answer. The invariant is a traceable reason for
the change, not a permanently fixed recommendation.[^21][^22]

### Further cognitive improvements to investigate

Research on the expertise reversal effect found that instructional support helpful
to inexperienced learners can become redundant or counterproductive with greater
experience.[^34] Candidate application: adapt explanation to the particular topic
and current need, gradually removing familiar scaffolding while keeping important
limitations visible. Do not infer a permanent novice/expert identity from one turn.
Transfer from learning experiments to agent collaboration needs evaluation.

Adaptation itself can impose a cost. In a 27-participant menu study, the static
condition was faster than the system-adaptive condition; user-adaptable performance
depended on order, and it was the most commonly preferred condition.[^35] This is
not a chatbot result. It motivates testing predictable structure and easy owner
override, rather than silently rearranging an interface or explanation on every turn.

Bainbridge's analysis warns that automation can leave people responsible for
abnormal conditions while creating additional operator problems.[^36] For akmon,
the proposed safeguard is a context-rich exception handoff: if the agent needs
human judgment, it must restore the goal, changed condition, attempted checks, and
real decision. Saving routine work should not leave the owner unable to understand
the moment at which their judgment is needed.

| Opportunity | Candidate behavior | Limit / failure to test |
| --- | --- | --- |
| Topic-specific scaffolding | Start from a known use scenario; explain the unfamiliar relationship; shorten familiar mechanics on subsequent turns | A request for explanation must not be treated as a global lack of expertise |
| Recognition instead of recall | Stable names, a current decision cursor, and references beside the claims they qualify | A shorter output must not require remembering unexplained IDs from earlier turns |
| Controlled novelty | Introduce the next consequential concept at a time in a joint walkthrough; keep the overall map visible | Do not serialize independent routine approvals or hide coupled consequences |
| Predictable adaptation | Keep stable section meanings; honor explicit requests such as an example, concise result, joint exploration, or evidence detail | Changing format must not silently change criteria, authority, or factual confidence |
| Prospective memory support | Agent tracks the pending next action and its trigger in an appropriate existing record | No extra owner reminder burden or parallel lifecycle database |
| Context-rich exception handoff | Before asking, investigate what is accessible and explain the remaining owner-only distinction | Do not deliver only the hardest unexplained residual after automating everything else |
| Correction without social penalty | Accept a corrected frame or new constraint; state how it changes the reasoning; preserve legitimate dissent | Neither defensiveness nor automatic agreement counts as checking |
| Less unnecessary switching | Batch background checks, distinguish informational updates from action requests, and pause only the affected work | Critical warnings and real authorization boundaries cannot wait for a convenient batch |

Prefer task-local interaction context over a new user-profile subsystem. Known
purpose, familiar terms, requested depth, and unresolved questions can be used in
the current conversation without a personality inference. Any future persistent
preferences need explicit scope and an inspectable, correctable owner; they must
not silently become cross-project requirements, psychological labels, or permission
to write elsewhere. No persistent profile is created by this plan.

### What to adapt, continue, check, or reopen

| Situation | Appropriate next action | Unnecessary or unsafe action |
| --- | --- | --- |
| The owner requests a different explanation | Change representation, example, detail, or pace | Treat the request as rejection of the underlying choice |
| A known accepted trade-off still applies | Restore its rationale briefly and implement/check conformance | Ask for the same approval because a new agent or session started |
| The owner expresses confidence in a factual conclusion without new grounds | Check the decisive evidence; clarify whether an unstated criterion or experience is missing | Rewrite the evidence to agree, or dismiss the statement without examining it |
| The owner supplies a new real constraint or changes a value priority | Identify the affected comparison and revise the recommendation if warranted | Insist on the old recommendation in the name of anti-sycophancy |
| New evidence contradicts a premise, including the agent's own premise | Recheck the affected claim and connected consequences; expose any changed acceptance scope | Reopen every unrelated decision or suppress the counterexample |
| Only a version, context window, or session identity changed | Assess whether the evidence subject or relevant behavior changed | Automatically invalidate all established knowledge or assume it all remains valid |
| Implementation differs from the accepted contract | Report the discrepancy and follow the existing repair/design boundary | Pretend that design approval established implementation correctness |

Mandatory tests, safety checks, freshness requirements, and an explicitly requested
full review remain in force. Avoiding repeated approval does not exempt a changed
implementation from verification. A revisit request should identify the changed
premise, evidence, affected decision, and actual owner action needed; if no premise
changed, determine whether this is merely a context-restoration problem.

### Proposed sequence and exit conditions

| Phase | Work and concrete output | Exit condition and owner involvement |
| --- | --- | --- |
| AP0 — Ground the target | Orchestrator selects a small set of existing discovery, implementation, and acceptance/resumption episodes. A delegate extracts the minimal evidence. Produce case cards: intended outcome, owner contribution, avoidable work, observed failure, desired behavior | Each case has an identifiable loss or missed insight, not just a long message. Ask the owner only for a consequential missing experience or priority; do not repeat the earlier requirements interview |
| AP1 — Specify the smallest behavior change | Draft a compact situation/action table, truth-preservation checklist, and accepted-choice versus premise-recheck boundary. Link state to existing rationale, evidence, and task owners | Every proposed behavior has a positive example and a counterexample. No new approval authority, mandatory questionnaire, global profile, or duplicated ledger; open architecture points remain marked |
| AP2 — Evaluate examples before machinery | Compare current guidance with the minimal candidate on the paired cases below. Use fictional or minimized authorized material. Record outputs, evidence subjects, material omissions, unnecessary questions, and reasons recommendations change | Evaluation distinguishes responsiveness from agreement-seeking and rigidity. It can reveal failure of either condition. No known false closure, hidden material risk, or unauthorized action is accepted; results remain scoped to tested cases |
| AP3 — Refine with a small owner-facing pilot and lock the first slice | After agreement to the trial, use bounded discovery, implementation handoff, and acceptance/resumption cases. Capture a short owner correction and observed reconstruction effort. Compare existing-guidance-only, minimal guidance, and optional walkthrough where appropriate | A concrete benefit is visible without loss of understanding/control. Remove ineffective ceremony. Owner accepts only the useful first contract slice through existing design/ADR/D2 gates, not this entire research catalogue |
| AP4 — Implement and verify that slice | Record authorized implementation tasks first. Update the owning guidance and worked examples; add a skill only if AP3 establishes a distinct trigger and result. Add deterministic tooling only for demonstrated repetitive mechanics, with tests | Changed behavior is evidenced on the cases, not merely by mandatory words appearing. Source-of-truth, delivery, negative contracts, tests, and limitations are checked. Approval, implementation, landing, and D2 Verified stay separate |
| AP5 — Controlled adoption and simplification | Apply to a small set of normal tasks; compare useful owner insights, repeated-context questions, omitted caveats, unnecessary reopening, and later rework. Keep a clear disable/revert path for optional behavior | Decide to retain, adjust, shrink, or remove the mechanism. Broader propagation requires evidence appropriate to its claim; no population-wide productivity claim from a small local pilot |

AP0 is the proposed next action, not completed case preparation. The research and
sample already exist; use them to reduce that work. AP2 should start with inspectable
example evaluation; any model-running experiment has its own explicit execution
scope and budget. This plan launches neither Codex nor Claude and authorizes no new
operative interaction rules. A conversational pilot does not require a new runtime
framework; it also does not authorize tool use outside the underlying task.

### Paired cases and negative controls

These are initial evaluation specifications, not results or a statistically
representative sample. Preserve identical technical facts and goals where only
presentation or social pressure is being varied.

| Pair | Expected distinction | Failure the case should expose |
| --- | --- | --- |
| Unknown use scenario / already recorded scenario | Ask a focused open question / reuse the known answer | Premature options or repeated intake questions |
| Unfamiliar concept / request for result only | Add a concrete example / compress familiar mechanics; preserve the same material caveat | Repetition without explanation or misleading brevity |
| Inspectable fact / owner-only experience | Investigate / elicit the real process or consequence | Offloading routine research or inventing preferences |
| Unsupported confidence in B / new offline requirement favoring B | Retain an evidence-based assessment while checking for missing criteria / revise the affected comparison | Sycophantic agreement or rigid refusal to learn |
| Repeated accepted priority / genuinely changed priority | Continue within the known trade-off / reconsider the dependent choice | Reapproval loops or treating values as immutable technical facts |
| Fresh session, same subject / materially changed dependency | Resume known rationale / recheck affected evidence and consequences | Repeated whole-design review or stale-evidence reuse |
| Counterexample to the agent / another agent's bare endorsement | Test and correct the original claim / seek evidence rather than count votes | Self-protective reasoning or consensus mistaken for truth |
| Concise completion / return after a pause, with one unresolved limitation | Preserve truthful status, limitation, and next action in both forms | False completion or loss of an unresolved obligation |

For the social-pressure cases, compare evidence assessment, not literal wording or
an always-identical recommendation. A new owner value can legitimately change the
choice. Independent checking may withhold the favored option when it is irrelevant
to testing a fact, but must preserve all relevant constraints and experience.

Agree the case rubric before comparing outputs; include hold-out variations rather
than tuning exclusively to the visible examples. Where practical, evaluators should
not know which guidance variant produced an answer. Repeated model runs, if later
authorized, should preserve model/version/configuration and variation in results.
Human assessment resolves disputed semantics; automated matching of "alternative"
or "risk" is not evidence of independent judgment. Do not teach the owner the same
case repeatedly and then count familiarity as improved format effectiveness.

### Implementation surfaces and dependencies

The following map identifies integration points, not edits authorized now. Prefer
links to owning artifacts over another universal collaboration document loaded in
every task.

- Shared principles and ownership: [MODEL](../../MODEL.md) and
  [common guardrails](../../guardrails/_common.md). Add only invariant material that
  is actually missing; final synthesis and owner dialogue remain orchestrator-owned.
- Dialogue and reporting: [architect role](../../roles/architect.md),
  [design flow](../../pipelines/design-flow.md),
  [review flow](../../pipelines/review-flow.md), and
  [code flow](../../pipelines/code-flow.md). Reuse Frame, rationale/revisit-if,
  bounded review, and the design-to-implementation handoff.
- Acceptance walkthrough: existing [D2 attachments and lifecycle](d2-ledger.md).
  A skill is a candidate presentation/assembly layer, not an alternative owner of
  acceptance state. C79 becomes relevant to delivery only if a skill is chosen.
- Context and reuse: A21 owns task/session transitions; C80/C81 concern machine
  context pressure, not human cognitive load; C82 concerns measured harness facts.
  Reuse their boundaries. A version change is a relevance-check candidate, not a
  reason to repeat every historical experiment.
- Metrics and automation: coordinate any later attention-metric change with C19,
  packet assembly with C24, and a reusable behavioral-evaluation framework with
  A14/C42. Do not silently revive A18's deferred automatic plan-draft trigger.
  These are integration seams, not blanket prerequisites for trying a small
  example-based interaction improvement. Current task ownership lives in
  [TASKS](../TASKS.md), not in this list.

For executable changes, verification includes focused regressions and the existing
`uv run pytest`, `uv run ruff check .`, `python3 meta/self_ci.py`, and `uv build`
checks. The installed-wheel leg's network/authentication prerequisite must be
separated from product failures. A claimed harness delivery/enforcement property
also needs an authorized live probe on the exact version and route; document its
measurement rather than infer cross-vendor parity. Documentary guidance and
behavioral efficacy require their own evidence, not only green code checks.

### First increment and deferred ambitions

Recommended first increment: paired cases, a small clarification of existing
interaction/reporting guidance, and a resumable decision packet demonstrated in
both a non-D2 task and a D2 walkthrough. Keep skill creation optional until a
distinct reusable need appears. A pure existing-guidance baseline remains a real
alternative: if applying it consistently solves the cases, adopt less new machinery.

Defer a psychological user model, passive emotion inference, adaptive notification
engine, approval auto-detection, new arbitrator role, decision-validity database,
and universal "attention score." These add assumptions, maintenance, or authority
risks before the useful behavior has been demonstrated. Revisit a deferred mechanism
only when a repeated observed failure cannot be addressed adequately with the
smaller approach. A failure of the pilot is a reason to reduce or revise the design,
not automatically to add another layer.

## Mission premises and decision trace

### Owner direction, evidence, and open hypotheses

The owner characterized this work as a potentially important distinction of akmon
and asked to make it central in the product description. The owner also identified
token efficiency for quality as the complementary priority, realized mainly through
subagents, model selection, roles, and possible skills/hooks. These are attributed
product intentions, not findings that akmon already outperforms competing products.

The canonical mission wording is in [MODEL](../../MODEL.md#mission-and-priorities).
README is its short reader-facing summary; CONCEPT explains the rationale; ROADMAP
sets development priority. This section owns the rationale of this research path,
not another copy of the operative mission or a new decision database.

| Premise | Provenance and epistemic status | What needs checking or could change the implementation |
| --- | --- | --- |
| Human attention and domain knowledge deserve deliberate investment | Explicit owner direction, compatible with MODEL's two-budget goal; historical episodes show requests for context, meaningful briefs, and agent-handled mechanics | Which effort is avoidable and which thinking is valuable; approval speed is not a substitute |
| Token efficiency must serve quality, not just cheap calls | Explicit owner direction and existing MODEL §10 leverage/task-kind routing | Total work and rework, achieved correctness, selected versus delivered model behavior |
| Efficiency is lifecycle resource allocation, not local saving | Owner clarification during D2-44 discussion: invest more in design or capable high-effort analysis/synthesis when downstream benefit warrants it | Relevant horizon, expected benefit and uncertainty, total costs and achieved outcome; neither cheap calls nor maximum effort prove efficiency |
| Adapt presentation, not facts to social pressure | Owner's symmetric-challenge requirement; sycophancy and verification-cost research [^21][^25][^26] | Cases must also reward legitimate revision after new constraints; anti-sycophancy must not become rigidity |
| Cognitive findings can inform akmon interactions | Published evidence above, with different populations and activities | The local pilot may show no benefit or harm; report budgets and transfer effects remain hypotheses |
| A minimal extension of existing guidance may be enough | Agent recommendation based on existing Frame, rationale, review, D2, and checkpoint mechanisms | If current guidance solves the cases, adopt less; a distinct repeated failure could justify a skill/tool |
| The combined approach may differentiate the product | Owner's positioning hypothesis | Comparative outcome evidence is absent here; do not promote intent into a superiority claim |

### Actual choices made in this planning path

The initial problem was report size and prolonged D2 review. The owner broadened
it to the full collaboration: extracting lived knowledge, designing for future use,
preserving goals, and challenging both parties. The session evidence showed both
avoidable reconstruction and valuable repeated review that found new defects.
Consequently, the plan targets context loss and unsupported agreement without
assuming every additional review round is waste.

Alternatives remain in [placement alternatives](#placement-alternatives). A fixed
report cap is insufficient for truthfulness; a D2-only skill is too narrow; a
universal profile/arbitration system creates premature infrastructure and authority
risks. The current recommendation is minimal shared guidance plus inspectable
examples, with an on-demand walkthrough only if its separate value is demonstrated.
Existing-guidance-only remains a real baseline. These are agent recommendations,
not owner-accepted operational choices.

For the documentation update, "mission" was selected because the owner proposed
it for a stable product purpose. "Product priorities" names the two investment
directions; roles, routing, skills, and hooks remain mechanisms. A report-format
label alone would lose the purpose; a proven-superiority claim would exceed the
evidence. D2-44 isolates inspection of this framing and its limits, not approval
of every mechanism suggested in the research.

One correction to MODEL is deliberate: its earlier "finite, measured" wording
could imply that attention was measured like token usage, while C19 still describes
deferred/proxy metrics. The revised statement distinguishes measurement, proxies,
and unknown effort. No exchange rate, composite score, new threshold, or rerouting
rule is introduced.

During the D2-44 walkthrough the owner sharpened the distinction between saving and
efficiency: the mission needs an economic model of resource allocation. More design
time or stronger, higher-effort inference can be worthwhile when it avoids greater
implementation and rework costs or improves the intended result. This clarifies why
the two budgets are investments, not targets for uniform reduction. The mission names
the purpose; the economic model explains how resource choices should be assessed.

This fits MODEL's existing downstream-leverage principle. Its description of key
points as "low-token" was removed because a valuable up-front analysis may itself
be costly. README now includes analysis and design, not only checks, as high-leverage
work. No current tier, task-kind routing, session-model ownership, or effort setting
was changed. Local saving is insufficient; universal maximum spending is also not
the chosen criterion. The return of a particular investment remains a hypothesis
until assessed, not a measured conclusion supplied by this clarification.

### Token-quality work and its evidence boundary

Use the existing [model-routing design](model-routing.md) and operative MODEL §10;
this initiative does not replace their accepted decisions. These are evaluation
questions, not new routing rules:

| Mechanism | Contribution to investigate | Evidence needed before claiming improvement |
| --- | --- | --- |
| Roles | Match analysis, design, and implementation to distinct responsibilities | Fewer missed boundaries and wrong-problem solutions, not more role switches |
| Bounded subagents | Remove routine work from the orchestrator and owner | Accepted outputs, integration/retry cost, sufficient context, preserved boundaries |
| Model selection | Invest capability and reasoning effort at high downstream error cost | Task outcome, total effort, and actual route/version/effort evidence where observable; requested settings alone are insufficient |
| Skills | Reuse proven procedures and focused context | Correct selection, useful execution, maintenance cost, counterexample behavior |
| Hooks and validators | Enforce observable invariants and reveal drift | Exact delivered payload/route, negative tests, false alarms, unsupported boundaries |
| Evidence/context reuse | Avoid repeating established work while detecting relevant change | Correct reuse on an unchanged subject and recheck when a premise changes |

Include retries, duplicated context, unsuccessful delegations, and orchestration
overhead in token comparisons. More parallelism can increase total work while
reducing latency. Do not shrink evidence until the owner must reconstruct it, or
classify a valuable independent check as waste solely because it consumes tokens.
Assess quality and human effort separately from computational cost.

For the A22 evaluation, compare a local-saving case that causes downstream rework
with a justified up-front investment, and include a counterexample where further
analysis or maximum effort adds no useful decision information. State the intended
outcome, relevant lifecycle horizon, expected avoided work or quality gain, extra
human/model effort and latency, and uncertainty. Define what useful result would
end the extra investigation or what observation would make it worth stopping.
Do not compare unlike outcomes as if lower cost alone established efficiency, add
minutes and tokens without an explicit valuation, or turn speculative avoided work
into a claimed measured return. This adds an evaluation question, not a new routing gate.

### Traceable records for human and model review

| Reviewer question | Existing owning artifact or evidence |
| --- | --- |
| What problem, owner knowledge, and premise motivated this? | Task brief, attributed premise table, research sources, bounded session evidence |
| Which alternatives and criteria led to the recommendation? | This concept's alternative/open-point registers and cases; later the accepted ADR |
| What exactly was accepted and what is still proposed? | Owning decision record and exact D2 scope, not a summary's implied consensus |
| What implementation was authorized and what actually changed? | TASKS design link, accepted slice, actual diff/commit, reported deviations |
| Does the result conform, and does the premise still hold? | Tests/probes for conformance, separately from behavioral/owner evidence of usefulness |
| What would require reconsideration? | Premise and scope/version where relevant, counterevidence or changed goal, affected decisions and revisit condition |

This is an inspectable justification and evidence path, not a transcript of private
reasoning. A reviewer may challenge an upstream premise even if code matches its
specification; a correct premise likewise does not prove a correct implementation.
Human and model reviews should use the same evidence subjects and disclose unknowns.
A second model's endorsement does not close either question.

## Tracked work and acceptance boundaries

Execution state lives in [TASKS](../TASKS.md), not the AP labels or a copied status
table here. The owner requested both the plan and its implementation task.

- **A22 — design refinement.** AP0–AP3: ground the cases, specify the smallest behavior
  change, evaluate alternatives, and prepare independently acceptable slices. Done
  requires explicit owner acceptance of the slice's premises, criteria, and behavior,
  its decision record/ADR, and linked acceptance examples. D2-44 verifies the mission
  wording separately; it does not accept a report protocol or skill.
- **C86 — implementation.** AP4–AP5, blocked on A22 locking an implementable slice and
  owner authorization to realize it. Start with owning guidance and examples;
  skills/tools are conditional. Done requires conformance evidence, behavioral
  evidence and limitations against accepted premises, accurate follow-up disposition,
  and the existing owner verification/landing process. A failed premise returns the
  affected choice to A22, not to silent feature growth or rewritten success criteria.
- **D2-44 — mission wording and top-document alignment.** The owner accepted the
  framing, including the economic clarification: lifecycle resource effectiveness,
  not local saving, with justified up-front investment in design and model reasoning.
  Acceptance does not extend to the proposed interaction protocol or routing/effort
  changes. Operational forks receive their own points when specified; they must not
  borrow this approval. The ledger owns approval/landing state; no other D2 point or
  task status is changed by this acceptance.

The immediate authorized change is mission/priority documentation and the requested
backlog/verification records. No runtime implementation, new skill/hook, consumer
change, automatic acceptance, or vendor experiment is claimed by this update.

### Review of this documentation increment

Bounded subagent reviews checked mission/protocol separation, task and D2 scope,
the recorded decision path, and document consistency. They identified stale role
descriptions in CONCEPT/ROADMAP and a task goal phrased as steps rather than an
outcome; these were corrected. The roadmap's package-carrier description was also
aligned with the current README, and planned evaluation was distinguished from
completed evaluation. New local links/anchors and all 36 bibliography definitions
were checked, together with diff whitespace. These are documentation checks, not
owner acceptance, a cross-vendor second opinion, executable regression results,
or evidence that the proposed interaction behavior improves outcomes.

## Sources

### Published research and practitioner sources

The numbered notes form the bibliography. Sources were consulted on September 13,
2026. Original papers, author copies, institutional records, and official guidance
are preferred. An institutional abstract supports only its stated findings; it is
not treated as inspection of an inaccessible full paper. Preprints and practitioner
methods are identified separately from established experimental results.

[^1]: George A. Miller. [The Magical Number Seven, Plus or Minus Two: Some Limits on Our Capacity for Processing Information](https://cse.buffalo.edu/~rapaport/575/F01/miller56.html). *Psychological Review* 63, 1956, pp. 81–97. Original article reproduced with permission; see immediate memory and recoding sections. Used for distinctions between capacity tasks and meaningful chunks, not a UI limit.

[^2]: Nelson Cowan. [The Magical Number 4 in Short-Term Memory: A Reconsideration of Mental Storage Capacity](https://memory.psych.missouri.edu/assets/doc/articles/2001/cowan-bbs-2001.pdf). *Behavioral and Brain Sciences* 24, 2001, pp. 87–114; [indexed abstract](https://pubmed.ncbi.nlm.nih.gov/11515286/). Review and theoretical synthesis; estimates depend on isolating capacity from supporting processes.

[^3]: Rebecca P. Sanchez, Elizabeth P. Lorch, and Robert F. Lorch Jr. [Effects of Headings on Text Processing Strategies](https://psychology.as.uky.edu/bibcite/reference/224). *Contemporary Educational Psychology* 26, 2001, pp. 418–428. Institutional abstract of an experiment with a 12-topic expository text; supports topic-organization recall, not an akmon report-size threshold.

[^4]: Robert F. Lorch Jr. and colleagues. [Effects of Headings on Text Summarization](https://psychology.as.uky.edu/bibcite/reference/227). *Contemporary Educational Psychology* 26, 2001; DOI 10.1006/ceps.1999.1037. Institutional abstract describes selective signalling effects across three experiments. Basis for the presentation-salience concern; transfer to agent reports is an inference.

[^5]: Evan F. Risko and Sam J. Gilbert. [Cognitive Offloading](https://discovery.ucl.ac.uk/id/eprint/1508770/). *Trends in Cognitive Sciences* 20, 2016, pp. 676–688. Review; institutional record/abstract. Supports external support for processing, not elimination of the need to understand a decision.

[^6]: Chris Parnin and Spencer Rugaber. [Resumption Strategies for Interrupted Programming Tasks](https://chrisparnin.me/pdf/parnin-icpc09.pdf). *ICPC*, 2009, pp. 80–89. Original conference paper. The sample figures cited above are from this version, not the expanded 2011 journal paper.

[^7]: Sophie Leroy and Theresa M. Glomb. [Tasks Interrupted](https://pubsonline.informs.org/doi/abs/10.1287/orsc.2017.1184) (title abbreviated). *Organization Science* 29, 2018, pp. 380–397. Publisher abstract; four studies of anticipated resumption pressure, attention residue, and a ready-to-resume intervention. Not a fixed time-saved estimate for programmers.

[^8]: Gloria Mark, Daniela Gudith, and Ulrich Klocke. [The Cost of Interrupted Work: More Speed and Stress](https://www.ics.uci.edu/~gmark/chi08-mark.pdf). *CHI*, 2008, pp. 107–110. Original paper; controlled email-task experiment with 48 participants. Speed, quality, and subjective costs must be interpreted separately.

[^9]: Shamsi T. Iqbal and Brian P. Bailey. [Oasis: A Framework for Linking Notification Delivery to the Perceptual Structure of Goal-Directed Tasks](https://www.microsoft.com/en-us/research/publication/oasis-a-framework-for-linking-notification-delivery-to-the-perceptual-structure-of-goal-directed-tasks/). *ACM Transactions on Computer-Human Interaction*, 2010. Author-affiliated record; task-structure-aware notification delivery, not a universal message heartbeat.

[^10]: Marc Brysbaert. [How Many Words Do We Read per Minute? A Review and Meta-analysis of Reading Rate](https://biblio.ugent.be/publication/8647789). *Journal of Memory and Language* 109, 2019, article 104047. Institutional record and abstract. English reading-rate estimates do not measure technical verification speed or Russian-language comprehension.

[^11]: Chang Xiao and Brenda Yang. [Streaming, Fast and Slow: Cognitive Load-Aware Streaming for Efficient LLM Serving](https://arxiv.org/html/2504.17999v1). arXiv preprint, April 25, 2025, version 1. Full text, especially sections 3, 3.2, 5, and 6. Resource-serving objective, comfortable-rate proxy, sampling exclusions, and code-generation exclusion limit transfer.

[^12]: Herbert H. Clark and Susan E. Brennan. [Grounding in Communication](https://web.stanford.edu/~clark/1990s/Clark,%20H.H.%20_%20Brennan,%20S.E.%20_Grounding%20in%20communication_%201991.pdf). In *Perspectives on Socially Shared Cognition*, 1991. Original chapter; common ground and collective effort. Formal project authorization is a separate construct.

[^13]: Eric Horvitz. [Principles of Mixed-Initiative User Interfaces](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/11/chi99horvitz.pdf). *CHI*, 1999, pp. 159–166. Original paper; decision-theoretic framework for combining initiative, uncertain goals, and interaction costs. The proposed routing table is an application, not a validated optimum.

[^14]: GOV.UK Service Manual. [Using In-depth Interviews](https://www.gov.uk/service-manual/user-research/using-in-depth-interviews). Published 2017. Official practitioner guidance on open neutral questions, real examples, and follow-up; not an experimental claim that every development task needs an interview.

[^15]: Benjamin Scheibehenne, Rainer Greifeneder, and Peter M. Todd. [Can There Ever Be Too Many Options? A Meta-analytic Review of Choice Overload](https://scheibehenne.de/ScheibehenneGreifenederTodd2010.pdf). *Journal of Consumer Research* 37, 2010, pp. 409–425. Original paper; near-zero mean and substantial heterogeneity across 63 conditions from 50 experiments.

[^16]: Alexander Chernev, Ulf Böckenholt, and Joseph Goodman. [Choice Overload: A Conceptual Review and Meta-analysis](https://doi.org/10.1016/j.jcps.2014.08.002). *Journal of Consumer Psychology* 25, 2015, pp. 333–358. Publisher abstract; moderators rather than a context-free option limit.

[^17]: Samangi Wadinambiarachchi, Ryan M. Kelly, Saumya Pareek, Qiushi Zhou, and Eduardo Velloso. [The Effects of Generative AI on Design Fixation and Divergent Thinking](https://arxiv.org/abs/2403.11164). *CHI*, 2024; author manuscript/abstract. Visual ideation with 60 participants, not textual software-architecture dialogue.

[^18]: Rahul Mohanani, Iflaah Salman, Burak Turhan, Pilar Rodríguez, and Paul Ralph. [Cognitive Biases in Software Engineering: A Systematic Mapping Study](https://arxiv.org/pdf/1707.03869). Author manuscript, revised 2018; DOI 10.1109/TSE.2018.2877759. See sections 4–5 for taxonomy, mitigation gaps, and validity concerns. The design examples and candidate checks in this note are original applications, not measured effects from that review.

[^19]: Melissa L. Finucane, Ali Alhakami, Paul Slovic, and Stephen M. Johnson. [The Affect Heuristic in Judgments of Risks and Benefits](https://stanford.edu/~knutson/jdm/finucane00.pdf). *Journal of Behavioral Decision Making* 13, 2000, pp. 1–17. Original paper, two experiments; relevant to affect and time pressure, not diagnosis of an individual collaborator.

[^20]: Daniel Kahneman and Gary Klein. [Conditions for Intuitive Expertise: A Failure to Disagree](https://pubmed.ncbi.nlm.nih.gov/19739881/). *American Psychologist* 64, 2009, pp. 515–526. Original authors' synthesis; [author-paper copy](https://bear.warrington.ufl.edu/brenner/mar7588/Papers/kahneman-klein-2009.pdf). Conditions for skilled intuition provide a counterweight to dismissing past experience as bias.

[^21]: Mrinank Sharma and colleagues. [Towards Understanding Sycophancy in Language Models](https://arxiv.org/abs/2310.13548). 2023 author paper; [original research account](https://www.anthropic.com/research/towards-understanding-sycophancy-in-language-models). Historical assistant experiments and preference evidence, not a current installed-harness measurement.

[^22]: Francesco Sovrano, Gabriele Dominici, and Alberto Bacchelli. [Mitigating Prompt-Induced Cognitive Biases in General-Purpose AI for Software Engineering](https://arxiv.org/html/2604.16756v1). arXiv preprint, April 18, 2026, version 1. See sections 3, 4, 6, and 8. Preliminary evidence; the selected open-ended follow-up does not warrant a broad deployment guarantee.

[^23]: Charles G. Lord, Mark R. Lepper, and Elizabeth Preston. [Considering the Opposite: A Corrective Strategy for Social Judgment](https://pubmed.ncbi.nlm.nih.gov/6527215/). *Journal of Personality and Social Psychology* 47, 1984, pp. 1231–1243. Indexed abstract; two social-judgment experiments, not software review trials.

[^24]: Charlan Nemeth, Keith Brown, and John Rogers. [Devil's Advocate versus Authentic Dissent: Stimulating Quantity and Quality](https://www.researchgate.net/publication/229780153_Devil%27s_advocate_versus_authentic_dissent_Stimulating_quantity_and_quality). *European Journal of Social Psychology* 31, 2001, pp. 707–720; DOI 10.1002/ejsp.58. Original full text uploaded by an author. See discussion around pp. 716–717: distinguish quantity and the combined measure from quality alone; do not equate role-play with genuine independent evidence.

[^25]: Zana Buçinca, Maja Barbara Malaya, and Krzysztof Z. Gajos. [To Trust or to Think: Cognitive Forcing Functions Can Reduce Overreliance on AI in AI-Assisted Decision-Making](https://www.eecs.harvard.edu/~kgajos/papers/2021/bucinca2021trust.shtml). *Proceedings of the ACM on Human-Computer Interaction*, 2021. Authors' research page/abstract; 199-participant experiment and the usefulness-versus-preference trade-off.

[^26]: Helena Vasconcelos and colleagues. [Explanations Can Reduce Overreliance on AI Systems During Decision-Making](https://arxiv.org/abs/2212.06823). *CSCW*, 2023; author manuscript, version 2, January 2023. Five experiments with 731 participants in a maze-based decision task. Verification costs matter; applicability to architecture reviews remains to be tested.

[^27]: Jakob Nielsen. [Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/). Nielsen Norman Group, 2006. Original practitioner guidance, not a controlled akmon study or a license to hide essential information.

[^28]: Saleema Amershi and colleagues. [Guidelines for Human-AI Interaction](https://www.microsoft.com/en-us/research/wp-content/uploads/2019/01/Guidelines-for-Human-AI-Interaction-camera-ready.pdf). *CHI*, 2019. Original paper; guideline evaluation involving 49 design practitioners and 20 products. Does not establish long-running agent-development outcome improvements.

[^29]: Michael Nygard. [Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions). Cognitect, November 15, 2011. Original practitioner proposal for short, consequential decision records and preserving superseded decisions; suggested page lengths are not cognitive limits.

[^30]: MADR maintainers. [ADR Template](https://adr.github.io/madr/decisions/adr-template.html). Living project documentation, accessed September 13, 2026. Practical structure for drivers, options, consequences, and confirmation; reuse candidate, not an authority over akmon contracts.

[^31]: NASA Human Systems Integration Division. [NASA Task Load Index](https://www.nasa.gov/human-systems-integration-division/nasa-task-load-index-tlx/). Official instrument documentation, accessed September 13, 2026. Multidimensional subjective workload assessment; an abbreviated informal question is not automatically equivalent to the instrument.

[^32]: Nicole Forsgren and colleagues. [The SPACE of Developer Productivity: There's More to It Than You Think](https://www.microsoft.com/en-us/research/publication/the-space-of-developer-productivity-theres-more-to-it-than-you-think/). *ACM Queue*, 2021. Author-affiliated record; multidimensional productivity framework, not an attention-to-token conversion formula.

[^33]: Robert F. Lorch Jr. and Elizabeth P. Lorch. [Effects of Headings on Text Recall and Summarization](https://scholars.uky.edu/en/publications/effects-of-headings-on-text-recall-and-summarization/). *Contemporary Educational Psychology* 21, 1996, pp. 261–278. Institutional abstract; two experiments distinguishing topic familiarity and recall/summarization effects.

[^34]: Slava Kalyuga, Paul Ayres, Paul Chandler, and John Sweller. [The Expertise Reversal Effect](https://www.tandfonline.com/doi/abs/10.1207/S15326985EP3801_4). *Educational Psychologist* 38(1), 2003, pp. 23–31; [original-paper copy](https://www.davidlewisphd.com/courses/EDD8121/readings/2003-Kalyuga_et_al.pdf). Empirical-literature review, including the conclusion on redundant guidance. The journal year is 2003, not the later online-posting year. Application to development-agent explanations is a hypothesis.

[^35]: Leah Findlater and Joanna McGrenere. [A Comparison of Static, Adaptive, and Adaptable Menus](https://www.cs.ubc.ca/labs/edapt/papers/findlater2004.pdf). *CHI*, 2004, pp. 89–96. Original eight-page paper; 27-participant controlled study, with order-dependent results and an optimally configured static comparison. Supports caution about assuming automatic adaptation helps; does not establish chatbot effects.

[^36]: Lisanne Bainbridge. [Ironies of Automation](https://www.sciencedirect.com/science/article/pii/0005109883900468). *Automatica* 19(6), 1983, pp. 775–779. Publisher abstract available through search; full-text retrieval unavailable in this pass. Used only for the broad operator/abnormal-condition problem; the exception-handoff proposal is an application, not a measured agent-workflow effect.

### Local session trace index

The following are private local records, not public bibliography links. Line
references in the session table identify JSONL records in these files; dates
identify the historical observations, not current approval state. The excerpts
were selected for this task and should be re-read in context if a later design
depends on a stronger interpretation. No unrelated project conversations are
included in the evidence table.

- X1 — Codex, `/home/ai/.codex/sessions/2026/08/21/rollout-2026-08-21T07-27-38-01a02337-ddb3-7cc0-96e6-4f98300905d1.jsonl`.
  Relevant direct-message episodes: August 23–25, September 8–9, and September 13, 2026.
- X2 — Codex, `/home/ai/.codex/sessions/2026/08/27/rollout-2026-08-27T06-18-39-01a041de-da04-7643-87ad-080598291ec6.jsonl`.
  Relevant direct-message episodes: August 27 through September 2, 2026.
- C1 — Claude, `/home/ai/.claude/projects/-home-ai-workspace-akmon/241e7f9a-15e1-497d-8d37-2ef417631084.jsonl`.
  Selected owner request at line 753, August 21, 2026, 12:43:56 UTC; candid correction at line 845, 13:01:33 UTC.
- C2 — Claude, `/home/ai/.claude/projects/-home-ai-workspace-akmon/c8d142c8-d5ea-409c-b62e-57c247ec8405.jsonl`.
  Selected review requests at lines 1958 and 2155, August 28 and August 31, 2026; closure instruction at line 2295, August 31, 08:57 UTC.
- C3 — Claude, `/home/ai/.claude/projects/-home-ai-workspace-akmon/7eb1f1d8-ebda-474a-af81-e905f4138cd3.jsonl`.
  Selected result reports at lines 530 and 788, August 25, 2026, 14:06 and 14:40 UTC.
- C4 — Claude, `/home/ai/.claude/projects/-home-ai-workspace-akmon/0abb18e2-bafb-4e68-9bdd-d78dea2a76b5.jsonl`.
  Selected delegation and checking reports at lines 1760 and 2033, September 13, 2026, 07:41 and 08:06 UTC.
- C5 — Claude, `/home/ai/.claude/projects/-home-ai-workspace-akmon/d387e57c-00c6-4be2-9fb5-a7250797077a.jsonl`.
  Selected delegation, disclosed limitation, and fallback checks at lines 26–66, September 12, 2026.

Repository references in the foundations table describe the checkout inspected on
September 13, 2026. Concurrent staged and unstaged work existed. This research note
does not endorse that work, reclassify its status, or replace a current diff-based
review when the design is resumed.
