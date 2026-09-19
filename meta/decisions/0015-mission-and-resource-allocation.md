# 0015 — Mission: attention, decision quality, and effective resource allocation

- **Status:** Accepted
- **Owner:** akuminov@gmail.com
- **References:** [MODEL mission](../../MODEL.md#mission-and-priorities) ·
  [research and living design](../design/attention-and-human-agent-collaboration.md) ·
  [A22/C86](../TASKS.md)

## Context

Agent work is not successful merely because it adds functionality, minimizes tokens, or reaches
agreement quickly. The scarce resources are different: owner attention, agent/model work,
elapsed time, implementation effort, and future rework. Local savings can worsen the total
outcome, while additional design or stronger reasoning can be the cheaper choice over the
relevant lifecycle.

## Accepted decision block

### D01 — Product mission and economic criterion

`Decision-ID: ADR-0015/D01`
`Legacy-ID: D2-44`

Akmon exists to improve project outcomes through better human-agent collaboration. It puts the
person's knowledge and judgment on goals and consequential choices, delegates routine cognitive
work, and keeps decisions understandable, challengeable, and verifiable. Resource policy seeks
the best expected outcome for total relevant cost, not minimum spend at each step. More design
time or the strongest suitable model at high reasoning effort is justified when its expected
reduction in implementation error, rework, or decision risk is greater than its cost.

Truthfulness, visible uncertainty and product-goal fit constrain optimization. Agreement is not
evidence of quality; the agent must expose material alternatives and problems and may challenge
both the owner's and its own preferred answer. Human attention and token spend remain distinct
costs and are reported separately where measured.

This block accepts the mission and priority ordering only. It does not claim that A22's proposed
interaction protocol is effective, does not impose a universal report length or model choice,
and does not authorize autonomous acceptance. Those behaviours require their own accepted
decision block plus implementation and evaluation evidence.

## Rejected alternatives

- **Minimize tokens or human time independently.** Rejected because either can move cost into
  defects, rework, or missed goals.
- **Always use maximum model effort.** Rejected because expense without expected leverage is not
  efficiency.
- **Treat owner agreement as the optimization target.** Rejected because sycophancy can reduce
  decision quality while making interaction feel easier.

## Reconsider when

Evaluation shows that this priority ordering systematically worsens real project outcomes, or a
measurable common cost model can replace the explicit multi-resource judgment without hiding
owner attention or downstream rework.
