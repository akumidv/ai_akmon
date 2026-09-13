"""Unit tests for the second-opinion diversity ladder (``tools/model_routing/routing.py``).

Covers ``second_opinion_command`` model-flag insertion and ``resolve_second_opinion``'s
walk of ``second_opinion_policy.diversity_ladder`` (design §9.3/§9.7 #2). Registries and
configs here are minimal in-memory dicts, independent of the real ``registry.json``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_KEYSTONE = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_ROUTING_DIR = _KEYSTONE / "tools" / "model_routing"
if str(_ROUTING_DIR) not in sys.path:
    sys.path.insert(0, str(_ROUTING_DIR))

import routing  # noqa: E402

# --------------------------------------------------------------------------------------
# second_opinion_command
# --------------------------------------------------------------------------------------


def test_second_opinion_command_without_model_is_unchanged():
    spec = {"harness": "claude", "operation": "review", "model_flag": "--model {model}"}
    assert routing.second_opinion_command(spec, "review this") == [
        "claude",
        "-p",
        "--output-format",
        "text",
        "review this",
    ]


def test_second_opinion_command_with_model_inserts_flag_before_prompt():
    spec = {"harness": "claude", "operation": "review", "model_flag": "--model {model}"}
    assert routing.second_opinion_command(spec, "review this", model="opus") == [
        "claude",
        "-p",
        "--output-format",
        "text",
        "--model",
        "opus",
        "review this",
    ]


def test_second_opinion_command_with_model_but_no_model_flag_omits_it():
    spec = {"harness": "codex", "operation": "review"}
    assert routing.second_opinion_command(spec, "review this", model="o3") == [
        "codex",
        "exec",
        "review this",
    ]


# --------------------------------------------------------------------------------------
# resolve_second_opinion
# --------------------------------------------------------------------------------------

_TWO_VENDOR_REGISTRY = {
    "anthropic": {
        "selection_policy": {},
        "second_opinion": {"harness": "codex", "operation": "review", "report_dir": ".claude/second-opinion"},
    },
    "openai": {
        "selection_policy": {},
        "second_opinion": {
            "harness": "claude",
            "operation": "review",
            "report_dir": ".claude/second-opinion",
        },
    },
    "second_opinion_policy": {"diversity_ladder": ["other-vendor", "same-vendor-other-model"]},
}

_ONE_VENDOR_REGISTRY = {
    "anthropic": {
        "selection_policy": {},
        "second_opinion": {"harness": "codex", "operation": "review", "report_dir": ".claude/second-opinion"},
    },
    "second_opinion_policy": {"diversity_ladder": ["other-vendor", "same-vendor-other-model"]},
}


def test_resolve_second_opinion_two_vendors_picks_other_vendor():
    config = {"orchestrator": "large", "binding": {"auditor": "large"}}
    target = routing.resolve_second_opinion(_TWO_VENDOR_REGISTRY, config, "anthropic")
    assert target == routing.SecondOpinionTarget("openai", None)


def test_resolve_second_opinion_single_vendor_uses_configured_fallback_model():
    config = {
        "orchestrator": "large",
        "binding": {"auditor": "large"},
        "second_opinion_fallback_model": "medium",
    }
    target = routing.resolve_second_opinion(_ONE_VENDOR_REGISTRY, config, "anthropic")
    assert target == routing.SecondOpinionTarget("anthropic", "medium")


def test_resolve_second_opinion_single_vendor_no_distinct_rung_skips():
    # orchestrator == auditor == the only available rung — no rung differs from both,
    # so second_opinion_fallback_model returns None and the caller must skip, never
    # falling back to the same model.
    config = {
        "orchestrator": "only",
        "binding": {"auditor": "only"},
        "available": ["only"],
    }
    assert routing.resolve_second_opinion(_ONE_VENDOR_REGISTRY, config, "anthropic") is None


def test_unavailability_names_the_single_vendor_cause_and_the_rungs_it_had():
    """`resolve_second_opinion` returns a bare None; the owner needs the population it saw."""
    config = {"orchestrator": "only", "binding": {"auditor": "only"}, "available": ["only"]}
    reason = routing.second_opinion_unavailability(_ONE_VENDOR_REGISTRY, config, "anthropic")
    assert "no other vendor is configured" in reason
    assert "['only']" in reason
    assert "orchestrator 'only'" in reason and "auditor 'only'" in reason


def test_unavailability_never_claims_a_verdict_it_did_not_derive():
    """A shortened ladder empties itself without any rung being unusable. Saying "no rung
    differs" there would be a confident false statement about a step never attempted."""
    registry = dict(_ONE_VENDOR_REGISTRY, second_opinion_policy={"diversity_ladder": ["other-vendor"]})
    config = {"orchestrator": "opus", "binding": {"auditor": "opus"}, "available": ["haiku", "opus"]}

    assert routing.resolve_second_opinion(registry, config, "anthropic") is None
    reason = routing.second_opinion_unavailability(registry, config, "anthropic")
    assert "not attempted, it is absent from the configured ladder" in reason
    assert "hold none that differs" not in reason


def test_unavailability_names_the_pin_when_another_vendor_was_available():
    """A same-vendor pin skips the other-vendor step by design — the owner must see that it
    was their own pin, not a missing installation, that emptied the ladder."""
    config = {
        "orchestrator": "large",
        "binding": {"auditor": "large"},
        "available": ["large"],
        "second_opinion_provider": "anthropic",
    }
    reason = routing.second_opinion_unavailability(_TWO_VENDOR_REGISTRY, config, "anthropic")
    assert "second_opinion_provider pins 'anthropic'" in reason
    assert "openai" in reason


def test_resolve_second_opinion_configured_provider_equals_orchestrator_stays_same_vendor():
    # Even though "openai" is configured elsewhere in the registry, an explicit
    # second_opinion_provider matching the orchestrator vendor routes to the
    # same-vendor branch instead of silently picking the other vendor.
    config = {
        "orchestrator": "large",
        "binding": {"auditor": "large"},
        "second_opinion_provider": "anthropic",
        "second_opinion_fallback_model": "medium",
    }
    target = routing.resolve_second_opinion(_TWO_VENDOR_REGISTRY, config, "anthropic")
    assert target == routing.SecondOpinionTarget("anthropic", "medium")
