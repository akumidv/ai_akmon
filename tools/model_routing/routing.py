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
import sys
import tempfile
from collections.abc import Iterable, Iterator
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
from common.runtime import harness_command


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


def settings_probe_names() -> tuple[str, ...]:
    """The ``.claude`` settings files the default-model probe reads, local first (single owner)."""
    return tuple(_agents_data()["settings_probe_names"])


def registry_path(akmon_dir: Path) -> Path:
    """Path to the shipped ``registry.json`` under an akmon tree."""
    return akmon_dir / "tools" / "model_routing" / "registry.json"


def overlay_path(project_root: Path) -> Path:
    """Path to the project's committed model-routing overlay file, if any."""
    return project_root / aitna_root_name() / overlay_name()


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_registry(akmon_dir: Path, project_root: Path | None = None) -> dict:
    """The merged registry: akmon data deep-merged with the project overlay (if any)."""
    registry = json.loads(registry_path(akmon_dir).read_text(encoding="utf-8"))
    if project_root is not None:
        overlay = overlay_path(project_root)
        if overlay.is_file():
            registry = _deep_merge(registry, json.loads(overlay.read_text(encoding="utf-8")))
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
    second_opinion_cli: str | None = None


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


def compute_binding(
    registry: dict,
    orchestrator: str,
    available: list[str] | None = None,
    vendor: str = "anthropic",
) -> Binding:
    """Bind tiers to model aliases from a semantic vendor policy (MODEL.md § Capability tiers).

    ``available`` is the concrete, local, discovery-derived ladder ordered weakest → strongest.
    The shared registry stores only the selection policy. Without ``available`` the binding uses
    semantic fallback labels and carries a warning; generated file-backed agents then omit concrete
    model frontmatter instead of pretending those labels are valid vendor model ids.
    """
    vendor_data = registry[vendor]
    semantic = not available
    rungs = list(available) if available else _semantic_rungs(vendor_data)
    if not rungs:
        rungs = _semantic_rungs(vendor_data)

    auditor = rungs[-1]  # pinned max, always — unlike the now-dynamic reasoner
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
        floor = policy.get("orchestrator_floor", "highest")
        floor_rung = rungs[-1] if floor == "highest" else str(floor)
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
                warning = jsondata.fill(
                    warnings["below_floor"], {"orchestrator": orchestrator, "floor": floor_rung}
                )
            elif orch_rank == len(rungs) - 1 and floor_rank < len(rungs) - 1:
                warning = jsondata.fill(
                    warnings["reserved_top"], {"orchestrator": orchestrator, "floor": floor_rung}
                )

    provider = opposite_vendor(registry, vendor)
    second_opinion = registry.get(provider, {}).get("second_opinion", {})
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
        second_opinion_cli=second_opinion.get("harness"),
    )


def task_kind_floors(registry: dict, rungs: list[str]) -> dict[str, str]:
    """Per-task-kind rung floors, resolved to concrete aliases from ``rungs``.

    Only task kinds carrying a ``"floor"`` key are included. ``"highest"`` resolves to
    ``rungs[-1]``; a literal alias passes through only when present in ``rungs``. A kind
    whose floor cannot be resolved (empty ``rungs``, or an alias absent from it) is skipped.
    """
    floors: dict[str, str] = {}
    if not rungs:
        return floors
    for kind, spec in registry.get("task_kinds", {}).items():
        floor = spec.get("floor")
        if not floor:
            continue
        if floor == "highest":
            floors[kind] = rungs[-1]
        elif floor in rungs:
            floors[kind] = str(floor)
    return floors


def vendors_with_routing_policy(registry: dict) -> list[str]:
    """Vendors that can run a main/orchestrator session under the semantic routing policy."""
    return [
        name
        for name, spec in registry.items()
        if isinstance(spec, dict) and isinstance(spec.get("selection_policy"), dict)
    ]


def opposite_vendor(registry: dict, vendor: str) -> str:
    """Default second-opinion provider: another configured vendor, preferring the recorded order."""
    for candidate in vendors_with_routing_policy(registry):
        if candidate != vendor and second_opinion_spec(registry, candidate, required=False):
            return candidate
    return vendor


