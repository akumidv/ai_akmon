"""Unit tests for the model-alias refresh tool (``tools/model_routing/models.py``, ADR 0024/D16).

The tool reads a provider's declared catalog only when it is run, and writes the generated
``<aitna_root>/local/model-aliases.json``. Every test points ``HOME`` at a scratch directory, so the
real ``~/.codex`` is never read.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_AKMON = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_ROUTING_DIR = _AKMON / "tools" / "model_routing"
if str(_ROUTING_DIR) not in sys.path:
    sys.path.insert(0, str(_ROUTING_DIR))

import models  # noqa: E402
import routing  # noqa: E402

_HOST_SLUGS = [
    ("gpt-6.1-sol", "list", 0),
    ("gpt-6.1-terra", "list", 1),
    ("gpt-6-astra", "list", 3),
    ("gpt-6-sol", "list", 4),
    ("gpt-reserve", "hide", 4),
    ("gpt-6-luna", "list", 5),
    ("gpt-5.6-sol", "list", 6),
    ("gpt-5.6-terra", "list", 7),
    ("gpt-5.6-luna", "list", 8),
    ("codex-auto-review", "hide", 43),
]
_REGISTRY = {
    "providers": {
        "codex": {
            "operation": "review",
            "model_flag": "--model {model}",
            "family": "gpt",
            "models": ["luna", "terra", "sol"],
            "aliases": True,
            "catalog": {"file": "~/.codex/models_cache.json", "format": "codex-models-cache"},
        },
        "claude": {"operation": "review", "model_flag": "--model {model}", "family": "claude", "models": ["opus"]},
    },
    "second_opinion_policy": {"ladder": ["codex"], "model_rule": "max"},
}


def _project(tmp_path: Path, registry: dict = _REGISTRY) -> Path:
    root = tmp_path / "proj"
    (root / "_aitna" / "akmon" / "tools" / "model_routing").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# project\n", encoding="utf-8")
    (root / "_aitna" / "akmon" / "tools" / "model_routing" / "registry.json").write_text(
        json.dumps(registry), encoding="utf-8"
    )
    return root


def _catalog(tmp_path: Path, slugs=_HOST_SLUGS, text: str | None = None) -> Path:
    path = tmp_path / "home" / ".codex" / "models_cache.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "client_version": "0.164.0",
        "models": [{"slug": slug, "visibility": vis, "priority": pri} for slug, vis, pri in slugs],
    }
    path.write_text(json.dumps(body) if text is None else text, encoding="utf-8")
    return path


def _run(tmp_path: Path, monkeypatch, *argv: str) -> int:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return models.main(["--project-root", str(tmp_path / "proj"), *argv])


def _stored(tmp_path: Path) -> dict:
    return json.loads(routing.local_aliases_path(tmp_path / "proj").read_text(encoding="utf-8"))


def test_refresh_writes_the_file_with_the_highest_version_of_each_alias(tmp_path, monkeypatch, capsys):
    _project(tmp_path)
    _catalog(tmp_path)

    assert _run(tmp_path, monkeypatch, "--refresh") == 0

    assert _stored(tmp_path) == {
        "codex": {
            "source": "~/.codex/models_cache.json (codex-models-cache)",
            "client": "0.164.0",
            "aliases": {"luna": "gpt-6-luna", "terra": "gpt-6.1-terra", "sol": "gpt-6.1-sol"},
        }
    }
    assert capsys.readouterr().out == (
        "catalog codex: source=~/.codex/models_cache.json (codex-models-cache) client=0.164.0\n"
        "  luna → gpt-6-luna\n  terra → gpt-6.1-terra\n  sol → gpt-6.1-sol\n"
        "wrote _aitna/local/model-aliases.json\n"
    )


def test_a_second_refresh_is_idempotent_and_says_unchanged(tmp_path, monkeypatch, capsys):
    _project(tmp_path)
    _catalog(tmp_path)
    assert _run(tmp_path, monkeypatch, "--refresh") == 0
    path = routing.local_aliases_path(tmp_path / "proj")
    first = path.read_bytes()
    mtime = path.stat().st_mtime_ns
    capsys.readouterr()

    assert _run(tmp_path, monkeypatch, "--refresh") == 0

    assert path.read_bytes() == first
    assert path.stat().st_mtime_ns == mtime
    assert capsys.readouterr().out.endswith("_aitna/local/model-aliases.json unchanged\n")


def test_dry_run_writes_nothing_and_says_what_it_would_write(tmp_path, monkeypatch, capsys):
    _project(tmp_path)
    _catalog(tmp_path)

    assert _run(tmp_path, monkeypatch, "--refresh", "--dry-run") == 0

    assert not routing.local_aliases_path(tmp_path / "proj").exists()
    assert capsys.readouterr().out.endswith("would write _aitna/local/model-aliases.json\n")


def test_the_listing_shows_what_is_stored_and_what_a_refresh_would_write_without_writing(tmp_path, monkeypatch, capsys):
    _project(tmp_path)
    _catalog(tmp_path)

    assert _run(tmp_path, monkeypatch) == 0
    before = capsys.readouterr().out
    assert _run(tmp_path, monkeypatch, "--refresh") == 0
    capsys.readouterr()
    assert _run(tmp_path, monkeypatch) == 0
    after = capsys.readouterr().out

    assert before.startswith("stored codex: none\ncatalog codex: source=")
    assert before.endswith("would write _aitna/local/model-aliases.json\n")
    assert after.startswith("stored codex: source=~/.codex/models_cache.json (codex-models-cache) client=0.164.0\n")
    assert after.endswith("would leave _aitna/local/model-aliases.json unchanged\n")


def test_an_alias_the_catalog_does_not_list_is_reported_and_left_unmapped(tmp_path, monkeypatch, capsys):
    _project(tmp_path)
    _catalog(tmp_path, [("gpt-6.1-sol", "list", 0), ("gpt-6-luna", "list", 5)])

    assert _run(tmp_path, monkeypatch, "--refresh") == 0

    assert _stored(tmp_path)["codex"]["aliases"] == {"luna": "gpt-6-luna", "sol": "gpt-6.1-sol"}
    assert "  terra: no match in the catalog; left unmapped\n" in capsys.readouterr().out


def test_a_refresh_replaces_a_stale_mapping_and_keeps_other_providers(tmp_path, monkeypatch):
    root = _project(tmp_path)
    path = routing.local_aliases_path(root)
    path.parent.mkdir(parents=True)
    other = {"other": routing.ProviderAliases("s", None, {"a": "b"})}
    stale = {"codex": routing.ProviderAliases("old", "0.1", {"sol": "gpt-5-sol"}), **other}
    path.write_text(routing.model_aliases_document(stale), encoding="utf-8")
    _catalog(tmp_path)

    assert _run(tmp_path, monkeypatch, "--refresh", "--provider", "codex") == 0

    stored = _stored(tmp_path)
    assert list(stored) == ["codex", "other"]
    assert stored["codex"]["aliases"]["sol"] == "gpt-6.1-sol"
    assert stored["other"] == {"source": "s", "client": None, "aliases": {"a": "b"}}


def test_a_refresh_replaces_a_generated_file_that_is_not_valid(tmp_path, monkeypatch):
    root = _project(tmp_path)
    path = routing.local_aliases_path(root)
    path.parent.mkdir(parents=True)
    path.write_text("garbage", encoding="utf-8")
    _catalog(tmp_path)

    assert _run(tmp_path, monkeypatch, "--refresh") == 0

    assert "sol" in _stored(tmp_path)["codex"]["aliases"]


def test_a_catalog_without_a_client_version_stores_null(tmp_path, monkeypatch):
    _project(tmp_path)
    _catalog(tmp_path, text=json.dumps({"models": [{"slug": "gpt-6-sol", "visibility": "list", "priority": 1}]}))

    assert _run(tmp_path, monkeypatch, "--refresh") == 0

    assert _stored(tmp_path)["codex"]["client"] is None


@pytest.mark.parametrize(
    ("argv", "line"),
    [
        (
            ("--refresh", "--provider", "nope"),
            "models: --provider names 'nope', which the providers table does not declare",
        ),
        (
            ("--refresh", "--provider", "claude"),
            "models: providers.claude declares no `catalog`; there is nothing to refresh its model aliases from",
        ),
    ],
)
def test_a_refusal_is_one_line_naming_the_provider_and_exit_2(tmp_path, monkeypatch, capsys, argv, line):
    _project(tmp_path)
    _catalog(tmp_path)

    assert _run(tmp_path, monkeypatch, *argv) == 2

    captured = capsys.readouterr()
    assert captured.err == line + "\n"
    assert captured.out == ""


def test_a_missing_catalog_is_refused_naming_the_file_and_the_row_key(tmp_path, monkeypatch, capsys):
    _project(tmp_path)

    assert _run(tmp_path, monkeypatch, "--refresh") == 2

    err = capsys.readouterr().err
    assert err.startswith("models: ~/.codex/models_cache.json (providers.codex.catalog.file) does not exist;")
    assert err.count("\n") == 1
    assert not routing.local_aliases_path(tmp_path / "proj").exists()


@pytest.mark.parametrize(
    ("text", "reason"),
    [("not json", "is not valid JSON"), ("[]", "holds no `models` list")],
)
def test_an_unreadable_catalog_is_refused_naming_the_file_and_the_row_key(tmp_path, monkeypatch, capsys, text, reason):
    _project(tmp_path)
    _catalog(tmp_path, text=text)

    assert _run(tmp_path, monkeypatch, "--refresh") == 2

    assert capsys.readouterr().err == f"models: ~/.codex/models_cache.json (providers.codex.catalog) {reason}\n"


def test_no_provider_with_a_catalog_is_refused(tmp_path, monkeypatch, capsys):
    registry = {**_REGISTRY, "providers": {"claude": _REGISTRY["providers"]["claude"]}}
    _project(tmp_path, registry)

    assert _run(tmp_path, monkeypatch, "--refresh") == 2

    assert capsys.readouterr().err.startswith("models: no provider row declares a `catalog`;")


def test_a_row_with_a_malformed_catalog_is_refused(tmp_path, monkeypatch, capsys):
    registry = {"providers": {"codex": {**_REGISTRY["providers"]["codex"], "catalog": "~/x.json"}}}
    _project(tmp_path, registry)

    assert _run(tmp_path, monkeypatch, "--refresh") == 2

    assert capsys.readouterr().err.startswith("models: providers.codex.catalog must be an object")


def test_the_refresh_reads_the_declared_catalog_with_the_tilde_expanded_from_home(tmp_path, monkeypatch):
    """The catalog is read by ``main``, the one explicit place (D11 holds for every other path)."""
    seen: list[Path] = []
    original = Path.read_text

    def spy(self, *args, **kwargs):
        seen.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy)
    _project(tmp_path)
    _catalog(tmp_path)
    seen.clear()

    assert _run(tmp_path, monkeypatch, "--refresh") == 0

    assert tmp_path / "home" / ".codex" / "models_cache.json" in seen


def test_a_models_entry_with_an_effort_is_the_alias_before_the_at_sign_listed_once(tmp_path, monkeypatch, capsys):
    row = {
        **_REGISTRY["providers"]["codex"],
        "models": ["luna", "sol", "sol@high"],
        "efforts": {"flag": "-c e={effort}", "levels": ["low", "high"]},
    }
    _project(tmp_path, {"providers": {"codex": row}})
    _catalog(tmp_path)

    assert _run(tmp_path, monkeypatch, "--refresh") == 0

    assert _stored(tmp_path)["codex"]["aliases"] == {"luna": "gpt-6-luna", "sol": "gpt-6.1-sol"}
    assert "unmapped" not in capsys.readouterr().out
