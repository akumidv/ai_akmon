#!/usr/bin/env python3
"""Synchronize generated agent pointers for an akmon-consuming project.

The source of truth stays in AGENTS.md, akmon docs, and SKILL.md files. This tool writes
thin vendor pointers and hook wiring so assistants do not need duplicated instruction
copies. It is intentionally stdlib-only and safe to run repeatedly.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

# The shared utilities live in the tree's ``common`` package, not beside this script:
# ``bin/`` is the launcher directory. A launcher is run as ``python3 <tree>/bin/sync.py``, so
# ``sys.path[0]`` is ``bin/`` — the tree root has to be added for the package to resolve. Done
# here rather than left to the caller because both launchers are entry points in their own right.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.findings import Finding, line_safe, print_findings  # noqa: E402
from common.materialization import (  # noqa: E402
    GENERATED_MARKER,
    generated_banner,
    materialized_markdown,
)
from common.project_root import (  # noqa: E402
    aitna_root,
    aitna_root_name,
    resolve_project_root,
)
from common.project_root import akmon_mount as akmon_root  # noqa: E402
from common.record import _strip_inline_comment, read_akmon_toml, recorded_mount  # noqa: E402,F401

# Two shared owners, both for the same reason a hook must reach them. The integration record
# (C69/D2-26): the hooks needed it too, and a sixth narrow copy is what that decision refused.
# The banner rule and the materialized-guardrail format (C77): a hook answers "is this copy of
# the guardrails still current?" at SessionStart, and it must not hold a second copy of the
# format to answer with. Both are re-exported here because `verify`, `init` and the tests
# already reach them through this module.

# The dev-layer (LOCAL) root is configurable and the project root is discovered, not assumed;
# both answers come from the single owner in ``common/project_root.py`` (C73) and are
# re-exported here because every generated pointer and hook command is templated from them, and
# because callers and tests already reach them through this module.


# This file's own tree root (``bin/``'s parent) — in a mounted checkout that is the mount
# itself; in package mode it is whatever copy of the standard is actually running this
# script (an installed wheel's embedded ``akmon/_tree``, or a plain source checkout during
# akmon's own development). A plain ``Path(__file__)`` derivation, not ``importlib.resources``
# or an import of the ``akmon`` package: bin/ must stay runnable standalone
# (``python3 <tree>/bin/sync.py``) in mounted mode, where no Python package is installed at
# all (ADR 0009 §4).
_TREE_ROOT = Path(__file__).resolve().parent.parent


def read_mount_mode(project_root: Path) -> str:
    """The recorded ``mount`` value from ``<AITNA_ROOT>/.akmon.toml`` (ADR 0009 §3):
    ``"submodule" | "vendored" | "subtree" | "package"``. An absent record or key defaults
    to ``"submodule"`` — the traditional mounted-tree default, kept for backward
    compatibility with every project that predates this field.
    """
    return recorded_mount(project_root) or "submodule"


def is_package_mode(project_root: Path) -> bool:
    """Whether ``project_root`` is governed by mount mode ``package`` (ADR 0009 §4).

    Driven solely by the recorded ``.akmon.toml`` ``mount`` field, never by whether
    ``<AITNA_ROOT>/akmon`` happens to exist on disk: a stale mount directory left over from
    a prior mode must not shadow a project that has since switched to package mode (and,
    symmetrically, an absent record must not be misread as package mode just because no
    mount exists yet — see ``read_mount_mode``'s backward-compatible default).
    """
    return read_mount_mode(project_root) == "package"


# A requirement *naming* akmon: the quoted PEP 508 form (`"akmon @ git+..."`, `"akmon==0.4.0"`)
# anywhere in a value. `(?![\w.-])` rather than `\b` so a different distribution whose name merely
# starts with it (`akmon-plugin`) is not read as the pin. The poetry/pdm table form
# (`akmon = { git = ... }`) is recognised by its key instead, in ``package_pin_status``.
_AKMON_REQUIREMENT_RE = re.compile(r"""["']\s*akmon(?![\w.-])""", re.IGNORECASE)

# Sections that declare a *runtime* dependency — one that reaches the consumer's own users.
# `optional-dependencies` (PEP 621 extras) counts: an extra ships with the distribution.
_RUNTIME_SECTIONS = ("project", "tool.poetry")
# Sections that say *where a package comes from*, never *that it is required*: a lockfile-ish
# source override naming akmon is not a declaration, and reading it as one was how a manifest
# with no akmon dependency at all classified as pinned.
_SOURCE_SECTIONS = ("tool.uv.sources", "tool.poetry.source", "tool.pdm.source")


def _is_dev_dependency_section(section: str, key: str) -> bool:
    """Whether ``section`` is a supported dev-dependency declaration table."""
    return (
        section == "dependency-groups"
        or (section == "tool.uv" and key == "dev-dependencies")
        or section == "tool.pdm.dev-dependencies"
        or (section.startswith("tool.poetry.group.") and section.endswith(".dependencies"))
    )


def manifest_lines(project_root: Path):
    """``pyproject.toml`` as ``(section, key, line)`` triples, comments stripped.

    A deliberate line scan rather than a full TOML parse: it reads just enough structure to tell
    *where* a requirement sits — the section header, and the key whose (possibly multi-line)
    array is still open — without adding a runtime dependency (ADR 0009 §1).
    """
    manifest = project_root / "pyproject.toml"
    if not manifest.is_file():
        return
    section = ""
    key = ""
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        line = _strip_inline_comment(raw).strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section, key = line[1:-1].strip(), ""
            continue
        name, sep, value = line.partition("=")
        if sep:
            key = name.strip()
            yield section, key, value.strip()
            if not value.strip().startswith("["):
                key = ""
            continue
        yield section, key, line
        if line.endswith("]"):
            key = ""


def package_pin_status(project_root: Path) -> str:
    """How the consumer's manifest pins akmon: ``"dev"``, ``"runtime"`` or ``"none"``.

    Mode ``package`` mounts no tree: the pin *is* the consumer's dependency declaration, and
    ADR 0009 §4 locks which class it may be — a **dev** group, never a runtime dependency and
    never an extra, because akmon is dev tooling and must not reach the consumer's own users.
    So this reports three answers, not two: a pin in the wrong class is a finding, not a pass.

    Every declaration is scanned and the **worst** answer wins — stopping at the first match
    let a correct dev pin hide a runtime one declared further down the same file. A bare
    mention in prose or a comment is not a pin, and neither is a `[tool.uv.sources]` entry:
    both used to read as "declared", which let a package-mode attach finish green over a
    project where ``uv run akmon`` cannot resolve at all.

    Shared by ``akmon init`` (which reports it as a next step) and ``verify.py`` (which gates
    on it) so the two cannot disagree about what a valid pin looks like.
    """
    status = "none"
    for section, key, line in manifest_lines(project_root):
        distribution_key = key.casefold() == "akmon"
        requirement_value = bool(_AKMON_REQUIREMENT_RE.search(line))
        if not (requirement_value or distribution_key):
            continue
        if section in _SOURCE_SECTIONS or section.endswith(".sources"):
            continue
        runtime = (
            # `[project] dependencies = [...]` / `[tool.poetry] dependencies = [...]`
            (section in _RUNTIME_SECTIONS and key == "dependencies")
            # poetry's runtime table: `[tool.poetry.dependencies]`, one key per package
            or (section == "tool.poetry.dependencies" and distribution_key)
            # an extra ships to the consumer's users too — ADR 0009 §4 rules it out with the rest
            or section.endswith("optional-dependencies")
        )
        if runtime:
            return "runtime"
        if _is_dev_dependency_section(section, key):
            status = "dev"
    return status


def standard_tree_root(project_root: Path) -> Path:
    """The standard-tree content this script operates against for ``project_root``.

    The mount at ``<AITNA_ROOT>/akmon`` for mounted modes; this script's own tree
    (``_TREE_ROOT``) in package mode — the installed package *is* the pin, so a lingering
    stale mount directory from a prior mode must not shadow it (ADR 0009 §4-5, mirrored from
    the CLI's dispatch rule).
    """
    mounted = akmon_root(project_root)
    if not is_package_mode(project_root) and mounted.exists():
        return mounted
    return _TREE_ROOT


def _claude_md() -> str:
    return f"""# CLAUDE.md

<!-- {generated_banner()} -->

This project uses **[AGENTS.md](AGENTS.md)** as the single source of guidance for AI
coding agents (including Claude Code).

Claude Code auto-loads `CLAUDE.md` but **not** `AGENTS.md`, so AGENTS.md is imported below.
This keeps the canonical rules, including the always-on prime directives and "read
`{aitna_root_name()}/memory/` at session start", present in context from the start.

@AGENTS.md
"""


def _copilot_md() -> str:
    return f"""# Copilot Instructions

<!-- {generated_banner()} -->

This project uses **[AGENTS.md](../AGENTS.md)** as the single source of guidance for AI
coding agents, including GitHub Copilot.

See [AGENTS.md](../AGENTS.md) for the project overview, environment setup, architecture,
commands, testing, and conventions.
"""


def _gemini_md() -> str:
    return f"""# GEMINI.md

<!-- {generated_banner()} -->

This project uses [AGENTS.md](AGENTS.md) as the single source of guidance for AI coding
agents, including Gemini.

Read AGENTS.md before doing project work.
"""


def _codex_readme() -> str:
    return f"""# Codex

<!-- {generated_banner()} -->

Codex uses the project root [AGENTS.md](../AGENTS.md) as the single source of guidance.
This directory contains generated hook wiring and pointers only; do not duplicate project
instructions here.
"""


# The mounted hooks dir, as a POSIX suffix appended after a vendor's root anchor (Codex: git
# toplevel · Claude: $CLAUDE_PROJECT_DIR). Mounted modes only: mode ``package`` names no
# directory at all — see ``launcher_relative``.
def _mounted_hooks_dir() -> str:
    return f"{aitna_root_name()}/akmon/hooks"


# The console script installed by the akmon dev pin, relative to the project root.
_CLI_NAME = "akmon"
_DEFAULT_LAUNCHER_REL = f".venv/bin/{_CLI_NAME}"


def is_executable_file(path: Path) -> bool:
    """Whether ``path`` is a regular file the generated POSIX command can execute."""
    return path.is_file() and os.access(path, os.X_OK)


def launcher_relative(root: Path) -> str:
    """Where the ``akmon`` console script sits **inside ``root``**, as a POSIX relative path.

    Mode ``package`` wires its hooks as ``"<anchor>/<this>" hook <name>`` (C77), and that
    wiring is a committed file every developer on the project runs. So the answer must be a
    property of the *project*, not of whoever happened to run ``sync``: the conventional venvs
    first, and an interpreter-adjacent or ``PATH`` script only when it resolves inside the
    project root. A pipx install and akmon's own dev checkout running ``sync`` over a fixture
    are both normal and both outside — neither says anything about the consumer's layout, and
    an absolute path in a shared file is a silent break for the next developer.

    Never fails. When nothing is found the convention is returned: the prediction becomes true
    the moment the pin is installed, which is exactly the state a first attach is in — ``init``
    runs ``sync`` *before* the dev group is installed by construction, so a hard error here
    would break the one flow that has to work out of the box. The diagnostic lives in
    ``verify`` (``hooks.launcher``), which runs in the consumer's CI.
    """
    for candidate in (_DEFAULT_LAUNCHER_REL, f"venv/bin/{_CLI_NAME}"):
        if is_executable_file(root / candidate):
            return candidate
    resolved_root = root.resolve()
    found = shutil.which(_CLI_NAME)
    # ``Path(sys.executable).parent``, deliberately unresolved: a venv's ``python3`` is usually a
    # symlink to the system interpreter, so resolving first would look for the console script
    # beside ``/usr/bin/python3`` instead of in the venv that is actually running.
    for candidate in (Path(sys.executable).parent / _CLI_NAME, Path(found) if found else None):
        if candidate is None or not is_executable_file(candidate):
            continue
        try:
            return candidate.resolve().relative_to(resolved_root).as_posix()
        except ValueError:
            continue
    return _DEFAULT_LAUNCHER_REL


# Every spelling the generator has ever emitted, independent of the project's *current* mode:
# recognising an entry as akmon-managed must not depend on which mode (or which version) wrote
# it, so switching modes replaces the other spelling's entries instead of leaving them
# orphaned beside the new ones (ADR 0009 §4).
def _akmon_hook_markers() -> tuple[str, ...]:
    aitna = aitna_root_name()
    return (
        f"{aitna}/akmon/hooks/",  # mounted modes
        f"{aitna}/.akmon/hooks/",  # package mode before C77, when the hooks were materialized
        # Package mode today: the console script, no path into the repo. The closing quote is
        # part of the marker — a bare `akmon hook ` would also match a project's own hook that
        # merely mentions the word.
        f'{_CLI_NAME}" hook ',
    )


def _codex_hook_command(root: Path) -> str:
    """The Codex wiring's command prefix; the advisory name is appended by the caller.

    Package mode calls the console script (``akmon hook codex-hook``) rather than a file: the
    only file it could name would be inside the wheel, and that path carries the venv's Python
    version, so it breaks on the next interpreter bump — silently, because a hook command the
    harness cannot find produces no output and no error. Mounted modes are unchanged: there the
    path is both spellable and pinned.
    """
    anchor = "$(git rev-parse --show-toplevel)"
    if is_package_mode(root):
        return f'"{anchor}/{launcher_relative(root)}" hook codex-hook'
    return f'python3 "{anchor}/{_mounted_hooks_dir()}/codex-hook.py"'


def _codex_hooks(root: Path) -> dict:
    base = _codex_hook_command(root)
    return {
        "hooks": {
            "PreToolUse": [
                {
                    # Routes, not spellings. Measured on codex 0.146.0: `Edit`, `Write` and
                    # `apply_patch` are three live aliases for the same patch call, while the
                    # shell — the route its model took when a denied patch was refused —
                    # matches as `Bash` and was named by nothing here (C49). Not widened to
                    # `.*`: an unconditional hook on every shell call costs latency and noise
                    # on the hottest tool and buys precision nowhere.
                    "matcher": "Bash|apply_patch",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"{base} role-on-code",
                            "statusMessage": "Checking akmon role switch",
                        },
                        {
                            "type": "command",
                            "command": f"{base} analysis-guard",
                            "statusMessage": "Checking analysis-before-mutation",
                        },
                        {
                            "type": "command",
                            "command": f"{base} d2-ledger-reminder",
                            "statusMessage": "Checking D2 ledger",
                        },
                    ],
                }
            ],
            "SessionStart": [
                {
                    "matcher": "startup|resume|clear|compact",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"{base} session-start",
                            "statusMessage": "Loading akmon session reminders",
                        }
                    ],
                }
            ],
        }
    }


