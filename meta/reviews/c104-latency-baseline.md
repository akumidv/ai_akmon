# C104 — Python hook latency baseline (M122)

The budget of ADR 0020/D05 is "JS hook p50 no slower than the Python package-mode hook p50 on the
same host". This file holds the Python side, measured before any JS hook exists, so the JS side
(C104 step 9) compares against a number recorded first rather than one chosen afterwards.

## What was measured

Wall time of one process launch per hook-corpus scenario, from the spawn to the exit, with the
scenario's own stdin payload (`meta/conformance/scenarios/hooks/*.toml`, 36 scenarios; the
`{{root}}` token filled with the project below). The command is the package wiring
`<project>/.venv/bin/akmon hook <name>` — what `.claude/settings.json` calls. Each scenario ran 3
warm-up launches (discarded) and 30 timed ones; its p50 is the median of the 30. The summary is
the median of the 36 scenario p50s.

The project is a throwaway `akmon init --mode package --no-ci --yes` attach in a scratch
directory (`git init`, `.venv/bin/akmon` linked to this checkout's console script). The launcher
runs the hook inside this checkout's tree. No harness was involved: the hooks were launched
directly, so the row carries no Claude Code or Codex version.

Host: Intel Xeon E5-2695 v2, 4 vCPU, Linux 6.8.0-139, load average 1.53 when the first pass began.
Python 3.12.3, Node v24.21.0, akmon 0.4.0.dev0 (84b9e86).

## Result

Two full passes (30 timed launches per scenario each) gave a median of scenario p50s of
**178.3 ms** and **194.4 ms**. The spread between passes is host noise, so the baseline is the
range, not either figure. Per-script medians of the scenario p50s, first pass:

| Hook script | Scenarios | Median p50 (ms) | Range (ms) |
|---|---|---|---|
| analysis-guard | 3 | 164 | 162–170 |
| session-start-agent | 3 | 169 | 169–174 |
| role-on-code | 2 | 168 | 164–172 |
| delegation-nudge | 7 | 177 | 161–186 |
| git-commit-guard | 6 | 178 | 165–184 |
| codex-hook | 7 | 191 | 155–201 |
| gate-audit | 3 | 201 | 189–207 |
| delegation-log | 2 | 204 | 199–210 |
| model-routing | 3 | 204 | 195–206 |

The three scripts that read `tools/model_routing/routing.py` (gate-audit, delegation-log,
model-routing) are the three slowest.

Process-start floors on the same host, 40 timed launches each (p50 / min, ms):

| Launch | p50 | min |
|---|---|---|
| `node empty.mjs` | 94.9 | 54.5 |
| `python3 -c pass` | 52.1 | 40.8 |
| `python3 -S -c pass` | 23.7 | 17.8 |
| `.venv/bin/akmon version` | 166.0 | 121.4 |

A launch of the Python package CLI that does nothing costs 166 ms, nearly all of the hook figure:
the Python hook is mostly import and launcher cost. The Node floor is about 95 ms (min 54 ms), so
a JS hook has roughly 80–100 ms of work above bare Node start before it loses to the Python
baseline. The same-host comparison still has to be taken again when the JS hooks exist.

## Reproduce

`bench.py <label> <runs> py-package` from a directory holding the scratch project at `./proj`;
after C104 lands, `node` replaces the launcher with `node js/hooks/<script>.mjs`.

```python
import json, os, statistics, subprocess, sys, time, tomllib
from pathlib import Path

REPO = Path("/home/ai/workspace/akmon")
PROJ = Path(__file__).parent / "proj"
TMP = Path(__file__).parent / "tmp"
TMP.mkdir(exist_ok=True)
label, runs, mode = sys.argv[1], int(sys.argv[2]), sys.argv[3]

def command(script, args):
    if mode == "py-package":
        return [str(PROJ / ".venv/bin/akmon"), "hook", script, *args]
    if mode == "node":
        return ["node", str(REPO / "js/hooks" / f"{script}.mjs"), *args]
    raise SystemExit(f"mode {mode}")

def fill(text):
    return text.replace("{{root}}", str(PROJ)).replace("{{tmp}}", str(TMP))

rows = []
for path in sorted((REPO / "meta/conformance/scenarios/hooks").glob("*.toml")):
    spec = tomllib.loads(path.read_text())
    run = spec["run"]
    payload = fill(json.dumps(run.get("payload", {}))) if run.get("payload") else ""
    args = [fill(a) for a in run.get("args", [])]
    if "{{" in payload or any("{{" in a for a in args):
        continue
    env = {**os.environ, "TMPDIR": str(TMP), **{k: fill(v) for k, v in spec.get("env", {}).items()}}
    argv = command(run["script"], args)
    samples = []
    for i in range(runs + 3):
        t0 = time.perf_counter()
        subprocess.run(argv, input=payload, text=True, capture_output=True, env=env, cwd=PROJ, check=False)
        if i >= 3:
            samples.append((time.perf_counter() - t0) * 1000)
    rows.append((spec["id"], run["script"], statistics.median(samples)))
print(label, "scenarios", len(rows), "median-of-p50", statistics.median(r[2] for r in rows))
```

(The run printed per-scenario lines as well; this copy keeps only the measuring core.)

## Limits

- Launch time, not in-harness time: a harness adds its own spawn and pipe cost to both sides.
- Scenarios whose state lives in `TMPDIR` (second-edit-silent) were not reset between launches,
  so a stateful hook may take its silent path on most of the 30; the figure is still one launch's
  cost, and the same applies to the JS run.
- A noisy 4-vCPU host: two passes differ by 16 ms. Compare the JS run to the range.
