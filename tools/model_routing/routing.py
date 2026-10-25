"""Model-routing core: registry loading, tier binding, generated-agent content.

Pure logic shared by the init tool (``init.py``) and the SessionStart hook
(``hooks/model-routing.py``). Stdlib-only; no I/O beyond reading the registry and the
optional project overlay. Vocabulary and policy: MODEL.md § Capability tiers; the
registry (``registry.json``) is the single owner of semantic selection policy +
task-kind data.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

# The optional-harness command map lives in the standard tree's ``bin/`` (C57, §7). Two parents
# up from ``tools/model_routing/`` is that tree root in every mount mode — the mounted
# ``<AITNA_ROOT>/akmon/`` and the materialized ``<AITNA_ROOT>/.akmon/`` alike — so this resolves
# without reading the mount record and stays clear of the tree-resolution fork (C69).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common import jsondata
from common.markers import claim_diagnostic_marker, release_diagnostic_markers
from common.project_root import aitna_root_name
from common.runtime import harness_command, harness_commands


def _agents_data() -> dict:
    """The shared routing texts and tables (``agents.json``), read on the call that needs it."""
    return jsondata.read(Path(__file__).parent / "agents.json")


def overlay_name() -> str:
    """Committed, per-project overlay file name (project-root-relative).

    Same shape as the registry, deep-merged over it; may add a "briefs" map with per-agent
    markdown appended to the generated subagent bodies — keyed by agent name, matched
    notation-insensitively, unmatched key is an error: see `resolve_briefs`.
    """
    return _agents_data()["overlay_name"]


def local_overlay_rel() -> str:
    """The developer-local overlay's path under the aitna root (gitignored with ``<aitna_root>/local/``)."""
    return _agents_data()["local_overlay_rel"]


def local_aliases_rel() -> str:
    """The generated resolved-aliases file's path under the aitna root (gitignored with ``<aitna_root>/local/``)."""
    return _agents_data()["local_aliases_rel"]


def default_model_token() -> str:
    """The reserved model token of the ``carrier[:model]`` grammar: ``carrier:default`` is the carrier's own model."""
    return _agents_data()["default_model_token"]


def local_config_rel() -> str:
    """Per-user resolved binding (gitignored, like .env) — written by init, read by the hook."""
    return _agents_data()["local_config_rel"]


def delegation_log_rel() -> str:
    """The delegation log the PreToolUse hook appends to (project-root-relative)."""
    return _agents_data()["delegation_log_rel"]


def agents_dir_rel() -> str:
    """The generated ``k_*`` subagent definitions' directory (project-root-relative)."""
    return _agents_data()["agents_dir_rel"]


def generated_banner() -> str:
    """The banner marking a generated agent file as machine-written — the obsolete sweep's gate."""
    return _agents_data()["generated_banner"]


def generated_banners() -> tuple[str, ...]:
    """Every banner a generated agent file may carry: the current one, then the ones earlier releases wrote.

    The obsolete sweep recognises all of them, so rewording the banner never turns an agent an
    earlier release generated into a hand-written one that nothing removes.
    """
    return (generated_banner(), *_agents_data()["generated_banners_earlier"])


def tool_command(runtime_root: str, tool: str) -> str:
    """How an agent runs ``tool`` (``model_routing/init``) from this implementation (ADR-0020/D06).

    ``runtime_root`` is ``hook_core.runtime_root_display``'s answer: from a mounted tree the
    tool is the mount's script (no CLI is installed there); from the wheel it is ``akmon tool``,
    the command the package installs.
    """
    texts = _agents_data()["tool_command"]
    if runtime_root == "$(akmon path)":
        return jsondata.fill(texts["python"], {"tool": tool})
    return jsondata.fill(texts["mount"], {"runtime_root": runtime_root, "tool": tool})


def settings_probe_names() -> tuple[str, ...]:
    """The ``.claude`` settings files the default-model probe reads, local first (single owner)."""
    return tuple(_agents_data()["settings_probe_names"])


def registry_path(akmon_dir: Path) -> Path:
    """Path to the shipped ``registry.json`` under an akmon tree."""
    return akmon_dir / "tools" / "model_routing" / "registry.json"


def overlay_path(project_root: Path) -> Path:
    """Path to the project's committed model-routing overlay file, if any."""
    return project_root / aitna_root_name() / overlay_name()


def local_overlay_path(project_root: Path) -> Path:
    """Path to the developer's own routing overlay (gitignored, hand-owned, never generated), if any.

    Same shape and file name as the project overlay, but under ``<aitna_root>/local/`` (ADR 0022):
    the strongest layer (ADR-0024/D11) — a developer states which harnesses and models they run
    without asking the team to share it.
    """
    return project_root / aitna_root_name() / local_overlay_rel()


def local_aliases_path(project_root: Path) -> Path:
    """Path to the generated resolved-aliases file (ADR-0024/D16), if any.

    Written only by ``tools/model_routing/models.py`` and never hand-owned: it maps each alias of an
    ``aliases: true`` provider row to the concrete id the carrier accepts on this machine.
    """
    return project_root / aitna_root_name() / local_aliases_rel()


class OverlayError(ValueError):
    """A routing overlay file is not a JSON object; the message names the file."""


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_overlay(path: Path, file: str) -> dict:
    """One overlay file's JSON object; anything else raises ``OverlayError`` naming ``file``."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise OverlayError(jsondata.fill(_agents_data()["overlay_errors"]["invalid"], {"file": file})) from exc
    if not isinstance(data, dict):
        raise OverlayError(jsondata.fill(_agents_data()["overlay_errors"]["invalid"], {"file": file}))
    return data


def _overlay_layers(project_root: Path) -> list[tuple[str, dict]]:
    """The overlay layers that exist, weakest first: the project overlay, then the developer's local one.

    Each is ``(project-root-relative file, parsed object)``; a missing file is no layer.
    """
    candidates = (
        (_overlay_file(), overlay_path(project_root)),
        (_local_overlay_file(), local_overlay_path(project_root)),
    )
    return [(file, _read_overlay(path, file)) for file, path in candidates if path.is_file()]


def load_registry(akmon_dir: Path, project_root: Path | None = None) -> dict:
    """The merged registry: akmon data, the project overlay, then the developer's local overlay (strongest).

    Dicts merge key by key and anything else — a list, hence a ``ladder`` — is replaced whole by the
    stronger layer (ADR-0024/D05, D11).
    """
    registry = json.loads(registry_path(akmon_dir).read_text(encoding="utf-8"))
    if project_root is not None:
        for _file, layer in _overlay_layers(project_root):
            registry = _deep_merge(registry, layer)
    return registry


def registry_hash(registry: dict) -> str:
    """Stable digest of the merged registry — staleness detection for the local config."""
    canonical = json.dumps(registry, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Binding:
    """The tier→model binding — a pure function of (selection policy, orchestrator, available)."""

    vendor: str
    orchestrator: str
    reasoner: str
    worker: str
    mid: str
    auditor: str
    escalation: tuple[str, ...]
    semantic_fallback: bool = False
    warning: str | None = None
    auditor_opt_in: str | None = None


def _semantic_rungs(vendor_data: dict) -> list[str]:
    fallback = vendor_data.get("semantic_fallback", {})
    worker = str(fallback.get("worker") or "worker")
    mid = str(fallback.get("mid") or "mid")
    reasoner = str(fallback.get("reasoner") or "strongest")
    auditor = str(fallback.get("auditor") or "strongest")
    rungs: list[str] = []
    for rung in (worker, mid, reasoner):
        if rung not in rungs:
            rungs.append(rung)
    if auditor not in rungs:
        rungs.append(auditor)
    return rungs


def selection_ladder(registry: dict, vendor: str, available: Sequence[str] | None) -> tuple[list[str], bool]:
    """The ladder ``vendor`` binds on, weakest to strongest, and whether it is the semantic one.

    A non-empty ``available`` list is the ladder, minus the vendor's auditor-only rungs (their
    order kept); otherwise the vendor's committed ``harness_rungs``; otherwise the semantic
    labels, flagged ``True`` (ADR-0004/D04). The single place that decides it — every caller
    that needs rungs asks here.
    """
    vendor_data = registry.get(vendor, {})
    if isinstance(available, list) and available:
        auditor_only = vendor_data.get("auditor_only_rungs") or []
        rungs = [alias for alias in available if alias not in auditor_only]
        if rungs:
            return rungs, False
    committed = vendor_data.get("harness_rungs")
    if committed:
        return list(committed), False
    return _semantic_rungs(vendor_data), True


def check_ladder_order(registry: dict, vendor: str, available: Sequence[str]) -> None:
    """Raise ``ValueError`` when ``available`` inverts the order of ``vendor``'s committed ladder.

    Only the aliases ``available`` shares with ``harness_rungs`` are ranked: an unknown alias or
    an auditor-only one never decides it, and a vendor with no committed ladder accepts any order.
    """
    committed = registry.get(vendor, {}).get("harness_rungs") or []
    shared = [alias for alias in available if alias in committed]
    if shared != sorted(shared, key=committed.index):
        raise ValueError(
            jsondata.fill(
                _agents_data()["ladder_errors"]["order"],
                {"given": ",".join(available), "vendor": vendor, "expected": ",".join(committed)},
            )
        )


def check_auditor_opt_in(registry: dict, vendor: str, available: Sequence[str] | None, alias: str) -> None:
    """Raise ``ValueError`` unless ``alias`` may be the opted-in auditor of ``vendor`` (ADR-0004/D04).

    It must be an auditor-only rung or a rung of the ladder, and when an ``available`` list is
    given it must be listed there.
    """
    rungs, semantic = selection_ladder(registry, vendor, available)
    auditor_only = list(registry.get(vendor, {}).get("auditor_only_rungs") or [])
    texts = _agents_data()["ladder_errors"]
    if alias not in [*auditor_only, *([] if semantic else rungs)]:
        raise ValueError(
            jsondata.fill(
                texts["auditor_unknown"],
                {
                    "alias": alias,
                    "vendor": vendor,
                    "ladder": ",".join([] if semantic else rungs),
                    "auditor_only": ",".join(auditor_only),
                },
            )
        )
    if available and alias not in available:
        raise ValueError(jsondata.fill(texts["auditor_unlisted"], {"alias": alias, "given": ",".join(available)}))


def compute_binding(
    registry: dict,
    orchestrator: str,
    available: list[str] | None = None,
    vendor: str = "anthropic",
    auditor_opt_in: str | None = None,
) -> Binding:
    """Bind tiers to model aliases from a semantic vendor policy (MODEL.md § Capability tiers).

    The ladder comes from ``selection_ladder``: ``available`` (the local, discovery-derived list,
    weakest → strongest, auditor-only rungs removed) or the vendor's committed ``harness_rungs``.
    A vendor with neither binds semantic labels with a warning; generated file-backed agents then
    omit concrete model frontmatter instead of pretending those labels are valid vendor model ids.
    The auditor is ``auditor_opt_in`` when given, else the top of the ladder; an auditor-only rung
    is never the worker, mid, reasoner or an escalation step (ADR-0004/D04).
    """
    vendor_data = registry[vendor]
    rungs, semantic = selection_ladder(registry, vendor, available)

    auditor = auditor_opt_in or rungs[-1]  # pinned max unless the owner opted in — unlike the now-dynamic reasoner
    worker = rungs[0]
    worker_pos = rungs.index(worker)
    mid = rungs[min(worker_pos + 1, len(rungs) - 1)]
    escalation = tuple(rungs[worker_pos + 1 : len(rungs) - 1])

    policy = vendor_data.get("selection_policy", {})
    reasoner_policy = policy.get("reasoner", "highest")
    if semantic:
        fallback = vendor_data.get("semantic_fallback", {})
        reasoner = str(fallback.get("reasoner") or "strongest")
    elif reasoner_policy == "orchestrator" and orchestrator in rungs:
        reasoner = orchestrator
    else:
        # Unknown orchestrator, or a non-"orchestrator" policy value (e.g. "highest") —
        # fall back to the top rung.
        reasoner = rungs[-1]

    warnings = _agents_data()["compute_binding_warnings"]
    warning = None
    if semantic:
        warning = warnings["semantic"]
    else:
        floor_rung = _corridor_floor(policy, rungs)
        if orchestrator not in rungs:
            warning = jsondata.fill(warnings["not_in_list"], {"orchestrator": orchestrator})
        elif floor_rung in rungs:
            # Healthy corridor: floor ≤ orchestrator < top (design §3, ADR 0006). When the
            # ladder tops out at the floor, floor == top and both arms stay silent — the
            # accepted degraded mode. A floor alias absent from the ladder disables the
            # check (nothing to rank against); the relative "highest" floor resolves to the
            # top rung, reproducing the pre-corridor below-top warning.
            orch_rank, floor_rank = rungs.index(orchestrator), rungs.index(floor_rung)
            if orch_rank < floor_rank:
                warning = jsondata.fill(warnings["below_floor"], {"orchestrator": orchestrator, "floor": floor_rung})
            elif orch_rank == len(rungs) - 1 and floor_rank < len(rungs) - 1:
                warning = jsondata.fill(warnings["reserved_top"], {"orchestrator": orchestrator, "floor": floor_rung})

    return Binding(
        vendor=vendor,
        orchestrator=orchestrator,
        reasoner=reasoner,
        worker=worker,
        mid=mid,
        auditor=auditor,
        escalation=escalation,
        semantic_fallback=semantic,
        warning=warning,
        auditor_opt_in=auditor_opt_in,
    )


def _corridor_floor(policy: dict, rungs: list[str]) -> str:
    """The corridor's lower bound on ``rungs``: ``orchestrator_floor``, ``"highest"`` the top rung.

    Not necessarily on the ladder — an alias the local ladder lacks disables the corridor.
    """
    floor = policy.get("orchestrator_floor", "highest")
    return rungs[-1] if floor == "highest" else str(floor)


def task_kind_floors(registry: dict, rungs: list[str], vendor: str = "anthropic") -> dict[str, str]:
    """Per-task-kind rung floors, resolved to concrete aliases from ``rungs``.

    Only task kinds carrying a ``"floor"`` key are included. ``"highest"`` resolves to
    ``rungs[-1]``; ``"orchestrator_floor"`` resolves to ``vendor``'s corridor floor
    (``selection_policy.orchestrator_floor``, itself ``"highest"`` or an alias) — the lowest
    rung the corridor accepts for the orchestrator, and so for the reasoner that follows it
    (C32: a healthy binding opens no gap); a literal alias passes through only when present in
    ``rungs``. A kind whose floor cannot be resolved (empty ``rungs``, or an alias absent from
    it) is skipped.
    """
    floors: dict[str, str] = {}
    if not rungs:
        return floors
    for kind, spec in registry.get("task_kinds", {}).items():
        floor = spec.get("floor")
        if not floor:
            continue
        if floor == "orchestrator_floor":
            floor = _corridor_floor(registry.get(vendor, {}).get("selection_policy", {}), rungs)
        resolved = _rung_floor(floor, rungs)
        if resolved is not None:
            floors[kind] = resolved
    return floors


def _rung_floor(floor: object, rungs: list[str]) -> str | None:
    """A ``"highest"`` or literal floor on ``rungs``, else None (an alias the ladder lacks)."""
    if floor == "highest":
        return rungs[-1]
    return str(floor) if floor in rungs else None


def vendors_with_routing_policy(registry: dict) -> list[str]:
    """Vendors that can run a main/orchestrator session under the semantic routing policy."""
    return [
        name
        for name, spec in registry.items()
        if isinstance(spec, dict) and isinstance(spec.get("selection_policy"), dict)
    ]


class RetiredKeyError(ValueError):
    """A configuration file still carries a key ADR 0024 retired; the message names the file and the keys."""


def retired_second_opinion_keys() -> dict[str, tuple[str, ...]]:
    """The keys the second-opinion rewrite retired, by where they live: ``policy``, ``vendor`` and ``config``.

    An overlay written before the change deep-merges *over* the shipped registry, so a stale
    key survives and rides along unread: the configuration looks usable and silently means something
    else. That is why each one is refused by name (``refuse_retired_keys``) instead of ignored.
    """
    return {scope: tuple(keys) for scope, keys in _agents_data()["retired_second_opinion_keys"].items()}


def _retired_overlay_keys(layer: dict) -> list[str]:
    """The retired keys one overlay-shaped dict still carries, policy first, then each block in order."""
    retired = retired_second_opinion_keys()
    found: list[str] = []
    policy = layer.get("second_opinion_policy")
    if isinstance(policy, dict):
        found += [f"second_opinion_policy.{key}" for key in retired["policy"] if key in policy]
    for name, spec in layer.items():
        if isinstance(spec, dict):
            found += [f"{name}.{key}" for key in retired["vendor"] if key in spec]
    return found


def refuse_retired_keys(registry: dict, config: dict, *, project_root: Path | None = None) -> None:
    """Raise ``RetiredKeyError`` naming the file when an overlay or the local config holds a retired key.

    The shipped registry carries none of them, so one found in the merged registry came from an
    overlay. With ``project_root`` each overlay file is read in turn, strongest first, and the error
    quotes the one that holds the key — the file to edit. Without it only the merged registry is
    known, so the error names both candidate files. The local config is a generated file, so its
    error says to regenerate it; an overlay is hand-owned, so its error says which keys to delete.
    """
    texts = _agents_data()["retired_key_errors"]
    if project_root is None:
        holders = [(f"{_local_overlay_file()} or {_overlay_file()}", _retired_overlay_keys(registry))]
    else:
        holders = [(file, _retired_overlay_keys(layer)) for file, layer in reversed(_overlay_layers(project_root))]
    for file, keys in holders:
        if keys:
            raise RetiredKeyError(jsondata.fill(texts["overlay"], {"file": file, "keys": ", ".join(keys)}))
    in_config = [key for key in retired_second_opinion_keys()["config"] if key in config]
    if in_config:
        raise RetiredKeyError(
            jsondata.fill(texts["config"], {"file": local_config_rel(), "keys": ", ".join(in_config)})
        )


class UnpinnableModelError(ValueError):
    """A second opinion asked for a model its provider declares no ``model_flag`` to pin (C97)."""

    def __init__(self, provider: str, model: str) -> None:
        super().__init__(
            jsondata.fill(_agents_data()["unpinnable_model"], {"model": repr(model), "provider": provider})
        )


# --------------------------------------------------------------------------------------
# The provider ladder (ADR-0024/D05-D12): one order, diversity tested on priors
# --------------------------------------------------------------------------------------

#: Rank 2 is the second opinion; 3 a third; 4 an arbiter. One walk answers them all (ADR-0024/D06).
OPINION_RANK_SECOND = 2


@dataclass(frozen=True)
class SecondOpinionTarget:
    """A resolved second-opinion target: which provider, which model to pin (if any), and whose priors answer."""

    provider: str
    model: str | None  # None = the carrier's own default model
    family: str | None = None  # the priors that answer (ADR-0024/D01); None = unknown (D08)
    effort: str | None = None  # the reasoning level sent with it (ADR-0024/D17); None = the carrier's own


@dataclass(frozen=True)
class SecondOpinionSession:
    """The working session as the ladder sees it: its carrier, the family that answers, its model."""

    provider: str
    family: str | None
    model: str | None = None


class SessionUnknownError(ValueError):
    """No source names the session's provider: an explicit argument, the ``session`` stanza or the bound vendor."""


