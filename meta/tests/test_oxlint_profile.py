"""akmon's JavaScript/TypeScript rules, ``profiles/oxlint.json`` — a standard oxlint configuration (ADR 0020 D09).

The rules must run without akmon, the two standard ways: ``oxlint -c`` and a project's own
``extends``. The second carries a measured subtlety these tests pin: the override that turns the
checks tsc owns off in ``.ts`` files must still reach a project that extends the profile.

akmon itself runs exactly the rules it offers — its ``.oxlintrc.json`` extends the profile and adds
no rule of its own. The size family (complexity, max-params, max-statements, max-depth) is a
ratchet (C109): ``overrides`` may switch a size rule off for the files that exceed it today, the
lists only shrink, a stale entry is removed, and an inline disable of a size rule is an offender.
Any other inline waiver is narrow — ``-disable-next-line`` naming its rules — and the population
oxlint skips (``ignorePatterns``) is pinned exactly (C15).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "profiles" / "oxlint.json"
OXLINT = ROOT / "node_modules" / ".bin" / "oxlint"
SIZE_RULES = ("complexity", "max-params", "max-statements", "max-depth")

pytestmark = pytest.mark.skipif(not OXLINT.exists(), reason="oxlint is akmon's development dependency (npm ci)")


def _oxlint(cwd: Path, *args: str) -> list[tuple[str, str]]:
    """The findings of ``oxlint -f json`` as (path relative to ``cwd``, rule) pairs."""
    result = subprocess.run([str(OXLINT), "-f", "json", *args], cwd=cwd, capture_output=True, text=True, check=False)
    assert result.returncode in (0, 1), result.stderr
    diagnostics = json.loads(result.stdout)["diagnostics"]
    return [(d["filename"], re.sub(r"^\w+\((.*)\)$", r"\1", d["code"])) for d in diagnostics]


def _rules(findings: list[tuple[str, str]], filename: str) -> set[str]:
    return {rule for name, rule in findings if name == filename}


def _sources(root: Path) -> None:
    (root / "a.js").write_text("var a = 1;\nif (a == 2) a = 3;\n", encoding="utf-8")


def test_the_rules_run_standalone_with_config(tmp_path):
    _sources(tmp_path)
    findings = _oxlint(tmp_path, "-c", str(PROFILE), ".")
    assert {"no-var", "eqeqeq", "curly"} <= _rules(findings, "a.js")


def test_a_project_extending_the_profile_runs_the_rules_and_leaves_undeclared_names_to_tsc(tmp_path):
    rules = tmp_path / "node_modules" / "akmon" / "profiles" / "oxlint.json"
    rules.parent.mkdir(parents=True)
    shutil.copy(PROFILE, rules)
    (tmp_path / ".oxlintrc.json").write_text(
        '{ "extends": ["./node_modules/akmon/profiles/oxlint.json"] }\n', encoding="utf-8"
    )
    _sources(tmp_path)
    (tmp_path / "b.ts").write_text("export const b = undeclaredName;\n", encoding="utf-8")
    (tmp_path / "c.js").write_text("export const c = undeclaredName;\n", encoding="utf-8")
    findings = _oxlint(tmp_path, ".")
    assert {"no-var", "eqeqeq", "curly"} <= _rules(findings, "a.js")
    assert "no-undef" in _rules(findings, "c.js")  # the control: JavaScript keeps no-undef
    assert "no-undef" not in _rules(findings, "b.ts")  # tsc owns it in TypeScript


def test_a_project_extending_the_profile_states_its_own_env(tmp_path):
    """C11: oxlint's ``extends`` carries rules, not ``env`` (M132) — the reason init's steps name ``env``.

    A base's ``env`` applies only with ``-c``; a project that extends it and says nothing about
    where its code runs sees host globals as undeclared, and its own ``env`` is what clears them.
    """
    base = tmp_path / "base.json"
    base.write_text(json.dumps({"extends": [str(PROFILE)], "env": {"node": True}}), encoding="utf-8")
    (tmp_path / "a.js").write_text("console.log(new Map());\n", encoding="utf-8")
    (tmp_path / ".oxlintrc.json").write_text('{ "extends": ["./base.json"] }\n', encoding="utf-8")
    assert ("a.js", "no-undef") in _oxlint(tmp_path, ".")  # the base's env.node did not arrive
    assert _oxlint(tmp_path, "-c", str(base), ".") == []  # with -c it is the config: its env applies
    own_env = '{ "extends": ["./base.json"], "env": { "node": true } }\n'
    (tmp_path / ".oxlintrc.json").write_text(own_env, encoding="utf-8")
    assert _oxlint(tmp_path, ".") == []  # the project's own env; `Map` needs none (ES globals are on)


def _profile() -> dict:
    """``profiles/oxlint.json`` parsed: its ``//`` comments (outside strings) dropped, then JSON."""
    text = PROFILE.read_text(encoding="utf-8")
    return json.loads(re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*', lambda m: m[0] if m[0].startswith('"') else "", text))


def test_the_profile_states_no_env():
    """M132: oxlint defines the ECMAScript globals itself, and ``extends`` does not carry ``env``.

    So an ``env`` here would change nothing ``no-undef`` sees for a project extending the profile;
    where the code runs is the project's own config to state.
    """
    profile = _profile()
    assert "rules" in profile  # the parse is the real profile, not an empty object
    assert "env" not in profile


def test_the_profile_alone_defines_the_ecmascript_globals(tmp_path):
    (tmp_path / "a.js").write_text(
        "export const a = [Promise.resolve(1), new Map(), BigInt(1), new WeakRef({}), globalThis];\n",
        encoding="utf-8",
    )
    assert "no-undef" not in _rules(_oxlint(tmp_path, "-c", str(PROFILE), "."), "a.js")


# --------------------------------------------------------------------------------------
# akmon's own configuration, and the size family (C109)
# --------------------------------------------------------------------------------------

# The files each size rule is switched off for today. Frozen: a list may shrink (a file brought
# under the limit leaves both here and .oxlintrc.json) and never grows.
FROZEN = {
    "complexity": {
        "js/akmon/_init.mjs",
        "js/akmon/cli.mjs",
        "js/bin/check.mjs",
        "js/bin/sync.mjs",
        "js/bin/verify.mjs",
        "js/common/check_runner.mjs",
        "js/common/codex_hooks.mjs",
        "js/common/glob.mjs",
        "js/common/json_writer.mjs",
        "js/common/markers.mjs",
        "js/common/materialization.mjs",
        "js/common/pyjson.mjs",
        "js/common/pyvalue.mjs",
        "js/common/shlex.mjs",
        "js/hooks/hook_core.mjs",
        "js/hooks/model-routing.mjs",
        "js/tools/model_routing/coverage_map.mjs",
        "js/tools/model_routing/gate_pack.mjs",
        "js/tools/model_routing/init.mjs",
        "js/tools/model_routing/routing.mjs",
        "js/tools/model_routing/second_opinion.mjs",
        "js/tools/model_routing/stats.mjs",
        "js/tools/release/release_check.mjs",
        "js/tools/tasks/archive.mjs",
        "meta/conformance/probe.mjs",
    },
    "max-params": {
        "js/tools/model_routing/routing.mjs",
        "js/tools/model_routing/second_opinion.mjs",
        "js/tools/model_routing/stats.mjs",
        "js/tools/tasks/archive.mjs",
    },
    "max-statements": {
        "js/tools/model_routing/init.mjs",
        "js/tools/model_routing/second_opinion.mjs",
    },
    "max-depth": {
        "meta/conformance/probe.mjs",
    },
}


def _akmon_oxlintrc() -> dict:
    return json.loads((ROOT / ".oxlintrc.json").read_text(encoding="utf-8"))


def _listed() -> dict[str, set[str]]:
    """Each size rule -> the files ``.oxlintrc.json`` overrides switch it off for."""
    listed: dict[str, set[str]] = {rule: set() for rule in SIZE_RULES}
    for override in _akmon_oxlintrc().get("overrides", []):
        for rule in override["rules"]:
            listed[rule].update(override["files"])
    return listed


# What akmon's own lint run skips — pinned exactly, so the population oxlint covers cannot narrow
# silently (C15): vendored code, and harness/tool state directories that are not akmon source.
IGNORED = ["js/vendor/**", ".qwen/**", ".claude/**", ".review/**", ".venv/**"]


def test_akmon_runs_exactly_the_rules_it_offers():
    config = _akmon_oxlintrc()
    assert config["extends"] == ["./profiles/oxlint.json"]
    assert set(config) == {"extends", "env", "ignorePatterns", "overrides"}  # no rule of its own
    assert config["env"] == {"node": True}
    assert config["ignorePatterns"] == IGNORED
    for override in config.get("overrides", []):
        assert set(override) == {"files", "rules"}
        assert set(override["rules"]) <= set(SIZE_RULES), override
        assert set(override["rules"].values()) == {"off"}, override


def test_the_size_exceptions_only_shrink():
    listed = _listed()
    assert set(listed) == set(FROZEN)
    for rule, files in listed.items():
        added = files - FROZEN[rule]
        assert not added, f"{rule}: bring {sorted(added)} under the limit instead of listing it"


def test_every_listed_size_exception_is_still_needed(tmp_path):
    listed = _listed()
    config = tmp_path / "bare.oxlintrc.json"  # the profile alone: no overrides
    config.write_text(json.dumps({"extends": [str(PROFILE)], "env": {"node": True}}), encoding="utf-8")
    files = sorted(set().union(*listed.values()))
    findings = _oxlint(ROOT, "-c", str(config), *files)
    for rule, names in listed.items():
        for name in sorted(names):
            assert rule in _rules(findings, name), f"{name} no longer breaks {rule}: remove it from .oxlintrc.json"


_JS = ("*.js", "*.mjs", "*.cjs", "*.jsx", "*.ts", "*.mts", "*.cts", "*.tsx")
_DIRECTIVE = re.compile(r"(?:oxlint|eslint)-(?:disable|enable)[\w-]*[^\n]*")
# The one waiver form: the next line only, naming its rules (an optional `-- reason` after them).
_NARROW = re.compile(
    r"(?:oxlint|eslint)-disable-next-line[ \t]+([\w/@-]+(?:[ \t]*,[ \t]*[\w/@-]+)*)(?:[ \t]+--.*)?(?:[ \t]*\*/)?"
)


def _inline_directives() -> list[tuple[str, str]]:
    """Every oxlint/ESLint directive comment in akmon's tracked JavaScript, as (file, directive)."""
    tracked = subprocess.run(["git", "ls-files", *_JS], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    found = []
    for name in tracked.split():
        if (ROOT / name).is_file() and not name.startswith("js/vendor/"):
            text = (ROOT / name).read_text(encoding="utf-8")
            found += [(name, m.group(0).strip()) for m in _DIRECTIVE.finditer(text)]
    return found


def _waiver_offence(directive: str) -> str | None:
    """Why ``directive`` is not a narrow waiver of a non-size rule, or ``None`` when it is one."""
    narrow = _NARROW.fullmatch(directive)
    if narrow is None:
        return "not `-disable-next-line <rule>`"
    rules = {rule.strip() for rule in narrow.group(1).split(",")}
    return "waives a size rule" if rules & set(SIZE_RULES) else None


def test_every_inline_disable_is_narrow_and_never_names_a_size_rule():
    """C15: a blanket ``/* oxlint-disable */`` or a ruleless one hides every rule, so it is an offender too.

    A size limit is met, never waived inline; any other waiver names its rule for the next line only.
    """
    directives = _inline_directives()
    offenders = [(name, d, why) for name, d in directives if (why := _waiver_offence(d))]
    assert offenders == []
    # The population is live and pinned: a new waiver, or one that went away, is a reviewed change here.
    waivers = {
        (name, rule.strip())
        for name, d in directives
        if (narrow := _NARROW.fullmatch(d))
        for rule in narrow.group(1).split(",")
    }
    assert waivers == {
        ("js/common/always_loaded.mjs", "no-control-regex"),
        ("js/common/findings.mjs", "no-control-regex"),
        ("js/common/pyjson.mjs", "no-control-regex"),
    }
    assert len(directives) == len(waivers)


@pytest.mark.parametrize(
    ("directive", "offence"),
    [
        ("// eslint-disable-next-line no-control-regex", None),
        ("// oxlint-disable-next-line no-empty, no-debugger -- reason", None),
        ("/* oxlint-disable-next-line no-empty */", None),
        ("/* oxlint-disable */", "not `-disable-next-line <rule>`"),
        ("// eslint-disable-next-line", "not `-disable-next-line <rule>`"),
        ("// oxlint-disable-line no-empty", "not `-disable-next-line <rule>`"),
        ("/* eslint-disable no-empty */", "not `-disable-next-line <rule>`"),
        ("// oxlint-enable", "not `-disable-next-line <rule>`"),
        ("// eslint-disable-next-line complexity", "waives a size rule"),
        ("// oxlint-disable-next-line no-empty, max-depth", "waives a size rule"),
    ],
)
def test_the_waiver_check_sees_every_directive_form(directive, offence):
    found = _DIRECTIVE.search(directive)
    assert found is not None
    assert _waiver_offence(found.group(0).strip()) == offence