def retired_second_opinion_keys() -> tuple[str, ...]:
    """Keys C57 retired when the executable moved into ``common/runtime.py``.

    A project overlay written before that change deep-merges *over* the shipped registry, so
    the new keys survive and the stale ones ride along unread — the config looks usable and
    silently means something else.
    """
    return tuple(_agents_data()["retired_second_opinion_keys"])


def second_opinion_spec(registry: dict, provider: str, *, required: bool = True) -> dict:
    """The second-opinion policy for one provider, or ``{}`` when it is absent and optional.

    A spec still carrying the retired keys always raises, in both the required and optional
    calls: it is a stale *configuration*, not an absent capability, and degrading it to "no
    second opinion available" would hide the migration behind a silently weaker run.
    """
    errors = _agents_data()["second_opinion_spec_errors"]
    spec = registry.get(provider, {}).get("second_opinion", {})
    if isinstance(spec, dict):
        retired = [key for key in retired_second_opinion_keys() if key in spec]
        if retired:
            raise KeyError(
                jsondata.fill(errors["retired_keys"], {"provider": provider, "retired": ", ".join(retired)})
            )
        if spec.get("harness") and spec.get("operation") and spec.get("report_dir"):
            return spec
    if required:
        raise KeyError(jsondata.fill(errors["no_usable_spec"], {"provider": provider}))
    return {}


def second_opinion_fallback_model(rungs: list[str], orchestrator: str, auditor: str) -> str | None:
    """The same-vendor fallback rung when no other vendor is reachable (design §9.7 #2).

    The diversity requirement is about *model* priors, not vendor branding: the strongest
    rung that differs from both the orchestrator (the author) and the auditor. ``None`` when
    no rung differs from the orchestrator at all (a single distinct rung) — the caller warns
    or skips; it must never fall back to the same model.
    """
    for rung in reversed(rungs):
        if rung not in (orchestrator, auditor):
            return rung
    return None


def second_opinion_command(spec: dict, prompt: str, model: str | None = None) -> list[str]:
    """Build the non-interactive CLI command; the prompt is passed as the final argv.

    The executable and the operation's argv come from the single owner in ``common/runtime.py``;
    the registry contributes only *policy* — which harness, which operation, and the optional
    ``model_flag`` format string (e.g. ``"--model {model}"``) inserted before the prompt so the
    same-vendor branch of the diversity ladder can pin a *different* model.

    A requested ``model`` with no ``model_flag`` raises ``UnpinnableModelError`` (C97): the run
    would otherwise go out on the harness's default model and still be filed as a model-diverse
    second opinion — the one guarantee the ladder exists to give, lost without a signal.
    """
    argv = harness_command(str(spec["harness"]), str(spec["operation"]))
    if model:
        model_flag = spec.get("model_flag")
        if not model_flag:
            raise UnpinnableModelError(str(spec["harness"]), model)
        argv += shlex.split(str(model_flag).format(model=model))
    return [*argv, prompt]


class UnpinnableModelError(ValueError):
    """A second opinion asked for a model its vendor declares no ``model_flag`` to pin (C97)."""

    def __init__(self, harness: str, model: str) -> None:
        super().__init__(
            jsondata.fill(
                _agents_data()["unpinnable_model"], {"model": repr(model), "harness": harness}
            )
        )


