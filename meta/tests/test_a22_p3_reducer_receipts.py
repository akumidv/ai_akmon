"""Adversarial offline coverage for receipt-gated P3 score reduction."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

REDUCER_PATH = Path(__file__).parents[1] / "experiments" / "a22-p3" / "reduce_scorer_tsvs.py"
SPEC = importlib.util.spec_from_file_location("a22_p3_reducer_receipts", REDUCER_PATH)
assert SPEC is not None and SPEC.loader is not None
reducer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reducer)

PACKET_ID = "g0123456789abcdef"
PACKET_SHA = "1" * 64
PROMPT_SHA = "2" * 64
MODEL = {"codex": "gpt-6-astra", "qwen": "qwen3.8-27b"}


def _write_reading(
    root: Path,
    usage_root: Path,
    route: str,
    *,
    outcome_status: str = "SCORED_READING_ACCEPTED",  # noqa: PLR0913
    text: str | None = None,
    replace: bool = False,
) -> tuple[Path, dict[str, object]]:
    call_id = ("a" if route == "codex" else "b") * 32
    attempt_dir = root / call_id
    attempt_dir.mkdir(parents=True, exist_ok=replace)
    final = text or (
        "run_id\telement\tverdict\treason\n"
        + "".join(f"{PACKET_ID}\tE{i}\tPASS\t{route} reason {i}\n" for i in range(1, 5))
    )
    final_bytes = final.encode()
    (attempt_dir / "final.tsv").write_bytes(final_bytes)
    request_id = f"p3-scored-reading-{call_id}"
    attempt = {
        "record_type": "p3_scored_reading",
        "status": "invoking",
        "attempt_id": call_id,
        "request_id": request_id,
        "route": route,
        "opaque_packet_id": PACKET_ID,
        "packet_sha256": PACKET_SHA,
        "request_sha256": "3" * 64,
        "prompt_sha256": PROMPT_SHA,
        "model_requested": MODEL[route],
    }
    evidence = {
        "opaque_packet_id": PACKET_ID,
        "packet_sha256": PACKET_SHA,
        "request_sha256": "3" * 64,
        "tsv_sha256": hashlib.sha256(final_bytes).hexdigest(),
    }
    saved = {
        "usage": {"input_tokens": 100, "output_tokens": 30},
        "request_id": request_id,
        "session_id": f"session-{route}",
        "model_id": MODEL[route],
        "call_id": call_id,
        "evidence": evidence,
    }
    usage_path = usage_root / f"{call_id}.usage.json"
    usage_bytes = (json.dumps(saved, sort_keys=True) + "\n").encode()
    usage_path.write_bytes(usage_bytes)
    artifact = {
        "artifact_path": usage_path.name,
        "artifact_sha256": hashlib.sha256(usage_bytes).hexdigest(),
        "request_id": request_id,
        "session_id": f"session-{route}",
        "model_id": MODEL[route],
        "call_id": call_id,
    }
    outcome = {
        "status": outcome_status,
        "ledger_outcome": "accepted",
        "attempt_id": call_id,
        "request_id": request_id,
        "opaque_packet_id": PACKET_ID,
        "session_id": f"session-{route}",
        "model_id": MODEL[route],
        "usage_artifact": artifact,
        "tsv_sha256": hashlib.sha256(final_bytes).hexdigest(),
        "scored_p3": True,
        "qualification_data": True,
    }
    (attempt_dir / "attempt.json").write_text(json.dumps(attempt), encoding="utf-8")
    (attempt_dir / "outcome.json").write_text(json.dumps(outcome), encoding="utf-8")
    return attempt_dir / "final.tsv", {"route": route, "usage": saved["usage"], "usage_artifact": artifact}


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path, Path]:
    bundle_root = tmp_path / "bundles"
    bundle_root.mkdir()
    codex_root, qwen_root = tmp_path / "codex", tmp_path / "qwen"
    usage_root = tmp_path / "usage"
    codex_root.mkdir()
    qwen_root.mkdir()
    usage_root.mkdir()
    _codex_file, codex_row = _write_reading(codex_root, usage_root, "codex")
    _qwen_file, qwen_row = _write_reading(qwen_root, usage_root, "qwen")
    monkeypatch.setattr(
        reducer,
        "_load_evaluator_bundles",
        lambda _root: {
            PACKET_ID: {
                "source_run_id": "run-1",
                "elements": {"E1", "E2", "E3", "E4"},
                "packet_sha256": PACKET_SHA,
                "prompt_sha256": PROMPT_SHA,
            }
        },
    )
    ledger = SimpleNamespace(DEFAULT_PATHS=(usage_root / "ledger.jsonl", Path("plan"), Path("seal"), Path("approval")))
    monkeypatch.setattr(reducer, "_load_ledger", lambda: ledger)
    codex_row.update({"opaque_packet_id": PACKET_ID, "packet_sha256": PACKET_SHA})
    qwen_row.update({"opaque_packet_id": PACKET_ID, "packet_sha256": PACKET_SHA})
    monkeypatch.setattr(reducer, "_accepted_readings", lambda _ledger: {"a" * 32: codex_row, "b" * 32: qwen_row})
    return codex_root, qwen_root, bundle_root, tmp_path / "output"


def test_reducer_accepts_two_independent_receipted_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    codex, qwen, bundles, output = _setup(tmp_path, monkeypatch)
    result = reducer.reduce_scores(codex, qwen, bundles, output)
    assert result["packet_count"] == 1
    assert (output / "scorer-1-grid.tsv").read_text().startswith("run-1\tE1\tPASS\tcodex reason 1")
    assert (output / "scorer-2-grid.tsv").read_text().startswith("run-1\tE1\tPASS\tqwen reason 1")


@pytest.mark.parametrize("attack", ["same_directory", "missing_receipt", "fabricated_outcome"])
def test_reducer_rejects_unpaired_or_fabricated_receipts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attack: str,
) -> None:
    codex, qwen, bundles, output = _setup(tmp_path, monkeypatch)
    if attack == "same_directory":
        qwen = codex
    elif attack == "missing_receipt":
        (qwen / ("b" * 32) / "outcome.json").unlink(missing_ok=True)
    elif attack == "fabricated_outcome":
        path = qwen / ("b" * 32) / "outcome.json"
        receipt = json.loads(path.read_text())
        receipt["status"] = "FAILED_CLOSED"
        path.write_text(json.dumps(receipt))
    with pytest.raises((ValueError, FileNotFoundError)):
        reducer.reduce_scores(codex, qwen, bundles, output)
    assert not output.exists()


def test_reducer_allows_identical_tsv_content_from_distinct_accepted_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex, qwen, bundles, output = _setup(tmp_path, monkeypatch)
    identical = (codex / ("a" * 32) / "final.tsv").read_text()
    _path, qwen_row = _write_reading(qwen, tmp_path / "usage", "qwen", text=identical, replace=True)
    monkeypatch.setattr(
        reducer,
        "_accepted_readings",
        lambda _ledger: {
            "a" * 32: {
                "route": "codex",
                "usage": {"input_tokens": 100, "output_tokens": 30},
                "usage_artifact": json.loads((codex / ("a" * 32) / "outcome.json").read_text())["usage_artifact"],
                "opaque_packet_id": PACKET_ID,
                "packet_sha256": PACKET_SHA,
            },
            "b" * 32: {**qwen_row, "opaque_packet_id": PACKET_ID, "packet_sha256": PACKET_SHA},
        },
    )
    result = reducer.reduce_scores(codex, qwen, bundles, output)
    assert result["packet_count"] == 1
