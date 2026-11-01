"""Unit tests for the second-opinion CLI (``tools/model_routing/second_opinion.py``).

Covers the priors wiring (ADR 0024): the walk picks the provider by the session's priors, ``--list``
proposes the ranked candidates, ``--rank`` takes the third opinion or the arbiter, ``--provider``
pins an explicit choice and discloses it as ``kind=pinned``, an empty chain takes the disclosed last
resort, and a pack travels on stdin where a row says so. Only ``--dry-run``, ``--list``, the skip
branch and a faked ``subprocess.run`` are exercised through ``main`` so no test ever spawns a real
harness, and carrier presence is supplied by the test, never read from the host's ``PATH``.
"""

from __future__ import annotations

import json
import os
import subprocess
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
import second_opinion  # noqa: E402

from common import jsondata  # noqa: E402

_REGISTRY = {
    "anthropic": {"selection_policy": {}, "carrier": "claude"},
    "openai": {"selection_policy": {}, "carrier": "codex"},
    "providers": {
        "claude": {
            "operation": "review",
            "model_flag": "--model {model}",
            "family": "claude",
            "models": ["haiku", "sonnet", "opus"],
            "report_dir": ".claude/second-opinion/",
        },
        "codex": {
            "operation": "review",
            "model_flag": "--model {model}",
            "family": "gpt",
            "models": ["luna", "terra", "sol"],
            "report_dir": ".codex/second-opinion/",
        },
        "qwen": {
            "operation": "review",
            "model_flag": "-m {model}",
            "family": "qwen",
            "models": [],
            "report_dir": ".qwen/second-opinion/",
        },
        # Another harness, the same mind as claude: the walk must pass it over.
        "homi": {
            "argv": ["homi", "--model", "{model}"],
            "family": "claude",
            "models": [],
            "report_dir": ".homi/second-opinion/",
        },
        # A multi-family carrier nobody declared a model for: priors unknown, asked about.
        "opencode": {
            "operation": "review",
            "model_flag": "-m {model}",
            "family": None,
            "models": [],
            "model_families": {},
            "report_dir": ".opencode/second-opinion/",
        },
        # A carrier its owner declared outright, fed on stdin (D12).
        "myqwen": {
            "argv": ["myqwen", "-m", "{model}"],
            "prompt": "stdin",
            "family": "qwen",
            "models": ["m1"],
            "report_dir": ".myqwen/second-opinion/",
        },
    },
    "second_opinion_policy": {"ladder": ["claude", "codex", "qwen", "homi", "opencode"], "model_rule": "max"},
}

_ONE_PROVIDER_REGISTRY = {**_REGISTRY, "second_opinion_policy": {"ladder": ["claude"], "model_rule": "max"}}

_CONFIG = {"vendor": "anthropic", "orchestrator": "opus", "binding": {"auditor": "opus"}}


@pytest.fixture(autouse=True)
def _every_carrier_present(monkeypatch):
    """Presence is a host fact the test supplies; nothing here reads ``PATH`` (ADR 0024/D11)."""
    monkeypatch.setattr(routing, "carrier_present", lambda registry, provider, project_root: True)


def _write_project(tmp_path: Path, registry: dict, config: dict | None = None) -> Path:
    """A minimal project root: AGENTS.md + <aitna>/akmon marker + registry + local config."""
    (tmp_path / "AGENTS.md").write_text("# project\n", encoding="utf-8")
    registry_path = tmp_path / "_aitna" / "akmon" / "tools" / "model_routing" / "registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    local_config_path = tmp_path / routing.local_config_rel()
    local_config_path.parent.mkdir(parents=True, exist_ok=True)
    local_config_path.write_text(json.dumps(_CONFIG if config is None else config), encoding="utf-8")
    return tmp_path


def _gate_pack(tmp_path: Path, text: str = "Review this change.") -> Path:
    pack = tmp_path / "pack.md"
    pack.write_text(text, encoding="utf-8")
    return pack


def _main(root: Path, *extra: str, gate: bool = True) -> int:
    argv = ["--project-root", str(root), *extra]
    if gate:
        argv += ["--gate", "code-verify", "--gate-pack", str(_gate_pack(root))]
    return second_opinion.main(argv)


class _Completed:
    returncode = 0
    stdout = b"verdict: fine\n"
    stderr = b""


def _no_subprocess(monkeypatch):
    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("subprocess.run must not be called here")

    monkeypatch.setattr(second_opinion.subprocess, "run", _fail_if_called)


# --------------------------------------------------------------------------------------
# --dry-run through the walk: the session's priors decide, the provider's row decides the rest
# --------------------------------------------------------------------------------------


def test_dry_run_picks_the_first_provider_with_other_priors_and_its_strongest_model(tmp_path, capsys):
    root = _write_project(tmp_path, _REGISTRY)

    assert _main(root, "--dry-run") == 0

    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("codex exec --model sol ")
    assert "report: .codex/second-opinion/code-verify-1.md" in out
    assert "provider=codex priors=gpt carrier=harness repo=worktree model=sol kind=chain" in out
    assert "skipped claude: self" in out
    assert "skipped homi: same priors as claude" in out


def test_the_session_comes_from_the_flags_when_the_config_names_none(tmp_path, capsys):
    root = _write_project(tmp_path, _REGISTRY, {})

    assert _main(root, "--session-provider", "codex", "--session-model", "sol", "--dry-run") == 0

    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("claude -p --output-format text --model opus ")
    assert "provider=claude priors=claude carrier=harness repo=worktree model=opus kind=chain" in out
    assert "skipped codex: self" in out


def test_a_session_flag_overrides_the_recorded_session(tmp_path, capsys):
    root = _write_project(tmp_path, _REGISTRY, {**_CONFIG, "session": {"provider": "qwen"}})

    assert _main(root, "--session-provider", "codex", "--dry-run") == 0

    assert "provider=claude " in capsys.readouterr().out


def test_the_deprecated_orchestrator_vendor_alias_maps_to_the_vendors_carrier(tmp_path, capsys):
    root = _write_project(tmp_path, _REGISTRY, {})

    assert _main(root, "--orchestrator-vendor", "openai", "--dry-run") == 0

    out = capsys.readouterr().out
    assert "provider=claude " in out and "skipped codex: self" in out


