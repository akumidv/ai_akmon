"""Unit tests for the model-routing core (``tools/model_routing/routing.py``) and init tool.

These build throwaway project trees under ``tmp_path``; nothing touches the real repo.
"""

from __future__ import annotations

import importlib.util
import json
import sys
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
    assert binding.synthesizer == "large"
    assert binding.worker == "small"
    assert binding.mid == "medium"
    assert binding.escalation == ("medium",)
    assert binding.warning is None


def test_binding_reasoner_follows_orchestrator_rung():
    """Dynamic reasoner: defaults to the orchestrator's own rung, not the top rung."""
    binding = routing.compute_binding(REGISTRY, "medium", available=["small", "medium", "large"])
    assert binding.reasoner == "medium"
    assert binding.synthesizer == "large"  # synthesizer stays pinned to the top rung


def test_binding_synthesizer_pinned_to_top_regardless_of_orchestrator():
    for orchestrator in ("small", "medium", "large"):
        binding = routing.compute_binding(REGISTRY, orchestrator, available=["small", "medium", "large"])
        assert binding.synthesizer == "large"


def test_binding_orchestrator_below_floor_warns_as_weak_prior():
    binding = routing.compute_binding(REGISTRY, "medium", available=["small", "medium", "large"])
    assert binding.warning is not None
    assert "weak prior" in binding.warning
    # The binding itself is unchanged — the warning is advisory only.
    assert binding.synthesizer == "large"


def test_binding_unknown_orchestrator_warns_without_ranking():
    binding = routing.compute_binding(REGISTRY, "mystery-model", available=["small", "medium", "large"])
    assert binding.warning is not None
    assert "not in the discovered model list" in binding.warning


def test_binding_reasoner_falls_back_to_top_for_unknown_orchestrator():
    binding = routing.compute_binding(REGISTRY, "mystery-model", available=["small", "medium", "large"])
    assert binding.reasoner == "large"


def test_binding_available_filter_caps_reasoner_and_synthesizer():
    binding = routing.compute_binding(REGISTRY, "medium", available=["small", "medium"])
    assert binding.reasoner == "medium"
    assert binding.synthesizer == "medium"
    assert binding.worker == "small"
    assert binding.mid == "medium"
    assert binding.escalation == ()


def test_binding_single_rung_collapses_all_tiers():
    binding = routing.compute_binding(REGISTRY, "only", available=["only"])
    assert (binding.reasoner, binding.worker, binding.mid, binding.synthesizer) == ("only", "only", "only", "only")


def test_binding_openai_policy_for_codex_models():
    binding = routing.compute_binding(REGISTRY, "large", available=["small", "medium", "large"], vendor="openai")
    assert binding.vendor == "openai"
    assert binding.reasoner == "large"
    assert binding.synthesizer == "large"
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
    assert binding.synthesizer == "strongest"
    assert binding.warning is not None
    assert "model:" not in files[".claude/agents/k-explorer.md"]


def test_task_kind_floors_resolves_highest():
    floors = routing.task_kind_floors(REGISTRY, ["small", "medium", "large"])
    assert floors == {"quant-derivation": "large"}


def test_task_kind_floors_empty_without_rungs():
    assert routing.task_kind_floors(REGISTRY, []) == {}


def test_second_opinion_fallback_model_top_orchestrator_returns_rung_below_top():
    # orchestrator == synthesizer == top rung → the answer is the rung below the top.
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
    keystone = tmp_path / "_forge" / "keystone" / "tools" / "model_routing"
    keystone.mkdir(parents=True)
    (keystone / "registry.json").write_text(json.dumps(REGISTRY), encoding="utf-8")
    return tmp_path


def test_overlay_deep_merges_and_changes_hash(tmp_path):
    root = _make_project(tmp_path)
    keystone_dir = root / "_forge" / "keystone"
    base = routing.load_registry(keystone_dir, root)
    base_hash = routing.registry_hash(base)

    overlay = {
        "anthropic": {"semantic_fallback": {"worker": "local-worker"}},
        "briefs": {"k-explorer": "Project note."},
    }
    routing.overlay_path(root).write_text(json.dumps(overlay), encoding="utf-8")
    merged = routing.load_registry(keystone_dir, root)

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
        ".claude/agents/k-synthesizer.md",
    }
    assert "model: small" in files[".claude/agents/k-explorer.md"]
    assert "model: medium" in files[".claude/agents/k-implementer.md"]
    assert "model: large" in files[".claude/agents/k-reasoner.md"]
    assert "model: large" in files[".claude/agents/k-synthesizer.md"]
    for content in files.values():
        assert content.startswith("---\n")
        assert routing.GENERATED_BANNER in content


def test_generated_k_synthesizer_is_read_only():
    binding = routing.compute_binding(REGISTRY, "large", available=["small", "medium", "large"])
    files = routing.generated_agent_files(REGISTRY, binding)
    content = files[".claude/agents/k-synthesizer.md"]
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
        if spec["tier"] in ("worker", "reasoner", "synthesizer")
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
    lines = routing.status_lines(_fresh_config(), REGISTRY, "_forge")
    joined = "\n".join(lines)
    assert "orchestrator=large" in joined
    assert "synthesizer=large" in joined
    assert "worker=small" in joined
    assert "second-opinion=codex(on)" in joined
    assert "Self-check" in joined
    assert "⚠" not in joined


def test_status_lines_warn_below_floor_as_weak_prior():
    binding = routing.compute_binding(REGISTRY, "small", available=["small", "medium", "large"])
    config = routing.local_config(binding, REGISTRY, second_opinion=False, available=["small", "medium", "large"])
    joined = "\n".join(routing.status_lines(config, REGISTRY, "_forge"))
    assert "⚠" in joined and "weak prior" in joined


# --------------------------------------------------------------------------------------
# local_config: synthesizer, task_kind_floors, second-opinion fallback model
# --------------------------------------------------------------------------------------


def test_local_config_carries_synthesizer_and_task_kind_floors():
    config = _fresh_config()
    assert config["binding"]["synthesizer"] == "large"
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
        "Agent", {"subagent_type": "k-explorer", "model": "small", "description": "find  X"}, "T0"
    )
    assert line == "T0\tk-explorer\tsmall\tfind X"
    assert routing.delegation_log_line("Task", {}, "T0") == "T0\t-\t-\t"


def test_delegation_log_ignores_other_tools():
    assert routing.delegation_log_line("Bash", {"command": "ls"}, "T0") is None


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
    assert config["registry_hash"] == routing.registry_hash(routing.load_registry(root / "_forge" / "keystone", root))
    assert (root / ".claude" / "agents" / "k-reasoner.md").is_file()
    synthesizer_file = root / ".claude" / "agents" / "k-synthesizer.md"
    assert synthesizer_file.is_file()
    synthesizer_content = synthesizer_file.read_text(encoding="utf-8")
    assert "model: large" in synthesizer_content
    assert "tools: Read, Grep, Glob, Bash" in synthesizer_content

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