def opinion_ladder(registry: dict) -> tuple[str, ...]:
    """The one flat ladder — team-committed, or replaced whole by the local overlay (ADR-0024/D05)."""
    policy = registry.get("second_opinion_policy")
    ladder = policy.get("ladder") if isinstance(policy, dict) else None
    return tuple(str(entry) for entry in ladder or ())


def providers(registry: dict) -> dict:
    """The provider table — the single owner of every provider row (ADR-0024/D02)."""
    rows = registry.get("providers")
    return rows if isinstance(rows, dict) else {}


def provider_row(registry: dict, provider: str) -> dict:
    """One row by id. A ladder id the table does not declare is a named error, never a silent skip.

    The error names the two overlay files that can hold the ladder (the developer's and the team's),
    the same placeholders an ask names, because the entry came from one of them (ADR-0024/D05).
    """
    row = providers(registry).get(provider)
    if isinstance(row, dict):
        return row
    values = {"provider": provider, "local_overlay": _local_overlay_file(), "overlay": _overlay_file()}
    raise KeyError(jsondata.fill(_agents_data()["opinion_ladder_unknown"], values))


def family_vocabulary(registry: dict) -> tuple[str, ...]:
    """The closed set of family names, in declared order: ``second_opinion_policy.families``' keys (ADR-0024/D01).

    An object, not a list, so an overlay adds a family by key without restating the shipped ones (a
    list would be replaced whole by the stronger layer). Closed means a family is named on purpose —
    a typo or a carrier name is not one — and extending it is a declaration in an overlay.
    """
    policy = registry.get("second_opinion_policy")
    families = policy.get("families") if isinstance(policy, dict) else None
    return tuple(str(name) for name in families) if isinstance(families, dict) else ()


def check_session_family(registry: dict, family: str) -> None:
    """Raise ``ValueError`` naming the files that extend the vocabulary when ``family`` is not in it."""
    known = family_vocabulary(registry)
    if family in known:
        return
    values = {
        "family": family,
        "known": ", ".join(known),
        "local_overlay": _local_overlay_file(),
        "overlay": _overlay_file(),
    }
    raise ValueError(jsondata.fill(_agents_data()["session_family_unknown"], values))


def vendor_refusal(registry: dict, vendor: str, vendors: Sequence[str]) -> str:
    """The usage error for a ``--vendor`` with no tier-binding block.

    A name the providers table declares is a carrier: it has no vendor block, so it cannot bind
    tiers, and the message says how to start from that harness instead (``--session-provider``, with
    ``--vendor`` still choosing the binding it borrows). Tier binding stays owned by a vendor block
    (ADR-0024/D15).
    """
    texts = _agents_data()
    key = "vendor_is_carrier" if vendor in providers(registry) else "vendor_unknown"
    return jsondata.fill(texts[key], {"vendor": vendor, "vendors": ", ".join(vendors)})


def hook_overlay_line(hook: str, error: OverlayError) -> str:
    """The one stderr line a hook prints for a bad hand-owned overlay: the hook, the file, what it costs."""
    texts = _agents_data()["hook_overlay_error"]
    effect = texts["effects"][hook]
    return jsondata.fill(texts["line"], {"hook": hook, "error": error.args[0], "effect": effect})


def split_opinion_entry(entry: str) -> tuple[str, str | None]:
    """A ``carrier[:model]`` entry as ``(provider, model)``, split on the FIRST colon only.

    A model id may itself hold ``/`` and ``:`` (``anthropic/claude-sonnet-4``, ``qwen3:8b``), so the
    carrier is whatever precedes the first colon and everything after it is the model.
    """
    provider, _, model = entry.partition(":")
    return provider, model or None


def split_model_effort(text: str | None) -> tuple[str | None, str | None]:
    """A ``model[@effort]`` text as ``(model, effort)``, split at its LAST ``@`` (ADR-0024/D17).

    A model id that itself encodes the level (``acme/qwen3.8-27b-max``) stays one id, because akmon
    never parses a model name; no ``@`` means no effort. An empty side is ``None`` for the model and
    kept as ``""`` for the effort, which no row lists, so ``m@`` is refused rather than ignored.
    """
    if text is None:
        return None, None
    model, at, effort = text.rpartition("@")
    if not at:
        return text or None, None
    return model or None, effort


def ladder_pins_default(registry: dict, provider: str) -> bool:
    """Whether a ladder entry names ``provider:default`` (with any effort) — the carrier's own model (ADR-0024/D16)."""
    token = default_model_token()
    for entry in opinion_ladder(registry):
        entry_provider, pinned = split_opinion_entry(entry)
        if entry_provider == provider and split_model_effort(pinned)[0] == token:
            return True
    return False


def provider_family(registry: dict, provider: str, model: str | None = None) -> str | None:
    """The priors that answer when ``provider`` runs ``model``: the model's own entry, else the row's, else unknown.

    A carrier that fronts several families (a gateway, a multi-provider harness) states each model's
    family in ``model_families``; a single-family carrier states ``family`` once. A model neither
    names resolves to ``None``, which the walk treats as unknown and fails closed (ADR-0024/D08) —
    guessing a family from the model id would be the silent weakness this record removes.
    """
    row = provider_row(registry, provider)
    families = row.get("model_families")
    if model and isinstance(families, dict) and families.get(model):
        return str(families[model])
    family = row.get("family")
    return str(family) if family else None


def carrier_present(registry: dict, provider: str) -> bool:
    """Whether the carrier's executable resolves on `PATH` — a yes-or-no about a binary, nothing more.

    This is the one host fact the resolver takes (ADR-0024/D11): it reads no carrier settings file, no
    developer dot-directory and no environment value, and never invokes the carrier to ask what it is,
    so the same code answers the same way on the owner's host and on a consumer's. The executable is
    the row's ``requires_command``, a declared ``argv``'s first element, or — for a shipped carrier —
    the command map's own name for it, so the map stays the only place that spells one.
    """
    row = provider_row(registry, provider)
    argv = row.get("argv")
    mapped = harness_commands().get(provider)
    binary = str(
        row.get("requires_command")
        or (argv[0] if isinstance(argv, list) and argv else "")
        or (mapped.binary if mapped else "")
    )
    return bool(binary) and shutil.which(binary) is not None


