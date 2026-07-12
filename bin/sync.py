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
import sys
from dataclasses import dataclass
from pathlib import Path

# The dev-layer (LOCAL) root is configurable: ``_aitna`` is the default, but a project may
# relocate it by declaring ``AITNA_ROOT`` (a project-root-relative path, e.g. ``tools/ai``).
# akmon is always mounted at ``<aitna-root>/akmon``. Every generated pointer and hook
# command is templated from this one resolver instead of hard-coding ``_aitna/``.
_AITNA_ROOT_DEFAULT = "_aitna"


def aitna_root_name() -> str:
    """The configured dev-layer root, as a project-root-relative POSIX path (default ``_aitna``)."""
    return (os.environ.get("AITNA_ROOT") or _AITNA_ROOT_DEFAULT).strip("/") or _AITNA_ROOT_DEFAULT


def aitna_root(project_root: Path) -> Path:
    """Absolute dev-layer root for ``project_root`` (``<project_root>/<AITNA_ROOT>``)."""
    return project_root / aitna_root_name()


def akmon_root(project_root: Path) -> Path:
    """Absolute akmon mount for ``project_root`` (``<aitna-root>/akmon``)."""
    return aitna_root(project_root) / "akmon"


# This file's own tree root (``bin/``'s parent) — in a mounted checkout that is the mount
# itself; in package mode it is whatever copy of the standard is actually running this
# script (an installed wheel's embedded ``akmon/_tree``, or a plain source checkout during
# akmon's own development). A plain ``Path(__file__)`` derivation, not ``importlib.resources``
# or an import of the ``akmon`` package: bin/ must stay runnable standalone
# (``python3 <tree>/bin/sync.py``) in mounted mode, where no Python package is installed at
# all (ADR 0009 §4).
_TREE_ROOT = Path(__file__).resolve().parent.parent


def read_akmon_toml(path: Path) -> dict:
    """Read ``_aitna/.akmon.toml`` (the integration record) into a nested dict.

    Uses ``tomllib`` when present (Python 3.11+); else a minimal stdlib fallback for the subset
    the record uses — flat ``key = "value"`` lines, ``[section]`` headers, ``#`` comments — so the
    reader stays stdlib-only and works on a consumer host with an older Python (the contract checks
    must not assume 3.11). Quotes are stripped; values are treated as strings. Returns ``{}`` if the
    file is absent or unreadable."""
    if not path.is_file():
        return {}
    try:
        import tomllib

        with path.open("rb") as handle:
            return tomllib.load(handle)
    except ImportError:
        pass
    data: dict = {}
    section = data
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = data.setdefault(stripped[1:-1].strip(), {})
            continue
        key, sep, value = stripped.partition("=")
        if not sep:
            continue
        section[key.strip()] = value.strip().strip('"').strip("'")
    return data


def read_mount_mode(project_root: Path) -> str:
    """The recorded ``mount`` value from ``<AITNA_ROOT>/.akmon.toml`` (ADR 0009 §3):
    ``"submodule" | "vendored" | "subtree" | "package"``. An absent record or key defaults
    to ``"submodule"`` — the traditional mounted-tree default, kept for backward
    compatibility with every project that predates this field.
    """
    fields = read_akmon_toml(aitna_root(project_root) / ".akmon.toml")
    return fields.get("mount") or "submodule"


def is_package_mode(project_root: Path) -> bool:
    """Whether ``project_root`` is governed by mount mode ``package`` (ADR 0009 §4).

    Driven solely by the recorded ``.akmon.toml`` ``mount`` field, never by whether
    ``<AITNA_ROOT>/akmon`` happens to exist on disk: a stale mount directory left over from
    a prior mode must not shadow a project that has since switched to package mode (and,
    symmetrically, an absent record must not be misread as package mode just because no
    mount exists yet — see ``read_mount_mode``'s backward-compatible default).
    """
    return read_mount_mode(project_root) == "package"


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


def _generated_banner() -> str:
    """The do-not-edit banner; tracks the configured root so it never drifts from real paths."""
    return f"Generated by {aitna_root_name()}/akmon/bin/sync.py. Do not edit this file by hand."


