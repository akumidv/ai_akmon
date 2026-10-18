#!/usr/bin/env python3
"""Validate raw owner-message provenance from a retained local Codex session log.

This establishes byte integrity and a reproducible extraction from the supplied
local log. It does not authenticate who controlled the account or cryptographically
sign the conversation.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
SESSION_ID = "01a0cd8d-4d82-7ac0-8b96-ce11eb0ff664"
SOURCE_LOG = Path(
    "/home/ai/.codex/sessions/2026/09/23/"
    "rollout-2026-09-23T09-16-25-01a0cd8d-4d82-7ac0-8b96-ce11eb0ff664.jsonl"
)
ACCEPTANCE_MESSAGE_ID = "msg_01a13fac-74fc-7c53-b0e8-3ccd0cab5518"
OVERRIDE_MESSAGE_ID = "msg_01a13fd2-60d4-76c1-9534-789886872230"
OVERRIDE_TEXT = "запусти все, я утверждаю без этой повторной отправки с коррекцией символов."  # noqa: RUF001
NORMALIZATION_ID = "blockquote-soft-wrap-dehyphen-v1"
CANONICAL_QUOTE = (
    "I accept the V3-only 5,000,000-token Codex accounting ceiling, including its exclusion of the "
    "known 153,614-token V2 debit and unresolved q1461 usage from that ceiling while preserving both "
    "as separately reported V2 history. I accept the frozen technical-source conditions, the "
    "OBSERVED_NO_RETRY evidence limit, the 80% five-hour and 90% weekly stop thresholds, the "
    "requirement for fresh interpretable quota telemetry, and the named human stop operator recorded "
    "in the amended approval. I authorize only the technical_source phase for the exact amended "
    "proposal and seal. This does not authorize route checks, qualification, comparison, repair, retry, "
    "or any other provider call."
)


class ChatEvidenceError(ValueError):
    """Raw chat evidence is absent, stale, malformed, or out of scope."""


def sha256_bytes(data: bytes) -> str:
    """Hash exact bytes."""
    return hashlib.sha256(data).hexdigest()


def _outside_repo(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == REPO or REPO in resolved.parents:
        raise ChatEvidenceError("chat evidence and source log must remain external to the repository")
    return resolved


def normalize_markdown_quote(raw_text: str) -> str:
    """Remove quote leaders, join soft wraps, and repair only wrap-split hyphens."""
    lines = raw_text.splitlines()
    body: list[str] = []
    for line in lines:
        match = re.fullmatch(r"\s*> ?(.*)", line)
        if match is None:
            raise ChatEvidenceError("approval quote contains a non-blockquote line")
        body.append(match.group(1).strip())
    joined = " ".join(part for part in body if part)
    joined = re.sub(r"(?<=[A-Za-z])-(?=\s+[a-z])\s+", "-", joined)
    return re.sub(r"\s+", " ", joined).strip()


def _records(log_path: Path) -> tuple[str, dict[str, dict[str, Any]]]:  # noqa: C901
    source = _outside_repo(log_path)
    try:
        raw_bytes = source.read_bytes()
    except OSError as exc:
        raise ChatEvidenceError("retained Codex source log is unavailable") from exc
    found: dict[str, dict[str, Any]] = {}
    metadata_record_sha256: str | None = None
    try:
        parsed_rows = []
        for line in raw_bytes.splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                if ACCEPTANCE_MESSAGE_ID.encode() in line or OVERRIDE_MESSAGE_ID.encode() in line:
                    raise
                continue
            parsed_rows.append(row)
            payload = row.get("payload", {})
            if len(parsed_rows) == 1:
                metadata_record_sha256 = sha256_bytes(line)
            if (row.get("type") == "response_item" and payload.get("type") == "message" and
                    payload.get("role") == "user" and payload.get("id") in {
                        ACCEPTANCE_MESSAGE_ID, OVERRIDE_MESSAGE_ID
                    }):
                message_id = payload["id"]
                if message_id in found:
                    raise ChatEvidenceError("source log repeats a selected user message ID")
                found[message_id] = {
                    "ordinal": row.get("ordinal"),
                    "session_id": payload.get(
                        "internal_chat_message_metadata_passthrough", {}).get("turn_id"),
                    "timestamp": row.get("timestamp"),
                    "log_record_sha256": sha256_bytes(line),
                    "text": "\n".join(item["text"] for item in payload.get("content", [])
                                     if item.get("type") == "input_text"),
                }
    except (json.JSONDecodeError, AttributeError, KeyError, TypeError) as exc:
        raise ChatEvidenceError("retained Codex source log is malformed") from exc
    metadata = parsed_rows[0].get("payload", {}) if parsed_rows else {}
    if (parsed_rows[0].get("type") != "session_meta" or metadata.get("session_id") != SESSION_ID or
            metadata.get("originator") != "codex-tui"):
        raise ChatEvidenceError("source log metadata does not identify the expected Codex TUI session")
    if set(found) != {ACCEPTANCE_MESSAGE_ID, OVERRIDE_MESSAGE_ID}:
        raise ChatEvidenceError("source log does not contain both selected user messages")
    if any(not isinstance(record["text"], str) for record in found.values()):
        raise ChatEvidenceError("selected user message text is malformed")
    selected = {
        "session_metadata_record_sha256": metadata_record_sha256,
        ACCEPTANCE_MESSAGE_ID: found[ACCEPTANCE_MESSAGE_ID]["log_record_sha256"],
        OVERRIDE_MESSAGE_ID: found[OVERRIDE_MESSAGE_ID]["log_record_sha256"],
    }
    return sha256_bytes(json.dumps(selected, sort_keys=True, separators=(",", ":")).encode()), found


def capture(log_path: Path = SOURCE_LOG) -> dict[str, Any]:
    """Return an unsigned evidence record extracted from the fixed session log."""
    selected_records_hash, messages = _records(log_path)
    acceptance = messages[ACCEPTANCE_MESSAGE_ID]
    override = messages[OVERRIDE_MESSAGE_ID]
    if (acceptance["session_id"] != "01a13fac-73f5-7302-abc1-4d3d5c6b9d8e" or
            override["session_id"] != "01a13fd2-5a39-7570-8ae5-50d42fc54e13" or
            override["text"] != OVERRIDE_TEXT or
            normalize_markdown_quote(acceptance["text"]) != CANONICAL_QUOTE):
        raise ChatEvidenceError("retained user message identity or text differs from the captured evidence")
    return {
        "schema": 1,
        "record_type": "p3_v3_chat_acceptance_evidence",
        "session_id": SESSION_ID,
        "source_log_path": str(_outside_repo(log_path)),
        "selected_log_records_sha256": selected_records_hash,
        "source_log_authentication": (
            "local_unsigned_log; no cryptographic signature or independent account authentication"
        ),
        "acceptance_message": {
            "message_id": ACCEPTANCE_MESSAGE_ID,
            "turn_id": acceptance["session_id"],
            "ordinal": 23009,
            "timestamp": acceptance["timestamp"],
            "raw_text": acceptance["text"],
            "raw_text_sha256": sha256_bytes(acceptance["text"].encode("utf-8")),
            "canonical_quote": CANONICAL_QUOTE,
            "normalization_id": NORMALIZATION_ID,
        },
        "override_message": {
            "message_id": OVERRIDE_MESSAGE_ID,
            "turn_id": override["session_id"],
            "ordinal": 23313,
            "timestamp": override["timestamp"],
            "raw_text": override["text"],
            "raw_text_sha256": sha256_bytes(override["text"].encode("utf-8")),
            "scope": ["technical_source"],
        },
        "normalization": {
            "id": NORMALIZATION_ID,
            "steps": [
                "require every physical quote line to begin with optional whitespace and a Markdown > marker",
                "remove that marker and at most one following ASCII space",
                "trim each line and join non-empty lines with one ASCII space",
                "remove whitespace after a line-final ASCII hyphen before a lowercase ASCII letter",
                "collapse remaining whitespace runs to one ASCII space and trim ends",
            ],
            "raw_text_is_canonical_quote": False,
        },
        "scope": ["technical_source"],
    }


def validate_artifact(*, artifact_path: Path, expected_quote: str,
                      source_log_path: Path = SOURCE_LOG) -> dict[str, Any]:
    """Re-read the exact log, verify artifact hashes, and enforce the narrow scope."""
    artifact_path = _outside_repo(artifact_path)
    try:
        artifact_bytes = artifact_path.read_bytes()
        artifact = json.loads(artifact_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise ChatEvidenceError("external chat evidence artifact is unavailable or malformed") from exc
    expected = capture(source_log_path)
    if (artifact != expected or expected_quote != CANONICAL_QUOTE or
            artifact["acceptance_message"]["canonical_quote"] != expected_quote or
            artifact["scope"] != ["technical_source"] or
            artifact["override_message"]["scope"] != ["technical_source"]):
        raise ChatEvidenceError("chat evidence does not bind the canonical quote and technical_source-only override")
    return {
        "artifact_sha256": sha256_bytes(artifact_bytes),
        "selected_log_records_sha256": expected["selected_log_records_sha256"],
        "acceptance_message_id": ACCEPTANCE_MESSAGE_ID,
        "override_message_id": OVERRIDE_MESSAGE_ID,
        "scope": ["technical_source"],
        "authentication": "unsigned local log evidence; not a cryptographic signature",
    }
