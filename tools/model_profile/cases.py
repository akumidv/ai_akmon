"""The probe item set: load it, validate it, and name the measurement it defines.

The item set is the yardstick. A case is a small synthetic program with one planted defect,
clean decoy files beside it, a hidden test that must separate the buggy program from the fixed
one, and one ask per family. Two hashes identify the measurement, and a score without them
cannot be compared with another score:

* ``cases_sha`` - the content of the item set: the items file itself plus every embedded file
  source, hashed by content and never by filename, so editing a fixture changes the
  yardstick's identity and moving the file does not.
* ``envelope_sha`` - the request envelope: the pinned temperature, the output-token cap, the
  timeout, the response format and the system prompts used. Two rows are comparable only when
  their envelopes match.

The set is **validated at load time and a malformed set raises** - it never half-loads. The
rules: every family a case names has an ask, the hidden test lives inside the case's own
namespace and never collides with a program file, and the oracle is never authored by a model.

``fixed_files`` is a **patch over** ``files``, not a second full program: the seed set carries
only the fixed copy of the defective file, and the fixed program is the case's files with that
patch applied.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import settings

# The families, the keys a case must carry and the length of a hash as the ledger writes it
# are data: ``profile.json``, read through ``settings.load()``.


class ItemSetError(ValueError):
    """The item set is malformed - raised at load time, never half-loaded."""


@dataclass(frozen=True)
class Bug:
    """Where the defect is: the file, the function inside it, and what kind of defect it is."""

    file: str
    function: str
    kind: str


@dataclass(frozen=True)
class HiddenTest:
    """The oracle: the test file that must fail on the buggy program and pass on the fixed one."""

    path: str
    content: str


@dataclass(frozen=True)
class Ask:
    """One family's prompt: the system instruction and the user's question."""

    system: str
    user: str


@dataclass(frozen=True)
class Case:
    """One probe item: a buggy program, its fixed twin, an oracle and one ask per family."""

    id: str
    families: tuple[str, ...]
    bug: Bug
    files: Mapping[str, str]
    fixed_files: Mapping[str, str]
    hidden_test: HiddenTest
    asks: Mapping[str, Ask]

    def program(self) -> dict[str, str]:
        """The buggy program as the sandbox sees it."""
        return dict(self.files)

    def fixed_program(self) -> dict[str, str]:
        """The fixed program: the case's files with ``fixed_files`` patched over them."""
        program = dict(self.files)
        program.update(self.fixed_files)
        return program

    def ask(self, family: str) -> Ask:
        """The prompt for ``family`` - raises when the case does not carry that family."""
        try:
            return self.asks[family]
        except KeyError as exc:
            raise ItemSetError(f"case {self.id!r} has no ask for family {family!r}") from exc


@dataclass(frozen=True)
class Envelope:
    """The pinned request envelope - everything that makes two scores comparable.

    The temperature is pinned at 0 because a single run's pass@1 moves by several points
    without it, and the output-token cap is what stops a runaway answer. Every call streams;
    that is part of the transport, not a knob.
    """

    temperature: float = field(default_factory=lambda: settings.load().envelope.temperature)
    max_output_tokens: int = field(default_factory=lambda: settings.load().envelope.max_output_tokens)
    timeout_s: int = field(default_factory=lambda: settings.load().envelope.timeout_s)
    response_format: str = field(default_factory=lambda: settings.load().envelope.response_format)


@dataclass(frozen=True)
class ItemSet:
    """A validated item set and the two hashes that identify it."""

    version: str
    cases: tuple[Case, ...]
    cases_sha: str
    envelope_sha: str
    families: tuple[str, ...]

    def select(self, case_ids: Sequence[str] | None = None, families: Sequence[str] | None = None) -> tuple[Case, ...]:
        """The cases of this set, narrowed by id and by family."""
        wanted_ids = None if case_ids is None else set(case_ids)
        chosen = [case for case in self.cases if wanted_ids is None or case.id in wanted_ids]
        if families is None:
            return tuple(chosen)
        wanted = set(families)
        return tuple(case for case in chosen if wanted.intersection(case.families))


def _update_with_text(update: Callable[[bytes], None], text: str) -> None:
    update(text.encode("utf-8"))
    update(b"\0")


def cases_sha(raw: bytes, cases: Sequence[Case]) -> str:
    """The hash of the item set's content: the items file plus every embedded source.

    Content, never filename: moving the items file does not change the hash, editing a fixture
    does.
    """
    digest = hashlib.sha256()
    digest.update(raw)
    for case in sorted(cases, key=lambda item: item.id):
        for path in sorted(case.files):
            _update_with_text(digest.update, case.files[path])
        for path in sorted(case.fixed_files):
            _update_with_text(digest.update, case.fixed_files[path])
        _update_with_text(digest.update, case.hidden_test.content)
    return digest.hexdigest()[: settings.load().hash_length]


