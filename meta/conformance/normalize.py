#!/usr/bin/env python3
"""Corpus normalization, v2 — the spec half of the conformance corpus (design §5, C101).

The corpus compares *normalized* process output: a scenario file is written in normalized
form already (it contains the ``{{token}}`` placeholders), and the runner maps every
observable of the implementation under test — stdout, stderr, written file contents, and
the paths it names — into that same form before comparing byte for byte. Anything a rule
below does not normalize must match exactly.

The rules exist so that the two permanent implementations (ADR 0020 D01) can be compared
at the process boundary without either one winning on spelling:

- a hook command in generated wiring is one fact — *which anchor it hangs from* and *which
  hook it runs* — however the ecosystem spells the invocation (``python3 "<anchor>/…/hooks/
  <name>.py"``, ``node "<anchor>/…/hooks/<name>.mjs"``, or a launcher ``"<anchor>/<rel>" hook
  <name>``). The anchor is kept: a command that does not hang from ``$CLAUDE_PROJECT_DIR`` or
  ``$(git rev-parse --show-toplevel)`` is not normalized, so an absolute path stays visible;
- the package-mode spelling of a tool invocation (``python3 $(akmon path)/tools/<tool>.py``)
  is one fact, ``{{tool <tool>}}`` — the Node spelling joins this rule with ``akmon tool``
  (C108). The mounted spelling names the mount and is deliberately left as written;
- a parser's own diagnostic (the text after ``invalid JSON:`` / ``cannot be read as TOML:``)
  is implementation-defined; that the file failed to parse, and which file, is spec;
- where the project sits, where the standard tree sits, and where temp state goes, are
  facts of the host, not of the implementation;
- the running version, and dates and timestamps *of the run day*, are point-in-time facts.
  A date from any other day came from a fixture and is compared literally.

Order matters and is normative: the wiring and tool rules run first (they contain paths),
then parser details, then the path tokens longest-path-first, then the point-in-time
tokens. A rule change is a new corpus version: bump :data:`NORM_VERSION` and say what
changed in README.md, do not reorder silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Corpus normalization version. Scenario expectations are only comparable across runs
#: that used the same version; the runner stamps it into its report.
#: v2: the hook rule keeps the anchor and covers the launcher form; {{tool}}; {{parse-error}};
#: point-in-time tokens only for the run day.
NORM_VERSION = 2

# --- the tokens a scenario file may contain -------------------------------------

ROOT = "{{root}}"
MOUNT = "{{mount}}"
TREE = "{{tree}}"
TMP = "{{tmp}}"
REPO = "{{repo}}"
VERSION = "{{version}}"
TS = "{{ts}}"
DATE = "{{date}}"
PARSE_ERROR = "{{parse-error}}"


@dataclass(frozen=True)
class Ctx:
    """The host facts one runner invocation knows, and the normalization maps onto."""

    root: str  # the consumer project root for this scenario run
    mount: str  # <root>/<aitna>/akmon when a mount is present, else "" (no rule applied)
    tree: str  # the standard tree under test (the implementation's own checkout)
    tmp: str  # the run-private tempdir the process under test is pointed at
    version: str  # the version the implementation under test reports
    repo: str = ""  # the local standard-tree git repo the runner builds for --repo runs, else ""
    days: tuple[str, ...] = field(default=())  # YYYY-MM-DD dates the run spans (usually one)


# The two anchors a generated hook command may hang from (sync's spellings), as regex.
_ANCHORS = (r"\$CLAUDE_PROJECT_DIR", r"\$\(git rev-parse --show-toplevel\)")
_ANCHOR = r"(" + r"|".join(_ANCHORS) + r")"
# In raw JSON file contents the quotes are backslash-escaped; both spellings match.
_Q = r'\\?"'
_NAME = r"([a-z0-9][a-z0-9-]*)"
_DIRECT_HOOK = re.compile(r"(?:python3|node) " + _Q + _ANCHOR + r'/[^"\\]*?hooks/' + _NAME + r"\.(?:py|mjs)" + _Q)
_LAUNCHER_HOOK = re.compile(_Q + _ANCHOR + r'/[^"\\]+?' + _Q + r" hook " + _NAME)
_TOOL = re.compile(r"python3 \$\(akmon path\)/tools/([a-z0-9_/]+)\.py")
# The parser's own words run to the finding's fix arrow or the line end (a parser detail is only
# ever printed inside a finding line; it may itself hold a quoted repr such as '\n').
_PARSE_DETAIL = re.compile(r"(invalid JSON|cannot be read as TOML): .+?(?= → |$)", re.MULTILINE)

_TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")
_STAMP_RE = re.compile(r"\b(\d{4})(\d{2})(\d{2})-\d{6}\b")
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def _hook_token(match: re.Match[str]) -> str:
    return f"{{{{hook {match.group(1)} {match.group(2)}}}}}"


def _point_in_time(text: str, days: tuple[str, ...]) -> str:
    """Timestamps and dates of the run day become tokens; any other day is fixture data."""
    out = _TS_RE.sub(lambda m: TS if m.group(1) in days else m.group(0), text)
    out = _STAMP_RE.sub(lambda m: TS if f"{m.group(1)}-{m.group(2)}-{m.group(3)}" in days else m.group(0), out)
    return _DATE_RE.sub(lambda m: DATE if m.group(0) in days else m.group(0), out)


def normalize(text: str, ctx: Ctx) -> str:
    """Map one observable into the corpus's normalized form (see module docstring for order)."""
    out = _DIRECT_HOOK.sub(_hook_token, text)
    out = _LAUNCHER_HOOK.sub(_hook_token, out)
    out = _TOOL.sub(lambda m: f"{{{{tool {m.group(1)}}}}}", out)
    out = _PARSE_DETAIL.sub(lambda m: f"{m.group(1)}: {PARSE_ERROR}", out)
    # Longest path first: a path nested in another (the mount in the root) must win over its parent.
    paths = ((ctx.mount, MOUNT), (ctx.tree, TREE), (ctx.root, ROOT), (ctx.repo, REPO), (ctx.tmp, TMP))
    for raw, token in sorted((pair for pair in paths if pair[0]), key=lambda pair: -len(pair[0])):
        out = out.replace(raw, token)
    if ctx.version:
        out = out.replace(ctx.version, VERSION)
    return _point_in_time(out, ctx.days)