def opinion_model(registry: dict, provider: str) -> str | None:
    """The model the second opinion takes inside ``provider``: its strongest declared one.

    This rule belongs to the second opinion alone (ADR-0024/D14) and reads the provider table's
    ``models`` and nothing else — never the tier binding's rungs, which answer a different consumer's
    question and would let a reviewer inherit a `worker`'s list. No declared list means the answer is
    ``None``: the carrier's own default, the one honest value left. A rule nobody implemented raises,
    because silently picking by some other order would be an unstated policy.
    """
    policy = registry.get("second_opinion_policy")
    rule = str(policy.get("model_rule", "max")) if isinstance(policy, dict) else "max"
    if rule != "max":
        raise ValueError(f"second opinion: unknown model_rule {rule!r}; the only rule implemented is 'max'")
    models = provider_row(registry, provider).get("models")
    if not isinstance(models, list) or not models:
        return None
    return str(models[-1])


class EffortError(ValueError):
    """An effort a row cannot take: it declares no ``efforts``, or the level is not one of its ``levels``."""


def check_effort(registry: dict, provider: str, effort: str | None) -> None:
    """Raise ``EffortError`` unless ``effort`` is ``None`` or a level the provider's ``efforts`` lists (ADR-0024/D17).

    akmon never guesses a level and never forwards one the row does not list: a carrier with no
    ``efforts`` is refused naming it, and an unlisted level is refused naming the accepted ones.
    """
    if effort is None:
        return
    declared = provider_row(registry, provider).get("efforts")
    levels = declared.get("levels") if isinstance(declared, dict) else None
    texts = _agents_data()["effort_errors"]
    if not isinstance(levels, list):
        values = {
            "provider": provider,
            "effort": effort,
            "local_overlay": _local_overlay_file(),
            "overlay": _overlay_file(),
        }
        raise EffortError(jsondata.fill(texts["unsupported"], values))
    if effort not in levels:
        values = {"provider": provider, "effort": effort, "levels": ", ".join(str(level) for level in levels)}
        raise EffortError(jsondata.fill(texts["unknown"], values))


def opinion_pick(registry: dict, provider: str, pinned: str | None) -> tuple[str | None, str | None]:
    """The ``(model, effort)`` a ``carrier[:model[@effort]]`` entry runs (ADR-0024/D16, D17).

    ``default`` is a token, not a model id: it drops the pin altogether, so the carrier uses the model
    it is configured with and no alias is resolved, and ``default@high`` sends only the level. An
    effort-only pin (``@high``) keeps the rule's model. No pin at all still means the strongest
    declared entry (``opinion_model``, D14), with the effort that entry carries. A level the row does
    not list raises ``EffortError``.
    """
    model, effort = split_model_effort(pinned)
    check_effort(registry, provider, effort)
    if model == default_model_token():
        return None, effort
    if model is not None:
        return model, effort
    strongest, strongest_effort = split_model_effort(opinion_model(registry, provider))
    return strongest, effort if pinned is not None else strongest_effort


def resolve_session(
    registry: dict,
    config: dict,
    *,
    provider: str | None = None,
    model: str | None = None,
    family: str | None = None,
) -> SecondOpinionSession:
    """The session's carrier, model and priors: explicit arguments, else the ``session`` stanza, else the bound vendor.

    The session may start from any harness on any model, so nothing here assumes a vendor: the
    ``session`` stanza of the local config (written by ``init --session-provider``) names it
    outright, and only when neither it nor an argument does the bound vendor's ``carrier`` and the
    recorded orchestrator alias stand in. Each field comes from the first layer that states it for
    the chosen provider — a layer that names another provider never lends it a model or a family.
    A family none of them states is read from the provider table (``provider_family``), and stays
    ``None`` when that says nothing (ADR-0024/D08). No provider anywhere raises ``SessionUnknownError``.
    """
    stanza = config.get("session")
    vendor_block = registry.get(str(config.get("vendor") or ""))
    derived = {
        "provider": vendor_block.get("carrier") if isinstance(vendor_block, dict) else None,
        "model": config.get("orchestrator"),
    }
    layers = (
        {"provider": provider, "model": model, "family": family},
        stanza if isinstance(stanza, dict) else {},
        derived,
    )
    chosen = next((str(layer["provider"]) for layer in layers if layer.get("provider")), None)
    if chosen is None:
        raise SessionUnknownError(_agents_data()["session_unknown"])

    def stated(field: str) -> str | None:
        for layer in layers:
            if layer.get(field) and layer.get("provider") in (None, "", chosen):
                return str(layer[field])
        return None

    resolved_model = stated("model")
    resolved_family = stated("family")
    if resolved_family is None and chosen in providers(registry):
        resolved_family = provider_family(registry, chosen, resolved_model)
    return SecondOpinionSession(chosen, resolved_family, resolved_model)


def _overlay_file() -> str:
    """The project routing overlay's path, project-root-relative — where an owner declares a missing prior."""
    return f"{aitna_root_name()}/{overlay_name()}"


def _local_overlay_file() -> str:
    """The developer-local routing overlay's path, project-root-relative — the strongest place to declare a prior."""
    return f"{aitna_root_name()}/{local_overlay_rel()}"


def _priors_ask(provider: str, model: str | None) -> str:
    """The named key that would settle an unknown family, and the file to write it in (ADR-0024/D08, D11)."""
    asks = _agents_data()["opinion_asks"]
    values = {
        "provider": provider,
        "model": str(model),
        "local_overlay": _local_overlay_file(),
        "overlay": _overlay_file(),
    }
    return jsondata.fill(asks["provider" if model else "provider_default"], values)


def _session_ask(session: SecondOpinionSession) -> str:
    """The ask for a session whose own family cannot be resolved: nothing is counted as diverse until it is."""
    asks = _agents_data()["opinion_asks"]
    values = {
        "provider": session.provider,
        "model": str(session.model),
        "local_overlay": _local_overlay_file(),
        "overlay": _overlay_file(),
        "local": local_config_rel(),
    }
    return jsondata.fill(asks["session" if session.model else "session_default"], values)


def _walk_opinion_ladder(
    registry: dict, session: SecondOpinionSession
) -> tuple[list[tuple[str, str | None, str | None]], list[tuple[str, str]], list[str]]:
    """The one top-down walk: the admissible chain, every provider passed over with its reason, and the asks.

    Two skips carry the design (ADR-0024/D06): the session's own carrier, and any provider whose
    family or concrete model is already spoken for — a different harness answering with the same
    mind, or the same model under another name, buys no diversity. The compared model is the one the
    consumer's rule resolves (D14), not only a ladder pin, or two providers answering with the same
    weights would both pass; the family is read for that chosen model (``provider_family``), because
    a carrier that fronts several families has no single answer. ``families``/``models`` record which
    provider holds each, so a reason names the owner rather than only refusing. Rank is a position in
    the *resulting* chain, so a skip never leaves a hole the report must explain.

    A session whose own family is unknown yields an empty chain (D08): nothing can be said to differ
    from priors nobody knows. A provider whose family is unknown is skipped and asked about.
    """
    reasons = _agents_data()["opinion_skip_reasons"]
    if not session.family:
        return [], [(session.provider, str(reasons["session_priors_unknown"]))], [_session_ask(session)]
    chain: list[tuple[str, str | None, str | None]] = []
    skips: list[tuple[str, str]] = []
    asks: list[str] = []
    families: dict[str, str] = {str(session.family): session.provider}
    models: dict[str, str] = {str(session.model): session.provider} if session.model else {}
    for entry in opinion_ladder(registry):
        provider, pinned = split_opinion_entry(entry)
        provider_row(registry, provider)  # an id the table does not declare is a named error, even for the self-skip
        check_effort(registry, provider, split_model_effort(pinned)[1])  # so is an effort the row cannot take (D17)
        if provider == session.provider:
            skips.append((provider, str(reasons["self"])))
            continue
        if not carrier_present(registry, provider):
            skips.append((provider, str(reasons["absent"])))
            continue
        chosen, effort = opinion_pick(registry, provider, pinned)
        family = provider_family(registry, provider, chosen)
        if not family:
            skips.append((provider, str(reasons["priors_unknown"])))
            asks.append(_priors_ask(provider, chosen))
            continue
        if family in families:
            skips.append((provider, jsondata.fill(reasons["same_priors"], {"owner": families[family]})))
            continue
        if chosen and chosen in models:
            skips.append((provider, jsondata.fill(reasons["same_model"], {"owner": models[chosen]})))
            continue
        families[family] = provider
        if chosen:
            models[chosen] = provider
        chain.append((provider, chosen, effort))
    return chain, skips, asks


def opinion_chain(registry: dict, session: SecondOpinionSession) -> tuple[SecondOpinionTarget, ...]:
    """The whole admissible chain, in rank order from rank 2: every provider the walk kept, resolved."""
    chain, _, _ = _walk_opinion_ladder(registry, session)
    return tuple(
        SecondOpinionTarget(provider, model, provider_family(registry, provider, model), effort)
        for provider, model, effort in chain
    )


def resolve_opinion_chain(
    registry: dict, session: SecondOpinionSession, *, rank: int = OPINION_RANK_SECOND
) -> SecondOpinionTarget | None:
    """The provider at ``rank`` of the chain the walk produced, or ``None`` past its end.

    ``None`` says the chain is empty or shorter than asked; the caller then takes the disclosed last
    resort (ADR-0024/D07) rather than arriving at the same model without saying so.
    """
    chain = opinion_chain(registry, session)
    index = rank - OPINION_RANK_SECOND
    return chain[index] if 0 <= index < len(chain) else None


def opinion_skips(registry: dict, session: SecondOpinionSession) -> tuple[tuple[str, str], ...]:
    """Every provider passed over and why — the ledger that travels with the report (ADR-0024/D08)."""
    return tuple(_walk_opinion_ladder(registry, session)[1])


def opinion_asks(registry: dict, session: SecondOpinionSession) -> tuple[str, ...]:
    """One line per unknown prior the walk met, each naming the key and the file that would settle it (D08, D11)."""
    return tuple(_walk_opinion_ladder(registry, session)[2])


def opinion_last_resort(registry: dict, session: SecondOpinionSession) -> SecondOpinionTarget:
    """The disclosed last resort for an empty chain: the session's own provider, on a different model if declared.

    The strongest entry of the provider's declared ``models`` whose model differs from the session's —
    read from the provider table and not from the tier binding's rungs (ADR-0024/D14) — and only when
    none differs the carrier's own default in a clean context (D07). The caller files the run as
    ``kind=last-resort``: same priors are never bought, only disclosed.
    """
    row = provider_row(registry, session.provider)
    declared = [str(entry) for entry in row.get("models") or [] if split_model_effort(str(entry))[0] != session.model]
    model, effort = split_model_effort(declared[-1] if declared else None)
    family = provider_family(registry, session.provider, model) or session.family
    return SecondOpinionTarget(session.provider, model, family, effort)


def opinion_repo(registry: dict, provider: str) -> str:
    """What the reviewer could see: derived for a carrier akmon ships, stated or unknown for the rest.

    A knob would let a report claim repository access a bare completion cannot have, so a harness
    carrier is ``worktree``, a tool carrier is ``none``, and a carrier its owner declared with
    nothing said reports ``unknown`` instead of the optimistic reading (ADR-0024/D10, D12).
    """
    row = provider_row(registry, provider)
    stated = row.get("repo")
    if stated:
        return str(stated)
    if row.get("argv"):
        return "unknown"
    return "none" if row.get("carrier") == "tool" or row.get("raw_model") else "worktree"


def opinion_carrier(registry: dict, provider: str) -> str:
    """The carrier kind the report names: ``declared`` for an owner's own argv, else the row's kind or ``harness``."""
    row = provider_row(registry, provider)
    return "declared" if row.get("argv") else str(row.get("carrier") or "harness")


def _without_model_placeholder(parts: Sequence[str]) -> list[str]:
    """``parts`` with every ``{model}`` element gone, and the bare flag that pointed at a lone one."""
    kept: list[str] = []
    for part in parts:
        if "{model}" not in part:
            kept.append(part)
        elif part == "{model}" and kept and kept[-1].startswith("-") and "=" not in kept[-1]:
            kept.pop()
    return kept


