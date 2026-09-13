#!/usr/bin/env python3
"""Initialize model routing for a akmon-consuming project.

Computes the tier→model binding from the registry's semantic selection policy (relative
to the orchestrating model) and writes the generated artifacts:

- ``.claude/agents/k_*.md`` — subagent definitions (per-user, gitignored: the frontmatter
  pins each delegate to a model chosen for *this* session's orchestrator, and the
  SessionStart hook rewrites them whenever it changes, so committing one would commit
  somebody else's session. Concrete ``model:`` frontmatter is emitted only when local model
  discovery / ``--available`` provides concrete aliases);
- ``.claude/model-routing.local.json`` — the resolved binding + second-opinion opt-in +
  registry hash (per-user, gitignored like ``.env``).

Stdlib-only and idempotent: re-running with the same inputs changes nothing. The registry
(``registry.json``) plus the optional project overlay (``<aitna-root>/model-routing.json``)
are the data to edit — never the generated files.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# The tree root, so the shared ``common`` package resolves: it holds the single owner of
# project-root discovery (C73) and is reachable at the same tree-relative depth from the
# mounted tree and from the materialized ``<AITNA_ROOT>/.akmon/`` copy alike.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import routing

from common.project_root import resolve_project_root
from common.record import records_package_mode


def _standard_tree_root(project_root: Path) -> Path:
    """The tree this script reads ``registry.json`` from: the mount for mounted modes, this script's own tree otherwise.

    (ADR 0009 §4, mirroring ``bin/sync.py::standard_tree_root``.) In package mode that own tree
    is either the materialized ``<AITNA_ROOT>/.akmon/`` copy or the installed package's
    embedded tree, whichever this file was executed from — both carry
    ``tools/model_routing/registry.json``. The recorded ``mount`` field decides, never the mere
    presence of the directory: a stale ``<AITNA_ROOT>/akmon`` left over from a prior mode must
    not shadow the pin.
    """
    aitna = project_root / routing.aitna_root_name()
    if not records_package_mode(project_root):
        mounted = aitna / "akmon"
        if mounted.is_dir():
            return mounted
    return Path(__file__).resolve().parents[2]


def _settings_model(project_root: Path) -> str | None:
    """The harness default model, when the settings record one (local settings win)."""
    for name in ("settings.local.json", "settings.json"):
        path = project_root / ".claude" / name
        if not path.is_file():
            continue
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        model = settings.get("model") if isinstance(settings, dict) else None
        if isinstance(model, str) and model:
            return model
    return None


def _existing_config(project_root: Path) -> dict:
    path = project_root / routing.LOCAL_CONFIG_REL
    if not path.is_file():
        return {}
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return config if isinstance(config, dict) else {}


def _existing_second_opinion(project_root: Path) -> bool:
    return bool(_existing_config(project_root).get("second_opinion"))


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: compute the binding and write (or check) the generated routing artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, help="Project root. Defaults to cwd or a parent with AGENTS.md.")
    parser.add_argument(
        "--vendor",
        default="anthropic",
        help="Orchestrator vendor selection policy to use (default: anthropic).",
    )
    parser.add_argument("--orchestrator", help="Alias of the model the session runs on (only the agent knows it).")
    parser.add_argument("--available", help="Comma-separated model aliases available in the harness.")
    parser.add_argument("--second-opinion", choices=("on", "off"), help="Enable cross-vendor review (opt-in).")
    parser.add_argument("--check", action="store_true", help="Do not write; exit 1 when generated files are stale.")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing them.")
    args = parser.parse_args(argv)

    root, root_notice = resolve_project_root(args.project_root)
    if root_notice:
        print(root_notice, file=sys.stderr)
    akmon_dir = _standard_tree_root(root)
    registry = routing.load_registry(akmon_dir, root)
    vendors = routing.vendors_with_routing_policy(registry)
    if args.vendor not in vendors:
        parser.error(f"--vendor must be one of: {', '.join(vendors)}")
    available = [alias.strip() for alias in args.available.split(",") if alias.strip()] if args.available else None
    fallback = registry[args.vendor].get("semantic_fallback", {})
    orchestrator = (
        args.orchestrator
        or _settings_model(root)
        or (available[-1] if available else fallback.get("orchestrator", "strongest"))
    )
    second_opinion = _existing_second_opinion(root) if args.second_opinion is None else args.second_opinion == "on"

    binding = routing.compute_binding(registry, orchestrator, available, args.vendor)
    try:
        artifacts = routing.binding_artifacts(registry, binding, second_opinion=second_opinion, available=available)
    except routing.BriefError as exc:
        # Nothing is written: generating the definitions without the overlay's briefs would
        # drop hand-authored project instructions, and the sweep below would then delete the
        # only files still carrying them (C50).
        print(f"error: {exc}", file=sys.stderr)
        print(f"error: fix {routing.overlay_path(root).relative_to(root)}; no files were written", file=sys.stderr)
        return 2
    planned: dict[Path, str] = {root / rel: content for rel, content in artifacts.items()}

    write = not args.check and not args.dry_run
    changed = []
    for path, content in planned.items():
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == content:
            print(f"ok: {path.relative_to(root)}")
            continue
        changed.append(path)
        action = "would update" if not write else "updated"
        print(f"{action}: {path.relative_to(root)}")
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    for path in routing.remove_obsolete_agents(root, planned, write=write):
        changed.append(path)
        print(f"{'would delete' if not write else 'deleted'}: {path.relative_to(root)}")

    print(
        "model routing: "
        f"vendor={binding.vendor} · orchestrator={binding.orchestrator} · reasoner={binding.reasoner} · "
        f"auditor={binding.auditor} · "
        f"worker={binding.worker} · mid={binding.mid} · "
        f"second-opinion={binding.second_opinion_cli or '-'}({'on' if second_opinion else 'off'})"
    )
    if binding.warning:
        print(f"⚠ {binding.warning}")
    if args.check and changed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