def second_opinion_unavailability(registry: dict, config: dict, orchestrator_vendor: str) -> str:
    """Why no model-diverse reviewer exists, walked step by step over the configured ladder.

    Deliberately not a second verdict: ``resolve_second_opinion`` owns the answer. This states,
    per ladder step, the population that step had — and it states a *conclusion* ("nothing
    differs") only where it derives one from the same helper the ladder uses. A step that was
    never attempted says so instead of being explained away, because an overlay can shorten
    the ladder, and "no diverse reviewer" then means something entirely different.
    """
    policy = registry.get("second_opinion_policy", {}) if isinstance(registry, dict) else {}
    ladder = policy.get("diversity_ladder") or ["other-vendor", "same-vendor-other-model"]
    others = [
        vendor
        for vendor in vendors_with_routing_policy(registry)
        if vendor != orchestrator_vendor and second_opinion_spec(registry, vendor, required=False)
    ]
    configured = config.get("second_opinion_provider")
    rungs = config.get("available") or _semantic_rungs(registry.get(orchestrator_vendor, {}))
    orchestrator = str(config.get("orchestrator") or "?")
    auditor = str(config.get("binding", {}).get("auditor") or "?")
    against = f"the orchestrator '{orchestrator}' and the auditor '{auditor}'"
    texts = _agents_data()["second_opinion_unavailability"]

    if "other-vendor" not in ladder:
        other_vendor = texts["other_vendor_absent"]
    elif not others:
        other_vendor = texts["other_vendor_none"]
    elif isinstance(configured, str) and configured == orchestrator_vendor:
        other_vendor = jsondata.fill(
            texts["other_vendor_pinned"], {"configured": configured, "others": ", ".join(others)}
        )
    else:
        other_vendor = jsondata.fill(texts["other_vendor_usable"], {"others": ", ".join(others)})

    if "same-vendor-other-model" not in ladder:
        same_vendor = texts["same_vendor_absent"]
    elif second_opinion_fallback_model(rungs, orchestrator, auditor) is None:
        same_vendor = jsondata.fill(
            texts["same_vendor_no_diverse_rung"],
            {"vendor": orchestrator_vendor, "rungs": repr(rungs), "against": against},
        )
    else:
        same_vendor = jsondata.fill(
            texts["same_vendor_diverse_rung"],
            {"vendor": orchestrator_vendor, "rungs": repr(rungs), "against": against},
        )
    return f"{other_vendor}; {same_vendor}"


@dataclass(frozen=True)
class SecondOpinionTarget:
    """A resolved second-opinion target: which provider, and which model to pin (if any)."""

    provider: str
    model: str | None  # None = the provider CLI's default model (other-vendor case)


def resolve_second_opinion(registry: dict, config: dict, orchestrator_vendor: str) -> SecondOpinionTarget | None:
    """Walk `second_opinion_policy.diversity_ladder` to a (provider, model) target.

    Diversity is about *model priors* (design §9.3 item 3): the reviewer must differ
    from the models it reviews. Ladder steps (registry data):
      - "other-vendor": another configured vendor with a usable spec — different priors
        by construction, so model=None (its CLI default is already a different model);
      - "same-vendor-other-model": the same vendor, pinned to the strongest rung that
        differs from BOTH orchestrator (author) and auditor, via
        `second_opinion_fallback_model` (design §9.7 #2);
      - `never: same-model` — if no rung differs, return None (skip); the caller must
        never fall back to the same model.

    An explicit `config["second_opinion_provider"]` is honored: a configured *other*
    vendor satisfies the other-vendor step; configured == orchestrator vendor routes to
    the same-vendor branch.
    """
    policy = registry.get("second_opinion_policy", {}) if isinstance(registry, dict) else {}
    ladder = policy.get("diversity_ladder") or ["other-vendor", "same-vendor-other-model"]
    orchestrator = str(config.get("orchestrator") or "")
    auditor = str(config.get("binding", {}).get("auditor") or "")
    configured = config.get("second_opinion_provider")
    for step in ladder:
        if step == "other-vendor":
            # An explicit same-vendor override is a deliberate "stay on my vendor, pin a
            # different model" choice — skip the other-vendor step so it falls through to
            # same-vendor-other-model rather than silently picking the opposite vendor.
            if isinstance(configured, str) and configured == orchestrator_vendor:
                continue
            provider = (
                configured
                if isinstance(configured, str) and configured and configured != orchestrator_vendor
                else opposite_vendor(registry, orchestrator_vendor)
            )
            if provider != orchestrator_vendor and second_opinion_spec(registry, provider, required=False):
                return SecondOpinionTarget(provider, None)
        elif step == "same-vendor-other-model":
            provider = orchestrator_vendor
            if not second_opinion_spec(registry, provider, required=False):
                continue
            model = config.get("second_opinion_fallback_model")
            if not model:
                rungs = config.get("available") or _semantic_rungs(registry.get(provider, {}))
                model = second_opinion_fallback_model(rungs, orchestrator, auditor)
            if model:
                return SecondOpinionTarget(provider, str(model))
    return None


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
    if (
        not isinstance(available, list)
        or not available
        or not all(isinstance(alias, str) for alias in available)
        or model not in available
    ):
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
    return jsondata.fill(
        _agents_data()["role_matrix_warning"],
        {"subagent": subagent_type, "kinds": ", ".join(kinds), "role": role, "allowed": allowed_text},
    )


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
    (meta/reviews/c80-context-fill-20260912.md).
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
    registry: dict, binding: Binding, *, second_opinion: bool, available: list[str] | None
) -> dict[str, str]:
    """Every generated routing artifact as ``project-root-relative path → content``.

    The generated ``k_*`` subagent definitions plus the local config — the single set the
    init tool and the SessionStart/UserPromptSubmit hook both write, so a rebind from
    either path produces byte-identical files.
    """
    files = dict(generated_agent_files(registry, binding))
    config = local_config(binding, registry, second_opinion=second_opinion, available=available)
    files[local_config_rel()] = json.dumps(config, indent=2) + "\n"
    return files