def opinion_command(
    registry: dict, provider: str, *, model: str | None = None, effort: str | None = None, prompt: str | None = None
) -> list[str]:
    """The argv for one provider: the command map for a shipped carrier, the owner's own list for a declared one.

    The executable and the operation's prefix come from ``common/runtime.py`` — the sole owner — and
    the row adds only policy: its ``model_flag`` and the prompt as the last argument. A declared
    ``argv`` is a list and is never split or handed to a shell (ADR-0024/D12) — the config the owner
    wrote is the trust boundary, and a command string would make every value in it a candidate
    command. ``{model}`` is the one placeholder, and a pin with nowhere to go raises
    ``UnpinnableModelError`` rather than shipping an unpinned run filed as a diverse one (C97).
    Unpinned, an element holding ``{model}`` is dropped whole; when that element is exactly
    ``{model}`` and the one before it is a bare flag (leading ``-``, no ``=``), the flag goes with it,
    so ``["qwen", "-m", "{model}"]`` runs as ``["qwen"]`` rather than with a flag that now eats the
    next argument (``_without_model_placeholder``).
    An ``effort`` (ADR-0024/D17) is the row's ``efforts.flag`` with ``{effort}`` filled, split like
    ``model_flag`` and appended after the model flag — or, for a declared ``argv``, after the argv —
    and before the prompt; a level the row does not list raises ``EffortError``, so nothing unlisted
    is ever forwarded. It needs no model pin: ``effort`` alone sends only the level.
    A row with ``prompt: "stdin"`` gets no prompt argument; the caller feeds the pack on stdin.
    """
    check_effort(registry, provider, effort)
    row = provider_row(registry, provider)
    argv = row.get("argv")
    if isinstance(argv, list):
        parts = [str(part) for part in argv]
        if model:
            if not any("{model}" in part for part in parts):
                raise UnpinnableModelError(provider, str(model))
            parts = [part.replace("{model}", str(model)) for part in parts]
        else:
            parts = _without_model_placeholder(parts)
    else:
        parts = harness_command(provider, str(row.get("operation", "review")))
        if model:
            model_flag = row.get("model_flag")
            if not model_flag:
                raise UnpinnableModelError(provider, str(model))
            parts += [part.replace("{model}", str(model)) for part in shlex.split(str(model_flag))]
    if effort is not None:
        parts += [part.replace("{effort}", effort) for part in shlex.split(str(row["efforts"]["flag"]))]
    if prompt and str(row.get("prompt", "argv")) != "stdin":
        parts.append(str(prompt))
    return parts


# --------------------------------------------------------------------------------------
# Model aliases (ADR-0024/D16): shipped aliases, concrete ids only in a local file
# --------------------------------------------------------------------------------------

#: The catalog formats ``parse_catalog`` reads; ``bin/verify.json`` keeps the same closed list for the verifier.
CATALOG_FORMATS = ("codex-models-cache",)

_CODEX_SLUG = re.compile(r"[a-z][a-z0-9]*-(\d+(?:\.\d+)*)-([a-z]+)", re.ASCII)


class UnresolvedAliasError(ValueError):
    """A provider row declares ``aliases: true`` and the alias asked for has no concrete id in the local file."""


@dataclass(frozen=True)
class ProviderAliases:
    """One provider's entry of the resolved-aliases file: what produced it, the client version, alias → concrete id."""

    source: str
    client: str | None
    aliases: dict[str, str]


@dataclass(frozen=True)
class CatalogModel:
    """A catalog slug that names a versioned alias: ``gpt-6.1-sol`` is alias ``sol`` at version ``(6, 1)``."""

    slug: str
    alias: str
    version: tuple[int, ...]
    priority: int | None


@dataclass(frozen=True)
class Catalog:
    """What a provider's catalog lists: the carrier version it states, if any, and its listed versioned models."""

    client: str | None
    models: tuple[CatalogModel, ...]


def _alias_file() -> str:
    """The resolved-aliases file's path, project-root-relative — what an unresolved alias asks to have refreshed."""
    return f"{aitna_root_name()}/{local_aliases_rel()}"


def _valid_provider_aliases(value: object) -> ProviderAliases | None:
    """``value`` as a ``ProviderAliases``, or ``None`` when it does not have the file's shape."""
    if not isinstance(value, dict):
        return None
    source, client, aliases = value.get("source"), value.get("client"), value.get("aliases")
    if not isinstance(source, str) or not (client is None or isinstance(client, str)) or not isinstance(aliases, dict):
        return None
    if not all(isinstance(key, str) and isinstance(item, str) for key, item in aliases.items()):
        return None
    return ProviderAliases(source, client, dict(aliases))


def read_model_aliases(project_root: Path) -> dict[str, ProviderAliases]:
    """The resolved-aliases file as typed entries by provider; ``{}`` when it does not exist.

    A file that is not the shape ``models.py`` writes raises ``ValueError`` naming it: the file is
    generated, so the cure is deleting it and refreshing, never a hand edit.
    """
    path = local_aliases_path(project_root)
    if not path.is_file():
        return {}
    invalid = ValueError(jsondata.fill(_agents_data()["alias_errors"]["invalid"], {"file": _alias_file()}))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise invalid from exc
    entries = {key: _valid_provider_aliases(value) for key, value in data.items()} if isinstance(data, dict) else None
    if entries is None or any(entry is None for entry in entries.values()):
        raise invalid
    return {key: entry for key, entry in entries.items() if entry is not None}


def model_aliases_document(stored: Mapping[str, ProviderAliases]) -> str:
    """The file's text for ``stored``: indent 2, insertion order, a trailing newline (no dates, nothing host-wide)."""
    document = {
        provider: {"source": entry.source, "client": entry.client, "aliases": dict(entry.aliases)}
        for provider, entry in stored.items()
    }
    return json.dumps(document, indent=2) + "\n"


def is_model_alias(registry: dict, provider: str, model: str) -> bool:
    """Whether ``model`` is an alias the carrier does not accept: the row says ``aliases: true`` and lists it."""
    row = provider_row(registry, provider)
    models = row.get("models")
    if row.get("aliases") is not True or not isinstance(models, list):
        return False
    return model in [split_model_effort(str(entry))[0] for entry in models]  # an entry may carry an @effort (D17)


def resolve_opinion_model(
    registry: dict, stored: Mapping[str, ProviderAliases], provider: str, model: str | None
) -> str | None:
    """The model a carrier is sent: an alias replaced by its concrete id, anything else passed through.

    Only a model that is an alias of an ``aliases: true`` row is replaced; a concrete id (not in the
    row's ``models``) and the carrier's own default (``None``) pass through. An alias with no mapping
    raises ``UnresolvedAliasError`` naming the refresh command — fail closed, never an unresolved
    alias sent to the carrier (ADR-0024/D16, D08).
    """
    if model is None or not is_model_alias(registry, provider, model):
        return model
    entry = stored.get(provider)
    concrete = entry.aliases.get(model) if entry else None
    if not concrete:
        values = {"provider": provider, "model": model, "file": _alias_file()}
        raise UnresolvedAliasError(jsondata.fill(_agents_data()["alias_errors"]["unresolved"], values))
    return concrete


def expand_home(path_text: str, home: str) -> str:
    """``path_text`` with a leading ``~`` or ``~/`` replaced by ``home`` — the only expansion a catalog path takes."""
    if path_text == "~" or path_text.startswith("~/"):
        return (home.rstrip("/") + path_text[1:]) or "/"
    return path_text


def parse_catalog(text: str, catalog_format: str) -> Catalog:
    """A catalog file's text read as ``catalog_format``; ``ValueError`` says what is wrong with it, not where.

    ``codex-models-cache``: ``{"models": [{"slug", "visibility", "priority", ...}]}``. Only ``visibility ==
    "list"`` entries count, and a slug counts when it reads ``<family>-<version>-<alias>``
    (``gpt-6.1-sol``): ``gpt-reserve`` and ``codex-auto-review`` are ignored, never guessed at.
    """
    texts = _agents_data()["catalog_errors"]
    if catalog_format not in CATALOG_FORMATS:
        raise ValueError(
            jsondata.fill(texts["format"], {"format": catalog_format, "known": ", ".join(CATALOG_FORMATS)})
        )
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ValueError(texts["json"]) from exc
    listed = data.get("models") if isinstance(data, dict) else None
    if not isinstance(listed, list):
        raise ValueError(texts["shape"])
    client = data.get("client_version")
    models: list[CatalogModel] = []
    for entry in listed:
        slug = entry.get("slug") if isinstance(entry, dict) else None
        match = _CODEX_SLUG.fullmatch(slug) if isinstance(slug, str) else None
        if match is None or entry.get("visibility") != "list":
            continue
        priority = entry.get("priority")
        version = tuple(int(part) for part in match.group(1).split("."))
        models.append(
            CatalogModel(
                slug,
                match.group(2),
                version,
                priority if isinstance(priority, int) and not isinstance(priority, bool) else None,
            )
        )
    return Catalog(client if isinstance(client, str) else None, tuple(models))


def catalog_aliases(catalog: Catalog, aliases: Sequence[str]) -> dict[str, str]:
    """Each of ``aliases`` mapped to its highest-versioned slug, ties by lowest priority; an unmatched one is absent.

    Absent means unmapped: nothing here guesses an id for an alias the catalog does not list
    (ADR-0024/D16). The result follows ``aliases``' order.
    """
    resolved: dict[str, str] = {}
    for alias in aliases:
        best: CatalogModel | None = None
        for model in catalog.models:
            if model.alias != alias:
                continue
            if best is None or (model.version, -_rank_of(model)) > (best.version, -_rank_of(best)):
                best = model
        if best is not None:
            resolved[alias] = best.slug
    return resolved


def _rank_of(model: CatalogModel) -> float:
    """A model's catalog priority as a number where lower is better; a model stating none ranks last."""
    return float("inf") if model.priority is None else float(model.priority)


def opinion_head(registry: dict, config: dict) -> tuple[str, str | None]:
    """What the second opinion would run first, as a display and any warning (the status line and the init summary).

    Resolved through the same walk the runner takes rather than through any stored provider: a
    display that can disagree with the policy is a second owner of one fact, the drift class C46
    exists to remove. ``priors=unknown`` stands for a session nobody could name the family of, and
    the warning carries the ask beside it (ADR-0024/D08); a stale key raises out of here
    (``refuse_retired_keys``) and costs the whole status block, deliberately.
    """
    refuse_retired_keys(registry, config)
    texts = _agents_data()["opinion_status"]
    try:
        session = resolve_session(registry, config)
    except SessionUnknownError as exc:
        return str(texts["unavailable_unknown"]), str(exc)
    if not session.family:
        return str(texts["unavailable_unknown"]), _session_ask(session)
    chain = opinion_chain(registry, session)
    if not chain:
        return str(texts["unavailable"]), jsondata.fill(texts["chain_empty"], {"provider": session.provider})
    head = chain[0]
    pin = head.model or (default_model_token() if head.effort is not None else "")
    pin = f"{pin}@{head.effort}" if head.effort is not None else pin
    target = f"{head.provider}:{pin}" if pin else head.provider
    return jsondata.fill(texts["head"], {"target": target, "family": head.family or "unknown"}), None


# --------------------------------------------------------------------------------------
# Generated subagent definitions (the `k-` akmon namespace)
# --------------------------------------------------------------------------------------


# Each agent groups the task kinds whose briefs coincide; the tier picks its model from
# the binding. Bodies are project-neutral (this is SHARED); project specifics are appended
# via the overlay's "briefs" map.
@dataclass(frozen=True)
class AgentSpec:
    """One generated ``k_*`` subagent's definition: tier, description, tools, body, task kinds."""

    name: str
    tier: str  # "worker" | "mid" | "reasoner" | "auditor"
    description: str
    tools: str | None  # frontmatter `tools:`; None = all tools
    body: str
    kinds: tuple[str, ...] = field(default=())


def agent_specs() -> tuple[AgentSpec, ...]:
    """The six generated ``k_*`` subagent definitions (``agents.json``), in roster order."""
    return tuple(
        AgentSpec(
            name=raw["name"],
            tier=raw["tier"],
            description=raw["description"],
            tools=raw["tools"],
            body=raw["body"],
            kinds=tuple(raw["kinds"]),
        )
        for raw in _agents_data()["agent_specs"]
    )


def _agent_model(spec: AgentSpec, binding: Binding) -> str | None:
    if binding.semantic_fallback:
        return None
    return {
        "worker": binding.worker,
        "mid": binding.mid,
        "reasoner": binding.reasoner,
        "auditor": binding.auditor,
    }[spec.tier]


def agent_file_content(spec: AgentSpec, binding: Binding, brief_extra: str = "") -> str:
    """Render one generated ``.claude/agents/<name>.md`` file: frontmatter, banner, body, brief."""
    lines = ["---", f"name: {spec.name}", "description: >-"]
    # The auditor reads a fan-out rather than being a zone of it, so it carries no zone convention.
    description = spec.description if spec.name == "k_auditor" else f"{spec.description} {zone_convention()}"
    lines.extend(f"  {chunk}" for chunk in _wrap(description, 88))
    if spec.tools:
        lines.append(f"tools: {spec.tools}")
    model = _agent_model(spec, binding)
    if model:
        lines.append(f"model: {model}")
    lines.append("---")
    lines.append("")
    lines.append(f"<!-- {generated_banner()} -->")
    lines.append("")
    lines.append(spec.body)
    if brief_extra.strip():
        lines.append("")
        lines.append("<!-- project overlay brief -->")
        lines.append("")
        lines.append(brief_extra.strip())
    return "\n".join(lines) + "\n"


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            chunks.append(current)
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


