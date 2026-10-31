"""Unit tests for the second-opinion provider ladder (``tools/model_routing/routing.py``).

Covers the command builder (``opinion_command``: shipped carrier through the command map, a
declared one through its own argv), the priors walk (``resolve_opinion_chain``, ADR 0024 D05-D08),
the family a carrier answers with (``provider_family``), the session's identity
(``resolve_session``), the disclosed last resort and the retired keys. Registries and configs here
are minimal in-memory dicts, independent of the real ``registry.json`` except where a test says it
reads the shipped one.
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
# opinion_command: the argv of one provider, the command map owning executable and operation
# --------------------------------------------------------------------------------------

_SHIPPED = routing.load_registry(_AKMON)


@pytest.fixture
def project(tmp_path):
    """A minimal project whose dev root is the default `_aitna` (no `.aitna-root` declaration)."""
    (tmp_path / "AGENTS.md").write_text("# project\n", encoding="utf-8")
    (tmp_path / "_aitna").mkdir()
    return tmp_path


def test_opinion_command_without_model_is_the_map_prefix_and_the_prompt(project):
    registry = {"providers": {"claude": {"operation": "review", "model_flag": "--model {model}"}}}
    assert routing.opinion_command(registry, "claude", project, routing.OpinionRun(prompt="review this")) == [
        "claude",
        "-p",
        "--output-format",
        "text",
        "review this",
    ]


def test_opinion_command_with_model_inserts_the_flag_before_the_prompt(project):
    registry = {"providers": {"claude": {"operation": "review", "model_flag": "--model {model}"}}}
    assert routing.opinion_command(
        registry, "claude", project, routing.OpinionRun(model="opus", prompt="review this")
    ) == [
        "claude",
        "-p",
        "--output-format",
        "text",
        "--model",
        "opus",
        "review this",
    ]


def test_opinion_command_with_a_model_id_holding_slash_and_colon_keeps_it_one_argument(project):
    registry = {"providers": {"opencode": {"operation": "review", "model_flag": "-m {model}"}}}
    assert routing.opinion_command(
        registry, "opencode", project, routing.OpinionRun(model="anthropic/claude-sonnet-4:beta", prompt="p")
    ) == [
        "opencode",
        "run",
        "--agent",
        "plan",
        "-m",
        "anthropic/claude-sonnet-4:beta",
        "p",
    ]


def test_opinion_command_with_model_but_no_model_flag_fails_loudly(project):
    """C97: a pin the provider cannot apply is an error, not a silently unpinned run."""
    registry = {"providers": {"codex": {"operation": "review"}}}
    with pytest.raises(routing.UnpinnableModelError, match="declares no model_flag"):
        routing.opinion_command(registry, "codex", project, routing.OpinionRun(model="o3", prompt="review this"))


def test_every_shipped_provider_declares_a_flag_that_pins_a_model_before_the_prompt(project):
    for provider in routing.providers(_SHIPPED):
        argv = routing.opinion_command(_SHIPPED, provider, project, routing.OpinionRun(model="m", prompt="p"))
        # A stdin row (qwen) carries no prompt argument: the model is then last.
        pinned = argv[:-1] if _SHIPPED["providers"][provider].get("prompt") != "stdin" else argv
        assert pinned[-1] == "m", provider
        assert pinned[-2].startswith("-"), provider
        assert (argv[-1] == "p") == (_SHIPPED["providers"][provider].get("prompt") != "stdin"), provider


def test_every_shipped_ladder_entry_names_a_row_and_a_command_map_harness():
    from common.runtime import harness_commands

    for entry in routing.opinion_ladder(_SHIPPED):
        provider, _ = routing.split_opinion_entry(entry)
        assert provider in routing.providers(_SHIPPED), entry
        assert provider in harness_commands(), entry


def test_each_shipped_provider_has_its_own_report_directory():
    """C163: the directory follows the carrier — the swapped vendor values are gone."""
    dirs = {provider: row["report_dir"] for provider, row in routing.providers(_SHIPPED).items()}
    assert dirs == {
        "claude": ".claude/second-opinion/",
        "codex": ".codex/second-opinion/",
        "qwen": ".qwen/second-opinion/",
        "opencode": ".opencode/second-opinion/",
        "pi": ".pi/second-opinion/",
    }


def test_the_vendor_blocks_keep_orchestration_only_and_name_their_carrier():
    assert _SHIPPED["anthropic"]["carrier"] == "claude"
    assert _SHIPPED["openai"]["carrier"] == "codex"
    assert "second_opinion" not in _SHIPPED["anthropic"]
    assert "diversity_ladder" not in _SHIPPED["second_opinion_policy"]
    assert _SHIPPED["second_opinion_policy"]["model_rule"] == "max"
    assert _SHIPPED["second_opinion_policy"]["never"] == "silently-same-model"


def test_the_deleted_two_step_machinery_is_gone():
    for name in (
        "opposite_vendor",
        "second_opinion_spec",
        "second_opinion_fallback_model",
        "second_opinion_unavailability",
        "resolve_second_opinion",
        "second_opinion_command",
    ):
        assert not hasattr(routing, name), name


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

_ALL_PRESENT = (
    "claude",
    "codex",
    "qwen",
    "homi",
    "sphinx",
    "myqwen",
    "nomodel",
    "nodefault",
    "opencode",
    "pi",
    "mixed",
)


@pytest.fixture
def all_present(monkeypatch):
    """Presence is a host fact the test supplies; nothing here reads `PATH` (ADR 0024/D11)."""
    monkeypatch.setattr(routing, "carrier_present", lambda registry, provider, project_root: provider in _ALL_PRESENT)


def _session(provider, family, model=None):
    return routing.SecondOpinionSession(provider=provider, family=family, model=model)


def test_ladder_walk_skips_the_session_carrier(all_present, project):
    target = routing.resolve_opinion_chain(_PRIORS_REGISTRY, _session("claude", "claude"), project, rank=2)
    assert target == routing.SecondOpinionTarget("codex", None, "gpt")


def test_ladder_walk_is_relative_to_the_session_not_absolute(all_present, project):
    """The top of the ladder is reachable for everyone but itself — no per-carrier second choice."""
    target = routing.resolve_opinion_chain(_PRIORS_REGISTRY, _session("codex", "gpt"), project, rank=2)
    assert target == routing.SecondOpinionTarget("claude", None, "claude")


def test_same_priors_behind_another_carrier_is_skipped(all_present, project):
    """`homi` is a different harness and still the same mind, so it buys nothing (D06)."""
    session = _session("claude", "claude")
    assert routing.resolve_opinion_chain(_PRIORS_REGISTRY, session, project, rank=3) == routing.SecondOpinionTarget(
        "qwen", None, "qwen"
    )
    skips = routing.opinion_skips(_PRIORS_REGISTRY, session, project)
    assert ("claude", "self") in skips
    assert ("homi", "same priors as claude") in skips


def test_a_model_the_session_already_answers_with_is_skipped(all_present, project):
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
    assert routing.resolve_opinion_chain(registry, session, project, rank=2) is None
    assert routing.opinion_skips(registry, session, project) == (("claude", "self"), ("qwen", "same model as claude"))


def test_a_provider_without_declared_priors_is_skipped(all_present, project):
    """Nothing was read from the host to fill this in, and guessing would be the old defect.
    Two `qwen`-family providers are one mind, so the chain stops at two and rank 4 is past it."""
    session = _session("claude", "claude")
    assert ("sphinx", "priors unknown") in routing.opinion_skips(_PRIORS_REGISTRY, session, project)
    assert routing.resolve_opinion_chain(_PRIORS_REGISTRY, session, project, rank=3) == routing.SecondOpinionTarget(
        "qwen", None, "qwen"
    )
    assert routing.resolve_opinion_chain(_PRIORS_REGISTRY, session, project, rank=4) is None


def test_an_absent_carrier_is_skipped_with_that_reason(monkeypatch, project):
    monkeypatch.setattr(
        routing, "carrier_present", lambda registry, provider, project_root: provider in ("claude", "qwen")
    )
    session = _session("claude", "claude")
    assert routing.resolve_opinion_chain(_PRIORS_REGISTRY, session, project, rank=2) == routing.SecondOpinionTarget(
        "qwen", None, "qwen"
    )
    assert ("codex", "carrier absent") in routing.opinion_skips(_PRIORS_REGISTRY, session, project)


def test_a_ladder_id_outside_the_table_is_a_named_error(all_present, project):
    registry = {
        "providers": _PRIORS_REGISTRY["providers"],
        "second_opinion_policy": {"ladder": ["claude", "ghost"]},
    }
    with pytest.raises(KeyError, match="ghost"):
        routing.resolve_opinion_chain(registry, _session("claude", "claude"), project, rank=2)


def test_an_exhausted_chain_yields_nothing_for_the_caller_to_dress_up(all_present, project):
    """Rank past the chain is `None`; the last resort (D07) is the caller's disclosed step."""
    assert routing.resolve_opinion_chain(_PRIORS_REGISTRY, _session("claude", "claude"), project, rank=9) is None