def obsolete_agent_files(root: Path, planned_paths: Iterable[Path]) -> list[Path]:
    """Generated subagent definitions on disk that the current ``agent_specs()`` no longer plan.

    Only files carrying ``generated_banner()`` are candidates, so a hand-written agent living in
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
        if generated_banner() in text:
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

    Reuses the recorded ``available`` list and opt-ins from ``config`` — only the
    orchestrator moves. Idempotent: unchanged files are left untouched. This is how the
    hook makes subagent models follow the session's actual orchestrating model.
    """
    available = config.get("available")
    second_opinion = bool(config.get("second_opinion"))
    vendor = str(config.get("vendor") or "anthropic")
    binding = compute_binding(registry, orchestrator, available, vendor)
    files = binding_artifacts(registry, binding, second_opinion=second_opinion, available=available)
    changed = write_artifacts(root, files, write=write)
    remove_obsolete_agents(root, (root / rel for rel in files), write=write)
    return binding, changed


def local_config(binding: Binding, registry: dict, *, second_opinion: bool, available: list[str] | None) -> dict:
    """The per-user resolved config written to ``local_config_rel()`` (binding, opt-ins, staleness hash)."""
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
        "second_opinion_provider": opposite_vendor(registry, binding.vendor),
        "available": available,
        "registry_hash": registry_hash(registry),
        "task_kind_floors": task_kind_floors(registry, available or []),
    }
    provider = config["second_opinion_provider"]
    if provider == binding.vendor:
        rungs = list(available) if available else _semantic_rungs(registry.get(binding.vendor, {}))
        config["second_opinion_fallback_model"] = second_opinion_fallback_model(
            rungs, binding.orchestrator, binding.auditor
        )
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

    Resolved through the same ladder the runner walks (``resolve_second_opinion``) rather
    than through the pre-ladder ``second_opinion_provider``: the latter names the
    *configured* provider, so an installation whose ladder is exhausted still read
    ``second-opinion=<harness>(on)`` while every gate silently skipped. A display that can
    disagree with the policy is a second owner of one fact — the drift class C46 exists to
    remove — so this one asks the policy.
    """
    enabled = bool(config.get("second_opinion"))
    state = "on" if enabled else "off"
    # A retired-key overlay (C57, ADR-0004/D02) raises out of here, deliberately and not only here:
    # ``compute_binding`` reaches the same spec through ``opposite_vendor``, so a stale
    # overlay costs the whole status block, not this field. Catching it locally would look
    # like resilience while changing nothing, so the raise is left to travel.
    target = resolve_second_opinion(registry, config, orchestrator_vendor)
    if target is None:
        warning = (
            "second-opinion is on but the diversity ladder is exhausted: no reachable "
            "provider differs from the reviewed model, so every gate will skip it — "
            "second_opinion.py states the reason at the gate and names the one thing that "
            "can still be run by hand, with its limits"
        )
        return f"second-opinion=unavailable({state})", warning if enabled else None
    harness = str(second_opinion_spec(registry, target.provider, required=False).get("harness") or "-")
    pin = f", model={target.model}" if target.model else ""
    return f"second-opinion={harness}({state}{pin})", None


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
    ladder = config.get("available") if isinstance(config, dict) else None
    gaps = [gap for gap in floor_gaps(config) if gap.agent == subagent_type]
    if not gaps or not isinstance(ladder, list):
        return None
    call_rank = _rank(ladder, call_model)
    open_gaps = [gap for gap in gaps if call_rank is None or call_rank < ladder.index(gap.floor)]
    if not open_gaps:
        return None
    kinds = ", ".join(f"{gap.kind} (floor {gap.floor})" for gap in open_gaps)
    return jsondata.fill(
        _agents_data()["delegation_floor_warning"],
        {"subagent": subagent_type, "bound": open_gaps[0].bound, "kinds": kinds},
    )


def _escalation_hint(config: dict) -> str:
    """The recorded escalation path, named only when the binding pins concrete aliases."""
    binding = config.get("binding", {})
    path = binding.get("escalation") if isinstance(binding, dict) else None
    ladder = config.get("available")
    if not isinstance(path, list) or not path or not isinstance(ladder, list) or not ladder:
        return ""
    return f" (escalation path: {' → '.join(str(rung) for rung in path)})"


def status_lines(config: dict, registry: dict, runtime_root: str) -> list[str]:
    """The steady-state status injection: one binding line + self-check, plus any warning.

    ``runtime_root`` is the project-root-relative directory the routing tools actually live in
    — ``<AITNA_ROOT>/akmon`` when the standard is mounted, ``<AITNA_ROOT>/.akmon`` in mount mode
    ``package``, where there is no mount at all (ADR 0009 §4). It is passed in rather than
    derived here because only the caller knows the project root; naming the mount
    unconditionally used to hand a package-mode session a path that does not exist.
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
        jsondata.fill(texts["self_check"], {"orchestrator": orchestrator, "runtime_root": runtime_root}),
    ]
    warning = compute_binding(registry, orchestrator, config.get("available"), orchestrator_vendor).warning
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
    warning = compute_binding(registry, orchestrator, config.get("available"), vendor).warning
    if warning:
        lines.append(f"⚠ {warning}")
    lines.extend(floor_gap_lines(config))
    return lines


