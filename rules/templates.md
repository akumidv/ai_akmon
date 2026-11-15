# Rules: templates

The shapes the [rules](collaboration.md) use, loaded at session start so the first reply already has
them. A format owned by code or a pipeline — a backlog row, a park note, a decision block — stays with
its owner.

## Owner request item

A decision:

```
1. **D-C139-ORDER** — order of rows in the report

   Σ. <the question in one to three sentences, one fact each, on a concrete case>.

   Options:
   - (a) <the choice> — <its cost, its weak spot, what stays>;
   - (b) <the choice> — <its cost, its weak spot, what stays>;
   - (c) <the choice> — rejected: <why>.

   Recommendation — (b): <the reason, one or two sentences>. After <what it waits on>.
```

The blank lines and the option list are kept: a Markdown view joins adjacent lines into one paragraph.

An action:

```
2. **D-C139-WRITE** — record the accepted order in the ADR.
```

## Needed from you

```
## Needed from you

**Decide**

1. <decision items>

**Act**

2. <action items>

Answer "all as recommended" for the decisions and name the exceptions by code; each action needs its own code.
```

An answer `all as recommended, except D-C139-ORDER: a; D-C139-WRITE: yes` accepts every recommended
decision but the order, takes (a) there, and permits the one action by its code.