def test_declared_carrier_builds_its_own_argv_with_the_pin(all_present, project):
    assert routing.opinion_command(_PRIORS_REGISTRY, "myqwen", project, routing.OpinionRun(model="qwen3.8-flash")) == [
        "myqwen",
        "-m",
        "qwen3.8-flash",
    ]


def _declared(*argv: str) -> dict:
    return {"providers": {"d": {"argv": list(argv), "family": "qwen", "report_dir": _SO_DIR}}}


def test_an_unpinned_declared_argv_drops_the_model_element_and_the_flag_before_it(project):
    """The owner's rule: no dangling flag — `["qwen", "-m", "{model}"]` runs as `["qwen"]`, not `["qwen", "-m"]`."""
    assert routing.opinion_command(_declared("qwen", "-m", "{model}"), "d", project) == ["qwen"]
    assert routing.opinion_command(
        _declared("d-bin", "-m", "{model}", "--flag"), "d", project, routing.OpinionRun(prompt="p")
    ) == [
        "d-bin",
        "--flag",
        "p",
    ]


def test_an_unpinned_declared_argv_drops_an_element_that_merely_contains_the_placeholder_whole(project):
    """`--model={model}` carries its own flag, so only that element goes and the one before it stays."""
    assert routing.opinion_command(_declared("d-bin", "--keep", "--model={model}", "--x"), "d", project) == [
        "d-bin",
        "--keep",
        "--x",
    ]


