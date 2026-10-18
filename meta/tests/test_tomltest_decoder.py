"""The toml-test decoder adapter fences TOML 1.0.0 with the record reader's own fence (C117).

``meta/conformance/tomltest/decoder.mjs`` once carried an older copy of the fence that missed the
``\\e`` escape and a line break in an inline table nested in an array. It now asks
``js/common/toml10.mjs::toml10Refusal``; these rows pin both cases and the tagged output of a
document the fence lets through.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DECODER = ROOT / "meta" / "conformance" / "tomltest" / "decoder.mjs"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="the adapter runs on node")


def _decode(document: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(DECODER)], input=document, capture_output=True, text=True, encoding="utf-8", check=False
    )


@pytest.mark.parametrize(
    ("document", "reason"),
    [
        ('a = "\\e"\n', "the \\e escape is a TOML 1.1.0 feature"),
        ('a = "\\x41"\n', "the \\x escape is a TOML 1.1.0 feature"),
        ("a = [{a = 1,\n b = 2}]\n", "line break inside an inline table"),
        ("a = {b = 1,}\n", "trailing comma in an inline table"),
    ],
)
def test_a_toml_1_1_construct_is_refused_with_the_fences_reason(document, reason):
    result = _decode(document)
    assert result.returncode == 1
    assert result.stdout == ""
    assert reason in result.stderr


def test_a_toml_1_0_document_is_tagged():
    result = _decode('a = [{b = 1}, "x"]\nc = 1.5\nd = 1979-05-27T07:32:00Z\n')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "a": [{"b": {"type": "integer", "value": "1"}}, {"type": "string", "value": "x"}],
        "c": {"type": "float", "value": "1.5"},
        "d": {"type": "datetime", "value": "1979-05-27T07:32:00Z"},
    }
