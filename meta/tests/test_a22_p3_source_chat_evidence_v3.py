"""Chat-evidence extraction stays explicit, raw-preserving, and source-phase scoped."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

EXPERIMENT = Path(__file__).resolve().parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(EXPERIMENT))
spec = importlib.util.spec_from_file_location("source_chat_evidence_v3", EXPERIMENT / "source_chat_evidence_v3.py")
assert spec and spec.loader
chat = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = chat
spec.loader.exec_module(chat)
phase_spec = importlib.util.spec_from_file_location("source_phase_v3_chat_test", EXPERIMENT / "source_phase_v3.py")
assert phase_spec and phase_spec.loader
phase = importlib.util.module_from_spec(phase_spec)
sys.modules[phase_spec.name] = phase
phase_spec.loader.exec_module(phase)


def _synthetic_log(path: Path, *, override: str = chat.OVERRIDE_TEXT) -> None:
    acceptance = (
        "> I accept the V3-only 5,000,000-token Codex accounting ceiling, including its exclusion of the known "
        "153,614-token V2 debit and unresolved q1461 usage from that\n"
        "  > ceiling while preserving both as separately reported V2 history. I accept the frozen technical-source "
        "conditions, the OBSERVED_NO_RETRY evidence limit, the 80% five-\n"
        "  > hour and 90% weekly stop thresholds, the requirement for fresh interpretable quota telemetry, and the "
        "named human stop operator recorded in the amended approval. I\n"
        "  > authorize only the technical_source phase for the exact amended proposal and seal. This does not "
        "authorize route checks, qualification, comparison, repair, retry, or\n"
        "  > any other provider call."
    )
    rows: list[dict[str, Any]] = [
        {"type": "session_meta", "payload": {"session_id": chat.SESSION_ID, "originator": "codex-tui"}},
        {
            "type": "response_item",
            "ordinal": 23009,
            "timestamp": "stable-acceptance",
            "payload": {
                "type": "message",
                "id": chat.ACCEPTANCE_MESSAGE_ID,
                "role": "user",
                "content": [{"type": "input_text", "text": acceptance}],
                "internal_chat_message_metadata_passthrough": {"turn_id": "01a13fac-73f5-7302-abc1-4d3d5c6b9d8e"},
            },
        },
        {
            "type": "response_item",
            "ordinal": 23313,
            "timestamp": "stable-override",
            "payload": {
                "type": "message",
                "id": chat.OVERRIDE_MESSAGE_ID,
                "role": "user",
                "content": [{"type": "input_text", "text": override}],
                "internal_chat_message_metadata_passthrough": {"turn_id": "01a13fd2-5a39-7570-8ae5-50d42fc54e13"},
            },
        },
    ]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_synthetic_chat_log_preserves_raw_text_and_normalizes_wrapped_approval(tmp_path: Path) -> None:
    source_log = tmp_path / "session.jsonl"
    artifact_path = tmp_path / "evidence.json"
    _synthetic_log(source_log)
    artifact = chat.capture(source_log)
    assert artifact["acceptance_message"]["raw_text"] != artifact["acceptance_message"]["canonical_quote"]
    assert artifact["acceptance_message"]["canonical_quote"] == chat.CANONICAL_QUOTE
    assert artifact["acceptance_message"]["normalization_id"] == chat.NORMALIZATION_ID
    assert artifact["override_message"]["raw_text"] == chat.OVERRIDE_TEXT
    assert artifact["override_message"]["scope"] == ["technical_source"]
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    checked = chat.validate_artifact(
        artifact_path=artifact_path, expected_quote=chat.CANONICAL_QUOTE, source_log_path=source_log
    )
    assert checked["scope"] == ["technical_source"]
    assert checked["authentication"] == "unsigned local log evidence; not a cryptographic signature"


def test_synthetic_override_edit_and_non_quote_line_are_rejected(tmp_path: Path) -> None:
    source_log = tmp_path / "session.jsonl"
    _synthetic_log(source_log, override="запусти всё")
    with pytest.raises(chat.ChatEvidenceError, match="identity or text differs"):
        chat.capture(source_log)
    with pytest.raises(chat.ChatEvidenceError, match="non-blockquote"):
        chat.normalize_markdown_quote("> first\nsecond")


def test_source_phase_acceptance_gate_consumes_raw_chat_artifact(tmp_path: Path) -> None:
    source_log = tmp_path / "session.jsonl"
    artifact_path = tmp_path / "evidence.json"
    _synthetic_log(source_log)
    artifact = chat.capture(source_log)
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    evidence = {
        "exact_quote": chat.CANONICAL_QUOTE,
        "transcript_path": str(artifact_path),
        "transcript_sha256": chat.sha256_bytes(artifact_path.read_bytes()),
        "amendment_proposal_sha256": "a" * 64,
        "proposal_sha256": "b" * 64,
        "operative_v3_seal_sha256": "c" * 64,
        "amendment_seal_sha256": "d" * 64,
    }
    digest = phase._validate_acceptance_transcript(evidence, phase.AMENDMENT_PROPOSAL)
    assert digest == evidence["transcript_sha256"]