def test_an_unpinned_placeholder_keeps_a_predecessor_that_is_not_a_bare_flag(project):
    """Only a flag (leading `-`, no `=`) is paired with the value after it; a subcommand or `--k=v` stays."""
    assert routing.opinion_command(_declared("d-bin", "run", "{model}"), "d", project) == ["d-bin", "run"]
    assert routing.opinion_command(_declared("d-bin", "--k=v", "{model}"), "d", project) == ["d-bin", "--k=v"]
    assert routing.opinion_command(_declared("{model}", "x"), "d", project) == ["x"]


def test_an_unpinned_argv_with_several_placeholders_drops_each_flag_pair(project):
    assert routing.opinion_command(
        _declared("d-bin", "-m", "{model}", "-n", "1", "--alt", "{model}"), "d", project
    ) == [
        "d-bin",
        "-n",
        "1",
    ]


def test_a_pinned_declared_argv_is_unchanged_by_the_dangling_flag_rule(project):
    assert routing.opinion_command(
        _declared("d-bin", "-m", "{model}", "--model={model}"), "d", project, routing.OpinionRun(model="m1")
    ) == [
        "d-bin",
        "-m",
        "m1",
        "--model=m1",
    ]


def test_declared_carrier_without_a_placeholder_refuses_a_pin(all_present, project):
    """The C97 guarantee, kept for a carrier akmon never measured: no silent unpinned run."""
    with pytest.raises(routing.UnpinnableModelError, match="declares no model"):
        routing.opinion_command(_PRIORS_REGISTRY, "nomodel", project, routing.OpinionRun(model="gpt-x"))


def test_declared_carrier_reports_repo_as_unknown_unless_stated(all_present, project):
    """Repository access is derived for a harness and never invented for a declaration."""
    assert routing.opinion_repo(_PRIORS_REGISTRY, "myqwen", project) == "unknown"
    assert routing.opinion_repo(_PRIORS_REGISTRY, "claude", project) == "worktree"


def test_shipped_carrier_still_routes_through_the_command_map(all_present, project):
    argv = routing.opinion_command(
        _PRIORS_REGISTRY, "claude", project, routing.OpinionRun(model="opus", prompt="review this")
    )
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


def test_the_second_opinion_takes_the_strongest_declared_model(all_present, project):
    session = _session("qwen", "qwen")
    assert routing.resolve_opinion_chain(_RULE_REGISTRY, session, project, rank=2) == routing.SecondOpinionTarget(
        "claude", "opus", "claude"
    )
    assert routing.resolve_opinion_chain(_RULE_REGISTRY, session, project, rank=3) == routing.SecondOpinionTarget(
        "codex", "sol", "gpt"
    )


def test_a_provider_declaring_no_models_yields_the_carrier_default(all_present, project):
    session = _session("qwen", "qwen")
    assert routing.resolve_opinion_chain(_RULE_REGISTRY, session, project, rank=4) == routing.SecondOpinionTarget(
        "nodefault", None, "gemini"
    )


def test_the_model_rule_reads_the_provider_table_never_the_bindings_rungs(all_present, project):
    """D14's separation: `anthropic.harness_rungs` says tiny/small, and that is not this answer."""
    assert routing.opinion_model(_RULE_REGISTRY, "claude", project) == "opus"


