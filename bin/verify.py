#!/usr/bin/env python3
"""Validate a akmon-consuming project's USE contract.

This is the USE-layer verifier: it checks the structural contract a *consuming* project
must satisfy — AGENTS.md, generated vendor pointers, hooks, skills, memory, the local
_aitna layout, and the USE-surface isolation rule. It deliberately knows nothing about
akmon's own development artifacts; akmon's self-checks live in the dev-layer
validator (run in-tree from akmon's own repo, not shipped as part of the contract a
consumer follows). It does not modify files; run ``sync.py`` for generated pointer fixes.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# The shared utilities live in the tree's ``common`` package, not beside this script:
# ``bin/`` is the launcher directory. A launcher is run as ``python3 <tree>/bin/sync.py``, so
# ``sys.path[0]`` is ``bin/`` — the tree root has to be added for the package to resolve. Done
# here rather than left to the caller because both launchers are entry points in their own right.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sync as sync_tool  # noqa: E402

from common.findings import Finding, exit_code, line_safe, print_findings  # noqa: E402
from common.project_root import resolve_project_root  # noqa: E402

_TASKS_MAX_LINES = 200
_TASK_STATUSES = ("active", "blocked", "deferred", "done")
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def _sample(ids: list[str], limit: int = 4) -> str:
    """Name the offenders, not just their count — a finding a reader cannot locate is half a finding."""
    shown = ", ".join(ids[:limit])
    return shown if len(ids) <= limit else f"{shown}, +{len(ids) - limit} more"

_DELEGATION_DEFAULT_RE = re.compile(r"\bdelegation\s+is\s+the\s+default\b", re.IGNORECASE)
_GENERATED_MARKER = sync_tool.GENERATED_MARKER
_SKILL_REQUIRED_FRONTMATTER = ("name", "description", "when_to_use", "owner")

# USE-surface isolation: the documentary surface a consumer reads as guidance must be
# self-contained and must not even *name* akmon's own development artifacts. A deployed
# external agent should not learn they exist — naming them costs tokens and invites it to chase
# inert files. The rule forbids three things, while leaving generic process vocabulary ("file an
# ADR", "run sync and verify") intact:
#   1. a citation of a specific numbered standard-level decision record (DR + a number), or a
#      roadmap item/file, even in plain prose;
#   2. any link or inline-code *path* into the development tree or its artifacts;
#   3. an unambiguous dev-artifact name in plain prose (e.g. "self_ci") — names that mean nothing
#      but a akmon dev file, unlike generic words ("sync", "verify", "pytest").
# Scanned surface = the documentary USE docs only. tools/ *executables* (.py) are NOT scanned:
# the release tool legitimately operates on the dev tree (it runs meta/self_ci.py) — that is code
# doing its job, not guidance naming an inert artifact. README.md, CHANGELOG.md, and examples/
# are deliberate bridges and are not in this surface: examples/ is meta-documentation *about* the
# mechanism (worked examples with provenance citations into meta/reviews/, meta/design/, etc.), read
# by a maintainer studying how akmon works — not operative guidance a deployed consumer agent
# executes. Same class as README/CHANGELOG citing dev history; a consumer never attaches examples/.
# (C35: decided explicitly rather than left as an accidental gap in _USE_OPERATIVE_GLOBS below.)
_USE_OPERATIVE_GLOBS = (
    "roles/*.md",
    "pipelines/*.md",
    "guardrails/*.md",
    "profiles/*.md",
    "skills/**/*.md",
    "tools/**/*.md",
)
_USE_OPERATIVE_FILES = ("ARCHETYPES.md", "BOOTSTRAP.md", "MODEL.md")

# Citations that pin a specific akmon development artifact, even in plain prose:
#  - a numbered decision record ("ADR 0001", "ADR-12") — the bare word "ADR" as a concept is fine;
#  - a roadmap item or file ("ROADMAP O1", "ROADMAP.md") — the generic word "roadmap" is fine.
_NUMBERED_DR_RE = re.compile(r"\bADR[\s-]?\d{2,4}\b")
_ROADMAP_CITE_RE = re.compile(r"\bROADMAP(?:\.md|\s+O\d+)")
# Unambiguous dev-artifact names that leak even in plain prose. Kept deliberately narrow: only
# tokens that can mean nothing *but* a akmon dev file. Generic words a consumer legitimately
# uses ("sync", "verify", "pytest", "design", "decisions") are excluded.
_DEV_NAME_RE = re.compile(r"\bself_ci\b|\bCONCEPT\.md\b")
# Markdown link target and inline-code span — the two ways a path is written in these docs.
_LINK_RE = re.compile(r"\]\(([^)]+)\)")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
# Path fragments that only ever point into akmon's own development tree / artifacts. A path
# (link target or inline code) containing any of these is a leak; the same word in free prose
# (e.g. "detail in decisions/ ADRs") is not, because it is not written as a path here.
_DEV_PATH_TOKENS = ("meta/", "decisions/", "reviews/", "ROADMAP", "CONCEPT", "self_ci")

_VENDOR_POINTERS = {
    "CLAUDE.md": ("AGENTS.md", "@AGENTS.md"),
    ".github/copilot-instructions.md": ("AGENTS.md", None),
    "GEMINI.md": ("AGENTS.md", None),
    ".codex/README.md": ("AGENTS.md", None),
}


class Verifier:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.findings: list[Finding] = []
        # The dev-layer root is configurable (AITNA_ROOT, default _aitna); akmon mounts at
        # <aitna>/akmon. Every path below derives from these so a relocated layer still verifies.
        self.aitna = sync_tool.aitna_root_name()
        self.akmon = f"{self.aitna}/akmon"
        # The standard tree this project actually operates against: the mount for mounted
        # modes, the embedded tree for package mode (ADR 0009 §4) — may live outside
        # ``self.root`` entirely. Used by ``check_standard_path`` and the checks that
        # validate the standard's own shipped content rather than the consumer's use of it.
        self.standard_root = sync_tool.standard_tree_root(self.root)

    def ok(self, code: str, message: str, *, target: str = "", fix: str) -> None:
        self.findings.append(Finding("ok", code, line_safe(message), line_safe(target), line_safe(fix)))

    def warn(self, code: str, message: str, *, target: str = "", fix: str) -> None:
        self.findings.append(Finding("warn", code, line_safe(message), line_safe(target), line_safe(fix)))

    def error(self, code: str, message: str, *, target: str = "", fix: str) -> None:
        self.findings.append(Finding("error", code, line_safe(message), line_safe(target), line_safe(fix)))

    def check_path(self, relative: str, *, kind: str = "file") -> bool:
        path = self.root / relative
        exists = path.is_dir() if kind == "dir" else path.is_file()
        if exists:
            self.ok(
                "layout.consumer-path",
                f"{relative} exists",
                target=relative,
                fix=f"Keep {relative} in place.",
            )
            return True
        self.error(
            "layout.consumer-path",
            f"{relative} is missing",
            target=relative,
            fix=f"Create {relative}.",
        )
        return False

    def _display_path(self, path: Path) -> str:
        """``path`` rendered relative to the consumer root when possible (mounted mode: the
        standard tree lives under ``self.root``, so this matches ``check_path``'s wording
        exactly — byte-identical output for existing mounted consumers). Package mode's
        embedded tree can live outside ``self.root`` entirely, so this falls back to a
        ``standard tree:``-prefixed path relative to ``self.standard_root``.
        """
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return f"standard tree:{path.relative_to(self.standard_root)}"

    def check_standard_path(self, relative: str, *, kind: str = "file") -> bool:
        """Like ``check_path``, resolved against ``self.standard_root`` instead of
        ``self.root`` — for content that ships with the standard itself (roles, pipelines,
        model-routing tools, …) rather than being generated into the consumer repo.
        """
        path = self.standard_root / relative
        exists = path.is_dir() if kind == "dir" else path.is_file()
        display = self._display_path(path)
        if exists:
            self.ok(
                "layout.standard-path",
                f"{display} exists",
                target=display,
                fix=f"Keep {display} in the standard tree.",
            )
            return True
        self.error(
            "layout.standard-path",
            f"{display} is missing",
            target=display,
            fix=f"Restore {display} by re-attaching or updating the akmon standard tree.",
        )
        return False

    def check_basic_layout(self) -> None:
        aitna = self.aitna
        for relative in (
            "AGENTS.md",
            f"{aitna}/TASKS.md",
        ):
            self.check_path(relative)
        for relative in (
            "README.md",
            "BOOTSTRAP.md",
            "ARCHETYPES.md",
            "CHANGELOG.md",
            "MODEL.md",
            "CAPABILITIES.md",
            "roles/README.md",
            "roles/review.md",
            "roles/architect.md",
            "roles/engineer.md",
            "roles/learn.md",
            "roles/release.md",
            "guardrails/_common.md",
            "pipelines/pre-commit.md",
            "pipelines/code-flow.md",
            "pipelines/design-flow.md",
            "pipelines/release.md",
            "pipelines/tasks.md",
            "bin/sync.py",
            "bin/verify.py",
        ):
            self.check_standard_path(relative)
        for relative in (f"{aitna}/agents", f"{aitna}/memory"):
            self.check_path(relative, kind="dir")

    def check_use_surface_isolation(self) -> None:
        """The operative USE surface must not name akmon's own development artifacts.

        A consumer follows roles/pipelines/guardrails/profiles/skills/tools +
        ARCHETYPES/BOOTSTRAP/MODEL; those must be self-contained, so a deployed agent never
        reads (or even learns of) the inert development tree. Forbidden: a numbered
        decision-record citation, and any link/inline-code path into the dev tree or its
        artifacts. Generic process vocabulary ("file an ADR") stays allowed. README.md and
        CHANGELOG.md are the deliberate bridges and are not in this surface.
        """
        akmon = self.standard_root
        if not akmon.is_dir():
            return
        sources: list[Path] = []
        for pattern in _USE_OPERATIVE_GLOBS:
            sources.extend(sorted(akmon.glob(pattern)))
        for name in _USE_OPERATIVE_FILES:
            candidate = akmon / name
            if candidate.is_file():
                sources.append(candidate)

        violations: list[str] = []
        for source in sorted(set(sources)):
            violations.extend(self._isolation_violations(source))
        if violations:
            self.error(
                "isolation.use-surface",
                "USE surface names akmon development artifacts (keep it self-contained so a "
                f"consumer never reads the dev tree): {'; '.join(violations)}",
                fix="Remove the listed development-tree citations and paths from the USE surface.",
            )
        else:
            self.ok(
                "isolation.use-surface",
                "USE surface names no akmon development artifacts",
                fix="Keep decision-record citations and dev-tree paths out of the USE surface.",
            )

    def _isolation_violations(self, source: Path) -> list[str]:
        text = source.read_text(encoding="utf-8")
        relative = self._display_path(source)
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
            self.error(
                "agents.generated-source",
                "AGENTS.md must be a hand-reviewed source document, not generated by sync.py",
                target="AGENTS.md",
                fix="Remove the generated banner and hand-own AGENTS.md.",
            )
        if sync_tool.is_package_mode(self.root):
            # Provisional package-mode contract (ADR 0009 §4-5, pinned by the owner ahead of
            # C37 slice B's verify.py adaptation): no mounted tree to link, so the
            # load-bearing anchor is the materialized guardrails import (the always-on
            # surface `akmon sync` writes to `.akmon/`); `akmon path` is how an agent reaches
            # the rest of the standard (roles, MODEL.md) locally. Revisit this exact wording
            # once the alphavar pilot's findings fold back, before the first PyPI publish
            # (meta/design/packaging/README.md §Open points).
            required = {
                "akmon block": "## Dev layer — akmon",
                "guardrails import": f"@{self.aitna}/.akmon/guardrails/_common.md",
                "akmon path pointer": "akmon path",
                "archetype link": "ARCHETYPES.md",
                "memory rule": f"{self.aitna}/memory",
                "owner verifies directive": "D2",
                "owner owns commits directive": "D5",
                "secrets rule": ".env",
            }
        else:
            required = {
                "akmon block": "## Dev layer — akmon",
                "model link": f"{self.akmon}/README.md",
                "archetype link": "ARCHETYPES.md",
                "role link": f"{self.akmon}/roles/",
                "memory rule": f"{self.aitna}/memory",
                "owner verifies directive": "D2",
                "owner owns commits directive": "D5",
                "secrets rule": ".env",
            }
        missing = [name for name, snippet in required.items() if snippet not in text]
        if not _DELEGATION_DEFAULT_RE.search(text):
            missing.append("direct delegation-default rule")
        if missing:
            self.error(
                "agents.block-anchors",
                f"AGENTS.md akmon block is missing: {', '.join(missing)}",
                target="AGENTS.md",
                fix="Add the listed anchors to the akmon block in AGENTS.md.",
            )
        else:
            self.ok(
                "agents.block-anchors",
                "AGENTS.md akmon block contains required anchors",
                target="AGENTS.md",
                fix="Keep every required anchor in the AGENTS.md akmon block.",
            )

    def check_cross_agent_contract(self) -> None:
        """Validate the source-to-pointer contract without generating AGENTS.md."""
        agents_md = self.root / "AGENTS.md"
        if not agents_md.is_file():
            return
        agents_text = agents_md.read_text(encoding="utf-8")

        missing_agents_links = []
        present_pointers = 0
        for relative, (agents_anchor, required_import) in _VENDOR_POINTERS.items():
            path = self.root / relative
            if not path.is_file():
                continue  # check_generated_pointers reports stale/missing generated files.
            present_pointers += 1
            text = path.read_text(encoding="utf-8")
            if agents_anchor not in text:
                missing_agents_links.append(relative)
            if required_import and required_import not in text:
                self.error(
                    "pointers.vendor-import",
                    f"{relative} must import {required_import}; a prose pointer is not enough",
                    target=relative,
                    fix=f"Re-run akmon sync so {relative} imports {required_import}.",
                )
        if missing_agents_links:
            self.error(
                "pointers.vendor-agents-link",
                f"vendor pointer(s) do not point at AGENTS.md: {', '.join(missing_agents_links)}",
                fix="Re-run akmon sync so every vendor pointer points at AGENTS.md.",
            )
        elif present_pointers == len(_VENDOR_POINTERS):
            self.ok(
                "pointers.vendor-agents-link",
                "vendor pointers point at AGENTS.md",
                fix="Keep every vendor pointer aimed at AGENTS.md.",
            )

        if ".claude/skills" in agents_text:
            self.warn(
                "agents.skill-stub-link",
                "AGENTS.md should not point to generated .claude/skills stubs; link source skill roots instead",
                target="AGENTS.md",
                fix="Replace the generated stub path in AGENTS.md with the source skill root.",
            )

        skill_sources, _ = sync_tool._skill_sources(self.root)
        if skill_sources:
            skill_roots = ("skills/", f"{self.aitna}/skills", f"{self.akmon}/skills")
            if any(root_hint in agents_text for root_hint in skill_roots):
                self.ok(
                    "agents.skill-roots",
                    "AGENTS.md references source skill roots",
                    target="AGENTS.md",
                    fix="Keep the source skill roots named in AGENTS.md.",
                )
            else:
                self.warn(
                    "agents.skill-roots",
                    "skills exist, but AGENTS.md does not mention source skill roots",
                    target="AGENTS.md",
                    fix="Name the source skill roots in AGENTS.md so agents find the skills.",
                )

    def check_agent_charters(self) -> None:
        agents_dir = self.root / self.aitna / "agents"
        if not agents_dir.is_dir():
            return
        agents = sorted(path for path in agents_dir.iterdir() if path.is_dir())
        if not agents:
            self.warn(
                "charters.present",
                f"{self.aitna}/agents has no agent charters",
                target=f"{self.aitna}/agents",
                fix=f"Add one directory per agent under {self.aitna}/agents, each with a README.md charter.",
            )
            return
        for agent in agents:
            readme = agent / "README.md"
            relative = str(readme.relative_to(self.root))
            if not readme.is_file():
                self.error(
                    "charters.readme",
                    f"{relative} is missing",
                    target=relative,
                    fix=f"Create {relative} linking the akmon role this agent follows.",
                )
                continue
            text = readme.read_text(encoding="utf-8")
            if f"{self.akmon}/roles" in text or "akmon/roles" in text:
                self.ok(
                    "charters.role-link",
                    f"{relative} links a akmon role",
                    target=relative,
                    fix="Keep the akmon role link in this charter.",
                )
            else:
                self.warn(
                    "charters.role-link",
                    f"{relative} does not link a akmon role",
                    target=relative,
                    fix=f"Link the akmon role this agent follows from {relative}.",
                )

    def check_memory(self) -> None:
        memory_dir = self.root / self.aitna / "memory"
        if not memory_dir.is_dir():
            return
        index = memory_dir / "README.md"
        legacy_index = memory_dir / "MEMORY.md"
        if index.is_file():
            index_text = index.read_text(encoding="utf-8")
            self.ok(
                "memory.index",
                f"{self.aitna}/memory/README.md exists",
                target=f"{self.aitna}/memory/README.md",
                fix="Keep README.md as the memory index.",
            )
        elif legacy_index.is_file():
            index_text = legacy_index.read_text(encoding="utf-8")
            self.warn(
                "memory.index",
                f"{self.aitna}/memory/MEMORY.md exists; README.md is the preferred index",
                target=f"{self.aitna}/memory/MEMORY.md",
                fix=f"Rename {self.aitna}/memory/MEMORY.md to README.md.",
            )
        else:
            self.error(
                "memory.index",
                f"{self.aitna}/memory needs README.md index",
                target=f"{self.aitna}/memory",
                fix=f"Add a README.md index under {self.aitna}/memory.",
            )
            return

        missing_from_index = []
        for memory_file in sorted(memory_dir.glob("*.md")):
            if memory_file.name in {"README.md", "MEMORY.md"}:
                continue
            if memory_file.name not in index_text:
                missing_from_index.append(memory_file.name)
        if missing_from_index:
            self.warn(
                "memory.index-coverage",
                f"memory files not mentioned in index: {', '.join(missing_from_index)}",
                target=f"{self.aitna}/memory",
                fix="List the unmentioned memory files in the memory index.",
            )
        else:
            self.ok(
                "memory.index-coverage",
                "memory index mentions all memory markdown files",
                target=f"{self.aitna}/memory",
                fix="Keep every memory file listed in the index.",
            )

    def _skill_frontmatter(self, source: Path) -> dict[str, str] | None:
        lines = source.read_text(encoding="utf-8").splitlines()
        relative = self._display_path(source)
        if not lines or lines[0].strip() != "---":
            self.error(
                "skills.frontmatter",
                f"{relative} is missing required frontmatter",
                target=relative,
                fix=f"Open {relative} with a --- frontmatter block.",
            )
            return None

        fields: dict[str, str] = {}
        for line in lines[1:]:
            if line.strip() == "---":
                return fields
            if ":" not in line:
                self.error(
                    "skills.frontmatter-syntax",
                    f"{relative} frontmatter line is not key: value: {line!r}",
                    target=relative,
                    fix="Write each frontmatter line as key: value.",
                )
                continue
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()

        self.error(
            "skills.frontmatter-close",
            f"{relative} frontmatter is not closed with ---",
            target=relative,
            fix=f"Close the {relative} frontmatter block with ---.",
        )
        return None

    def check_skill_contract(self, source: Path) -> None:
        relative = self._display_path(source)
        fields = self._skill_frontmatter(source)
        if fields is None:
            return

        missing = [field for field in _SKILL_REQUIRED_FRONTMATTER if field not in fields]
        empty = [field for field in _SKILL_REQUIRED_FRONTMATTER if field in fields and not fields[field]]
        if missing:
            self.error(
                "skills.required-fields",
                f"{relative} frontmatter is missing: {', '.join(missing)}",
                target=relative,
                fix="Add the listed frontmatter keys to this skill.",
            )
        if empty:
            self.error(
                "skills.field-values",
                f"{relative} frontmatter has empty value(s): {', '.join(empty)}",
                target=relative,
                fix="Give every required frontmatter key a value.",
            )
        if fields.get("name") and fields["name"] != source.parent.name:
            self.error(
                "skills.name-matches-dir",
                f"{relative} frontmatter name must match its skill directory ({source.parent.name})",
                target=relative,
                fix=f"Set the frontmatter name to {source.parent.name}.",
            )

    def check_skills(self) -> None:
        sources, errors = sync_tool._skill_sources(self.root)
        for error in errors:
            self.error(
                "skills.duplicate-name",
                error,
                fix="Rename one of the two skill directories so each skill name is unique.",
            )
        if sources:
            self.ok(
                "skills.present",
                f"found {len(sources)} skill(s)",
                fix="Keep at least one SKILL.md in a skill root.",
            )
            for source in sources:
                self.check_skill_contract(source)
        else:
            self.warn(
                "skills.present",
                "no SKILL.md files found in akmon/local/usage skill roots",
                fix="Add a SKILL.md under a skill root, or ignore this if the project ships no skills.",
            )

    def check_generated_pointers(self) -> None:
        files, errors = sync_tool._planned_files(self.root)
        for error in errors:
            self.error(
                "pointers.generated-plan",
                error,
                fix="Resolve the reported planning error, then re-run akmon sync.",
            )
        result = sync_tool._apply(files, write=False, root=self.root)
        if result.changed or result.deleted:
            stale_paths = [*result.changed, *result.deleted]
            stale = ", ".join(str(path.relative_to(self.root)) for path in stale_paths)
            self.error(
                "pointers.generated-freshness",
                f"generated pointers are stale or missing: {stale}; run sync.py",
                fix="Run akmon sync to regenerate the listed files.",
            )
        else:
            self.ok(
                "pointers.generated-freshness",
                "generated pointers match sync.py",
                fix="Re-run akmon sync after every change to a generated file's source.",
            )

    @staticmethod
    def _entry_id(entry: str) -> str:
        """The id heading a backlog entry, for naming it in a finding."""
        head = entry.split(" · ", 1)[0]
        return head.removeprefix("- ").strip().strip("*") or "?"

    @staticmethod
    def _entry_status(entry: str) -> str | None:
        """The status of one backlog entry: the head word of its third ``·`` field, or ``None``.

        Read the *field*, not the line. This check used to search the whole entry for one of the
        four status words, which cannot fail on the defect it names: an entry whose prose happens
        to contain "blocked" passed with any status text at all, and an entry whose prose
        contained "done" was reported as needing archiving. Both directions were wrong, and the
        first is how a backlog drifts into free-form statuses under a green check.

        The head word is what is checked, so the house form ``blocked (after C51)`` — a valid
        status plus a qualifier naming what it waits on — stays valid, as does ``**active**``.
        """
        fields = entry.split(" · ")
        if len(fields) < 3:
            return None
        status = fields[2].strip().strip("*").strip()
        if not status:
            return None
        return status.split()[0].strip("*:,;").lower() or None

    def check_tasks(self) -> None:
        path = self.root / self.aitna / "TASKS.md"
        if not path.is_file():
            return  # basic layout already reports a missing TASKS.md
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > _TASKS_MAX_LINES:
            self.warn(
                "tasks.index-length",
                f"{self.aitna}/TASKS.md is {len(lines)} lines; keep it an index "
                "(pipelines/tasks.md) — detail by reference, not inlined",
                target=f"{self.aitna}/TASKS.md",
                fix="Move inlined task detail out to a referenced document.",
            )
        # Entries are top-level list items. An indented bullet is a note *under* an entry
        # (pipelines/tasks.md), and holding one to the entry grammar reports a defect that is not
        # there — which `lstrip()` here used to do.
        entries = [line for line in lines if line.startswith("- ") and " · " in line]
        if entries:
            statuses = [(self._entry_id(line), self._entry_status(line)) for line in entries]
            bad = [entry_id for entry_id, status in statuses if status not in _TASK_STATUSES]
            if bad:
                self.warn(
                    "tasks.entry-status",
                    f"{len(bad)} TASKS.md entry(ies) carry a status outside "
                    f"{' | '.join(_TASK_STATUSES)}: {_sample(bad)}",
                    target=f"{self.aitna}/TASKS.md",
                    fix=f"Set each listed entry's status field to one of {' | '.join(_TASK_STATUSES)}.",
                )
            finished = [entry_id for entry_id, status in statuses if status == "done"]
            if finished:
                self.warn(
                    "tasks.done-archived",
                    f"TASKS.md has 'done' entries; move them to TASKS_ARCHIVE.md: {_sample(finished)}",
                    target=f"{self.aitna}/TASKS.md",
                    fix="Move the listed done entries to TASKS_ARCHIVE.md.",
                )
            if not bad:
                self.ok(
                    "tasks.entry-status",
                    "TASKS.md uses well-formed index entries",
                    target=f"{self.aitna}/TASKS.md",
                    fix=f"Keep every entry's status field within {' | '.join(_TASK_STATUSES)}.",
                )
        if _DATE_RE.search("\n".join(lines)):
            self.warn(
                "tasks.dates",
                f"{self.aitna}/TASKS.md contains dates; dates are noise — derive them from git history",
                target=f"{self.aitna}/TASKS.md",
                fix="Delete the dates from TASKS.md and read them from git history instead.",
            )

    def check_hooks(self) -> None:
        """The hook scripts must exist in the standard tree this project runs.

        Checked in every mode, package included. It used to short-circuit there on the grounds
        that the generated-pointers check already covered the materialized copies — but since
        C77 there are no copies: the wiring calls ``akmon hook <name>``, which runs these files
        out of the wheel, so their existence in the tree *is* what the wiring rests on. Nothing
        else covers it, and a missing one fails the way every hook failure fails — silently.
        """
        for script in (
            "hook_core.py",
            "claude_adapter.py",
            "codex_adapter.py",
            "codex-hook.py",
            "git-commit-guard.py",
            "session-start-agent.py",
            "role-on-code.py",
            "analysis-guard.py",
            "model-routing.py",
            "delegation-log.py",
        ):
            self.check_standard_path(f"hooks/{script}")

    def check_hook_launcher(self) -> None:
        """Mode ``package``: the console script the generated hook wiring names must be executable.

        The wiring spells ``"<anchor>/.venv/bin/akmon" hook <name>`` (ADR 0009 §4). A hook
        command whose executable is missing or not executable **fails silently** — the harness
        runs it, the shell error stays outside the session, and the session shows no non-zero gate,
        just guardrails that stopped firing. So this is checked here, in the consumer's CI, rather
        than as a ``sync`` plan error: the first attach runs ``sync`` before the dev group is
        installed, and failing there would break the flow that has to work out of the box.

        Mode ``package`` therefore requires the venv **inside the project root**: the wiring is
        a committed shared file, so an absolute path to whatever venv the person who ran
        ``sync`` happened to use is the same silent break for everyone else.
        """
        if not sync_tool.is_package_mode(self.root):
            return
        relative = sync_tool.launcher_relative(self.root)
        if sync_tool.is_executable_file(self.root / relative):
            self.ok(
                "hooks.launcher",
                f"generated hook wiring calls {relative}, which is executable",
                target=relative,
                fix=f"Keep the akmon dev pin installed into a project-local venv ({relative}).",
            )
            return
        self.error(
            "hooks.launcher",
            f"generated hook wiring calls {relative}, which is missing or not executable — every akmon hook "
            "command fails silently (an unavailable executable produces no session-visible error), "
            "so the guardrails are off",
            target=relative,
            fix=(
                "Install the akmon dev pin into a project-local virtualenv, then re-run akmon sync."
            ),
        )

    def check_model_routing(self) -> None:
        """The routing registry and tools must ship with akmon and parse cleanly.

        Freshness of the per-user local config is the SessionStart hook's job (it injects
        the re-init instruction); verify only guards the committed contract surface.
        """
        for relative in (
            "tools/model_routing/registry.json",
            "tools/model_routing/routing.py",
            "tools/model_routing/init.py",
            "tools/model_routing/second_opinion.py",
        ):
            self.check_standard_path(relative)
        registry_path = self.standard_root / "tools" / "model_routing" / "registry.json"
        if registry_path.is_file():
            try:
                registry = sync_tool._read_json(registry_path)
                self.ok(
                    "routing.registry-parse",
                    "model-routing registry parses",
                    target=self._display_path(registry_path),
                    fix="Keep the model-routing registry valid JSON.",
                )
                self._check_model_routing_registry(registry)
            except ValueError as exc:
                self.error(
                    "routing.registry-parse",
                    str(exc),
                    target=self._display_path(registry_path),
                    fix="Repair the model-routing registry so it parses as JSON.",
                )
        overlay = self.root / self.aitna / "model-routing.json"
        if overlay.is_file():
            try:
                overlay_data = sync_tool._read_json(overlay)
                self.ok(
                    "routing.overlay-parse",
                    "model-routing project overlay parses",
                    target=f"{self.aitna}/model-routing.json",
                    fix="Keep the project routing overlay valid JSON.",
                )
            except ValueError as exc:
                self.error(
                    "routing.overlay-parse",
                    str(exc),
                    target=f"{self.aitna}/model-routing.json",
                    fix="Repair the project routing overlay so it parses as JSON.",
                )
            else:
                # Outside the try: a defect in the check below must not be reported as a
                # parse failure of the file it is reading.
                self._check_overlay_second_opinion(overlay_data)

    def _check_overlay_second_opinion(self, overlay: object) -> None:
        """The overlay must not carry keys C57 retired.

        The overlay is deep-merged *over* the shipped registry, so a stale `cli`/`invoke` pair
        does not displace `harness`/`operation` — it rides alongside them, unread. The merged
        config then looks complete while meaning something the runtime no longer honours, which
        is why this is checked at the file rather than inferred from the merged result.
        """
        if not isinstance(overlay, dict):
            return
        for vendor in ("anthropic", "openai"):
            spec = overlay.get(vendor)
            if not isinstance(spec, dict):
                continue
            second = spec.get("second_opinion")
            if not isinstance(second, dict):
                continue
            retired = [key for key in ("cli", "invoke") if key in second]
            if retired:
                self.error(
                    "routing.second-opinion",
                    f"project overlay {vendor} second_opinion carries the retired "
                    f"key(s) {', '.join(retired)}",
                    target=f"{self.aitna}/model-routing.json#{vendor}",
                    fix="Delete only cli/invoke from this hand-owned overlay, leave the rest "
                        "of the object as it is, then re-run the routing initializer.",
                )

    def _check_model_routing_registry(self, registry: dict) -> None:
        for vendor in ("anthropic", "openai"):
            spec = registry.get(vendor)
            if not isinstance(spec, dict):
                self.error(
                    "routing.vendor-present",
                    f"model-routing registry is missing vendor {vendor!r}",
                    target=f"tools/model_routing/registry.json#{vendor}",
                    fix=f"Add a {vendor} object to the model-routing registry.",
                )
                continue
            policy = spec.get("selection_policy")
            # "orchestrator" is the ADR 0005/0006 dynamic default (reasoner rides the
            # orchestrator's own model, tools/model_routing/routing.py::compute_binding);
            # "highest" is the pre-ADR-0005 static default, still a valid fallback for any
            # non-"orchestrator" value there. Keep this set in sync with routing.py, not with
            # whichever one the registry happened to say last (C26).
            _REASONER_POLICY_VALUES = ("orchestrator", "highest")
            if (
                isinstance(policy, dict)
                and policy.get("reasoner") in _REASONER_POLICY_VALUES
                and policy.get("worker") == "lowest"
            ):
                self.ok(
                    "routing.selection-policy",
                    f"model-routing {vendor} semantic selection policy exists",
                    target=f"tools/model_routing/registry.json#{vendor}",
                    fix="Keep the semantic selection policy on this vendor.",
                )
            else:
                self.error(
                    "routing.selection-policy",
                    f"model-routing {vendor} needs semantic selection_policy with "
                    f"worker=lowest and reasoner in {_REASONER_POLICY_VALUES}",
                    target=f"tools/model_routing/registry.json#{vendor}",
                    fix=(
                        "Set this vendor's selection_policy to worker=lowest and reasoner in "
                        f"{_REASONER_POLICY_VALUES}."
                    ),
                )
            fallback = spec.get("semantic_fallback")
            fallback_keys = ("worker", "mid", "reasoner", "orchestrator")
            if isinstance(fallback, dict) and all(fallback.get(key) for key in fallback_keys):
                self.ok(
                    "routing.semantic-fallback",
                    f"model-routing {vendor} semantic fallback exists",
                    target=f"tools/model_routing/registry.json#{vendor}",
                    fix="Keep a model named for every tier in this vendor's semantic_fallback.",
                )
            else:
                self.error(
                    "routing.semantic-fallback",
                    f"model-routing {vendor} semantic_fallback must name worker/mid/reasoner/orchestrator",
                    target=f"tools/model_routing/registry.json#{vendor}",
                    fix="Name a model for each of worker, mid, reasoner and orchestrator in semantic_fallback.",
                )
            second = spec.get("second_opinion")
            if not isinstance(second, dict):
                self.error(
                    "routing.second-opinion",
                    f"model-routing {vendor} second_opinion is missing",
                    target=f"tools/model_routing/registry.json#{vendor}",
                    fix="Add a second_opinion object with harness, operation and report_dir to this vendor.",
                )
                continue
            missing = [key for key in ("harness", "operation", "report_dir") if not second.get(key)]
            if missing:
                self.error(
                    "routing.second-opinion",
                    f"model-routing {vendor} second_opinion missing: {', '.join(missing)}",
                    target=f"tools/model_routing/registry.json#{vendor}",
                    fix="Fill in the listed second_opinion keys for this vendor.",
                )
            else:
                self.ok(
                    "routing.second-opinion",
                    f"model-routing {vendor} second_opinion is configured",
                    target=f"tools/model_routing/registry.json#{vendor}",
                    fix="Keep harness, operation and report_dir set for this vendor's second_opinion.",
                )

    def check_gitignore(self) -> None:
        path = self.root / ".gitignore"
        if not path.is_file():
            self.warn(
                "gitignore.env-secrets",
                ".gitignore is missing",
                target=".gitignore",
                fix="Add a .gitignore ignoring '*.env' while keeping '!*.env.example'.",
            )
            return
        text = path.read_text(encoding="utf-8")
        if "*.env" in text and "!*.env.example" in text:
            self.ok(
                "gitignore.env-secrets",
                ".gitignore has the akmon env secret pattern",
                target=".gitignore",
                fix="Keep the '*.env' and '!*.env.example' patterns in .gitignore.",
            )
        else:
            self.warn(
                "gitignore.env-secrets",
                ".gitignore should include '*.env' and '!*.env.example'",
                target=".gitignore",
                fix="Add '*.env' and '!*.env.example' to .gitignore.",
            )

    def check_akmon_gitignore(self) -> None:
        """Warn when the akmon submodule has no .gitignore ignoring __pycache__.

        The bin/ and tools/ Python is run in-tree, so without this a release commit cut from
        the submodule sweeps in __pycache__/ noise (surfaced as a manual finding during the
        v0.1.0 cut). A missing akmon .gitignore is a warning, not an error — akmon may
        be vendored read-only — but a present one should ignore the bytecode caches.
        """
        akmon = self.root / self.akmon
        if not akmon.is_dir():
            return
        path = akmon / ".gitignore"
        if not path.is_file():
            self.warn(
                "gitignore.akmon-pycache",
                f"{self.akmon}/.gitignore is missing; add one ignoring __pycache__/",
                target=f"{self.akmon}/.gitignore",
                fix=f"Add {self.akmon}/.gitignore ignoring __pycache__/.",
            )
            return
        if "__pycache__" in path.read_text(encoding="utf-8"):
            self.ok(
                "gitignore.akmon-pycache",
                "akmon .gitignore ignores __pycache__",
                target=f"{self.akmon}/.gitignore",
                fix="Keep __pycache__/ ignored in the akmon .gitignore.",
            )
        else:
            self.warn(
                "gitignore.akmon-pycache",
                f"{self.akmon}/.gitignore should ignore __pycache__/",
                target=f"{self.akmon}/.gitignore",
                fix=f"Add __pycache__/ to {self.akmon}/.gitignore.",
            )

    def check_ci(self) -> None:
        workflow_dir = self.root / ".github" / "workflows"
        workflows = sorted(workflow_dir.glob("*.yml")) + sorted(workflow_dir.glob("*.yaml"))
        if not workflows:
            self.warn(
                "ci.akmon-checks",
                "no GitHub Actions workflows found",
                target=".github/workflows",
                fix="Add a workflow running the akmon sync and verify checks.",
            )
            return
        workflow_text = "\n".join(path.read_text(encoding="utf-8") for path in workflows)
        if sync_tool.is_package_mode(self.root):
            # Pinned package-mode contract: the CLI, not a path into a mount that doesn't
            # exist (ADR 0009 §4). Substring match so `uv run akmon sync --check` etc. pass.
            required = ("akmon sync --check", "akmon verify --strict")
        else:
            required = (
                f"python3 {self.akmon}/bin/sync.py --check",
                f"python3 {self.akmon}/bin/verify.py --strict",
            )
        missing = [command for command in required if command not in workflow_text]
        if missing:
            self.warn(
                "ci.akmon-checks",
                f"CI should run: {', '.join(missing)}",
                target=".github/workflows",
                fix="Add the listed akmon commands to a CI workflow step.",
            )
        else:
            self.ok(
                "ci.akmon-checks",
                "CI checks akmon generated pointers and verify",
                target=".github/workflows",
                fix="Keep the akmon sync and verify commands in CI.",
            )

    def check_changelog(self) -> None:
        """Warn when akmon's CHANGELOG.md exists without an `Unreleased` section.

        Keeps the "consumer-visible change ⇒ changelog entry" discipline mechanical rather than
        trust-based (ADR 0001 §9). A missing CHANGELOG.md is not an error here — only a present
        one that has nowhere to record pending changes.
        """
        if sync_tool.is_package_mode(self.root):
            # Standard-internal discipline concern (the standard's own changelog, not this
            # consumer's integration surface) — not meaningful to re-check per consumer.
            self.ok(
                "changelog.package-mode",
                "package mode: changelog discipline is owned by the akmon repository",
                fix="Track the standard's changelog discipline in the akmon repository itself.",
            )
            return
        path = self.root / self.akmon / "CHANGELOG.md"
        if not path.is_file():
            return
        text = path.read_text(encoding="utf-8")
        if re.search(r"^##\s+Unreleased\b", text, re.MULTILINE | re.IGNORECASE):
            self.ok(
                "changelog.unreleased",
                "CHANGELOG.md has an Unreleased section",
                target=f"{self.akmon}/CHANGELOG.md",
                fix="Keep an `## Unreleased` heading for pending changes.",
            )
        else:
            self.warn(
                "changelog.unreleased",
                "CHANGELOG.md has no `## Unreleased` section; add one for pending changes",
                target=f"{self.akmon}/CHANGELOG.md",
                fix="Add an `## Unreleased` heading above the latest release.",
            )

    def check_package_pin(self) -> None:
        """In mount mode ``package``, the consumer's manifest must pin akmon in a **dev** group.

        Package mode mounts no tree, so that declaration *is* the pin (ADR 0009 §4): without it
        `uv run akmon ...` cannot resolve and the CI commands this same file checks for cannot
        run at all — the project looks attached and nothing works. The class is locked too: a
        runtime dependency (or an extra, which ships with the distribution) pushes dev tooling
        onto the consumer's own users, so it is an error rather than a warning.

        Only checked when a ``pyproject.toml`` exists: a non-Python consumer has no manifest to
        pin in and stays a design open point (meta/design/packaging/README.md §Open points), not a finding.
        """
        if not sync_tool.is_package_mode(self.root):
            return
        if not (self.root / "pyproject.toml").is_file():
            return
        status = sync_tool.package_pin_status(self.root)
        if status == "runtime":
            self.error(
                "package.dev-pin",
                "pyproject.toml pins akmon as a runtime dependency (or an extra); it is dev "
                "tooling and belongs in a dev group (ADR 0009 §4)",
                target="pyproject.toml",
                fix="Move the akmon requirement into a dev dependency group.",
            )
        elif status == "none":
            self.warn(
                "package.dev-pin",
                "package mode: pyproject.toml does not pin akmon in a dev group — "
                "`akmon` cannot resolve here, so the CI checks above cannot run",
                target="pyproject.toml",
                fix="Pin akmon in a dev dependency group so the akmon command resolves.",
            )
        else:
            self.ok(
                "package.dev-pin",
                "pyproject.toml pins akmon in a dev group",
                target="pyproject.toml",
                fix="Keep akmon pinned in a dev dependency group.",
            )

    def check_attach_record(self) -> None:
        """Validate the `_aitna/.akmon.toml` integration record *of a consuming project*.

        It is the "where the project is" anchor that BOOTSTRAP §B2 diffs against akmon's
        CHANGELOG to compute which Breaking/migration entries a realign still needs to verify.
        The agent writes it on attach/realign (sync.py is stdlib-only and cannot run `git describe`).

        It is a **consumer** artifact, so this check applies when akmon is mounted as a
        submodule (`<AITNA_ROOT>/akmon/` present) *or* the record itself exists (package
        mode has no mount at all, ADR 0009 §4 — `.akmon.toml` is the only trace a
        package-mode consumer leaves) — verify run against the akmon repo itself (no mount,
        no record) skips it. Even on a consumer, a *missing* record is a non-gating note (the
        project may predate this contract; the fix is a realign), so it never fails
        `--strict`; only a *present but malformed* record — missing the required top-level
        keys — is an error.
        """
        name = f"{self.aitna}/.akmon.toml"
        path = self.root / self.aitna / ".akmon.toml"
        if not (self.root / self.akmon).is_dir() and not path.is_file():
            return  # akmon repo itself, or not a akmon consumer — no integration record expected
        if not path.is_file():
            self.ok(
                "attach.record",
                f"{name} not present (optional; a realign writes it so future "
                "bumps can diff the CHANGELOG — BOOTSTRAP §B2)",
                target=name,
                fix=f"Run a realign when you next bump akmon so {name} is written.",
            )
            return
        fields = sync_tool.read_akmon_toml(path)
        required = ("akmon_version", "attached_archetype", "last_realign")
        missing = [key for key in required if not fields.get(key)]
        if missing:
            self.error(
                "attach.record",
                f"{name} is missing required key(s): {', '.join(missing)}",
                target=name,
                fix=f"Add the listed keys to {name} by re-running a realign.",
            )
        else:
            self.ok(
                "attach.record",
                f"{name} records akmon version {fields['akmon_version']}",
                target=name,
                fix=f"Refresh {name} on every akmon bump.",
            )

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
        self.check_hook_launcher()
        self.check_model_routing()
        self.check_gitignore()
        self.check_akmon_gitignore()
        self.check_ci()
        self.check_changelog()
        self.check_package_pin()
        self.check_attach_record()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, help="Project root. Defaults to cwd or a parent with AGENTS.md.")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    parser.add_argument("--quiet", action="store_true", help="Only print warnings and errors.")
    args = parser.parse_args(argv)

    root, root_notice = resolve_project_root(args.project_root)
    if root_notice:
        print(root_notice, file=sys.stderr)
    verify = Verifier(root)
    verify.run()
    print_findings(verify.findings, quiet=args.quiet)
    return exit_code(verify.findings, strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
