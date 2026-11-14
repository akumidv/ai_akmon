"""Tests for the Python wrapper of ``akmon tool browser`` (``tools/browser.py``, ADR 0032/D02).

The wrapper adds no behaviour: it finds Node, needs major 22, and passes arguments, streams and the
exit status through. These tests run a copy of it inside a throwaway tree whose ``js/tools/browser.mjs``
is a stub, so no Chrome, no network and no real implementation is involved.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_AKMON = Path(__file__).resolve().parents[2]
_NODE = shutil.which("node")


def _tree(tmp_path: Path, stub: str) -> Path:
    """A tree holding the wrapper and a stub ``browser.mjs``; returns the wrapper's path."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "js" / "tools").mkdir(parents=True)
    wrapper = tmp_path / "tools" / "browser.py"
    shutil.copy(_AKMON / "tools" / "browser.py", wrapper)
    (tmp_path / "js" / "tools" / "browser.mjs").write_text(stub, encoding="utf-8")
    return wrapper


def _run(
    wrapper: Path,
    *args: str,
    path: str | None = None,
    stdin: str = "",
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {"PATH": path, **(extra_env or {})} if path is not None else None
    return subprocess.run(
        [sys.executable, "-I", str(wrapper), *args], input=stdin, capture_output=True, text=True, check=False, env=env
    )


def test_no_node_on_path_is_one_line_and_exit_2(tmp_path: Path) -> None:
    wrapper = _tree(tmp_path, "")
    result = _run(wrapper, "status", path=str(tmp_path / "empty"))
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.splitlines() == [
        "akmon tool browser: Node.js 22 or newer is required and `node` is not on PATH"
    ]


def _fake_node(directory: Path, version: str) -> Path:
    """A ``node`` that only answers ``--version``."""
    directory.mkdir()
    node = directory / "node"
    node.write_text(f'#!/bin/sh\n[ "$1" = "--version" ] && echo {version} && exit 0\nexit 99\n', encoding="utf-8")
    node.chmod(0o755)
    return directory


def test_node_older_than_the_floor_is_one_line_and_exit_2(tmp_path: Path) -> None:
    wrapper = _tree(tmp_path, "")
    result = _run(wrapper, "status", path=str(_fake_node(tmp_path / "old", "v20.11.1")))
    assert result.returncode == 2
    lines = result.stderr.splitlines()
    assert len(lines) == 1
    assert "Node.js 22 or newer is required, found 20.11.1" in lines[0]


@pytest.mark.skipif(_NODE is None, reason="node is not on PATH")
def test_arguments_streams_and_exit_status_pass_through(tmp_path: Path) -> None:
    stub = (
        "import fs from 'node:fs';\n"
        "process.stdout.write(JSON.stringify(process.argv.slice(2)) + '\\n');\n"
        "process.stdout.write('stdin:' + fs.readFileSync(0, 'utf8') + '\\n');\n"
        "process.stderr.write('to stderr\\n');\n"
        "process.exitCode = 7;\n"
    )
    version = subprocess.run([_NODE, "--version"], capture_output=True, text=True, check=True).stdout  # type: ignore[list-item]
    if int(version.strip().removeprefix("v").split(".")[0]) < 22:
        pytest.skip("node is older than 22")
    wrapper = _tree(tmp_path, stub)
    node_dir = str(Path(_NODE).parent)  # type: ignore[arg-type]
    result = _run(wrapper, "start", "--url", "https://example.org", path=node_dir, stdin="hello")
    assert result.returncode == 7
    assert result.stdout.splitlines() == ['["start","--url","https://example.org"]', "stdin:hello"]
    assert result.stderr == "to stderr\n"


@pytest.mark.skipif(_NODE is None, reason="node is not on PATH")
def test_the_environment_passes_through_so_akmon_browser_root_reaches_the_tool(tmp_path: Path) -> None:
    stub = "process.stdout.write(`${process.env.AKMON_BROWSER_ROOT}\\n`);\n"
    version = subprocess.run([_NODE, "--version"], capture_output=True, text=True, check=True).stdout  # type: ignore[list-item]
    if int(version.strip().removeprefix("v").split(".")[0]) < 22:
        pytest.skip("node is older than 22")
    wrapper = _tree(tmp_path, stub)
    node_dir = str(Path(_NODE).parent)  # type: ignore[arg-type]
    result = _run(wrapper, "status", path=node_dir, extra_env={"AKMON_BROWSER_ROOT": "/work/installation"})
    assert result.stdout == "/work/installation\n"


def test_a_node_that_does_not_answer_is_one_line_and_exit_2(tmp_path: Path) -> None:
    wrapper = _tree(tmp_path, "")
    broken = tmp_path / "broken"
    broken.mkdir()
    node = broken / "node"
    node.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    node.chmod(0o755)
    result = _run(wrapper, "status", path=str(broken))
    assert result.returncode == 2
    assert result.stderr.splitlines() == [
        f"akmon tool browser: Node.js 22 or newer is required; `{node} --version` did not answer"
    ]


def _load_wrapper() -> ModuleType:
    """The wrapper imported from its file, to call ``main`` in this process."""
    spec = importlib.util.spec_from_file_location("akmon_browser_wrapper", _AKMON / "tools" / "browser.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_node_version_raises_a_typed_error_instead_of_returning_none(monkeypatch: pytest.MonkeyPatch) -> None:
    wrapper = _load_wrapper()

    def garbled(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, stdout="not a version\n")

    monkeypatch.setattr(wrapper.subprocess, "run", garbled)
    with pytest.raises(wrapper.NodeUnusableError, match="did not answer"):
        wrapper._node_version("node")

    def missing(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("node")

    monkeypatch.setattr(wrapper.subprocess, "run", missing)
    with pytest.raises(wrapper.NodeUnusableError, match="did not answer"):
        wrapper._node_version("node")


@pytest.mark.parametrize("interrupted_call", [1, 2], ids=["version check", "tool run"])
def test_ctrl_c_ends_without_a_traceback_and_exits_130(
    interrupted_call: int, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    wrapper = _load_wrapper()
    calls = {"count": 0}

    def run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls["count"] += 1
        if calls["count"] == interrupted_call:
            raise KeyboardInterrupt
        return subprocess.CompletedProcess([], 0, stdout="v24.0.0\n")

    monkeypatch.setattr(wrapper.subprocess, "run", run)
    assert wrapper.main(["status"], node="node") == 130
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")


def test_the_wrapper_imports_nothing_outside_the_standard_library() -> None:
    source = (_AKMON / "tools" / "browser.py").read_text(encoding="utf-8")
    imports = {line.split()[1].split(".")[0] for line in source.splitlines() if line.startswith(("import ", "from "))}
    assert imports <= set(sys.stdlib_module_names) | {"__future__"}
