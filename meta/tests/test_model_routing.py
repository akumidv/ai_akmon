"""Unit tests for the model-routing core (``tools/model_routing/routing.py``) and init tool.

These build throwaway project trees under ``tmp_path``; nothing touches the real repo.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from pathlib import Path

_KEYSTONE = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_ROUTING_DIR = _KEYSTONE / "tools" / "model_routing"
if str(_ROUTING_DIR) not in sys.path:
    sys.path.insert(0, str(_ROUTING_DIR))

import routing  # noqa: E402


def _load_init():
    spec = importlib.util.spec_from_file_location("model_routing_init", _ROUTING_DIR / "init.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REGISTRY = json.loads((_ROUTING_DIR / "registry.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------
# compute_binding
# --------------------------------------------------------------------------------------


def test_binding_from_local_available_list_top_orchestrator():
    binding = routing.compute_binding(REGISTRY, "large", available=["small", "medium", "large"])
    assert binding.reasoner == "large"
    assert binding.auditor == "large"
    assert binding.worker == "small"
    assert binding.mid == "medium"
    assert binding.escalation == ("medium",)
    assert binding.warning is None


def test_binding_reasoner_follows_orchestrator_rung():
    """Dynamic reasoner: defaults to the orchestrator's own rung, not the top rung."""
    binding = routing.compute_binding(REGISTRY, "medium", available=["small", "medium", "large"])
    assert binding.reasoner == "medium"
    assert binding.auditor == "large"  # auditor stays pinned to the top rung


def test_binding_auditor_pinned_to_top_regardless_of_orchestrator():
    for orchestrator in ("small", "medium", "large"):
        binding = routing.compute_binding(REGISTRY, orchestrator, available=["small", "medium", "large"])
        assert binding.auditor == "large"


def test_binding_corridor_below_floor_warns():
    binding = routing.compute_binding(REGISTRY, "sonnet", available=["haiku", "sonnet", "opus", "fable"])
    assert binding.warning is not None
    assert "below the orchestration floor (opus)" in binding.warning
    # The binding itself is unchanged — the warning is advisory only.
    assert binding.auditor == "fable"


def test_binding_corridor_healthy_orchestrator_is_silent():
    binding = routing.compute_binding(REGISTRY, "opus", available=["haiku", "sonnet", "opus", "fable"])
    assert binding.warning is None


def test_binding_corridor_reserved_top_rung_warns_wasteful():
    binding = routing.compute_binding(REGISTRY, "fable", available=["haiku", "sonnet", "opus", "fable"])
    assert binding.warning is not None
    assert "reserved top rung" in binding.warning
    assert "/model down to opus" in binding.warning


def test_binding_corridor_collapse_to_floor_without_top_is_silent():
    # fable unavailable: the ladder tops out at the floor → floor == top → no warning,
    # and every high tier collapses to the floor (the accepted degraded mode).
    binding = routing.compute_binding(REGISTRY, "opus", available=["haiku", "sonnet", "opus"])
    assert binding.warning is None
    assert binding.reasoner == "opus"
    assert binding.auditor == "opus"


def test_binding_corridor_disabled_when_floor_not_in_ladder():
    # An abstract ladder without the named floor alias: nothing to rank against → silent.
    binding = routing.compute_binding(REGISTRY, "medium", available=["small", "medium", "large"])
    assert binding.warning is None


def test_binding_openai_keeps_relative_highest_floor():
    binding = routing.compute_binding(REGISTRY, "medium", available=["small", "medium", "large"], vendor="openai")
    assert binding.warning is not None
    assert "below the orchestration floor (large)" in binding.warning


def test_binding_unknown_orchestrator_warns_without_ranking():
    binding = routing.compute_binding(REGISTRY, "mystery-model", available=["small", "medium", "large"])
    assert binding.warning is not None
    assert "not in the discovered model list" in binding.warning


def test_binding_reasoner_falls_back_to_top_for_unknown_orchestrator():
    binding = routing.compute_binding(REGISTRY, "mystery-model", available=["small", "medium", "large"])
    assert binding.reasoner == "large"


def test_binding_available_filter_caps_reasoner_and_auditor():
    binding = routing.compute_binding(REGISTRY, "medium", available=["small", "medium"])
    assert binding.reasoner == "medium"
    assert binding.auditor == "medium"
    assert binding.worker == "small"
    assert binding.mid == "medium"
    assert binding.escalation == ()