class BriefError(ValueError):
    """A project overlay's ``briefs`` map cannot be applied to the current agent specs.

    Raised instead of defaulting to an empty brief: an overlay brief is hand-authored
    project instruction, and a key that matches no agent means those instructions would
    silently vanish from the generated definition — no diff to look at, no warning. That is
    the tolerance-degrades-to-silence shape C48 argues against, and ADR 0011's ``k-*`` →
    ``k_*`` rename made it live (C50).
    """


def agent_key(name: str) -> str:
    """Normal form of an agent name for overlay lookups — folds case, ``-``/``_`` and surrounding whitespace.

    Overlay brief keys are a public contract written by hand in a consumer's repository, so
    a change of *notation* (ADR 0011) must not orphan them. The tolerance line, owner-verified
    at ADR-0011/D02: invisible and notational differences are forgiven — surrounding whitespace does
    not survive a diff, so failing on it costs more to diagnose than the tolerance costs to hold
    — while any difference in significant characters, an internal space included, still fails
    (see ``resolve_briefs``).
    """
    return name.strip().lower().replace("-", "_")


def resolve_briefs(registry: dict) -> dict[str, str]:
    """Overlay briefs re-keyed by the **current** spec names; raises ``BriefError`` otherwise."""
    briefs = registry.get("briefs", {})
    if not isinstance(briefs, dict):
        raise BriefError(f"overlay 'briefs' must be an object, got {type(briefs).__name__}")
    by_key = {agent_key(spec.name): spec.name for spec in agent_specs()}
    resolved: dict[str, str] = {}
    source: dict[str, str] = {}
    for key, text in sorted(briefs.items()):
        if not isinstance(text, str):
            raise BriefError(f"overlay brief '{key}' must be a string, got {type(text).__name__}")
        name = by_key.get(agent_key(str(key)))
        if name is None:
            known = ", ".join(sorted(by_key.values()))
            raise BriefError(f"overlay brief key '{key}' matches no agent (known: {known})")
        if name in resolved:
            raise BriefError(f"overlay brief keys '{source[name]}' and '{key}' both resolve to '{name}'")
        source[name] = str(key)
        resolved[name] = text
    return resolved


def brief_warning(registry: dict, aitna: str | None = None) -> str | None:
    """Owner-addressed line naming an unusable overlay ``briefs`` map, or None when it is fine."""
    try:
        resolve_briefs(registry)
    except BriefError as exc:
        root = aitna or aitna_root_name()
        return f"⚠ {exc} — fix {root}/{overlay_name()}; k_* definitions are not regenerated until it resolves"
    return None


_REBIND_MARKER = "suppressed-rebind"


def suppressed_rebind_warning(
    warning: str | None,
    detected_model: str | None,
    session_id: str | None,
    *,
    marker_dir: Path | None = None,
) -> list[str]:
    """Emit one warning per session/model/error episode; reset when the condition clears.

    A refused rebind leaves the recorded orchestrator unchanged, so comparing the next
    transcript against that config reports the same switch on every prompt. The marker is
    deliberately temporary rather than project state: it remembers only which warning the
    current session already saw. A changed model or error produces a new digest and re-arms
    the notice; a cleared condition removes the marker so a later recurrence speaks again.

    Since C36(a) the marker is claimed through ``common.markers`` — atomic, hashed, ``0600``,
    aged out after a day — so exactly-once per episode is the contract rather than the
    best-effort residual ADR-0011/D02 once accepted here: a crashed or reused session id no
    longer hides the notice for longer than the age-out. The condition is folded into the
    marker's kind, and moving to another condition or clearing it releases the session's
    other markers, which is what re-arms a later recurrence.
    """
    # Without a reliable session identity, never let one anonymous invocation silence
    # another session. Repeating the warning is safer than a process-global ``nosession``
    # marker that hides an unresolved lossy-rebind condition from an unrelated owner.
    if not session_id:
        return [warning] if warning is not None and detected_model is not None else []

    session = str(session_id)
    if warning is None or detected_model is None:
        release_diagnostic_markers(_REBIND_MARKER, session, directory=marker_dir)
        return []

    condition = hashlib.sha256(f"{detected_model}\0{warning}".encode()).hexdigest()[:16]
    kind = f"{_REBIND_MARKER}-{condition}"
    if not claim_diagnostic_marker(kind, session, directory=marker_dir):
        return []
    release_diagnostic_markers(_REBIND_MARKER, session, keep_kind=kind, directory=marker_dir)
    return [warning]


def generated_agent_files(registry: dict, binding: Binding) -> dict[str, str]:
    """Map of ``.claude/agents/<name>.md`` relative paths → generated content."""
    briefs = resolve_briefs(registry)
    return {
        f"{agents_dir_rel()}/{spec.name}.md": agent_file_content(spec, binding, briefs.get(spec.name, ""))
        for spec in agent_specs()
    }


def _agent_by_name() -> dict[str, AgentSpec]:
    return {spec.name: spec for spec in agent_specs()}


def subagent_kinds(name: str) -> tuple[str, ...]:
    """Task kinds a generated subagent covers; empty for a host built-in / unknown name."""
    spec = _agent_by_name().get(name)
    return spec.kinds if spec else ()


def bound_model_for(config: dict, subagent_type: str) -> str | None:
    """Model a generated ``k_*`` agent is pinned to — its tier's binding alias, or None.

    The generated agent frontmatter carries ``model: <alias>`` (see ``_agent_model``), but an
    ``Agent`` call rarely echoes it — so the delegation record shows ``-`` and the console
    line omits the model. Deriving it from the recorded binding restores it. None for an
    unknown agent (a host built-in) or for a semantic-fallback binding, whose tier values are
    labels (``worker``/``strongest``), not vendor aliases.

    The config does not persist ``Binding.semantic_fallback``, so the mode is re-derived the
    same way ``compute_binding`` decides it: **no recorded ``available`` ladder is exactly
    semantic fallback**. That is the mirror of ``_agent_model`` emitting no ``model:`` line —
    an agent file without a pin is inherited by the host from the session, so there is no pin
    to report and the record honestly says ``-``. Reporting the label instead would assert a
    pin precisely where the design refuses to make one.
    """
    spec = _agent_by_name().get(subagent_type)
    if spec is None or not isinstance(config, dict):
        return None
    binding = config.get("binding")
    if not isinstance(binding, dict):
        return None
    model = binding.get(spec.tier)
    if not isinstance(model, str) or not model:
        return None
    available = config.get("available")
    if not isinstance(available, list) or not available or not all(isinstance(alias, str) for alias in available):
        return None
    # The opted-in auditor is an auditor-only rung: pinned although the ladder never lists it.
    if model not in available and not (spec.tier == "auditor" and model == config.get("auditor_opt_in")):
        return None
    return model


# The patterns of this module that use ``\s``/``\S``/``\w``/``\d`` are ``re.ASCII``: the JavaScript
# twin's classes are narrower or differently drawn than Python's Unicode ones (``\d`` matching
# Arabic-Indic digits, ``\s`` matching U+001C to U+001F and U+0085), so the two would read the same
# text differently. Each one reads ASCII markup — a role declaration, a zone label, a markdown
# heading, list item or table row — so the real answers are unchanged. ``_HEADING_WORD_RE`` is the
# deliberate exception: its words are any script's letters (C98).
_ROLE_DECL_RE = re.compile(r"\A\s*🧭\s*agent:\s*([A-Za-z][\w-]*)", re.ASCII)


def _assistant_text(entry: dict) -> str:
    message = entry.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


#: Block size of the tail read. A line longer than one block is assembled across blocks.
_TAIL_BLOCK_BYTES = 1 << 16
# The line breaks a forward text-mode read splits on (universal newlines): the tail read has to
# see exactly the lines the forward scan saw.
_LINE_BREAK = re.compile(rb"\r\n|\r|\n")


def _transcript_file(transcript_path: str | Path | None) -> Path | None:
    if not transcript_path:
        return None
    path = Path(transcript_path)
    return path if path.is_file() else None


def _lines_from_end(handle: BinaryIO, needle: bytes) -> Iterator[str]:
    r"""The lines of ``handle`` that contain ``needle``, last line first (A19).

    Both transcript scanners want the *last* record that qualifies, so reading from the end and
    stopping at the first qualifying record returns what a full forward scan returns, at a cost
    set by the distance from the end rather than by the file's size. Lines split on ``\r\n``,
    ``\r`` and ``\n``, as a forward text-mode read splits them, and each line decodes as strict
    UTF-8. A line that does not decode is skipped: the forward read raised on it instead, losing
    every other line with it. Memory stays at one block plus the longest line.
    """
    handle.seek(0, os.SEEK_END)
    position = handle.tell()
    carry: list[bytes] = []  # the start of the line that runs past the current block, in file order
    while position > 0:
        size = min(_TAIL_BLOCK_BYTES, position)
        position -= size
        handle.seek(position)
        block = handle.read(size)
        # JSON escapes a carriage return, so a real transcript carries none, and bytes.split is
        # several times faster than the regex. A block holding one takes the exact split.
        pieces = _LINE_BREAK.split(block) if b"\r" in block else block.split(b"\n")
        if len(pieces) == 1:
            carry.insert(0, pieces[0])
            continue
        complete = [b"".join([pieces[-1], *carry]), *reversed(pieces[1:-1])]
        carry = [pieces[0]]
        yield from _decoded(complete, needle)
    yield from _decoded([b"".join(carry)], needle)


def _decoded(lines: Iterable[bytes], needle: bytes) -> Iterator[str]:
    for raw in lines:
        if needle in raw:
            try:
                yield raw.decode("utf-8")
            except UnicodeDecodeError:
                continue


def _main_chain_assistant(line: str) -> dict | None:
    """The record on ``line`` when it is a main-chain assistant turn, else None.

    Sidechain (subagent) turns are skipped, and so is a line that is not JSON — a torn last line
    included, since the harness may be writing it while a hook reads.
    """
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(entry, dict) or entry.get("type") != "assistant" or entry.get("isSidechain"):
        return None
    return entry


def active_role(transcript_path: str | Path | None) -> str | None:
    """The role from the last qualifying ``🧭 agent: <name>`` transcript declaration.

    The chat declaration is invisible to a hook as chat, but the transcript records it in the
    assistant turns a hook can already scan (as C22/C23 do). Only main-chain assistant turns
    are read, so the SessionStart reminder / a subagent echo never masquerades as the
    declaration. A declaration qualifies only as the first non-whitespace text of its turn,
    so later inline and Markdown-prefixed examples cannot change state. A first-position marker
    is a declaration by definition. Returns the case-normalized role name, else None.

    Read from the end (A19), stopping at the first qualifying declaration, which is the last one.
    A session that never declared a role still reads the whole file: bounding the read would
    forget a role declared early, and the owner chose the exact scan.
    """
    path = _transcript_file(transcript_path)
    if path is None:
        return None
    try:
        with path.open("rb") as handle:
            # Cheap ascii pre-filter: the emoji may be \u-escaped in the JSONL, but "agent:" is
            # always literal. json.loads then decodes the real marker.
            for line in _lines_from_end(handle, b"agent:"):
                entry = _main_chain_assistant(line)
                match = _ROLE_DECL_RE.match(_assistant_text(entry)) if entry is not None else None
                if match:
                    return match.group(1).casefold()
    except OSError:
        return None
    return None


def role_matrix_warning(registry: dict, subagent_type: str, role: str | None) -> str | None:
    """Conservative advisory (§10.2): the agent has no effectively allowed task kind.

    The call carries the agent, not an authoritative invocation kind, so warn only when *none*
    of the agent's kinds intersect the role's effective allowed set. Silence proves one allowed
    overlap, not conformance of an intended kind carried by a multi-kind agent. None when the
    role is unknown/undeclared or the agent is a host built-in (no kinds).

    **Cross-cutting verification kinds** (``cross_cutting_kinds`` — ``independent-review`` and
    ``audit``) are *not* role-gated (A7 (b), §10.2): any role may route them and *when* they
    apply is the structural trigger (§9.5), not the producing role. They join every role's
    allowed set, so an agent whose only kinds are cross-cutting (e.g. ``k_auditor``) never
    warns under any role.
    """
    fields = _role_matrix_fields(registry, subagent_type, role)
    return None if fields is None else jsondata.fill(_agents_data()["role_matrix_warning"], fields)


def role_matrix_directive(registry: dict, subagent_type: str, role: str | None) -> str | None:
    """The model-addressed form of ``role_matrix_warning``: re-route or switch role.

    Same predicate, same silence; the delegation log sends it as ``additionalContext`` beside
    the owner's ``systemMessage`` (ADR 0006 item 4, M149).
    """
    fields = _role_matrix_fields(registry, subagent_type, role)
    return None if fields is None else jsondata.fill(_agents_data()["role_matrix_directive"], fields)


