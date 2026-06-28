#!/usr/bin/env python3
"""Validate a keystone-consuming project's USE contract.

This is the USE-layer verifier: it checks the structural contract a *consuming* project
must satisfy — AGENTS.md, generated vendor pointers, hooks, skills, memory, the local
_forge layout, and the USE-surface isolation rule. It deliberately knows nothing about
keystone's own development artifacts; keystone's self-checks live in the dev-layer
validator (run in-tree from keystone's own repo, not shipped as part of the contract a
consumer follows). It does not modify files; run ``sync.py`` for generated pointer fixes.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import sync as sync_tool

_TASKS_MAX_LINES = 200
_TASK_STATUS_RE = re.compile(r"\b(active|blocked|deferred|done)\b")
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_GENERATED_MARKER = sync_tool.GENERATED_MARKER
_SKILL_REQUIRED_FRONTMATTER = ("name", "description", "when_to_use", "owner")

# USE-surface isolation: the documentary surface a consumer reads as guidance must be
# self-contained and must not even *name* keystone's own development artifacts. A deployed
# external agent should not learn they exist — naming them costs tokens and invites it to chase
# inert files. The rule forbids three things, while leaving generic process vocabulary ("file an
# ADR", "run sync and verify") intact:
#   1. a citation of a specific numbered standard-level decision record (DR + a number), or a
#      roadmap item/file, even in plain prose;
#   2. any link or inline-code *path* into the development tree or its artifacts;
#   3. an unambiguous dev-artifact name in plain prose (e.g. "self_ci") — names that mean nothing
#      but a keystone dev file, unlike generic words ("sync", "verify", "pytest").
# Scanned surface = the documentary USE docs only. tools/ *executables* (.py) are NOT scanned:
# the release tool legitimately operates on the dev tree (it runs meta/self_ci.py) — that is code
# doing its job, not guidance naming an inert artifact. Only README.md and CHANGELOG.md may bridge
# to the dev tree, and they are not in this surface.
_USE_OPERATIVE_GLOBS = (
    "roles/*.md",
    "pipelines/*.md",
    "guardrails/*.md",
    "profiles/*.md",
    "skills/**/*.md",
    "tools/**/*.md",
)
_USE_OPERATIVE_FILES = ("ARCHETYPES.md", "BOOTSTRAP.md", "MODEL.md")

# Citations that pin a specific keystone development artifact, even in plain prose:
#  - a numbered decision record ("ADR 0001", "ADR-12") — the bare word "ADR" as a concept is fine;
#  - a roadmap item or file ("ROADMAP O1", "ROADMAP.md") — the generic word "roadmap" is fine.
_NUMBERED_DR_RE = re.compile(r"\bADR[\s-]?\d{2,4}\b")
_ROADMAP_CITE_RE = re.compile(r"\bROADMAP(?:\.md|\s+O\d+)")
# Unambiguous dev-artifact names that leak even in plain prose. Kept deliberately narrow: only
# tokens that can mean nothing *but* a keystone dev file. Generic words a consumer legitimately
# uses ("sync", "verify", "pytest", "design", "decisions") are excluded.
_DEV_NAME_RE = re.compile(r"\bself_ci\b|\bCONCEPT\.md\b")
# Markdown link target and inline-code span — the two ways a path is written in these docs.
_LINK_RE = re.compile(r"\]\(([^)]+)\)")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
# Path fragments that only ever point into keystone's own development tree / artifacts. A path
# (link target or inline code) containing any of these is a leak; the same word in free prose
# (e.g. "detail in decisions/ ADRs") is not, because it is not written as a path here.
_DEV_PATH_TOKENS = ("meta/", "decisions/", "reviews/", "ROADMAP", "CONCEPT", "self_ci")

_VENDOR_POINTERS = {
    "CLAUDE.md": ("AGENTS.md", "@AGENTS.md"),
    ".github/copilot-instructions.md": ("AGENTS.md", None),
    "GEMINI.md": ("AGENTS.md", None),
    ".codex/README.md": ("AGENTS.md", None),
}


@dataclass(frozen=True)
class Finding:
    level: str
    message: str


class Verifier:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.findings: list[Finding] = []
        # The dev-layer root is configurable (FORGE_ROOT, default _forge); keystone mounts at
        # <forge>/keystone. Every path below derives from these so a relocated layer still verifies.
        self.forge = sync_tool.forge_root_name()
        self.keystone = f"{self.forge}/keystone"

    def ok(self, message: str) -> None:
        self.findings.append(Finding("ok", message))

    def warn(self, message: str) -> None:
        self.findings.append(Finding("warn", message))

    def error(self, message: str) -> None:
        self.findings.append(Finding("error", message))

    def check_path(self, relative: str, *, kind: str = "file") -> bool:
        path = self.root / relative
        exists = path.is_dir() if kind == "dir" else path.is_file()
        if exists:
            self.ok(f"{relative} exists")
            return True
        self.error(f"{relative} is missing")
        return False

    def check_basic_layout(self) -> None:
        forge, keystone = self.forge, self.keystone
        for relative in (
            "AGENTS.md",
            f"{forge}/TASKS.md",
            f"{keystone}/README.md",
            f"{keystone}/BOOTSTRAP.md",
            f"{keystone}/ARCHETYPES.md",
            f"{keystone}/CHANGELOG.md",
            f"{keystone}/MODEL.md",
            f"{keystone}/roles/README.md",
            f"{keystone}/roles/review.md",
            f"{keystone}/roles/architect.md",
            f"{keystone}/roles/engineer.md",
            f"{keystone}/roles/learn.md",
            f"{keystone}/roles/release.md",
            f"{keystone}/guardrails/_common.md",
            f"{keystone}/pipelines/pre-commit.md",
            f"{keystone}/pipelines/code-flow.md",
            f"{keystone}/pipelines/design-flow.md",
            f"{keystone}/pipelines/release.md",
            f"{keystone}/pipelines/tasks.md",
            f"{keystone}/bin/sync.py",
            f"{keystone}/bin/verify.py",
        ):
            self.check_path(relative)
        for relative in (f"{forge}/agents", f"{forge}/memory"):
            self.check_path(relative, kind="dir")

    def check_use_surface_isolation(self) -> None:
        """The operative USE surface must not name keystone's own development artifacts.

        A consumer follows roles/pipelines/guardrails/profiles/skills/tools +
        ARCHETYPES/BOOTSTRAP/MODEL; those must be self-contained, so a deployed agent never
        reads (or even learns of) the inert development tree. Forbidden: a numbered
        decision-record citation, and any link/inline-code path into the dev tree or its
        artifacts. Generic process vocabulary ("file an ADR") stays allowed. README.md and
        CHANGELOG.md are the deliberate bridges and are not in this surface.
        """
        keystone = self.root / self.keystone
        if not keystone.is_dir():
            return
        sources: list[Path] = []
        for pattern in _USE_OPERATIVE_GLOBS:
            sources.extend(sorted(keystone.glob(pattern)))
        for name in _USE_OPERATIVE_FILES:
            candidate = keystone / name
            if candidate.is_file():
                sources.append(candidate)

        violations: list[str] = []
        for source in sorted(set(sources)):
            violations.extend(self._isolation_violations(source))
        if violations:
            self.error(
                "USE surface names keystone development artifacts (keep it self-contained so a "
                f"consumer never reads the dev tree): {'; '.join(violations)}"
            )
        else:
            self.ok("USE surface names no keystone development artifacts")

    def _isolation_violations(self, source: Path) -> list[str]:
        text = source.read_text(encoding="utf-8")
        relative = source.relative_to(self.root)
        found: list[str] = []
        for cite_re in (_NUMBERED_DR_RE, _ROADMAP_CITE_RE):
            found.extend(f"{relative} → cites {cite}" for cite in cite_re.findall(text))
        found.extend(f"{relative} → names {name}" for name in _DEV_NAME_RE.findall(text))
        for span in (*_LINK_RE.findall(text), *_INLINE_CODE_RE.findall(text)):
            path = span.split()[0].split("#", 1)[0] if span.strip() else ""
            if any(token in path for token in _DEV_PATH_TOKENS):
                found.append(f"{relative} → path {span}")
        return found

    def check_agents_md(self) -> None:
        path = self.root / "AGENTS.md"
        if not path.is_file():
            return
        text = path.read_text(encoding="utf-8")
        if _GENERATED_MARKER in text:
            self.error("AGENTS.md must be a hand-reviewed source document, not generated by sync.py")
        required = {
            "keystone block": "## Dev layer — keystone",
            "model link": f"{self.keystone}/README.md",
            "archetype link": "ARCHETYPES.md",
            "role link": f"{self.keystone}/roles/",
            "memory rule": f"{self.forge}/memory",
            "owner verifies directive": "D2",
            "owner owns commits directive": "D5",
            "secrets rule": ".env",
        }
        missing = [name for name, snippet in required.items() if snippet not in text]
        if missing:
            self.error(f"AGENTS.md keystone block is missing: {', '.join(missing)}")
        else:
            self.ok("AGENTS.md keystone block contains required anchors")

    def check_cross_agent_contract(self) -> None:
        """Validate the source-to-pointer contract without generating AGENTS.md."""
        agents_md = self.root / "AGENTS.md"
        if not agents_md.is_file():
            return
        agents_text = agents_md.read_text(encoding="utf-8")

        missing_agents_links = []
        for relative, (agents_anchor, required_import) in _VENDOR_POINTERS.items():
            path = self.root / relative
            if not path.is_file():
                continue  # check_generated_pointers reports stale/missing generated files.
            text = path.read_text(encoding="utf-8")
            if agents_anchor not in text:
                missing_agents_links.append(relative)
            if required_import and required_import not in text:
                self.error(f"{relative} must import {required_import}; a prose pointer is not enough")
        if missing_agents_links:
            self.error(f"vendor pointer(s) do not point at AGENTS.md: {', '.join(missing_agents_links)}")
        else:
            self.ok("vendor pointers point at AGENTS.md")

        if ".claude/skills" in agents_text:
            self.warn("AGENTS.md should not point to generated .claude/skills stubs; link source skill roots instead")

        skill_sources, _ = sync_tool._skill_sources(self.root)
        if skill_sources:
            skill_roots = ("skills/", f"{self.forge}/skills", f"{self.keystone}/skills")
            if any(root_hint in agents_text for root_hint in skill_roots):
                self.ok("AGENTS.md references source skill roots")
            else:
                self.warn("skills exist, but AGENTS.md does not mention source skill roots")

    def check_agent_charters(self) -> None:
        agents_dir = self.root / self.forge / "agents"
        if not agents_dir.is_dir():
            return
        agents = sorted(path for path in agents_dir.iterdir() if path.is_dir())
        if not agents:
            self.warn(f"{self.forge}/agents has no agent charters")
            return
        for agent in agents:
            readme = agent / "README.md"
            if not readme.is_file():
                self.error(f"{readme.relative_to(self.root)} is missing")
                continue
            text = readme.read_text(encoding="utf-8")
            if f"{self.keystone}/roles" in text or "keystone/roles" in text:
                self.ok(f"{readme.relative_to(self.root)} links a keystone role")
            else:
                self.warn(f"{readme.relative_to(self.root)} does not link a keystone role")

    def check_memory(self) -> None:
        memory_dir = self.root / self.forge / "memory"
        if not memory_dir.is_dir():
            return
        index = memory_dir / "README.md"
        legacy_index = memory_dir / "MEMORY.md"
        if index.is_file():
            index_text = index.read_text(encoding="utf-8")
            self.ok(f"{self.forge}/memory/README.md exists")
        elif legacy_index.is_file():
            index_text = legacy_index.read_text(encoding="utf-8")
            self.warn(f"{self.forge}/memory/MEMORY.md exists; README.md is the preferred index")
        else:
            self.error(f"{self.forge}/memory needs README.md index")
            return

        missing_from_index = []
        for memory_file in sorted(memory_dir.glob("*.md")):
            if memory_file.name in {"README.md", "MEMORY.md"}:
                continue
            if memory_file.name not in index_text:
                missing_from_index.append(memory_file.name)
        if missing_from_index:
            self.warn(f"memory files not mentioned in index: {', '.join(missing_from_index)}")
        else:
            self.ok("memory index mentions all memory markdown files")

    def _skill_frontmatter(self, source: Path) -> dict[str, str] | None:
        lines = source.read_text(encoding="utf-8").splitlines()
        relative = source.relative_to(self.root)
        if not lines or lines[0].strip() != "---":
            self.error(f"{relative} is missing required frontmatter")
            return None

        fields: dict[str, str] = {}
        for line in lines[1:]:
            if line.strip() == "---":
                return fields
            if ":" not in line:
                self.error(f"{relative} frontmatter line is not key: value: {line!r}")
                continue
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()

        self.error(f"{relative} frontmatter is not closed with ---")
        return None

    def check_skill_contract(self, source: Path) -> None:
        relative = source.relative_to(self.root)
        fields = self._skill_frontmatter(source)
        if fields is None:
            return

        missing = [field for field in _SKILL_REQUIRED_FRONTMATTER if field not in fields]
        empty = [field for field in _SKILL_REQUIRED_FRONTMATTER if field in fields and not fields[field]]
        if missing:
            self.error(f"{relative} frontmatter is missing: {', '.join(missing)}")
        if empty:
            self.error(f"{relative} frontmatter has empty value(s): {', '.join(empty)}")
        if fields.get("name") and fields["name"] != source.parent.name:
            self.error(f"{relative} frontmatter name must match its skill directory ({source.parent.name})")

    def check_skills(self) -> None:
        sources, errors = sync_tool._skill_sources(self.root)
        for error in errors:
            self.error(error)
        if sources:
            self.ok(f"found {len(sources)} skill(s)")
            for source in sources:
                self.check_skill_contract(source)
        else:
            self.warn("no SKILL.md files found in keystone/local/usage skill roots")

    def check_generated_pointers(self) -> None:
        files, errors = sync_tool._planned_files(self.root)
        for error in errors:
            self.error(error)
        result = sync_tool._apply(files, write=False, root=self.root)
        if result.changed or result.deleted:
            stale_paths = [*result.changed, *result.deleted]
            stale = ", ".join(str(path.relative_to(self.root)) for path in stale_paths)
            self.error(f"generated pointers are stale or missing: {stale}; run sync.py")
        else:
            self.ok("generated pointers match sync.py")

    def check_tasks(self) -> None:
        path = self.root / self.forge / "TASKS.md"
        if not path.is_file():
            return  # basic layout already reports a missing TASKS.md
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > _TASKS_MAX_LINES:
            self.warn(
                f"{self.forge}/TASKS.md is {len(lines)} lines; keep it an index "
                "(pipelines/tasks.md) — detail by reference, not inlined"
            )
        entries = [line for line in lines if line.lstrip().startswith("- ") and " · " in line]
        if entries:
            without_status = [line for line in entries if not _TASK_STATUS_RE.search(line)]
            if without_status:
                self.warn(f"{len(without_status)} TASKS.md entry(ies) lack a status token")
            if any(re.search(r"\bdone\b", line) for line in entries):
                self.warn("TASKS.md has 'done' entries; move them to TASKS_ARCHIVE.md")
            if not without_status:
                self.ok("TASKS.md uses well-formed index entries")
        if _DATE_RE.search("\n".join(lines)):
            self.warn(f"{self.forge}/TASKS.md contains dates; dates are noise — derive them from git history")

    def check_hooks(self) -> None:
        for script in (
            "hook_core.py",
            "claude_adapter.py",
            "codex_adapter.py",
            "codex-hook.py",
            "git-commit-guard.py",
            "session-start-agent.py",
            "role-on-code.py",
            "analysis-guard.py",
        ):
            self.check_path(f"{self.keystone}/hooks/{script}")

    def check_gitignore(self) -> None:
        path = self.root / ".gitignore"
        if not path.is_file():
            self.warn(".gitignore is missing")
            return
        text = path.read_text(encoding="utf-8")
        if "*.env" in text and "!*.env.example" in text:
            self.ok(".gitignore has the keystone env secret pattern")
        else:
            self.warn(".gitignore should include '*.env' and '!*.env.example'")

    def check_keystone_gitignore(self) -> None:
        """Warn when the keystone submodule has no .gitignore ignoring __pycache__.

        The bin/ and tools/ Python is run in-tree, so without this a release commit cut from
        the submodule sweeps in __pycache__/ noise (surfaced as a manual finding during the
        v0.1.0 cut). A missing keystone .gitignore is a warning, not an error — keystone may
        be vendored read-only — but a present one should ignore the bytecode caches.
        """
        keystone = self.root / self.keystone
        if not keystone.is_dir():
            return
        path = keystone / ".gitignore"
        if not path.is_file():
            self.warn(f"{self.keystone}/.gitignore is missing; add one ignoring __pycache__/")
            return
        if "__pycache__" in path.read_text(encoding="utf-8"):
            self.ok("keystone .gitignore ignores __pycache__")
        else:
            self.warn(f"{self.keystone}/.gitignore should ignore __pycache__/")

    def check_ci(self) -> None:
        workflow_dir = self.root / ".github" / "workflows"
        workflows = sorted(workflow_dir.glob("*.yml")) + sorted(workflow_dir.glob("*.yaml"))
        if not workflows:
            self.warn("no GitHub Actions workflows found")
            return
        workflow_text = "\n".join(path.read_text(encoding="utf-8") for path in workflows)
        required = (
            f"python3 {self.keystone}/bin/sync.py --check",
            f"python3 {self.keystone}/bin/verify.py --strict",
        )
        missing = [command for command in required if command not in workflow_text]
        if missing:
            self.warn(f"CI should run: {', '.join(missing)}")
        else:
            self.ok("CI checks keystone generated pointers and verify")

    def check_changelog(self) -> None:
        """Warn when keystone's CHANGELOG.md exists without an `Unreleased` section.

        Keeps the "consumer-visible change ⇒ changelog entry" discipline mechanical rather than
        trust-based (ADR 0001 §9). A missing CHANGELOG.md is not an error here — only a present
        one that has nowhere to record pending changes.
        """
        path = self.root / self.keystone / "CHANGELOG.md"
        if not path.is_file():
            return
        text = path.read_text(encoding="utf-8")
        if re.search(r"^##\s+Unreleased\b", text, re.MULTILINE | re.IGNORECASE):
            self.ok("CHANGELOG.md has an Unreleased section")
        else:
            self.warn("CHANGELOG.md has no `## Unreleased` section; add one for pending changes")

    def check_attach_record(self) -> None:
        """Validate the `_forge/.keystone.toml` integration record *of a consuming project*.

        It is the "where the project is" anchor that BOOTSTRAP §B2 diffs against keystone's
        CHANGELOG to compute which Breaking/migration entries a realign still needs to verify.
        The agent writes it on attach/realign (sync.py is stdlib-only and cannot run `git describe`).

        It is a **consumer** artifact, so this check applies only when keystone is mounted as a
        submodule (`<FORGE_ROOT>/keystone/` present) — verify run against the keystone repo itself
        skips it. Even on a consumer, a *missing* record is a non-gating note (the project may
        predate this contract; the fix is a realign), so it never fails `--strict`; only a
        *present but malformed* record — missing the required top-level keys — is an error.
        """
        if not (self.root / self.keystone).is_dir():
            return  # keystone repo itself, or not a keystone consumer — no integration record expected
        name = f"{self.forge}/.keystone.toml"
        path = self.root / self.forge / ".keystone.toml"
        if not path.is_file():
            self.ok(
                f"{name} not present (optional; a realign writes it so future "
                "bumps can diff the CHANGELOG — BOOTSTRAP §B2)"
            )
            return
        fields = sync_tool.read_keystone_toml(path)
        required = ("keystone_version", "attached_archetype", "last_realign")
        missing = [key for key in required if not fields.get(key)]
        if missing:
            self.error(f"{name} is missing required key(s): {', '.join(missing)}")
        else:
            self.ok(f"{name} records keystone version {fields['keystone_version']}")

    def run(self) -> None:
        self.check_basic_layout()
        self.check_use_surface_isolation()
        self.check_agents_md()
        self.check_cross_agent_contract()
        self.check_agent_charters()
        self.check_memory()
        self.check_tasks()
        self.check_skills()
        self.check_generated_pointers()
        self.check_hooks()
        self.check_gitignore()
        self.check_keystone_gitignore()
        self.check_ci()
        self.check_changelog()
        self.check_attach_record()


def print_findings(findings: list[Finding], *, quiet: bool) -> None:
    for finding in findings:
        if quiet and finding.level == "ok":
            continue
        print(f"[{finding.level}] {finding.message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, help="Project root. Defaults to cwd or a parent with AGENTS.md.")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    parser.add_argument("--quiet", action="store_true", help="Only print warnings and errors.")
    args = parser.parse_args(argv)

    root = (args.project_root or sync_tool._find_project_root(Path.cwd())).resolve()
    verify = Verifier(root)
    verify.run()
    print_findings(verify.findings, quiet=args.quiet)

    has_errors = any(finding.level == "error" for finding in verify.findings)
    has_warnings = any(finding.level == "warn" for finding in verify.findings)
    if has_errors or (args.strict and has_warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