def test_binding_single_rung_collapses_all_tiers():
    binding = routing.compute_binding(REGISTRY, "only", available=["only"])
    assert (binding.reasoner, binding.worker, binding.mid, binding.auditor) == ("only", "only", "only", "only")


def test_binding_openai_policy_for_codex_models():
    binding = routing.compute_binding(REGISTRY, "large", available=["small", "medium", "large"], vendor="openai")
    assert binding.vendor == "openai"
    assert binding.reasoner == "large"
    assert binding.auditor == "large"
    assert binding.worker == "small"
    assert binding.mid == "medium"
    assert binding.escalation == ("medium",)
    assert binding.second_opinion_cli == "claude"


def test_binding_without_available_uses_semantic_fallback_and_omits_agent_models():
    binding = routing.compute_binding(REGISTRY, "strongest")
    files = routing.generated_agent_files(REGISTRY, binding)

    assert binding.semantic_fallback is True
    assert binding.worker == "worker"
    assert binding.mid == "mid"
    assert binding.reasoner == "strongest"
    assert binding.auditor == "strongest"
    assert binding.warning is not None
    assert "model:" not in files[".claude/agents/k-explorer.md"]


def test_task_kind_floors_resolves_highest():
    floors = routing.task_kind_floors(REGISTRY, ["small", "medium", "large"])
    assert floors == {"quant-derivation": "large"}


def test_task_kind_floors_empty_without_rungs():
    assert routing.task_kind_floors(REGISTRY, []) == {}


def test_second_opinion_fallback_model_top_orchestrator_returns_rung_below_top():
    # orchestrator == auditor == top rung → the answer is the rung below the top.
    assert routing.second_opinion_fallback_model(["small", "medium", "large"], "large", "large") == "medium"


def test_second_opinion_fallback_model_mid_orchestrator_returns_top():
    assert routing.second_opinion_fallback_model(["small", "medium", "large"], "medium", "large") == "small"


def test_second_opinion_fallback_model_single_rung_returns_none():
    assert routing.second_opinion_fallback_model(["only"], "only", "only") is None


def test_second_opinion_defaults_to_opposite_vendor_and_builds_command():
    binding = routing.compute_binding(REGISTRY, "large", available=["small", "medium", "large"], vendor="openai")
    config = routing.local_config(binding, REGISTRY, second_opinion=True, available=None)
    provider = routing.second_opinion_provider(REGISTRY, config, "openai")
    spec = routing.second_opinion_spec(REGISTRY, provider)

    assert provider == "anthropic"
    assert spec["cli"] == "claude"
    assert routing.second_opinion_command(spec, "review this") == [
        "claude",
        "-p",
        "--output-format",
        "text",
        "review this",
    ]


# --------------------------------------------------------------------------------------
# registry loading: overlay merge + hash
# --------------------------------------------------------------------------------------


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    akmon = tmp_path / "_aitna" / "akmon" / "tools" / "model_routing"
    akmon.mkdir(parents=True)
    (akmon / "registry.json").write_text(json.dumps(REGISTRY), encoding="utf-8")
    return tmp_path


def test_overlay_deep_merges_and_changes_hash(tmp_path):
    root = _make_project(tmp_path)
    akmon_dir = root / "_aitna" / "akmon"
    base = routing.load_registry(akmon_dir, root)
    base_hash = routing.registry_hash(base)

    overlay = {
        "anthropic": {"semantic_fallback": {"worker": "local-worker"}},
        "briefs": {"k-explorer": "Project note."},
    }
    routing.overlay_path(root).write_text(json.dumps(overlay), encoding="utf-8")
    merged = routing.load_registry(akmon_dir, root)

    assert merged["anthropic"]["semantic_fallback"]["worker"] == "local-worker"
    assert merged["anthropic"]["selection_policy"] == REGISTRY["anthropic"]["selection_policy"]  # untouched by merge
    assert merged["briefs"]["k-explorer"] == "Project note."
    assert routing.registry_hash(merged) != base_hash


# --------------------------------------------------------------------------------------
# generated agents
# --------------------------------------------------------------------------------------