def _role_matrix_fields(registry: dict, subagent_type: str, role: str | None) -> dict[str, str] | None:
    """The role-matrix advisory's template fields, or ``None`` when it stays silent (§10.2)."""
    if not role:
        return None
    role_rows = registry.get("role_task_kinds", {})
    if not isinstance(role_rows, dict) or role not in role_rows:
        return None
    allowed = role_rows[role]
    if not isinstance(allowed, list):
        return None
    effective_allowed = tuple(dict.fromkeys((*allowed, *registry.get("cross_cutting_kinds", []))))
    kinds = subagent_kinds(subagent_type)
    if not kinds or set(kinds) & set(effective_allowed):
        return None
    allowed_text = ", ".join(effective_allowed) or "no task kinds"
    return {"subagent": subagent_type, "kinds": ", ".join(kinds), "role": role, "allowed": allowed_text}


# --------------------------------------------------------------------------------------
# Local config + status line (the SessionStart hook contract)
# --------------------------------------------------------------------------------------


def resolve_alias(model_id: str | None, available: list[str] | None) -> str | None:
    """Map a concrete vendor model id (e.g. ``claude-opus-4-8``) to a known local alias.

    The alias is matched as a case-insensitive substring of the id, preferring the longest
    match so overlapping aliases disambiguate (``opus`` over a bare ``o``). ``None`` when no
    alias in ``available`` matches — the caller keeps the recorded binding rather than guess.
    """
    if not model_id or not available:
        return None
    lowered = model_id.lower()
    matches = [alias for alias in available if alias and alias.lower() in lowered]
    return max(matches, key=len) if matches else None


#: ``(model id, usage)`` of the last main-chain assistant turn — what ``last_main_turn`` returns.
MainTurn = tuple[str | None, dict | None]


def last_main_turn(transcript_path: str | Path | None) -> MainTurn:
    """(model id, usage) of the last *main-chain* assistant turn in the session transcript.

    The transcript (a JSONL the harness records; its path arrives in the hook payload)
    carries ``message.model`` and ``message.usage`` per assistant turn. Sidechain
    (subagent) turns and synthetic entries are skipped, so a delegate's model or usage
    never masquerades as the orchestrator's. One read yields both facts: the hook passes it to
    orchestrator detection and to context-pressure detection as ``turn``. Read from the end
    (A19) and stopped at the first qualifying turn, so the cost does not grow with the session.
    ``(None, None)`` when the transcript is missing/empty/unreadable or names no model yet.
    """
    path = _transcript_file(transcript_path)
    if path is None:
        return None, None
    try:
        with path.open("rb") as handle:
            for line in _lines_from_end(handle, b'"model"'):
                entry = _main_chain_assistant(line)
                message = entry.get("message") if entry is not None else None
                model = message.get("model") if isinstance(message, dict) else None
                if isinstance(model, str) and model and not model.startswith("<"):
                    usage = message.get("usage")
                    return model, usage if isinstance(usage, dict) else None
    except OSError:
        return None, None
    return None, None


def detect_orchestrator(
    transcript_path: str | Path | None, available: list[str] | None, *, turn: MainTurn | None = None
) -> str | None:
    """Alias of the model the *main chain* last ran on, read from the session transcript.

    ``None`` when the transcript names no model yet or the model maps to no known alias
    (a fresh session before the first turn, or an unrecognized id): the caller then keeps
    the recorded orchestrator instead of guessing. ``turn`` is a ``last_main_turn`` result the
    caller already read; the transcript is read only without one.
    """
    model_id, _ = turn if turn is not None else last_main_turn(transcript_path)
    return resolve_alias(model_id, available)


def detection_aliases(registry: dict, config: dict) -> list[str]:
    """The aliases orchestrator detection recognises: the recorded ladder plus the vendor's auditor-only rungs.

    Empty without a recorded ladder (the semantic case), so detection stays silent there as before.
    """
    ladder = config.get("available") if isinstance(config, dict) else None
    if not isinstance(ladder, list) or not ladder:
        return []
    auditor_only = registry.get(str(config.get("vendor") or "anthropic"), {}).get("auditor_only_rungs") or []
    return [*ladder, *(alias for alias in auditor_only if alias not in ladder)]


# --------------------------------------------------------------------------------------
# Context-pressure detection (design §12, ADR 0006) — the tokens axis of runtime weakness
# --------------------------------------------------------------------------------------


def context_fill(usage: dict | None) -> int | None:
    """Context fill at a turn: the three input components partition the prompt.

    ``output_tokens`` is not context carried forward, so it is excluded. ``None`` unless all
    three input components are non-negative integers (a bool is not a count): one valid
    component never stands in for the prompt, so the caller stays silent rather than warn
    from a partial or malformed record.
    """
    if not isinstance(usage, dict):
        return None
    components = [usage.get(key) for key in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")]
    if not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in components):
        return None
    return sum(components)


#: Overrides the recommended maximum for every model when it holds a positive integer — per user
#: (the shell, or ``env`` in ``~/.claude/settings.json``) or per project (``env`` in
#: ``.claude/settings.json``). Any other value is ignored and the registry decides.
RECOMMENDED_MAX_ENV = "AKMON_CONTEXT_RECOMMENDED_MAX"


def recommended_max_context(registry: dict, model_id: str | None) -> int:
    """The recommended context budget, in tokens — what pressure percentages are a share of.

    The recommended active-context budget for a session intended to carry one task, not the
    model's hard limit (design §12.2): a session should carry the task it is solving, not its
    history — fewer tokens spent, less drift from the task, less forgetting — and quality
    degrades with length whatever the limit. This code knows neither which task a session
    carries nor what that task needs; it sees only the prompt fill. Resolution:
    ``AKMON_CONTEXT_RECOMMENDED_MAX`` when it holds a positive integer, else the longest
    alias-substring key of ``recommended_max_by_alias`` found in the model id (e.g. a model whose
    hard limit sits below the default), else ``recommended_max``. The shipped 200000 is a
    configurable owner policy checked against measurement — above where sessions get compacted
    in practice, below the 258,400-token window Codex reports for OpenAI models — C80
    (meta/reviews/c80-context-fill.md).
    """
    try:
        override = int(os.environ.get(RECOMMENDED_MAX_ENV, ""))
    except ValueError:
        override = 0
    if override > 0:
        return override
    policy = registry.get("context_pressure", {})
    default = int(policy.get("recommended_max") or 200000)
    by_alias = policy.get("recommended_max_by_alias", {})
    if model_id and isinstance(by_alias, dict):
        lowered = model_id.lower()
        matches = [key for key in by_alias if key and key.lower() in lowered]
        if matches:
            return int(by_alias[max(matches, key=len)])
    return default


def _context_fill_metrics(
    registry: dict, transcript_path: str | Path | None, turn: MainTurn | None = None
) -> tuple[int, int, float] | None:
    """``(fill, recommended_max, ratio)`` for the last main-chain turn; ``None`` if unavailable.

    Shared by ``context_pressure_notice`` (the two-level reminder) and ``context_fill_ratio``
    (the C29 axis-2 coefficient) so both read the same fill/recommended-max definition. ``turn``
    is a ``last_main_turn`` result the caller already read; the transcript is read only without one.
    """
    model_id, usage = turn if turn is not None else last_main_turn(transcript_path)
    fill = context_fill(usage)
    if fill is None:
        return None
    recommended = recommended_max_context(registry, model_id)
    if recommended <= 0:
        return None
    return fill, recommended, fill / recommended


def context_fill_ratio(registry: dict, transcript_path: str | Path | None) -> float | None:
    """Fill as a share of the recommended maximum for the last main-chain turn (can pass 1.0); ``None`` if unavailable.

    Reused by the C29 output-weight nudge to weight cumulative tool-output bytes by how far
    into the recommended maximum the session already is — the same signal
    ``context_pressure_notice`` bands.
    """
    metrics = _context_fill_metrics(registry, transcript_path)
    return metrics[2] if metrics else None