def test_an_unimplemented_model_rule_is_refused_not_guessed(all_present, project):
    registry = dict(_RULE_REGISTRY, second_opinion_policy={"ladder": ["claude"], "model_rule": "median"})
    with pytest.raises(ValueError, match="model_rule"):
        routing.opinion_model(registry, "claude", project)


def test_two_providers_answering_with_the_same_model_are_not_two_minds(monkeypatch, project):
    """D06 and D14 together: the model the rule picks is what must differ, not only the family."""
    monkeypatch.setattr(routing, "carrier_present", lambda registry, provider, project_root: True)
    registry = {
        "providers": {
            "alpha": {"argv": ["alpha"], "family": "claude", "models": ["shared"], "report_dir": _SO_DIR},
            "beta": {"argv": ["beta"], "family": "gpt", "models": ["shared"], "report_dir": _SO_DIR},
        },
        "second_opinion_policy": {"ladder": ["alpha", "beta"]},
    }
    session = _session("gamma", "qwen")
    assert routing.resolve_opinion_chain(registry, session, project, rank=2) == routing.SecondOpinionTarget(
        "alpha", "shared", "claude"
    )
    assert routing.resolve_opinion_chain(registry, session, project, rank=3) is None
    assert ("beta", "same model as alpha") in routing.opinion_skips(registry, session, project)


# --------------------------------------------------------------------------------------
# provider_family: the priors that answer for the CHOSEN model (multi-family carriers)
# --------------------------------------------------------------------------------------

_GATEWAYS = {
    "providers": {
        "opencode": {
            "family": None,
            "models": [],
            "model_families": {"anthropic/claude-sonnet-4": "claude", "qwen3:8b": "qwen"},
            "report_dir": _SO_DIR,
        },
        "pi": {"family": None, "models": [], "model_families": {}, "report_dir": _SO_DIR},
        "claude": {"family": "claude", "models": ["haiku", "sonnet", "opus"], "report_dir": _SO_DIR},
        "mixed": {"family": "gpt", "model_families": {"qwen3:8b": "qwen"}, "report_dir": _SO_DIR},
    },
    "second_opinion_policy": {"ladder": []},
}


def test_provider_family_reads_the_models_own_entry_first(project):
    assert routing.provider_family(_GATEWAYS, "opencode", project, "anthropic/claude-sonnet-4") == "claude"
    assert routing.provider_family(_GATEWAYS, "opencode", project, "qwen3:8b") == "qwen"
    assert routing.provider_family(_GATEWAYS, "mixed", project, "qwen3:8b") == "qwen"


def test_provider_family_falls_back_to_the_row_then_to_unknown(project):
    assert routing.provider_family(_GATEWAYS, "mixed", project, "anything-else") == "gpt"
    assert routing.provider_family(_GATEWAYS, "claude", project, "opus") == "claude"
    assert routing.provider_family(_GATEWAYS, "claude", project) == "claude"
    assert routing.provider_family(_GATEWAYS, "opencode", project, "undeclared/model") is None
    assert routing.provider_family(_GATEWAYS, "opencode", project) is None
    assert routing.provider_family(_GATEWAYS, "pi", project, "anything") is None


def test_provider_family_of_an_undeclared_provider_is_a_named_error(project):
    with pytest.raises(KeyError, match="ghost"):
        routing.provider_family(_GATEWAYS, "ghost", project, "m")


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ("claude", ("claude", None)),
        ("claude:opus", ("claude", "opus")),
        ("opencode:anthropic/claude-sonnet-4", ("opencode", "anthropic/claude-sonnet-4")),
        ("opencode:qwen3:8b", ("opencode", "qwen3:8b")),
        ("claude:", ("claude", None)),
    ],
)
def test_a_ladder_entry_splits_on_the_first_colon(entry, expected):
    assert routing.split_opinion_entry(entry) == expected


# --------------------------------------------------------------------------------------
# the walk with multi-family carriers: the family is read for the model the walk chose
# --------------------------------------------------------------------------------------


def _gateway_registry(ladder):
    return {**_GATEWAYS, "second_opinion_policy": {"ladder": ladder}}


def test_a_multi_family_carrier_resolves_the_family_of_its_pinned_model(all_present, project):
    registry = _gateway_registry(["opencode:anthropic/claude-sonnet-4"])
    chain = routing.resolve_opinion_chain(registry, _session("qwen", "qwen", "qwen3:8b"), project, rank=2)
    assert chain == routing.SecondOpinionTarget("opencode", "anthropic/claude-sonnet-4", "claude")


