"""Vendor-neutral keystone hook decisions.

This module contains the guardrail logic only. Vendor entrypoints adapt their incoming
payload and serialize ``HookResult`` into the shape their runtime expects.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

# The dev-layer (LOCAL) root is configurable: ``_forge`` is the default, but a project may
# relocate it by declaring ``FORGE_ROOT`` (a path relative to the project root, e.g.
# ``tools/ai``). keystone is always mounted at ``<forge-root>/keystone``. Tooling derives every
# dev-layer path from this one resolver instead of hard-coding ``_forge/``.
_FORGE_ROOT_DEFAULT = "_forge"


def forge_root_name() -> str:
    """The configured dev-layer root, as a project-root-relative POSIX path (default ``_forge``)."""
    return (os.environ.get("FORGE_ROOT") or _FORGE_ROOT_DEFAULT).strip("/") or _FORGE_ROOT_DEFAULT


def forge_root(project_root: Path) -> Path:
    """Absolute dev-layer root for ``project_root`` (``<project_root>/<FORGE_ROOT>``)."""
    return project_root / forge_root_name()


def keystone_root(project_root: Path) -> Path:
    """Absolute keystone mount for ``project_root`` (``<forge-root>/keystone``)."""
    return forge_root(project_root) / "keystone"


@dataclass(frozen=True)
class HookResult:
    event_name: str
    additional_context: str | None = None
    permission_decision: str | None = None
    permission_reason: str | None = None


_CODE_EXTENSIONS = frozenset(
    {
        ".py",
        ".pyi",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".go",
        ".rs",
        ".java",
        ".rb",
        ".c",
        ".h",
        ".cpp",
        ".cc",
        ".hpp",
        ".cs",
        ".swift",
        ".kt",
        ".scala",
        ".php",
        ".sh",
        ".bash",
        ".zsh",
        ".sql",
        ".r",
        ".jl",
        ".lua",
        ".dart",
        ".m",
        ".mm",
    }
)
# Path-classification segments are derived from the configured dev-layer root (default
# ``_forge``) so relocating it via FORGE_ROOT keeps the code/planning-doc detection correct.
# These match lowercased path *substrings*, so the segment uses the lowercased root name.
def _non_code_segments() -> tuple[str, ...]:
    forge = forge_root_name().lower()
    return ("/docs/", f"/{forge}/design/", f"/{forge}/memory/", f"/{forge}/keystone/", "/.claude/")


# Neutral tool-kind: each vendor adapter normalizes its own file-editing tool name(s) to this
# token before calling. The core stays vendor-clean — it never names a vendor's tools.
EDIT_TOOL = "edit"
_EDIT_TOOL_KINDS = frozenset({EDIT_TOOL})


# Planning / design docs — editing one may be an analysis-only turn that needs confirmation
# first (see guardrails/_common.md § Analysis before mutation).
def _planning_doc_segments() -> tuple[str, ...]:
    forge = forge_root_name().lower()
    return (f"/{forge}/design/", "/docs/dev/", f"/{forge}/keystone/")


def _planning_doc_files() -> tuple[str, ...]:
    forge = forge_root_name().lower()
    return (f"/{forge}/tasks.md", f"/{forge}/tasks_archive.md")


def current_git_branch() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def find_project_root(start: Path | None = None) -> Path:
    """Walk up from ``start`` (or cwd) to the first dir holding AGENTS.md + <forge-root>/keystone."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "AGENTS.md").is_file() and keystone_root(candidate).exists():
            return candidate
    return current


def git_commit_guard_result(command: str, branch: str | None = None) -> HookResult | None:
    if "git" not in command:
        return None

    if re.search(r"co-authored-by", command, re.IGNORECASE):
        return HookResult(
            event_name="PreToolUse",
            permission_decision="deny",
            permission_reason="Commit guardrail: no AI 'Co-Authored-By' trailer — the committer is "
            "the human. Remove it and retry.",
        )

    def is_git(subcommand: str) -> bool:
        return re.search(r"\bgit\b[^|&;]*\b" + subcommand + r"\b", command) is not None

    if is_git("push") or is_git("tag") or is_git("merge"):
        return HookResult(
            event_name="PreToolUse",
            permission_decision="ask",
            permission_reason="Commit guardrail: the owner owns commits. push/tag/merge land history "
            "— confirm this is explicitly requested.",
        )

    if is_git("commit"):
        resolved_branch = current_git_branch() if branch is None else branch
        if resolved_branch in ("main", "master") or not resolved_branch:
            return HookResult(
                event_name="PreToolUse",
                permission_decision="ask",
                permission_reason=f"Commit guardrail: the owner owns commits. A commit on "
                f"'{resolved_branch or 'detached HEAD'}' is a landing commit — confirm "
                "explicitly, or branch to backup/* first.",
            )

    return None


