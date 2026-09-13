"""Unit tests for the ``akmon`` console CLI (``src/akmon/cli.py``, C37 slice A).

Covers dispatch (mounted tree vs embedded tree), ``path``, ``version``, and the ``init``
stub. Nothing touches the real repo except read-only fallbacks to this checkout's own
embedded tree (the dev bench for akmon *is* a plain source checkout — no pip install here,
so the "embedded tree" resolves to this repo's own akmon root via the editable fallback in
``akmon._tree``, exactly as it would for anyone developing akmon itself).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_KEYSTONE = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_SRC = _KEYSTONE / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import akmon  # noqa: E402
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

# A hook that imports a neighbour by bare name — the way every real akmon hook imports
# ``hook_core`` — and echoes the argv tail it was handed.
HOOK_PY = """
import sys

from {neighbour} import CARRIER


def main():
    print(CARRIER, sys.argv[1:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""

FAILING_HOOK_PY = """
import sys

if __name__ == "__main__":
    print("boom", file=sys.stderr)
    raise SystemExit(7)
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _embedded_tree(tmp_path: Path, sync_body: str = SYNC_PY) -> Path:
    """A stand-in embedded tree: a fixture launcher plus the real shared library.

    ``common`` is copied rather than stubbed because the CLI asks the embedded tree for the
    dev-layer name (one owner, C73). A tree without it is not a tree the wheel can ship — the
    force-include list and the wheel smoke both assert that — so faking one here would test a
    layout that cannot exist.
    """
    fixture_tree = tmp_path / "embedded"
    _write(fixture_tree / "bin" / "sync.py", sync_body)
    shutil.copytree(
        _KEYSTONE / "common",
        fixture_tree / "common",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    return fixture_tree


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


def test_mount_field_is_read_through_an_inline_comment(tmp_path):
    """`mount = "package"  # materialized` is the documented shape; without comment stripping it
    read back as `package"  # materialized`, so the stale mount shadowed the pin after all."""
    root = _package_mode_project(tmp_path, with_stale_mount=True)
    (root / "_aitna" / ".akmon.toml").write_text(
        'mount = "package"  # no tree in the repo (ADR 0009 §4)\n', encoding="utf-8"
    )
    assert cli._embedded_common_module(_tree.embedded_tree_root(), "record").recorded_mount(root) == "package"
    assert cli._mounted_akmon_root(root) is None


def test_mounted_akmon_root_none_when_akmon_toml_says_package_despite_stale_mount_dir(tmp_path):
    root = _package_mode_project(tmp_path, with_stale_mount=True)
    assert cli._mounted_akmon_root(root) is None


def test_dispatch_ignores_stale_mount_when_akmon_toml_says_package(tmp_path, monkeypatch, capfd):
    root = _package_mode_project(tmp_path, with_stale_mount=True)
    fixture_tree = _embedded_tree(tmp_path)
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
    fixture_tree = _embedded_tree(tmp_path)
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
    fixture_tree = _embedded_tree(tmp_path)
    monkeypatch.setattr(_tree, "embedded_tree_root", lambda: fixture_tree)
    assert cli._run_embedded("sync", ["--check"]) == 11


def test_run_embedded_falls_back_to_subprocess_when_no_main(tmp_path, monkeypatch, capfd):
    fixture_tree = _embedded_tree(tmp_path, NO_MAIN_PY)
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


def test_skew_notice_absent_when_the_pin_carries_a_v_prefix(tmp_path):
    """The spelling that made the notice fire on every command in a mounted consumer."""
    root = _mounted_project(tmp_path)
    _write(root / "_aitna" / ".akmon.toml", f'akmon_version = "v{__version__}"\n')
    assert cli._skew_notice(root / "_aitna" / "akmon") is None


def test_skew_notice_reports_distance_when_the_pin_has_a_describe_suffix(tmp_path):
    """A `git describe` distance is a separate fact from a version mismatch."""
    root = _mounted_project(tmp_path)
    pin = f"v{__version__}-5-gdeadbee"
    _write(root / "_aitna" / ".akmon.toml", f'akmon_version = "{pin}"\n')
    notice = cli._skew_notice(root / "_aitna" / "akmon")
    assert notice is not None
    assert pin in notice
    assert "5 commits past the tag this CLI matches" in notice
    assert "CLI is" not in notice  # not the mismatch sentence


def test_skew_notice_renders_the_pin_as_recorded(tmp_path):
    """The old form re-prefixed an already-prefixed pin and printed "v v0.3.0"."""
    root = _mounted_project(tmp_path)
    _write(root / "_aitna" / ".akmon.toml", 'akmon_version = "v0.3.0"\n')
    notice = cli._skew_notice(root / "_aitna" / "akmon")
    assert notice is not None
    assert "v0.3.0" in notice
    assert "v v0.3.0" not in notice
    assert "vv0.3.0" not in notice
    assert f"CLI is {__version__}," in notice


def test_split_version_normalizes_only_the_two_recorded_spellings():
    assert cli._split_version("v0.3.0") == ("0.3.0", None)
    assert cli._split_version("0.3.0") == ("0.3.0", None)
    assert cli._split_version("v0.3.0-5-gdeadbee") == ("0.3.0", "5")
    assert cli._split_version("v0.3.0-5-gdeadbee-dirty") == ("0.3.0", "5")
    # A PEP 440 segment names a different version, not another spelling of the same one.
    assert cli._split_version("0.4.0.dev0") == ("0.4.0.dev0", None)
    assert cli._split_version("0.4.0") != cli._split_version("0.4.0.dev0")


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
# akmon hook — the entry point the generated vendor wiring names (C77)
# --------------------------------------------------------------------------------------


def _hooks(tree: Path, carrier: str) -> Path:
    """A hooks directory in ``tree``, tagged so a test can tell which tree ran.

    The neighbour module is named per carrier because these tests run several hooks in one
    interpreter, and an imported module stays in ``sys.modules``. In production that cannot
    happen — the harness starts a process per hook call — so this is a test-bench concern only.
    """
    neighbour = f"neighbour_{carrier}"
    _write(tree / "hooks" / "probe.py", HOOK_PY.format(neighbour=neighbour))
    _write(tree / "hooks" / f"{neighbour}.py", f'CARRIER = "{carrier}"\n')
    _write(tree / "hooks" / "angry.py", FAILING_HOOK_PY)
    return tree


def _hook_project(tmp_path: Path) -> Path:
    """A project whose mounted tree carries the fixture hooks."""
    root = _mounted_project(tmp_path)
    mounted = _hooks(root / "_aitna" / "akmon", "mounted")
    shutil.copytree(
        _KEYSTONE / "common",
        mounted / "common",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    return root


def test_hook_runs_the_script_from_the_mounted_tree(tmp_path, capsys):
    root = _hook_project(tmp_path)
    assert cli._cmd_hook(["probe"], cwd=root) == 0
    assert capsys.readouterr().out.strip() == "mounted []"


def test_mounted_hook_imports_common_from_its_own_tree(tmp_path, monkeypatch, capsys):
    """Project-root discovery loads embedded ``common`` first; that cache must not pair a
    mounted hook with utilities from a different release of the standard."""
    root = _hook_project(tmp_path)
    mounted = root / "_aitna" / "akmon"
    _write(mounted / "common" / "carrier.py", 'CARRIER = "mounted"\n')
    _write(
        mounted / "hooks" / "common-probe.py",
        "from common.carrier import CARRIER\nprint(CARRIER)\n",
    )

    embedded = _embedded_tree(tmp_path / "fixture")
    _write(embedded / "common" / "carrier.py", 'CARRIER = "embedded"\n')
    monkeypatch.setattr(_tree, "embedded_tree_root", lambda: embedded)
    assert cli._embedded_common_module(embedded, "carrier").CARRIER == "embedded"

    assert cli._cmd_hook(["common-probe"], cwd=root) == 0
    assert capsys.readouterr().out.strip() == "mounted"
    assert sys.modules["common.carrier"].CARRIER == "embedded"


def test_hook_falls_back_to_the_embedded_tree_without_a_mount(tmp_path, monkeypatch, capsys):
    """Mode ``package`` has no mount at all, so this is its only path — the wiring calls the
    console script and the wheel's own tree answers."""
    embedded = _hooks(_embedded_tree(tmp_path), "embedded")
    monkeypatch.setattr(_tree, "embedded_tree_root", lambda: embedded)
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    assert cli._cmd_hook(["probe"], cwd=consumer) == 0
    assert capsys.readouterr().out.strip() == "embedded []"


def test_hook_passes_the_rest_of_argv_through_verbatim(tmp_path, capsys):
    """What lets the Codex wiring keep its dispatcher shape: ``akmon hook codex-hook role-on-code``."""
    root = _hook_project(tmp_path)
    assert cli._cmd_hook(["probe", "role-on-code", "--flag"], cwd=root) == 0
    assert capsys.readouterr().out.strip() == "mounted ['role-on-code', '--flag']"


def test_hook_puts_the_hooks_directory_on_sys_path_and_restores_it(tmp_path, capsys):
    """The hooks import each other flatly; an ordinary ``python3 <script>`` run gets that from
    ``sys.path[0]``, and ``runpy.run_path`` does not supply it. The fixture hook's neighbour
    import is the assertion — it raises ImportError without this."""
    root = _hook_project(tmp_path)
    before_path, before_argv = list(sys.path), list(sys.argv)
    assert cli._cmd_hook(["probe"], cwd=root) == 0
    assert capsys.readouterr().out.strip() == "mounted []"
    assert sys.path == before_path
    assert sys.argv == before_argv


def test_hook_accepts_the_py_suffix(tmp_path, capsys):
    root = _hook_project(tmp_path)
    assert cli._cmd_hook(["probe.py"], cwd=root) == 0
    assert capsys.readouterr().out.strip() == "mounted []"


@pytest.mark.parametrize("name", ["hooks/probe.py", "../probe", ".hidden", "a\\b"])
def test_hook_refuses_a_path_where_a_name_belongs(tmp_path, capsys, name):
    """Only generated wiring calls this, so a path is the caller's error rather than a place to
    be accommodating."""
    root = _hook_project(tmp_path)
    assert cli._cmd_hook([name], cwd=root) == 2
    assert "is a path" in capsys.readouterr().err


def test_hook_names_what_is_available_when_the_name_is_unknown(tmp_path, capsys):
    root = _hook_project(tmp_path)
    assert cli._cmd_hook(["nope"], cwd=root) == 2
    err = capsys.readouterr().err
    assert "unknown hook 'nope'" in err
    assert "probe" in err and "neighbour_mounted" in err


def test_hook_without_a_name_is_an_error(capsys):
    assert cli._cmd_hook([]) == 2
    assert "missing hook name" in capsys.readouterr().err


def test_hook_propagates_the_scripts_exit_code(tmp_path, capsys):
    root = _hook_project(tmp_path)
    assert cli._cmd_hook(["angry"], cwd=root) == 7
    assert "boom" in capsys.readouterr().err


def test_main_dispatches_hook_with_its_argv_tail(tmp_path, monkeypatch, capsys):
    root = _hook_project(tmp_path)
    monkeypatch.chdir(root)
    assert cli.main(["hook", "probe", "role-on-code"]) == 0
    assert capsys.readouterr().out.strip() == "mounted ['role-on-code']"


# --------------------------------------------------------------------------------------
# akmon version
# --------------------------------------------------------------------------------------


def test_importing_the_cli_does_not_resolve_the_package_version():
    """``akmon hook`` runs on the hottest tools of a session, and
    ``importlib.metadata.version()`` walks every installed distribution's metadata. A
    ``from akmon import __version__`` anywhere on the import path puts that cost back on every
    hook invocation, including the hooks that never ask for a version — so the CLI reaches it
    through the module and the attribute resolves lazily (PEP 562).

    Asserted in a subprocess because this test module imports ``__version__`` itself, which
    caches it into the package namespace.
    """
    result = subprocess.run(
        [sys.executable, "-c", "import akmon.cli, akmon; print('__version__' in vars(akmon))"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(_SRC)},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False", result.stderr


def test_the_version_attribute_resolves_and_caches_on_first_access():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import akmon; v = akmon.__version__; print(v); print(vars(akmon)['__version__'] == v)",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(_SRC)},
    )
    assert result.returncode == 0, result.stderr
    version, cached = result.stdout.split()
    assert version == __version__
    assert cached == "True"


def test_the_package_namespace_has_no_other_lazy_attributes():
    with pytest.raises(AttributeError):
        akmon.__getattr__("nope")


def test_cmd_version_prints_package_version(capsys):
    assert cli._cmd_version() == 0
    assert capsys.readouterr().out.strip() == __version__


# --------------------------------------------------------------------------------------
# akmon init — dispatched to akmon._init (behaviour lives in meta/tests/test_init.py)
# --------------------------------------------------------------------------------------


def test_cmd_init_delegates_to_the_init_module(monkeypatch):
    from akmon import _init

    seen = {}

    def fake_main(argv):
        seen["argv"] = argv
        return 0

    monkeypatch.setattr(_init, "main", fake_main)
    assert cli._cmd_init(["--mode", "vendored"]) == 0
    assert seen["argv"] == ["--mode", "vendored"]


def test_main_passes_init_flags_through(monkeypatch):
    from akmon import _init

    monkeypatch.setattr(_init, "main", lambda argv: 7 if argv == ["--mode", "package", "--yes"] else 1)
    assert cli.main(["init", "--mode", "package", "--yes"]) == 7


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
    fixture_tree = _embedded_tree(tmp_path)
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
