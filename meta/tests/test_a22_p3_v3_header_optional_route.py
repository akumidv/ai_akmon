"""Offline integrity checks for the two-packet header-optional route."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(HERE))

import v3_header_optional_route as route  # noqa: E402
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
        "record_type": "p3_v3_header_optional_route_plan",
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