def test_the_alias_for_a_vendor_without_a_carrier_is_refused_by_name(tmp_path, capsys):
    root = _write_project(tmp_path, _REGISTRY, {})

    assert _main(root, "--orchestrator-vendor", "nobody", "--dry-run") == 2

    assert "--orchestrator-vendor 'nobody' names no vendor with a `carrier`" in capsys.readouterr().err


def test_a_session_nothing_names_is_refused_with_the_flag_to_pass(tmp_path, capsys):
    root = _write_project(tmp_path, _REGISTRY, {})

    assert _main(root, "--dry-run") == 2

    assert "--session-provider" in capsys.readouterr().err


def test_dry_run_with_a_task_names_the_next_ordinal_and_creates_nothing(tmp_path, capsys):
    """C114: ``[<task>-]<gate>-<n>.md``, n one past the largest existing ordinal of that prefix."""
    root = _write_project(tmp_path, _REGISTRY)
    report_dir = root / ".codex" / "second-opinion"
    report_dir.mkdir(parents=True)
    (report_dir / "C7-code-verify-1.md").write_text("earlier\n", encoding="utf-8")
    (report_dir / "code-verify-4.md").write_text("no task\n", encoding="utf-8")

    assert _main(root, "--task", "C7", "--dry-run") == 0

    assert "report: .codex/second-opinion/C7-code-verify-2.md" in capsys.readouterr().out
    assert sorted(p.name for p in report_dir.iterdir()) == ["C7-code-verify-1.md", "code-verify-4.md"]


# --------------------------------------------------------------------------------------
# --rank: third opinion, arbiter, and the end of the chain
# --------------------------------------------------------------------------------------


def test_rank_three_takes_the_next_provider_of_the_chain(tmp_path, capsys):
    root = _write_project(tmp_path, _REGISTRY)

    assert _main(root, "--rank", "3", "--dry-run") == 0

    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("qwen ")
    assert "provider=qwen priors=qwen" in out


def test_a_rank_past_the_chain_is_a_skip_with_the_reason_and_the_weaker_check_offered(tmp_path, capsys, monkeypatch):
    """A bare "skipped" leaves the owner with no reason and no option. The gate refuses to
    downgrade itself, but the same-model self-check is still worth offering — to a person,
    with the boundary attached — so its result is never filed as a second opinion."""
    root = _write_project(tmp_path, _REGISTRY)
    _no_subprocess(monkeypatch)

    assert _main(root, "--rank", "4") == 0

    out = capsys.readouterr().out
    assert "skipped at gate 'code-verify' — no provider could be run for rank 4" in out
    assert "the chain holds 2 provider(s), fewer than rank 4 asks for" in out
    assert "subagent" in out and "fresh context" in out
    assert "does not remove shared model priors" in out
    assert "must not be filed as one" in out
    assert "skipped homi: same priors as claude" in out


def test_a_rank_below_the_second_opinion_is_a_usage_error(tmp_path):
    root = _write_project(tmp_path, _REGISTRY)
    with pytest.raises(SystemExit) as excinfo:
        _main(root, "--rank", "1", "--dry-run")
    assert excinfo.value.code == 2


def test_the_gate_is_required_unless_the_chain_is_only_listed(tmp_path):
    root = _write_project(tmp_path, _REGISTRY)
    with pytest.raises(SystemExit) as excinfo:
        _main(root, "--dry-run", gate=False)
    assert excinfo.value.code == 2


# --------------------------------------------------------------------------------------
# --list: how the owner is proposed the priorities, without running anything
# --------------------------------------------------------------------------------------


def test_list_prints_the_ranked_chain_the_skip_ledger_and_the_asks_and_runs_nothing(tmp_path, capsys, monkeypatch):
    root = _write_project(tmp_path, _REGISTRY)
    _no_subprocess(monkeypatch)

    assert _main(root, "--list", gate=False) == 0

    assert capsys.readouterr().out.splitlines() == [
        "session: provider=claude model=opus priors=claude",
        "rank 2: provider=codex model=sol priors=gpt repo=worktree",
        "rank 3: provider=qwen model=(default) priors=qwen repo=worktree",
        "skipped:",
        "  claude: self",
        "  homi: same priors as claude",
        "  opencode: priors unknown",
        "asks:",
        "  opencode: priors unknown for its default model; declare providers.opencode.family"
        " in _aitna/.local/model-routing.json to keep it to yourself,"
        " or _aitna/model-routing.json to share it with the team",
    ]


def test_a_relocated_dev_root_declared_by_aitna_root_moves_the_files_the_asks_name(tmp_path, capsys, monkeypatch):
    """ADR 0022 D09: the dev root comes from `<project>/.aitna-root`, never from the environment."""
    root = _write_project(tmp_path, _REGISTRY)
    (root / ".aitna-root").write_text("tools/ai\n", encoding="utf-8")
    _no_subprocess(monkeypatch)

    assert _main(root, "--list", gate=False) == 0

    out = capsys.readouterr().out
    assert (
        "  opencode: priors unknown for its default model; declare providers.opencode.family"
        " in tools/ai/.local/model-routing.json to keep it to yourself,"
        " or tools/ai/model-routing.json to share it with the team"
    ) in out.splitlines()
    assert "_aitna" not in out


def test_list_reads_the_developers_local_overlay_as_the_strongest_layer(tmp_path, capsys, monkeypatch):
    """The local overlay declares the family the asks name, and its ladder replaces the project's whole."""
    root = _write_project(tmp_path, _REGISTRY)
    local = routing.local_overlay_path(root)
    local.parent.mkdir(parents=True)
    local.write_text(
        json.dumps(
            {"providers": {"opencode": {"family": "gemini"}}, "second_opinion_policy": {"ladder": ["opencode"]}}
        ),
        encoding="utf-8",
    )
    _no_subprocess(monkeypatch)

    assert _main(root, "--list", gate=False) == 0

    out = capsys.readouterr().out.splitlines()
    assert "rank 2: provider=opencode model=(default) priors=gemini repo=worktree" in out
    assert not any(line.startswith("rank 3") for line in out)  # the shipped ladder is gone, not extended


