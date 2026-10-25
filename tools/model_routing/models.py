#!/usr/bin/env python3
"""Refresh the concrete ids behind a provider's model aliases, on request only (ADR 0024/D16).

A provider row that says ``aliases: true`` ships unversioned aliases (``luna``, ``terra``, ``sol``)
that its carrier may not accept; the second-opinion runner sends the concrete id kept in the local,
generated file ``<aitna_root>/local/model-aliases.json``. This tool is the ONE place that reads a
carrier's catalog — the file the row's ``catalog`` declares — and it reads it only when an owner runs
it: ``--refresh`` writes the file, no flag lists what is stored and what a refresh would write, and
``--dry-run`` previews a refresh. It never calls a carrier and never guesses an id for an alias the
catalog does not list.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# The tree root, so the shared ``common`` package resolves (see ``second_opinion.py``).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import routing

from common import jsondata
from common.project_root import resolve_project_root
from common.record import records_package_mode


def _texts() -> dict:
    """The tool's texts (``models.json``), read on the call that needs them."""
    return jsondata.read(Path(__file__).parent / "models.json")


def _standard_tree_root(project_root: Path) -> Path:
    """The tree ``registry.json`` is read from: the mount for mounted modes, this script's own tree otherwise.

    The rule of ``init.py::_standard_tree_root``: the recorded ``mount`` field decides, so a stale
    mount directory from a prior mode does not shadow the installed tree.
    """
    mounted = project_root / routing.aitna_root_name() / "akmon"
    if not records_package_mode(project_root) and mounted.is_dir():
        return mounted
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class _Plan:
    """What a refresh would store for one provider, and which of its aliases the catalog left unmapped."""

    provider: str
    entry: routing.ProviderAliases
    unmapped: tuple[str, ...]


def _catalog_declaration(registry: dict, provider: str) -> tuple[str, str]:
    """The row's ``catalog`` as ``(file, format)``; ``ValueError`` when the row has none or it is malformed."""
    texts = _texts()["errors"]
    declared = routing.provider_row(registry, provider).get("catalog")
    if declared is None:
        raise ValueError(jsondata.fill(texts["no_catalog"], {"provider": provider}))
    file = declared.get("file") if isinstance(declared, dict) else None
    catalog_format = declared.get("format") if isinstance(declared, dict) else None
    if not isinstance(file, str) or not isinstance(catalog_format, str):
        raise ValueError(jsondata.fill(texts["bad_catalog"], {"provider": provider}))
    return file, catalog_format


def _plan(registry: dict, provider: str, home: str) -> _Plan:
    """Read the provider's declared catalog and map each of the row's aliases; the only read of a catalog."""
    texts = _texts()["errors"]
    file, catalog_format = _catalog_declaration(registry, provider)
    values = {"file": file, "provider": provider}
    path = Path(routing.expand_home(file, home))
    if not path.is_file():
        raise ValueError(jsondata.fill(texts["missing"], values))
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(jsondata.fill(texts["unreadable"], values)) from exc
    try:
        catalog = routing.parse_catalog(text, catalog_format)
    except ValueError as exc:
        raise ValueError(jsondata.fill(texts["invalid"], {**values, "reason": exc.args[0]})) from exc
    entries = routing.provider_row(registry, provider).get("models") or []
    # An entry may carry an @effort (ADR 0024/D17); the alias is the model before it, listed once.
    models = list(dict.fromkeys(model for model in (routing.split_model_effort(str(e))[0] for e in entries) if model))
    mapped = routing.catalog_aliases(catalog, models)
    entry = routing.ProviderAliases(f"{file} ({catalog_format})", catalog.client, mapped)
    return _Plan(provider, entry, tuple(model for model in models if model not in mapped))


def _selected(registry: dict, provider: str | None) -> list[str]:
    """The providers a run covers: the named one, else every row that declares a ``catalog``."""
    if provider is not None:
        if provider not in routing.providers(registry):
            raise ValueError(jsondata.fill(_texts()["errors"]["unknown_provider"], {"provider": provider}))
        return [provider]
    declared = [name for name, row in routing.providers(registry).items() if isinstance(row, dict) and "catalog" in row]
    if not declared:
        raise ValueError(_texts()["errors"]["none_declared"])
    return declared


def _entry_lines(
    provider: str, entry: routing.ProviderAliases, label: str, unmapped: tuple[str, ...] = ()
) -> list[str]:
    """One provider's block: its header line (``label`` says stored or catalog) and one line per alias."""
    output = _texts()["output"]
    client = entry.client if entry.client is not None else output["client_unknown"]
    lines = [jsondata.fill(output[label], {"provider": provider, "source": entry.source, "client": client})]
    lines += [
        jsondata.fill(output["mapped"], {"alias": alias, "concrete": concrete})
        for alias, concrete in entry.aliases.items()
    ]
    lines += [jsondata.fill(output["unmapped"], {"alias": alias}) for alias in unmapped]
    return lines


def _stored_lines(stored: Mapping[str, routing.ProviderAliases], providers: list[str]) -> list[str]:
    """What the local file holds for each of ``providers``."""
    lines: list[str] = []
    for provider in providers:
        entry = stored.get(provider)
        if entry is None:
            lines.append(jsondata.fill(_texts()["output"]["stored_none"], {"provider": provider}))
        else:
            lines += _entry_lines(provider, entry, "stored")
    return lines


def _build_parser() -> argparse.ArgumentParser:
    """The command line: refresh or list, which provider, and whether a refresh only previews."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, help="Project root. Defaults to cwd or a parent with AGENTS.md.")
    parser.add_argument("--refresh", action="store_true", help="Write the resolved aliases from the declared catalog.")
    parser.add_argument("--provider", help="Cover this provider only; default: every row that declares a catalog.")
    parser.add_argument(
        "--dry-run", action="store_true", help="With --refresh: print what would be written, write nothing."
    )
    return parser


def _run(root: Path, registry: dict, args: argparse.Namespace, home: str) -> int:
    """Plan every selected provider (nothing is written unless all of them planned), then list, preview or write."""
    output = _texts()["output"]
    providers = _selected(registry, args.provider)
    plans = [_plan(registry, provider, home) for provider in providers]
    try:
        stored = routing.read_model_aliases(root)
    except ValueError:
        if not args.refresh:
            raise
        stored = {}  # a generated file that is not valid is replaced by a refresh, not repaired
    lines = [] if args.refresh else _stored_lines(stored, providers)
    for plan in plans:
        lines += _entry_lines(plan.provider, plan.entry, "catalog", plan.unmapped)
    document = routing.model_aliases_document({**stored, **{plan.provider: plan.entry for plan in plans}})
    relative = f"{routing.aitna_root_name()}/{routing.local_aliases_rel()}"
    changed = routing.write_artifacts(root, {relative: document}, write=args.refresh and not args.dry_run)
    if args.refresh and not args.dry_run:
        verdict = "wrote" if changed else "unchanged"
    else:
        verdict = "would_write" if changed else "would_leave"
    lines.append(jsondata.fill(output[verdict], {"file": relative}))
    print("\n".join(lines))
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: refresh the resolved aliases from the declared catalog, or list what is stored."""
    args = _build_parser().parse_args(argv)
    root, root_notice = resolve_project_root(args.project_root)
    if root_notice:
        print(root_notice, file=sys.stderr)
    home = os.environ.get("HOME") or str(Path.home())
    try:
        registry = routing.load_registry(_standard_tree_root(root), root)
        return _run(root, registry, args, home)
    except (ValueError, KeyError) as exc:
        print(f"models: {exc.args[0]}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
