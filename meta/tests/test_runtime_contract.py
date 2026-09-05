"""Contract suite for the runtime declaration and the harness-command map (C57, design §7/F16).

The two joins are checked as one pure function over its inputs, so every fixture below states a
whole world — declarations, map, wiring — and mutates exactly one thing in it. That is what lets
"exactly one finding" mean something: a fixture that changed two facts could not tell which one
the checker reacted to.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import routing
from checks import runtime as runtime_checks

from common import runtime as runtime_declaration
from common.findings import exit_code
from common.runtime import (
    GENERATED_WIRING,
    OPTIONAL,
    OWN_TOOLING,
    POSIX_SHELL,
    REQUIRED,
    REQUIRED_ON,
    HarnessCommands,
    RuntimeDeclaration,
)

_KEYSTONE = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)

# The shape the real tree has: python3 everywhere, git only on the Codex route, both carried by
# a shell because the wiring is delivered as command *strings*.
WIRING = {
    "claude": ['python3 "$CLAUDE_PROJECT_DIR/_aitna/akmon/hooks/session-start-agent.py"'],
    "codex": ['python3 "$(git rev-parse --show-toplevel)/_aitna/akmon/hooks/codex-hook.py" session-start'],
}

DECLARATIONS = (
    RuntimeDeclaration(POSIX_SHELL, GENERATED_WIRING, REQUIRED),
    RuntimeDeclaration("python3", GENERATED_WIRING, REQUIRED),
    RuntimeDeclaration("git", GENERATED_WIRING, REQUIRED_ON + "codex"),
    RuntimeDeclaration("claude", OWN_TOOLING, OPTIONAL),
    RuntimeDeclaration("codex", OWN_TOOLING, OPTIONAL),
)

MAP = {
    "claude": HarnessCommands(binary="claude", operations={"version": ("--version",)}),
    "codex": HarnessCommands(binary="codex", operations={"version": ("--version",)}),
}


def _check(tmp_path, *, declarations=None, harness_commands=None, wiring=None):
    """Run the join in an empty tree, so only the seeded fact differs from the clean world."""
    return runtime_checks.check_runtime(
        declarations=DECLARATIONS if declarations is None else declarations,
        harness_commands=MAP if harness_commands is None else harness_commands,
        wiring=WIRING if wiring is None else wiring,
        root=tmp_path,
    )


def _codes(findings):
    return [finding.code for finding in findings]


def _only(findings, code: str, severity: str = "error"):
    assert [(f.severity, f.code) for f in findings] == [(severity, code)], _codes(findings)
    return findings[0]


def _without(binary: str, **overrides):
    return tuple(
        replace(d, **overrides) if d.binary == binary else d for d in DECLARATIONS
    )


# --------------------------------------------------------------------------------------
# the clean world, and the real tree
# --------------------------------------------------------------------------------------


def test_the_clean_world_has_no_findings(tmp_path):
    assert _check(tmp_path) == []


def test_the_real_tree_satisfies_its_own_declaration():
    """The join is not a fiction over fixtures: akmon's declaration matches akmon's wiring."""
    assert runtime_checks.check_declared_runtimes(_KEYSTONE) == []


def test_the_derivation_reproduces_the_declared_populations():
    per_vendor = runtime_checks.derive_generated_population(
        runtime_checks.generated_wiring(_KEYSTONE)
    )
    assert per_vendor["claude"] == {POSIX_SHELL, "python3"}
    assert per_vendor["codex"] == {POSIX_SHELL, "python3", "git"}


# --------------------------------------------------------------------------------------
# runtime.undeclared-binary
# --------------------------------------------------------------------------------------


def test_an_undeclared_generated_invocation_is_one_error(tmp_path):
    wiring = dict(WIRING, codex=[*WIRING["codex"], 'jq -r .x "$CLAUDE_PROJECT_DIR/x.json"'])
    finding = _only(_check(tmp_path, wiring=wiring), "runtime.undeclared-binary")
    assert "jq" in finding.message


def test_an_undeclared_own_tool_query_is_one_error(tmp_path):
    harness = dict(MAP, gemini=HarnessCommands(binary="gemini", operations={"version": ("-v",)}))
    finding = _only(_check(tmp_path, harness_commands=harness), "runtime.undeclared-binary")
    assert "gemini" in finding.message


# --------------------------------------------------------------------------------------
# runtime.unused-binary — a warn that keeps a non-strict run at zero
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("binary", "population"), [("jq", GENERATED_WIRING), ("gemini", OWN_TOOLING)]
)
def test_an_unused_declaration_is_one_warn(tmp_path, binary, population):
    declarations = (*DECLARATIONS, RuntimeDeclaration(binary, population, REQUIRED))
    findings = _check(tmp_path, declarations=declarations)
    finding = _only(findings, "runtime.unused-binary", severity="warn")
    assert binary in finding.message
    assert exit_code(findings, strict=False) == 0
    assert exit_code(findings, strict=True) == 1


def test_wiring_that_stops_needing_a_shell_leaves_the_carrier_unused(tmp_path):
    """Argv entries are executed directly, so the implicit POSIX-shell carrier disappears.

    The world here is deliberately git-free on both routes: dropping the shell from the real
    wiring would also drop the `$(git ...)` substitution, and a fixture that changes two facts
    cannot say which one the checker answered.
    """
    shell_free = (
        RuntimeDeclaration(POSIX_SHELL, GENERATED_WIRING, REQUIRED),
        RuntimeDeclaration("python3", GENERATED_WIRING, REQUIRED),
        RuntimeDeclaration("claude", OWN_TOOLING, OPTIONAL),
        RuntimeDeclaration("codex", OWN_TOOLING, OPTIONAL),
    )
    wiring = {
        "claude": [["python3", "/x/session-start-agent.py"]],
        "codex": [["python3", "/x/codex-hook.py", "session-start"]],
    }
    findings = _check(tmp_path, declarations=shell_free, wiring=wiring)
    finding = _only(findings, "runtime.unused-binary", severity="warn")
    assert POSIX_SHELL in finding.message
    assert exit_code(findings, strict=False) == 0


# --------------------------------------------------------------------------------------
# runtime.wrong-population
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("binary", [POSIX_SHELL, "python3", "git", "claude", "codex"])
def test_a_missing_population_field_is_one_wrong_population(tmp_path, binary):
    declarations = _without(binary, population="")
    finding = _only(_check(tmp_path, declarations=declarations), "runtime.wrong-population")
    assert binary in finding.message


@pytest.mark.parametrize("binary", [POSIX_SHELL, "python3", "git", "claude", "codex"])
def test_the_other_population_is_one_wrong_population(tmp_path, binary):
    other = OWN_TOOLING if binary in (POSIX_SHELL, "python3", "git") else GENERATED_WIRING
    finding = _only(
        _check(tmp_path, declarations=_without(binary, population=other)),
        "runtime.wrong-population",
    )
    assert binary in finding.message


# --------------------------------------------------------------------------------------
# runtime.wrong-modality
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("binary", "wrong"),
    [
        (POSIX_SHELL, OPTIONAL),
        (POSIX_SHELL, REQUIRED_ON + "codex"),
        ("python3", OPTIONAL),
        ("python3", REQUIRED_ON + "claude"),
        ("git", REQUIRED),
        ("git", REQUIRED_ON + "claude"),
        ("claude", REQUIRED),
        ("codex", REQUIRED),
    ],
)
def test_a_wrong_modality_is_one_error(tmp_path, binary, wrong):
    finding = _only(
        _check(tmp_path, declarations=_without(binary, modality=wrong)), "runtime.wrong-modality"
    )
    assert binary in finding.message


def test_modality_follows_the_wiring_rather_than_the_declaration(tmp_path):
    """Drop git from the Codex route and the declaration that named it becomes the defect."""
    wiring = dict(WIRING, codex=['python3 "$CODEX_PROJECT_DIR/x/codex-hook.py" session-start'])
    _only(_check(tmp_path, wiring=wiring), "runtime.unused-binary", severity="warn")


# --------------------------------------------------------------------------------------
# runtime.duplicate-query-owner
# --------------------------------------------------------------------------------------


def test_a_harness_binary_spelled_outside_the_map_is_one_error(tmp_path):
    source = tmp_path / "tools" / "thing.py"
    source.parent.mkdir(parents=True)
    source.write_text('import subprocess\nsubprocess.run(["codex", "exec"])\n', encoding="utf-8")
    finding = _only(_check(tmp_path), "runtime.duplicate-query-owner")
    assert "codex" in finding.message


def test_a_second_query_map_is_one_error(tmp_path):
    source = tmp_path / "bin" / "other_map.py"
    source.parent.mkdir(parents=True)
    source.write_text('COMMANDS = {"claude": ("--version",)}\n', encoding="utf-8")
    _only(_check(tmp_path), "runtime.duplicate-query-owner")


def test_the_map_itself_is_never_its_own_duplicate(tmp_path):
    owner = tmp_path / "bin" / "runtime.py"
    owner.parent.mkdir(parents=True)
    owner.write_text('HARNESS = {"claude": "claude", "codex": "codex"}\n', encoding="utf-8")
    assert _check(tmp_path) == []


def test_tests_and_data_are_not_scanned_for_literals(tmp_path):
    """A fixture naming a harness describes the map; the registry refers to it by name."""
    fixture = tmp_path / "meta" / "tests" / "test_x.py"
    fixture.parent.mkdir(parents=True)
    fixture.write_text('SPEC = {"harness": "claude"}\n', encoding="utf-8")
    data = tmp_path / "tools" / "model_routing" / "registry.json"
    data.parent.mkdir(parents=True)
    data.write_text('{"anthropic": {"second_opinion": {"harness": "claude"}}}\n', encoding="utf-8")
    assert _check(tmp_path) == []


def test_the_real_tree_spells_no_harness_binary_outside_the_map():
    assert runtime_checks.own_tool_literals(_KEYSTONE, runtime_declaration.harness_binaries()) == []


# --------------------------------------------------------------------------------------
# the map owns the executable and the operation prefix
# --------------------------------------------------------------------------------------


def test_c57_lock_text_pins_prefix_ownership_without_the_old_overclaim():
    """The task lock states the same narrow ownership boundary as the implementation."""
    tasks = (_KEYSTONE / "meta" / "TASKS.md").read_text(encoding="utf-8")
    entries = [line for line in tasks.splitlines() if line.startswith("- C57 · ")]

    assert len(entries) == 1
    entry = entries[0]
    assert (
        "map is the sole owner and constructor of the executable-plus-operation prefix"
        in entry
    )
    assert "sole executable owner and constructor" not in entry


def test_the_map_constructs_the_second_opinion_argv():
    import routing

    spec = {"harness": "claude", "operation": "review", "model_flag": "--model {model}"}
    assert routing.second_opinion_command(spec, "review this") == [
        "claude", "-p", "--output-format", "text", "review this",
    ]
    assert routing.second_opinion_command(spec, "review this", model="opus") == [
        "claude", "-p", "--output-format", "text", "--model", "opus", "review this",
    ]


def test_an_unknown_harness_or_operation_is_refused():
    with pytest.raises(ValueError):
        runtime_declaration.harness_command("gemini", "version")
    with pytest.raises(ValueError):
        runtime_declaration.harness_command("claude", "app-server")


def test_the_version_query_comes_from_the_same_owner():
    assert runtime_declaration.version_command("claude") == ["claude", "--version"]
    assert runtime_declaration.version_command("codex") == ["codex", "--version"]


# --- compound command strings (N-review finding 5) ------------------------------------------
#
# A hook command is a shell string, not one invocation. Reading only its head closed the join
# over the first binary and left everything behind `&&`, `;` or `|` both undeclared and unseen.


@pytest.mark.parametrize(
    "command, expected",
    [
        ("python3 hook.py && jq . | sed s/a/b/", {POSIX_SHELL, "python3", "jq", "sed"}),
        ("python3 hook.py; rm -rf /tmp/x", {POSIX_SHELL, "python3", "rm"}),
        ("FOO=1 python3 a.py || curl -s http://x", {POSIX_SHELL, "python3", "curl"}),
        ("python3 a.py & python3 b.py", {POSIX_SHELL, "python3"}),
        ('cd "$(git rev-parse --show-toplevel)" && python3 bin/verify.py',
         {POSIX_SHELL, "git", "python3"}),
        ("if test -f x; then python3 a.py; fi", {POSIX_SHELL, "python3"}),
        # An operator inside a quoted argument is data, not a segment boundary.
        ('python3 hook.py --arg "a | b"', {POSIX_SHELL, "python3"}),
        ('python3 -c "print(1); print(2)"', {POSIX_SHELL, "python3"}),
        # Wrappers run the command after them; reading the wrapper loses the real binary.
        ("command git status", {POSIX_SHELL, "git"}),
        ("exec python3 hook.py", {POSIX_SHELL, "python3"}),
        # An *external* wrapper is itself a host requirement, so it is counted alongside the
        # command it runs; `command`/`exec` are shell-provided and are not.
        ("env FOO=1 python3 hook.py", {POSIX_SHELL, "env", "python3"}),
        ("nice python3 hook.py", {POSIX_SHELL, "nice", "python3"}),
        ("xargs jq", {POSIX_SHELL, "xargs", "jq"}),
        # `while`/`until` are followed by a command, so the segment walk is correct for them.
        ("while python3 check.py; do jq .; done", {POSIX_SHELL, "python3", "jq"}),
        # Grouping is a shell construct, not an executable called "(python3".
        ("(python3 a.py; jq .) | sed s/a/b/", {POSIX_SHELL, "python3", "jq", "sed"}),
        # A redirection target is a path.
        ("python3 a.py > /tmp/out 2>&1", {POSIX_SHELL, "python3"}),
    ],
)
def test_every_executable_segment_is_a_declared_binary(command, expected):
    assert runtime_checks._binaries_in_command(command) == expected


@pytest.mark.parametrize("builtin", ["cd /tmp", "echo hi", "export FOO=1", "printf x"])
def test_a_shell_builtin_needs_no_host_declaration(builtin):
    """POSIX requires the shell to provide these, so declaring the shell already covers them."""
    assert runtime_checks._binaries_in_command(builtin) == {POSIX_SHELL}


def test_a_binary_hidden_behind_a_pipe_is_one_undeclared_error(tmp_path):
    wiring = dict(WIRING, claude=['python3 "$CLAUDE_PROJECT_DIR/x.py" | jq -r .decision'])
    finding = _only(_check(tmp_path, wiring=wiring), "runtime.undeclared-binary")
    assert "jq" in finding.message


# --- retired registry keys (N-review finding 6) ---------------------------------------------


@pytest.mark.parametrize("required", [True, False])
def test_a_registry_still_using_the_retired_keys_is_refused(required):
    """`cli`/`invoke` moved into the harness map; a stale config must fail, not fall back."""
    stale = {"anthropic": {"second_opinion": {
        "cli": "claude", "invoke": "claude -p --output-format text",
        "report_dir": ".codex/second-opinion/",
    }}}
    with pytest.raises(KeyError):
        routing.second_opinion_spec(stale, "anthropic", required=required)


@pytest.mark.parametrize("required", [True, False])
def test_an_upgraded_registry_under_a_stale_overlay_is_refused(required):
    """The real upgrade path: the shipped registry is new, the project overlay is not.

    `_deep_merge` layers the overlay *over* the registry, so `harness`/`operation` survive and
    the retired pair rides along beside them. The merged spec then satisfies every presence
    check while carrying two contradictory statements of the same command — the exact shape a
    standalone-stale fixture cannot reach.
    """
    shipped = {"anthropic": {"second_opinion": {
        "harness": "claude", "operation": "review", "report_dir": ".codex/second-opinion/",
    }}}
    overlay = {"anthropic": {"second_opinion": {
        "cli": "claude", "invoke": "claude -p --output-format text",
    }}}
    merged = routing._deep_merge(shipped, overlay)
    assert set(merged["anthropic"]["second_opinion"]) == {
        "harness", "operation", "report_dir", "cli", "invoke",
    }, "the merge keeps both, which is why presence checks alone cannot catch this"
    with pytest.raises(KeyError) as raised:
        routing.second_opinion_spec(merged, "anthropic", required=required)
    assert "retired" in str(raised.value)


def test_a_clean_overlay_still_resolves_after_the_merge():
    """The negative boundary: an overlay that only overrides policy must keep working."""
    shipped = {"anthropic": {"second_opinion": {
        "harness": "claude", "operation": "review", "report_dir": ".codex/second-opinion/",
    }}}
    overlay = {"anthropic": {"second_opinion": {"report_dir": ".local/second-opinion/"}}}
    spec = routing.second_opinion_spec(routing._deep_merge(shipped, overlay), "anthropic")
    assert spec["report_dir"] == ".local/second-opinion/"
    assert spec["harness"] == "claude"


def test_no_shipped_registry_or_document_still_spells_the_retired_keys():
    root = Path(__file__).resolve().parents[2]
    sources = [root / "tools" / "model_routing" / "registry.json"]
    sources += sorted(root.glob("meta/design/*.md"))
    offenders = [
        path.relative_to(root).as_posix()
        for path in sources
        if any(key in path.read_text(encoding="utf-8") for key in ('"cli":', '"invoke":'))
    ]
    assert offenders == []


@pytest.mark.parametrize(
    "command",
    [
        "python3 `jq -r .x` a.py",         # a substitution syntax this parser does not read
        'python3 "unbalanced',             # a token stream shlex cannot trust
        "python3 $((1 + 2)).py",           # arithmetic, which is not a command substitution
        "for f in *.py; do python3 \"$f\"; done",   # a word list, not a command list
        "case $x in a) python3 a.py;; esac",
    ],
)
def test_a_command_the_parser_cannot_read_is_refused_rather_than_under_counted(command):
    with pytest.raises(runtime_checks.UnparsedCommand):
        runtime_checks._binaries_in_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "env -i python3 a.py",             # -i is an option, not the command
        "sudo -u root python3 a.py",       # -u takes its own argument
        "nice -n 10 python3 a.py",
        "xargs -n1 jq",
        "timeout 5 python3 a.py",          # a mandatory positional before the command
    ],
)
def test_a_wrapper_carrying_its_own_options_is_refused(command):
    """Skipping the wrapper name alone reported the *option* as the binary.

    Each wrapper has its own option grammar, and encoding five of them correctly only moves the
    defect to the sixth. A refusal states the limit; a confident wrong answer hides it.
    """
    with pytest.raises(runtime_checks.UnparsedCommand):
        runtime_checks._binaries_in_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "foo() { python3 a.py; }",         # a definition, not an invocation of `foo`
        "foo () { python3 a.py; }",
        "echo() { jq .; }",                # a function may be named after a builtin
        "printf() { git status; }",
        "command() { jq .; }",             # or after a wrapper
        "nice() { jq .; }",
        "(( x = 1 )) && python3 a.py",     # an arithmetic command; `x` is not a binary
        "[[ -f a ]] && python3 a.py",      # a conditional with its own operand grammar
        "[[ -f a && -f b ]] && python3 a.py",   # the inner `&&` restarted the segment walk
        "coproc python3 a.py",
        "time python3 a.py",               # a keyword in some shells, a program in others
        "nice time python3 a.py",          # and the ambiguity survives behind a wrapper
    ],
)
def test_a_construct_with_a_grammar_of_its_own_is_refused(command):
    """These parsed *confidently and wrongly*, which is worse than a stated refusal.

    Each construct opens a grammar that is not a command list, so the segment walk read its
    operands as binaries: `foo`, `x`, `-f`, `[[`. `time` fails for a different reason — it is a
    shell reserved word in some shells and `/usr/bin/time` in others, so the command string does
    not say whether a host binary is needed at all.
    """
    with pytest.raises(runtime_checks.UnparsedCommand):
        runtime_checks._binaries_in_command(command)


@pytest.mark.parametrize(
    "command, expected",
    [
        ("( python3 a.py )", {"python3"}),          # grouping is still read
        ('echo "a (( b" && python3 a.py', {"python3"}),   # refused tokens only when they are tokens
        ('sh -c "x [[ y" && python3 a.py', {"sh", "python3"}),
    ],
)
def test_the_refusals_do_not_swallow_the_supported_grammar(command, expected):
    """A refusal set that also refuses valid wiring would be bought with false failures."""
    assert runtime_checks._binaries_in_command(command) == {POSIX_SHELL, *expected}



@pytest.mark.parametrize(
    "command, expected",
    [
        # quoting decides what a `$(` is: data inside single quotes, a substitution otherwise
        ("printf %s '$(jq .)'", set()),
        ('echo "$(git status)" && python3 a.py', {"git", "python3"}),
        ("echo '`date`'", set()),                  # a backtick in single quotes is data too
        # nesting is counted, not cut at the first `)`
        ("echo $(jq -r .x $(git rev-parse --show-toplevel)/f.json)", {"jq", "git"}),
        ('echo $(printf %s ")") && python3 a.py', {"python3"}),
        # an assignment may hold a substitution; the binary is still the word after it
        ("X=$(git rev-parse HEAD) python3 a.py", {"git", "python3"}),
    ],
)
def test_a_substitution_is_read_with_quoting_and_nesting_honoured(command, expected):
    """A regex over the raw string got this wrong in both directions.

    `printf %s '$(jq .)'` declared `jq` out of a literal string, and `[^)]*` stopped at the
    first `)`, so the *outer* command of a nested substitution was never read.
    """
    assert runtime_checks._binaries_in_command(command) == {POSIX_SHELL, *expected}


@pytest.mark.parametrize(
    "command",
    [
        "$RUNNER hook.py",                 # declared a binary literally named `$RUNNER`
        '"$RUNNER" hook.py',
        "$HOME/bin/tool a.py",
        "$(which python3) a.py",           # the substitution names the binary, not the string
        "echo $(unterminated",
    ],
)
def test_a_head_the_command_string_does_not_spell_is_refused(command):
    """An expansion in head position is not a binary name; it is the absence of one."""
    with pytest.raises(runtime_checks.UnparsedCommand):
        runtime_checks._binaries_in_command(command)


@pytest.mark.parametrize(
    "command, expected",
    [
        ("python3 hook.py --mode case", {"python3"}),
        ("python3 hook.py --sort time", {"python3"}),
        ("python3 hook.py --key in", {"python3"}),
        ('python3 a.py --pattern "[["', {"python3"}),
        ("python3 a.py --label function", {"python3"}),
    ],
)
def test_a_refused_word_used_as_an_argument_is_not_a_construct(command, expected):
    """The refusal is about a *construct*, so it belongs to head position only.

    Applied to every token, it turned an ordinary `--mode case` into an unreadable command —
    a false failure bought with nothing, since an argument opens no grammar.
    """
    assert runtime_checks._binaries_in_command(command) == {POSIX_SHELL, *expected}



@pytest.mark.parametrize(
    "command, expected",
    [
        ('python3 a.py "&&" evil.py', {"python3"}),
        ('python3 a.py ";" evil.py', {"python3"}),
        ("python3 a.py '|' evil.py", {"python3"}),
        ('python3 "" evil.py', {"python3"}),        # an empty token is not an operator either
        ("python3 a.py && jq .", {"python3", "jq"}),          # the real operator still splits
        ('echo "a && b" && python3 a.py', {"python3"}),
    ],
)
def test_an_argument_that_is_exactly_an_operator_is_still_an_argument(command, expected):
    """Quote removal made `"&&"` and `&&` the same string, so the argument ended the segment.

    The earlier carrier used a *multi-word* quoted argument, which never produced a token equal
    to an operator and so could not see this. Structure is now read from the token as written.
    """
    assert runtime_checks._binaries_in_command(command) == {POSIX_SHELL, *expected}


@pytest.mark.parametrize(
    "command, expected",
    [
        ("python3 a.py\njq .", {"python3", "jq"}),
        ('python3 -c "a\nb" && jq .', {"python3", "jq"}),    # a quoted newline is not a break
    ],
)
def test_a_newline_separates_two_commands(command, expected):
    """`_SEPARATORS` listed `\n`, but `shlex` treats it as whitespace, so the entry was dead.

    A second line's head was silently swallowed as an argument of the first line's command.
    """
    assert runtime_checks._binaries_in_command(command) == {POSIX_SHELL, *expected}


def test_a_here_document_is_refused_rather_than_swallowed():
    """`sh <<EOF … EOF` feeds a whole script this parser never reads.

    The body was consumed as arguments of `sh`, so every binary in it went unreported — the
    silent under-count the refusal set exists to prevent. `<<<` stays readable: a here-string is
    one word, not a body.
    """
    with pytest.raises(runtime_checks.UnparsedCommand):
        runtime_checks._binaries_in_command("sh <<EOF\njq .\nEOF")
    assert runtime_checks._binaries_in_command('python3 a.py <<< "text"') == {
        POSIX_SHELL, "python3",
    }



@pytest.mark.parametrize(
    "command, expected",
    [
        ("python3 a.py#x && jq .", {"python3", "jq"}),   # `#` mid-word is a literal
        ("python3 a.py --tag '#1' && jq .", {"python3", "jq"}),
        ("python3 a.py # note\njq .", {"python3", "jq"}),   # a comment ends at the newline
        ("python3 a.py --tag #1 && jq .", {"python3"}),  # word-initial: a real comment
    ],
)
def test_a_comment_starts_only_at_a_word_start(command, expected):
    """`shlex` starts a comment at a `#` anywhere, which is not what a shell does.

    `a.py#x && jq .` lost everything from the `#`, so `jq` went unreported — the silent
    under-count again, this time from a tokenizer default rather than from the walk.
    """
    assert runtime_checks._binaries_in_command(command) == {POSIX_SHELL, *expected}


def test_an_empty_word_is_not_a_binary():
    """`"" evil.py` declared a runtime whose name is the empty string."""
    with pytest.raises(runtime_checks.UnparsedCommand):
        runtime_checks._binaries_in_command('"" evil.py')


def test_the_tab_form_of_a_here_document_is_refused_too():
    """`<<-EOF` reaches the walk as `<<` + `-EOF`, so one entry covers both spellings."""
    with pytest.raises(runtime_checks.UnparsedCommand):
        runtime_checks._binaries_in_command("sh <<-EOF\njq .\nEOF")



@pytest.mark.parametrize(
    "command, expected",
    [
        # a word that mixes a quoted part with an unquoted one is one word to a shell
        ('python3 "$(git rev-parse --show-toplevel)"/h.py && jq .', {"python3", "git", "jq"}),
        ("python3 'a'b && jq .", {"python3", "jq"}),
        # a backslash escapes the next character rather than making the command unreadable
        ("python3 a.py \\&\\& evil.py", {"python3"}),
        ("my\\ tool a.py", {"my tool"}),
    ],
)
def test_a_word_that_mixes_quoting_is_still_one_word(command, expected):
    """Two `shlex` passes — one quoted, one not — disagreed on exactly this shape.

    `"$DIR"/hook.py` is one word to a shell and two to the raw pass, so the guard against that
    disagreement refused a legitimate command and blamed a backslash for it. Tokenizing the
    already-scanned text directly removes the reconciliation instead of tightening it.
    """
    assert runtime_checks._binaries_in_command(command) == {POSIX_SHELL, *expected}


def test_grouping_survives_the_arithmetic_refusal():
    """`((` is refused as one token; `( (` with a space is ordinary nested grouping."""
    with pytest.raises(runtime_checks.UnparsedCommand):
        runtime_checks._binaries_in_command("(( x = 1 )) && python3 a.py")
    assert runtime_checks._binaries_in_command("( ( python3 a.py ) ) && jq .") == {
        POSIX_SHELL, "python3", "jq",
    }



@pytest.mark.parametrize(
    "command",
    [
        "python3 a.py --re x((y",          # declared a binary called `y`
        "python3 foo(bar)",                # declared `bar`
        "python3 ((x))",                   # declared `x`
    ],
)
def test_a_parenthesis_that_cannot_be_grouping_is_refused(command):
    """Each is a shell syntax error that the walk answered with a confident binary name.

    `(` glued to a word is either the `()` of a definition or nothing this parser reads, and
    `((` is refused wherever it appears — quoted it is a word and never arrives as an operator,
    so unlike `case` or `time` it cannot be a legitimate argument.
    """
    with pytest.raises(runtime_checks.UnparsedCommand):
        runtime_checks._binaries_in_command(command)


@pytest.mark.parametrize(
    "command, expected",
    [
        ("2>&1 python3 a.py", {"python3"}),          # declared `2` and missed `python3`
        ("2> /dev/null python3 a.py", {"python3"}),
        (">log python3 a.py", {"python3"}),
        ("python3 a.py 2>&1 | jq .", {"python3", "jq"}),
    ],
)
def test_a_redirection_may_precede_the_command(command, expected):
    """A redirection prefix is valid shell, and its file-descriptor number is not a binary."""
    assert runtime_checks._binaries_in_command(command) == {POSIX_SHELL, *expected}



@pytest.mark.parametrize(
    "command",
    ["python3 a.py <(jq .)", "python3 a.py >(jq .)", "diff <(jq . a) <(jq . b)"],
)
def test_process_substitution_is_refused(command):
    """It *runs* the command inside it, and the redirection branch ate the `(` before it.

    `python3 a.py <(jq .)` reported no `jq`; `diff <(jq . a) <(jq . b)` reported one — the same
    construct read two ways depending on where it sat, which is worse than either answer.
    """
    with pytest.raises(runtime_checks.UnparsedCommand):
        runtime_checks._binaries_in_command(command)


def test_an_ordinary_redirection_is_not_a_process_substitution():
    assert runtime_checks._binaries_in_command("python3 a.py < in.txt && jq .") == {
        POSIX_SHELL, "python3", "jq",
    }
    assert runtime_checks._binaries_in_command('python3 a.py --re "<(x" && jq .') == {
        POSIX_SHELL, "python3", "jq",
    }


def test_an_unreadable_command_is_one_error_and_does_not_shrink_the_population(tmp_path):
    """A refusal must be louder than a quiet under-count, and must not fake a clean join.

    Dropping the command silently would also drop the binaries it invokes, which can turn a
    `required` modality into `required-on:<the other vendor>` — a refusal that *causes* a
    second wrong finding is worse than the gap it reports.
    """
    wiring = dict(WIRING, claude=[*WIRING["claude"], "python3 `jq -r .x` hook.py"])
    _only(_check(tmp_path, wiring=wiring), "runtime.unparsed-command")


def test_an_external_wrapper_is_itself_a_declared_requirement(tmp_path):
    """`nice python3 hook.py` needs both binaries; reading only the wrapped one under-counts."""
    wiring = dict(WIRING, claude=['nice python3 "$CLAUDE_PROJECT_DIR/hook.py"'])
    finding = _only(_check(tmp_path, wiring=wiring), "runtime.undeclared-binary")
    assert "nice" in finding.message
