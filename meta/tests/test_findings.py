"""Contract suite for the shared finding envelope (C51, design §1).

Every rule the envelope declares carries a seeded violation here: an invalid severity, an
invalid or retired ``code``, a ``fix`` that is absent, empty, multi-line or multi-sentence, a
serializer that mutates or drifts, a second owner for the mapping, an adopter that kept the old
``level`` field or its own renderer, a rendered line missing or reordering a field, a ``--json``
mode arriving before C59, and every cell of the severity × strict-state exit matrix — the last
parameterized over the three strict-capable adopters, with sync's 0/1/2 vocabulary carried
separately, so a representative implementation cannot hide a stale one.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from common import findings as findings_mod
from common.findings import (
    CODE_RE,
    RETIRED_CODES,
    SEVERITIES,
    Finding,
    exit_code,
    line_safe,
    print_findings,
    render,
)

_KEYSTONE = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)

#: Every adopter of the envelope, by the name used in test ids, and its source file.
ADOPTER_SOURCES = {
    "verify": _KEYSTONE / "bin" / "verify.py",
    "sync": _KEYSTONE / "bin" / "sync.py",
    "validate": _KEYSTONE / "meta" / "bin" / "validate.py",
    "self_ci": _KEYSTONE / "meta" / "self_ci.py",
}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


validate = _load("akmon_validate_findings", ADOPTER_SOURCES["validate"])
self_ci = _load("akmon_self_ci_findings", ADOPTER_SOURCES["self_ci"])

import verify  # noqa: E402  (conftest puts bin/ on sys.path)


def _finding(**overrides) -> Finding:
    fields = {
        "severity": "warn",
        "code": "area.rule",
        "message": "something is off",
        "target": "some/file.md",
        "fix": "Do the one thing that fixes it.",
    }
    fields.update(overrides)
    return Finding(**fields)


# --------------------------------------------------------------------------------------
# severity — the closed vocabulary, and the absence of `level`
# --------------------------------------------------------------------------------------


def test_severity_vocabulary_is_exactly_ok_warn_error():
    assert SEVERITIES == ("ok", "warn", "error")


@pytest.mark.parametrize("severity", SEVERITIES)
def test_every_declared_severity_constructs(severity):
    assert _finding(severity=severity).severity == severity


@pytest.mark.parametrize("severity", ["fatal", "OK", "info", "", None])
def test_out_of_vocabulary_severity_is_rejected(severity):
    with pytest.raises(ValueError):
        _finding(severity=severity)


def test_finding_has_severity_and_no_level_field():
    finding = _finding()
    assert finding.severity == "warn"
    assert not hasattr(finding, "level")


def test_constructor_rejects_a_level_keyword():
    """F1 is a rename, not an alias: `level=` must not construct, even positionally-shaped."""
    with pytest.raises(TypeError):
        Finding(level="warn", code="area.rule", message="m", target="t", fix="Fix it.")


# --------------------------------------------------------------------------------------
# code — the dotted slug, and the retired-code record
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code",
    ["boundary.missing-banner", "caps.always-loaded", "a.b", "area.rule.sub", "x1.y2-z3"],
)
def test_valid_dotted_slugs_construct(code):
    assert _finding(code=code).code == code


@pytest.mark.parametrize(
    "code",
    [
        "nodot",  # no dot at all
        "Area.rule",  # uppercase
        "area .rule",  # whitespace
        "area..rule",  # empty segment
        ".rule",  # empty leading segment
        "area.",  # empty trailing segment
        "area.ru--le",  # repeated hyphen
        "-area.rule",  # leading hyphen
        "area.rule-",  # trailing hyphen
        "area.rule ",  # trailing whitespace
        "area.rule\n",  # `$` alone accepts a final newline; validation uses fullmatch
        "area.rule\r",  # every line separator is invalid in every rendered field
        "area.rule\u2028",
    ],
)
def test_invalid_dotted_slugs_are_rejected(code):
    with pytest.raises(ValueError):
        _finding(code=code)


def test_the_grammar_is_the_one_the_design_declares():
    assert CODE_RE.pattern == r"^[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[a-z0-9]+(?:-[a-z0-9]+)*)+$"


def test_a_code_in_the_retired_record_is_rejected(monkeypatch):
    """Non-reuse is the half a consumer greps for: a spent slug never comes back."""
    monkeypatch.setattr(findings_mod, "RETIRED_CODES", frozenset({"area.rule"}))
    with pytest.raises(ValueError):
        _finding(code="area.rule")
    assert _finding(code="area.other").code == "area.other"


def test_the_retired_record_holds_only_valid_slugs():
    for code in RETIRED_CODES:
        assert CODE_RE.fullmatch(code), code


def test_no_live_code_appears_in_the_retired_record():
    live = {code for codes in _adopter_codes().values() for code in codes}
    assert live.isdisjoint(RETIRED_CODES)


# --------------------------------------------------------------------------------------
# message · target · fix
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("message", ["", "   ", None])
def test_message_must_be_present(message):
    with pytest.raises(ValueError):
        _finding(message=message)


@pytest.mark.parametrize(
    "separator",
    ["\n", "\r", "\r\n", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"],
)
@pytest.mark.parametrize("field", ["message", "target", "fix"])
def test_every_rendered_field_must_be_one_line(field, separator):
    with pytest.raises(ValueError):
        _finding(**{field: f"first{separator}second"})


@pytest.mark.parametrize(
    ("separator", "escaped"),
    [
        ("\n", r"\n"),
        ("\r", r"\r"),
        ("\r\n", r"\r\n"),
        ("\v", r"\v"),
        ("\f", r"\f"),
        ("\x1c", r"\u001c"),
        ("\x1d", r"\u001d"),
        ("\x1e", r"\u001e"),
        ("\x85", r"\u0085"),
        ("\u2028", r"\u2028"),
        ("\u2029", r"\u2029"),
    ],
)
def test_line_safe_escapes_only_the_separator(separator, escaped):
    assert line_safe(f"до{separator}после") == f"до{escaped}после"


def test_an_empty_target_is_valid():
    """A finding about the tree as a whole has no artifact to name."""
    assert _finding(target="").target == ""


def test_a_non_string_target_is_rejected():
    with pytest.raises(ValueError):
        _finding(target=Path("some/file.md"))


def test_fix_is_required():
    with pytest.raises(TypeError):
        Finding("warn", "area.rule", "message", "target")


@pytest.mark.parametrize("fix", ["", "   ", None])
def test_an_empty_fix_is_rejected(fix):
    with pytest.raises(ValueError):
        _finding(fix=fix)


@pytest.mark.parametrize("fix", ["Do this.\nThen that.", "Do this.\r\nThen that."])
def test_a_multi_line_fix_is_rejected(fix):
    with pytest.raises(ValueError):
        _finding(fix=fix)


@pytest.mark.parametrize(
    "fix",
    [
        "Do this. Then do that.",
        "Do this? Then do that.",
        "Do this!  Then do that.",
        "Do this.Then do that.",
        "Do this?Then do that.",
        "Do this!Then do that.",
    ],
)
def test_a_multi_sentence_fix_is_rejected(fix):
    with pytest.raises(ValueError):
        _finding(fix=fix)


@pytest.mark.parametrize(
    "fix",
    [
        "Run akmon sync to regenerate CLAUDE.md.",
        "Restore meta/CONCEPT.md from git history.",
        "Add '*.env' and '!*.env.example' to .gitignore.",
        "Set the frontmatter name to demo.",
    ],
)
def test_ordinary_one_sentence_fixes_construct(fix):
    assert _finding(fix=fix).fix == fix


def test_ok_findings_carry_a_fix_too():
    """An `ok` finding states the invariant to keep; the envelope refuses a blank one."""
    assert _finding(severity="ok", fix="Keep every required anchor in place.").fix
    with pytest.raises(ValueError):
        _finding(severity="ok", fix="")


# --------------------------------------------------------------------------------------
# serialization — one owner, pure, JSON-safe
# --------------------------------------------------------------------------------------


def test_to_dict_pins_the_exact_schema():
    assert _finding().to_dict() == {
        "severity": "warn",
        "code": "area.rule",
        "message": "something is off",
        "target": "some/file.md",
        "fix": "Do the one thing that fixes it.",
    }


def test_to_dict_has_no_level_key():
    assert "level" not in _finding().to_dict()


def test_to_dict_preserves_unicode_and_an_empty_target():
    finding = _finding(message="стрелка → есть", target="", fix="Убери «шум» из индекса.")
    payload = finding.to_dict()
    assert payload["message"] == "стрелка → есть"
    assert payload["target"] == ""
    assert json.loads(json.dumps(payload, ensure_ascii=False)) == payload


def test_to_dict_does_not_mutate_the_finding():
    finding = _finding()
    before = (finding.severity, finding.code, finding.message, finding.target, finding.fix)
    payload = finding.to_dict()
    payload["severity"] = "error"
    payload["code"] = "other.rule"
    after = (finding.severity, finding.code, finding.message, finding.target, finding.fix)
    assert before == after


def test_to_dict_is_deterministic():
    finding = _finding()
    assert finding.to_dict() == finding.to_dict()


def test_to_dict_output_passes_json_dumps_directly():
    json.dumps(_finding().to_dict())


def test_exactly_one_canonical_serializer_exists():
    """A second owner of the field mapping is the defect, not only a copy in an adopter."""
    tree = ast.parse(ADOPTER_SOURCES["verify"].read_text(encoding="utf-8"))  # sanity: parses
    assert tree is not None
    module = ast.parse((_KEYSTONE / "common" / "findings.py").read_text(encoding="utf-8"))
    serializers = [
        node.name
        for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _returns_the_canonical_mapping(node)
    ]
    assert serializers == ["to_dict"]


def _returns_the_canonical_mapping(node) -> bool:
    canonical = {"severity", "code", "message", "target", "fix"}
    for child in ast.walk(node):
        if canonical <= _mapping_keys(child):
            return True
    return False


def _mapping_keys(node) -> set[str]:
    if isinstance(node, ast.Dict):
        return {key.value for key in node.keys if isinstance(key, ast.Constant)}
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict":
        return {keyword.arg for keyword in node.keywords if keyword.arg is not None}
    return set()


def test_a_second_serializer_built_with_dict_call_is_detected():
    module = ast.parse(
        "def second(f):\n"
        "    return dict(severity=f.severity, code=f.code, message=f.message, "
        "target=f.target, fix=f.fix)\n"
    )
    function = module.body[0]
    assert _returns_the_canonical_mapping(function)


@pytest.mark.parametrize("name", sorted(ADOPTER_SOURCES))
def test_no_adopter_repeats_the_field_mapping(name):
    module = ast.parse(ADOPTER_SOURCES[name].read_text(encoding="utf-8"))
    for node in ast.walk(module):
        assert not {"severity", "code", "message", "target", "fix"} <= _mapping_keys(node), (
            f"{name} carries its own field mapping; call Finding.to_dict()"
        )


def test_findings_module_imports_only_the_standard_library():
    module = ast.parse((_KEYSTONE / "common" / "findings.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    stdlib = getattr(sys, "stdlib_module_names", None) or {
        "re",
        "sys",
        "dataclasses",
        "typing",
        "json",
        "pathlib",
        "argparse",
        "os",
    }
    assert imported <= set(stdlib), imported - set(stdlib)


# --------------------------------------------------------------------------------------
# rendering — the exact canonical line
# --------------------------------------------------------------------------------------


def test_render_is_severity_code_target_message_fix_in_that_order():
    finding = _finding(
        severity="error",
        code="pointers.stale",
        target="CLAUDE.md",
        message="generated pointer is stale",
        fix="Run akmon sync.",
    )
    assert render(finding) == ("ERROR pointers.stale CLAUDE.md: generated pointer is stale → Run akmon sync.")


def test_render_keeps_every_field():
    line = render(_finding())
    for part in ("WARN", "area.rule", "some/file.md", "something is off", "Do the one thing that fixes it."):
        assert part in line


def test_render_collapses_only_an_empty_target():
    assert render(_finding(target="")) == "WARN area.rule: something is off → Do the one thing that fixes it."


def test_render_order_is_not_message_first():
    """The seed for a reordered rendering: the code must precede the message, always."""
    line = render(_finding())
    assert line.index("area.rule") < line.index("something is off") < line.index("Do the one thing")


def test_print_findings_writes_one_line_per_finding(capsys):
    print_findings([_finding(), _finding(severity="error", code="area.other")])
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("WARN ") and lines[1].startswith("ERROR ")


def test_print_findings_quiet_drops_only_ok(capsys):
    print_findings(
        [_finding(severity="ok"), _finding(severity="warn"), _finding(severity="error")],
        quiet=True,
    )
    lines = capsys.readouterr().out.strip().splitlines()
    assert [line.split(" ", 1)[0] for line in lines] == ["WARN", "ERROR"]


@pytest.mark.parametrize("name", sorted(ADOPTER_SOURCES))
def test_no_adopter_keeps_the_old_renderer(name):
    text = ADOPTER_SOURCES[name].read_text(encoding="utf-8")
    assert "[{finding.level}]" not in text
    assert "[{level}]" not in text
    assert "def print_findings" not in text, f"{name} must use the shared renderer"


@pytest.mark.parametrize("name", sorted(ADOPTER_SOURCES))
def test_no_adopter_defines_its_own_finding_or_reads_level(name):
    module = ast.parse(ADOPTER_SOURCES[name].read_text(encoding="utf-8"))
    for node in ast.walk(module):
        assert not (isinstance(node, ast.ClassDef) and node.name == "Finding"), (
            f"{name} defines a local Finding; import the shared envelope"
        )
        if isinstance(node, ast.Attribute) and node.attr == "level":
            raise AssertionError(f"{name} still reads .level at line {node.lineno}")


# --------------------------------------------------------------------------------------
# code ownership across adopters
# --------------------------------------------------------------------------------------


def _codes_in(path: Path) -> set[str]:
    """Every finding code the source issues, read from the literals at its call sites."""
    module = ast.parse(path.read_text(encoding="utf-8"))
    codes: set[str] = set()
    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        # A code reaches the envelope two ways: as the slug leading an emit call, or as a
        # `code=` argument a check forwards to a shared presence/shape helper.
        emitter = (isinstance(target, ast.Attribute) and target.attr in {"ok", "warn", "error"}) or (
            isinstance(target, ast.Name) and target.id == "Finding"
        )
        if emitter:
            positional = node.args[1:2] if isinstance(target, ast.Name) else node.args[0:1]
            for argument in positional:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    codes.add(argument.value)
        for keyword in node.keywords:
            if keyword.arg == "code" and isinstance(keyword.value, ast.Constant):
                codes.add(keyword.value.value)
    return {code for code in codes if CODE_RE.fullmatch(code)}


def _adopter_codes() -> dict:
    return {name: _codes_in(path) for name, path in ADOPTER_SOURCES.items()}


def test_every_adopter_issues_at_least_one_code():
    for name, codes in _adopter_codes().items():
        assert codes, f"{name} issues no finding code"


def test_no_code_is_shared_by_two_adopters():
    """A slug names one check; two owners for one slug is the duplicate seed."""
    seen: dict = {}
    for name, codes in sorted(_adopter_codes().items()):
        for code in sorted(codes):
            assert code not in seen, f"{code} is issued by both {seen[code]} and {name}"
            seen[code] = name


def _keyword(node, name):
    for keyword in node.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _emit_sites(module: ast.Module):
    """Every site that puts a finding into a stream, with its code and fix arguments.

    Two shapes exist: an adopter's ``self.ok/warn/error(code, message, …)`` helper, and a
    direct ``Finding(severity, code, message, target, fix)`` construction where an adopter
    builds the stream itself.
    """
    for parent in ast.walk(module):
        if not isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(parent):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            if (
                isinstance(target, ast.Attribute)
                and target.attr in {"ok", "warn", "error"}
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
            ):
                code = node.args[0] if node.args else _keyword(node, "code")
                yield parent, node, code, _keyword(node, "fix")
            elif isinstance(target, ast.Name) and target.id == "Finding":
                code = node.args[1] if len(node.args) > 1 else _keyword(node, "code")
                fix = node.args[4] if len(node.args) > 4 else _keyword(node, "fix")
                yield parent, node, code, fix


def _declares_code_parameter(function) -> bool:
    arguments = function.args
    names = [arg.arg for arg in (*arguments.args, *arguments.posonlyargs, *arguments.kwonlyargs)]
    return "code" in names


def test_every_issued_code_is_a_valid_slug():
    """Every emit site leads with a literal slug, or forwards one its own caller supplied."""
    seen = 0
    for name, path in ADOPTER_SOURCES.items():
        module = ast.parse(path.read_text(encoding="utf-8"))
        for function, node, code, fix in _emit_sites(module):
            seen += 1
            assert code is not None, f"{name}:{node.lineno} emits a finding without a code"
            if isinstance(code, ast.Name):
                assert code.id == "code" and _declares_code_parameter(function), (
                    f"{name}:{node.lineno} takes its code from something other than a caller-supplied slug"
                )
            else:
                assert isinstance(code, ast.Constant) and CODE_RE.fullmatch(code.value), (
                    f"{name}:{node.lineno} does not lead with a dotted slug"
                )
            assert fix is not None, f"{name}:{node.lineno} emits a finding without a fix"
    assert seen > 70, "the emit-site scanner stopped seeing the population it guards"


# --------------------------------------------------------------------------------------
# the CLI surface — no public JSON before C59
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(ADOPTER_SOURCES))
def test_no_adopter_exposes_json_output_before_c59(name):
    text = ADOPTER_SOURCES[name].read_text(encoding="utf-8")
    assert "--json" not in text, f"{name} adds --json; C59 owns the first public JSON output"


# --------------------------------------------------------------------------------------
# the severity × strict-state exit matrix, over every strict-capable adopter
# --------------------------------------------------------------------------------------


def _exit_verify(monkeypatch, tmp_path, seeded, strict):
    monkeypatch.setattr(verify.Verifier, "run", lambda self: self.findings.extend(seeded))
    argv = ["--project-root", str(tmp_path)]
    return verify.main(argv + (["--strict"] if strict else []))


def _exit_validate(monkeypatch, tmp_path, seeded, strict):
    monkeypatch.setattr(validate.Validator, "run", lambda self: self.findings.extend(seeded))
    return validate.main(["--strict"] if strict else [])


def _exit_self_ci(monkeypatch, tmp_path, seeded, strict):
    monkeypatch.setattr(self_ci, "_run", lambda root: list(seeded))
    return self_ci.main(["--strict"] if strict else [])


_STRICT_ADOPTERS = {
    "verify": _exit_verify,
    "validate": _exit_validate,
    "self_ci": _exit_self_ci,
}


#: The exact line the canonical form produces for `_finding(severity="warn")`. Spelled out
#: rather than computed from `render`, so a renderer that drops or reorders a field cannot
#: satisfy this by agreeing with itself.
_EXACT_LINE = "WARN area.rule some/file.md: something is off → Do the one thing that fixes it."


@pytest.mark.parametrize("adopter", sorted(_STRICT_ADOPTERS))
def test_exact_rendering_is_identical_across_adopters(adopter, monkeypatch, tmp_path, capsys):
    """A representative implementation cannot hide a stale one: every adopter prints this line."""
    _STRICT_ADOPTERS[adopter](monkeypatch, tmp_path, [_finding()], False)
    assert _EXACT_LINE in capsys.readouterr().out.splitlines()


@pytest.mark.parametrize("adopter", sorted(_STRICT_ADOPTERS))
@pytest.mark.parametrize(
    ("severity", "strict", "expected"),
    [
        ("ok", False, 0),
        ("ok", True, 0),
        ("warn", False, 0),
        ("warn", True, 1),
        ("error", False, 1),
        ("error", True, 1),
    ],
)
def test_exit_matrix_is_identical_across_adopters(adopter, severity, strict, expected, monkeypatch, tmp_path):
    seeded = [_finding(severity=severity)]
    assert _STRICT_ADOPTERS[adopter](monkeypatch, tmp_path, seeded, strict) == expected


@pytest.mark.parametrize(
    ("severity", "strict", "expected"),
    [("ok", False, 0), ("warn", True, 1), ("error", False, 1)],
)
def test_exit_code_helper_matches_the_matrix(severity, strict, expected):
    assert exit_code([_finding(severity=severity)], strict=strict) == expected


def test_exit_code_of_an_empty_stream_is_zero():
    assert exit_code([], strict=True) == 0


def test_sync_keeps_its_own_exit_vocabulary(tmp_path):
    """The owner-decided C51 exception: `sync` separates "cannot plan" (2) from drift (1).

    Recorded as a test rather than left to intent, because it is the one adopter whose exit
    codes are *not* the envelope's, and nothing else would notice it drifting into 1.
    """
    import sync

    (tmp_path / "AGENTS.md").write_text("# AGENTS.md\n", encoding="utf-8")
    assert sync.main(["--project-root", str(tmp_path), "--check"]) == 1  # stale, not yet written
    assert sync.main(["--project-root", str(tmp_path)]) == 0  # write
    assert sync.main(["--project-root", str(tmp_path), "--check"]) == 0  # clean

    duplicate = tmp_path / "skills" / "demo"
    duplicate.mkdir(parents=True)
    (duplicate / "SKILL.md").write_text("---\nname: demo\n---\n", encoding="utf-8")
    (tmp_path / "_aitna" / "skills" / "demo").mkdir(parents=True)
    (tmp_path / "_aitna" / "skills" / "demo" / "SKILL.md").write_text("---\nname: demo\n---\n", encoding="utf-8")
    assert sync.main(["--project-root", str(tmp_path), "--check"]) == 2  # cannot plan


def test_sync_check_speaks_the_envelope(tmp_path, capsys):
    import sync

    (tmp_path / "AGENTS.md").write_text("# AGENTS.md\n", encoding="utf-8")
    sync.main(["--project-root", str(tmp_path), "--check"])
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines, "sync --check printed nothing"
    for line in lines:
        assert line.startswith(("OK ", "WARN ", "ERROR "))
        assert " → " in line
    assert (
        "ERROR sync.stale-generated CLAUDE.md: generated file is stale or missing: CLAUDE.md "
        "→ Run akmon sync to regenerate this file."
    ) in lines


def test_sync_write_mode_keeps_its_action_log(tmp_path, capsys):
    """Only `--check` speaks findings: "updated this file" is a record, not a diagnostic."""
    import sync

    (tmp_path / "AGENTS.md").write_text("# AGENTS.md\n", encoding="utf-8")
    sync.main(["--project-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert "updated: CLAUDE.md" in out
    assert "ERROR " not in out


def test_self_ci_fixture_carries_and_runs_its_mounted_launchers(tmp_path):
    fixture = tmp_path / "consumer"
    self_ci._make_fixture(fixture, _KEYSTONE)
    mounted_bin = fixture / "_aitna" / "akmon" / "bin"
    assert (fixture / "_aitna" / "akmon" / "common" / "findings.py").is_file()
    for script in ("sync.py", "verify.py", "check.py"):
        result = self_ci.subprocess.run(
            [sys.executable, str(mounted_bin / script), "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


def test_self_ci_leg_uses_a_success_specific_invariant(monkeypatch):
    completed = self_ci.subprocess.CompletedProcess([], 0, stdout="", stderr="")
    monkeypatch.setattr(self_ci.subprocess, "run", lambda *args, **kwargs: completed)
    emitted = []
    assert self_ci._leg(
        emitted,
        "fixture sync",
        ["sync"],
        code="selfci.fixture-sync",
        ok_fix="Keep fixture sync green.",
        error_fix="Fix the sync failure.",
    )
    assert emitted == [Finding("ok", "selfci.fixture-sync", "fixture sync passes", "", "Keep fixture sync green.")]


def test_checked_suppresses_success_output(monkeypatch, capsys):
    completed = self_ci.subprocess.CompletedProcess(
        [], 0, stdout="successful child stdout\n", stderr="successful child stderr\n"
    )
    monkeypatch.setattr(self_ci.subprocess, "run", lambda *args, **kwargs: completed)
    self_ci._checked(["child"])
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
