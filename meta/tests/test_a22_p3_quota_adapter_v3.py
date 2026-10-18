"""Synthetic-only checks for the V3 Codex subscription quota adapter."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "experiments" / "a22-p3"))
import quota_adapter_v3 as quota
import usage_ledger_v3 as ledger

CAPTURED = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
FIXTURE = {
    "rateLimitsByLimitId": {
        "codex": {
            "primary": {"windowDurationMins": 300, "usedPercent": 79, "resetsAt": 1792080000},
            "secondary": {"windowDurationMins": 10080, "usedPercent": 89, "resetsAt": 1792600000},
        },
    },
}


def test_parse_normalizes_codex_windows_and_hides_raw_payload() -> None:
    snapshot = quota.parse_snapshot(FIXTURE, captured_at=CAPTURED, freshness_seconds=1.25)
    assert snapshot == {
        "captured_utc": "2026-10-15T12:00:00Z",
        "source": quota.SOURCE,
        "source_version": quota.RPC_VERSION,
        "freshness_seconds": 1.25,
        "five_hour_used_percent": 79,
        "five_hour_reset_utc": "2026-10-15T16:00:00Z",
        "weekly_used_percent": 89,
        "weekly_reset_utc": "2026-10-21T16:26:40Z",
        "raw_redacted_sha256": snapshot["raw_redacted_sha256"],
    }
    assert len(snapshot["raw_redacted_sha256"]) == 64
    assert set(snapshot) == {
        "captured_utc",
        "source",
        "source_version",
        "freshness_seconds",
        "five_hour_used_percent",
        "five_hour_reset_utc",
        "weekly_used_percent",
        "weekly_reset_utc",
        "raw_redacted_sha256",
    }


def test_legacy_windows_are_supported_and_thresholds_stop_at_equality() -> None:
    legacy = {
        "rateLimits": {
            "primary": {"windowDurationMins": 300, "usedPercent": 80, "resetsAt": 1792080000},
            "secondary": {"windowDurationMins": 10080, "usedPercent": 20, "resetsAt": 1792600000},
        }
    }
    snapshot = quota.parse_snapshot(legacy, captured_at=CAPTURED)
    with pytest.raises(ledger.LedgerError, match="stop threshold"):
        quota.checkpoint_decision(snapshot)
    below = quota.parse_snapshot(FIXTURE, captured_at=CAPTURED)
    assert quota.checkpoint_decision(below)["dispatch_allowed"] is True


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"rateLimitsByLimitId": {"other": {}}},
        {
            "rateLimitsByLimitId": {
                "codex": {"primary": {"windowDurationMins": 300, "usedPercent": 10, "resetsAt": 1792080000}}
            }
        },
        {
            "rateLimitsByLimitId": {
                "codex": {
                    "primary": {"windowDurationMins": 300, "usedPercent": 101, "resetsAt": 1792080000},
                    "secondary": {"windowDurationMins": 10080, "usedPercent": 10, "resetsAt": 1792600000},
                }
            }
        },
        {
            "rateLimitsByLimitId": {
                "codex": {
                    "primary": {"windowDurationMins": 300, "usedPercent": 10, "resetsAt": None},
                    "secondary": {"windowDurationMins": 10080, "usedPercent": 10, "resetsAt": 1792600000},
                }
            }
        },
    ],
)
def test_missing_malformed_or_uninterpretable_quota_fails_closed(bad: object) -> None:
    with pytest.raises(quota.QuotaError):
        quota.parse_snapshot(bad, captured_at=CAPTURED)


def test_stale_freshness_fails_closed() -> None:
    with pytest.raises(quota.QuotaError, match="stale"):
        quota.parse_snapshot(FIXTURE, captured_at=CAPTURED, freshness_seconds=601)


def test_weekly_threshold_stops_at_equality() -> None:
    payload = {
        "rateLimitsByLimitId": {
            "codex": {
                "primary": {"windowDurationMins": 300, "usedPercent": 5, "resetsAt": 1792080000},
                "secondary": {"windowDurationMins": 10080, "usedPercent": 90, "resetsAt": 1792600000},
            }
        }
    }
    snapshot = quota.parse_snapshot(payload, captured_at=CAPTURED)
    with pytest.raises(ledger.LedgerError, match="stop threshold"):
        quota.checkpoint_decision(snapshot)
