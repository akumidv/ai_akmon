"""Unit tests for ``meta/self_ci.py``'s failure reporting.

The installed-wheel leg has two kinds of red: something akmon ships is broken, and a
prerequisite of the leg is missing (no network reach, or a git that cannot authenticate
outside this checkout — the leg resolves the pin from the akmon repository's release tags).
They read identically as a bare exit status and cost very different work, so the leg has to
tell them apart.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile

import pytest
import self_ci

from common.findings import Finding

_PREREQUISITE = (
    "/tmp/x/venv/bin/akmon init --mode package --project-root /tmp/x/c --yes: "
    "akmon init: cannot discover the latest release tag from "
    "'https://github.com/akumidv/ai_akmon'; pass --ref explicitly"
)


def _finding(detail: str) -> Finding:
    message, fix = self_ci._wheel_smoke_report(detail)
    # Constructed, not just returned: the envelope caps ``fix`` at one sentence, and a
    # remediation that cannot be filed is the same as no remediation.
    return Finding("error", "selfci.wheel-smoke", message, "", fix)


def test_a_missing_prerequisite_is_named_as_one():
    finding = _finding(_PREREQUISITE)
    assert "prerequisite of this leg, not a packaging defect" in finding.message
    assert "cannot discover the latest release tag" in finding.message
    assert "gh auth setup-git" in finding.fix


def test_a_git_credential_failure_is_the_same_prerequisite():
    finding = _finding("fatal: could not read Username for 'https://github.com'")
    assert "prerequisite of this leg" in finding.message
    assert "gh auth setup-git" in finding.fix


def test_any_other_failure_keeps_the_packaging_remediation():
    finding = _finding("verify --strict: exit 1")
    assert finding.message == "installed-wheel smoke failed: verify --strict: exit 1"
    assert "fix the packaged-install failure" in finding.fix
    assert "gh auth" not in finding.fix


def _wheel_with_metadata(tmp_path, metadata: str):
    wheel = tmp_path / "akmon-test.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("akmon-0.0.dist-info/METADATA", metadata)
    return wheel


def test_wheel_python_floor_accepts_the_exact_field(tmp_path):
    wheel = _wheel_with_metadata(tmp_path, "Metadata-Version: 2.4\nRequires-Python: >=3.12\n")
    self_ci._assert_wheel_python_floor(wheel)


@pytest.mark.parametrize(
    "metadata",
    (
        "Metadata-Version: 2.4\n",
        "Requires-Python: >=3.9\n",
        "Requires-Python: >=3.11\n",
        "Requires-Python: >=3.12\nRequires-Python: >=3.12\n",
    ),
)
def test_wheel_python_floor_rejects_missing_stale_or_duplicate_fields(tmp_path, metadata):
    wheel = _wheel_with_metadata(tmp_path, metadata)
    with pytest.raises(RuntimeError, match=r"Requires-Python must be exactly >=3\.12"):
        self_ci._assert_wheel_python_floor(wheel)


def test_a_hung_js_leg_is_stopped_and_named_as_timed_out(monkeypatch):
    """A leg that never returns must not hang the release check: it is stopped at the bound and
    its finding says it timed out, after how long, rather than a bare status."""
    seen = {}

    def hang(command, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output="partial")

    monkeypatch.setattr(self_ci.shutil, "which", lambda binary: f"/usr/bin/{binary}")
    monkeypatch.setattr(self_ci.subprocess, "run", hang)
    findings: list[Finding] = []
    self_ci._js_leg(
        findings,
        "differential hook fuzz",
        self_ci.LegInvocation(["node", "fuzz.mjs"]),
        code="selfci.fuzz",
        fixes=self_ci.LegFixes(ok_fix="Keep it green.", error_fix="Rerun the leg."),
    )
    assert seen["timeout"] == self_ci.JS_LEG_TIMEOUT
    [finding] = findings
    assert finding.severity == "error"
    assert finding.code == "selfci.fuzz"
    assert "timed out" in finding.message
    assert f"{self_ci.JS_LEG_TIMEOUT} s" in finding.message


def test_the_fuzz_rerun_command_keeps_its_drafts_in_a_gitignored_named_dir():
    """The fuzz leg's fix tells the owner to review the drafts, so the rerun it prints must name
    where they go — a fixed path the owner can find, ignored so a draft never stages."""
    command = self_ci.fuzz_rerun_command(2000, 7)
    assert command.endswith(f"--cases 2000 --seed 7 --emit {self_ci.FUZZ_EMIT_DIR}")
    if shutil.which("git") is None:
        pytest.skip("git is not on PATH")
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", f"{self_ci.FUZZ_EMIT_DIR}/draft.toml"],
        cwd=self_ci._AKMON_ROOT,
        check=False,
    )
    assert ignored.returncode == 0, f"{self_ci.FUZZ_EMIT_DIR} is not gitignored"


def test_path_without_hides_only_the_named_binary(tmp_path):
    """C70's fixture legs stand in an absent Codex by hiding it from PATH: the binary must stop
    resolving while everything beside it — in its own directory and in the others — still does,
    and the real directory is left alone."""
    first, second = tmp_path / "first", tmp_path / "second"
    for directory, names in ((first, ("codex", "tool")), (second, ("other",))):
        directory.mkdir()
        for name in names:
            (directory / name).write_text("#!/bin/sh\n", encoding="utf-8")
            (directory / name).chmod(0o755)
    path = self_ci.path_without("codex", os.pathsep.join((str(first), str(second))), tmp_path / "scratch")
    assert shutil.which("codex", path=path) is None
    assert shutil.which("tool", path=path) is not None
    assert shutil.which("other", path=path) == str(second / "other")
    assert (first / "codex").is_file()


def test_every_leg_fix_text_is_a_valid_finding_fix() -> None:
    """A leg's fix text only meets the ``Finding`` validator when the leg fails, so a text the
    validator refuses (``eslint . and fix`` reads as two sentences) crashes the gate instead of
    reporting it. Every literal ``ok_fix``/``error_fix`` is checked here, while it is green."""
    import ast
    import inspect

    texts = [
        keyword.value.value
        for node in ast.walk(ast.parse(inspect.getsource(self_ci)))
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg in {"ok_fix", "error_fix"}
        and isinstance(keyword.value, ast.Constant)
        and isinstance(keyword.value.value, str)
    ]
    assert len(texts) >= 6
    for text in texts:
        Finding("error", "selfci.example", "message", "", text)


#: The quotes GNU env prints around a name under a UTF-8 locale, spelt by code point (RUF001).
_LEFT_QUOTE, _RIGHT_QUOTE = chr(0x2018), chr(0x2019)


def _npm_finding(detail: str) -> Finding:
    message, fix = self_ci._npm_smoke_report(detail)
    # Constructed, not just returned: these fix texts reach the ``Finding`` validator only when
    # the npm smoke is red, so the leg-fix sweep above cannot see them.
    return Finding("error", "selfci.npm-smoke", message, "", fix)


@pytest.mark.parametrize(
    "detail",
    (
        # Python spawning a binary that is not on PATH.
        "[Errno 2] No such file or directory: 'npm'",
        "[Errno 2] No such file or directory: 'node'",
        "[Errno 2] No such file or directory: 'git'",
        # node missing behind npm's / the akmon bin's `#!/usr/bin/env node` shebang, as measured
        # under the C locale and under a UTF-8 one (coreutils env 9.4), and a translated reason.
        "npm pack --silent --pack-destination /tmp/x/dist: /usr/bin/env: 'node': No such file or directory",
        f"npm pack --silent: /usr/bin/env: {_LEFT_QUOTE}node{_RIGHT_QUOTE}: No such file or directory",
        "/tmp/x/node_modules/.bin/akmon init --yes: env: «node»: Datei oder Verzeichnis nicht gefunden",
        # The up-front check.
        "the `git` binary is not on PATH",
        "the `node` binary is not on PATH",
        "node v20.11.0 is older than 22",
    ),
)
def test_a_missing_or_old_toolchain_is_the_npm_smoke_prerequisite(detail):
    finding = _npm_finding(detail)
    assert finding.message.startswith(f"npm smoke could not run: {detail} :: prerequisite of this leg")
    assert "node >= 22, npm and git on PATH" in finding.message
    assert "node >= 22" in finding.fix
    assert "git" in finding.fix


@pytest.mark.parametrize(
    "detail",
    (
        "/tmp/x/node_modules/.bin/akmon verify --strict --quiet: exit 1",
        "npm pack produced no akmon-*.tgz tarball in /tmp/x/dist",
        'the Node attach did not record ecosystem = "node"',
    ),
)
def test_any_other_npm_smoke_failure_is_an_akmon_defect(detail):
    finding = _npm_finding(detail)
    assert finding.message == f"npm smoke failed: {detail}"
    assert "prerequisite" not in finding.message
    assert "fix the Python-free Node install failure" in finding.fix


def _stub_binaries(directory, scripts):
    directory.mkdir()
    for name, body in scripts.items():
        (directory / name).write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        (directory / name).chmod(0o755)
    return {"PATH": str(directory)}


def test_the_npm_smoke_names_a_missing_binary_before_running_anything(tmp_path):
    env = _stub_binaries(tmp_path / "bin", {"node": "echo v24.0.0", "npm": "exit 0"})
    with pytest.raises(RuntimeError, match=r"the `git` binary is not on PATH") as caught:
        self_ci._check_npm_smoke_prerequisites(env)
    assert "prerequisite of this leg" in _npm_finding(str(caught.value)).message


def test_the_npm_smoke_names_a_node_below_the_floor(tmp_path):
    env = _stub_binaries(tmp_path / "bin", {"node": "echo v20.11.0", "npm": "exit 0", "git": "exit 0"})
    with pytest.raises(RuntimeError, match=r"node v20\.11\.0 is older than 22") as caught:
        self_ci._check_npm_smoke_prerequisites(env)
    assert "prerequisite of this leg" in _npm_finding(str(caught.value)).message


def test_the_npm_smoke_accepts_a_node_at_the_floor(tmp_path):
    env = _stub_binaries(tmp_path / "bin", {"node": "echo v22.0.0", "npm": "exit 0", "git": "exit 0"})
    self_ci._check_npm_smoke_prerequisites(env)


def test_python_free_env_hides_every_python_and_keeps_the_rest(tmp_path):
    env = _stub_binaries(tmp_path / "bin", {"python3": "exit 0", "python": "exit 0", "node": "exit 0"})
    hidden = self_ci._python_free_env({**env, "HOME": "/home/x"}, tmp_path / "scratch")
    assert hidden["HOME"] == "/home/x"
    for binary in self_ci._PYTHON_BINARIES:
        assert shutil.which(binary, path=hidden["PATH"]) is None
    assert shutil.which("node", path=hidden["PATH"]) is not None
    assert (tmp_path / "bin" / "python3").is_file()


def test_python_free_env_raises_when_a_python_stays_on_path(tmp_path, monkeypatch):
    """The leg's whole claim is "no Python on PATH": a shadow that leaves one resolvable must stop
    the leg rather than let it pass on a host where the hooks could still fall back to Python."""
    env = _stub_binaries(tmp_path / "bin", {"python3": "exit 0"})
    monkeypatch.setattr(self_ci, "path_without", lambda binary, path, scratch: path)
    with pytest.raises(RuntimeError, match=r"could not hide python3 from PATH"):
        self_ci._python_free_env(env, tmp_path / "scratch")
