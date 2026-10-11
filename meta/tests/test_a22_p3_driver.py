from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

MODULE_PATH = Path(__file__).parents[1] / "experiments" / "a22-p3" / "driver.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("a22_p3_driver", MODULE_PATH)
assert SPEC and SPEC.loader
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


@pytest.mark.parametrize("attempt_class", ["scored", "technical"])
def test_non_defect_subject_attempt_has_no_origin(attempt_class):
    driver.validate_attempt_class(attempt_class, None)


def test_defect_subject_attempt_requires_opaque_origin():
    origin = "0123456789abcdef0123456789abcdef"
    driver.validate_attempt_class("defect", origin)
    for invalid in (None, "run-1", "A" * 32, "0" * 31):
        with pytest.raises(ValueError, match="immutable 128-bit origin"):
            driver.validate_attempt_class("defect", invalid)


@pytest.mark.parametrize("attempt_class", [None, "route_check", "Scored"])
def test_new_subject_attempt_requires_supported_explicit_class(attempt_class):
    with pytest.raises(ValueError, match="explicitly set"):
        driver.validate_attempt_class(attempt_class, None)


def test_only_defect_attempt_can_name_origin():
    with pytest.raises(ValueError, match="only a defect"):
        driver.validate_attempt_class("scored", "0123456789abcdef0123456789abcdef")


def test_turn_usage_requires_input_and_output_and_rejects_bool():
    assert driver._turn_usage({"last_token_usage": {"input_tokens": 8, "output_tokens": 2}}) == {
        "input_tokens": 8, "output_tokens": 2,
    }
    assert driver._turn_usage({"last_token_usage": {"input_tokens": 8, "output_tokens": 0}}) == {
        "input_tokens": 8, "output_tokens": 0,
    }
    for usage in (
        {"input_tokens": 8},
        {"input_tokens": True, "output_tokens": 2},
        {"input_tokens": 8, "output_tokens": False},
        {"input_tokens": 8, "output_tokens": -1},
    ):
        assert driver._turn_usage({"last_token_usage": usage}) is None
