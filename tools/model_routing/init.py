#!/usr/bin/env python3
"""Initialize model routing for a akmon-consuming project.

Computes the tier→model binding from the registry's selection policy over the vendor's
committed harness ladder (or an ``--available`` list), relative to the orchestrating model,
and writes the generated artifacts:

- ``.claude/agents/k_*.md`` — subagent definitions (per-user, gitignored: the frontmatter
  pins each delegate to a model chosen for *this* session's orchestrator, and the
  SessionStart hook rewrites them whenever it changes, so committing one would commit
  somebody else's session. Concrete ``model:`` frontmatter is emitted whenever a ladder
  binds — the vendor's committed one or ``--available`` — and omitted only for a vendor
  with neither);
- ``.claude/model-routing.local.json`` — the resolved binding + second-opinion opt-in +
  the optional ``session`` stanza (the harness, model and priors the session runs on, recorded with
  ``--session-provider``/``--session-model``/``--session-family``) + registry hash (per-user, gitignored like ``.env``).

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
# mounted tree and from the materialized ``<dev root>/.akmon/`` copy alike.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import routing

from common.project_root import resolve_project_root
from common.record import records_package_mode


def _standard_tree_root(project_root: Path) -> Path:
    """The tree this script reads ``registry.json`` from: the mount for mounted modes, this script's own tree otherwise.

    (ADR 0009 §4, mirroring ``bin/sync.py::standard_tree_root``.) In package mode that own tree
    is either the materialized ``<dev root>/.akmon/`` copy or the installed package's
    embedded tree, whichever this file was executed from — both carry
    ``tools/model_routing/registry.json``. The recorded ``mount`` field decides, never the mere
    presence of the directory: a stale ``<dev root>/akmon`` left over from a prior mode must
    not shadow the pin.
    """
    if not records_package_mode(project_root):
        mounted = routing.aitna_root(project_root) / "akmon"
        if mounted.is_dir():
            return mounted
    return Path(__file__).resolve().parents[2]


def _settings_model(project_root: Path) -> str | None:
    """The harness default model, when the settings record one (local settings win)."""
    for name in routing.settings_probe_names():
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
    path = project_root / routing.local_config_rel()
    if not path.is_file():
        return {}
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return config if isinstance(config, dict) else {}


def _existing_second_opinion(project_root: Path) -> bool:
    return bool(_existing_config(project_root).get("second_opinion"))


def _session_stanza(args: argparse.Namespace, registry: dict, existing: dict, root: Path) -> dict | None:
    """The ``session`` stanza to record: the flags over the one already recorded, else none.

    Record only: it names the harness, model and priors the session runs on so the second opinion
    knows which carrier to skip and which family to differ from, and gives the harness no tier
    binding (tier binding stays owned by a vendor block: ``--vendor`` selects the one a harness with
    none borrows). A model or family with no provider borrows the recorded one, else the vendor's
    ``carrier``; a provider alone keeps the recorded model only when it is the same provider, and a
    recorded family only while the model is unchanged — the family belongs to the model (D15). A
    ``--session-family`` outside the closed vocabulary is refused (D01).
    """
    recorded = existing.get("session")
    recorded = recorded if isinstance(recorded, dict) else {}
    if not (args.session_provider or args.session_model or args.session_family):
        return dict(recorded) or None
    if args.session_family:
        routing.check_session_family(registry, args.session_family, root)
    vendor_block = registry.get(args.vendor)
    carrier = vendor_block.get("carrier") if isinstance(vendor_block, dict) else None
    provider = args.session_provider or recorded.get("provider") or carrier
    if not provider:
        flag = "--session-model" if args.session_model else "--session-family"
        raise ValueError(f"{flag} needs a provider: pass --session-provider, {args.vendor!r} declares no carrier")
    same_provider = recorded.get("provider") == provider
    model = args.session_model or (recorded.get("model") if same_provider else None)
    family = args.session_family or (
        recorded.get("family") if same_provider and model == recorded.get("model") else None
    )
    stanza = {"provider": str(provider)}
    if model:
        stanza["model"] = str(model)
    if family:
        stanza["family"] = str(family)
    return stanza


def _require_vendor(parser: argparse.ArgumentParser, registry: dict, vendor: str) -> None:
    """Exit with a usage error unless ``vendor`` has a routing policy; a carrier's id is told where to start."""
    vendors = routing.vendors_with_routing_policy(registry)
    if vendor not in vendors:
        parser.error(routing.vendor_refusal(registry, vendor, vendors))