def agent_names(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    return sorted(
        item.name
        for item in directory.iterdir()
        if item.is_dir() and not item.name.startswith(".") and (item / "README.md").is_file()
    )


def session_start_result(root: Path) -> HookResult | None:
    dev = agent_names(forge_root(root) / "agents")
    desk = agent_names(root / "agents")
    if not dev and not desk:
        return None

    lines = [
        "[keystone] Active-agent declaration",
        "Before doing project work, state which agent you are operating as, and restate it "
        "whenever you switch. Format: `\U0001f9ed agent: <name> — <focus>`.",
    ]
    if dev:
        lines.append(f"- DEVELOP (build the project): {', '.join(dev)}")
    if desk:
        lines.append(f"- OPERATE (run/use from outside): {', '.join(desk)}")
    lines.append("No agent is active yet.")
    if dev:
        # The DEVELOP routing discriminator (ADR 0003 §4): give the picking rule up front, not
        # only after a code/planning edit already happened. Keyed by cognitive operation.
        lines.append(
            "Pick by operation: decompose an existing thing → review · construct a new "
            "structure/decision → architect · realize a decided structure in code → engineer. "
            "If unclear, ask."
        )
    else:
        lines.append("Pick the one the task calls for; if unclear, ask.")
    lines.append(f"Also: read `{forge_root_name()}/memory/` at session start (project memory).")
    return HookResult(event_name="SessionStart", additional_context="\n".join(lines))


def is_code_path(file_path: str) -> bool:
    lowered = file_path.replace("\\", "/").lower()
    if any(segment in lowered for segment in _non_code_segments()):
        return False
    return Path(lowered).suffix in _CODE_EXTENSIONS


def role_on_code_message() -> str:
    tasks = f"{forge_root_name()}/TASKS.md"
    return (
        "[keystone] Role check — you are editing project code.\n"
        "Editing code is **realization** → the `engineer` role. Discriminator: decompose an "
        "existing thing → `review` · construct a new structure/decision → `architect` · "
        "realize a decided structure in code → `engineer`. If you were assessing (`review`) or "
        "designing (`architect`) — or no role is declared — this is a switch: declare "
        "`\U0001f9ed agent: engineer — <focus>` and follow its pipeline (code-flow + pre-commit: "
        "tests + lint mandatory before \"done\") before continuing. "
        "Restate the role on every switch (roles/README.md).\n"
        "Design→code hand-off: before writing code, confirm the task is **landed in "
        f"`{tasks}`** with a link to its design (design-flow step 8 Hand-off), and **re-read "
        "the backlog** to sequence it against other work (code-flow step 1 Take) — a cold engineer "
        f"session must be able to pick this task from `{tasks}` alone."
    )


def role_on_code_result(tool_name: str, file_path: str | None, session_id: str | None) -> HookResult | None:
    if tool_name not in _EDIT_TOOL_KINDS:
        return None
    if not isinstance(file_path, str) or not is_code_path(file_path):
        return None

    marker = Path(tempfile.gettempdir()) / f"keystone-role-on-code-{session_id or 'nosession'}.marker"
    if marker.exists():
        return None
    try:
        marker.write_text("seen", encoding="utf-8")
    except OSError:
        pass

    return HookResult(event_name="PreToolUse", additional_context=role_on_code_message())


def is_planning_doc(file_path: str) -> bool:
    lowered = file_path.replace("\\", "/").lower()
    if lowered.endswith(_planning_doc_files()):
        return True
    if not lowered.endswith(".md"):
        return False
    return any(segment in lowered for segment in _planning_doc_segments())


def analysis_before_mutation_message() -> str:
    return (
        "[keystone] Analysis-before-mutation check — you are editing a planning/design doc "
        "(backlog / design / ADR / requirements / keystone process).\n"
        "Role: **assessing what is** (problems, state, conformance) is `review`; **constructing "
        "the design** (options, contracts, the chosen structure) is `architect`. Declare the role "
        "(`\U0001f9ed agent: <name> — <focus>`) and restate it on a switch (roles/README.md).\n"
        "If this turn is analysis-only — the owner asked you to analyze, explain, review, "
        "compare options, or identify what remains — STOP: report findings + a recommendation in "
        "chat and get explicit confirmation (\"write it\" / \"record it\" / \"make the change\") "
        "before editing. If the request was already an edit command, proceed. Rule: "
        "guardrails/_common.md § Analysis before mutation."
    )


def analysis_write_result(tool_name: str, file_path: str | None, session_id: str | None) -> HookResult | None:
    if tool_name not in _EDIT_TOOL_KINDS:
        return None
    if not isinstance(file_path, str) or not is_planning_doc(file_path):
        return None

    marker = Path(tempfile.gettempdir()) / f"keystone-analysis-guard-{session_id or 'nosession'}.marker"
    if marker.exists():
        return None
    try:
        marker.write_text("seen", encoding="utf-8")
    except OSError:
        pass

    return HookResult(event_name="PreToolUse", additional_context=analysis_before_mutation_message())
