"""The tool's data: every constant, bar and name that is not code, read from ``profile.json``.

Both implementations of the probe (this one and ``js/tools/model_profile/``) read the same
file, so a bar, a family name, a path or a limit is written once and a score made by one twin
is comparable with a score made by the other. Code - the rules, the grading, the sandbox's
argv - stays separate in each language.

Nothing is read at import time: :func:`load` reads and validates the file on the first call and
hands the same :class:`Settings` back afterwards. The in-container runner's source is a Python
program that both twins ship to the container; it lives in a file of its own (named by
``sandbox.runner_source_file``) and :func:`runner_source` reads it the same way.
"""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_HERE = Path(__file__).resolve().parent

#: The data file, next to this module.
PROFILE_FILE = "profile.json"


class SettingsError(RuntimeError):
    """``profile.json`` or the in-container runner's source is missing or malformed."""


@dataclass(frozen=True)
class Gate:
    """A bar one (model, family) cell is measured against; ``family`` ``None`` means every family."""

    name: str
    family: str | None
    metric: str
    operator: Literal[">=", "<="]
    threshold: float
    meaning: str


@dataclass(frozen=True)
class Band:
    """The pass-rate band an item must sit in across the pool of models to separate them."""

    name: str
    low: float
    high: float
    min_scored: int
    meaning: str


@dataclass(frozen=True)
class CaseKeys:
    """The keys a case, its bug, its asks and its hidden test must carry."""

    case: tuple[str, ...]
    bug: tuple[str, ...]
    ask: tuple[str, ...]
    hidden_test: tuple[str, ...]


@dataclass(frozen=True)
class Families:
    """The families the runner knows, the one that asks for a location and the ones that ask for a patch."""

    known: tuple[str, ...]
    hunt: str
    fix: tuple[str, ...]


@dataclass(frozen=True)
class EnvelopeDefaults:
    """The pinned request envelope's knobs."""

    temperature: float
    max_output_tokens: int
    timeout_s: int
    response_format: str


@dataclass(frozen=True)
class RunSettings:
    """The verdict names, the budget reason and the names of the files a run writes."""

    verdicts: tuple[str, ...]
    budget_reason: str
    ledger_file: str
    detail_dir: str


@dataclass(frozen=True)
class Estimate:
    """The four constants the cost estimate stands on."""

    call_seconds: float
    sandbox_seconds: float
    chars_per_token: int
    output_tokens: int


@dataclass(frozen=True)
class TransportSettings:
    """The endpoint's paths, its stream marker, the default scaffold and the transport's own limits."""

    completions_path: str
    models_path: str
    done_sentinel: str
    direct_scaffold: str
    models_timeout_s: int
    error_detail_chars: int


@dataclass(frozen=True)
class SandboxSettings:
    """The container's image and limits, the names the sandbox owns and docker's failure codes."""

    image: str
    default_timeout_s: int
    memory_limit: str
    pids_limit: str
    workspace_size: str
    container_user: str
    work_dir: str
    result_prefix: str
    runner_file: str
    nonce_file: str
    runner_source_file: str
    docker_failure_codes: tuple[int, ...]
    docker_command_timeout_s: int
    detail_chars: int


@dataclass(frozen=True)
class CliSettings:
    """The command line's defaults."""

    default_token_env: str
    out_subdir: str
    default_items: str


@dataclass(frozen=True)
class Settings:
    """Everything ``profile.json`` holds, as typed objects."""

    hash_length: int
    families: Families
    case_keys: CaseKeys
    envelope: EnvelopeDefaults
    run: RunSettings
    estimate: Estimate
    gates: tuple[Gate, ...]
    item_band: Band
    transport: TransportSettings
    sandbox: SandboxSettings
    cli: CliSettings


def _section(document: dict, name: str) -> dict:
    section = document.get(name)
    if not isinstance(section, dict):
        raise SettingsError(f"{PROFILE_FILE} has no {name!r} object")
    return section


def _parse(document: dict) -> Settings:
    families = _section(document, "families")
    keys = _section(document, "case_keys")
    run = _section(document, "run")
    sandbox = dict(_section(document, "sandbox"))
    sandbox["docker_failure_codes"] = tuple(sandbox["docker_failure_codes"])
    return Settings(
        hash_length=document["hash_length"],
        families=Families(known=tuple(families["known"]), hunt=families["hunt"], fix=tuple(families["fix"])),
        case_keys=CaseKeys(**{name: tuple(value) for name, value in keys.items()}),
        envelope=EnvelopeDefaults(**_section(document, "envelope")),
        run=RunSettings(**{**run, "verdicts": tuple(run["verdicts"])}),
        estimate=Estimate(**_section(document, "estimate")),
        gates=tuple(Gate(**gate) for gate in document["gates"]),
        item_band=Band(**_section(document, "item_band")),
        transport=TransportSettings(**_section(document, "transport")),
        sandbox=SandboxSettings(**sandbox),
        cli=CliSettings(**_section(document, "cli")),
    )


@functools.cache
def load() -> Settings:
    """Read ``profile.json`` once and hand back its typed contents.

    Raises:
        SettingsError: the file is missing, is not JSON, or lacks a section or a key.
    """
    path = _HERE / PROFILE_FILE
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SettingsError(f"the model-profile data file cannot be read: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SettingsError(f"the model-profile data file {path} is not valid JSON: {exc}") from exc
    try:
        return _parse(document)
    except (KeyError, TypeError) as exc:
        raise SettingsError(f"the model-profile data file {path} is malformed: {exc!r}") from exc


@functools.cache
def runner_source() -> str:
    """The source of the program that runs the hidden test inside the container.

    Raises:
        SettingsError: the file is missing.
    """
    path = _HERE / load().sandbox.runner_source_file
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return handle.read()
    except OSError as exc:
        raise SettingsError(f"the in-container runner's source cannot be read: {path}: {exc}") from exc
