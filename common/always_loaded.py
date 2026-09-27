"""The always-loaded ratchet's one counter — population, measurement, finding and report (C56).

ADR 0012 F18 fixes the contract: *always-loaded* is everything reaching the model before it
asks for anything, measured over two scopes that differ on purpose.

- **akmon-shipped** — the marked akmon block of ``AGENTS.md`` (from ``## Dev layer — akmon`` to
  the next peer ``##`` heading or EOF), the guardrail chain it ``@``-imports, resolved
  transitively, and the selected language guardrail;
- **consumer total** — the whole ``AGENTS.md`` plus that same chain and language guardrail.

Members are counted as a union (an imported selected file is never doubled) and summed with no
synthetic separator: lines are ``len(text.splitlines())``, bytes ``len(text.encode("utf-8"))``,
decimal and inclusive. Vendor pointers, hook wiring, roles, pipelines, skills and on-demand
documents are outside both scopes by construction: only the block's imports enter the chain.

:func:`over` and :func:`report` read the same :class:`Population`, so the numbers a reader sees
are the numbers the cap was checked against — never a stale constant.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from common import jsondata

CODE = "caps.always-loaded"


def _always_loaded_data() -> dict:
    """The block heading, scopes, caps and severities, as the data file carries them."""
    return jsondata.read(Path(__file__).parent / "always_loaded.json")


def block_heading() -> str:
    """The heading that marks the akmon block of a project's ``AGENTS.md``."""
    return _always_loaded_data()["block_heading"]

# An ``@``-import as the harness reads it: a token starting a line or following whitespace.
# Code spans, fenced blocks and HTML comments are stripped first — the harness does not import
# from them (a commented example import is documentation, not context).
_IMPORT_RE = re.compile(r"(?:^|(?<=\s))@([^\s`]+)", re.MULTILINE)
_FENCED_RE = re.compile(r"^(```|~~~).*?^\1[^\n]*$", re.MULTILINE | re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


@dataclass(frozen=True)
class Cap:
    """One scope's inclusive caps."""

    lines: int
    bytes: int


#: ADR 0012 F18 as re-baselined by its C56 amendment — today's shipped shape (311 lines /
#: 20,190 bytes) rounded up, plus the unchanged hand-owned allowance of 250 lines / 13,000
#: bytes for the consumer scope. The numbers are the ratchet; lowering them is C60's work.
#: They live in ``common/always_loaded.json`` (the shared owner both implementations read).
def shipped() -> str:
    """The akmon-shipped scope name."""
    return _always_loaded_data()["scopes"][0]


def consumer() -> str:
    """The consumer-total scope name."""
    return _always_loaded_data()["scopes"][1]


def caps() -> dict[str, Cap]:
    """One scope's inclusive caps, for every scope."""
    data = _always_loaded_data()
    return {
        scope: Cap(lines=data["caps"][scope]["lines"], bytes=data["caps"][scope]["bytes"]) for scope in data["scopes"]
    }


def severity() -> dict[str, str]:
    """The severity an over-cap finding carries, per scope."""
    return dict(_always_loaded_data()["severity"])


@dataclass(frozen=True)
class Member:
    """One counted text: a file, or the marked block, by the name the report uses."""

    name: str
    text: str

    @property
    def lines(self) -> int:
        """``len(text.splitlines())``."""
        return len(self.text.splitlines())

    @property
    def size(self) -> int:
        """Decimal bytes, UTF-8."""
        return len(self.text.encode("utf-8"))


@dataclass(frozen=True)
class Population:
    """The members of one scope and their summed measurements."""

    scope: str
    members: tuple[Member, ...]

    @property
    def lines(self) -> int:
        """Summed member lines, no synthetic separator."""
        return sum(member.lines for member in self.members)

    @property
    def size(self) -> int:
        """Summed member bytes, no synthetic separator."""
        return sum(member.size for member in self.members)


def marked_block(agents_text: str) -> str | None:
    """The akmon block of ``AGENTS.md``: its heading line up to the next peer ``##`` or EOF."""
    heading = block_heading()
    lines = agents_text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if line.startswith(heading)), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "".join(lines[start:end])


def _imports(text: str) -> list[str]:
    visible = _COMMENT_RE.sub(" ", _INLINE_CODE_RE.sub(" ", _FENCED_RE.sub("\n", text)))
    return _IMPORT_RE.findall(visible)


def import_chain(text: str, base: Path, *, root: Path) -> list[Path]:
    """Files ``text`` ``@``-imports, transitively and in first-seen order; missing targets skipped.

    A relative import resolves against the importing file's directory (``base`` for the first
    level). Resolution never leaves ``root``: the population is the project's context, and an
    import pointing outside it is not ours to count.
    """
    seen: list[Path] = []
    pending = [(target, base) for target in _imports(text)]
    while pending:
        target, directory = pending.pop(0)
        path = Path(target).expanduser()
        path = (path if path.is_absolute() else directory / path).resolve()
        if path in seen or not path.is_file() or not path.is_relative_to(root.resolve()):
            continue
        seen.append(path)
        pending.extend((nested, path.parent) for nested in _imports(path.read_text(encoding="utf-8")))
    return seen


def _union(root: Path, head: Member, chain: list[Path], selected: list[Path]) -> tuple[Member, ...]:
    members, seen = [head], set()
    for path in [*chain, *selected]:
        resolved = path.resolve()
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        members.append(Member(str(resolved.relative_to(root.resolve())), resolved.read_text(encoding="utf-8")))
    return tuple(members)


def populations(agents_text: str, root: Path, selected: Sequence[Path] = ()) -> dict[str, Population] | None:
    """Both scopes for one project; None when ``AGENTS.md`` carries no marked akmon block."""
    block = marked_block(agents_text)
    if block is None:
        return None
    chain = import_chain(block, root, root=root)
    shipped_scope, consumer_scope = shipped(), consumer()
    return {
        shipped_scope: Population(
            shipped_scope, _union(root, Member("AGENTS.md (akmon block)", block), chain, list(selected))
        ),
        consumer_scope: Population(
            consumer_scope, _union(root, Member("AGENTS.md", agents_text), chain, list(selected))
        ),
    }


def report(population: Population, cap: Cap) -> str:
    """The dynamic report — scope, then actual over cap for both dimensions.

    The finding that carries it names the code, so the message does not repeat it.
    """
    return f"{population.scope}: lines={population.lines}/{cap.lines} bytes={population.size}/{cap.bytes}"


def over(population: Population, cap: Cap) -> bool:
    """Whether either inclusive dimension is exceeded."""
    return population.lines > cap.lines or population.size > cap.bytes