def init_instruction(reason: str, runtime_root: str) -> list[str]:
    """The one-time setup instruction.

    ``runtime_root``: see ``status_lines`` — the recovery path must name the tree this
    project actually has, mounted or materialized.
    """
    values = {"reason": reason, "runtime_root": runtime_root}
    return [jsondata.fill(line, values) for line in _agents_data()["init_instruction"]]


# --------------------------------------------------------------------------------------
# Delegation log (the PreToolUse hook contract)
# --------------------------------------------------------------------------------------

_SUBAGENT_TOOLS = frozenset({"Task", "Agent"})


_ZONE_BRACKETED = re.compile(r"\[\s*zone\s*:\s*([^\]]*)\]\s*(.*)", re.ASCII | re.IGNORECASE | re.DOTALL)
# Unbracketed only as one token (``zone:auth``): with a space after the colon, prose such as
# "zone: the auth module" would otherwise yield the label "the".
_ZONE_BARE = re.compile(r"zone:(\S+)\s*(.*)", re.ASCII | re.IGNORECASE | re.DOTALL)


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
    No marker -> ``(None, <description stripped>)``.
    """
    text = description.strip()
    bracketed = _ZONE_BRACKETED.match(text)
    if bracketed:
        return (bracketed.group(1).strip() or None, bracketed.group(2).strip())
    bare = _ZONE_BARE.match(text)
    if bare:
        # C33: the unbracketed ``zone:X …`` spelling was observed live and used to leave the
        # whole fan-out unlabelled — an all-uncovered coverage map.
        return (bare.group(1).rstrip(",;:") or None, bare.group(2).strip())
    return (None, text)


def unlabelled_fanout_warning(
    entries: Iterable[DelegationEntry], session_id: str | None, subagent: str, zone: str | None
) -> str | None:
    """Warn on an unlabelled fan-out delegation in a session that is running a zone plan (C33).

    A zone plan lives in the conversation, not in a file (§10.3), so the observable sign that
    one is active is that earlier delegations of this session carried zone labels. The
    auditor is exempt: an audit reads the fan-out, it is not a zone of it.
    """
    if zone or not session_id or subagent not in _agent_by_name() or subagent == "k_auditor":
        return None
    labelled = sorted({e.zone for e in entries if e.session_id == session_id and e.zone})
    if not labelled:
        return None
    return jsondata.fill(
        _agents_data()["unlabelled_fanout_warning"], {"subagent": subagent, "labelled": ", ".join(labelled)}
    )


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


def count_gate_items(message: str, rule: GateRule) -> int:
    """Structural items under every ``rule`` section of ``message`` (C25's counting rule).

    Counted: the section's outermost bullets and numbered items, and table rows with content.
    An item indented deeper than the section's first one belongs to that item and is detail, a
    table's header and separator are not rows, and prose is not an item. Sections close at the
    next heading of the same or a higher level, so the material following a role's summary is
    not swept in. The base indent is per section: a section whose whole list sits inside a
    numbered step counts its items, not zero.
    """
    total, level, in_table, base = 0, None, False, None
    for line in message.splitlines():
        heading = _heading(line)
        if heading is not None:
            opened, text = heading
            if level is not None and opened <= level:
                level, in_table, base = None, False, None
            if level is None and _opens_section(text, rule.headings):
                level, base = opened, None
            continue
        if level is None:
            continue
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


def gate_threshold(registry: dict, rule: GateRule) -> int | None:
    """``rule``'s count floor from the registry, or None when it is absent or not a count."""
    triggers = registry.get("gate_triggers") if isinstance(registry, dict) else None
    value = triggers.get(rule.trigger) if isinstance(triggers, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def gate_rule_for(role: str | None) -> GateRule | None:
    """The count gate for a declared role, or None for a role that has none."""
    return next((rule for rule in gate_rules() if rule.role == role), None)


def gate_audit_request(registry: dict, config: dict, role: str | None, message: str) -> str | None:
    """The one thing the gate asks for when a role's count reached its floor, else None.

    The floor is advisory in the flows — the orchestrator may skip it — so the request names
    both live moves: run the audit, or say the skip out loud. What it does not allow is the
    gate passing unmentioned, which is the whole of C25.
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
        "(`tools/model_routing/gate_pack.py`) and fold its verdict in, or state in one line that you "
        "are skipping the audit and why. The floor is advisory; passing it in silence is not."
    )


def gate_audit_marker_kind(rule: GateRule, count: int) -> str:
    """The marker kind for one gate episode: role and count, so a changed count asks again."""
    return f"{_GATE_MARKER_PREFIX}-{rule.role}-{count}"


def gate_audit_once(role: str | None, message: str, session_id: str | None, *, marker_dir: Path | None = None) -> bool:
    """Claim this gate episode for ``session_id``; False when it was already asked for.

    Keyed by role and count (C36 markers): the same material never blocks twice, while a later
    turn that carries a different count is a new gate and is asked about again.
    """
    rule = gate_rule_for(role)
    if rule is None:
        return False
    kind = gate_audit_marker_kind(rule, count_gate_items(message, rule))
    claimed = claim_diagnostic_marker(kind, session_id, directory=marker_dir)
    release_diagnostic_markers(_GATE_MARKER_PREFIX, session_id, keep_kind=kind, directory=marker_dir)
    return claimed