def test_a_retired_key_in_the_local_overlay_is_refused_naming_that_file(tmp_path, capsys, monkeypatch):
    root = _write_project(tmp_path, _REGISTRY)
    local = routing.local_overlay_path(root)
    local.parent.mkdir(parents=True)
    local.write_text(json.dumps({"second_opinion_policy": {"diversity_ladder": []}}), encoding="utf-8")
    _no_subprocess(monkeypatch)

    assert _main(root, "--list", gate=False) == 2

    err = capsys.readouterr().err
    assert "_aitna/.local/model-routing.json" in err and "diversity_ladder" in err


@pytest.mark.parametrize("content", ["{ not json", "[1, 2]"])
def test_an_overlay_that_is_not_a_json_object_is_one_error_line_and_exit_2(tmp_path, capsys, monkeypatch, content):
    root = _write_project(tmp_path, _REGISTRY)
    local = routing.local_overlay_path(root)
    local.parent.mkdir(parents=True)
    local.write_text(content, encoding="utf-8")
    _no_subprocess(monkeypatch)

    assert _main(root, "--list", gate=False) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "second-opinion: the routing overlay _aitna/.local/model-routing.json is not a valid JSON object;"
        " repair or delete it (it is hand-owned, so akmon never rewrites it)\n"
    )


def test_list_of_an_empty_chain_says_so_and_names_the_last_resort(tmp_path, capsys):
    root = _write_project(tmp_path, _ONE_PROVIDER_REGISTRY)

    assert _main(root, "--list", gate=False) == 0

    out = capsys.readouterr().out.splitlines()
    assert "chain: empty — no ladder provider differs from the session" in out
    assert "last resort at rank 2 (kind=last-resort): provider=claude model=sonnet priors=claude repo=worktree" in out


def test_list_for_a_session_of_unknown_priors_asks_for_them_and_shows_the_last_resort_a_run_takes(tmp_path, capsys):
    root = _write_project(tmp_path, _REGISTRY, {})

    assert _main(root, "--list", "--session-provider", "opencode", "--session-model", "x/y", gate=False) == 0

    out = capsys.readouterr().out
    assert "session: provider=opencode model=x/y priors=unknown" in out
    assert "last resort at rank 2 (kind=last-resort): provider=opencode model=(default) priors=unknown" in out
    assert "skipped:\n  opencode: session priors unknown" in out
    assert "providers.opencode.model_families.x/y" in out and "session.family" in out


def test_list_and_a_run_agree_on_the_last_resort_for_a_session_of_unknown_priors(tmp_path, capsys):
    root = _write_project(tmp_path, _REGISTRY, {})
    flags = ["--session-provider", "opencode", "--session-model", "x/y"]

    assert _main(root, "--list", *flags, gate=False) == 0
    listed = capsys.readouterr().out
    assert _main(root, *flags, "--dry-run") == 0
    ran = capsys.readouterr().out

    assert "provider=opencode priors=unknown carrier=harness repo=worktree model=(default) kind=last-resort" in ran
    assert "provider=opencode model=(default) priors=unknown repo=worktree" in listed


def test_list_says_why_no_last_resort_exists_when_the_session_provider_has_no_row(tmp_path, capsys):
    root = _write_project(tmp_path, _REGISTRY, {})

    assert _main(root, "--list", "--session-provider", "gemini", gate=False) == 0

    out = capsys.readouterr().out
    assert "chain: empty" in out
    assert "no last resort: the session's own provider 'gemini' has no row in the providers table" in out
    assert "last resort at rank 2" not in out