def _binding_inputs(args: argparse.Namespace, registry: dict, root: Path) -> tuple[list[str] | None, str]:
    """The validated ``--available`` list and the orchestrator alias; ``ValueError`` names a refused flag.

    The orchestrator is ``--orchestrator``, else the settings model, else the top of the ladder
    (the vendor's committed one without ``--available``), else the semantic label.
    """
    available = [alias.strip() for alias in args.available.split(",") if alias.strip()] if args.available else None
    if available:
        routing.check_ladder_order(registry, args.vendor, available)
    if args.auditor:
        routing.check_auditor_opt_in(registry, args.vendor, available, args.auditor)
    rungs, semantic = routing.selection_ladder(registry, args.vendor, available)
    fallback = registry[args.vendor].get("semantic_fallback", {})
    orchestrator = (
        args.orchestrator
        or _settings_model(root)
        or (fallback.get("orchestrator", "strongest") if semantic else rungs[-1])
    )
    return available, orchestrator


def _write_planned(root: Path, planned: dict[Path, str], *, write: bool) -> list[Path]:
    """Report each planned file as ``ok`` / ``updated`` / ``would update``, writing the changed ones when asked."""
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
    return changed


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
    parser.add_argument(
        "--available",
        help="Comma-separated model aliases available in the harness, weakest first; "
        "defaults to the vendor's committed ladder.",
    )
    parser.add_argument(
        "--auditor",
        help="Opt in to this rung as the auditor: an auditor-only rung of the vendor (e.g. fable) "
        "or one of its ladder; with --available it must be listed there.",
    )
    parser.add_argument("--second-opinion", choices=("on", "off"), help="Enable second-opinion review (opt-in).")
    parser.add_argument(
        "--session-provider",
        help="Record the provider (harness) the session runs on, so the second opinion skips it; "
        "record only — it binds no tiers.",
    )
    parser.add_argument("--session-model", help="Record the model the session runs on (with --session-provider).")
    parser.add_argument(
        "--session-family",
        help="Record the priors (model family) the session answers with; it must be in the family vocabulary "
        "(second_opinion_policy.families), which an overlay may extend.",
    )
    parser.add_argument("--check", action="store_true", help="Do not write; exit 1 when generated files are stale.")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing them.")
    args = parser.parse_args(argv)

    root, root_notice = resolve_project_root(args.project_root)
    if root_notice:
        print(root_notice, file=sys.stderr)
    akmon_dir = _standard_tree_root(root)
    try:
        registry = routing.load_registry(akmon_dir, root)
    except routing.OverlayError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _require_vendor(parser, registry, args.vendor)
    try:
        available, orchestrator = _binding_inputs(args, registry, root)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    second_opinion = _existing_second_opinion(root) if args.second_opinion is None else args.second_opinion == "on"

    try:
        routing.refuse_retired_keys(registry, {}, root, layered=True)
        session = _session_stanza(args, registry, _existing_config(root), root)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    binding = routing.compute_binding(registry, orchestrator, available, args.vendor, args.auditor or None)
    try:
        artifacts = routing.binding_artifacts(
            registry, binding, second_opinion=second_opinion, available=available, session=session
        )
    except routing.BriefError as exc:
        # Nothing is written: generating the definitions without the overlay's briefs would
        # drop hand-authored project instructions, and the sweep below would then delete the
        # only files still carrying them (C50).
        print(f"error: {exc}", file=sys.stderr)
        print(f"error: fix {routing.overlay_path(root).relative_to(root)}; no files were written", file=sys.stderr)
        return 2
    planned: dict[Path, str] = {root / rel: content for rel, content in artifacts.items()}

    write = not args.check and not args.dry_run
    changed = _write_planned(root, planned, write=write)

    for path in routing.remove_obsolete_agents(root, planned, write=write):
        changed.append(path)
        print(f"{'would delete' if not write else 'deleted'}: {path.relative_to(root)}")

    head, _ = routing.opinion_head(registry, json.loads(artifacts[routing.local_config_rel()]), root)
    print(
        "model routing: "
        f"vendor={binding.vendor} · orchestrator={binding.orchestrator} · reasoner={binding.reasoner} · "
        f"auditor={binding.auditor} · "
        f"worker={binding.worker} · mid={binding.mid} · "
        f"second-opinion={head} ({'on' if second_opinion else 'off'})"
    )
    if binding.warning:
        print(f"⚠ {binding.warning}")
    if args.check and changed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
