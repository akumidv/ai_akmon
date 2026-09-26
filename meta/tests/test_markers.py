"""C36 — one owner for the tempdir diagnostic markers, their lifecycle, and the hook paths it guards."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import time
from pathlib import Path

import hook_core
import pytest
import routing

from common import markers

_KEYSTONE = Path(__file__).resolve().parents[2]


@pytest.fixture
def tempdir(tmp_path, monkeypatch):
    monkeypatch.setattr(markers.tempfile, "gettempdir", lambda: str(tmp_path))
    return tmp_path


def _age(path: Path, seconds: float) -> None:
    past = time.time() - seconds
    os.utime(path, (past, past))


def test_claim_is_once_per_identity_with_a_hashed_private_file(tempdir):
    assert markers.claim_diagnostic_marker("probe", "sess/../escape")
    assert not markers.claim_diagnostic_marker("probe", "sess/../escape")
    [marker] = list(tempdir.glob("akmon-probe-*"))
    assert "/" not in marker.name.removeprefix("akmon-probe-")
    assert stat.S_IMODE(marker.stat().st_mode) == 0o600


@pytest.mark.parametrize("identity", [None, "", "nosession"])
def test_an_unidentified_claim_repeats_and_leaves_no_marker(tempdir, identity):
    assert markers.claim_diagnostic_marker("probe", identity)
    assert markers.claim_diagnostic_marker("probe", identity)
    assert list(tempdir.iterdir()) == []


def test_a_stale_marker_ages_out_and_speaks_again(tempdir):
    assert markers.claim_diagnostic_marker("probe", "s1")
    [marker] = list(tempdir.glob("akmon-probe-*"))
    _age(marker, markers.MARKER_MAX_AGE_SECONDS - 60)
    assert not markers.claim_diagnostic_marker("probe", "s1")
    _age(marker, markers.MARKER_MAX_AGE_SECONDS + 60)
    assert markers.claim_diagnostic_marker("probe", "s1")
    assert not markers.claim_diagnostic_marker("probe", "s1")


def test_release_removes_one_identitys_markers_and_spares_the_kept_one(tempdir):
    for kind in ("cond-a", "cond-b"):
        assert markers.claim_diagnostic_marker(kind, "s1")
    assert markers.claim_diagnostic_marker("cond-a", "s2")
    markers.release_diagnostic_markers("cond", "s1", keep_kind="cond-b")
    assert markers.claim_diagnostic_marker("cond-a", "s1")  # released
    assert not markers.claim_diagnostic_marker("cond-b", "s1")  # kept
    assert not markers.claim_diagnostic_marker("cond-a", "s2")  # another session untouched


@pytest.mark.parametrize(
    ("result", "path"),
    [(hook_core.role_on_code_result, "src/x.py"), (hook_core.analysis_write_result, "_aitna/design/probe.md")],
)
def test_the_advisories_remind_once_per_session_and_repeat_without_one(tempdir, result, path):
    target = str(tempdir / path)
    assert result(hook_core.EDIT_TOOL, target, "sess-1", tempdir) is not None
    assert result(hook_core.EDIT_TOOL, target, "sess-1", tempdir) is None
    assert result(hook_core.EDIT_TOOL, target, "sess-2", tempdir) is not None
    # The literal "nosession" used to share one marker across every id-less session.
    assert result(hook_core.EDIT_TOOL, target, "nosession", tempdir) is not None
    assert result(hook_core.EDIT_TOOL, target, "nosession", tempdir) is not None
    assert all(".marker" not in p.name for p in tempdir.iterdir())


def test_suppressed_rebind_speaks_again_when_an_earlier_condition_returns(tmp_path):
    warn_a, warn_b = "refused: a", "refused: b"
    assert routing.suppressed_rebind_warning(warn_a, "opus", "s1", marker_dir=tmp_path) == [warn_a]
    assert routing.suppressed_rebind_warning(warn_b, "opus", "s1", marker_dir=tmp_path) == [warn_b]
    assert routing.suppressed_rebind_warning(warn_a, "opus", "s1", marker_dir=tmp_path) == [warn_a]
    assert len(list(tmp_path.glob("akmon-suppressed-rebind-*"))) == 1


def test_a_stale_suppressed_rebind_marker_no_longer_hides_the_notice(tmp_path):
    warning = "refused: a"
    assert routing.suppressed_rebind_warning(warning, "opus", "s1", marker_dir=tmp_path) == [warning]
    assert routing.suppressed_rebind_warning(warning, "opus", "s1", marker_dir=tmp_path) == []
    [marker] = list(tmp_path.glob("akmon-suppressed-rebind-*"))
    _age(marker, markers.MARKER_MAX_AGE_SECONDS + 60)
    assert routing.suppressed_rebind_warning(warning, "opus", "s1", marker_dir=tmp_path) == [warning]


# --------------------------------------------------------------------------------------
# C36(b) — the model-routing entry point's failure paths
# --------------------------------------------------------------------------------------


def _model_routing_hook():
    spec = importlib.util.spec_from_file_location("model_routing_hook_c36", _KEYSTONE / "hooks" / "model-routing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_model_routing_main_reports_a_crash_and_never_blocks(monkeypatch, capsys):
    hook = _model_routing_hook()

    def boom():
        raise RuntimeError("secret path /home/someone")

    monkeypatch.setattr(hook, "load_payload", boom)
    assert hook.main() == 0
    captured = capsys.readouterr()
    assert "model-routing" in json.loads(captured.out)["systemMessage"]
    assert "RuntimeError" in captured.err
    assert "secret path" not in captured.err + captured.out  # the class is named, never the message


def test_model_routing_survives_a_transcript_with_malformed_lines(tmp_path):
    hook = _model_routing_hook()
    init_spec = importlib.util.spec_from_file_location("init_c36", _KEYSTONE / "tools" / "model_routing" / "init.py")
    init = importlib.util.module_from_spec(init_spec)
    init_spec.loader.exec_module(init)
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    ladder = "claude-haiku-4-5,claude-sonnet-5,claude-opus-5"
    assert init.main(["--project-root", str(root), "--orchestrator", "claude-opus-5", "--available", ladder]) == 0
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        "{not json\n"
        + json.dumps({"type": "assistant", "message": {"model": "claude-opus-5", "content": "ok"}})
        + "\n\x00garbage\n[]\n",
        encoding="utf-8",
    )
    result = hook.model_routing_result(root, {"hook_event_name": "SessionStart", "transcript_path": str(transcript)})
    assert result is not None and "orchestrator=claude-opus-5" in result.additional_context
