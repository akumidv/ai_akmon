#!/usr/bin/env python3
"""Initialize model routing for a keystone-consuming project.

Computes the tier→model binding from the registry's semantic selection policy (relative
to the orchestrating model) and writes the generated artifacts:

- ``.claude/agents/k-*.md`` — subagent definitions (committed; concrete ``model:``
  frontmatter is emitted only when local model discovery / ``--available`` provides
  concrete aliases);
- ``.claude/model-routing.local.json`` — the resolved binding + second-opinion opt-in +
  registry hash (per-user, gitignored like ``.env``).

Stdlib-only and idempotent: re-running with the same inputs changes nothing. The registry
(``registry.json``) plus the optional project overlay (``<forge-root>/model-routing.json``)
are the data to edit — never the generated files.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import routing


def _find_project_root(start: Path) -> Path:
    forge = routing.forge_root_name()
    for candidate in (start, *start.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / forge / "keystone").exists():
            return candidate
    return start


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

    root = (args.project_root or _find_project_root(Path.cwd())).resolve()
    keystone_dir = root / routing.forge_root_name() / "keystone"
    registry = routing.load_registry(keystone_dir, root)
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
    if args.second_opinion is None:
        second_opinion = _existing_second_opinion(root)
    else:
        second_opinion = args.second_opinion == "on"

    binding = routing.compute_binding(registry, orchestrator, available, args.vendor)
    planned: dict[Path, str] = {
        root / rel: content for rel, content in routing.generated_agent_files(registry, binding).items()
    }
    config = routing.local_config(binding, registry, second_opinion=second_opinion, available=available)
    planned[root / routing.LOCAL_CONFIG_REL] = json.dumps(config, indent=2) + "\n"

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

    print(
        "model routing: "
        f"vendor={binding.vendor} · orchestrator={binding.orchestrator} · reasoner={binding.reasoner} · "
        f"synthesizer={binding.synthesizer} · "
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
