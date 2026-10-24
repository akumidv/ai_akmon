"""Offline gates for the fresh header-optional A qualification package."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "experiments" / "a22-p3"
sys.path[:0] = [str(ROOT / "successors"), str(ROOT)]

import v3_qualification_header_optional as trial  # noqa: E402


def test_fresh_grid_excludes_terminal_schedules_and_v8_route() -> None:
    candidate = trial.schedule.read(trial.schedule.SCHEDULE)
    trial.schedule.verify_schedule(candidate)
    plan = trial.call_plan()
    assert len(plan) == 128
    assert len({step["call_id"] for step in plan}) == 128
    assert all(row["arm"] == "A" for row in candidate["cells"])
    assert {row["tier"] for row in candidate["cells"]} == {"mid", "strongest"}
    prior = trial.schedule.prior_ids()
    route_ids = {call["call_id"] for call in trial.route.plan()["calls"]}
    assert not ({step["call_id"] for step in plan} & (prior | route_ids))


def test_default_deny_blocks_qualification_dispatch() -> None:
    trial.verify_seal()
    trial.verify_approval(dispatch=False)
    with pytest.raises(trial.QualificationError, match="approval"):
        trial.verify_approval(dispatch=True)
    assert not trial.RUNTIME.exists()


def test_headerless_reply_preserves_rows_and_binds_packet_id() -> None:
    row = next(row for row in trial.schedule.read(trial.schedule.SCHEDULE)["cells"] if len(row["element_ids"]) == 4)
    raw = "\n".join(f"{element}\tFAIL\tReason {element}." for element in row["element_ids"])
    canonical, kind = trial.identity.canonicalize(raw, row["packet_id"], row["element_ids"])
    normalized = trial.route._normalized_from_canonical(canonical, row["packet_id"]).encode()
    assert kind == "inserted_header"
    assert trial.route._normalized_bytes_match(normalized, canonical, row["packet_id"])
    trial.scorer.validate_tsv(canonical, row["packet_id"], row["element_ids"])
    assert all(f"{element}\tFAIL\tReason {element}." in normalized.decode() for element in row["element_ids"])


def test_v8_lineage_and_codex_opening_are_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    body = trial.seal_body()
    assert body["opening_codex_tokens"] == 667_881
    assert body["v8_route_ledger_sha256"] == trial.sha(trial.route.LEDGER)
    assert body["v8_route_seal_sha256"] == trial.sha(trial.route.SEAL)
    assert body["terminal_identity_qualification_failure_sha256"] == trial.sha(trial.OLD_FAILURE)
    monkeypatch.setattr(trial, "OPENING", 667_880)
    with pytest.raises(trial.QualificationError, match="opening"):
        trial.seal_body()


def test_owner_approval_template_is_exactly_default_deny() -> None:
    approval = trial.approval_template()
    assert approval["authorized_phases"] == []
    assert approval["dispatch_allowed"] is False
    assert approval["owner_accepted"] is False
    assert json.loads(trial.APPROVAL.read_text()) == approval


def test_dispatch_rechecks_runtime_path_after_preflight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "target"
    target.mkdir()
    linked = tmp_path / "runtime"
    linked.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(trial, "RUNTIME", linked)
    monkeypatch.setattr(trial, "verify_seal", lambda: None)
    monkeypatch.setattr(trial, "verify_approval", lambda **_kwargs: None)
    monkeypatch.setattr(trial, "sha", lambda _path: "test-seal")
    monkeypatch.setattr(
        trial,
        "read",
        lambda _path: {
            "status": "PASSED_OFFLINE_QUALIFICATION_SUCCESSOR_PREFLIGHT",
            "operational_seal_sha256": "test-seal",
            "provider_calls": 0,
            "dispatch_allowed": False,
            "planned_calls": 128,
            "opening_codex_tokens": 667_881,
            "gateway_probe": "verified_tls_handshake_without_api_request",
        },
    )
    with pytest.raises(trial.QualificationError, match="runtime is linked"):
        trial.advance()
    assert list(target.iterdir()) == []
