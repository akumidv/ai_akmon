#!/usr/bin/env python3
"""V3-only Codex subscription quota capture through app-server RPC.

This module reads account quota state only. It never creates a thread or starts
a model turn. Synthetic protocol responses can be supplied to ``parse_snapshot``
for offline validation.
"""
from __future__ import annotations

import hashlib
import json
import os
import select
import stat
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import usage_ledger_v3 as ledger

SOURCE = "codex app-server account/rateLimits/read"
RPC_VERSION = "JSON-RPC 2.0"
TIMEOUT_SECONDS = 15
MAX_LINE_BYTES = 65536
MAX_STDERR_BYTES = 8192
MAX_QUOTA_FRESHNESS_SECONDS = 600
PERCENT_MAX = 100
MAX_VERSION_CHARS = 120
INIT_ID = 1
QUOTA_ID = 2
ACCOUNT_BINDING_FIELDS = {
    "codex_executable_sha256", "codex_home_sha256", "account_id_sha256",
    "five_hour_stop_percent", "weekly_stop_percent", "limit_receipt_sha256",
}


class QuotaError(ValueError):
    """Quota telemetry is unavailable, stale, or uninterpretable."""


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _reset_utc(value: object) -> str:
    # app-server RateLimitWindow.resetsAt is an epoch-seconds int64.
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise QuotaError("quota reset time is missing or malformed")
    try:
        return _utc(datetime.fromtimestamp(value, tz=UTC))
    except (OverflowError, OSError, ValueError) as exc:
        raise QuotaError("quota reset time is outside the supported range") from exc


def _selected_limits(result: object) -> object:
    if not isinstance(result, dict):
        raise QuotaError("quota RPC result is malformed")
    by_id = result.get("rateLimitsByLimitId")
    if isinstance(by_id, dict):
        codex = by_id.get("codex")
        if codex is None:
            raise QuotaError("Codex quota bucket is missing")
        return codex
    if by_id is not None:
        raise QuotaError("quota bucket map is malformed")
    legacy = result.get("rateLimits")
    if legacy is None:
        raise QuotaError("quota limits are missing")
    return legacy


def _windows(limits: object) -> tuple[dict[str, object], dict[str, object]]:  # noqa: C901
    if not isinstance(limits, dict):
        raise QuotaError("quota limits payload is malformed")
    found: dict[int, dict[str, object]] = {}

    def walk(node: object) -> None:
        if isinstance(node, dict):
            duration = node.get("windowDurationMins", node.get("window_duration_mins"))
            used = node.get("usedPercent", node.get("used_percent"))
            if duration in (300, 10080) and not isinstance(duration, bool):
                if duration in found:
                    raise QuotaError("duplicate quota window")
                if (not isinstance(used, (int, float)) or isinstance(used, bool) or
                        not 0 <= used <= PERCENT_MAX):
                    raise QuotaError("quota percentage is missing or malformed")
                reset = node.get("resetsAt", node.get("resets_at"))
                found[duration] = {"used": used, "reset": _reset_utc(reset)}
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(limits)
    if set(found) != {300, 10080}:
        raise QuotaError("both five-hour and weekly quota windows are required")
    return found[300], found[10080]