def test_a_multi_family_carrier_pinned_to_the_sessions_family_is_skipped_as_same_priors(all_present, project):
    registry = _gateway_registry(["opencode:anthropic/claude-sonnet-4"])
    session = _session("claude", "claude", "opus")
    assert routing.resolve_opinion_chain(registry, session, project, rank=2) is None
    assert ("opencode", "same priors as claude") in routing.opinion_skips(registry, session, project)


def test_a_multi_family_carrier_with_an_unknown_model_is_skipped_and_asked_about(all_present, project):
    registry = _gateway_registry(["opencode:undeclared/model", "pi"])
    session = _session("claude", "claude")
    assert routing.resolve_opinion_chain(registry, session, project, rank=2) is None
    assert routing.opinion_skips(registry, session, project) == (
        ("opencode", "priors unknown"),
        ("pi", "priors unknown"),
    )
    asks = routing.opinion_asks(registry, session, project)
    assert len(asks) == 2
    assert "providers.opencode.model_families.undeclared/model" in asks[0]
    assert "model-routing.json" in asks[0]
    assert "providers.pi.family" in asks[1]
    assert "model_families" not in asks[1]


def test_an_ask_names_the_local_overlay_first_and_the_project_overlay_second(all_present, project):
    """D11 layer 1: the strongest file is offered first, the shared one second, in the same sentence."""
    registry = _gateway_registry(["opencode:undeclared/model", "pi"])
    asks = routing.opinion_asks(registry, _session("claude", "claude"), project)
    local_file, project_file = "_aitna/local/model-routing.json", "_aitna/model-routing.json"
    assert asks[1] == (
        f"pi: priors unknown for its default model; declare providers.pi.family in {local_file}"
        f" to keep it to yourself, or {project_file} to share it with the team"
    )
    assert asks[0].index(local_file) < asks[0].index(project_file)


def test_a_session_ask_names_both_overlays_then_the_recorded_session_family(all_present, project):
    session = _session("opencode", None, "undeclared/model")
    [ask] = routing.opinion_asks(_PRIORS_REGISTRY, session, project)
    local_file, project_file = "_aitna/local/model-routing.json", "_aitna/model-routing.json"
    assert ask.index(local_file) < ask.index(project_file) < ask.index("session.family")
    assert "to keep it to yourself" in ask and "to share it with the team" in ask


def test_a_model_id_with_a_colon_reaches_the_walk_whole(all_present, project):
    registry = _gateway_registry(["opencode:qwen3:8b"])
    target = routing.resolve_opinion_chain(registry, _session("claude", "claude"), project, rank=2)
    assert target == routing.SecondOpinionTarget("opencode", "qwen3:8b", "qwen")


def test_the_same_carrier_twice_on_two_models_of_one_family_is_one_mind(all_present, project):
    registry = _gateway_registry(["opencode:qwen3:8b", "mixed:qwen3:8b"])
    session = _session("claude", "claude")
    assert routing.resolve_opinion_chain(registry, session, project, rank=3) is None
    assert ("mixed", "same priors as opencode") in routing.opinion_skips(registry, session, project)


def test_a_session_with_unknown_priors_yields_an_empty_chain_and_the_ask(all_present, project):
    """D08, in the other direction: nothing can be said to differ from priors nobody knows."""
    session = _session("opencode", None, "undeclared/model")
    assert routing.resolve_opinion_chain(_PRIORS_REGISTRY, session, project, rank=2) is None
    assert routing.opinion_skips(_PRIORS_REGISTRY, session, project) == (("opencode", "session priors unknown"),)
    [ask] = routing.opinion_asks(_PRIORS_REGISTRY, session, project)
    assert "providers.opencode.model_families.undeclared/model" in ask
    assert "session.family" in ask


# --------------------------------------------------------------------------------------
# resolve_session: any harness, any model — explicit, then the stanza, then the bound vendor
# --------------------------------------------------------------------------------------

_SESSION_REGISTRY = {
    "anthropic": {"selection_policy": {}, "carrier": "claude"},
    "providers": {
        "claude": {"family": "claude", "report_dir": _SO_DIR},
        "qwen": {"family": "qwen", "report_dir": _SO_DIR},
        "opencode": {
            "family": None,
            "model_families": {"anthropic/claude-sonnet-4": "claude"},
            "report_dir": _SO_DIR,
        },
    },
}


def test_the_session_derives_from_the_bound_vendors_carrier_and_the_orchestrator_alias():
    config = {"vendor": "anthropic", "orchestrator": "opus"}
    assert routing.resolve_session(_SESSION_REGISTRY, config) == routing.SecondOpinionSession(
        "claude", "claude", "opus"
    )