def test_generated_agents_cover_all_specs_with_models():
    binding = routing.compute_binding(REGISTRY, "large", available=["small", "medium", "large"])
    files = routing.generated_agent_files(REGISTRY, binding)
    assert set(files) == {
        ".claude/agents/k-explorer.md",
        ".claude/agents/k-mechanic.md",
        ".claude/agents/k-validator.md",
        ".claude/agents/k-implementer.md",
        ".claude/agents/k-reasoner.md",
        ".claude/agents/k-auditor.md",
    }
    assert "model: small" in files[".claude/agents/k-explorer.md"]
    assert "model: medium" in files[".claude/agents/k-implementer.md"]
    assert "model: large" in files[".claude/agents/k-reasoner.md"]
    assert "model: large" in files[".claude/agents/k-auditor.md"]
    for content in files.values():
        assert content.startswith("---\n")
        assert routing.GENERATED_BANNER in content


def test_generated_k_auditor_is_read_only():
    binding = routing.compute_binding(REGISTRY, "large", available=["small", "medium", "large"])
    files = routing.generated_agent_files(REGISTRY, binding)
    content = files[".claude/agents/k-auditor.md"]
    assert "tools: Read, Grep, Glob, Bash" in content


def test_generated_agent_appends_overlay_brief():
    binding = routing.compute_binding(REGISTRY, "large", available=["small", "medium", "large"])
    registry = dict(REGISTRY, briefs={"k-implementer": "Use the project data dictionary."})
    files = routing.generated_agent_files(registry, binding)
    assert "Use the project data dictionary." in files[".claude/agents/k-implementer.md"]
    assert "project data dictionary" not in files[".claude/agents/k-mechanic.md"]


def test_agent_specs_cover_every_delegable_task_kind():
    delegable = {
        kind
        for kind, spec in REGISTRY["task_kinds"].items()
        if spec["tier"] in ("worker", "reasoner", "auditor")
    }
    covered = {kind for spec in routing.AGENT_SPECS for kind in spec.kinds}
    assert covered == delegable


# --------------------------------------------------------------------------------------
# role_task_kinds
# --------------------------------------------------------------------------------------


def test_role_task_kinds_reference_only_known_task_kinds():
    known = set(REGISTRY["task_kinds"])
    for role, kinds in REGISTRY["role_task_kinds"].items():
        for kind in kinds:
            assert kind in known, f"role_task_kinds[{role!r}] references unknown kind {kind!r}"


def test_role_task_kinds_review_never_routes_edit_kinds():
    edit_kinds = {"mech-edit", "implement-under-spec", "test-scaffold", "validate-loop"}
    review_kinds = set(REGISTRY["role_task_kinds"]["review"])
    assert not (review_kinds & edit_kinds)


def test_role_task_kinds_engineer_never_routes_design_fork():
    assert "design-fork" not in REGISTRY["role_task_kinds"]["engineer"]


# --------------------------------------------------------------------------------------
# local config + staleness + status lines
# --------------------------------------------------------------------------------------


def _fresh_config() -> dict:
    binding = routing.compute_binding(REGISTRY, "large", available=["small", "medium", "large"])
    return routing.local_config(binding, REGISTRY, second_opinion=True, available=["small", "medium", "large"])


def test_staleness_fresh_config_is_none():
    assert routing.staleness(_fresh_config(), REGISTRY, settings_model=None) is None
    assert routing.staleness(_fresh_config(), REGISTRY, settings_model="large") is None


def test_staleness_missing_config():
    assert "not initialized" in routing.staleness({}, REGISTRY, None)


def test_staleness_on_registry_change():
    changed = dict(REGISTRY, briefs={"k-explorer": "new"})
    assert "changed since init" in routing.staleness(_fresh_config(), changed, None)


def test_staleness_on_settings_model_mismatch():
    assert "differs" in routing.staleness(_fresh_config(), REGISTRY, settings_model="medium")


def test_status_lines_name_binding_and_self_check():
    lines = routing.status_lines(_fresh_config(), REGISTRY, "_aitna")
    joined = "\n".join(lines)
    assert "orchestrator=large" in joined
    assert "auditor=large" in joined
    assert "worker=small" in joined
    assert "second-opinion=codex(on)" in joined
    assert "Self-check" in joined
    assert "⚠" not in joined


def test_status_lines_warn_when_orchestrator_leaves_corridor():
    ladder = ["haiku", "sonnet", "opus", "fable"]
    binding = routing.compute_binding(REGISTRY, "sonnet", available=ladder)
    config = routing.local_config(binding, REGISTRY, second_opinion=False, available=ladder)
    joined = "\n".join(routing.status_lines(config, REGISTRY, "_aitna"))
    assert "⚠" in joined and "below the orchestration floor" in joined


# --------------------------------------------------------------------------------------
# local_config: auditor, task_kind_floors, second-opinion fallback model
# --------------------------------------------------------------------------------------


