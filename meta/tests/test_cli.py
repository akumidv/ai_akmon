"""Unit tests for the ``akmon`` console CLI (``src/akmon/cli.py``, C37 slice A).

Covers dispatch (mounted tree vs embedded tree), ``path``, ``version``, and the ``init``
stub. Nothing touches the real repo except read-only fallbacks to this checkout's own
embedded tree (the dev bench for akmon *is* a plain source checkout — no pip install here,
so the "embedded tree" resolves to this repo's own akmon root via the editable fallback in
``akmon._tree``, exactly as it would for anyone developing akmon itself).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_KEYSTONE = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_SRC = _KEYSTONE / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from akmon import __version__, _tree, cli  # noqa: E402

SYNC_PY = """
def main(argv=None):
    print("fixture-sync", argv)
    return 11


if __name__ == "__main__":
    import sys as _sys

    raise SystemExit(main(_sys.argv[1:]))
"""

VERIFY_PY = """
import sync


def main(argv=None):
    print("fixture-verify sees sync:", sync.MARKER)
    return 22


if __name__ == "__main__":
    import sys as _sys

    raise SystemExit(main(_sys.argv[1:]))
"""

SYNC_PY_WITH_MARKER = SYNC_PY.replace("def main", 'MARKER = "fixture"\n\n\ndef main')

NO_MAIN_PY = 'print("ran as a script, no main() defined")\n'


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _mounted_project(tmp_path: Path, *, sync_body: str = SYNC_PY, verify_body: str = VERIFY_PY) -> Path:
    """A project tree with a mounted akmon tree at ``_aitna/akmon`` (fixture launchers)."""
    root = tmp_path
    _write(root / "AGENTS.md", "# AGENTS\n")
    _write(root / "_aitna" / "akmon" / "bin" / "sync.py", sync_body)
    _write(root / "_aitna" / "akmon" / "bin" / "verify.py", verify_body)
    return root


# --------------------------------------------------------------------------------------
# _mounted_akmon_root
# --------------------------------------------------------------------------------------


def test_mounted_akmon_root_found_from_nested_cwd(tmp_path):
    root = _mounted_project(tmp_path)
    nested = root / "src" / "pkg"
    nested.mkdir(parents=True)
    assert cli._mounted_akmon_root(nested) == root / "_aitna" / "akmon"


def test_mounted_akmon_root_none_without_agents_md(tmp_path):
    assert cli._mounted_akmon_root(tmp_path) is None


def test_mounted_akmon_root_none_without_akmon_dir(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    assert cli._mounted_akmon_root(tmp_path) is None


# --------------------------------------------------------------------------------------
# mount mode "package" (ADR 0009 §4) — .akmon.toml's `mount` field overrides a stale mount
# --------------------------------------------------------------------------------------


def _package_mode_project(tmp_path: Path, *, with_stale_mount: bool = False) -> Path:
    root = tmp_path
    _write(root / "AGENTS.md", "# AGENTS\n")
    _write(root / "_aitna" / ".akmon.toml", 'mount = "package"\n')
    if with_stale_mount:
        # a leftover mount dir from a prior mode; must not shadow package mode.
        _write(root / "_aitna" / "akmon" / "bin" / "sync.py", "def main(argv=None):\n    return 99\n")
    return root


def test_mounted_akmon_root_none_when_akmon_toml_says_package(tmp_path):
    root = _package_mode_project(tmp_path)
    assert cli._mounted_akmon_root(root) is None


def test_mounted_akmon_root_none_when_akmon_toml_says_package_despite_stale_mount_dir(tmp_path):
    root = _package_mode_project(tmp_path, with_stale_mount=True)
    assert cli._mounted_akmon_root(root) is None


def test_dispatch_ignores_stale_mount_when_akmon_toml_says_package(tmp_path, monkeypatch, capfd):
    root = _package_mode_project(tmp_path, with_stale_mount=True)
    fixture_tree = tmp_path / "embedded"
    _write(fixture_tree / "bin" / "sync.py", SYNC_PY)
    monkeypatch.setattr(_tree, "embedded_tree_root", lambda: fixture_tree)

    code = cli._dispatch("sync", [], cwd=root)
    out = capfd.readouterr().out
    assert code == 11  # the embedded fixture's exit code, not the stale mount's 99
    assert "fixture-sync" in out


def test_cmd_path_uses_embedded_when_akmon_toml_says_package(tmp_path, capsys):
    root = _package_mode_project(tmp_path, with_stale_mount=True)
    assert cli._cmd_path(cwd=root) == 0
    assert capsys.readouterr().out.strip() == str(_tree.embedded_tree_root())


# --------------------------------------------------------------------------------------
# dispatch — mounted tree (always subprocess, per the skew rule)
# --------------------------------------------------------------------------------------


def test_dispatch_runs_mounted_sync_and_propagates_exit_code(tmp_path, capfd):
    root = _mounted_project(tmp_path)
    code = cli._dispatch("sync", ["--some-flag"], cwd=root)
    out = capfd.readouterr().out
    assert code == 11
    assert "fixture-sync ['--some-flag']" in out


def test_dispatch_runs_mounted_verify_that_imports_sync(tmp_path, capfd):
    root = _mounted_project(tmp_path, sync_body=SYNC_PY_WITH_MARKER)
    code = cli._dispatch("verify", [], cwd=root)
    out = capfd.readouterr().out
    assert code == 22
    assert "fixture-verify sees sync: fixture" in out


def test_dispatch_falls_back_to_embedded_when_no_mount(tmp_path, monkeypatch, capfd):
    fixture_tree = tmp_path / "embedded"
    _write(fixture_tree / "bin" / "sync.py", SYNC_PY)
    monkeypatch.setattr(_tree, "embedded_tree_root", lambda: fixture_tree)

    no_mount_cwd = tmp_path / "consumer"
    no_mount_cwd.mkdir()
    code = cli._dispatch("sync", ["x"], cwd=no_mount_cwd)
    out = capfd.readouterr().out
    assert code == 11
    assert "fixture-sync ['x']" in out


# --------------------------------------------------------------------------------------
# _run_embedded — import main() when possible, else subprocess
# --------------------------------------------------------------------------------------


def test_run_embedded_imports_main_in_process(tmp_path, monkeypatch):
    fixture_tree = tmp_path / "embedded"
    _write(fixture_tree / "bin" / "sync.py", SYNC_PY)
    monkeypatch.setattr(_tree, "embedded_tree_root", lambda: fixture_tree)
    assert cli._run_embedded("sync", ["--check"]) == 11


def test_run_embedded_falls_back_to_subprocess_when_no_main(tmp_path, monkeypatch, capfd):
    fixture_tree = tmp_path / "embedded"
    _write(fixture_tree / "bin" / "sync.py", NO_MAIN_PY)
    monkeypatch.setattr(_tree, "embedded_tree_root", lambda: fixture_tree)
    code = cli._run_embedded("sync", [])
    out = capfd.readouterr().out
    assert code == 0
    assert "ran as a script, no main() defined" in out


# --------------------------------------------------------------------------------------
# skew notice
# --------------------------------------------------------------------------------------


def test_skew_notice_absent_without_akmon_toml(tmp_path):
    root = _mounted_project(tmp_path)
    assert cli._skew_notice(root / "_aitna" / "akmon") is None


def test_skew_notice_absent_when_versions_match(tmp_path):
    root = _mounted_project(tmp_path)
    _write(root / "_aitna" / ".akmon.toml", f'akmon_version = "{__version__}"\n')
    assert cli._skew_notice(root / "_aitna" / "akmon") is None


def test_skew_notice_printed_when_versions_differ(tmp_path):
    root = _mounted_project(tmp_path)
    _write(root / "_aitna" / ".akmon.toml", 'akmon_version = "not-a-real-version"\n')
    notice = cli._skew_notice(root / "_aitna" / "akmon")
    assert notice is not None
    assert __version__ in notice
    assert "not-a-real-version" in notice


def test_dispatch_prints_skew_notice_to_stderr(tmp_path, capfd):
    root = _mounted_project(tmp_path)
    _write(root / "_aitna" / ".akmon.toml", 'akmon_version = "not-a-real-version"\n')
    cli._dispatch("sync", [], cwd=root)
    err = capfd.readouterr().err
    assert "not-a-real-version" in err


# --------------------------------------------------------------------------------------
# akmon path
# --------------------------------------------------------------------------------------


def test_cmd_path_prints_mounted_root(tmp_path, capsys):
    root = _mounted_project(tmp_path)
    assert cli._cmd_path(cwd=root) == 0
    assert capsys.readouterr().out.strip() == str(root / "_aitna" / "akmon")


def test_cmd_path_prints_embedded_root_without_mount(tmp_path, capsys):
    no_mount_cwd = tmp_path / "consumer"
    no_mount_cwd.mkdir()
    assert cli._cmd_path(cwd=no_mount_cwd) == 0
    assert capsys.readouterr().out.strip() == str(_tree.embedded_tree_root())


# --------------------------------------------------------------------------------------
# akmon version
# --------------------------------------------------------------------------------------


def test_cmd_version_prints_package_version(capsys):
    assert cli._cmd_version() == 0
    assert capsys.readouterr().out.strip() == __version__


# --------------------------------------------------------------------------------------
# akmon init (stub — later slice)
# --------------------------------------------------------------------------------------


def test_cmd_init_is_a_non_zero_stub(capsys):
    code = cli._cmd_init([])
    err = capsys.readouterr().err
    assert code != 0
    assert "not implemented yet" in err


def test_main_init_returns_stub_exit_code(capsys):
    assert cli.main(["init"]) != 0


# --------------------------------------------------------------------------------------
# main() — argv parsing, incl. passthrough flags starting with "-"
# --------------------------------------------------------------------------------------


def test_main_version_command(capsys):
    assert cli.main(["version"]) == 0
    assert capsys.readouterr().out.strip() == __version__


def test_main_requires_a_command():
    with pytest.raises(SystemExit) as excinfo:
        cli.main([])
    assert excinfo.value.code == 2


def test_main_rejects_unknown_command():
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["bogus"])
    assert excinfo.value.code == 2


def test_main_passes_leading_dash_flags_through_to_sync(tmp_path, monkeypatch, capfd):
    # Regression guard: argparse subparsers + REMAINDER mis-parse a remainder starting
    # with "-" (e.g. `akmon sync --check`); main() uses a single-level REMAINDER instead.
    fixture_tree = tmp_path / "embedded"
    _write(fixture_tree / "bin" / "sync.py", SYNC_PY)
    monkeypatch.setattr(_tree, "embedded_tree_root", lambda: fixture_tree)
    monkeypatch.chdir(tmp_path)  # no AGENTS.md here -> no mount found -> embedded path
    code = cli.main(["sync", "--check", "--project-root", "/tmp/x"])
    out = capfd.readouterr().out
    assert code == 11
    assert "['--check', '--project-root', '/tmp/x']" in out


# --------------------------------------------------------------------------------------
# akmon._tree.embedded_tree_root — editable/source-checkout fallback
# --------------------------------------------------------------------------------------


def test_embedded_tree_root_resolves_this_checkout():
    root = _tree.embedded_tree_root()
    assert (root / "bin" / "sync.py").is_file()
    assert (root / "bin" / "verify.py").is_file()
