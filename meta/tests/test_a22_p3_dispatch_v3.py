"""The proposed V3 dispatch boundary remains fail-closed without live gates."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("a22_p3_dispatch_v3", HERE / "dispatch_v3.py")
dispatch = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(dispatch)


def test_canonical_default_deny_approval_cannot_admit_dispatch(tmp_path: Path) -> None:
    with pytest.raises(dispatch.ledger.LedgerError):
        dispatch.require_dispatch(
            phase="technical_source",
            approval=HERE / "runs" / "owner-approval-v3.json",
            seal_path=tmp_path / "missing-seal.json",
            plan=HERE / "RUN_PLAN_V3_CLEAN_RESTART_PROPOSAL.md",
            packet_seal=HERE / "seal.json",
            ledger_path=tmp_path / "missing-ledger.jsonl",
        )


def test_unknown_phase_is_rejected_before_reading_artifacts() -> None:
    with pytest.raises(dispatch.ledger.LedgerError, match="unknown V3 dispatch phase"):
        dispatch.require_dispatch(phase="v2_retry")