def _claude_hooks(root: Path) -> dict:
    package_mode = is_package_mode(root)
    launcher = launcher_relative(root) if package_mode else ""

    def cmd(script: str) -> str:
        """One hook command. Package mode names the console script (see ``_codex_hook_command``
        for why a path cannot be committed there); mounted modes name the file, unchanged."""
        if package_mode:
            return f'"$CLAUDE_PROJECT_DIR/{launcher}" hook {script}'
        return f'python3 "$CLAUDE_PROJECT_DIR/{_mounted_hooks_dir()}/{script}.py"'

    return {
        "hooks": {
            "PreToolUse": [
                {
                    # This one process also carries the unclassified-shell-route diagnostic
                    # (C49, D2-19 e): the advisories below sit on the edit tools, so a write
                    # that arrives through Bash is invisible to them on Claude too. Reusing
                    # the already-wired guard keeps that statement free — no second process
                    # on the hottest tool.
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": cmd("git-commit-guard")}],
                },
                {
                    "matcher": "Edit|Write|MultiEdit",
                    "hooks": [
                        {"type": "command", "command": cmd("role-on-code")},
                        {"type": "command", "command": cmd("analysis-guard")},
                        {"type": "command", "command": cmd("d2-ledger-reminder")},
                    ],
                },
                {
                    "matcher": "Task|Agent",
                    "hooks": [{"type": "command", "command": cmd("delegation-log")}],
                },
                {
                    # One entry with a combined matcher: _merge_hook_entries dedups by
                    # command, so the same script must not ride several matcher groups.
                    # Read|Grep|Glob are included so the nudge/ask also see read/sweep drift,
                    # not just edit/shell (guardrails/_common.md § Route by task kind).
                    "matcher": "Bash|Edit|Write|MultiEdit|Task|Agent|Read|Grep|Glob",
                    "hooks": [{"type": "command", "command": cmd("delegation-nudge")}],
                },
            ],
            "SessionStart": [
                {
                    "hooks": [
                        {"type": "command", "command": cmd("session-start-agent")},
                        {"type": "command", "command": cmd("model-routing")},
                    ]
                }
            ],
            # Per-turn: model-routing re-detects the orchestrator from the transcript and
            # rebinds subagents when a mid-session /model switch lands (silent otherwise).
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {"type": "command", "command": cmd("model-routing")},
                    ]
                }
            ],
        }
    }