def test_local_config_carries_auditor_and_task_kind_floors():
    config = _fresh_config()
    assert config["binding"]["auditor"] == "large"
    assert config["task_kind_floors"] == {"quant-derivation": "large"}


def test_local_config_no_task_kind_floors_without_available():
    binding = routing.compute_binding(REGISTRY, "large")
    config = routing.local_config(binding, REGISTRY, second_opinion=False, available=None)
    assert config["task_kind_floors"] == {}


def test_local_config_carries_fallback_model_when_provider_equals_vendor(tmp_path):
    # Force a registry with a single vendor so the second-opinion provider falls back to
    # the orchestrating vendor itself (opposite_vendor has nowhere else to go).
    single_vendor_registry = {k: v for k, v in REGISTRY.items() if k != "openai"}
    available = ["small", "medium", "large"]
    binding = routing.compute_binding(single_vendor_registry, "large", available=available)
    config = routing.local_config(binding, single_vendor_registry, second_opinion=True, available=available)
    assert config["second_opinion_provider"] == "anthropic"
    assert config["second_opinion_fallback_model"] == "medium"


# --------------------------------------------------------------------------------------
# delegation log
# --------------------------------------------------------------------------------------


def test_delegation_log_line_for_subagent_tools():
    line = routing.delegation_log_line(
        "Agent",
        {"subagent_type": "k-explorer", "model": "small", "description": "find  X"},
        "T0",
        "sess-1",
    )
    # timestamp · session_id · subagent · model · zone · description
    assert line == "T0\tsess-1\tk-explorer\tsmall\t-\tfind X"
    assert routing.delegation_log_line("Task", {}, "T0") == "T0\t-\t-\t-\t-\t"


def test_delegation_log_line_parses_zone_marker():
    line = routing.delegation_log_line(
        "Agent",
        {"subagent_type": "k-explorer", "model": "small", "description": "[zone:auth]  check tokens"},
        "T0",
        "sess-1",
    )
    assert line == "T0\tsess-1\tk-explorer\tsmall\tauth\tcheck tokens"


def test_parse_zone():
    assert routing.parse_zone("[zone:auth] check tokens") == ("auth", "check tokens")
    assert routing.parse_zone("no marker here") == (None, "no marker here")
    assert routing.parse_zone("[zone:] empty") == (None, "empty")


def test_parse_delegation_entries_current_and_legacy():
    entries = routing.parse_delegation_entries(
        [
            "T0\tsess-1\tk-explorer\tsmall\tauth\tcheck tokens",
            "T1\tk-explorer\tsmall\tlegacy line",  # legacy 4-col: no session/zone
            "too\tshort",  # skipped
            "",  # skipped
        ]
    )
    assert len(entries) == 2
    assert entries[0] == routing.DelegationEntry("T0", "sess-1", "k-explorer", "small", "auth", "check tokens")
    assert entries[1] == routing.DelegationEntry("T1", None, "k-explorer", "small", None, "legacy line")


def test_delegation_log_ignores_other_tools():
    assert routing.delegation_log_line("Bash", {"command": "ls"}, "T0") is None


# --------------------------------------------------------------------------------------
# Bound-model derivation (console line / record name the agent's pinned model)
# --------------------------------------------------------------------------------------

_BINDING_CONFIG = {
    "binding": {"worker": "haiku", "mid": "sonnet", "reasoner": "opus", "auditor": "fable"},
    "available": ["haiku", "sonnet", "opus", "fable"],
}


def test_bound_model_for_derives_from_binding_by_tier():
    assert routing.bound_model_for(_BINDING_CONFIG, "k-explorer") == "haiku"  # worker
    assert routing.bound_model_for(_BINDING_CONFIG, "k-implementer") == "sonnet"  # mid
    assert routing.bound_model_for(_BINDING_CONFIG, "k-reasoner") == "opus"  # reasoner
    assert routing.bound_model_for(_BINDING_CONFIG, "k-auditor") == "fable"  # auditor
    assert routing.bound_model_for(_BINDING_CONFIG, "general-purpose") is None  # host built-in
    assert routing.bound_model_for({}, "k-explorer") is None  # no binding


def test_bound_model_for_skips_semantic_fallback_token():
    # A tier value that is not a real alias (semantic-fallback) -> None, mirroring _agent_model.
    config = {"binding": {"worker": "worker"}, "available": ["haiku", "sonnet"]}
    assert routing.bound_model_for(config, "k-explorer") is None


