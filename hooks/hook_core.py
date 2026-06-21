"""Vendor-neutral keystone hook decisions.

This module contains the guardrail logic only. Vendor entrypoints adapt their incoming
payload and serialize ``HookResult`` into the shape their runtime expects.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


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
_NON_CODE_SEGMENTS = ("/docs/", "/_forge/design/", "/_forge/memory/", "/_forge/keystone/", "/.claude/")
# Neutral tool-kind: each vendor adapter normalizes its own file-editing tool name(s) to this
# token before calling. The core stays vendor-clean — it never names a vendor's tools.
EDIT_TOOL = "edit"
_EDIT_TOOL_KINDS = frozenset({EDIT_TOOL})

# Planning / design docs — editing one may be an analysis-only turn that needs confirmation
# first (see guardrails/_common.md § Analysis before mutation).
_PLANNING_DOC_SEGMENTS = ("/_forge/design/", "/docs/dev/", "/_forge/keystone/")
_PLANNING_DOC_FILES = ("/_forge/tasks.md", "/_forge/tasks_archive.md")


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
    """Walk up from ``start`` (or cwd) to the first dir holding AGENTS.md + _forge/keystone."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "_forge" / "keystone").exists():
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
    dev = agent_names(root / "_forge" / "agents")
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
        lines.append(f"- OPERATE (run on the market): {', '.join(desk)}")
    lines.append("No agent is active yet — pick the one the task calls for; if unclear, ask.")
    lines.append("Also: read `_forge/memory/` at session start (project memory).")
    return HookResult(event_name="SessionStart", additional_context="\n".join(lines))


def is_code_path(file_path: str) -> bool:
    lowered = file_path.replace("\\", "/").lower()
    if any(segment in lowered for segment in _NON_CODE_SEGMENTS):
        return False
    return Path(lowered).suffix in _CODE_EXTENSIONS


def role_on_code_message() -> str:
    return (
        "[keystone] Role check — you are editing project code.\n"
        "If you have been operating as a design/architect role (or no role is declared), this is a "
        "switch to the **build** role: declare `\U0001f9ed agent: engineer — <focus>` and follow its "
        "pipeline (code-flow + pre-commit: tests + lint mandatory before \"done\") before continuing. "
        "Restate the role on every switch (roles/README.md).\n"
        "Design→code hand-off: before writing code, confirm the task is **landed in "
        "`_forge/TASKS.md`** with a link to its design (design-flow step 8 Hand-off), and **re-read "
        "the backlog** to sequence it against other work (code-flow step 1 Take) — a cold engineer "
        "session must be able to pick this task from `_forge/TASKS.md` alone."
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
    if lowered.endswith(_PLANNING_DOC_FILES):
        return True
    if not lowered.endswith(".md"):
        return False
    return any(segment in lowered for segment in _PLANNING_DOC_SEGMENTS)


def analysis_before_mutation_message() -> str:
    return (
        "[keystone] Analysis-before-mutation check — you are editing a planning/design doc "
        "(backlog / design / ADR / requirements / keystone process).\n"
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
