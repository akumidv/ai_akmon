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
import os
import sys
from pathlib import Path

import pytest

_AKMON = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_ROUTING_DIR = _AKMON / "tools" / "model_routing"
if str(_ROUTING_DIR) not in sys.path:
    sys.path.insert(0, str(_ROUTING_DIR))

import routing  # noqa: E402
import second_opinion  # noqa: E402

from common import jsondata  # noqa: E402

_TWO_VENDOR_REGISTRY = {
    "anthropic": {
        "selection_policy": {},
        "second_opinion": {
            "harness": "codex",
            "operation": "review",
            "report_dir": ".claude/second-opinion",
        },
    },
    "openai": {
        "selection_policy": {},
        "second_opinion": {
            "harness": "claude",
            "operation": "review",
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
            "harness": "codex",
            "operation": "review",
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
    local_config_path = tmp_path / routing.local_config_rel()
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
    assert "report: .claude/second-opinion/code-verify-1.md" in out


def test_dry_run_with_a_task_names_the_next_ordinal_and_creates_nothing(tmp_path, capsys):
    """C114: ``[<task>-]<gate>-<n>.md``, n one past the largest existing ordinal of that prefix."""
    root = _write_project(tmp_path, _TWO_VENDOR_REGISTRY, {"orchestrator": "large", "binding": {"auditor": "large"}})
    report_dir = root / ".claude" / "second-opinion"
    report_dir.mkdir(parents=True)
    (report_dir / "C7-code-verify-1.md").write_text("earlier\n", encoding="utf-8")
    (report_dir / "code-verify-4.md").write_text("no task\n", encoding="utf-8")
    argv = ["--project-root", str(root), "--orchestrator-vendor", "anthropic", "--gate", "code-verify"]
    argv += ["--gate-pack", str(_gate_pack(root)), "--task", "C7", "--dry-run"]

    assert second_opinion.main(argv) == 0
    assert "report: .claude/second-opinion/C7-code-verify-2.md" in capsys.readouterr().out
    assert sorted(p.name for p in report_dir.iterdir()) == ["C7-code-verify-1.md", "code-verify-4.md"]


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


def test_the_skip_states_its_reason_and_offers_the_weaker_check_with_its_limits(tmp_path, capsys, monkeypatch):
    """A bare "skipped" leaves the owner with no reason and no option. The gate refuses to
    downgrade itself, but the same-model self-check is still worth offering — to a person,
    with the boundary attached, so its result is never filed as a second opinion."""
    config = {
        "orchestrator": "only",
        "binding": {"auditor": "only"},
        "available": ["only"],
    }
    root = _write_project(tmp_path, _ONE_VENDOR_REGISTRY, config)
    monkeypatch.setattr(
        second_opinion.subprocess,
        "run",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no subprocess on the skip branch")),
    )

    second_opinion.main(
        [
            "--project-root",
            str(root),
            "--orchestrator-vendor",
            "anthropic",
            "--gate",
            "code-verify",
            "--gate-pack",
            str(_gate_pack(root)),
        ]
    )
    out = capsys.readouterr().out

    # The reason, derived from the ladder's own inputs rather than restated here.
    assert "no other vendor is configured" in out
    assert "'only'" in out
    # The option, and — inseparably — what it does not buy.
    assert "subagent" in out and "fresh context" in out
    assert "does not remove shared model priors" in out
    assert "must not be filed as one" in out


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


def test_a_pin_the_vendor_cannot_apply_stops_the_run_loudly(tmp_path, capsys, monkeypatch):
    """C97: the same-vendor step needs a model pin; without a model_flag it must not run unpinned."""
    config = {
        "orchestrator": "large",
        "binding": {"auditor": "large"},
        "available": ["small", "large"],
        "second_opinion_fallback_model": "small",
    }
    root = _write_project(tmp_path, _ONE_VENDOR_REGISTRY, config)
    pack = _gate_pack(root)

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("an unpinnable second opinion must not reach the harness")

    monkeypatch.setattr(second_opinion.subprocess, "run", _fail_if_called)
    argv = ["--project-root", str(root), "--orchestrator-vendor", "anthropic", "--gate", "code-verify"]
    exit_code = second_opinion.main([*argv, "--gate-pack", str(pack)])

    assert exit_code == 2
    assert "declares no model_flag" in capsys.readouterr().err


def test_package_mode_reads_the_registry_from_its_own_tree(tmp_path, capsys):
    """A package-mode project has no ``<AITNA_ROOT>/akmon`` mount: the registry comes from the tree
    the tool runs from (the conformance corpus's native attach found the mount path hardcoded)."""
    root = tmp_path / "proj"
    (root / "_aitna").mkdir(parents=True)
    (root / "_aitna" / ".akmon.toml").write_text('mount = "package"\n', encoding="utf-8")
    pack = _gate_pack(root)

    exit_code = second_opinion.main(
        [
            "--project-root",
            str(root),
            "--provider",
            "anthropic",
            "--orchestrator-vendor",
            "openai",
            "--gate",
            "code-verify",
            "--gate-pack",
            str(pack),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert "provider=anthropic" in capsys.readouterr().out


# --------------------------------------------------------------------------------------
# C102: second_opinion.json — the runner texts
# --------------------------------------------------------------------------------------


def test_second_opinion_data_pins_the_structure_and_characteristic_texts():
    data = json.loads((_ROUTING_DIR / "second_opinion.json").read_text(encoding="utf-8"))
    assert set(data) == {"prompt", "unavailable_notice", "report_dir_outside", "summary"}
    assert data["prompt"].startswith("You are an independent second-opinion reviewer for a akmon verify gate.")
    assert data["prompt"].endswith("Material to review:\n{{material}}\n")
    assert len(data["unavailable_notice"]) == 5
    assert data["unavailable_notice"][0] == (
        "second-opinion: skipped at gate '{{gate}}' — ladder exhausted, no model-diverse reviewer is reachable."
    )
    assert data["report_dir_outside"] == (
        "second-opinion: report_dir '{{report_dir}}' resolves outside the project;"
        " it must be a directory inside the project root."
    )
    assert data["summary"]["result_line"] == (
        "second-opinion provider={{provider}} model={{model}} gate={{gate}} exit={{exit}}"
    )


def test_second_opinion_loader_reads_exactly_its_two_data_files(monkeypatch):
    seen: list[Path] = []

    def spy(path: Path):
        seen.append(path)
        return json.loads(path.read_text(encoding="utf-8"))

    monkeypatch.setattr(jsondata, "read", spy)
    second_opinion._prompt("g", "m")
    assert seen == [_ROUTING_DIR / "second_opinion.json"]
    second_opinion._digest("x" * 2000)
    assert seen == [_ROUTING_DIR / "second_opinion.json", _ROUTING_DIR / "gate.json"]


def test_a_missing_second_opinion_json_raises_from_main(monkeypatch, tmp_path):
    root = _write_project(tmp_path, _TWO_VENDOR_REGISTRY, {"orchestrator": "large", "binding": {"auditor": "large"}})
    pack = _gate_pack(root)

    def broken(path: Path):
        raise jsondata.DataFileError(f"akmon data file missing: {path}")

    monkeypatch.setattr(jsondata, "read", broken)
    with pytest.raises(jsondata.DataFileError):
        second_opinion.main(
            ["--project-root", str(root), "--orchestrator-vendor", "anthropic", "--gate", "g", "--gate-pack", str(pack)]
        )


def test_the_provider_output_is_read_with_universal_newlines(tmp_path, capsys, monkeypatch):
    """``text=True`` turns a provider's CRLF and lone CR into LF in the report (the C115 reference)."""
    config = {"orchestrator": "large", "binding": {"auditor": "large"}}
    (tmp_path / "project").mkdir()
    root = _write_project(tmp_path / "project", _TWO_VENDOR_REGISTRY, config)
    pack = _gate_pack(root)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stand_in = bin_dir / "codex"
    stand_in.write_text("#!/bin/sh\nprintf 'a\\r\\nb\\rc\\r\\n'\nprintf 'w\\r\\nx\\r' >&2\n", encoding="utf-8")
    stand_in.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    exit_code = second_opinion.main(
        ["--project-root", str(root), "--provider", "anthropic", "--gate", "g", "--gate-pack", str(pack)]
    )

    capsys.readouterr()
    assert exit_code == 0
    report = root / ".claude" / "second-opinion" / "g-1.md"
    assert report.read_bytes() == b"a\nb\nc\n\n[stderr]\nw\nx\n"


def test_an_undecodable_provider_byte_is_replaced_and_the_report_is_written(tmp_path, capsys, monkeypatch):
    """A byte that is not UTF-8 reads as U+FFFD on both pipes; the run still writes its report (C120)."""
    config = {"orchestrator": "large", "binding": {"auditor": "large"}}
    (tmp_path / "project").mkdir()
    root = _write_project(tmp_path / "project", _TWO_VENDOR_REGISTRY, config)
    pack = _gate_pack(root)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stand_in = bin_dir / "codex"
    stand_in.write_text("#!/bin/sh\nprintf 'ok\\377x'\nprintf 'e\\377' >&2\n", encoding="utf-8")
    stand_in.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    exit_code = second_opinion.main(
        ["--project-root", str(root), "--provider", "anthropic", "--gate", "g", "--gate-pack", str(pack)]
    )

    assert "\ufffd" in capsys.readouterr().out
    assert exit_code == 0
    report = root / ".claude" / "second-opinion" / "g-1.md"
    assert report.read_text(encoding="utf-8") == "ok\ufffdx\n\n[stderr]\ne\ufffd\n"


# --------------------------------------------------------------------------------------
# report_dir must resolve inside the project (C9): refused before the provider or any write
# --------------------------------------------------------------------------------------


def _registry_with_report_dir(report_dir: str) -> dict:
    registry = json.loads(json.dumps(_TWO_VENDOR_REGISTRY))
    registry["openai"]["second_opinion"]["report_dir"] = report_dir
    return registry


def _outside_case(kind: str, tmp_path: Path) -> tuple[str, Path]:
    """``(configured report_dir, the outside directory it reaches)`` for one way of leaving the project."""
    outside = tmp_path / "outside"
    if kind == "absolute":
        return str(outside / "reviews"), outside
    if kind == "dotdot":
        return "../outside/reviews", outside
    outside.mkdir()
    (tmp_path / "project" / "link").symlink_to(outside, target_is_directory=True)
    return "link/reviews", outside


@pytest.mark.parametrize("dry_run", [False, True], ids=["run", "dry-run"])
@pytest.mark.parametrize("kind", ["absolute", "dotdot", "symlink"])
def test_a_report_dir_outside_the_project_is_refused_before_anything_runs(tmp_path, capsys, monkeypatch, kind, dry_run):
    (tmp_path / "project").mkdir()
    configured, outside = _outside_case(kind, tmp_path)
    config = {"orchestrator": "large", "binding": {"auditor": "large"}}
    root = _write_project(tmp_path / "project", _registry_with_report_dir(configured), config)

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("a report_dir outside the project must not reach the provider")

    monkeypatch.setattr(second_opinion.subprocess, "run", _fail_if_called)
    argv = ["--project-root", str(root), "--orchestrator-vendor", "anthropic", "--gate", "g"]
    argv += ["--gate-pack", str(_gate_pack(root))] + (["--dry-run"] if dry_run else [])

    exit_code = second_opinion.main(argv)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == (
        f"second-opinion: report_dir '{configured}' resolves outside the project;"
        " it must be a directory inside the project root.\n"
    )
    assert not (outside / "reviews").exists()


def test_a_report_dir_inside_the_project_still_writes_its_report(tmp_path, capsys, monkeypatch):
    """``..`` and a link that stay inside the project are fine; the report line names the resolved path."""
    (tmp_path / "project").mkdir()
    (tmp_path / "project" / "docs").mkdir()
    (tmp_path / "project" / "link").symlink_to(tmp_path / "project" / "docs", target_is_directory=True)
    config = {"orchestrator": "large", "binding": {"auditor": "large"}}
    root = _write_project(tmp_path / "project", _registry_with_report_dir("link/../link/reviews"), config)

    class _Completed:
        returncode = 0
        stdout = b"verdict: fine\n"
        stderr = b""

    monkeypatch.setattr(second_opinion.subprocess, "run", lambda *_a, **_k: _Completed())
    argv = ["--project-root", str(root), "--orchestrator-vendor", "anthropic", "--gate", "g"]

    assert second_opinion.main([*argv, "--gate-pack", str(_gate_pack(root))]) == 0
    assert "report: docs/reviews/g-1.md" in capsys.readouterr().out
    assert (root / "docs" / "reviews" / "g-1.md").read_text(encoding="utf-8") == "verdict: fine\n"