def test_the_session_stanza_outranks_the_vendor():
    config = {"vendor": "anthropic", "orchestrator": "opus", "session": {"provider": "qwen", "model": "qwen3-max"}}
    assert routing.resolve_session(_SESSION_REGISTRY, config) == routing.SecondOpinionSession(
        "qwen", "qwen", "qwen3-max"
    )


def test_explicit_arguments_outrank_the_stanza_and_the_vendor():
    config = {"vendor": "anthropic", "orchestrator": "opus", "session": {"provider": "qwen", "model": "x"}}
    session = routing.resolve_session(_SESSION_REGISTRY, config, provider="opencode", model="anthropic/claude-sonnet-4")
    assert session == routing.SecondOpinionSession("opencode", "claude", "anthropic/claude-sonnet-4")


def test_a_layer_naming_another_provider_never_lends_its_model_or_family():
    config = {"vendor": "anthropic", "orchestrator": "opus", "session": {"provider": "claude", "family": "claude"}}
    session = routing.resolve_session(_SESSION_REGISTRY, config, provider="qwen")
    assert session == routing.SecondOpinionSession("qwen", "qwen", None)


def test_an_explicit_family_wins_over_the_table():
    session = routing.resolve_session(_SESSION_REGISTRY, {}, provider="opencode", model="m", family="gpt")
    assert session == routing.SecondOpinionSession("opencode", "gpt", "m")


def test_a_multi_family_session_with_an_undeclared_model_has_unknown_priors():
    session = routing.resolve_session(_SESSION_REGISTRY, {}, provider="opencode", model="undeclared/model")
    assert session == routing.SecondOpinionSession("opencode", None, "undeclared/model")


def test_a_session_on_a_harness_with_no_row_is_still_a_session_with_unknown_priors():
    assert routing.resolve_session(_SESSION_REGISTRY, {}, provider="gemini") == routing.SecondOpinionSession(
        "gemini", None, None
    )


def test_a_session_nothing_names_is_a_named_error():
    with pytest.raises(routing.SessionUnknownError, match="--session-provider"):
        routing.resolve_session(_SESSION_REGISTRY, {})


# --------------------------------------------------------------------------------------
# the disclosed last resort (D07)
# --------------------------------------------------------------------------------------


def test_the_last_resort_takes_the_strongest_declared_model_that_differs_from_the_sessions(project):
    registry = {"providers": {"claude": {"family": "claude", "models": ["haiku", "sonnet", "opus"]}}}
    assert routing.opinion_last_resort(
        registry, _session("claude", "claude", "opus"), project
    ) == routing.SecondOpinionTarget("claude", "sonnet", "claude")
    assert routing.opinion_last_resort(
        registry, _session("claude", "claude", "haiku"), project
    ) == routing.SecondOpinionTarget("claude", "opus", "claude")


def test_the_last_resort_falls_back_to_the_carrier_default_when_no_model_differs(project):
    registry = {"providers": {"qwen": {"family": "qwen", "models": []}, "solo": {"family": "gpt", "models": ["x"]}}}
    assert routing.opinion_last_resort(registry, _session("qwen", "qwen", "q"), project) == routing.SecondOpinionTarget(
        "qwen", None, "qwen"
    )
    assert routing.opinion_last_resort(registry, _session("solo", "gpt", "x"), project) == routing.SecondOpinionTarget(
        "solo", None, "gpt"
    )


def test_the_last_resort_reads_the_provider_table_not_the_bindings_rungs(project):
    registry = {
        "anthropic": {"selection_policy": {}, "harness_rungs": ["tiny", "small"]},
        "providers": {"claude": {"family": "claude", "models": ["haiku", "opus"]}},
    }
    assert routing.opinion_last_resort(registry, _session("claude", "claude", "opus"), project).model == "haiku"


# --------------------------------------------------------------------------------------
# the carrier's presence resolves its binary from the command map for a shipped row
# --------------------------------------------------------------------------------------


def test_a_shipped_carrier_is_present_when_the_command_maps_binary_resolves(monkeypatch, project):
    seen = []
    monkeypatch.setattr(routing.shutil, "which", lambda binary: seen.append(binary) or "/bin/x")
    assert routing.carrier_present(_SHIPPED, "qwen", project) is True
    assert seen == ["qwen"]


