"""Unit tests for the second-opinion diversity ladder (``tools/model_routing/routing.py``).

Covers ``second_opinion_command`` model-flag insertion and ``resolve_second_opinion``'s
walk of ``second_opinion_policy.diversity_ladder`` (design §9.3/§9.7 #2). Registries and
configs here are minimal in-memory dicts, independent of the real ``registry.json``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_AKMON = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_ROUTING_DIR = _AKMON / "tools" / "model_routing"
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


def test_second_opinion_command_with_model_but_no_model_flag_fails_loudly():
    """C97: a pin the vendor cannot apply is an error, not a silently unpinned run."""
    spec = {"harness": "codex", "operation": "review"}
    with pytest.raises(routing.UnpinnableModelError, match="declares no model_flag"):
        routing.second_opinion_command(spec, "review this", model="o3")


def test_every_routed_vendor_declares_its_measured_model_flag():
    registry = routing.load_registry(Path(__file__).resolve().parents[2])
    for vendor in routing.vendors_with_routing_policy(registry):
        spec = routing.second_opinion_spec(registry, vendor)
        assert routing.second_opinion_command(spec, "p", model="m")[-3:] == ["--model", "m", "p"], vendor


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


# --------------------------------------------------------------------------------------
# ADR 0024: one ladder over providers, diversity tested on priors (D05, D06, D08, D11, D12)
# --------------------------------------------------------------------------------------

_SO_DIR = ".akmon/second-opinion/"

_PRIORS_REGISTRY = {
    "providers": {
        "claude": {
            "carrier": "harness",
            "operation": "review",
            "model_flag": "--model {model}",
            "family": "claude",
            "report_dir": _SO_DIR,
        },
        "codex": {
            "carrier": "harness",
            "operation": "review",
            "model_flag": "--model {model}",
            "family": "gpt",
            "report_dir": _SO_DIR,
        },
        "qwen": {
            "carrier": "harness",
            "operation": "review",
            "model_flag": "-m {model}",
            "family": "qwen",
            "report_dir": _SO_DIR,
        },
        # Another carrier, the same mind: D06 exists to catch this one.
        "homi": {
            "carrier": "harness",
            "operation": "review",
            "model_flag": "--model {model}",
            "family": "claude",
            "report_dir": _SO_DIR,
        },
        # A carrier nobody declared priors for: fail closed (D08, D11).
        "sphinx": {"carrier": "harness", "operation": "review", "report_dir": _SO_DIR},
        # A carrier its owner declared outright (D12): a command list, the pack on stdin.
        "myqwen": {"argv": ["myqwen", "-m", "{model}"], "prompt": "stdin", "family": "qwen", "report_dir": _SO_DIR},
        # A declared carrier that cannot take a pin, because its argv has no placeholder.
        "nomodel": {"argv": ["nomodel", "run"], "family": "gpt", "report_dir": _SO_DIR},
    },
    "second_opinion_policy": {
        "ladder": ["claude", "codex", "qwen", "homi", "sphinx", "myqwen", "nomodel"],
        "never": "silently-same-model",
    },
}

_ALL_PRESENT = ("claude", "codex", "qwen", "homi", "sphinx", "myqwen", "nomodel")


@pytest.fixture
def all_present(monkeypatch):
    """Presence is a host fact the test supplies; nothing here reads `PATH` (ADR 0024/D11)."""
    monkeypatch.setattr(routing, "carrier_present", lambda registry, provider: provider in _ALL_PRESENT)


def _session(provider, family, model=None):
    return routing.SecondOpinionSession(provider=provider, family=family, model=model)


def test_ladder_walk_skips_the_session_carrier(all_present):
    target = routing.resolve_opinion_chain(_PRIORS_REGISTRY, _session("claude", "claude"), rank=2)
    assert target == routing.SecondOpinionTarget("codex", None, "gpt")


def test_ladder_walk_is_relative_to_the_session_not_absolute(all_present):
    """The top of the ladder is reachable for everyone but itself — no per-carrier second choice."""
    target = routing.resolve_opinion_chain(_PRIORS_REGISTRY, _session("codex", "gpt"), rank=2)
    assert target == routing.SecondOpinionTarget("claude", None, "claude")


def test_same_priors_behind_another_carrier_is_skipped(all_present):
    """`homi` is a different harness and still the same mind, so it buys nothing (D06)."""
    session = _session("claude", "claude")
    assert routing.resolve_opinion_chain(_PRIORS_REGISTRY, session, rank=3) == routing.SecondOpinionTarget(
        "qwen", None, "qwen"
    )
    skips = routing.opinion_skips(_PRIORS_REGISTRY, session)
    assert ("claude", "self") in skips
    assert ("homi", "same priors as claude") in skips


def test_a_model_the_session_already_answers_with_is_skipped(all_present):
    """D06's second half: another harness answering with the same model is not another mind.
    A family nobody else carries keeps the skip on the model alone."""
    registry = {
        "providers": {
            "claude": {"argv": ["claude"], "family": "claude", "report_dir": _SO_DIR},
            "qwen": {"argv": ["qwen", "-m", "{model}"], "family": "qwen", "report_dir": _SO_DIR},
        },
        "second_opinion_policy": {"ladder": ["claude", "qwen:opus"]},
    }
    session = _session("claude", "claude", model="opus")
    assert routing.resolve_opinion_chain(registry, session, rank=2) is None
    assert routing.opinion_skips(registry, session) == (("claude", "self"), ("qwen", "same model as claude"))


def test_a_provider_without_declared_priors_is_skipped(all_present):
    """Nothing was read from the host to fill this in, and guessing would be the old defect.
    Two `qwen`-family providers are one mind, so the chain stops at two and rank 4 is past it."""
    session = _session("claude", "claude")
    assert ("sphinx", "priors unknown") in routing.opinion_skips(_PRIORS_REGISTRY, session)
    assert routing.resolve_opinion_chain(_PRIORS_REGISTRY, session, rank=3) == routing.SecondOpinionTarget(
        "qwen", None, "qwen"
    )
    assert routing.resolve_opinion_chain(_PRIORS_REGISTRY, session, rank=4) is None


def test_an_absent_carrier_is_skipped_with_that_reason(monkeypatch):
    monkeypatch.setattr(routing, "carrier_present", lambda registry, provider: provider in ("claude", "qwen"))
    session = _session("claude", "claude")
    assert routing.resolve_opinion_chain(_PRIORS_REGISTRY, session, rank=2) == routing.SecondOpinionTarget(
        "qwen", None, "qwen"
    )
    assert ("codex", "carrier absent") in routing.opinion_skips(_PRIORS_REGISTRY, session)


def test_a_ladder_id_outside_the_table_is_a_named_error(all_present):
    registry = {
        "providers": _PRIORS_REGISTRY["providers"],
        "second_opinion_policy": {"ladder": ["claude", "ghost"]},
    }
    with pytest.raises(KeyError, match="ghost"):
        routing.resolve_opinion_chain(registry, _session("claude", "claude"), rank=2)


def test_an_exhausted_chain_yields_nothing_for_the_caller_to_dress_up(all_present):
    """Rank past the chain is `None`; the last resort (D07) is the caller's disclosed step."""
    assert routing.resolve_opinion_chain(_PRIORS_REGISTRY, _session("claude", "claude"), rank=9) is None


