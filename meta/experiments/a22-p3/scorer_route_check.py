#!/usr/bin/env python3
"""One-shot, ledger-reserved mechanics check for a frozen P3 scorer route.

The CLI is intentionally a single provider process. This file contains no score
aggregation and never writes a scorer response into the experiment's score ledger.
Dispatch requires the canonical V2 ledger reservation to authorize route_check.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
LEDGER_PATH = RUNS / "provider-usage-v2.jsonl"
CODEX = {"executable": "codex", "version": "0.156.1", "model": "gpt-6-astra", "effort": "medium"}
QWEN = {"executable": "qwen", "version": "0.24.7", "model": "qwen3.8-27b"}
INPUT_CAP = 20_000
OUTPUT_CAP = {"codex": 1_000, "qwen": 2_000}
OPAQUE_ID = re.compile(r"g[0-9a-f]{16}\Z")
TOOL_KEYS = {"tool_name", "tool_call_id"}
TOOL_MARKERS = {"function_call", "custom_tool_call", "local_shell_call", "web_search_call",
                "tool_search_call", "image_generation_call", "mcp_tool_call", "command_execution",
                "file_change", "computer_call", "tool_call", "shell_command"}
PACKET_MARKER = b"\nScoring packet follows as the sole supplied packet:\n\n"
RETRY_ERROR_MARKER = re.compile(r"\b(?:retr(?:y|ies|ied|ying)|error|failed|failure)\b", re.IGNORECASE)
RETRY_ERROR_EVENT_MARKER = re.compile(r"retry|error|failed|failure", re.IGNORECASE)
PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
TSV_COLUMN_COUNT = 4


class ProviderStartError(RuntimeError):
    """The provider CLI process could not be started."""


def sha(data: bytes) -> str:
    """Return the lowercase SHA-256 digest for bytes."""
    return hashlib.sha256(data).hexdigest()


def private_write(path: Path, data: bytes) -> None:
    """Create a private artifact without replacing an existing file."""
    path.parent.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
    if path.parent.is_symlink() or stat.S_IMODE(path.parent.stat().st_mode) != PRIVATE_DIR_MODE:
        raise ValueError("private artifact directory permissions are invalid")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, PRIVATE_FILE_MODE)
    try:
        os.fchmod(fd, PRIVATE_FILE_MODE)
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)


def write_json(path: Path, value: Any) -> None:
    """Write private JSON evidence with stable key ordering."""
    private_write(path, (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())


def _packet_builder() -> Any:
    path = HERE / "build_single_packet.py"
    spec = importlib.util.spec_from_file_location("a22_p3_packet_builder", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load the sealed packet verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _grid_source_context(builder: Any, current_hashes: dict[str, str]) -> tuple[dict[str, Any], dict[str, str]]:  # noqa: C901
    """Re-derive the current B/C map from the private A scorer pair."""
    import_record_path = RUNS / "qualification-import.json"
    if import_record_path.is_symlink() or not import_record_path.is_file():
        raise ValueError("grid qualification import provenance is missing")
    try:
        imported = json.loads(import_record_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("grid qualification import provenance is malformed") from exc
    if (not isinstance(imported, dict) or set(imported) != {"scorer_1", "scorer_2", "run_evidence"}
            or not isinstance(imported.get("scorer_1"), dict)
            or not isinstance(imported.get("scorer_2"), dict)
            or not isinstance(imported.get("run_evidence"), dict)):
        raise ValueError("grid qualification import provenance is incomplete")

    scorer_paths: list[Path] = []
    for key in ("scorer_1", "scorer_2"):
        item = imported[key]
        if not isinstance(item.get("path"), str):
            raise ValueError("grid qualification scorer provenance is malformed")
        path = Path(item["path"]).expanduser()
        if path.is_symlink() or not path.is_file():
            raise ValueError("private qualification scorer TSV is missing or unsafe")
        resolved = path.resolve(strict=True)
        if (stat.S_IMODE(resolved.stat().st_mode) != PRIVATE_FILE_MODE
                or stat.S_IMODE(resolved.parent.stat().st_mode) != PRIVATE_DIR_MODE):
            raise ValueError("private qualification scorer TSV permissions are invalid")
        digest = sha(resolved.read_bytes())
        if item.get("sha256") != digest:
            raise ValueError("qualification scorer TSV differs from import provenance")
        scorer_paths.append(resolved)
    derived, hashes = builder._grid_map_from_qualification(HERE, *scorer_paths)
    map_path = RUNS / "grid-sealed-map.json"
    if map_path.is_symlink() or not map_path.is_file():
        raise ValueError("generated grid map is missing or unsafe")
    candidate = builder._read_json(map_path)
    if candidate != derived:
        raise ValueError("generated grid map differs from scorer re-derivation")
    hashes = {**current_hashes, **hashes, "runs/grid-sealed-map.json": sha(map_path.read_bytes())}
    return derived, hashes


def validate_bundle(packet_dir: Path, evaluator_dir: Path) -> tuple[dict[str, Any], bytes, bytes, list[str]]:  # noqa: C901, PLR0912, PLR0915
    """Verify fresh packet bytes against the current sealed source without exposing its map."""
    builder = _packet_builder()
    if packet_dir.is_symlink() or evaluator_dir.is_symlink():
        raise ValueError("packet bundle uses a symlink")
    visible = packet_dir.resolve(strict=True)
    evaluator = evaluator_dir.resolve(strict=True)
    bundle = builder.verify_bundle(visible, evaluator)
    manifest = json.loads((evaluator / "manifest.json").read_text(encoding="utf-8"))
    packet = (visible / "packet.md").read_bytes()
    if {p.name for p in visible.iterdir()} != {"packet.md"}:
        raise ValueError("model-visible packet directory must contain exactly one file")
    if {p.name for p in evaluator.iterdir()} != {"manifest.json", "evaluator-map.json"}:
        raise ValueError("evaluator directory has unexpected files")
    if bundle.get("model_visible_packet_count") != 1 or bundle.get("packet_sha256") != sha(packet):
        raise ValueError("packet bundle verification disagrees with packet bytes")
    opaque_id = bundle.get("opaque_packet_id")
    if not isinstance(opaque_id, str) or not OPAQUE_ID.fullmatch(opaque_id):
        raise ValueError("packet id is not fresh opaque form")

    seal_files, sealed_map, current_hashes = builder._sealed_context(HERE)
    evaluator_map = json.loads((evaluator / "evaluator-map.json").read_text(encoding="utf-8"))
    source_id = evaluator_map.get("source_run_id")
    map_kind = manifest.get("source_map_kind")
    if map_kind not in {"qualification", "grid"} or evaluator_map.get("source_map_kind") != map_kind:
        raise ValueError("packet source map kind is unsupported or does not match evaluator mapping")
    if map_kind == "grid":
        source_map, expected_hashes = _grid_source_context(builder, current_hashes)
    else:
        source_map, expected_hashes = sealed_map, current_hashes
    cell = source_map.get(source_id) if isinstance(source_id, str) else None
    if not isinstance(cell, dict) or evaluator_map.get("sealed_cell") != cell:
        raise ValueError("private packet provenance does not match the current sealed map")
    case_path, case_bytes, scoring = builder._load_case(HERE, seal_files, cell)
    provenance = builder._verify_provenance(HERE, source_id, cell, seal_files)
    exchange_bytes, turns = builder._load_exchange(HERE, source_id)
    expected_sources = {
        **expected_hashes,
        case_path.as_posix(): sha(case_bytes),
        f"runs/{source_id}.exchange.json": sha(exchange_bytes),
    }
    sources = manifest.get("source_sha256")
    if not isinstance(sources, dict) or sources != expected_sources:
        raise ValueError("packet manifest does not bind the current sealed source files")
    if evaluator_map.get("provenance") != provenance:
        raise ValueError("packet provenance verification failed")
    expected_packet = builder._render_packet(opaque_id, turns, scoring)
    if packet != expected_packet:
        raise ValueError("packet bytes differ from the current sealed renderer output")

    ids = []
    for element in scoring:
        match = re.match(r"^(E[1-9][0-9]*)\b", element)
        if match is None:
            raise ValueError("sealed scoring element identifier is malformed")
        ids.append(match.group(1))
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError("sealed scoring elements are empty or duplicated")
    prompt = builder._sealed_bytes(HERE, seal_files, Path("scoring/scorer-prompt.txt"))
    if not prompt.strip():
        raise ValueError("sealed scorer prompt is empty")
    return manifest, packet, prompt, ids


def make_request(prompt: bytes, packet: bytes) -> bytes:
    """Join the frozen scorer prompt and one packet using the canary marker."""
    if not prompt.strip() or not packet.strip():
        raise ValueError("scorer request contains empty prompt or packet")
    return prompt + PACKET_MARKER + packet


def parse_jsonl(data: bytes) -> list[dict[str, Any]]:
    """Parse a nonempty provider JSONL stream containing object events only."""
    rows: list[dict[str, Any]] = []
    for line in data.decode("utf-8", errors="strict").splitlines():
        if line.strip():
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("provider event is not a JSON object")
            rows.append(row)
    if not rows:
        raise ValueError("provider event stream is empty")
    return rows


def tool_markers(value: Any) -> list[str]:
    """Collect recognizable tool-call markers from nested provider event data."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"type", "kind", "event_type"} and isinstance(child, str):
                lower = child.lower()
                if lower in TOOL_MARKERS or "tool_call" in lower or "function_call" in lower:
                    found.append(lower)
            if key in TOOL_KEYS and child:
                found.append(key)
            found.extend(tool_markers(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(tool_markers(child))
    return found


def cli_retry_error_markers(events: list[dict[str, Any]], stderr: bytes) -> list[str]:
    """Find CLI-visible retry/error indicators without claiming wire-level observability."""
    found: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        for key in ("type", "event", "event_type", "status"):
            value = event.get(key)
            if isinstance(value, str) and RETRY_ERROR_EVENT_MARKER.search(value):
                found.append(f"event:{key}")
        for key in ("message", "error", "detail", "reason"):
            value = event.get(key)
            if isinstance(value, str) and RETRY_ERROR_MARKER.search(value):
                found.append(f"event:{key}")
    if RETRY_ERROR_MARKER.search(stderr.decode("utf-8", errors="replace")):
        found.append("stderr")
    return found


def validate_retry_evidence(policy: str, route: str, events: list[dict[str, Any]], stderr: bytes,  # noqa: PLR0913
                            process_invocations: int, settings: dict[str, Any],
                            session: dict[str, Any], command: list[str]) -> list[str]:
    """Apply OBSERVED_NO_RETRY controls; this does not prove wire-level retry absence."""
    if policy != "OBSERVED_NO_RETRY":
        raise ValueError("retry evidence policy is not selected")
    markers = cli_retry_error_markers(events, stderr)
    if process_invocations != 1:
        raise ValueError("observed retry policy requires exactly one CLI process")
    if route == "qwen" and (settings.get("maxRetries") != 0 or session.get("requests") != 1 or
                            settings.get("model_fallbacks") != [] or
                            "--fallback-model" in command):
        raise ValueError("Qwen no-retry controls or request count are invalid")
    return markers


def _all_usage(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if isinstance(value.get("usage"), dict):
                found.append(value["usage"])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(events)
    return found


def usage_from_events(events: list[dict[str, Any]]) -> dict[str, int]:
    """Extract one explicit nonnegative provider input/output usage record."""
    found = _all_usage(events)
    if len(found) != 1:
        raise ValueError("expected exactly one provider usage object")
    raw = found[0]
    input_tokens = raw.get("input_tokens", raw.get("prompt_tokens"))
    output_tokens = raw.get("output_tokens", raw.get("completion_tokens"))
    if (not isinstance(input_tokens, int) or isinstance(input_tokens, bool) or input_tokens < 0
            or not isinstance(output_tokens, int) or isinstance(output_tokens, bool) or output_tokens < 0):
        raise ValueError("provider usage has invalid token counts")
    return {"input_tokens": input_tokens, "output_tokens": output_tokens}


def final_text(events: list[dict[str, Any]]) -> str:
    """Return the final assistant text from a supported CLI event stream."""
    values: list[str] = []
    for row in events:
        item = row.get("item")
        if row.get("type") == "item.completed" and isinstance(item, dict):
            if item.get("type") in {"agent_message", "assistant_message"} and isinstance(item.get("text"), str):
                values.append(item["text"])
        elif row.get("type") in {"result", "message", "assistant"}:
            text = row.get("content", row.get("text", row.get("result")))
            if isinstance(text, str):
                values.append(text)
    if not values or not values[-1].strip():
        raise ValueError("provider returned no final assistant text")
    return values[-1]


def validate_tsv(reply: str, opaque_id: str, element_ids: list[str]) -> None:
    """Require exact scorer columns, packet identity, and all expected elements."""
    lines = [line for line in reply.splitlines() if line.strip()]
    if not lines or lines[0].strip() != "run_id\telement\tverdict\treason":
        raise ValueError("scorer TSV header mismatch")
    rows: dict[str, list[str]] = {}
    for line in lines[1:]:
        columns = line.split("\t")
        if (len(columns) != TSV_COLUMN_COUNT or columns[0] != opaque_id or columns[2] not in {"PASS", "FAIL"}
                or not columns[3].strip()):
            raise ValueError("scorer TSV row is malformed")
        if columns[1] in rows:
            raise ValueError("scorer TSV contains a duplicate element")
        rows[columns[1]] = columns
    if set(rows) != set(element_ids):
        raise ValueError("scorer TSV element IDs do not match the packet")


def event_session_ids(events: list[dict[str, Any]]) -> set[str]:
    """Collect CLI session or thread identifiers from top-level events."""
    return {row[key] for row in events for key in ("thread_id", "session_id")
            if isinstance(row.get(key), str) and row[key]}


def codex_rollout(codex_home: Path, session_id: str) -> tuple[bytes, dict[str, Any]]:
    """Find and verify one persisted Codex session matching the CLI thread id."""
    matches: list[tuple[Path, list[dict[str, Any]]]] = []
    for path in (codex_home / "sessions").rglob("*.jsonl"):
        if path.is_symlink():
            continue
        try:
            rows = parse_jsonl(path.read_bytes())
            if any(row.get("type") == "session_meta" and
                   row.get("payload", {}).get("id") == session_id for row in rows):
                matches.append((path, rows))
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
            continue
    if len(matches) != 1:
        raise ValueError("Codex session correlation is not unique")
    path, rows = matches[0]
    sessions = [row.get("payload", {}) for row in rows if row.get("type") == "session_meta"]
    contexts = [row.get("payload", {}) for row in rows if row.get("type") == "turn_context"]
    if len(sessions) != 1 or len(contexts) != 1:
        raise ValueError("Codex session/context cardinality mismatch")
    session, context = sessions[0], contexts[0]
    if (session.get("id") != session_id or session.get("cli_version") != CODEX["version"]
            or context.get("model") != CODEX["model"] or context.get("effort") != CODEX["effort"]
            or tool_markers(rows)):
        raise ValueError("persisted Codex identity or tool evidence mismatch")
    return path.read_bytes(), {"session_id": session_id, "model_id": context["model"],
                               "effort": context["effort"], "cli_version": session["cli_version"],
                               "cwd": session.get("cwd"), "tool_markers": []}


def qwen_usage_record(path: Path, project: str, session_id: str, before_ids: set[str]) -> dict[str, Any]:
    """Find the single Qwen usage row matching a new session and project."""
    if not path.is_file() or path.is_symlink():
        raise ValueError("Qwen usage record is unavailable")
    found = []
    for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (isinstance(row, dict) and row.get("project") == project
                and row.get("sessionId") == session_id and session_id not in before_ids):
            found.append(row)
    if len(found) != 1:
        raise ValueError("Qwen usage record is not uniquely correlated")
    row = found[0]
    models = row.get("models")
    if not isinstance(models, dict) or set(models) != {QWEN["model"]}:
        raise ValueError("Qwen usage model identity mismatch")
    usage = models[QWEN["model"]]
    tokens_in, tokens_out = usage.get("inputTokens"), usage.get("outputTokens")
    if (usage.get("requests") != 1 or isinstance(tokens_in, bool) or not isinstance(tokens_in, int)
            or tokens_in < 0 or isinstance(tokens_out, bool) or not isinstance(tokens_out, int)
            or tokens_out < 0 or row.get("tools", {}).get("totalCalls") != 0):
        raise ValueError("Qwen request, token, or tool evidence is invalid")
    return {"session_id": session_id, "project": project, "model_id": QWEN["model"],
            "requests": 1, "input_tokens": tokens_in, "output_tokens": tokens_out,
            "tool_calls": 0}


def secure_capture(data: bytes, secret: str = "") -> bytes:
    """Redact common credential forms before persisting captured CLI output."""
    text = data.decode("utf-8", errors="replace")
    if secret:
        text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;\"']+", r"\1[REDACTED]", text)
    text = re.sub(r"https?://[^/@\s:]+:[^/@\s]+@", "https://[REDACTED]@", text)
    return text.encode("utf-8")


def _provider_entries(config: dict[str, Any], model_id: str) -> list[tuple[str, dict[str, Any]]]:
    providers = config.get("modelProviders", {})
    if not isinstance(providers, dict):
        return []
    return [(group, entry) for group, entries in providers.items() if isinstance(entries, list)
            for entry in entries if isinstance(entry, dict) and entry.get("id") == model_id]


def _provider_disables_thinking(config: dict[str, Any], model_id: str) -> bool:
    for _, entry in _provider_entries(config, model_id):
        generation = entry.get("generationConfig", {})
        extra_body = generation.get("extra_body", {}) if isinstance(generation, dict) else {}
        if isinstance(extra_body, dict) and extra_body.get("enable_thinking") is False:
            return True
    return False


def _qwen_preflight(home: Path, env: dict[str, str]) -> tuple[str, dict[str, Any], dict[str, Any]]:  # noqa: C901, PLR0912
    if env.get("QWEN_CODE_SYSTEM_SETTINGS_PATH") or Path("/etc/qwen-code/settings.json").exists():
        raise ValueError("existing Qwen system override prevents a controlled default-thinking route")
    defaults_path = Path(env.get("QWEN_CODE_SYSTEM_DEFAULTS_PATH", "/etc/qwen-code/system-defaults.json"))
    user_path = home / ".qwen/settings.json"
    user = json.loads(user_path.read_text(encoding="utf-8"))
    defaults = json.loads(defaults_path.read_text(encoding="utf-8")) if defaults_path.exists() else {}
    if user.get("security", {}).get("auth", {}).get("selectedType") != "openai":
        raise ValueError("Qwen authentication route is not the expected OpenAI-compatible provider")
    gateway = user.get("model", {}).get("baseUrl")
    if not isinstance(gateway, str) or not gateway.startswith("https://"):
        raise ValueError("secure Qwen gateway is missing")
    if not env.get("LITE_LLM_AUTH_TOKEN"):
        raise ValueError("Qwen credential is unavailable")
    for cfg in (user, defaults):
        fallback_models = cfg.get("modelFallbacks") if isinstance(cfg, dict) else None
        if fallback_models not in (None, "", []):
            raise ValueError("Qwen configured model fallbacks are not allowed")
        model = cfg.get("model", {}) if isinstance(cfg, dict) else {}
        generation = model.get("generationConfig", {}) if isinstance(model, dict) else {}
        sampling = generation.get("samplingParams", {}) if isinstance(generation, dict) else {}
        if isinstance(sampling, dict) and sampling.get("max_tokens") not in (None, OUTPUT_CAP["qwen"]):
            raise ValueError("Qwen existing output setting conflicts with 2000")
        if generation.get("enable_thinking") is False:
            raise ValueError("Qwen existing setting disables default thinking")
        if _provider_disables_thinking(cfg, QWEN["model"]):
            raise ValueError("Qwen existing provider setting disables default thinking")
    matches = _provider_entries(defaults, QWEN["model"])
    if len(matches) != 1 or matches[0][0] != "openai":
        raise ValueError("Qwen pinned model provider mapping is absent or ambiguous")
    source_entry = matches[0][1]
    source_generation = source_entry.get("generationConfig", {})
    if not isinstance(source_generation, dict):
        raise ValueError("Qwen provider generation configuration is malformed")
    generation = {
        "maxRetries": source_generation.get("maxRetries"),
        "samplingParams": source_generation.get("samplingParams", {}),
    }
    if not isinstance(generation, dict):
        raise ValueError("Qwen provider generation configuration is malformed")
    if generation.get("maxRetries") not in (None, 0):
        raise ValueError("Qwen provider retries are not disabled")
    generation["maxRetries"] = 0
    sampling = generation.setdefault("samplingParams", {})
    if not isinstance(sampling, dict) or sampling.get("max_tokens") not in (None, OUTPUT_CAP["qwen"]):
        raise ValueError("Qwen provider token setting conflicts with 2000")
    # Preserve the successful default-thinking canary's provider overlay shape.
    # Copy only non-secret identity fields and the explicit no-retry/output settings.
    entry = {key: source_entry[key] for key in ("id", "name", "envKey")
             if isinstance(source_entry.get(key), str)}
    entry["generationConfig"] = {
        "maxRetries": 0,
        "samplingParams": {"max_tokens": OUTPUT_CAP["qwen"]},
    }
    overlay = {"modelProviders": {"openai": [entry]}}
    meta = {"auth_type_matches": True, "gateway_secure": True, "credential_present": True,
            "provider_group": "openai", "maxRetries": 0, "max_tokens": OUTPUT_CAP["qwen"],
            "model_fallbacks": [],
            "thinking_override": "omitted; provider default retained"}
    return gateway, overlay, meta


def _model_settings(route: str) -> dict[str, Any]:
    if route == "codex":
        return CODEX
    if route == "qwen":
        return QWEN
    raise ValueError("unknown scorer route")


def _expected_version(route: str) -> str:
    return str(_model_settings(route)["version"] if route == "codex" else QWEN["version"])


def _version_matches(output: str, expected: str) -> bool:
    """Match an exact dotted version token, rejecting longer numeric versions."""
    return re.search(rf"(?<![A-Za-z0-9.+-])v?{re.escape(expected)}(?![A-Za-z0-9.+-])", output) is not None


def _child_environment(route: str, parent: dict[str, str], *, auth_token: str | None = None) -> dict[str, str]:
    """Build a small process environment without inheriting unrelated credentials."""
    allowed = {key: parent[key] for key in ("PATH", "LANG", "LC_ALL", "TERM", "NO_COLOR")
               if isinstance(parent.get(key), str)}
    allowed["HOME"] = str(Path.home())
    if route == "codex":
        codex_home = parent.get("CODEX_HOME")
        if codex_home:
            allowed["CODEX_HOME"] = codex_home
    elif route == "qwen":
        if auth_token:
            allowed["OPENAI_API_KEY"] = auth_token
    else:
        raise ValueError("unknown scorer route")
    return allowed


def _redacted_argv(route: str, executable: str, scratch: Path, session_id: str) -> list[str]:
    if route == "codex":
        return [executable, "exec", "--json", "--skip-git-repo-check", "--ignore-user-config",
                "--ignore-rules", "--disable", "memories", "--disable", "multi_agent",
                "-C", str(scratch), "-s", "read-only", "-m", CODEX["model"],
                "-c", 'model_reasoning_effort="medium"', "-c", 'web_search="disabled"', "-"]
    return [executable, "--safe-mode", "--approval-mode", "plan", "--advisor", "off",
            "--auth-type", "openai", "--openai-base-url", "[configured gateway omitted]",
            "--model", QWEN["model"], "--max-session-turns", "1", "--max-tool-calls", "0",
            "--session-id", session_id, "--input-format", "text", "--output-format", "stream-json",
            "Apply the scoring instructions and the single packet from stdin."]


def _codex_command(executable: str, scratch: Path) -> list[str]:
    return [executable, "exec", "--json", "--skip-git-repo-check", "--ignore-user-config",
            "--ignore-rules", "--disable", "memories", "--disable", "multi_agent",
            "-C", str(scratch), "-s", "read-only", "-m", CODEX["model"],
            "-c", 'model_reasoning_effort="medium"', "-c", 'web_search="disabled"', "-"]


def _qwen_command(executable: str, gateway: str, session_id: str) -> list[str]:
    return [executable, "--safe-mode", "--approval-mode", "plan", "--advisor", "off",
            "--auth-type", "openai", "--openai-base-url", gateway, "--model", QWEN["model"],
            "--max-session-turns", "1", "--max-tool-calls", "0", "--session-id", session_id,
            "--input-format", "text", "--output-format", "stream-json",
            "Apply the scoring instructions and the single packet from stdin."]


def invoke_one_provider_process(command: list[str], request: bytes, scratch: Path,
                                env: dict[str, str]) -> subprocess.CompletedProcess[bytes]:
    """Start exactly one provider CLI process; callers must never retry its result."""
    try:
        return subprocess.run(command, input=request, cwd=scratch, env=env,
                              capture_output=True, timeout=300, check=False)
    except OSError as exc:
        raise ProviderStartError from exc


def _request_id(attempt_id: str) -> str:
    return f"p3-route-check-{attempt_id}"


def _usage_artifact(path: Path, *, usage: dict[str, int], call_id: str, request_id: str,  # noqa: PLR0913
                    session_id: str, model_id: str, evidence: dict[str, Any]) -> dict[str, str]:
    saved = {"usage": usage, "request_id": request_id, "session_id": session_id,
             "model_id": model_id, "call_id": call_id, **evidence}
    raw = (json.dumps(saved, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    private_write(path, raw)
    return {"artifact_path": path.relative_to(LEDGER_PATH.parent).as_posix(),
            "artifact_sha256": sha(raw), "request_id": request_id,
            "session_id": session_id, "model_id": model_id, "call_id": call_id}


def terminalize_attempt(ledger: Any, attempt_id: str, *, outcome: str, actual_usage: Any,  # noqa: PLR0913
                        usage_artifact: Any, failure_code: str | None) -> dict[str, Any]:
    """Try intended completion, then fail closed with missing usage if validation fails."""
    try:
        return ledger.complete_attempt(attempt_id, outcome=outcome, actual_usage=actual_usage,
                                       usage_artifact=usage_artifact, failure_code=failure_code)
    except Exception:  # noqa: BLE001 - invalid evidence must not strand a reservation
        # If the first append succeeded but later validation raised, this second call
        # will reject the already-terminal attempt. Otherwise it records a failed,
        # unknown-usage outcome and blocks future dispatch.
        return ledger.complete_attempt(attempt_id, outcome="failed", actual_usage=None,
                                       usage_artifact=None, failure_code="missing_usage")


def _route_evidence_dir(attempt_id: str) -> Path:
    path = RUNS / "route-checks" / attempt_id
    path.parent.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
    if path.parent.is_symlink() or stat.S_IMODE(path.parent.stat().st_mode) != PRIVATE_DIR_MODE:
        raise ValueError("route evidence directory permissions are invalid")
    path.mkdir(mode=PRIVATE_DIR_MODE, exist_ok=False)
    return path


def _load_ledger() -> Any:
    spec = importlib.util.spec_from_file_location("a22_p3_usage_ledger", HERE / "usage_ledger_v2.py")
    if spec is None or spec.loader is None:
        raise SystemExit("route check blocked: shared ledger API unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_route_pair(route: str, packet_id: str, packet_hash: str, prompt_hash: str,
                      approval_hash: str) -> None:
    """Keep both route checks on one opaque packet and frozen prompt per approval."""
    other_route = "qwen" if route == "codex" else "codex"
    root = RUNS / "route-checks"
    if not root.exists():
        return
    if root.is_symlink() or not root.is_dir():
        raise ValueError("route-check evidence root is not a regular directory")
    for attempt_dir in root.iterdir():
        record_path = attempt_dir / "attempt.json"
        if attempt_dir.is_symlink() or record_path.is_symlink() or not record_path.is_file():
            continue
        try:
            prior = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("prior route-check evidence is unreadable") from exc
        if prior.get("approval_sha256") != approval_hash or prior.get("route") != other_route:
            continue
        if (prior.get("opaque_packet_id") != packet_id or prior.get("packet_sha256") != packet_hash
                or prior.get("prompt_sha256") != prompt_hash):
            raise ValueError("both scorer routes must receive the same sealed packet and prompt")


def dispatch(route: str, packet_dir: Path, evaluator_dir: Path) -> int:  # noqa: C901, PLR0912, PLR0915
    """Perform one scorer route check after the canonical ledger gate reserves it."""
    ledger_module = _load_ledger()
    process_invocations = 0
    retry_policy = "UNSELECTED"
    try:
        # Read-only canonical gate must run before even probing a provider CLI.
        ledger_module.require_dispatch_authorization(paths=ledger_module.DEFAULT_PATHS,
                                                     phase="route_check")
        retry_policy = ledger_module.approved_retry_evidence_policy(
            paths=ledger_module.DEFAULT_PATHS, phase="route_check")
        if retry_policy != "OBSERVED_NO_RETRY":
            raise ValueError("retry evidence policy is not selected")
        manifest, packet, prompt, element_ids = validate_bundle(packet_dir, evaluator_dir)
        request = make_request(prompt, packet)
        attempt_id = uuid.uuid4().hex
        approval_hash = sha((RUNS / "owner-approval-v2.json").read_bytes())
        _check_route_pair(route, manifest["opaque_packet_id"], sha(packet), sha(prompt), approval_hash)
        settings = _model_settings(route)
        executable = shutil.which(settings["executable"])
        if executable is None:
            raise ValueError("pinned scorer CLI is unavailable")
        probe_env = _child_environment(route, os.environ)
        version_result = subprocess.run([executable, "--version"], env=probe_env,
                                         capture_output=True, timeout=10, check=False)
        version_text = (version_result.stdout + version_result.stderr).decode("utf-8", errors="replace").strip()
        if version_result.returncode != 0 or not _version_matches(version_text, settings["version"]):
            raise ValueError("pinned scorer CLI version mismatch")
        scratch_root = Path(tempfile.gettempdir()) / "akmon-p3-route-check"
        scratch_root.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
        if scratch_root.is_symlink():
            raise ValueError("scratch root cannot be a symlink")
        scratch = scratch_root / attempt_id
        scratch.mkdir(mode=PRIVATE_DIR_MODE, exist_ok=False)
        parent_env = os.environ.copy()
        child_env = _child_environment(route, parent_env)
        secret = ""
        gateway: str | None = None
        settings_meta: dict[str, Any] = {}
        usage_path: Path | None = None
        before_ids: set[str] = set()
        session_id = str(uuid.uuid4()) if route == "qwen" else ""
        if route == "qwen":
            gateway, overlay, settings_meta = _qwen_preflight(Path.home(), parent_env)
            secret = parent_env["LITE_LLM_AUTH_TOKEN"]
            child_env = _child_environment(route, parent_env, auth_token=secret)
            settings_file = scratch_root / f"{attempt_id}.system-settings.json"
            private_write(settings_file, (json.dumps(overlay, sort_keys=True, indent=2) + "\n").encode())
            child_env["QWEN_CODE_SYSTEM_SETTINGS_PATH"] = str(settings_file)
            child_env["QWEN_CODE_MAX_OUTPUT_TOKENS"] = str(OUTPUT_CAP["qwen"])
            child_env["QWEN_CODE_UNATTENDED_RETRY"] = "0"
            usage_path = Path.home() / ".qwen/usage_record.jsonl"
            if usage_path.exists():
                for line in usage_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    try:
                        previous = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(previous, dict) and previous.get("project") == str(scratch):
                        before_ids.add(str(previous.get("sessionId")))
            command = _qwen_command(executable, gateway, session_id)
        else:
            command = _codex_command(executable, scratch)

        evidence_dir = _route_evidence_dir(attempt_id)
        run_record: dict[str, Any] = {
            "schema": 1, "record_type": "p3_scorer_route_check", "route": route,
            "status": "prepared", "attempt_id": attempt_id, "request_id": _request_id(attempt_id),
            "approval_sha256": approval_hash,
            "opaque_packet_id": manifest["opaque_packet_id"], "packet_sha256": sha(packet),
            "request_sha256": sha(request), "prompt_sha256": sha(prompt),
            "model_requested": settings["model"], "cli_version": version_text,
            "retry_evidence_policy": retry_policy,
            "output_limit": OUTPUT_CAP[route], "input_observed_limit": INPUT_CAP,
            "settings": settings_meta, "argv_redacted": _redacted_argv(route, executable, scratch, session_id),
            "provider_process_invocations_planned": 1, "retry_count": None,
            "retry_evidence": "provider retry count is not independently observable before dispatch",
            "scored_p3": False, "qualification_data": False,
        }
        write_json(evidence_dir / "prepared.json", run_record)
        # The ledger performs the current approval/epoch gate under its lock.
        # If it has no implemented authorization API, it must raise here.
        attempt_id_reserved = ledger_module.reserve_attempt(
            route, "route_check", paths=ledger_module.DEFAULT_PATHS, attempt_id=attempt_id,
        )
        run_record["status"] = "reserved"
        try:
            write_json(evidence_dir / "attempt.json", run_record)
        except OSError:
            terminalize_attempt(ledger_module, attempt_id_reserved, outcome="failed", actual_usage=None,
                                usage_artifact=None, failure_code="missing_usage")
            raise
        actual_usage = None
        artifact = None
        failure_code = "attempt_failed"
        outcome = "failed"
        final_status = "FAILED_CLOSED"
        session: dict[str, Any] = {}
        events: list[dict[str, Any]] = []
        retry_error_markers: list[str] = []
        reply = ""
        process_returncode = None
        stdout = b""
        stderr = b""
        try:
            process = invoke_one_provider_process(command, request, scratch, child_env)
            process_invocations = 1
            process_returncode = process.returncode
            stdout = secure_capture(process.stdout, secret)
            stderr = secure_capture(process.stderr, secret)
            private_write(evidence_dir / "stdout.raw", stdout)
            private_write(evidence_dir / "stderr.raw", stderr)
            events = parse_jsonl(stdout)
            write_json(evidence_dir / "events.json", events)
            if route == "codex":
                session_ids = {row["thread_id"] for row in events if isinstance(row.get("thread_id"), str)}
                if len(session_ids) != 1:
                    raise ValueError("Codex thread id is not uniquely correlated")
                session_id = next(iter(session_ids))
                actual_usage = usage_from_events(events)
                codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
                rollout, session = codex_rollout(codex_home, session_id)
                private_write(evidence_dir / "rollout.jsonl", secure_capture(rollout, secret))
                if session.get("cwd") != str(scratch):
                    raise ValueError("Codex persisted session cwd does not match isolated scratch")
                terminal_events = [row for row in events if row.get("type") == "turn.completed"]
                if len(terminal_events) != 1:
                    raise ValueError("Codex terminal turn cardinality is not one")
            else:
                if event_session_ids(events) != {session_id}:
                    raise ValueError("Qwen event session does not match the one-shot request")
                qwen = qwen_usage_record(usage_path, str(scratch), session_id, before_ids)
                actual_usage = {"input_tokens": qwen["input_tokens"], "output_tokens": qwen["output_tokens"]}
                session = {"session_id": session_id, "model_id": qwen["model_id"],
                           "requests": qwen["requests"], "tool_calls": qwen["tool_calls"]}
            reply = final_text(events)
            if process.returncode != 0:
                raise ValueError("scorer CLI exited unsuccessfully")
            markers = tool_markers(events)
            if markers:
                raise ValueError("tool activity was observed")
            retry_error_markers = validate_retry_evidence(
                retry_policy, route, events, stderr, process_invocations, settings_meta, session, command)
            if retry_error_markers:
                raise ValueError("CLI-visible retry or error marker was observed")
            validate_tsv(reply, manifest["opaque_packet_id"], element_ids)
            if actual_usage["input_tokens"] > INPUT_CAP or actual_usage["output_tokens"] > OUTPUT_CAP[route]:
                failure_code = "per_call_limit_breach"
                raise ValueError("observed provider usage exceeds route allowance")
            private_write(evidence_dir / "final.tsv", reply.encode("utf-8"))
            final_status = "ROUTE_MECHANICS_PASS_UNSCORED"
            outcome = "accepted"
            failure_code = None
        except subprocess.TimeoutExpired as exc:
            process_invocations = 1
            stdout = secure_capture(exc.stdout or b"", secret)
            stderr = secure_capture(exc.stderr or b"", secret)
            private_write(evidence_dir / "stdout.raw", stdout)
            private_write(evidence_dir / "stderr.raw", stderr)
            failure_code = "missing_usage"
            final_status = "FAILED_CLOSED_UNCERTAIN_PROVIDER_OUTCOME"
        except ProviderStartError as exc:
            run_record["failure_kind"] = type(exc).__name__
            run_record["failure_code"] = "missing_usage"
            failure_code = "missing_usage"
            final_status = "FAILED_CLOSED_PROCESS_START"
        except Exception as exc:  # noqa: BLE001 - terminalize provider outcomes without leaking exception text
            run_record["failure_kind"] = type(exc).__name__
            failure_code = failure_code or ("attempt_failed" if process_invocations == 0 else "missing_usage")
            run_record["failure_code"] = failure_code
            final_status = "FAILED_CLOSED"
        finally:
            correlation_ok = bool(actual_usage and session_id and settings.get("model")
                                  and session.get("model_id") == settings.get("model"))
            ledger_usage = actual_usage
            if actual_usage is not None and not correlation_ok:
                ledger_usage = None
                failure_code = "missing_usage"
                outcome = "failed"
                final_status = "FAILED_CLOSED_USAGE_UNCORRELATED"
            if actual_usage and correlation_ok:
                evidence = {
                    "opaque_packet_id": manifest["opaque_packet_id"],
                    "packet_sha256": sha(packet), "request_sha256": sha(request),
                    "request_id_provenance": "runner-generated; linked to exact stdin hash and one CLI process",
                    "retry_evidence_policy": retry_policy,
                    "process_returncode": process_returncode,
                    "provider_process_invocations": process_invocations,
                    "retry_count": None,
                    "retry_observed_markers": retry_error_markers if process_invocations else [],
                    "retry_evidence": (
                        "OBSERVED_NO_RETRY passed at the CLI/session layer; provider transport retries "
                        "are not observable"
                        if final_status == "ROUTE_MECHANICS_PASS_UNSCORED" else
                        "CLI/session retry evidence is incomplete or failed; provider transport retries "
                        "are not observable"
                    ),
                    "tool_markers": tool_markers(events), "session": session,
                    "tsv_sha256": sha(reply.encode("utf-8")) if reply else None,
                    "tsv_valid": bool(reply and final_status == "ROUTE_MECHANICS_PASS_UNSCORED"),
                    "tsv_row_count": len([line for line in reply.splitlines() if line.strip()]) - 1 if reply else 0,
                }
                usage_dir = RUNS / "usage-artifacts"
                try:
                    usage_dir.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
                    if stat.S_IMODE(usage_dir.stat().st_mode) != PRIVATE_DIR_MODE or usage_dir.is_symlink():
                        raise ValueError("usage artifact directory permissions are invalid")
                    artifact = _usage_artifact(usage_dir / f"{attempt_id_reserved}.json", usage=actual_usage,
                                               call_id=attempt_id_reserved,
                                               request_id=_request_id(attempt_id_reserved), session_id=session_id,
                                               model_id=settings["model"], evidence=evidence)
                except (OSError, ValueError):
                    ledger_usage = None
                    artifact = None
                    failure_code = "missing_usage"
                    outcome = "failed"
                    final_status = "FAILED_CLOSED_USAGE_ARTIFACT"
            if final_status != "ROUTE_MECHANICS_PASS_UNSCORED" and failure_code is None:
                failure_code = "attempt_failed"
            terminal = terminalize_attempt(
                ledger_module,
                attempt_id_reserved,
                outcome=outcome,
                actual_usage=ledger_usage,
                usage_artifact=artifact,
                failure_code=failure_code,
            )
            write_json(evidence_dir / "outcome.json", {
                "status": final_status, "ledger_outcome": terminal["outcome"],
                "attempt_id": attempt_id_reserved, "request_id": _request_id(attempt_id_reserved),
                "session_id": session_id or None, "model_id": settings["model"],
                "usage": ledger_usage, "observed_usage": actual_usage, "usage_artifact": artifact,
                "failure_code": failure_code, "failure_kind": run_record.get("failure_kind"),
                "process_returncode": process_returncode,
                "retry_evidence_policy": retry_policy,
                "tool_markers": tool_markers(events), "provider_process_invocations": process_invocations,
                "retry_count": None,
                "retry_evidence": (
                    "OBSERVED_NO_RETRY passed at the CLI/session layer; provider transport retries "
                    "are not observable"
                    if final_status == "ROUTE_MECHANICS_PASS_UNSCORED" else
                    "CLI/session retry evidence is incomplete or failed; provider transport retries "
                    "are not observable"
                ),
                "retry_observed_markers": retry_error_markers if process_invocations else [],
                "tsv_sha256": sha(reply.encode()) if reply else None,
                "tsv_valid": final_status == "ROUTE_MECHANICS_PASS_UNSCORED",
                "scored_p3": False, "qualification_data": False,
            })
            print(json.dumps({"status": final_status, "route": route,
                              "scored_p3": False, "qualification_data": False}))
        return 0 if final_status == "ROUTE_MECHANICS_PASS_UNSCORED" else 1  # noqa: TRY300
    except Exception as exc:  # noqa: BLE001 - fail closed without printing provider or packet details
        # Deliberately do not print exception text: it can include paths, packet data,
        # gateway details, or provider-controlled strings. No call occurs before reserve.
        print(json.dumps({"status": "DISPATCH_BLOCKED", "reason_class": type(exc).__name__,
                          "provider_process_invocations": process_invocations}))
        return 2


def main() -> int:
    """Parse one-shot route-check CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    check = sub.add_parser("dispatch", help="make one gated route-check call")
    check.add_argument("--route", choices=("codex", "qwen"), required=True)
    check.add_argument("--packet-dir", type=Path, required=True)
    check.add_argument("--evaluator-dir", type=Path, required=True)
    args = parser.parse_args()
    return dispatch(args.route, args.packet_dir, args.evaluator_dir)


if __name__ == "__main__":
    raise SystemExit(main())