@dataclass(frozen=True)
class PlannedFile:
    path: Path
    content: str


@dataclass
class Result:
    changed: list[Path]
    deleted: list[Path]
    ok: list[Path]
    errors: list[str]


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _hook_commands(entry: object) -> set[str]:
    if not isinstance(entry, dict):
        return set()
    hooks = entry.get("hooks")
    if not isinstance(hooks, list):
        return set()
    commands: set[str] = set()
    for hook in hooks:
        if isinstance(hook, dict) and isinstance(hook.get("command"), str):
            commands.add(hook["command"])
    return commands


def _is_akmon_entry(entry: object) -> bool:
    commands = _hook_commands(entry)
    markers = _akmon_hook_markers()
    return bool(commands) and all(any(marker in command for marker in markers) for command in commands)


def _merge_hook_entries(existing: object, wanted: list[dict]) -> list[object]:
    if not isinstance(existing, list):
        return list(wanted)
    # Drop stale akmon-managed entries first, then re-append the wanted ones. This keeps
    # user-authored hooks untouched while letting sync rewrite its own (e.g. a renamed hook
    # path) instead of leaving a dangling duplicate.
    merged = [entry for entry in existing if not _is_akmon_entry(entry)]
    existing_commands = set().union(*(_hook_commands(entry) for entry in merged)) if merged else set()
    for entry in wanted:
        commands = _hook_commands(entry)
        if not commands or commands.isdisjoint(existing_commands):
            merged.append(entry)
            existing_commands.update(commands)
    return merged


