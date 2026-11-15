# Pipeline: knowledge lookup

How an agent, in any role, gets knowledge the work needs and does not have, and what a math question
to the owner carries. It layers on the [common guardrails](../guardrails/_common.md), which point here.

## Where knowledge comes from

In this order, stopping at the first that answers:

1. The project's own records — memory, designs, decisions, measurements, a skill's `references/` —
   and its code.
2. The documentation and source of the language, library or service in question.
3. The ordinary web request.

A fact from outside the project that the work relies on is recorded where the project keeps
knowledge — a memory note, or the `references/` of the skill that needs it — with the address of
its source and the date it was read, so the next session does not look it up again.

## When no source has it — gather it with the user

When the ordinary web request cannot reach the knowledge — a bot check, a sign-in, a page that only
a browser renders, a resource with no API or no token — the agent does not guess and does not stop
at the refusal. It says what is missing and proposes to get it **together with the user**:

- **The shared window.** The [`akmon-browser`](../skills/akmon-browser/SKILL.md) skill gives the
  project a Chrome window shared with the user. The user signs in by hand; the agent reads the
  pages and navigates them; a change on the site is one step the user confirmed while watching. This
  is how material for development is collected from resources a bot is refused: with the user, not
  instead of them.
- **Without the window** — no Node, the user declines it, or the harness cannot run it — the user
  opens the page and pastes the part the work needs into the chat.
- **Only in the developer's session.** An `autonomous` run and a delegated agent do not drive the
  browser; they name the knowledge they lack and hand the step back to the developer's session.
- **Not a way around a site.** The shared window lets the agent work beside the user; it does not
  get around a site's bot check or its terms of use. Where a site blocks automation or its terms
  forbid automated reading, the user reads the page and the agent works from what the user passes
  on.

What is gathered is recorded as in [§ Where knowledge comes from](#where-knowledge-comes-from), with
the page's address.

## The browser on request, and several projects

When the user asks, the agent opens the browser through the skill — `akmon tool browser start`,
with `--url` for a given page, after the one-time setup the skill describes — to read, check or
debug a page under development, or to work in a resource together.

Each project has its own Chrome, with its own profile and port, so several projects are developed
side by side, each in its own window with its own sign-ins. A session that works across several
checkouts runs the tool from each project's own checkout and follows that project's own rules and
branch; one project's Chrome is refused from another.

## Industry practice for a math question

Before a question to the owner about math — a formula, a method, a convention, a numerical scheme, a
model or a calibration choice — the agent gathers **how the industry does it**:

- **The established approaches**, the ones reference texts, standards and widely used libraries
  take, each with a source the owner can open: a paper, a textbook, a standard, a library's
  documentation or source. The search is proportional: a settled convention needs one good source,
  a contested method needs each of its schools.
- **Where the project stands:** which approach its code uses now and where (`path:line`), or that
  it has none yet.

The request then follows [design-flow § Decision requests](design-flow.md#decision-requests), and:

- **every option says who does it that way;**
- **a recommendation that departs from common practice says why;**
- **an approach with no source is named unconfirmed**, and where the industry has no settled
  practice, the request says so rather than presenting one.

The gathered material — the approaches, their sources and the project's current place — lives in the
design or task the request belongs to, not only in the chat. A source behind a sign-in or a bot check
is gathered [with the user](#when-no-source-has-it--gather-it-with-the-user). A project doing
numerics also follows the [quant](../profiles/quant.md) profile.