# Stable substring used to recognise a generated file regardless of the configured root —
# verify/sync look for this prefix, not the full banner (which embeds the root path).
GENERATED_MARKER = "Generated by "


def _claude_md() -> str:
    return f"""# CLAUDE.md

<!-- {_generated_banner()} -->

This project uses **[AGENTS.md](AGENTS.md)** as the single source of guidance for AI
coding agents (including Claude Code).

Claude Code auto-loads `CLAUDE.md` but **not** `AGENTS.md`, so AGENTS.md is imported below.
This keeps the canonical rules, including the always-on prime directives and "read
`{aitna_root_name()}/memory/` at session start", present in context from the start.

@AGENTS.md
"""


def _copilot_md() -> str:
    return f"""# Copilot Instructions

<!-- {_generated_banner()} -->

This project uses **[AGENTS.md](../AGENTS.md)** as the single source of guidance for AI
coding agents, including GitHub Copilot.

See [AGENTS.md](../AGENTS.md) for the project overview, environment setup, architecture,
commands, testing, and conventions.
"""


def _gemini_md() -> str:
    return f"""# GEMINI.md

<!-- {_generated_banner()} -->

This project uses [AGENTS.md](AGENTS.md) as the single source of guidance for AI coding
agents, including Gemini.

Read AGENTS.md before doing project work.
"""


def _codex_readme() -> str:
    return f"""# Codex

<!-- {_generated_banner()} -->

Codex uses the project root [AGENTS.md](../AGENTS.md) as the single source of guidance.
This directory contains generated hook wiring and pointers only; do not duplicate project
instructions here.
"""


# The hooks dir lives under the configured dev-layer root; the leading project-root anchor is
# vendor-specific (Codex: git toplevel · Claude: $CLAUDE_PROJECT_DIR). Both are templated below.
def _hooks_dir(root: Path) -> str:
    """``<aitna-root>/akmon/hooks`` (mounted modes) or ``<aitna-root>/.akmon/hooks``
    (package mode — the materialization destination, ADR 0009 §4), as a POSIX suffix
    appended after a vendor's root anchor."""
    aitna = aitna_root_name()
    if is_package_mode(root):
        return f"{aitna}/.akmon/hooks"
    return f"{aitna}/akmon/hooks"


# Both possible hook-dir markers (mounted + package mode), independent of the project's
# *current* mode: recognising an entry as akmon-managed must not depend on which mode wrote
# it, so switching modes drops the other mode's stale entries instead of leaving them
# unrecognised and orphaned (ADR 0009 §4).
def _akmon_hook_markers() -> tuple[str, str]:
    aitna = aitna_root_name()
    return (f"{aitna}/akmon/hooks/", f"{aitna}/.akmon/hooks/")


def _codex_hook_command(root: Path) -> str:
    return f'python3 "$(git rev-parse --show-toplevel)/{_hooks_dir(root)}/codex-hook.py"'


def _codex_hooks(root: Path) -> dict:
    base = _codex_hook_command(root)
    return {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Edit|Write|apply_patch",
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
    hooks_dir = _hooks_dir(root)

    def cmd(script: str) -> str:
        return f'python3 "$CLAUDE_PROJECT_DIR/{hooks_dir}/{script}"'

    return {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": cmd("git-commit-guard.py")}],
                },
                {
                    "matcher": "Edit|Write|MultiEdit",
                    "hooks": [
                        {"type": "command", "command": cmd("role-on-code.py")},
                        {"type": "command", "command": cmd("analysis-guard.py")},
                        {"type": "command", "command": cmd("d2-ledger-reminder.py")},
                    ],
                },
                {
                    "matcher": "Task|Agent",
                    "hooks": [{"type": "command", "command": cmd("delegation-log.py")}],
                },
                {
                    # One entry with a combined matcher: _merge_hook_entries dedups by
                    # command, so the same script must not ride several matcher groups.
                    # Read|Grep|Glob are included so the nudge/ask also see read/sweep drift,
                    # not just edit/shell (guardrails/_common.md § Route by task kind).
                    "matcher": "Bash|Edit|Write|MultiEdit|Task|Agent|Read|Grep|Glob",
                    "hooks": [{"type": "command", "command": cmd("delegation-nudge.py")}],
                },
            ],
            "SessionStart": [
                {
                    "hooks": [
                        {"type": "command", "command": cmd("session-start-agent.py")},
                        {"type": "command", "command": cmd("model-routing.py")},
                    ]
                }
            ],
            # Per-turn: model-routing re-detects the orchestrator from the transcript and
            # rebinds subagents when a mid-session /model switch lands (silent otherwise).
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {"type": "command", "command": cmd("model-routing.py")},
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