def test_delegation_log_line_uses_bound_model_and_call_override():
    line = routing.delegation_log_line(
        "Agent", {"subagent_type": "k-explorer", "description": "d"}, "T0", "s", "haiku"
    )
    assert line == "T0\ts\tk-explorer\thaiku\t-\td"
    # An explicit model on the call overrides the bound one.
    override = routing.delegation_log_line(
        "Agent", {"subagent_type": "k-explorer", "model": "opus", "description": "d"}, "T0", "s", "haiku"
    )
    assert override == "T0\ts\tk-explorer\topus\t-\td"


# --------------------------------------------------------------------------------------
# C20 — role → task-kind advisory
# --------------------------------------------------------------------------------------


def test_subagent_kinds():
    assert routing.subagent_kinds("k-explorer") == ("explore-search", "summarize")
    assert routing.subagent_kinds("general-purpose") == ()


def test_role_matrix_warning_against_the_real_registry():
    registry = routing.load_registry(_KEYSTONE)
    # Edit agents under the analysis-only review role -> warn (no kind intersects).
    assert routing.role_matrix_warning(registry, "k-mechanic", "review") is not None
    assert routing.role_matrix_warning(registry, "k-implementer", "review") is not None
    # k-reasoner shares debug-deep/plan-draft with review -> no warn.
    assert routing.role_matrix_warning(registry, "k-reasoner", "review") is None
    # engineer may route implementation.
    assert routing.role_matrix_warning(registry, "k-implementer", "engineer") is None
    # Cross-cutting verification (A7 (b)): k-auditor's only kind is audit, a
    # cross_cutting_kind -> routable from ANY role, never warns (incl. roles whose row omits it).
    for role in ("review", "architect", "engineer", "learn", "release"):
        assert routing.role_matrix_warning(registry, "k-auditor", role) is None
    # The exemption is driven by cross_cutting_kinds, not the per-role rows: drop it and the
    # same routing warns again (guards against the kind silently re-entering a row instead).
    gated = {**registry, "cross_cutting_kinds": []}
    assert routing.role_matrix_warning(gated, "k-auditor", "engineer") is not None
    # No/unknown role, or a host built-in with no kinds -> no check.
    assert routing.role_matrix_warning(registry, "k-mechanic", None) is None
    assert routing.role_matrix_warning(registry, "k-mechanic", "no-such-role") is None
    assert routing.role_matrix_warning(registry, "general-purpose", "review") is None


def _assistant_turn(text, sidechain=False):
    entry = {"type": "assistant", "message": {"content": text}}
    if sidechain:
        entry["isSidechain"] = True
    return json.dumps(entry)  # default ensure_ascii=True -> emoji is \u-escaped, as a real transcript may be


def test_active_role_reads_last_main_chain_declaration(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        _assistant_turn([{"type": "text", "text": "🧭 agent: review — analysis"}])
        + "\n"
        + _assistant_turn("🧭 agent: engineer — build it")
        + "\n",
        encoding="utf-8",
    )
    assert routing.active_role(transcript) == "engineer"  # last declaration wins
    assert routing.active_role(tmp_path / "missing.jsonl") is None
    assert routing.active_role(None) is None