def envelope_sha(envelope: Envelope, system_prompts: Sequence[str]) -> str:
    """The hash of the request envelope: its knobs and the system prompts used."""
    payload = {
        "temperature": envelope.temperature,
        "max_output_tokens": envelope.max_output_tokens,
        "timeout_s": envelope.timeout_s,
        "response_format": envelope.response_format,
        "system_prompts": sorted(set(system_prompts)),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[: settings.load().hash_length]


def _require_mapping(value: object, where: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ItemSetError(f"{where} must be an object, got {type(value).__name__}")
    return value


def _require_text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ItemSetError(f"{where} must be a non-empty string")
    return value


def _require_relative_path(value: object, where: str) -> str:
    text = _require_text(value, where)
    path = Path(text)
    if path.is_absolute() or ".." in path.parts:
        raise ItemSetError(f"{where} must stay inside the case, got {text!r}")
    return text


def _require_keys(mapping: Mapping[str, object], keys: Sequence[str], where: str) -> None:
    missing = [key for key in keys if key not in mapping]
    if missing:
        raise ItemSetError(f"{where} is missing {', '.join(missing)}")


def _parse_bug(raw: object, where: str) -> Bug:
    mapping = _require_mapping(raw, where)
    _require_keys(mapping, settings.load().case_keys.bug, where)
    return Bug(
        file=_require_relative_path(mapping["file"], f"{where}.file"),
        function=_require_text(mapping["function"], f"{where}.function"),
        kind=_require_text(mapping["kind"], f"{where}.kind"),
    )


def _parse_files(raw: object, where: str) -> dict[str, str]:
    mapping = _require_mapping(raw, where)
    files: dict[str, str] = {}
    for path, source in mapping.items():
        files[_require_relative_path(path, f"{where} path")] = _require_text(source, f"{where}[{path!r}]")
    if not files:
        raise ItemSetError(f"{where} is empty - a case needs a program to run")
    return files


def _parse_hidden_test(raw: object, where: str, files: Mapping[str, str]) -> HiddenTest:
    mapping = _require_mapping(raw, where)
    _require_keys(mapping, settings.load().case_keys.hidden_test, where)
    path = _require_relative_path(mapping["path"], f"{where}.path")
    content = _require_text(mapping["content"], f"{where}.content")
    if path in files:
        raise ItemSetError(f"{where}.path {path!r} collides with a program file of the case")
    return HiddenTest(path=path, content=content)


def _parse_asks(raw: object, where: str, families: Sequence[str]) -> dict[str, Ask]:
    mapping = _require_mapping(raw, where)
    asks: dict[str, Ask] = {}
    for family, value in mapping.items():
        if family not in settings.load().families.known:
            raise ItemSetError(f"{where} carries an unknown family {family!r}")
        ask_mapping = _require_mapping(value, f"{where}[{family!r}]")
        _require_keys(ask_mapping, settings.load().case_keys.ask, f"{where}[{family!r}]")
        asks[family] = Ask(
            system=_require_text(ask_mapping["system"], f"{where}[{family!r}].system"),
            user=_require_text(ask_mapping["user"], f"{where}[{family!r}].user"),
        )
    absent = [family for family in families if family not in asks]
    if absent:
        raise ItemSetError(f"{where} has no ask for {', '.join(sorted(absent))}")
    return asks


def _parse_families(raw: object, where: str) -> list[str]:
    if not isinstance(raw, list) or not raw:
        raise ItemSetError(f"{where} must be a non-empty list")
    families: list[str] = []
    for family in raw:
        name = _require_text(family, f"{where} entry")
        if name not in settings.load().families.known:
            raise ItemSetError(f"{where} names an unknown family {name!r}")
        if name in families:
            raise ItemSetError(f"{where} names {name!r} twice")
        families.append(name)
    return families


def _parse_case(raw: object, index: int) -> Case:
    where = f"cases[{index}]"
    mapping = _require_mapping(raw, where)
    _require_keys(mapping, settings.load().case_keys.case, where)
    families = _parse_families(mapping["families"], f"{where}.families")

    files = _parse_files(mapping["files"], f"{where}.files")
    fixed_files = _parse_files(mapping["fixed_files"], f"{where}.fixed_files")
    for path in fixed_files:
        if path not in files:
            raise ItemSetError(f"{where}.fixed_files patches {path!r}, which the case does not carry")

    bug = _parse_bug(mapping["bug"], f"{where}.bug")
    if bug.file not in files:
        raise ItemSetError(f"{where}.bug.file {bug.file!r} is not one of the case's files")

    return Case(
        id=_require_text(mapping["id"], f"{where}.id"),
        families=tuple(families),
        bug=bug,
        files=files,
        fixed_files=fixed_files,
        hidden_test=_parse_hidden_test(mapping["hidden_test"], f"{where}.hidden_test", files),
        asks=_parse_asks(mapping["asks"], f"{where}.asks", families),
    )


def load_item_set(path: Path, envelope: Envelope | None = None) -> ItemSet:
    """Load, validate and hash the item set at ``path``.

    Raises:
        ItemSetError: anything is malformed - a half-loaded set is never returned.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ItemSetError(f"cannot read the item set at {path}: {exc}") from exc
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ItemSetError(f"the item set at {path} is not valid JSON: {exc}") from exc

    mapping = _require_mapping(document, f"item set {path}")
    cases_raw = mapping.get("cases")
    if not isinstance(cases_raw, list) or not cases_raw:
        raise ItemSetError(f"the item set at {path} carries no cases")

    cases = tuple(_parse_case(raw_case, index) for index, raw_case in enumerate(cases_raw))
    identifiers = [case.id for case in cases]
    if len(set(identifiers)) != len(identifiers):
        raise ItemSetError(f"the item set at {path} carries a case id twice")

    prompts = [ask.system for case in cases for ask in case.asks.values()]
    return ItemSet(
        version=_require_text(mapping.get("version"), f"item set {path}.version"),
        cases=cases,
        cases_sha=cases_sha(raw, cases),
        envelope_sha=envelope_sha(envelope or Envelope(), prompts),
        families=tuple(sorted({family for case in cases for family in case.families})),
    )