def test_a_declared_carrier_is_present_by_its_requires_command_then_its_argv(monkeypatch, project):
    seen = []
    monkeypatch.setattr(routing.shutil, "which", lambda binary: seen.append(binary) or None)
    registry = {"providers": {"a": {"requires_command": "tool-a", "argv": ["x"]}, "b": {"argv": ["tool-b", "-m"]}}}
    assert routing.carrier_present(registry, "a", project) is False
    assert routing.carrier_present(registry, "b", project) is False
    assert seen == ["tool-a", "tool-b"]


def test_a_row_naming_no_executable_anywhere_is_absent(project):
    assert routing.carrier_present({"providers": {"nameless": {"family": "gpt"}}}, "nameless", project) is False


# --------------------------------------------------------------------------------------
# retired keys: refused by name, quoting the file that carries them
# --------------------------------------------------------------------------------------


def test_the_retired_keys_are_listed_by_where_they_live():
    assert routing.retired_second_opinion_keys() == {
        "policy": ("diversity_ladder",),
        "vendor": ("second_opinion",),
        "config": ("second_opinion_provider", "second_opinion_fallback_model"),
    }


def test_a_retired_ladder_in_the_overlay_is_refused_and_names_the_overlay_file(project):
    registry = {"second_opinion_policy": {"ladder": ["claude"], "diversity_ladder": ["other-vendor"]}}
    with pytest.raises(routing.RetiredKeyError, match=r"model-routing\.json.*second_opinion_policy\.diversity_ladder"):
        routing.refuse_retired_keys(registry, {}, project)


def test_a_vendor_second_opinion_object_in_the_overlay_is_refused_and_names_the_vendor(project):
    registry = {"anthropic": {"selection_policy": {}, "second_opinion": {"report_dir": "x"}}}
    with pytest.raises(routing.RetiredKeyError, match=r"model-routing\.json.*anthropic\.second_opinion"):
        routing.refuse_retired_keys(registry, {}, project)


def test_the_retired_local_config_keys_are_refused_and_name_the_local_config_file(project):
    config = {"second_opinion_provider": "openai", "second_opinion_fallback_model": "medium"}
    with pytest.raises(
        routing.RetiredKeyError,
        match=r"model-routing\.local\.json.*second_opinion_provider, second_opinion_fallback_model",
    ):
        routing.refuse_retired_keys({}, config, project)


def test_a_clean_registry_and_config_pass(project):
    routing.refuse_retired_keys(_SHIPPED, {"vendor": "anthropic", "session": {"provider": "qwen"}}, project)


# --------------------------------------------------------------------------------------
# opinion_head: the status line and init summary read the same walk
# --------------------------------------------------------------------------------------


def test_the_head_names_the_first_provider_its_model_and_its_priors(all_present, project):
    config = {"vendor": "anthropic", "orchestrator": "opus"}
    registry = {**_RULE_REGISTRY, "anthropic": {"selection_policy": {}, "carrier": "claude"}}
    registry["providers"] = {**_RULE_REGISTRY["providers"]}
    assert routing.opinion_head(registry, config, project) == ("codex:sol priors=gpt", None)


def test_a_head_without_a_model_is_the_bare_provider(all_present, project):
    config = {"session": {"provider": "claude", "model": "opus"}}
    registry = {**_PRIORS_REGISTRY, "second_opinion_policy": {"ladder": ["claude", "qwen"]}}
    assert routing.opinion_head(registry, config, project) == ("qwen priors=qwen", None)


def test_an_empty_chain_reads_unavailable_and_says_why(all_present, project):
    config = {"session": {"provider": "claude", "model": "opus"}}
    registry = {**_PRIORS_REGISTRY, "second_opinion_policy": {"ladder": ["claude"]}}
    display, warning = routing.opinion_head(registry, config, project)
    assert display == "unavailable"
    assert "provider chain is empty" in warning and "--list" in warning


def test_a_session_of_unknown_priors_reads_priors_unknown_beside_the_key_to_declare(all_present, project):
    config = {"session": {"provider": "opencode", "model": "undeclared/model"}}
    registry = {**_PRIORS_REGISTRY, "providers": {**_PRIORS_REGISTRY["providers"], "opencode": {"family": None}}}
    display, warning = routing.opinion_head(registry, config, project)
    assert display == "unavailable priors=unknown"
    assert "providers.opencode.model_families.undeclared/model" in warning


def test_a_session_nothing_names_reads_priors_unknown_too(all_present, project):
    display, warning = routing.opinion_head(_PRIORS_REGISTRY, {}, project)
    assert display == "unavailable priors=unknown"
    assert "--session-provider" in warning


# --------------------------------------------------------------------------------------
# the unknown-ladder-id error names the files to edit (D05, H13); the family vocabulary (D01)
# --------------------------------------------------------------------------------------


