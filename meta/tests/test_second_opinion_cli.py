"""Unit tests for the second-opinion CLI (``tools/model_routing/second_opinion.py``).

Covers the ladder wiring added in C16 step 4: ``--gate-pack`` replacing ``--prompt-file``,
provider+model selection via ``routing.resolve_second_opinion`` (design §4.6, §9.3/§9.4),
the explicit ``--provider`` override, and the skip branch when the ladder is exhausted
(§9.7 #2 — weaker diversity beats none, but no diversity means skip, never same-model).
Only ``--dry-run`` and the skip branch are exercised through ``main`` so no test ever
spawns the real ``claude``/``codex`` CLI.
"""

from __future__ import annotations

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
import second_opinion  # noqa: E402

_TWO_VENDOR_REGISTRY = {
    "anthropic": {
        "selection_policy": {},
        "second_opinion": {
            "cli": "codex",
            "invoke": "codex exec",
            "report_dir": ".claude/second-opinion",
        },
    },
    "openai": {
        "selection_policy": {},
        "second_opinion": {
            "cli": "claude",
            "invoke": "claude -p --output-format text",
            "model_flag": "--model {model}",
            "report_dir": ".claude/second-opinion",
        },
    },
    "second_opinion_policy": {"diversity_ladder": ["other-vendor", "same-vendor-other-model"]},
}

_ONE_VENDOR_REGISTRY = {
    "anthropic": {
        "selection_policy": {},
        "second_opinion": {
            "cli": "codex",
            "invoke": "codex exec",
            "report_dir": ".claude/second-opinion",
        },
    },
    "second_opinion_policy": {"diversity_ladder": ["other-vendor", "same-vendor-other-model"]},
}


def _write_project(tmp_path: Path, registry: dict, config: dict) -> Path:
    """A minimal project root: AGENTS.md + <aitna>/akmon marker + registry + local config."""
    (tmp_path / "AGENTS.md").write_text("# project\n", encoding="utf-8")
    registry_path = tmp_path / "_aitna" / "akmon" / "tools" / "model_routing" / "registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    local_config_path = tmp_path / routing.LOCAL_CONFIG_REL
    local_config_path.parent.mkdir(parents=True, exist_ok=True)
    local_config_path.write_text(json.dumps(config), encoding="utf-8")
    return tmp_path


def _gate_pack(tmp_path: Path, text: str = "Review this change.") -> Path:
    pack = tmp_path / "pack.md"
    pack.write_text(text, encoding="utf-8")
    return pack


# --------------------------------------------------------------------------------------
# --dry-run through the ladder: two vendors -> other-vendor step, model=(default)
# --------------------------------------------------------------------------------------


def test_dry_run_two_vendors_picks_other_vendor_with_default_model(tmp_path, capsys):
    config = {"orchestrator": "large", "binding": {"auditor": "large"}}
    root = _write_project(tmp_path, _TWO_VENDOR_REGISTRY, config)
    pack = _gate_pack(root)

    exit_code = second_opinion.main(
        [
            "--project-root",
            str(root),
            "--orchestrator-vendor",
            "anthropic",
            "--gate",
            "code-verify",
            "--gate-pack",
            str(pack),
            "--dry-run",
        ]
    )

    out = capsys.readouterr().out
    command_line = out.splitlines()[0]
    assert exit_code == 0
    assert command_line.startswith("claude -p --output-format text ")
    assert "--model" not in command_line  # other-vendor step: no model pin
    assert "provider=openai model=(default)" in out
    assert "report:" in out


# --------------------------------------------------------------------------------------
# skip branch: single vendor, no distinct fallback rung -> ladder exhausted
# --------------------------------------------------------------------------------------


def test_skip_branch_when_ladder_exhausted_runs_no_subprocess(tmp_path, capsys, monkeypatch):
    config = {
        "orchestrator": "only",
        "binding": {"auditor": "only"},
        "available": ["only"],
    }
    root = _write_project(tmp_path, _ONE_VENDOR_REGISTRY, config)
    pack = _gate_pack(root)

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("subprocess.run must not be called on the skip branch")

    monkeypatch.setattr(second_opinion.subprocess, "run", _fail_if_called)

    exit_code = second_opinion.main(
        [
            "--project-root",
            str(root),
            "--orchestrator-vendor",
            "anthropic",
            "--gate",
            "code-verify",
            "--gate-pack",
            str(pack),
        ]
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "second-opinion: skipped" in out
    assert "ladder exhausted" in out


# --------------------------------------------------------------------------------------
# explicit --provider override bypasses the ladder
# --------------------------------------------------------------------------------------


def test_explicit_provider_override_bypasses_ladder(tmp_path, capsys):
    # Config that would otherwise route through the ladder to "openai"; the explicit
    # --provider anthropic must win and carry no ladder-pinned model.
    config = {"orchestrator": "large", "binding": {"auditor": "large"}}
    root = _write_project(tmp_path, _TWO_VENDOR_REGISTRY, config)
    pack = _gate_pack(root)

    exit_code = second_opinion.main(
        [
            "--project-root",
            str(root),
            "--provider",
            "anthropic",
            "--orchestrator-vendor",
            "anthropic",
            "--gate",
            "code-verify",
            "--gate-pack",
            str(pack),
            "--dry-run",
        ]
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert out.splitlines()[0].startswith("codex exec ")
    assert "provider=anthropic model=(default)" in out