def _find_project_root(start: Path) -> Path:
    """Walk up from ``start`` for a project ``AGENTS.md`` plus either a mounted tree
    (``<AITNA_ROOT>/akmon``) or an integration record (``<AITNA_ROOT>/.akmon.toml`` —
    the only marker package-mode projects have, since they carry no mounted tree at all;
    ADR 0009 §4)."""
    for candidate in (start, *start.parents):
        if not (candidate / "AGENTS.md").is_file():
            continue
        aitna = aitna_root(candidate)
        if (aitna / "akmon").exists() or (aitna / ".akmon.toml").is_file():
            return candidate
    return start


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
    name = source.parent.name
    path = root / ".claude" / "skills" / name / "SKILL.md"
    relative_source = os.path.relpath(source, path.parent).replace(os.sep, "/")
    content = f"""# {name}

<!-- {_generated_banner()} -->

Source skill: [{relative_source}]({relative_source})

Read and follow the source SKILL.md. Do not duplicate its contents here.
"""
    return PlannedFile(path, content)


def _materialized_python_content(source_text: str) -> str:
    """``source_text`` with the generated-pointer banner inserted as a ``#`` comment.

    Placed right after a leading shebang line when present (keeping the materialized copy
    directly executable via ``python3 <path>``, with no venv — the same property the
    mounted tree gives today, ADR 0009 §4), else at the very top.
    """
    banner_line = f"# {_generated_banner()}"
    lines = source_text.splitlines(keepends=True)
    if lines and lines[0].startswith("#!"):
        return lines[0] + banner_line + "\n" + "".join(lines[1:])
    return banner_line + "\n" + source_text


def _materialized_markdown_content(source_text: str) -> str:
    """``source_text`` with the generated-pointer banner inserted as an HTML comment
    (matching the convention the other generated ``.md`` pointers already use), right after
    a leading top-level heading when present, else at the very top.
    """
    banner_line = f"<!-- {_generated_banner()} -->"
    lines = source_text.splitlines(keepends=True)
    if lines and lines[0].lstrip().startswith("#"):
        return lines[0] + banner_line + "\n\n" + "".join(lines[1:])
    return banner_line + "\n\n" + source_text


def _materialized_files(root: Path) -> list[PlannedFile]:
    """Package-mode materialization (ADR 0009 §4): the always-on surface and every
    stdlib-only runtime dependency of its hooks, copied into ``<AITNA_ROOT>/.akmon/``.

    Python and Markdown files carry the generated banner. JSON must remain parseable, but is
    still drift-checked because it is part of the planned file set. A no-op outside package mode.
    """
    if not is_package_mode(root):
        return []
    source = standard_tree_root(root)
    dest = aitna_root(root) / ".akmon"
    files: list[PlannedFile] = []

    hooks_source = source / "hooks"
    if hooks_source.is_dir():
        for hook_path in sorted(hooks_source.glob("*.py")):
            content = _materialized_python_content(hook_path.read_text(encoding="utf-8"))
            files.append(PlannedFile(dest / "hooks" / hook_path.name, content))

    guardrails_source = source / "guardrails"
    if guardrails_source.is_dir():
        for guardrail_path in sorted(p for p in guardrails_source.iterdir() if p.is_file()):
            content = _materialized_markdown_content(guardrail_path.read_text(encoding="utf-8"))
            files.append(PlannedFile(dest / "guardrails" / guardrail_path.name, content))

    runtime_files = (
        *sorted((source / "tools" / "model_routing").glob("*.py")),
        source / "tools" / "model_routing" / "registry.json",
        source / "tools" / "d2_ledger" / "d2_ledger.py",
    )
    for runtime_path in runtime_files:
        if not runtime_path.is_file():
            continue
        relative = runtime_path.relative_to(source)
        source_text = runtime_path.read_text(encoding="utf-8")
        content = (
            _materialized_python_content(source_text)
            if runtime_path.suffix == ".py"
            else source_text
        )
        files.append(PlannedFile(dest / relative, content))

    return files