def _claude_settings(root: Path) -> PlannedFile:
    path = root / ".claude" / "settings.json"
    settings = _read_json(path)
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError(f"{path}: expected hooks to be a JSON object")
    for event_name, wanted_entries in _claude_hooks(root)["hooks"].items():
        hooks[event_name] = _merge_hook_entries(hooks.get(event_name), wanted_entries)
    return PlannedFile(path, json.dumps(settings, indent=2) + "\n")


def _skill_sources(root: Path) -> tuple[list[Path], list[str]]:
    aitna = aitna_root(root)
    search_roots = (
        standard_tree_root(root) / "skills",
        aitna / "skills",
        root / "skills",
    )
    sources: list[Path] = []
    errors: list[str] = []
    names: dict[str, Path] = {}
    for search_root in search_roots:
        if not search_root.is_dir():
            continue
        for source in sorted(search_root.glob("*/SKILL.md")):
            name = source.parent.name
            if name in names:
                errors.append(f"duplicate skill name {name!r}: {names[name]} and {source}")
                continue
            names[name] = source
            sources.append(source)
    return sources, errors


def _claude_skill_stub(root: Path, source: Path) -> PlannedFile:
    """A pointer to one skill's source.

    A relative link whenever the source is in the repository — the project's own skills, and
    every mounted mode. When it is not (mode ``package``: the source is inside the installed
    wheel), the relative link would spell ``../../../.venv/lib/python3.13/site-packages/...``
    and be committed: a path carrying the venv's Python version, wrong on the next bump and on
    any differently laid out environment. ADR 0009 §4 already answers that for package-mode
    docs — reach the standard through ``akmon path``, not through a path that is not there.
    """
    name = source.parent.name
    path = root / ".claude" / "skills" / name / "SKILL.md"
    try:
        source.relative_to(root)
        in_repo = True
    except ValueError:
        in_repo = False
    if in_repo:
        relative_source = os.path.relpath(source, path.parent).replace(os.sep, "/")
        pointer = f"Source skill: [{relative_source}]({relative_source})"
    else:
        pointer = f"Source skill: `$({_CLI_NAME} path)/skills/{name}/SKILL.md`"
    content = f"""# {name}

<!-- {generated_banner()} -->

{pointer}

Read and follow the source SKILL.md. Do not duplicate its contents here.
"""
    return PlannedFile(path, content)