def parse_snapshot(result: object, *, captured_at: datetime,
                   freshness_seconds: float = 0) -> dict[str, Any]:
    """Normalize a successful ``account/rateLimits/read`` result."""
    if freshness_seconds < 0 or freshness_seconds > MAX_QUOTA_FRESHNESS_SECONDS:
        raise QuotaError("quota telemetry is missing or stale")
    limits = _selected_limits(result)
    five_hour, weekly = _windows(limits)
    # Retain only the two quota window records in the digest; account identity,
    # upsell metadata, and unrelated response fields never enter the artifact.
    redacted = json.dumps(limits, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return {
        "captured_utc": _utc(captured_at),
        "source": SOURCE,
        "source_version": RPC_VERSION,
        "freshness_seconds": freshness_seconds,
        "five_hour_used_percent": five_hour["used"],
        "five_hour_reset_utc": five_hour["reset"],
        "weekly_used_percent": weekly["used"],
        "weekly_reset_utc": weekly["reset"],
        "raw_redacted_sha256": hashlib.sha256(redacted).hexdigest(),
    }


def account_limit_receipt(codex_executable: str, codex_home: Path) -> dict[str, Any]:
    """Bind quota limits to the exact CLI, external home, and account without exposing auth."""
    executable = Path(codex_executable).resolve()
    raw_home = codex_home.expanduser()
    if raw_home.is_symlink():
        raise QuotaError("external Codex home cannot be a symlink")
    home = raw_home.resolve()
    auth_path = home / "auth.json"
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise QuotaError("pinned Codex executable is unavailable")
    if not home.is_dir() or home.is_symlink() or not auth_path.is_file() or auth_path.is_symlink():
        raise QuotaError("external Codex home or account credential is unavailable")
    if stat.S_IMODE(auth_path.stat().st_mode) & 0o077:
        raise QuotaError("Codex auth file permissions are not private")
    try:
        auth = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QuotaError("Codex account credential is malformed") from exc
    tokens = auth.get("tokens") if isinstance(auth, dict) else None
    account_id = tokens.get("account_id") if isinstance(tokens, dict) else None
    if account_id is None and isinstance(auth, dict):
        account_id = auth.get("account_id")
    if not isinstance(account_id, str) or not account_id.strip():
        raise QuotaError("Codex account identifier is unavailable for binding")
    binding = {
        "codex_executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "codex_home_sha256": hashlib.sha256(str(home).encode()).hexdigest(),
        "account_id_sha256": hashlib.sha256(account_id.encode()).hexdigest(),
        "five_hour_stop_percent": ledger.FIVE_HOUR_STOP_PERCENT,
        "weekly_stop_percent": ledger.WEEKLY_STOP_PERCENT,
    }
    receipt_hash = hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {**binding, "limit_receipt_sha256": receipt_hash}


def _read_rpc_result(  # noqa: C901, PLR0912, PLR0915
        *, codex_executable: str, environment: dict[str, str],
        timeout: float = TIMEOUT_SECONDS) -> tuple[object, str]:
    """Perform only initialize + account/rateLimits/read, with bounded I/O."""
    try:
        proc = subprocess.Popen(
            [codex_executable, "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=tempfile.gettempdir(), env=environment, bufsize=0,
        )
    except OSError as exc:
        raise QuotaError("cannot start Codex app-server") from exc
    if proc.stdin is None or proc.stdout is None or proc.stderr is None:
        proc.kill()
        proc.wait()
        raise QuotaError("Codex app-server stdio is unavailable")
    deadline = time.monotonic() + timeout
    pending = bytearray()
    stderr = bytearray()
    phase = "initialize"
    response: object | None = None

    def send(item: dict[str, object]) -> None:
        proc.stdin.write((json.dumps(item, separators=(",", ":")) + "\n").encode())
        proc.stdin.flush()

    try:
        send({"id": INIT_ID, "method": "initialize", "params": {
            "clientInfo": {"name": "akmon-a22-p3-v3-quota", "version": "1"},
            "capabilities": {},
        }})
        streams = [proc.stdout, proc.stderr]
        while streams and time.monotonic() < deadline:
            ready, _, _ = select.select(streams, [], [], max(0, deadline - time.monotonic()))
            if not ready:
                raise QuotaError("Codex quota RPC timed out")
            for stream in ready:
                chunk = os.read(stream.fileno(), 4096)
                if not chunk:
                    streams.remove(stream)
                    continue
                if stream is proc.stderr:
                    if len(stderr) < MAX_STDERR_BYTES:
                        stderr.extend(chunk[:MAX_STDERR_BYTES - len(stderr)])
                    continue
                pending.extend(chunk)
                if b"\n" not in pending and len(pending) > MAX_LINE_BYTES:
                    raise QuotaError("Codex quota RPC line exceeds limit")
                while b"\n" in pending:
                    line, _, remainder = pending.partition(b"\n")
                    pending = bytearray(remainder)
                    if len(line) > MAX_LINE_BYTES:
                        raise QuotaError("Codex quota RPC line exceeds limit")
                    try:
                        message = json.loads(line)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        raise QuotaError("Codex quota RPC returned malformed JSON") from None
                    if not isinstance(message, dict):
                        raise QuotaError("Codex quota RPC response is malformed")
                    if message.get("id") == INIT_ID and phase == "initialize":
                        if "error" in message:
                            raise QuotaError("Codex app-server initialize failed")
                        send({"method": "initialized"})
                        send({"id": QUOTA_ID, "method": "account/rateLimits/read"})
                        phase = "quota"
                    elif message.get("id") == QUOTA_ID and phase == "quota":
                        if "error" in message or "result" not in message:
                            raise QuotaError("Codex quota RPC failed")
                        response = message["result"]
                        return response, bytes(stderr).decode("utf-8", errors="replace")
        raise QuotaError("Codex quota RPC closed before a quota response")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        for pipe in (proc.stdin, proc.stdout, proc.stderr):
            if pipe:
                pipe.close()


def _codex_version(codex_executable: str, environment: dict[str, str]) -> str:
    try:
        completed = subprocess.run([codex_executable, "--version"], cwd=tempfile.gettempdir(),
                                   env=environment, capture_output=True,
                                   text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise QuotaError("cannot determine Codex app-server version") from exc
    version = completed.stdout.strip()
    if completed.returncode != 0 or not version or len(version) > MAX_VERSION_CHARS:
        raise QuotaError("cannot determine Codex app-server version")
    return version


def read_quota_snapshot(*, codex_executable: str, codex_home: Path,
                        environment: dict[str, str], now: datetime | None = None) -> dict[str, Any]:
    """Capture a fresh quota snapshot; raises ``QuotaError`` on any uncertainty."""
    expected_receipt = account_limit_receipt(codex_executable, codex_home)
    if environment.get("CODEX_HOME") != str(codex_home.resolve()):
        raise QuotaError("quota probe CODEX_HOME differs from the source runner")
    started = time.monotonic()
    result, _stderr = _read_rpc_result(codex_executable=codex_executable, environment=environment)
    captured_at = datetime.now(UTC)
    if now is not None:
        captured_at = now.astimezone(UTC)
    freshness = max(0.0, time.monotonic() - started)
    snapshot = parse_snapshot(result, captured_at=captured_at, freshness_seconds=freshness)
    snapshot["source_version"] = _codex_version(codex_executable, environment)
    snapshot["account_limit_receipt"] = expected_receipt
    return snapshot


def checkpoint_decision(snapshot: object) -> dict[str, object]:
    """Validate a snapshot and expose the proposed 80%/90% Codex stop gate."""
    checked = ledger.validate_quota(snapshot, "codex")
    return {"dispatch_allowed": True, "five_hour_stop_percent": 80,
            "weekly_stop_percent": 90, "snapshot": checked}