def _upsert_toml_key(text: str, key: str, value: str) -> str:
    """Set a top-level ``key = "value"`` line in TOML-ish ``text``, preserving everything
    else verbatim (comments, other keys, ``[section]``s).

    Updates an existing top-level (pre-first-``[section]``) line for ``key`` in place; else
    inserts one just before the first ``[section]`` header (or appends at the end if none).
    A minimal, comment-preserving alternative to a full parse+rewrite — ``.akmon.toml`` mixes
    generated fields (this one) with hand-written ones (``attached_archetype``,
    ``last_realign``, ``[test]``…) that a full round-trip would risk losing.
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
    """Package-mode ``.akmon.toml`` stamping (ADR 0009 §4): the installed package version
    *is* the pin (no separate realign step the way a submodule pin-bump needs one), so sync
    keeps ``akmon_version`` in sync with reality on every run. Only the ``mount``/
    ``akmon_version`` keys are touched; every other field is preserved verbatim (see
    ``_upsert_toml_key``). ``None`` outside package mode, when the record does not exist yet
    (``init`` — a later slice — creates it), or when the installed version cannot be
    determined.
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


def _planned_files(root: Path) -> tuple[list[PlannedFile], list[str]]:
    errors: list[str] = []
    files = [
        PlannedFile(root / "CLAUDE.md", _claude_md()),
        PlannedFile(root / ".github" / "copilot-instructions.md", _copilot_md()),
        PlannedFile(root / "GEMINI.md", _gemini_md()),
        PlannedFile(root / ".codex" / "README.md", _codex_readme()),
        PlannedFile(root / ".codex" / "hooks.json", json.dumps(_codex_hooks(root), indent=2) + "\n"),
    ]
    try:
        files.append(_claude_settings(root))
    except ValueError as exc:
        errors.append(str(exc))
    sources, skill_errors = _skill_sources(root)
    errors.extend(skill_errors)
    files.extend(_claude_skill_stub(root, source) for source in sources)
    files.extend(_materialized_files(root))
    toml_plan = _package_mode_akmon_toml(root)
    if toml_plan is not None:
        files.append(toml_plan)
    return files, errors


def _obsolete_generated_files(root: Path, files: list[PlannedFile]) -> list[Path]:
    planned_paths = {planned.path for planned in files}
    skills_dir = root / ".claude" / "skills"
    if not skills_dir.is_dir():
        return []

    obsolete: list[Path] = []
    for path in sorted(skills_dir.glob("*/SKILL.md")):
        if path in planned_paths:
            continue
        text = path.read_text(encoding="utf-8")
        if GENERATED_MARKER in text:
            obsolete.append(path)
    return obsolete


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
        for path in _obsolete_generated_files(root, files):
            result.deleted.append(path)
            if write:
                path.unlink()
                _remove_empty_parents(path, root / ".claude" / "skills")
    return result


def _print_summary(result: Result, *, root: Path, mode: str) -> None:
    for path in result.changed:
        rel = path.relative_to(root)
        action = "would update" if mode in {"check", "dry-run"} else "updated"
        print(f"{action}: {rel}")
    for path in result.deleted:
        rel = path.relative_to(root)
        action = "would delete" if mode in {"check", "dry-run"} else "deleted"
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

    root = (args.project_root or _find_project_root(Path.cwd())).resolve()
    files, errors = _planned_files(root)
    write = not args.check and not args.dry_run
    result = _apply(files, write=write, root=root)
    result.errors.extend(errors)

    mode = "check" if args.check else "dry-run" if args.dry_run else "write"
    _print_summary(result, root=root, mode=mode)
    if result.errors:
        return 2
    if args.check and (result.changed or result.deleted):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
