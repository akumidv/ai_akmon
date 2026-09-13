# Attention and human–agent collaboration

## Task brief and direction

This is a living research concept for improving the whole collaboration between a
project owner and development agents. It preserves the problem statement, evidence,
candidate approaches, disagreements, and questions for a later design decision.
It is not an accepted contract, implementation specification, or D2 approval.

The objective is to spend the owner's time and thinking where their experience,
knowledge, judgment, and understanding of future use can improve the product. Agents
should absorb routine investigation, comparison, synthesis, and authorized repair;
communication should help both parties develop and retain an accurate shared
understanding. Shorter output is useful only when it preserves that understanding.

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

No architecture choice is locked here. Recording these notes does not authorize
changes to contracts, skills, tasks, the D2 ledger, or consumer materializations.

## Evidence and candidate design

Research synthesis is being assembled in this section. External findings, repository
observations, session evidence, proposed requirements, and unresolved choices will
be distinguished explicitly.