def context_pressure_notice(
    registry: dict,
    transcript_path: str | Path | None,
    session_id: str | None,
    *,
    marker_dir: Path | None = None,
    turn: MainTurn | None = None,
) -> list[str]:
    """One reminder line when the context fill reached a *new* pressure level; ``[]`` otherwise.

    Two levels of the recommended budget (design §12.2): **info** at ``info_ratio`` and **warn**
    at the budget itself, 1.0 — fixed, since reaching the budget is what the budget means.
    Throttled (the delegation-nudge marker idiom): a per-session temp-dir marker records the last
    announced level, so only a rise speaks — info once, warn once more, also when the fill jumps
    straight past 100%; a steady fill and any fill past the budget stay silent. A fill below the
    lowest level ends the pressure episode and clears the marker — the hook sees only the low
    fill, not its cause (a compact, a fresh session, anything else). The share is of the
    recommended budget, not the model's limit, so it can pass 100% on a model with a larger
    window; going on is the developer's call. Missing/malformed usage → silent; never raises
    past I/O.
    """
    policy = registry.get("context_pressure", {})
    info_ratio = policy.get("info_ratio")
    # Only a share strictly between 0 and 1 is a level below the budget; anything else (absent,
    # a bool, 0, 1 or more, a string) leaves the budget's own warning alone.
    if isinstance(info_ratio, bool) or not isinstance(info_ratio, (int, float)) or not 0 < info_ratio < 1:
        info_ratio = None
    metrics = _context_fill_metrics(registry, transcript_path, turn)
    if metrics is None:
        return []
    _, recommended, ratio = metrics
    level: int | None = None  # 0 = info, 1 = warn — the value the marker records
    if ratio >= 1.0:
        level = 1
    elif info_ratio is not None and ratio >= info_ratio:
        level = 0

    marker = (marker_dir or Path(tempfile.gettempdir())) / f"akmon-context-pressure-{session_id or 'nosession'}"
    try:
        last_level: int | None = int(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        last_level = None

    if level is None:
        # Below every level — the pressure episode is over and the throttle resets. The cause is
        # not visible here: a compact, a fresh session and anything else that lowered the fill
        # look alike.
        with contextlib.suppress(OSError):
            marker.unlink(missing_ok=True)
        return []
    if last_level is not None and level <= last_level:
        return []
    with contextlib.suppress(OSError):
        marker.write_text(str(level), encoding="utf-8")

    shown = f"{recommended // 1000}k" if recommended % 1000 == 0 else str(recommended)
    share = f"~{ratio:.0%} of the recommended {shown} budget"
    # A reminder to the owner and nothing more: the share and the command to type. `/compact` and
    # `/new` exist under those names in Claude Code and in Codex alike. The marks are the hook's
    # own: ⚠ for a warning, as the corridor's, ℹ for information.
    pressure = _agents_data()["context_pressure"]
    if level == 1:
        return [jsondata.fill(pressure["warn"], {"share": share})]
    return [jsondata.fill(pressure["info"], {"share": share})]


def binding_artifacts(
    registry: dict,
    binding: Binding,
    *,
    second_opinion: bool,
    available: list[str] | None,
    session: dict | None = None,
) -> dict[str, str]:
    """Every generated routing artifact as ``project-root-relative path → content``.

    The generated ``k_*`` subagent definitions plus the local config — the single set the
    init tool and the SessionStart/UserPromptSubmit hook both write, so a rebind from
    either path produces byte-identical files.
    """
    files = dict(generated_agent_files(registry, binding))
    config = local_config(binding, registry, second_opinion=second_opinion, available=available, session=session)
    files[local_config_rel()] = json.dumps(config, indent=2) + "\n"
    return files


def obsolete_agent_files(root: Path, planned_paths: Iterable[Path]) -> list[Path]:
    """Generated subagent definitions on disk that the current ``agent_specs()`` no longer plan.

    Only files carrying one of ``generated_banners()`` are candidates, so a hand-written agent living in
    the same directory is never a deletion target. Without this, renaming an agent leaves its
    old definition behind as a live duplicate — the harness keeps offering both, the stale one
    still pinned to a model, and nothing warns (``bin/sync.py`` prunes only skills, ADR 0011).
    """
    agents_dir = root / agents_dir_rel()
    if not agents_dir.is_dir():
        return []
    planned = set(planned_paths)
    obsolete: list[Path] = []
    for path in sorted(agents_dir.glob("*.md")):
        if path in planned:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if any(banner in text for banner in generated_banners()):
            obsolete.append(path)
    return obsolete


def remove_obsolete_agents(root: Path, planned_paths: Iterable[Path], *, write: bool = True) -> list[Path]:
    """Delete the generated agent definitions no longer planned; return their paths."""
    removed = obsolete_agent_files(root, planned_paths)
    if write:
        for path in removed:
            path.unlink(missing_ok=True)
    return removed


def write_artifacts(root: Path, files: dict[str, str], *, write: bool = True) -> list[Path]:
    """Write each artifact whose content changed; return the changed paths (idempotent)."""
    changed: list[Path] = []
    for rel, content in files.items():
        path = root / rel
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == content:
            continue
        changed.append(path)
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    return changed


def rebind_to(
    root: Path, registry: dict, config: dict, orchestrator: str, *, write: bool = True
) -> tuple[Binding, list[Path]]:
    """Recompute the binding for ``orchestrator`` and (re)write the artifacts under ``root``.

    Reuses the recorded ``available`` list, opt-ins and ``session`` stanza from ``config`` — only
    the orchestrator moves. Idempotent: unchanged files are left untouched. This is how the
    hook makes subagent models follow the session's actual orchestrating model.
    """
    available = config.get("available")
    second_opinion = bool(config.get("second_opinion"))
    vendor = str(config.get("vendor") or "anthropic")
    auditor_opt_in = config.get("auditor_opt_in") or None
    binding = compute_binding(registry, orchestrator, available, vendor, auditor_opt_in)
    files = binding_artifacts(
        registry, binding, second_opinion=second_opinion, available=available, session=config.get("session")
    )
    changed = write_artifacts(root, files, write=write)
    remove_obsolete_agents(root, (root / rel for rel in files), write=write)
    return binding, changed


def local_config(
    binding: Binding,
    registry: dict,
    *,
    second_opinion: bool,
    available: list[str] | None,
    session: dict | None = None,
) -> dict:
    """The per-user resolved config written to ``local_config_rel()`` (binding, opt-ins, staleness hash).

    ``available`` records the ladder the binding resolved (``selection_ladder``) — none in the
    semantic case — so the runtime readers need no ``--available`` of their own. ``session`` is the
    optional ``{provider, model, family?}`` stanza naming the harness the session runs on when it is
    not the bound vendor's own (ADR-0024); it is written only when given, so a project that never
    states one derives its session from the vendor as before.
    """
    rungs, semantic = selection_ladder(registry, binding.vendor, available)
    config = {
        "vendor": binding.vendor,
        "orchestrator": binding.orchestrator,
        "binding": {
            "reasoner": binding.reasoner,
            "worker": binding.worker,
            "mid": binding.mid,
            "auditor": binding.auditor,
            "escalation": list(binding.escalation),
        },
        "second_opinion": second_opinion,
        "available": None if semantic else rungs,
        "auditor_opt_in": binding.auditor_opt_in,
        "registry_hash": registry_hash(registry),
        "task_kind_floors": task_kind_floors(registry, [] if semantic else rungs, binding.vendor),
    }
    if session:
        config["session"] = dict(session)
    return config


def staleness(config: dict, registry: dict, settings_model: str | None) -> str | None:
    """Why the local config is stale — or None when it is fresh."""
    texts = _agents_data()["staleness"]
    if not config:
        return texts["no_config"]
    if config.get("registry_hash") != registry_hash(registry):
        return texts["registry_changed"]
    if settings_model and settings_model != config.get("orchestrator"):
        return jsondata.fill(texts["model_mismatch"], {"model": settings_model})
    return None


def _second_opinion_status(registry: dict, config: dict, orchestrator_vendor: str) -> tuple[str, str | None]:
    """What the second-opinion gate will actually do, as one status field plus any warning.

    The head of the chain the runner would walk (``opinion_head``), with the on/off state. The
    status shows the vendor the hook already resolved, so a config that predates the ``vendor`` key
    reads as the hook reads it.
    """
    enabled = bool(config.get("second_opinion"))
    display, warning = opinion_head(registry, {**config, "vendor": config.get("vendor") or orchestrator_vendor})
    state = "on" if enabled else "off"
    return f"second-opinion={display} ({state})", warning if enabled else None


@dataclass(frozen=True)
class FloorGap:
    """A task kind whose rung floor sits above the rung its routed agent is bound to (C32)."""

    kind: str
    agent: str
    floor: str
    bound: str


def _rank(ladder: list, alias: object) -> int | None:
    return ladder.index(alias) if isinstance(alias, str) and alias in ladder else None


def floor_gaps(config: dict) -> list[FloorGap]:
    """Kinds whose recorded ``task_kind_floors`` entry exceeds their agent's bound model.

    The floors are resolved at init against the local ladder; the agent's model is the one
    ``bound_model_for`` reports, so a semantic-fallback binding (no pin) yields no gap —
    there is no rung to compare. The reasoner follows the orchestrator, so a kind with a
    ``highest`` floor on ``k_reasoner`` opens a gap whenever the orchestrator is below the top.
    """
    floors = config.get("task_kind_floors") if isinstance(config, dict) else None
    ladder = config.get("available") if isinstance(config, dict) else None
    if not isinstance(floors, dict) or not isinstance(ladder, list):
        return []
    gaps: list[FloorGap] = []
    for spec in agent_specs():
        bound = bound_model_for(config, spec.name)
        bound_rank = _rank(ladder, bound)
        if bound is None or bound_rank is None:
            continue
        for kind in spec.kinds:
            floor = floors.get(kind)
            floor_rank = _rank(ladder, floor)
            if floor_rank is not None and floor_rank > bound_rank:
                gaps.append(FloorGap(kind=kind, agent=spec.name, floor=floor, bound=bound))
    return gaps


def floor_gap_lines(config: dict) -> list[str]:
    """One context line per floor gap: which kind, which agent, and the override that meets it."""
    template = _agents_data()["floor_gap_line"]
    return [
        jsondata.fill(template, {"kind": gap.kind, "floor": gap.floor, "agent": gap.agent, "bound": gap.bound})
        for gap in floor_gaps(config)
    ]


def delegation_floor_warning(config: dict, subagent_type: str, call_model: object) -> str | None:
    """Per-call form of the floor check for the delegation log (C32).

    The call does not say which task kind it carries, so the warning is conditional on the
    kind; an explicit ``model`` override at or above every gapped floor silences it.
    """
    open_gaps = _open_floor_gaps(config, subagent_type, call_model)
    if not open_gaps:
        return None
    kinds = ", ".join(f"{gap.kind} (floor {gap.floor})" for gap in open_gaps)
    return jsondata.fill(
        _agents_data()["delegation_floor_warning"],
        {"subagent": subagent_type, "bound": open_gaps[0].bound, "kinds": kinds},
    )


def delegation_floor_directive(config: dict, subagent_type: str, call_model: object) -> str | None:
    """The model-addressed form of ``delegation_floor_warning``: from the next call on, the floor's model.

    Same predicate, same silence; the delegation log sends it as ``additionalContext`` beside
    the owner's ``systemMessage`` (ADR 0006 item 4, M149).
    """
    open_gaps = _open_floor_gaps(config, subagent_type, call_model)
    if not open_gaps:
        return None
    texts = _agents_data()["delegation_floor_directive"]
    overrides = "; ".join(jsondata.fill(texts["override"], {"kind": gap.kind, "floor": gap.floor}) for gap in open_gaps)
    return jsondata.fill(
        texts["text"], {"subagent": subagent_type, "bound": open_gaps[0].bound, "overrides": overrides}
    )


def _open_floor_gaps(config: dict, subagent_type: str, call_model: object) -> list[FloorGap]:
    """The agent's floor gaps the call's ``model`` override leaves open (C32)."""
    ladder = config.get("available") if isinstance(config, dict) else None
    gaps = [gap for gap in floor_gaps(config) if gap.agent == subagent_type]
    if not gaps or not isinstance(ladder, list):
        return []
    call_rank = _rank(ladder, call_model)
    return [gap for gap in gaps if call_rank is None or call_rank < ladder.index(gap.floor)]


def _escalation_hint(config: dict) -> str:
    """The recorded escalation path, named only when the binding pins concrete aliases."""
    binding = config.get("binding", {})
    path = binding.get("escalation") if isinstance(binding, dict) else None
    ladder = config.get("available")
    if not isinstance(path, list) or not path or not isinstance(ladder, list) or not ladder:
        return ""
    return f" (escalation path: {' → '.join(str(rung) for rung in path)})"


def status_lines(config: dict, registry: dict, init_command: str) -> list[str]:
    """The steady-state status injection: one binding line + self-check, plus any warning.

    ``init_command`` is how this project runs the routing initializer (``tool_command``). It is
    passed in rather than derived here because only the caller knows the project root; naming
    the mount unconditionally used to hand a package-mode session a path that does not exist.
    """
    binding = config.get("binding", {})
    orchestrator_vendor = str(config.get("vendor") or "anthropic")
    second_display, second_warning = _second_opinion_status(registry, config, orchestrator_vendor)
    orchestrator = config.get("orchestrator", "?")
    texts = _agents_data()["status_lines"]
    lines = [
        jsondata.fill(
            texts["binding"],
            {
                "vendor": orchestrator_vendor,
                "orchestrator": orchestrator,
                "reasoner": binding.get("reasoner", "?"),
                "auditor": binding.get("auditor", "?"),
                "worker": binding.get("worker", "?"),
                "mid": binding.get("mid", "?"),
                "second_opinion": second_display,
            },
        ),
        jsondata.fill(
            texts["delegation"],
            {"escalation_hint": _escalation_hint(config), "zone_convention": zone_convention()},
        ),
        jsondata.fill(texts["self_check"], {"orchestrator": orchestrator, "init_command": init_command}),
    ]
    warning = compute_binding(
        registry, orchestrator, config.get("available"), orchestrator_vendor, config.get("auditor_opt_in") or None
    ).warning
    if warning:
        lines.append(f"⚠ {warning}")
    if second_warning:
        lines.append(f"⚠ {second_warning}")
    lines.extend(floor_gap_lines(config))
    return lines


def rebind_notice(config: dict, registry: dict) -> list[str]:
    """The concise mid-session note after the orchestrator model changed (UserPromptSubmit).

    One line naming the new orchestrator and the recomputed subagent binding, plus the
    weak-orchestrator warning when it applies — that warning is exactly what the owner
    wants surfaced on a switch *down* to a thin model.
    """
    binding = config.get("binding", {})
    orchestrator = config.get("orchestrator", "?")
    vendor = str(config.get("vendor") or "anthropic")
    lines = [
        jsondata.fill(
            _agents_data()["rebind_notice"],
            {
                "orchestrator": orchestrator,
                "reasoner": binding.get("reasoner", "?"),
                "auditor": binding.get("auditor", "?"),
                "worker": binding.get("worker", "?"),
                "mid": binding.get("mid", "?"),
            },
        ),
    ]
    warning = compute_binding(
        registry, orchestrator, config.get("available"), vendor, config.get("auditor_opt_in") or None
    ).warning
    if warning:
        lines.append(f"⚠ {warning}")
    lines.extend(floor_gap_lines(config))
    return lines


def init_instruction(reason: str, init_command: str) -> list[str]:
    """The one-time setup instruction.

    ``init_command``: see ``status_lines`` — the recovery command must work in the tree this
    project actually has, mounted or installed.
    """
    values = {"reason": reason, "init_command": init_command}
    return [jsondata.fill(line, values) for line in _agents_data()["init_instruction"]]


# --------------------------------------------------------------------------------------
# Delegation log (the PreToolUse hook contract)
# --------------------------------------------------------------------------------------

_SUBAGENT_TOOLS = frozenset({"Task", "Agent"})


_ZONE_BRACKETED = re.compile(r"\[\s*zone\s*:\s*([^\]]*)\]\s*(.*)", re.ASCII | re.IGNORECASE | re.DOTALL)
# Unbracketed only as one token (``zone:auth``): with a space after the colon, prose such as
# "zone: the auth module" would otherwise yield the label "the".
_ZONE_BARE = re.compile(r"zone:(\S+)\s*(.*)", re.ASCII | re.IGNORECASE | re.DOTALL)
#: A zone label (C33 review): a letter or digit first, then letters, digits, ``-``, ``_`` or ``.``.
#: Unicode letters and digits count; anything else — a bracket, a lone ``-`` — is no label.
_ZONE_LABEL = re.compile(r"[^\W_][\w.-]*")


def zone_convention() -> str:
    """The zone-label convention as the orchestrator reads it.

    On the generated fan-out agents and in the status line's delegation guidance (C33).
    """
    return _agents_data()["zone_convention"]


#: Column counts for ``parse_delegation_entries``: the current schema (timestamp, session_id,
#: subagent, model, zone, description) and the legacy one (timestamp, subagent, model,
#: description — no session/zone).
_CURRENT_SCHEMA_COLUMNS = 6
_LEGACY_SCHEMA_COLUMNS = 4


def parse_zone(description: str) -> tuple[str | None, str]:
    """Split a leading ``[zone:LABEL]`` marker off a delegation description.

    The zone label rides in the description — the only free-form field a subagent call
    carries (§9.4/§10.3). A marker only counts at the very start:
    ``[zone:auth] check tokens`` -> ``("auth", "check tokens")``; tolerated alike (C33):
    any case, spaces inside the brackets, and the bare one-token ``zone:auth check tokens``.
    No marker -> ``(None, <description stripped>)``. A marker whose label is not a label —
    empty, or breaking ``_ZONE_LABEL`` (``[zone:-]``, ``zone:[auth]``, ``zone:auth]x``) — is
    still taken off the description but yields no label. The label keeps its case as written;
    the coverage map matches it case-insensitively.
    """
    text = description.strip()
    bracketed = _ZONE_BRACKETED.match(text)
    if bracketed:
        return (_zone_label(bracketed.group(1).strip()), bracketed.group(2).strip())
    bare = _ZONE_BARE.match(text)
    if bare:
        # C33: the unbracketed ``zone:X …`` spelling was observed live and used to leave the
        # whole fan-out unlabelled — an all-uncovered coverage map.
        return (_zone_label(bare.group(1).rstrip(",;:")), bare.group(2).strip())
    return (None, text)


def _zone_label(candidate: str) -> str | None:
    """``candidate`` when it is a well-formed zone label, else None."""
    return candidate if _ZONE_LABEL.fullmatch(candidate) else None


def unlabelled_fanout_warning(
    entries: Iterable[DelegationEntry], session_id: str | None, subagent: str, zone: str | None
) -> str | None:
    """Warn on an unlabelled fan-out delegation in a session that is running a zone plan (C33).

    A zone plan lives in the conversation, not in a file (§10.3), so the observable sign that
    one is active is that earlier delegations of this session carried zone labels. The
    auditor is exempt: an audit reads the fan-out, it is not a zone of it.
    """
    labelled = _zoned_labels(entries, session_id, subagent, zone)
    if not labelled:
        return None
    return jsondata.fill(
        _agents_data()["unlabelled_fanout_warning"], {"subagent": subagent, "labelled": ", ".join(labelled)}
    )


def unlabelled_fanout_directive(
    entries: Iterable[DelegationEntry], session_id: str | None, subagent: str, zone: str | None
) -> str | None:
    """The model-addressed form of ``unlabelled_fanout_warning``: label the fan-out calls.

    Same predicate, same silence; the delegation log sends it as ``additionalContext`` beside
    the owner's ``systemMessage`` (ADR 0006 item 4, M149).
    """
    labelled = _zoned_labels(entries, session_id, subagent, zone)
    if not labelled:
        return None
    return jsondata.fill(
        _agents_data()["unlabelled_fanout_directive"], {"subagent": subagent, "labelled": ", ".join(labelled)}
    )


def _zoned_labels(
    entries: Iterable[DelegationEntry], session_id: str | None, subagent: str, zone: str | None
) -> list[str]:
    """The session's earlier zone labels when this call should carry one too, else ``[]`` (C33)."""
    if zone or not session_id or subagent not in _agent_by_name() or subagent == "k_auditor":
        return []
    return sorted({e.zone for e in entries if e.session_id == session_id and e.zone})


def delegation_log_line(
    tool_name: str,
    tool_input: dict,
    timestamp: str,
    session_id: str | None = None,
    bound_model: str | None = None,
) -> str | None:
    """One TSV line per subagent delegation; None for any other tool.

    Columns: ``timestamp · session_id · subagent · model · zone · description``. The zone
    is parsed off a leading ``[zone:LABEL]`` marker in the description (removed from the
    stored description); ``-`` marks an absent session / model / zone. The model is the
    call's explicit override if given, else ``bound_model`` (the agent's recorded tier pin,
    derived by the caller so the record + console line name the declared model selection).
    ``session_id`` scopes a fan-out round for the coverage-map assembler (C17).
    """
    if tool_name not in _SUBAGENT_TOOLS:
        return None
    subagent = str(tool_input.get("subagent_type") or "-")
    model = str(tool_input.get("model") or bound_model or "-")
    raw_description = " ".join(str(tool_input.get("description") or "").split())
    zone, description = parse_zone(raw_description)
    return f"{timestamp}\t{session_id or '-'}\t{subagent}\t{model}\t{zone or '-'}\t{description}"


@dataclass(frozen=True)
class DelegationEntry:
    """One parsed delegation-log row (schema: see ``delegation_log_line``)."""

    timestamp: str
    session_id: str | None
    subagent: str
    model: str | None
    zone: str | None
    description: str


def _dash_to_none(value: str) -> str | None:
    value = value.strip()
    return None if value in ("", "-") else value


def parse_delegation_entries(lines: Iterable[str]) -> list[DelegationEntry]:
    """Parse delegation-log lines into entries.

    Handles the current 6-column schema and the legacy 4-column one (no session/zone) so
    a mixed local log still parses; lines with fewer than 4 fields are skipped.
    """
    entries: list[DelegationEntry] = []
    for raw in lines:
        line = raw.rstrip("\n")
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= _CURRENT_SCHEMA_COLUMNS:
            ts, sid, subagent, model, zone = parts[0], parts[1], parts[2], parts[3], parts[4]
            description = "\t".join(parts[5:])
        elif len(parts) >= _LEGACY_SCHEMA_COLUMNS:
            # Legacy: timestamp · subagent · model · description (no session / zone).
            ts, sid, subagent, model, zone = parts[0], "-", parts[1], parts[2], "-"
            description = "\t".join(parts[3:])
        else:
            continue
        entries.append(
            DelegationEntry(
                timestamp=ts,
                session_id=_dash_to_none(sid),
                subagent=subagent.strip(),
                model=_dash_to_none(model),
                zone=_dash_to_none(zone),
                description=description.strip(),
            )
        )
    return entries


# --------------------------------------------------------------------------------------
# C25 — the missed-gate forcing function: count a role's findings/options at the gate
# --------------------------------------------------------------------------------------


def read_local_config(project_root: Path) -> dict:
    """The project's recorded binding, or ``{}`` when it is absent or unreadable.

    The hooks that need the live binding all read the same file the same way; the one
    tolerated failure is a missing or malformed config, which means "not set up yet".
    """
    path = project_root / local_config_rel()
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


@dataclass(frozen=True)
class GateRule:
    """One role's count floor: which registry trigger it reads and what it counts."""

    role: str
    trigger: str
    noun: str
    #: Section headings that open the counted material, lowercased prefixes.
    headings: tuple[str, ...]
    #: Where the flow puts this gate, for the reason the hook hands back.
    anchor: str


def _gate_data() -> dict:
    """The shared gate texts and tables (``gate.json``), read on the call that needs it."""
    return jsondata.read(Path(__file__).parent / "gate.json")


def gate_rules() -> tuple[GateRule, ...]:
    """The two floors `gate_triggers` carries. A role outside this tuple has no count gate."""
    return tuple(
        GateRule(
            role=raw["role"],
            trigger=raw["trigger"],
            noun=raw["noun"],
            headings=tuple(raw["headings"]),
            anchor=raw["anchor"],
        )
        for raw in _gate_data()["gate_rules"]
    )


#: A markdown heading (`## Findings`) or a whole line in bold (`**Findings**`) — both are how
#: a role's output actually labels its sections; a bold line counts as the deepest level, so
#: the next heading of any level closes it.
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$", re.ASCII)
_BOLD_HEADING_RE = re.compile(r"^\*\*(.+?)\*\*:?\s*$", re.ASCII)
#: A heading's words, letters only: digits and punctuation never take one of the three
#: leading slots, and a non-latin script yields its words like any other (C98 measured a
#: latin-only split reading every Cyrillic heading as wordless, so no section ever opened).
_HEADING_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
#: A structural item: a bullet or a numbered item, at whatever depth it sits.
_LIST_ITEM_RE = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+\S", re.ASCII)
#: A table row that carries content — not the header separator `|---|---|`.
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$", re.ASCII)
_GATE_MARKER_PREFIX = "gate-audit"


def _heading(line: str) -> tuple[int, str] | None:
    """``(level, text)`` when ``line`` opens a section, else None. A bold line is level 7."""
    match = _MD_HEADING_RE.match(line)
    if match:
        return len(match.group(1)), match.group(2)
    bold = _BOLD_HEADING_RE.match(line)
    return (7, bold.group(1)) if bold else None


def _opens_section(text: str, headings: tuple[str, ...]) -> bool:
    """Whether a heading's text names the counted material (`Findings`, `3 findings`, `Options`)."""
    words = _HEADING_WORD_RE.findall(text.lower())
    return any(word.startswith(heading) for word in words[:3] for heading in headings)


def _gate_section_lines(message: str, rule: GateRule) -> Iterator[tuple[int, str]]:
    """``(section ordinal, line)`` for every body line under a ``rule`` section of ``message``.

    A section opens at a heading that names the counted material and closes at the next heading
    of the same or a higher level; a deeper heading inside it is neither yielded nor a closer.
    The ordinal tells a caller where one section's body ends and the next one's begins.
    """
    level, ordinal = None, 0
    for line in message.splitlines():
        heading = _heading(line)
        if heading is not None:
            opened, text = heading
            if level is not None and opened <= level:
                level = None
            if level is None and _opens_section(text, rule.headings):
                level, ordinal = opened, ordinal + 1
            continue
        if level is not None:
            yield ordinal, line


def count_gate_items(message: str, rule: GateRule) -> int:
    """Structural items under every ``rule`` section of ``message`` (C25's counting rule).

    Counted: the section's outermost bullets and numbered items, and table rows with content.
    An item indented deeper than the section's first one belongs to that item and is detail, a
    table's header and separator are not rows, and prose is not an item. Sections close at the
    next heading of the same or a higher level, so the material following a role's summary is
    not swept in. The base indent is per section: a section whose whole list sits inside a
    numbered step counts its items, not zero.
    """
    total, section, in_table, base = 0, 0, False, None
    for ordinal, line in _gate_section_lines(message, rule):
        if ordinal != section:
            section, in_table, base = ordinal, False, None
        if line.lstrip().startswith("|"):
            if _TABLE_SEPARATOR_RE.match(line):
                in_table = True  # the row above it was the header, not an item
                continue
            total += 1 if in_table else 0
            continue
        in_table = False
        item = _LIST_ITEM_RE.match(line)
        if item is None:
            continue
        indent = len(item.group(1))
        base = indent if base is None else min(base, indent)
        if indent <= base:
            total += 1
    return total


def gate_section_text(message: str, rule: GateRule) -> str:
    """The body of every ``rule`` section of ``message``, one line each — the material a gate counts.

    The headings are left out (a renamed heading over the same items is the same gate), and so
    are blank lines and every line outside the sections (the summary around them moves from turn
    to turn).
    """
    return "\n".join(line for _ordinal, line in _gate_section_lines(message, rule) if line.strip())


def gate_threshold(registry: dict, rule: GateRule) -> int | None:
    """``rule``'s count floor from the registry, or None when it is absent or not a count."""
    triggers = registry.get("gate_triggers") if isinstance(registry, dict) else None
    value = triggers.get(rule.trigger) if isinstance(triggers, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def gate_rule_for(role: str | None) -> GateRule | None:
    """The count gate for a declared role, or None for a role that has none."""
    return next((rule for rule in gate_rules() if rule.role == role), None)


def gate_audit_request(
    registry: dict, config: dict, role: str | None, message: str, gate_pack_command: str
) -> str | None:
    """The one thing the gate asks for when a role's count reached its floor, else None.

    The floor is advisory in the flows — the orchestrator may skip it — so the request names
    both live moves: run the audit, or say the skip out loud. What it does not allow is the
    gate passing unmentioned, which is the whole of C25. ``gate_pack_command`` is how this
    project runs the gate-pack tool (``tool_command``).
    """
    rule = gate_rule_for(role)
    threshold = gate_threshold(registry, rule) if rule is not None else None
    if rule is None or threshold is None:
        return None
    count = count_gate_items(message, rule)
    if count < threshold:
        return None
    auditor = bound_model_for(config, "k_auditor")
    model = f" (model={auditor})" if auditor else ""
    return (
        f"[akmon gate] This turn carries {count} {rule.noun} as the {rule.role} role, at or above the "
        f"`{rule.trigger}` floor of {threshold} — {rule.anchor} routes an `audit` pass here. "
        f"Before handing off: either delegate `k_auditor`{model} over the gate-pack "
        f"(`{gate_pack_command}`) and fold its verdict in, or state in one line that you "
        "are skipping the audit and why. The floor is advisory; passing it in silence is not."
    )


def gate_audit_marker_kind(message: str, rule: GateRule) -> str:
    """The marker kind for one gate episode: the role and a digest of the counted material.

    Keyed by content, not count (C25 review): two different gates with the same count are two
    gates, and the same material is one gate however the count moved in between.
    """
    digest = hashlib.sha256(gate_section_text(message, rule).encode("utf-8")).hexdigest()[:16]
    return f"{_GATE_MARKER_PREFIX}-{rule.role}-{digest}"


def gate_audit_once(role: str | None, message: str, session_id: str | None, *, marker_dir: Path | None = None) -> bool:
    """Claim this gate episode for ``session_id``; False when it was already asked for.

    Keyed by role and the counted material (C36 markers): the same Findings/Options never block
    twice in a session, while different material — even with the same count — is a new gate and
    is asked about again. Markers are not released on a new gate, so returning to material
    already held (3 → 4 → 3) does not hold it a second time; they age out with the C36 throttle.
    """
    rule = gate_rule_for(role)
    if rule is None:
        return False
    return claim_diagnostic_marker(gate_audit_marker_kind(message, rule), session_id, directory=marker_dir)