def test_an_unknown_ladder_id_names_both_overlay_files_to_edit(project):
    with pytest.raises(KeyError) as raised:
        routing.provider_row({"providers": {}}, "ghost", project)

    message = raised.value.args[0]
    assert "the ladder names 'ghost', which the providers table does not declare" in message
    assert "declare providers.ghost or remove it from second_opinion_policy.ladder in" in message
    assert "_aitna/local/model-routing.json (yours)" in message
    assert "_aitna/model-routing.json (the team's)" in message


def test_the_shipped_family_vocabulary_is_the_four_minds_d01_names():
    assert routing.family_vocabulary(_SHIPPED) == ("claude", "gpt", "qwen", "gemini")


def test_an_overlay_extends_the_family_vocabulary_by_key_without_restating_it():
    extended = {**_SHIPPED, "second_opinion_policy": {**_SHIPPED["second_opinion_policy"]}}
    overlay = {"second_opinion_policy": {"families": {"deepseek": "DeepSeek models"}}}
    merged = routing._deep_merge(extended, overlay)
    assert routing.family_vocabulary(merged) == ("claude", "gpt", "qwen", "gemini", "deepseek")


def test_a_registry_without_a_vocabulary_has_an_empty_one():
    assert routing.family_vocabulary({}) == ()
    assert routing.family_vocabulary({"second_opinion_policy": {"families": ["claude"]}}) == ()


def test_check_session_family_accepts_a_member_and_refuses_the_rest_naming_the_files(project):
    routing.check_session_family(_SHIPPED, "qwen", project)
    with pytest.raises(ValueError, match=r"--session-family 'mimo' is not in the family vocabulary") as raised:
        routing.check_session_family(_SHIPPED, "mimo", project)
    assert "second_opinion_policy.families.mimo in _aitna/local/model-routing.json" in str(raised.value)


# --------------------------------------------------------------------------------------
# the dev root is declared by `.aitna-root` (ADR 0022 D09): printed overlay paths follow it
# --------------------------------------------------------------------------------------


def test_a_relocated_dev_root_moves_the_files_an_ask_names(all_present, project):
    (project / ".aitna-root").write_text("tools/ai\n", encoding="utf-8")
    registry = _gateway_registry(["pi"])
    [ask] = routing.opinion_asks(registry, _session("claude", "claude"), project)
    assert "providers.pi.family in tools/ai/local/model-routing.json" in ask
    assert "or tools/ai/model-routing.json to share it with the team" in ask
    assert "_aitna" not in ask


def test_a_relocated_dev_root_moves_the_files_an_unknown_ladder_id_names(project):
    (project / ".aitna-root").write_text("tools/ai\n", encoding="utf-8")
    with pytest.raises(KeyError) as raised:
        routing.provider_row({"providers": {}}, "ghost", project)
    assert "tools/ai/local/model-routing.json (yours)" in raised.value.args[0]
    assert "tools/ai/model-routing.json (the team's)" in raised.value.args[0]


def test_akmons_own_dev_root_is_declared_by_its_tracked_file():
    with pytest.raises(KeyError) as raised:
        routing.provider_row({"providers": {}}, "ghost", _AKMON)
    assert "meta/local/model-routing.json (yours)" in raised.value.args[0]


def test_without_a_project_root_the_files_an_ask_names_are_the_default_dev_root(all_present):
    [ask] = routing.opinion_asks(_gateway_registry(["pi"]), _session("claude", "claude"), None)
    assert "_aitna/local/model-routing.json" in ask and " _aitna/model-routing.json" in ask


def test_a_layered_refusal_reads_each_overlay_file_and_names_the_one_that_holds_the_key(project):
    (project / "_aitna" / "local").mkdir()
    (project / "_aitna" / "model-routing.json").write_text(
        '{"second_opinion_policy": {"diversity_ladder": ["x"]}}', encoding="utf-8"
    )
    with pytest.raises(routing.RetiredKeyError) as raised:
        routing.refuse_retired_keys({}, {}, project, layered=True)
    message = str(raised.value)
    assert "_aitna/model-routing.json" in message and "second_opinion_policy.diversity_ladder" in message
    assert "local/model-routing.json" not in message


def test_an_unlayered_refusal_names_both_overlay_files_under_the_dev_root(project):
    (project / ".aitna-root").write_text("tools/ai\n", encoding="utf-8")
    registry = {"second_opinion_policy": {"diversity_ladder": ["x"]}}
    with pytest.raises(routing.RetiredKeyError) as raised:
        routing.refuse_retired_keys(registry, {}, project)
    assert "tools/ai/local/model-routing.json or tools/ai/model-routing.json" in str(raised.value)