def test_declared_carrier_builds_its_own_argv_with_the_pin(all_present):
    assert routing.opinion_command(_PRIORS_REGISTRY, "myqwen", model="qwen3.8-flash") == [
        "myqwen",
        "-m",
        "qwen3.8-flash",
    ]


def test_declared_carrier_without_a_placeholder_refuses_a_pin(all_present):
    """The C97 guarantee, kept for a carrier akmon never measured: no silent unpinned run."""
    with pytest.raises(routing.UnpinnableModelError, match="declares no model"):
        routing.opinion_command(_PRIORS_REGISTRY, "nomodel", model="gpt-x")


def test_declared_carrier_reports_repo_as_unknown_unless_stated(all_present):
    """Repository access is derived for a harness and never invented for a declaration."""
    assert routing.opinion_repo(_PRIORS_REGISTRY, "myqwen") == "unknown"
    assert routing.opinion_repo(_PRIORS_REGISTRY, "claude") == "worktree"


def test_shipped_carrier_still_routes_through_the_command_map(all_present):
    argv = routing.opinion_command(_PRIORS_REGISTRY, "claude", model="opus", prompt="review this")
    assert argv == ["claude", "-p", "--output-format", "text", "--model", "opus", "review this"]


# --------------------------------------------------------------------------------------
# ADR 0024/D14: the model inside a provider is chosen by the second opinion's own rule
# --------------------------------------------------------------------------------------

