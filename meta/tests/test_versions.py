"""``common/versions.py::switch_tag`` — the ref every printed switch to the JavaScript implementation names.

The JavaScript twin (``js/common/versions.mjs::switchTag``) pins the same cases in
``js/common/versions.test.mjs``.
"""

from __future__ import annotations

import pytest

from common.versions import switch_tag


@pytest.mark.parametrize(
    ("recorded", "running", "tag"),
    [
        pytest.param("0.3.0", "0.5.0", "v0.5.0", id="the running release is newer"),
        pytest.param("0.6.0", "0.5.0", "v0.6.0", id="the recorded release is newer"),
        pytest.param("v0.5.0", "0.5.0", "v0.5.0", id="one release, two spellings"),
        pytest.param("0.3.0", None, "v0.3.0", id="no running version"),
        pytest.param(None, "0.5.0", "v0.5.0", id="no recorded version"),
        pytest.param("0.3.0", "0.5.0.dev0", "main", id="a newer development version has no tag"),
        pytest.param("0.6.0", "0.5.0.dev0", "v0.6.0", id="an older development version loses"),
        pytest.param("v0.5.0-3-gabc1234", "0.5.0", "main", id="a distance past the tag is newer and no release"),
        pytest.param("", "not-a-version", "main", id="nothing placeable"),
        pytest.param(None, None, "main", id="nothing at all"),
    ],
)
def test_switch_tag_names_the_newer_release(recorded, running, tag):
    assert switch_tag(recorded, running) == tag