def test_active_role_ignores_sidechain_turns(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(_assistant_turn("🧭 agent: review", sidechain=True) + "\n", encoding="utf-8")
    assert routing.active_role(transcript) is None


# --------------------------------------------------------------------------------------
# init tool (end to end on a throwaway tree)
# --------------------------------------------------------------------------------------


def test_init_writes_agents_and_config_and_is_idempotent(tmp_path, capsys):
    root = _make_project(tmp_path)
    init = _load_init()

    assert init.main(
        [
            "--project-root",
            str(root),
            "--orchestrator",
            "large",
            "--available",
            "small,medium,large",
            "--second-opinion",
            "on",
        ]
    ) == 0
    config = json.loads((root / ".claude" / "model-routing.local.json").read_text(encoding="utf-8"))
    assert config["orchestrator"] == "large"
    assert config["binding"]["worker"] == "small"
    assert config["second_opinion"] is True
    assert config["registry_hash"] == routing.registry_hash(routing.load_registry(root / "_aitna" / "akmon", root))
    assert (root / ".claude" / "agents" / "k-reasoner.md").is_file()
    auditor_file = root / ".claude" / "agents" / "k-auditor.md"
    assert auditor_file.is_file()
    auditor_content = auditor_file.read_text(encoding="utf-8")
    assert "model: large" in auditor_content
    assert "tools: Read, Grep, Glob, Bash" in auditor_content

    capsys.readouterr()
    # Second run: everything already matches; --check agrees.
    assert init.main(
        [
            "--project-root",
            str(root),
            "--orchestrator",
            "large",
            "--available",
            "small,medium,large",
            "--second-opinion",
            "on",
        ]
    ) == 0
    assert "updated:" not in capsys.readouterr().out
    assert init.main(
        [
            "--project-root",
            str(root),
            "--orchestrator",
            "large",
            "--available",
            "small,medium,large",
            "--second-opinion",
            "on",
            "--check",
        ]
    ) == 0


def test_init_check_flags_stale_agents(tmp_path, capsys):
    root = _make_project(tmp_path)
    init = _load_init()
    assert init.main(["--project-root", str(root), "--orchestrator", "large", "--available", "small,medium,large"]) == 0
    (root / ".claude" / "agents" / "k-explorer.md").write_text("hand-edited\n", encoding="utf-8")
    assert init.main(
        ["--project-root", str(root), "--orchestrator", "large", "--available", "small,medium,large", "--check"]
    ) == 1


def test_init_preserves_second_opinion_when_flag_omitted(tmp_path):
    root = _make_project(tmp_path)
    init = _load_init()
    assert init.main(
        [
            "--project-root",
            str(root),
            "--orchestrator",
            "large",
            "--available",
            "small,medium,large",
            "--second-opinion",
            "on",
        ]
    ) == 0
    assert init.main(["--project-root", str(root), "--orchestrator", "large", "--available", "small,medium,large"]) == 0
    config = json.loads((root / ".claude" / "model-routing.local.json").read_text(encoding="utf-8"))
    assert config["second_opinion"] is True


# --------------------------------------------------------------------------------------
# orchestrator detection from the transcript + rebind
# --------------------------------------------------------------------------------------

AVAILABLE = ["haiku", "sonnet", "opus", "fable"]


def test_resolve_alias_matches_substring_and_prefers_longest():
    assert routing.resolve_alias("claude-opus-4-8", AVAILABLE) == "opus"
    assert routing.resolve_alias("claude-fable-5", AVAILABLE) == "fable"
    assert routing.resolve_alias("claude-haiku-4-5-20251001", AVAILABLE) == "haiku"


def test_resolve_alias_none_for_unknown_or_missing():
    assert routing.resolve_alias("gpt-5", AVAILABLE) is None
    assert routing.resolve_alias("claude-opus-4-8", None) is None
    assert routing.resolve_alias(None, AVAILABLE) is None


def _write_transcript(path: Path, entries: list[dict]) -> None:
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")


def _assistant(model: str, *, sidechain: bool = False, usage: dict | None = None) -> dict:
    message: dict = {"model": model}
    if usage is not None:
        message["usage"] = usage
    return {"type": "assistant", "isSidechain": sidechain, "message": message}


def test_detect_orchestrator_returns_last_main_chain_model(tmp_path):
    transcript = tmp_path / "t.jsonl"
    _write_transcript(
        transcript,
        [
            {"type": "user", "message": {"role": "user"}},
            _assistant("claude-fable-5"),
            _assistant("claude-haiku-4-5", sidechain=True),  # a delegate — must be skipped
            _assistant("claude-opus-4-8"),
        ],
    )
    assert routing.detect_orchestrator(transcript, AVAILABLE) == "opus"


def test_detect_orchestrator_skips_sidechain_only_and_synthetic(tmp_path):
    transcript = tmp_path / "t.jsonl"
    _write_transcript(
        transcript,
        [
            _assistant("claude-fable-5"),
            _assistant("claude-haiku-4-5", sidechain=True),
            {"type": "assistant", "isSidechain": False, "message": {"model": "<synthetic>"}},
        ],
    )
    assert routing.detect_orchestrator(transcript, AVAILABLE) == "fable"


def test_detect_orchestrator_none_when_missing_empty_or_malformed(tmp_path):
    assert routing.detect_orchestrator(None, AVAILABLE) is None
    assert routing.detect_orchestrator(tmp_path / "nope.jsonl", AVAILABLE) is None
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    assert routing.detect_orchestrator(empty, AVAILABLE) is None
    junk = tmp_path / "junk.jsonl"
    junk.write_text('not json but has "model" text\n', encoding="utf-8")
    assert routing.detect_orchestrator(junk, AVAILABLE) is None


def test_rebind_to_recomputes_binding_and_regenerates_artifacts(tmp_path):
    root = _make_project(tmp_path)
    init = _load_init()
    assert init.main(["--project-root", str(root), "--orchestrator", "fable", "--available", ",".join(AVAILABLE)]) == 0
    registry = routing.load_registry(root / "_aitna" / "akmon", root)
    config = json.loads((root / routing.LOCAL_CONFIG_REL).read_text(encoding="utf-8"))
    assert config["binding"]["reasoner"] == "fable"

    binding, changed = routing.rebind_to(root, registry, config, "opus")
    assert binding.reasoner == "opus"  # dynamic reasoner follows the new orchestrator
    assert binding.auditor == "fable"  # pinned max, unchanged
    assert changed  # files were rewritten
    new_config = json.loads((root / routing.LOCAL_CONFIG_REL).read_text(encoding="utf-8"))
    assert new_config["orchestrator"] == "opus"
    assert "model: opus" in (root / ".claude" / "agents" / "k-reasoner.md").read_text(encoding="utf-8")

    # Idempotent: rebinding to the same orchestrator rewrites nothing.
    _, changed_again = routing.rebind_to(root, registry, new_config, "opus")
    assert changed_again == []


def test_rebind_notice_names_binding_and_warns_when_weak():
    config = {
        "orchestrator": "haiku",
        "vendor": "anthropic",
        "available": AVAILABLE,
        "binding": {"reasoner": "haiku", "auditor": "fable", "worker": "haiku", "mid": "sonnet"},
    }
    lines = routing.rebind_notice(config, REGISTRY)
    assert "orchestrator model changed → haiku" in lines[0]
    assert "auditor=fable" in lines[0]
    assert any("⚠" in line for line in lines)  # haiku is below the orchestration floor → corridor warning


# --------------------------------------------------------------------------------------
# hook entry — event branching (SessionStart vs UserPromptSubmit) + rebind
# --------------------------------------------------------------------------------------


def _load_hook():
    spec = importlib.util.spec_from_file_location("model_routing_hook", _KEYSTONE / "hooks" / "model-routing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _init_project(tmp_path: Path, orchestrator: str = "fable") -> Path:
    root = _make_project(tmp_path)
    assert _load_init().main(
        ["--project-root", str(root), "--orchestrator", orchestrator, "--available", ",".join(AVAILABLE)]
    ) == 0
    return root


def test_hook_session_start_status_line_without_transcript(tmp_path):
    root = _init_project(tmp_path)
    result = _load_hook().model_routing_result(root, {"hook_event_name": "SessionStart"})
    assert result.event_name == "SessionStart"
    assert "orchestrator=fable" in result.additional_context


def test_hook_session_start_rebinds_to_detected_model(tmp_path):
    root = _init_project(tmp_path, "fable")
    transcript = tmp_path / "t.jsonl"
    _write_transcript(transcript, [_assistant("claude-opus-4-8")])
    result = _load_hook().model_routing_result(
        root, {"hook_event_name": "SessionStart", "transcript_path": str(transcript)}
    )
    assert "orchestrator=opus" in result.additional_context  # detected + rebound
    config = json.loads((root / routing.LOCAL_CONFIG_REL).read_text(encoding="utf-8"))
    assert config["orchestrator"] == "opus"
    assert "model: opus" in (root / ".claude" / "agents" / "k-reasoner.md").read_text(encoding="utf-8")


def test_hook_user_prompt_submit_silent_without_change(tmp_path):
    root = _init_project(tmp_path, "fable")
    transcript = tmp_path / "t.jsonl"
    _write_transcript(transcript, [_assistant("claude-fable-5")])  # same as configured
    result = _load_hook().model_routing_result(
        root, {"hook_event_name": "UserPromptSubmit", "transcript_path": str(transcript)}
    )
    assert result is None  # no change → zero token cost


def test_hook_user_prompt_submit_notice_on_switch(tmp_path):
    root = _init_project(tmp_path, "fable")
    transcript = tmp_path / "t.jsonl"
    _write_transcript(transcript, [_assistant("claude-opus-4-8")])
    result = _load_hook().model_routing_result(
        root, {"hook_event_name": "UserPromptSubmit", "transcript_path": str(transcript)}
    )
    assert result.event_name == "UserPromptSubmit"
    assert "orchestrator model changed → opus" in result.additional_context
    assert "model: opus" in (root / ".claude" / "agents" / "k-reasoner.md").read_text(encoding="utf-8")
    # Owner-addressed → dual-channel (requirement 11): the notice also reaches the UI.
    assert "orchestrator model changed → opus" in result.system_message


def test_hook_session_start_owner_sees_corridor_warning(tmp_path):
    # fable orchestrator on a ladder whose floor (opus) sits lower → the wasteful arm,
    # surfaced to the owner as systemMessage while the status line stays in context.
    root = _init_project(tmp_path, "fable")
    result = _load_hook().model_routing_result(root, {"hook_event_name": "SessionStart"})
    assert "reserved top rung" in result.additional_context
    assert "reserved top rung" in result.system_message
    assert "model routing:" not in (result.system_message or "")  # status line is context-only


def test_hook_session_start_owner_sees_init_instruction(tmp_path):
    root = _make_project(tmp_path)  # no init → stale
    result = _load_hook().model_routing_result(root, {"hook_event_name": "SessionStart"})
    assert "needs initialization" in result.additional_context
    assert "needs initialization" in result.system_message


# --------------------------------------------------------------------------------------
# context pressure (design §12) — fill, window, banded throttled notice
# --------------------------------------------------------------------------------------


def _usage(fill: int) -> dict:
    # Split the fill across the three input components like a real cached turn.
    return {
        "input_tokens": 4,
        "cache_read_input_tokens": fill - 1004,
        "cache_creation_input_tokens": 1000,
        "output_tokens": 500,
    }


def test_context_fill_sums_input_components_and_ignores_output():
    assert routing.context_fill(_usage(170000)) == 170000
    assert routing.context_fill({"output_tokens": 500}) is None
    assert routing.context_fill(None) is None


def test_context_window_default_and_alias_exception():
    assert routing.context_window(REGISTRY, "claude-opus-4-8") == 200000
    registry = dict(REGISTRY, context_pressure={"window_default": 200000, "windows": {"sonnet": 1000000}})
    assert routing.context_window(registry, "claude-sonnet-5") == 1000000
    assert routing.context_window(registry, "claude-opus-4-8") == 200000


def test_context_pressure_notice_bands_throttle_and_reset(tmp_path):
    transcript = tmp_path / "t.jsonl"

    def notice(fill: int) -> list[str]:
        _write_transcript(transcript, [_assistant("claude-fable-5", usage=_usage(fill))])
        return routing.context_pressure_notice(REGISTRY, transcript, "s1", marker_dir=tmp_path)

    assert notice(100000) == []  # 50% — below every band
    high = notice(172000)  # 86% — crosses the plan band
    assert len(high) == 1 and "context pressure: ~86% of 200k" in high[0] and "plan compaction" in high[0]
    assert notice(174000) == []  # still the same band — throttled
    critical = notice(191000)  # 95.5% — band rises to critical
    assert len(critical) == 1 and "critical" in critical[0] and "/compact" in critical[0]
    assert notice(192000) == []  # steady critical — throttled
    assert notice(40000) == []  # compaction landed — resets the throttle silently
    assert len(notice(172000)) == 1  # the next cycle warns again


def test_context_pressure_notice_silent_without_usage_or_ratios(tmp_path):
    transcript = tmp_path / "t.jsonl"
    _write_transcript(transcript, [_assistant("claude-fable-5")])  # no usage recorded
    assert routing.context_pressure_notice(REGISTRY, transcript, "s2", marker_dir=tmp_path) == []
    no_ratios = dict(REGISTRY, context_pressure={"window_default": 200000, "warn_ratios": []})
    _write_transcript(transcript, [_assistant("claude-fable-5", usage=_usage(199000))])
    assert routing.context_pressure_notice(no_ratios, transcript, "s2", marker_dir=tmp_path) == []


def test_hook_user_prompt_submit_pressure_notice_dual_channel(tmp_path):
    root = _init_project(tmp_path, "fable")
    transcript = tmp_path / "t.jsonl"
    _write_transcript(transcript, [_assistant("claude-fable-5", usage=_usage(172000))])  # no switch, 86%
    result = _load_hook().model_routing_result(
        root,
        {
            "hook_event_name": "UserPromptSubmit",
            "transcript_path": str(transcript),
            # The hook uses the real temp dir for its marker — a uuid keeps runs isolated.
            "session_id": f"cp-{uuid.uuid4()}",
        },
    )
    assert "context pressure" in result.additional_context
    assert "context pressure" in result.system_message