def test_list_says_why_no_last_resort_exists_when_the_session_carrier_is_off_path(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(routing, "carrier_present", lambda registry, provider, project_root: False)
    root = _write_project(tmp_path, _ONE_PROVIDER_REGISTRY)

    assert _main(root, "--list", gate=False) == 0

    out = capsys.readouterr().out
    assert "no last resort: the session's own provider 'claude' is not on PATH" in out


# --------------------------------------------------------------------------------------
# --provider: an explicit choice, disclosed as pinned and never counted as diverse
# --------------------------------------------------------------------------------------


def test_an_explicit_provider_with_other_priors_runs_as_pinned_without_a_warning(tmp_path, capsys):
    root = _write_project(tmp_path, _REGISTRY)

    assert _main(root, "--provider", "qwen:qwen3-max", "--dry-run") == 0

    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith(
        "qwen --approval-mode default --exclude-tools write_file,edit,run_shell_command --max-wall-time 140s "
        "-m qwen3-max "
    )
    assert "provider=qwen priors=qwen carrier=harness repo=worktree model=qwen3-max kind=pinned" in out
    assert "warning:" not in out


def test_an_explicit_provider_that_is_the_sessions_own_is_pinned_with_a_warning(tmp_path, capsys):
    root = _write_project(tmp_path, _REGISTRY)

    assert _main(root, "--provider", "claude:haiku", "--dry-run") == 0

    out = capsys.readouterr().out
    assert "kind=pinned" in out and "model=haiku" in out
    assert "warning: 'claude' is the session's own provider" in out


def test_an_explicit_provider_sharing_the_sessions_priors_is_pinned_with_a_warning(tmp_path, capsys):
    root = _write_project(tmp_path, _REGISTRY)

    assert _main(root, "--provider", "homi", "--dry-run") == 0

    out = capsys.readouterr().out
    assert "kind=pinned" in out
    assert "warning: 'homi' answers with priors 'claude', the session's own" in out


def test_an_explicit_provider_of_unknown_priors_is_pinned_with_a_warning(tmp_path, capsys):
    root = _write_project(tmp_path, _REGISTRY)

    assert _main(root, "--provider", "opencode:some/model", "--dry-run") == 0

    out = capsys.readouterr().out
    assert "priors=unknown" in out and "kind=pinned" in out
    assert "warning: the priors of 'opencode' are unknown" in out


def test_an_explicit_provider_outside_the_table_is_a_named_error(tmp_path, capsys):
    root = _write_project(tmp_path, _REGISTRY)

    assert _main(root, "--provider", "ghost", "--dry-run") == 2

    assert "the ladder names 'ghost', which the providers table does not declare" in capsys.readouterr().err


# --------------------------------------------------------------------------------------
# the last resort (D07): disclosed, never silent
# --------------------------------------------------------------------------------------


def test_an_empty_chain_runs_the_session_provider_on_another_model_as_the_disclosed_last_resort(tmp_path, capsys):
    root = _write_project(tmp_path, _ONE_PROVIDER_REGISTRY)

    assert _main(root, "--dry-run") == 0

    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("claude -p --output-format text --model sonnet ")
    assert "model=sonnet kind=last-resort" in out
    assert "warning: no ladder provider differs from the session" in out
    assert "strongest declared model that differs from opus" in out


def test_the_last_resort_falls_back_to_the_carrier_default_when_no_other_model_is_declared(tmp_path, capsys):
    registry = {**_ONE_PROVIDER_REGISTRY, "second_opinion_policy": {"ladder": ["qwen"]}}
    root = _write_project(tmp_path, registry, {})

    assert _main(root, "--session-provider", "qwen", "--dry-run") == 0

    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("qwen ") and "-m" not in out.splitlines()[0].split()
    assert "model=(default) kind=last-resort" in out


def test_a_session_of_unknown_priors_still_gets_the_last_resort_with_the_ask(tmp_path, capsys):
    root = _write_project(tmp_path, _REGISTRY, {})

    argv = ["--session-provider", "opencode", "--session-model", "x/y", "--dry-run"]
    assert _main(root, *argv) == 0

    out = capsys.readouterr().out
    assert "priors=unknown carrier=harness repo=worktree model=(default) kind=last-resort" in out
    assert "ask: session opencode: priors unknown for model x/y" in out


def test_a_session_provider_with_no_row_has_nothing_to_run_and_says_so(tmp_path, capsys, monkeypatch):
    root = _write_project(tmp_path, {**_REGISTRY, "second_opinion_policy": {"ladder": []}}, {})
    _no_subprocess(monkeypatch)

    assert _main(root, "--session-provider", "gemini", "--session-family", "gemini") == 0

    out = capsys.readouterr().out
    assert "the session's own provider 'gemini' has no row in the providers table" in out


def test_a_session_provider_off_path_has_nothing_to_run_and_says_so(tmp_path, capsys, monkeypatch):
    root = _write_project(tmp_path, _ONE_PROVIDER_REGISTRY)
    monkeypatch.setattr(routing, "carrier_present", lambda registry, provider, project_root: False)
    _no_subprocess(monkeypatch)

    assert _main(root) == 0

    assert "the session's own provider 'claude' is not on PATH" in capsys.readouterr().out


# --------------------------------------------------------------------------------------
# a pin the provider cannot apply, retired keys, and the pack's channel
# --------------------------------------------------------------------------------------


def test_a_pin_the_provider_cannot_apply_stops_the_run_loudly(tmp_path, capsys, monkeypatch):
    """C97: a chosen model needs a model_flag; without one the run must not go out unpinned."""
    providers = json.loads(json.dumps(_REGISTRY["providers"]))
    del providers["codex"]["model_flag"]
    root = _write_project(tmp_path, {**_REGISTRY, "providers": providers})
    _no_subprocess(monkeypatch)

    assert _main(root) == 2

    assert "declares no model_flag" in capsys.readouterr().err


def test_a_local_config_with_a_retired_key_is_refused_naming_the_file(tmp_path, capsys, monkeypatch):
    root = _write_project(tmp_path, _REGISTRY, {**_CONFIG, "second_opinion_provider": "openai"})
    _no_subprocess(monkeypatch)

    assert _main(root, "--dry-run") == 2

    err = capsys.readouterr().err
    assert ".claude/model-routing.local.json" in err and "second_opinion_provider" in err


def test_an_overlay_with_a_retired_key_is_refused_naming_the_file(tmp_path, capsys, monkeypatch):
    root = _write_project(tmp_path, _REGISTRY)
    (root / "_aitna" / "model-routing.json").write_text(
        json.dumps({"second_opinion_policy": {"diversity_ladder": ["other-vendor"]}}), encoding="utf-8"
    )
    _no_subprocess(monkeypatch)

    assert _main(root, "--dry-run") == 2

    err = capsys.readouterr().err
    assert "_aitna/model-routing.json" in err and "second_opinion_policy.diversity_ladder" in err


def test_a_declared_carrier_gets_the_pack_on_stdin_and_never_as_an_argument(tmp_path, capsys, monkeypatch):
    registry = {**_REGISTRY, "second_opinion_policy": {"ladder": ["myqwen"]}}
    root = _write_project(tmp_path, registry)
    seen = {}

    def fake_run(command, **kwargs):
        seen.update(command=command, **kwargs)
        return _Completed()

    monkeypatch.setattr(second_opinion.subprocess, "run", fake_run)

    assert _main(root) == 0

    assert seen["command"] == ["myqwen", "-m", "m1"]
    assert b"Review this change." in seen["input"]
    assert "provider=myqwen priors=qwen carrier=declared repo=unknown model=m1 kind=chain" in capsys.readouterr().out


def test_a_shipped_carrier_gets_the_pack_as_the_last_argument_and_no_stdin(tmp_path, capsys, monkeypatch):
    root = _write_project(tmp_path, _REGISTRY)
    seen = {}

    def fake_run(command, **kwargs):
        seen.update(command=command, **kwargs)
        return _Completed()

    monkeypatch.setattr(second_opinion.subprocess, "run", fake_run)

    assert _main(root) == 0

    capsys.readouterr()
    assert seen["command"][:4] == ["codex", "exec", "--model", "sol"]
    assert "Review this change." in seen["command"][-1]
    assert seen.get("input") is None
    assert seen["stdin"] == subprocess.DEVNULL  # a prompt on argv leaves stdin nothing to carry (see the EOF test)


def test_the_provider_runs_with_the_second_opinion_marker_in_its_environment(tmp_path, capsys, monkeypatch):
    root = _write_project(tmp_path, _REGISTRY)
    seen = {}

    def fake_run(command, **kwargs):
        seen.update(kwargs)
        return _Completed()

    monkeypatch.setattr(second_opinion.subprocess, "run", fake_run)
    monkeypatch.setenv("KEEP_ME", "yes")

    assert _main(root) == 0

    capsys.readouterr()
    assert seen["env"]["AKMON_SECOND_OPINION"] == "1"  # the learning hook neither counts nor reminds this child
    assert seen["env"]["KEEP_ME"] == "yes"


_STDIN_PROBE = (
    "import os, select, sys\n"
    "ready, _, _ = select.select([0], [], [], 2)\n"
    "print('stdin:eof' if ready and os.read(0, 1) == b'' else 'stdin:open')\n"
)


def test_a_carrier_fed_its_prompt_as_an_argument_sees_eof_on_stdin_even_with_an_open_parent_pipe(
    tmp_path, capsys, monkeypatch
):
    """A parent's open, non-EOF stdin pipe must not reach a carrier that takes its prompt on argv."""
    probe = {
        "argv": [sys.executable, "-c", _STDIN_PROBE, "--"],
        "family": "qwen",
        "models": [],
        "report_dir": ".probe/second-opinion/",
    }
    registry = {
        **_REGISTRY,
        "providers": {**_REGISTRY["providers"], "probe": probe},
        "second_opinion_policy": {"ladder": ["probe"]},
    }
    root = _write_project(tmp_path, registry)
    read_end, write_end = os.pipe()
    saved = os.dup(0)
    os.dup2(read_end, 0)
    try:
        assert _main(root) == 0
    finally:
        os.dup2(saved, 0)
        for fd in (saved, read_end, write_end):
            os.close(fd)

    assert capsys.readouterr().out.rstrip().endswith("stdin:eof")


def _declared_row_without_report_dir(tmp_path: Path, provider: str = "pi") -> Path:
    """A project whose only ladder provider is an owner-declared row with a fake carrier and no ``report_dir``."""
    row = {"argv": [sys.executable, "-c", "print('verdict: fine')", "--"], "family": "qwen", "models": []}
    registry = {
        **_REGISTRY,
        "providers": {**_REGISTRY["providers"], provider: row},
        "second_opinion_policy": {"ladder": [provider]},
    }
    return _write_project(tmp_path, registry)


def test_a_declared_row_with_no_report_dir_files_its_report_under_the_providers_own_directory(tmp_path, capsys):
    root = _declared_row_without_report_dir(tmp_path)

    assert _main(root) == 0

    assert "report: .pi/second-opinion/code-verify-1.md" in capsys.readouterr().out
    report = (root / ".pi" / "second-opinion" / "code-verify-1.md").read_text(encoding="utf-8")
    assert report.endswith("\n\nverdict: fine\n")


def test_the_default_report_dir_is_still_checked_against_the_project_root(tmp_path, capsys):
    root = _declared_row_without_report_dir(tmp_path, provider="x/../..")

    assert _main(root, "--provider", "x/../..") == 2

    err = capsys.readouterr().err
    assert "report_dir '.x/../../second-opinion/' resolves outside the project" in err


def test_the_report_file_carries_the_header_and_the_skip_ledger_with_the_review(tmp_path, capsys, monkeypatch):
    root = _write_project(tmp_path, _REGISTRY)
    monkeypatch.setattr(second_opinion.subprocess, "run", lambda *_a, **_k: _Completed())

    assert _main(root) == 0

    report = (root / ".codex" / "second-opinion" / "code-verify-1.md").read_text(encoding="utf-8")
    lines = report.splitlines()
    assert lines[0] == (
        "second-opinion provider=codex priors=gpt carrier=harness repo=worktree model=sol kind=chain"
        " gate=code-verify exit=0"
    )
    assert "skipped claude: self" in lines
    assert report.endswith("\n\nverdict: fine\n")
    out = capsys.readouterr().out
    assert out.splitlines()[0] == lines[0]
    assert "report: .codex/second-opinion/code-verify-1.md" in out


def test_a_carrier_that_cannot_start_is_an_error_line_and_exit_2(tmp_path, capsys, monkeypatch):
    root = _write_project(tmp_path, _REGISTRY)

    def missing(*_a, **_k):
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setattr(second_opinion.subprocess, "run", missing)

    assert _main(root) == 2

    assert "could not start 'codex'" in capsys.readouterr().err
    assert not (root / ".codex" / "second-opinion").exists()


def test_package_mode_reads_the_registry_from_its_own_tree(tmp_path, capsys):
    """A package-mode project has no ``<dev root>/akmon`` mount: the registry comes from the tree
    the tool runs from (the conformance corpus's native attach found the mount path hardcoded)."""
    root = tmp_path / "proj"
    (root / "_aitna").mkdir(parents=True)
    (root / "_aitna" / ".akmon.toml").write_text('mount = "package"\n', encoding="utf-8")

    assert _main(root, "--provider", "claude", "--session-provider", "codex", "--dry-run") == 0

    assert "provider=claude" in capsys.readouterr().out


# --------------------------------------------------------------------------------------
# C102: second_opinion.json — the runner texts
# --------------------------------------------------------------------------------------


def test_second_opinion_data_pins_the_structure_and_characteristic_texts():
    data = json.loads((_ROUTING_DIR / "second_opinion.json").read_text(encoding="utf-8"))
    assert set(data) == {
        "prompt",
        "unavailable_notice",
        "unavailable_reasons",
        "default_report_dir",
        "report_dir_outside",
        "summary",
        "model_shown",
        "listing",
        "pinned_warnings",
        "last_resort_note",
        "errors",
    }
    assert data["prompt"].startswith("You are an independent second-opinion reviewer for a akmon verify gate.")
    assert data["prompt"].endswith("Material to review:\n{{material}}\n")
    assert len(data["unavailable_notice"]) == 5
    assert data["unavailable_notice"][0] == (
        "second-opinion: skipped at gate '{{gate}}' — no provider could be run for rank {{rank}}."
    )
    assert data["report_dir_outside"] == (
        "second-opinion: report_dir '{{report_dir}}' resolves outside the project;"
        " it must be a directory inside the project root."
    )
    assert data["summary"]["result_line"] == (
        "second-opinion provider={{provider}} priors={{priors}} carrier={{carrier}} repo={{repo}}"
        " model={{model}} kind={{kind}} gate={{gate}} exit={{exit}}"
    )


def test_second_opinion_loader_reads_exactly_its_two_data_files(monkeypatch):
    seen: list[Path] = []

    def spy(path: Path):
        seen.append(path)
        return json.loads(path.read_text(encoding="utf-8"))

    monkeypatch.setattr(jsondata, "read", spy)
    second_opinion._prompt("g", "m")
    assert seen == [_ROUTING_DIR / "second_opinion.json"]
    second_opinion._digest("x" * 2000)
    assert seen == [_ROUTING_DIR / "second_opinion.json", _ROUTING_DIR / "gate.json"]


def test_a_missing_second_opinion_json_raises_from_main(monkeypatch, tmp_path):
    root = _write_project(tmp_path, _REGISTRY)
    pack = _gate_pack(root)

    def broken(path: Path):
        raise jsondata.DataFileError(f"akmon data file missing: {path}")

    monkeypatch.setattr(jsondata, "read", broken)
    with pytest.raises(jsondata.DataFileError):
        second_opinion.main(["--project-root", str(root), "--gate", "g", "--gate-pack", str(pack)])


def test_the_provider_output_is_read_with_universal_newlines(tmp_path, capsys, monkeypatch):
    """``text=True`` turns a provider's CRLF and lone CR into LF in the report (the C115 reference)."""
    (tmp_path / "project").mkdir()
    root = _write_project(tmp_path / "project", _REGISTRY)
    pack = _gate_pack(root)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stand_in = bin_dir / "codex"
    stand_in.write_text("#!/bin/sh\nprintf 'a\\r\\nb\\rc\\r\\n'\nprintf 'w\\r\\nx\\r' >&2\n", encoding="utf-8")
    stand_in.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    exit_code = second_opinion.main(
        ["--project-root", str(root), "--provider", "codex", "--gate", "g", "--gate-pack", str(pack)]
    )

    capsys.readouterr()
    assert exit_code == 0
    report = root / ".codex" / "second-opinion" / "g-1.md"
    assert report.read_bytes().endswith(b"\n\na\nb\nc\n\n[stderr]\nw\nx\n")


def test_an_undecodable_provider_byte_is_replaced_and_the_report_is_written(tmp_path, capsys, monkeypatch):
    """A byte that is not UTF-8 reads as U+FFFD on both pipes; the run still writes its report (C120)."""
    (tmp_path / "project").mkdir()
    root = _write_project(tmp_path / "project", _REGISTRY)
    pack = _gate_pack(root)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stand_in = bin_dir / "codex"
    stand_in.write_text("#!/bin/sh\nprintf 'ok\\377x'\nprintf 'e\\377' >&2\n", encoding="utf-8")
    stand_in.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    exit_code = second_opinion.main(
        ["--project-root", str(root), "--provider", "codex", "--gate", "g", "--gate-pack", str(pack)]
    )

    assert "\ufffd" in capsys.readouterr().out
    assert exit_code == 0
    report = root / ".codex" / "second-opinion" / "g-1.md"
    assert report.read_text(encoding="utf-8").endswith("\n\nok\ufffdx\n\n[stderr]\ne\ufffd\n")


def _registry_with_report_dir(report_dir: str) -> dict:
    registry = json.loads(json.dumps(_REGISTRY))
    registry["providers"]["codex"]["report_dir"] = report_dir
    return registry


def _outside_case(kind: str, tmp_path: Path) -> tuple[str, Path]:
    """``(configured report_dir, the outside directory it reaches)`` for one way of leaving the project."""
    outside = tmp_path / "outside"
    if kind == "absolute":
        return str(outside / "reviews"), outside
    if kind == "dotdot":
        return "../outside/reviews", outside
    outside.mkdir()
    (tmp_path / "project" / "link").symlink_to(outside, target_is_directory=True)
    return "link/reviews", outside


@pytest.mark.parametrize("dry_run", [False, True], ids=["run", "dry-run"])
@pytest.mark.parametrize("kind", ["absolute", "dotdot", "symlink"])
def test_a_report_dir_outside_the_project_is_refused_before_anything_runs(tmp_path, capsys, monkeypatch, kind, dry_run):
    (tmp_path / "project").mkdir()
    configured, outside = _outside_case(kind, tmp_path)
    root = _write_project(tmp_path / "project", _registry_with_report_dir(configured))

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("a report_dir outside the project must not reach the provider")

    monkeypatch.setattr(second_opinion.subprocess, "run", _fail_if_called)
    argv = ["--project-root", str(root), "--gate", "g"]
    argv += ["--gate-pack", str(_gate_pack(root))] + (["--dry-run"] if dry_run else [])

    exit_code = second_opinion.main(argv)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == (
        f"second-opinion: report_dir '{configured}' resolves outside the project;"
        " it must be a directory inside the project root.\n"
    )
    assert not (outside / "reviews").exists()


def test_a_report_dir_inside_the_project_still_writes_its_report(tmp_path, capsys, monkeypatch):
    """``..`` and a link that stay inside the project are fine; the report line names the resolved path."""
    (tmp_path / "project").mkdir()
    (tmp_path / "project" / "docs").mkdir()
    (tmp_path / "project" / "link").symlink_to(tmp_path / "project" / "docs", target_is_directory=True)
    root = _write_project(tmp_path / "project", _registry_with_report_dir("link/../link/reviews"))
    monkeypatch.setattr(second_opinion.subprocess, "run", lambda *_a, **_k: _Completed())
    argv = ["--project-root", str(root), "--gate", "g"]

    assert second_opinion.main([*argv, "--gate-pack", str(_gate_pack(root))]) == 0
    assert "report: docs/reviews/g-1.md" in capsys.readouterr().out
    assert (root / "docs" / "reviews" / "g-1.md").read_text(encoding="utf-8").endswith("\n\nverdict: fine\n")


# --------------------------------------------------------------------------------------
# ADR-0024/D16: aliases resolve to a concrete id from the local file; `default` is the carrier's own model
# --------------------------------------------------------------------------------------

_ALIAS_ROW = {
    **_REGISTRY["providers"]["codex"],
    "aliases": True,
    "catalog": {"file": "~/.codex/models_cache.json", "format": "codex-models-cache"},
}
_ALIAS_REGISTRY = {**_REGISTRY, "providers": {**_REGISTRY["providers"], "codex": _ALIAS_ROW}}


def _write_aliases(root: Path, **aliases: str) -> None:
    path = routing.local_aliases_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    stored = {"codex": routing.ProviderAliases("~/.codex/models_cache.json (codex-models-cache)", "0.164.0", aliases)}
    path.write_text(routing.model_aliases_document(stored), encoding="utf-8")


def test_an_alias_is_sent_to_the_carrier_as_its_concrete_id_and_the_header_records_both(tmp_path, capsys):
    root = _write_project(tmp_path, _ALIAS_REGISTRY)
    _write_aliases(root, sol="gpt-6.1-sol")

    assert _main(root, "--dry-run") == 0

    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("codex exec --model gpt-6.1-sol ")
    assert "provider=codex priors=gpt carrier=harness repo=worktree model=sol→gpt-6.1-sol kind=chain" in out


def test_an_alias_without_a_mapping_refuses_the_run_with_one_line_and_exit_2(tmp_path, capsys, monkeypatch):
    root = _write_project(tmp_path, _ALIAS_REGISTRY)
    _no_subprocess(monkeypatch)

    assert _main(root) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("\n") == 1
    assert captured.err.startswith(
        "second-opinion: provider 'codex' declares model aliases, and 'sol' has no concrete id"
    )
    assert "akmon tool model_routing/models --refresh --provider codex" in captured.err


def test_a_dry_run_also_refuses_an_unmapped_alias(tmp_path, capsys):
    root = _write_project(tmp_path, _ALIAS_REGISTRY)

    assert _main(root, "--dry-run") == 2

    assert "has no concrete id" in capsys.readouterr().err


def test_a_pinned_concrete_id_passes_through_unchanged_with_no_file_needed(tmp_path, capsys):
    root = _write_project(tmp_path, _ALIAS_REGISTRY)

    assert _main(root, "--provider", "codex:gpt-6.1-sol", "--dry-run") == 0

    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("codex exec --model gpt-6.1-sol ")
    assert "model=gpt-6.1-sol kind=pinned" in out


def test_a_pinned_alias_resolves_through_the_file(tmp_path, capsys):
    root = _write_project(tmp_path, _ALIAS_REGISTRY)
    _write_aliases(root, luna="gpt-6-luna")

    assert _main(root, "--provider", "codex:luna", "--dry-run") == 0

    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("codex exec --model gpt-6-luna ")
    assert "model=luna→gpt-6-luna kind=pinned" in out


def test_list_shows_the_resolution_and_an_unmapped_alias_with_its_ask(tmp_path, capsys):
    root = _write_project(tmp_path, _ALIAS_REGISTRY)

    assert _main(root, "--list", gate=False) == 0
    unresolved = capsys.readouterr().out
    _write_aliases(root, sol="gpt-6.1-sol")
    assert _main(root, "--list", gate=False) == 0
    resolved = capsys.readouterr().out

    assert "rank 2: provider=codex model=sol→(unresolved) priors=gpt repo=worktree" in unresolved
    assert (
        "  codex: alias 'sol' has no concrete id; run `akmon tool model_routing/models --refresh --provider codex`"
        in unresolved
    )
    assert "rank 2: provider=codex model=sol→gpt-6.1-sol priors=gpt repo=worktree" in resolved
    assert "has no concrete id" not in resolved


def test_a_corrupt_aliases_file_refuses_naming_it(tmp_path, capsys):
    root = _write_project(tmp_path, _ALIAS_REGISTRY)
    path = routing.local_aliases_path(root)
    path.parent.mkdir(parents=True)
    path.write_text("[]", encoding="utf-8")

    assert _main(root, "--list", gate=False) == 2

    assert "_aitna/.local/model-aliases.json is not a valid alias map" in capsys.readouterr().err


def test_the_default_token_runs_the_carriers_own_model_without_any_alias_file(tmp_path, capsys):
    root = _write_project(tmp_path, _ALIAS_REGISTRY)

    assert _main(root, "--provider", "codex:default", "--dry-run") == 0

    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("codex exec You are an independent")
    assert "--model" not in out.splitlines()[0]
    assert "model=(default) kind=pinned" in out


def test_default_model_drops_the_pin_of_whichever_target_the_run_selects(tmp_path, capsys):
    root = _write_project(tmp_path, _ALIAS_REGISTRY)

    assert _main(root, "--default-model", "--dry-run") == 0

    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("codex exec You are an independent")
    assert "model=(default) kind=chain" in out


def test_default_model_with_provider_only_drops_the_strongest_pin(tmp_path, capsys):
    root = _write_project(tmp_path, _ALIAS_REGISTRY)

    assert _main(root, "--default-model", "--provider", "codex", "--dry-run") == 0

    assert "model=(default) kind=pinned" in capsys.readouterr().out


def test_default_model_together_with_an_explicit_model_is_one_refused_line(tmp_path, capsys):
    root = _write_project(tmp_path, _ALIAS_REGISTRY)

    assert _main(root, "--default-model", "--provider", "codex:gpt-6.1-sol", "--dry-run") == 2

    err = capsys.readouterr().err
    assert err == (
        "second-opinion: --default-model cannot be combined with --provider 'codex:gpt-6.1-sol', "
        "which pins a model; drop one of them\n"
    )


def test_a_ladder_entry_with_the_default_token_runs_unpinned_and_the_listing_marks_it(tmp_path, capsys):
    registry = {**_ALIAS_REGISTRY, "second_opinion_policy": {"ladder": ["codex:default", "qwen"], "model_rule": "max"}}
    root = _write_project(tmp_path, registry)

    assert _main(root, "--list", gate=False) == 0
    listing = capsys.readouterr().out
    assert _main(root, "--dry-run") == 0
    dry = capsys.readouterr().out

    assert "rank 2: provider=codex model=(default) priors=gpt repo=worktree pin=default" in listing
    assert "rank 3: provider=qwen model=(default) priors=qwen repo=worktree\n" in listing
    assert "has no concrete id" not in listing
    assert "model=(default) kind=chain" in dry


def test_list_with_default_model_marks_every_candidate(tmp_path, capsys):
    root = _write_project(tmp_path, _ALIAS_REGISTRY)

    assert _main(root, "--list", "--default-model", gate=False) == 0

    out = capsys.readouterr().out
    assert "rank 2: provider=codex model=(default) priors=gpt repo=worktree pin=default" in out
    assert "has no concrete id" not in out


def test_a_default_run_on_the_sessions_own_family_stays_a_disclosed_pinned_run(tmp_path, capsys):
    root = _write_project(tmp_path, _ALIAS_REGISTRY)

    assert (
        _main(root, "--session-provider", "codex", "--session-model", "sol", "--provider", "codex:default", "--dry-run")
        == 0
    )

    out = capsys.readouterr().out
    assert "model=(default) kind=pinned" in out
    assert "warning: 'codex' is the session's own provider" in out


# --------------------------------------------------------------------------------------
# ADR-0024/D17: `carrier:model@effort`
# --------------------------------------------------------------------------------------

_EFFORT_REGISTRY = {
    **_ALIAS_REGISTRY,
    "providers": {
        **_ALIAS_REGISTRY["providers"],
        "claude": {
            **_ALIAS_REGISTRY["providers"]["claude"],
            "efforts": {"flag": "--effort {effort}", "levels": ["low", "medium", "high"]},
        },
        "codex": {
            **_ALIAS_ROW,
            "efforts": {"flag": "-c model_reasoning_effort={effort}", "levels": ["low", "high"]},
        },
    },
}
_FLAGS = ["--session-provider", "qwen", "--session-model", "q"]


def test_a_pinned_model_with_an_effort_sends_both_and_the_header_shows_the_effort(tmp_path, capsys):
    root = _write_project(tmp_path, _EFFORT_REGISTRY)

    assert _main(root, *_FLAGS, "--provider", "claude:opus@high", "--dry-run") == 0

    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("claude -p --output-format text --model opus --effort high ")
    assert "model=opus@high kind=pinned" in out


def test_an_alias_is_resolved_first_and_the_effort_follows_the_concrete_id(tmp_path, capsys):
    root = _write_project(tmp_path, _EFFORT_REGISTRY)
    _write_aliases(root, sol="gpt-6.1-sol")

    assert _main(root, *_FLAGS, "--provider", "codex:sol@high", "--dry-run") == 0

    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("codex exec --model gpt-6.1-sol -c model_reasoning_effort=high ")
    assert "model=sol→gpt-6.1-sol@high kind=pinned" in out


def test_default_with_an_effort_pins_no_model_and_sends_only_the_level(tmp_path, capsys):
    root = _write_project(tmp_path, _EFFORT_REGISTRY)

    assert _main(root, *_FLAGS, "--provider", "codex:default@high", "--dry-run") == 0

    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("codex exec -c model_reasoning_effort=high ")
    assert "--model" not in out.splitlines()[0]
    assert "model=(default)@high kind=pinned" in out


def test_an_effort_alone_keeps_the_rules_model_and_adds_the_level(tmp_path, capsys):
    root = _write_project(tmp_path, _EFFORT_REGISTRY)

    assert _main(root, *_FLAGS, "--provider", "claude:@low", "--dry-run") == 0

    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("claude -p --output-format text --model opus --effort low ")
    assert "model=opus@low kind=pinned" in out


def test_an_effort_on_a_carrier_without_efforts_is_one_refused_line_and_exit_2(tmp_path, capsys, monkeypatch):
    root = _write_project(tmp_path, _EFFORT_REGISTRY)
    _no_subprocess(monkeypatch)

    assert _main(root, *_FLAGS, "--provider", "qwen:big@high") == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("\n") == 1
    assert captured.err.startswith("second-opinion: provider 'qwen' declares no `efforts`, so the effort 'high'")


def test_an_effort_outside_the_levels_is_one_refused_line_naming_the_accepted_ones(tmp_path, capsys):
    root = _write_project(tmp_path, _EFFORT_REGISTRY)

    assert _main(root, *_FLAGS, "--provider", "claude:opus@max", "--dry-run") == 2

    assert capsys.readouterr().err == (
        "second-opinion: provider 'claude' does not accept the effort 'max'; its levels are: low, medium, high\n"
    )


def test_a_ladder_entry_with_an_effort_runs_with_it_and_the_listing_shows_it(tmp_path, capsys):
    registry = {
        **_EFFORT_REGISTRY,
        "second_opinion_policy": {"ladder": ["claude:opus@high", "qwen"], "model_rule": "max"},
    }
    root = _write_project(tmp_path, registry)

    assert _main(root, "--list", *_FLAGS[:2], "--session-provider", "codex", "--session-model", "sol", gate=False) == 0
    listing = capsys.readouterr().out
    assert _main(root, "--session-provider", "codex", "--session-model", "sol", "--dry-run") == 0
    dry = capsys.readouterr().out

    assert "rank 2: provider=claude model=opus@high priors=claude repo=worktree" in listing
    assert "rank 3: provider=qwen model=(default) priors=qwen repo=worktree\n" in listing
    assert dry.splitlines()[0].startswith("claude -p --output-format text --model opus --effort high ")


def test_default_model_drops_the_model_pin_and_keeps_the_effort(tmp_path, capsys):
    registry = {
        **_EFFORT_REGISTRY,
        "second_opinion_policy": {"ladder": ["codex:sol@high"], "model_rule": "max"},
    }
    root = _write_project(tmp_path, registry)

    assert _main(root, "--default-model", "--session-provider", "claude", "--session-model", "opus", "--dry-run") == 0

    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("codex exec -c model_reasoning_effort=high ")
    assert "model=(default)@high kind=chain" in out


def test_default_model_with_an_effort_alone_or_default_at_effort_is_allowed(tmp_path, capsys):
    root = _write_project(tmp_path, _EFFORT_REGISTRY)

    assert _main(root, *_FLAGS, "--default-model", "--provider", "codex:@high", "--dry-run") == 0
    assert _main(root, *_FLAGS, "--default-model", "--provider", "codex:default@high", "--dry-run") == 0

    assert capsys.readouterr().out.count("model=(default)@high kind=pinned") == 2


def test_default_model_with_an_explicit_model_and_effort_is_still_refused(tmp_path, capsys):
    root = _write_project(tmp_path, _EFFORT_REGISTRY)

    assert _main(root, *_FLAGS, "--default-model", "--provider", "codex:sol@high", "--dry-run") == 2

    assert "--default-model cannot be combined with --provider 'codex:sol@high'" in capsys.readouterr().err
