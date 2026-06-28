"""Unit tests for the release-check test-runner resolution (``release_check``).

Focus: how ``_pytest_command`` picks a runner — the pinned ``[test].runner`` from the
integration record first, then discovery. ``release_check`` lives under ``tools/release/`` (not
on the test ``sys.path``), so load it by file path. Nothing touches the real repo.
"""

from __future__ import annotations

import builtins
import importlib.util
from pathlib import Path

import pytest

_KEYSTONE = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_spec = importlib.util.spec_from_file_location(
    "release_check", _KEYSTONE / "tools" / "release" / "release_check.py"
)
release_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_check)


def _attach(root: Path, body: str) -> None:
    (root / "_forge").mkdir(parents=True, exist_ok=True)
    (root / "_forge" / ".keystone.toml").write_text(body, encoding="utf-8")


def test_pinned_runner_is_used_verbatim_with_test_path(tmp_path):
    _attach(tmp_path, 'keystone_version = "v9"\n\n[test]\nrunner = "poetry run pytest"\n')
    assert release_check._pytest_command(tmp_path, "TESTS") == ["poetry", "run", "pytest", "TESTS"]


def test_pinned_runner_ignores_comments_and_blank_value(tmp_path):
    _attach(tmp_path, '# runner = "not this one"\n[test]\nrunner = ""\n')  # commented + empty → no pin
    assert release_check._pinned_test_runner(tmp_path) is None


def test_no_attach_record_falls_back_to_discovery(tmp_path):
    # No .keystone.toml at all: discovery must still yield a runnable pytest invocation.
    assert release_check._pinned_test_runner(tmp_path) is None
    cmd = release_check._pytest_command(tmp_path, "TESTS")
    assert cmd[-1] == "TESTS" and "pytest" in " ".join(cmd)


def test_dev_venv_discovered_as_python_dash_m(tmp_path):
    # A discovered dev venv must be invoked as `<venv>/bin/python -m pytest`, never bin/pytest.
    venv_python = tmp_path / "_forge" / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("#!/bin/sh\n", encoding="utf-8")
    cmd = release_check._pytest_command(tmp_path, "TESTS")
    assert cmd == [str(venv_python), "-m", "pytest", "TESTS"]


def test_toml_read_falls_back_when_tomllib_absent(tmp_path, monkeypatch):
    # Host Python < 3.11 has no tomllib: the stdlib line-parser fallback must still read the record.
    _attach(tmp_path, 'keystone_version = "v9"\n\n[test]\nrunner = "poetry run pytest"\n')
    real_import = builtins.__import__

    def no_tomllib(name, *args, **kwargs):
        if name == "tomllib":
            raise ImportError("simulated: no tomllib on this host")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_tomllib)
    assert release_check._pinned_test_runner(tmp_path) == "poetry run pytest"
