"""Offline regression for the pinned-CLI successor after a zero-call startup stop."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("v3_controls_successor_test", ROOT / "v3_controls_successor.py")
assert SPEC is not None and SPEC.loader is not None
controls = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(controls)


def test_successor_binds_zero_call_predecessor_and_pinned_binary() -> None:
    assert controls.verify_seal()["pinned_executable_sha256"] == controls.sha(controls.EXECUTABLE)
    rows = [
        json.loads(line) for line in (controls.PREDECESSOR_RUNTIME / "control-events.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 1
    assert not list((controls.PREDECESSOR_RUNTIME / "control-0" / "output").iterdir())
    assert controls.EXECUTABLE.is_file()


def test_current_cli_banner_in_isolated_home(tmp_path: Path) -> None:
    home, tmp = tmp_path / "home", tmp_path / "tmp"
    home.mkdir()
    tmp.mkdir()
    env = controls.source._codex_child_environment(home, tmp)
    version = subprocess.run([controls.EXECUTABLE, "--version"], env=env, capture_output=True, text=True, check=False)
    assert (version.returncode, version.stdout.strip(), version.stderr.strip()) == (0, controls.CLI_VERSION, "")


def test_successor_starts_no_process_without_exact_new_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("process started before successor approval")

    monkeypatch.setattr(controls.subprocess, "Popen", forbidden)
    with pytest.raises(controls.ControlError, match="acceptance"):
        controls.run()
    assert not controls.RUNTIME.exists()