# Fenced blocks first, then inline code spans: the akmon block in AGENTS.md *documents* the
# guardrail import as well as making it ("add this project's language guardrail on its own
# line (e.g. `@_aitna/.akmon/guardrails/python.md`)"), and read literally the example is
# indistinguishable from the real thing. Code spans are exactly where prose quotes a path it
# does not mean, so stripping them separates the two without requiring a real import to sit in
# any particular column.
_FENCED_BLOCK_RE = re.compile(r"^(?P<fence>```|~~~).*?(?:^(?P=fence)[^\n]*$|\Z)", re.MULTILINE | re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")

# The common guardrail is materialized whether or not the scan finds its import: it is the
# anchor ``verify`` requires of a package-mode AGENTS.md, so its absence is a finding about
# AGENTS.md, not a licence to ship the consumer a broken import target.
_ALWAYS_MATERIALIZED_GUARDRAIL = "_common.md"


def imported_guardrails(root: Path) -> tuple[list[str], list[str]]:
    """Guardrail file names the consumer's ``AGENTS.md`` actually ``@``-imports, and any plan
    errors. Read from the document rather than derived from the recorded archetype: the
    language guardrail is a line a human adds by hand (``init`` says so in as many words), an
    archetype-driven list would miss it, and it would ship files to a project whose archetype
    is still ``<archetype>``.
    """
    text_path = root / "AGENTS.md"
    names = {_ALWAYS_MATERIALIZED_GUARDRAIL}
    if text_path.is_file():
        text = _INLINE_CODE_RE.sub(" ", _FENCED_BLOCK_RE.sub("\n", text_path.read_text(encoding="utf-8")))
        prefix = re.escape(f"@{aitna_root_name()}/.akmon/guardrails/")
        names.update(re.findall(prefix + r"([A-Za-z0-9._-]+)", text))
    source = standard_tree_root(root) / "guardrails"
    errors = [
        f"AGENTS.md imports a guardrail the standard does not ship: guardrails/{name}"
        for name in sorted(names)
        if not (source / name).is_file()
    ]
    return sorted(names), errors


def _materialized_files(root: Path) -> tuple[list[PlannedFile], list[str]]:
    """Package-mode materialization (ADR 0009 §4, narrowed by C77): the guardrails the
    consumer's ``AGENTS.md`` imports, and nothing else.

    Nothing executable is copied any more. The hooks, the ``common`` package they import, the
    routing library and its registry are already installed beside the consumer, inside the
    wheel, and ``akmon hook`` runs them from there — a second copy in the repository was never
    a second implementation, only ~20 files of the standard rewritten into the project's
    history on every version bump.

    The guardrails are the one exception, and the reason is the *path*, not containment. The
    import lives in ``AGENTS.md``: a committed, hand-owned file shared by every developer, and
    the only path from there into the package carries the venv's Python version
    (``.venv/lib/python3.14/site-packages/...``) — the exact string C77 took out of the wiring.
    Claude's import syntax would follow an absolute path; it simply cannot be written down once
    and stay true. And it fails harder than the wiring did: a hook command with a missing
    executable at least runs, while an unresolved ``@``-import produces no diagnostic anywhere.
    Codex does not expand the import at all (it reads ``AGENTS.md`` literally — see
    ``meta/design/codex-runtime-contract.md``), so the copy serves the one harness that does.

    A no-op outside package mode.
    """
    if not is_package_mode(root):
        return [], []
    names, errors = imported_guardrails(root)
    source = standard_tree_root(root) / "guardrails"
    dest = aitna_root(root) / ".akmon" / "guardrails"
    files = [
        PlannedFile(
            dest / name,
            materialized_markdown((source / name).read_text(encoding="utf-8")),
        )
        for name in names
        if (source / name).is_file()
    ]
    return files, errors


def _upsert_toml_key(text: str, key: str, value: str) -> str:
    """Set a top-level ``key = "value"`` line in TOML-ish ``text``, preserving everything
    else verbatim (comments, other keys, ``[section]``s).

    Updates an existing top-level (pre-first-``[section]``) line for ``key`` in place; else
    inserts one just before the first ``[section]`` header (or appends at the end if none).
    A minimal, comment-preserving alternative to a full parse+rewrite — ``.akmon.toml`` mixes
    tool-written fields (``mount``, ``akmon_version``, and ``last_realign`` — the last written
    by ``_init._mark_realign_complete`` once every stage has succeeded, never here) with
    hand-written ones (``attached_archetype``, ``[test]``…) that a full round-trip would risk
    losing.
    """
    lines = text.splitlines()
    new_line = f'{key} = "{value}"'
    section_index = next((i for i, line in enumerate(lines) if line.strip().startswith("[")), None)
    top_lines = lines[:section_index] if section_index is not None else lines
    for i, line in enumerate(top_lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        found_key, sep, _ = stripped.partition("=")
        if sep and found_key.strip() == key:
            lines[i] = new_line
            break
    else:
        insert_at = section_index if section_index is not None else len(lines)
        lines[insert_at:insert_at] = [new_line]
    trailing_newline = "\n" if text.endswith("\n") or not text else ""
    return "\n".join(lines) + trailing_newline


def _installed_akmon_version() -> str | None:
    """The installed ``akmon`` package's version, via metadata lookup only (no import of the
    ``akmon`` package itself — bin/ must stay standalone-runnable with zero dependency on
    ``akmon`` being importable, e.g. when this file is the mounted-submodule copy with no
    package installed at all). ``None`` when not installed (mounted modes, or a raw
    embedded/editable checkout with no ``pip``/``uv`` install)."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("akmon")
    except PackageNotFoundError:
        return None


def _package_mode_akmon_toml(root: Path) -> PlannedFile | None:
    """Package-mode ``.akmon.toml`` stamping (ADR 0009 §4): the installed package version *is*
    the pin, so sync keeps ``akmon_version`` in sync with reality on every run. Only the
    ``mount``/``akmon_version`` keys are touched; every other field is preserved verbatim (see
    ``_upsert_toml_key``). ``None`` outside package mode, when the record does not exist yet
    (``init`` creates it), or when the installed version cannot be determined.

    **Stamping the pin is not a realign**, and this function must not be read as one. It moves
    the recorded pin while ``last_realign`` and the model-routing binding stay where the last
    completed realign left them. ``sync`` owns generated pointers, vendor wiring and imported
    guardrails. An existing AGENTS.md block and existing CI workflows are hand-owned: ``init``
    preserves them and reports any manual next steps instead of rewriting them. A package-mode
    bump therefore runs ``init`` before ``sync`` (BOOTSTRAP §E), and the gap between the two
    recorded versions is an error in ``verify`` (``verify.py::_check_realign_freshness``) rather
    than a silent success here.
    """
    if not is_package_mode(root):
        return None
    version = _installed_akmon_version()
    if version is None:
        return None
    path = aitna_root(root) / ".akmon.toml"
    if not path.is_file():
        return None
    text = _upsert_toml_key(path.read_text(encoding="utf-8"), "mount", "package")
    text = _upsert_toml_key(text, "akmon_version", version)
    return PlannedFile(path, text)


def _codex_hooks_text(root: Path) -> str:
    """The exact text ``.codex/hooks.json`` is generated with.

    One spelling for both readers: the plan below writes it, and ``verify``'s C70 host-trust
    check compares the file against it before parsing anything, so "current wiring" there means
    byte-for-byte what ``sync --check`` means by it.
    """
    return json.dumps(_codex_hooks(root), indent=2) + "\n"


def _planned_files(root: Path) -> tuple[list[PlannedFile], list[str]]:
    errors: list[str] = []
    files = [
        PlannedFile(root / "CLAUDE.md", _claude_md()),
        PlannedFile(root / ".github" / "copilot-instructions.md", _copilot_md()),
        PlannedFile(root / "GEMINI.md", _gemini_md()),
        PlannedFile(root / ".codex" / "README.md", _codex_readme()),
        PlannedFile(root / ".codex" / "hooks.json", _codex_hooks_text(root)),
    ]
    try:
        files.append(_claude_settings(root))
    except ValueError as exc:
        errors.append(str(exc))
    sources, skill_errors = _skill_sources(root)
    errors.extend(skill_errors)
    files.extend(_claude_skill_stub(root, source) for source in sources)
    materialized, materialization_errors = _materialized_files(root)
    files.extend(materialized)
    errors.extend(materialization_errors)
    toml_plan = _package_mode_akmon_toml(root)
    if toml_plan is not None:
        files.append(toml_plan)
    return files, errors


_BYTECODE_CACHE_DIR = "__pycache__"


def materialization_root(root: Path) -> Path:
    """``<AITNA_ROOT>/.akmon`` — the one directory this tool owns outright."""
    return aitna_root(root) / ".akmon"


def _obsolete_generated_files(root: Path, files: list[PlannedFile]) -> list[Path]:
    """Generated files present on disk that the current plan no longer wants.

    Two directories, two recognition rules, and the difference is deliberate. Under
    ``.claude/skills/`` the project keeps its **own** skills beside ours, so only a file
    carrying the generated banner is ours to delete. Under ``<AITNA_ROOT>/.akmon/`` nobody
    writes but us, so everything unplanned is stale **whether or not it carries a banner** —
    which is load-bearing rather than tidy: the materialized routing registry never carried one
    (it has to stay parseable JSON), so a banner-only sweep would leave exactly that file
    behind forever.
    """
    planned_paths = {planned.path for planned in files}
    obsolete: list[Path] = []

    skills_dir = root / ".claude" / "skills"
    if skills_dir.is_dir():
        for path in sorted(skills_dir.glob("*/SKILL.md")):
            if path in planned_paths:
                continue
            if GENERATED_MARKER in path.read_text(encoding="utf-8"):
                obsolete.append(path)

    materialization = materialization_root(root)
    if materialization.is_dir():
        for path in sorted(materialization.rglob("*")):
            if path.is_dir() or path in planned_paths:
                continue
            if _BYTECODE_CACHE_DIR in path.parts:
                continue  # swept separately and silently — see _sweep_materialization_bytecode
            obsolete.append(path)
    return obsolete


def _sweep_materialization_bytecode(root: Path) -> None:
    """Delete ``__pycache__`` under the materialization — silently, and before the deletions.

    Any project that has ever *run* a materialized hook has bytecode beside it. Deleting the
    source files leaves that cache untouched, so the directories survive the migration and the
    tree this change exists to remove stays in the repository, unread and uncomplained-about.

    Silent because ``sync --check`` must not fail a project for having executed a hook since
    the last sync — that is not drift. Before the deletion loop because only then do the parent
    directories actually empty and get pruned. Nothing regenerates it: the hooks now execute
    inside the wheel and cache beside it.
    """
    materialization = materialization_root(root)
    if not materialization.is_dir():
        return
    for cache in sorted(materialization.rglob(_BYTECODE_CACHE_DIR), reverse=True):
        if not cache.is_dir():
            continue
        for entry in sorted(cache.iterdir()):
            if entry.is_file() and entry.suffix in (".pyc", ".pyo"):
                entry.unlink()
        try:
            cache.rmdir()
        except OSError:
            pass


def _prune_stop(root: Path, path: Path) -> Path:
    """How far up to prune emptied directories after deleting ``path``.

    ``<AITNA_ROOT>`` for the materialization, so ``.akmon`` itself disappears once its last
    file is gone; the skills directory otherwise.
    """
    try:
        path.relative_to(materialization_root(root))
    except ValueError:
        return root / ".claude" / "skills"
    return aitna_root(root)


def _remove_empty_parents(path: Path, stop: Path) -> None:
    current = path.parent
    while current != stop and current.is_dir():
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _apply(files: list[PlannedFile], *, write: bool, root: Path | None = None) -> Result:
    result = Result(changed=[], deleted=[], ok=[], errors=[])
    for planned in files:
        current = planned.path.read_text(encoding="utf-8") if planned.path.exists() else None
        if current == planned.content:
            result.ok.append(planned.path)
            continue
        result.changed.append(planned.path)
        if write:
            planned.path.parent.mkdir(parents=True, exist_ok=True)
            planned.path.write_text(planned.content, encoding="utf-8")
    if root is not None:
        if write:
            _sweep_materialization_bytecode(root)
        for path in _obsolete_generated_files(root, files):
            result.deleted.append(path)
            if write:
                path.unlink()
                _remove_empty_parents(path, _prune_stop(root, path))
    return result


def _check_findings(result: Result, *, root: Path) -> list[Finding]:
    """``--check``'s observations as the shared envelope (C51).

    Only the non-writing ``--check`` mode speaks findings: ``--dry-run`` and a real write
    print an action log, because "updated this file" is a record of what happened, not a
    diagnostic about the tree. This is the stream ``akmon status`` consumes (F22).
    """
    findings: list[Finding] = []
    for path in result.changed:
        relative = str(path.relative_to(root))
        findings.append(
            Finding(
                "error",
                "sync.stale-generated",
                line_safe(f"generated file is stale or missing: {relative}"),
                line_safe(relative),
                "Run akmon sync to regenerate this file.",
            )
        )
    for path in result.deleted:
        relative = str(path.relative_to(root))
        findings.append(
            Finding(
                "error",
                "sync.obsolete-generated",
                line_safe(f"generated file is no longer planned: {relative}"),
                line_safe(relative),
                "Run akmon sync to delete this file.",
            )
        )
    for path in result.ok:
        relative = str(path.relative_to(root))
        findings.append(
            Finding(
                "ok",
                "sync.up-to-date",
                line_safe(f"generated file matches its source: {relative}"),
                line_safe(relative),
                "Re-run akmon sync after every change to this file's source.",
            )
        )
    for error in result.errors:
        findings.append(
            Finding(
                "error",
                "sync.plan-error",
                line_safe(error),
                "",
                "Resolve the reported planning error, then re-run akmon sync.",
            )
        )
    return findings


def _print_summary(result: Result, *, root: Path, mode: str) -> None:
    """The action log for the writing modes: ``dry-run`` and a real write (``--check`` speaks
    findings instead, see :func:`_check_findings`)."""
    for path in result.changed:
        rel = path.relative_to(root)
        action = "would update" if mode == "dry-run" else "updated"
        print(f"{action}: {rel}")
    for path in result.deleted:
        rel = path.relative_to(root)
        action = "would delete" if mode == "dry-run" else "deleted"
        print(f"{action}: {rel}")
    for path in result.ok:
        print(f"ok: {path.relative_to(root)}")
    for error in result.errors:
        print(f"error: {error}", file=sys.stderr)
    if not result.changed and not result.deleted and not result.errors:
        print("akmon sync: no changes")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, help="Project root. Defaults to cwd or a parent with AGENTS.md.")
    parser.add_argument("--check", action="store_true", help="Do not write; exit 1 when generated files are stale.")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing them.")
    args = parser.parse_args(argv)

    if args.check and args.dry_run:
        parser.error("--check and --dry-run are mutually exclusive")

    root, root_notice = resolve_project_root(args.project_root)
    if root_notice:
        print(root_notice, file=sys.stderr)
    files, errors = _planned_files(root)
    write = not args.check and not args.dry_run
    result = _apply(files, write=write, root=root)
    result.errors.extend(errors)

    if args.check:
        print_findings(_check_findings(result, root=root))
    else:
        _print_summary(result, root=root, mode="dry-run" if args.dry_run else "write")
    # `sync` keeps its own exit vocabulary rather than the envelope's `exit_code`, by owner
    # decision at C51: 2 separates "could not even plan the files" from 1's "the plan and the
    # tree disagree", and no `--strict` exists here because nothing in this stream warns.
    if result.errors:
        return 2
    if args.check and (result.changed or result.deleted):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
