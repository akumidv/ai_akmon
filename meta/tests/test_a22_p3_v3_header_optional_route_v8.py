"""Offline integrity checks for the two-packet header-optional route."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "successors"))

import v3_header_optional_route_v8 as route  # noqa: E402
import v3_scorer_header_optional as parser  # noqa: E402


def test_both_sealed_packets_and_their_terminal_calls_are_distinct() -> None:
    first_prompt, first_packet = route.prompt_and_packet("prior_route")
    second_prompt, second_packet = route.prompt_and_packet("identity_bound")

    assert first_prompt == second_prompt
    assert first_packet != second_packet
    assert route.PACKETS["prior_route"]["id"] == "gf04a4422bf50dd1f"
    assert route.PACKETS["identity_bound"]["id"] == "g9dce84eeb2db2e39"
    assert route.PACKETS["prior_route"]["call_id"] != route.PACKETS["identity_bound"]["call_id"]


def test_four_call_plan_has_one_fresh_qwen_and_codex_call_per_packet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = ["g" + f"{index:032x}" for index in range(1, 5)]
    plan = {
        "record_type": "p3_v3_header_optional_route_v8_plan",
        "packet_sha256": {key: route.sha(source["root"] / "packet.md") for key, source in route.PACKETS.items()},
        "prompt_sha256": route.sha(route.qualification.packet.PROMPT),
        "calls": [
            {"packet_key": key, "route": model, "call_id": call_id}
            for (key, model), call_id in zip(
                [(key, model) for key in route.PACKET_KEYS for model in route.ROUTES], ids, strict=True
            )
        ],
    }
    path = tmp_path / "plan.json"
    route.write_json(path, plan)
    monkeypatch.setattr(route, "PLAN", path)

    assert route.plan() == plan
    assert [(call["packet_key"], call["route"]) for call in route.plan()["calls"]] == [
        ("prior_route", "qwen"),
        ("prior_route", "codex"),
        ("identity_bound", "qwen"),
        ("identity_bound", "codex"),
    ]


def test_normalized_reply_round_trips_to_packet_bound_canonical_bytes() -> None:
    raw = (
        "\nE1\tPASS\tObservation one.\nE2\tFAIL\tObservation two.\n"
        "E3\tPASS\tObservation three.\nE4\tPASS\tObservation four.\n"
    )
    packet_id = route.PACKETS["identity_bound"]["id"]

    canonical, kind = parser.canonicalize(raw, packet_id, route.ELEMENTS)
    normalized = route._normalized_from_canonical(canonical, packet_id)
    reconstructed, reconstructed_kind = parser.canonicalize(normalized, packet_id, route.ELEMENTS)

    assert kind == "inserted_header"
    assert reconstructed_kind == "exact_header"
    assert normalized.startswith(parser.RAW_HEADER + "\n")
    assert reconstructed == canonical
    assert canonical.splitlines()[1].startswith(packet_id + "\tE1\tPASS\t")


def test_replay_normalized_bytes_reject_tampering() -> None:
    canonical, _ = parser.canonicalize(
        "E1\tPASS\tOne.\nE2\tPASS\tTwo.\nE3\tPASS\tThree.\nE4\tPASS\tFour.\n",
        route.PACKETS["prior_route"]["id"],
        route.ELEMENTS,
    )
    normalized = route._normalized_from_canonical(canonical, route.PACKETS["prior_route"]["id"]).encode()

    assert route._normalized_bytes_match(normalized, canonical, route.PACKETS["prior_route"]["id"])
    assert not route._normalized_bytes_match(
        normalized.replace(b"One.", b"Changed."), canonical, route.PACKETS["prior_route"]["id"]
    )


def test_qwen_effective_settings_hash_rejects_overlay_tampering(monkeypatch: pytest.MonkeyPatch) -> None:
    original = (
        "https://gateway.example/v1",
        {
            "modelProviders": {
                "openai": [{"generationConfig": {"maxRetries": 0, "samplingParams": {"max_tokens": 5000}}}]
            }
        },
        {"thinking_override": "omitted; provider default retained", "maxRetries": 0, "max_tokens": 5000},
    )
    monkeypatch.setattr(route.qwen_route, "qwen_settings", lambda: original)
    _, _, _, sealed = route.qwen_effective_settings()
    assert sealed["dispatch_environment"]["QWEN_CODE_MAX_OUTPUT_TOKENS"] == "5000"
    assert sealed["dispatch_environment"]["QWEN_CODE_UNATTENDED_RETRY"] == "0"
    assert sealed["dispatch_environment"]["QWEN_CODE_SYSTEM_SETTINGS_PATH"] == "<call-root>/qwen-settings.json"

    altered_overlay = {
        "modelProviders": {"openai": [{"generationConfig": {"maxRetries": 0, "samplingParams": {"max_tokens": 4000}}}]}
    }
    monkeypatch.setattr(route.qwen_route, "qwen_settings", lambda: (original[0], altered_overlay, original[2]))

    with pytest.raises(route.RouteError, match="effective Qwen settings"):
        route.verify_qwen_effective_settings(sealed)

    monkeypatch.setattr(route.qwen_route, "qwen_settings", lambda: original)
    monkeypatch.setattr(route, "QWEN_OUTPUT_CAP", 4000)
    with pytest.raises(route.RouteError, match="effective Qwen settings"):
        route.verify_qwen_effective_settings(sealed)


def test_codex_reservation_includes_observed_prior_call_usage() -> None:
    prior = route.OPENING + 21_000

    assert route.codex_reserved_upper_bound(prior) == prior + 21_000
    with pytest.raises(route.RouteError, match="aggregate ceiling"):
        route.codex_reserved_upper_bound(route.LIMIT - 20_999)


def test_owner_approval_template_cannot_authorize_dispatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(route, "SEAL", tmp_path / "seal.json")
    monkeypatch.setattr(route, "PREFLIGHT", tmp_path / "preflight.json")
    monkeypatch.setattr(route, "APPROVAL", tmp_path / "approval.json")
    route.write_json(route.SEAL, {"candidate": True})
    route.write_json(route.PREFLIGHT, {"dispatch_allowed": False})
    route.write_json(route.APPROVAL, route.approval_template())

    with pytest.raises(route.RouteError, match="approval"):
        route.verify_approval(dispatch=True)


def test_qwen_cli_version_insertion_is_allowed_but_settings_changes_are_not() -> None:
    base = {"modelProviders": {"openai": [{"id": "qwen3.8-27b", "generationConfig": {"maxRetries": 0}}]}}
    after = {**base, "$version": 4}

    assert route._allowed_qwen_cli_mutation(base, after)
    assert not route._allowed_qwen_cli_mutation(base, {**base, "$version": True})
    assert not route._allowed_qwen_cli_mutation(base, {"$version": 4, **base, "other": "changed"})
    assert not route._allowed_qwen_cli_mutation(base, {"modelProviders": {}, "$version": 4})


def test_v5_terminal_binding_includes_observed_mutated_settings() -> None:
    binding = route._v5_terminal_binding()
    assert binding["settings_after_cli"] == route.sha(route.V5_SETTINGS)
    assert binding["outcome"] == route.sha(route.V5_RUNTIME / route.V5_CALL_ID / "outcome.json")


def _copy_v5_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    runtime = tmp_path / "runtime"
    runs = tmp_path / "runs"
    shutil.copytree(route.V5_RUNTIME / route.V5_CALL_ID, runtime / route.V5_CALL_ID)
    shutil.copy2(route.V5_RUNTIME / "route-events.jsonl", runtime / "route-events.jsonl")
    runs.mkdir()
    for name in (
        "seal-v5.json",
        "approval-v5.json",
        "live-preflight-v5.json",
        "plan-v5.json",
    ):
        source_name = name.replace("-v5", "-v5")
        source = route.V5_RUNS / f"v3-header-optional-route-{source_name}"
        # Keep names explicit and preserve each predecessor artifact byte for byte.
        if name.startswith("seal"):
            source = route.V5_RUNS / "v3-header-optional-route-seal-v5.json"
        elif name.startswith("approval"):
            source = route.V5_RUNS / "v3-header-optional-route-approval-v5.json"
        elif name.startswith("live-preflight"):
            source = route.V5_RUNS / "v3-header-optional-route-live-preflight-v5.json"
        else:
            source = route.V5_RUNS / "v3-header-optional-route-plan-v5.json"
        shutil.copy2(source, runs / source.name)
    monkeypatch.setattr(route, "V5_RUNTIME", runtime)
    monkeypatch.setattr(route, "V5_RUNS", runs)
    return runtime, runs


def test_v5_terminal_relations_reject_ledger_status_tampering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _ = _copy_v5_terminal(tmp_path, monkeypatch)
    ledger = runtime / "route-events.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    rows[-1]["status"] = "failed"
    ledger.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))

    with pytest.raises(route.RouteError, match="V5 terminal evidence linkage"):
        route._v5_terminal_binding()


def test_v5_terminal_relations_reject_settings_and_outcome_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, _ = _copy_v5_terminal(tmp_path, monkeypatch)
    settings = runtime / route.V5_CALL_ID / "qwen-settings.json"
    value = json.loads(settings.read_text())
    value["modelProviders"]["openai"][0]["id"] = "tampered-model"
    settings.write_text(json.dumps(value))

    with pytest.raises(route.RouteError, match="V5 terminal evidence linkage"):
        route._v5_terminal_binding()


def test_v5_seal_rejects_source_map_and_plan_hash_tampering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, runs = _copy_v5_terminal(tmp_path, monkeypatch)
    seal_path = runs / "v3-header-optional-route-seal-v5.json"
    plan_path = runs / "v3-header-optional-route-plan-v5.json"
    seal = json.loads(seal_path.read_text())
    assert route._v5_source_and_plan_match(seal, plan_path)

    altered = json.loads(json.dumps(seal))
    altered["source_sha256"]["v3_runner.py"] = "0" * 64
    assert not route._v5_source_and_plan_match(altered, plan_path)
    altered = json.loads(json.dumps(seal))
    altered["plan_sha256"] = "0" * 64
    assert not route._v5_source_and_plan_match(altered, plan_path)


def test_v5_approval_rejects_operator_or_acceptance_basis_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, runs = _copy_v5_terminal(tmp_path, monkeypatch)
    approval_path = runs / "v3-header-optional-route-approval-v5.json"
    seal_path = runs / "v3-header-optional-route-seal-v5.json"
    preflight_path = runs / "v3-header-optional-route-live-preflight-v5.json"
    approval = json.loads(approval_path.read_text())
    assert route._v5_approval_matches(approval, seal_path, preflight_path)

    altered = dict(approval, named_stop_operator="unknown")
    assert not route._v5_approval_matches(altered, seal_path, preflight_path)
    altered = dict(approval, acceptance_basis="different authorization")
    assert not route._v5_approval_matches(altered, seal_path, preflight_path)