_RULE_REGISTRY = {
    # A vendor block whose rungs deliberately match no provider's declared list: if the reviewer's
    # model came from the tier binding, the assertions below would fail.
    "anthropic": {"selection_policy": {"worker": "lowest"}, "harness_rungs": ["tiny", "small"]},
    "providers": {
        "claude": {
            "argv": ["claude", "--model", "{model}"],
            "family": "claude",
            "models": ["haiku", "sonnet", "opus"],
            "report_dir": _SO_DIR,
        },
        "codex": {
            "argv": ["codex", "-m", "{model}"],
            "family": "gpt",
            "models": ["luna", "terra", "sol"],
            "report_dir": _SO_DIR,
        },
        "nodefault": {"argv": ["nodefault"], "family": "gemini", "report_dir": _SO_DIR},
    },
    "second_opinion_policy": {"ladder": ["claude", "codex", "nodefault"], "model_rule": "max"},
}


def test_the_second_opinion_takes_the_strongest_declared_model(all_present):
    session = _session("qwen", "qwen")
    assert routing.resolve_opinion_chain(_RULE_REGISTRY, session, rank=2) == routing.SecondOpinionTarget(
        "claude", "opus", "claude"
    )
    assert routing.resolve_opinion_chain(_RULE_REGISTRY, session, rank=3) == routing.SecondOpinionTarget(
        "codex", "sol", "gpt"
    )


def test_a_provider_declaring_no_models_yields_the_carrier_default(all_present):
    session = _session("qwen", "qwen")
    assert routing.resolve_opinion_chain(_RULE_REGISTRY, session, rank=4) == routing.SecondOpinionTarget(
        "nodefault", None, "gemini"
    )


def test_the_model_rule_reads_the_provider_table_never_the_bindings_rungs(all_present):
    """D14's separation: `anthropic.harness_rungs` says tiny/small, and that is not this answer."""
    assert routing.opinion_model(_RULE_REGISTRY, "claude") == "opus"


def test_an_unimplemented_model_rule_is_refused_not_guessed(all_present):
    registry = dict(_RULE_REGISTRY, second_opinion_policy={"ladder": ["claude"], "model_rule": "median"})
    with pytest.raises(ValueError, match="model_rule"):
        routing.opinion_model(registry, "claude")


def test_two_providers_answering_with_the_same_model_are_not_two_minds(monkeypatch):
    """D06 and D14 together: the model the rule picks is what must differ, not only the family."""
    monkeypatch.setattr(routing, "carrier_present", lambda registry, provider: True)
    registry = {
        "providers": {
            "alpha": {"argv": ["alpha"], "family": "claude", "models": ["shared"], "report_dir": _SO_DIR},
            "beta": {"argv": ["beta"], "family": "gpt", "models": ["shared"], "report_dir": _SO_DIR},
        },
        "second_opinion_policy": {"ladder": ["alpha", "beta"]},
    }
    session = _session("gamma", "qwen")
    assert routing.resolve_opinion_chain(registry, session, rank=2) == routing.SecondOpinionTarget(
        "alpha", "shared", "claude"
    )
    assert routing.resolve_opinion_chain(registry, session, rank=3) is None
    assert ("beta", "same model as alpha") in routing.opinion_skips(registry, session)
