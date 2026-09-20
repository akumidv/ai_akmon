"""Join guardrail policy prose to the hook callables that implement it (C53).

Two sides, one stable dotted policy ID between them (owner choice F7/B, ADR 0012):

- live guardrail prose carries ``Runtime check: <policy-id> — <subset prose>``, where the ID is
  the **first token** and everything after it is human prose this parser ignores (F8/4);
- every public ``hook_core.*_result`` docstring carries exactly one of ``Policy ID: <policy-id>``
  or ``Runtime classification: operational`` with a non-empty ``Rationale:``.

Each ID occurs exactly once on each side, so a rule cannot be claimed twice and a claim cannot
outlive the callable that backs it. Nothing sits between the two sides — no registry, no mapping
constant, no decorator: the join is re-derived from prose and source on every run, and a rename
that keeps the ID keeps the join. The hooks are **parsed, never imported**; importing them to read
metadata would run module-level hook code inside the checker.

ADR-0012/D07 supplies the population rule and one obligation beyond the join. The join runs over
the *current* public ``hook_core.*_result`` set rather than a snapshot, and a public callable that
reaches the owner from outside that set states its classification explicitly and carries no policy
ID — silence is not a valid state for it. Which callables those are is derived here from what they
do rather than from a list kept by hand: the callable **writes to a stream itself**, or an
**adapter renders its return value** into a vendor channel. The adapter modules are that rendering
seam, not members of the population. A text builder reached only through an already-classified
``*_result`` stays outside it; classifying those would let one policy ID be claimed from two
places and break the one-to-one join.

Policy IDs and the finding codes in ``common/findings.py`` share a shape and are **separate
namespaces** (F8/5). The slug pattern is therefore defined here rather than imported, so neither
namespace can quietly start validating the other.
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from common.findings import Finding

#: The marker line. The ID is the first token; the rest of the line — and the rest of its
#: paragraph — is the subset prose, read only so a reader can see what the marker claims.
_MARKER = re.compile(r"^Runtime check:\s*(?P<id>\S+)(?P<tail>.*)$")
#: The enforcement claims F7/B replaced. Live in guardrail prose they assert a join with no ID to
#: verify it by, which is the stage-1 defect this check exists to remove.
_LEGACY_CLAIM = re.compile(r"\*\*Enforced\*\*|\bEnforced by\b")
#: A policy ID: at least two lowercase dotted segments. Deliberately a second definition of the
#: shape ``common.findings.CODE_RE`` also describes — see this module's docstring on F8/5.
_POLICY_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[a-z0-9]+(?:-[a-z0-9]+)*)+$")

_DOCSTRING_FIELDS = {
    "policy_id": re.compile(r"^Policy ID:\s*(?P<value>.*)$"),
    "classification": re.compile(r"^Runtime classification:\s*(?P<value>.*)$"),
    "rationale": re.compile(r"^Rationale:\s*(?P<value>.*)$"),
}
#: The only classification value F7 defines beside a policy ID.
_OPERATIONAL = "operational"
#: The adapters are the vendor channel itself: what they render is owner-visible, they are the
#: seam that renders it. A callable defined here is machinery, never a member of the population.
_ADAPTER_MODULES = ("claude_adapter.py", "codex_adapter.py")
#: The join's scope (ADR-0012/D07): public ``*_result`` callables of this module, whatever the
#: current set holds. Adding or removing one is conformance in the owning task.
_JOIN_MODULE = "hook_core.py"
_JOIN_SUFFIX = "_result"

_ABSENT = "absent"


@dataclass(frozen=True)
class ProseMarker:
    """One ``Runtime check:`` marker: the join key, what it claims, and where it is written."""

    policy_id: str
    tail: str
    location: str


@dataclass(frozen=True)
class CallableClassification:
    """One public hook callable and the classification its own docstring declares."""

    name: str
    location: str
    policy_id: str
    classification: str
    rationale: str
    in_join_scope: bool
    owner_visible: bool


def _location(root: Path, path: Path, line: int) -> str:
    return f"{path.relative_to(root).as_posix()}:{line}"


def _paragraph_tail(lines: list[str], index: int) -> str:
    """The marker's remaining prose: its paragraph, up to the first blank line."""
    tail: list[str] = []
    for line in lines[index + 1 :]:
        if not line.strip():
            break
        tail.append(line.strip())
    return " ".join(tail)


def _read_prose(root: Path) -> tuple[list[ProseMarker], list[Finding]]:
    """Every marker in live guardrail prose, plus a finding for each legacy enforcement claim."""
    markers: list[ProseMarker] = []
    findings: list[Finding] = []
    for path in sorted((root / "guardrails").glob("**/*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, start=1):
            location = _location(root, path, number)
            if marker := _MARKER.match(line.strip()):
                tail = f"{marker.group('tail').strip()} {_paragraph_tail(lines, number - 1)}"
                markers.append(ProseMarker(marker.group("id"), tail.strip(), location))
            elif _LEGACY_CLAIM.search(line):
                findings.append(
                    Finding(
                        "error",
                        "canary.legacy-marker",
                        f"live guardrail prose still claims enforcement without a policy ID: {line.strip()[:80]}",
                        location,
                        "Replace the claim with a `Runtime check: <policy-id>` marker naming the subset it covers.",
                    )
                )
    return markers, findings


def _is_field_line(line: str) -> bool:
    return any(pattern.match(line.strip()) for pattern in _DOCSTRING_FIELDS.values())


def _field_value(lines: list[str], index: int, head: str) -> str:
    """A field's value: the rest of its own line, continued to the next blank line or field.

    The fields are written one under another with no blank line between them, so a value that
    stopped only at a paragraph break would read the next field's whole text as part of its own.
    """
    value = [head.strip()]
    for line in lines[index + 1 :]:
        if not line.strip() or _is_field_line(line):
            break
        value.append(line.strip())
    return " ".join(part for part in value if part).strip()


def _docstring_fields(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, str]:
    """The classification fields a docstring declares, each read from the callable's own text."""
    doc = ast.get_docstring(node, clean=True) or ""
    lines = doc.splitlines()
    fields: dict[str, str] = {}
    for index, line in enumerate(lines):
        for name, pattern in _DOCSTRING_FIELDS.items():
            if (match := pattern.match(line.strip())) and name not in fields:
                fields[name] = _field_value(lines, index, match.group("value"))
    return fields


def _writes_to_stream(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Whether the callable writes to a stream itself — the first arm of D07's predicate."""
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue
        if isinstance(inner.func, ast.Name) and inner.func.id == "print":
            return True
        if isinstance(inner.func, ast.Attribute) and inner.func.attr == "write":
            return True
    return False


def _adapter_referenced_names(root: Path) -> frozenset[str]:
    """Every name an adapter module references — the second arm: an adapter renders its return."""
    names: set[str] = set()
    for module in _ADAPTER_MODULES:
        path = root / "hooks" / module
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names.update(node.id for node in ast.walk(tree) if isinstance(node, ast.Name))
    return frozenset(names)


def _public_functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")
    ]


def _collect_callables(root: Path) -> list[CallableClassification]:
    """Every public hook callable, with its declared classification and its population membership."""
    rendered = _adapter_referenced_names(root)
    collected: list[CallableClassification] = []
    for path in sorted((root / "hooks").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in _public_functions(tree):
            fields = _docstring_fields(node)
            in_join = path.name == _JOIN_MODULE and node.name.endswith(_JOIN_SUFFIX)
            owner_visible = (
                not in_join
                and path.name not in _ADAPTER_MODULES
                and (_writes_to_stream(node) or node.name in rendered)
            )
            collected.append(
                CallableClassification(
                    name=node.name,
                    location=_location(root, path, node.lineno),
                    policy_id=fields.get("policy_id", ""),
                    classification=fields.get("classification", ""),
                    rationale=fields.get("rationale", ""),
                    in_join_scope=in_join,
                    owner_visible=owner_visible,
                )
            )
    return collected


def _coordinates(policy_id: str, callable_location: str, prose_location: str) -> str:
    """Both sides of the relation and its key, naming explicitly whichever side is absent."""
    return (
        f"policy ID {policy_id or _ABSENT} · callable {callable_location or _ABSENT} "
        f"· prose {prose_location or _ABSENT}"
    )


def _malformed_id_finding(policy_id: str, location: str, side: str) -> Finding:
    return Finding(
        "error",
        "canary.malformed-id",
        f"{side} declares {policy_id!r}, which is not a dotted policy ID — {_coordinates(policy_id, location, '')}",
        location,
        "Spell the policy ID as two or more lowercase dotted segments, such as `commits.owner-owned`.",
    )


def _duplicate_findings(claims: dict[str, list[str]], code: str, side: str, fix: str) -> list[Finding]:
    """One ID claimed from two places on the same side breaks the one-to-one join."""
    return [
        Finding(
            "error",
            code,
            f"policy ID {policy_id} is claimed by {len(locations)} {side} — {', '.join(locations)}",
            ", ".join(locations),
            fix,
        )
        for policy_id, locations in sorted(claims.items())
        if len(locations) > 1
    ]


def _prose_findings(markers: list[ProseMarker]) -> list[Finding]:
    """Malformed and duplicated IDs on the prose side."""
    findings = [
        _malformed_id_finding(marker.policy_id, marker.location, "a guardrail marker")
        for marker in markers
        if not _POLICY_ID.match(marker.policy_id)
    ]
    claims: dict[str, list[str]] = defaultdict(list)
    for marker in markers:
        claims[marker.policy_id].append(marker.location)
    findings.extend(
        _duplicate_findings(
            claims,
            "canary.duplicate-id",
            "guardrail markers",
            "Give each runtime-checked subset its own policy ID, or keep one marker for the rule.",
        )
    )
    return findings


def _classification_findings(entry: CallableClassification) -> list[Finding]:
    """What one callable's own docstring must declare, independent of the other side."""
    coordinates = _coordinates(entry.policy_id, entry.location, "")
    if entry.policy_id and entry.classification:
        return [
            Finding(
                "error",
                "canary.dual-classification",
                f"{entry.name} declares both a policy ID and a runtime classification — {coordinates}",
                entry.location,
                "Keep exactly one of `Policy ID:` or `Runtime classification: operational` on the callable.",
            )
        ]
    if not entry.policy_id and not entry.classification:
        return [
            Finding(
                "error",
                "canary.unclassified",
                f"public result {entry.name} declares no classification — {coordinates}",
                entry.location,
                "Declare either `Policy ID: <id>` or `Runtime classification: operational` with a rationale.",
            )
        ]
    if entry.policy_id and not _POLICY_ID.match(entry.policy_id):
        return [_malformed_id_finding(entry.policy_id, entry.location, f"{entry.name}")]
    return _operational_findings(entry)


def _operational_findings(entry: CallableClassification) -> list[Finding]:
    """An operational classification carries the one value F7 defines, and a real rationale."""
    if not entry.classification:
        return []
    coordinates = _coordinates(entry.policy_id, entry.location, "")
    if entry.classification != _OPERATIONAL:
        return [
            Finding(
                "error",
                "canary.malformed-classification",
                f"{entry.name} declares runtime classification {entry.classification!r} — {coordinates}",
                entry.location,
                f"Use `Runtime classification: {_OPERATIONAL}`, the one value defined beside a policy ID.",
            )
        ]
    if not entry.rationale:
        return [
            Finding(
                "error",
                "canary.empty-rationale",
                f"{entry.name} is operational with no rationale — {coordinates}",
                entry.location,
                "State why the callable carries no guardrail policy, so operational cannot become a silent exemption.",
            )
        ]
    return []


def _join_findings(markers: list[ProseMarker], callables: list[CallableClassification]) -> list[Finding]:
    """The join itself: every ID on one side must meet its counterpart on the other."""
    prose_by_id = {marker.policy_id: marker.location for marker in markers}
    callable_by_id = {entry.policy_id: entry for entry in callables if entry.policy_id}
    findings: list[Finding] = []
    for policy_id, location in sorted(prose_by_id.items()):
        if policy_id not in callable_by_id:
            findings.append(
                Finding(
                    "error",
                    "canary.prose-orphan",
                    f"guardrail prose claims a runtime check no callable implements — "
                    f"{_coordinates(policy_id, '', location)}",
                    location,
                    "Add the `Policy ID:` to the callable that implements it, or drop the marker from the prose.",
                )
            )
    for policy_id, entry in sorted(callable_by_id.items()):
        if policy_id not in prose_by_id:
            findings.append(
                Finding(
                    "error",
                    "canary.docstring-orphan",
                    f"{entry.name} claims a policy ID no guardrail prose declares — "
                    f"{_coordinates(policy_id, entry.location, '')}",
                    entry.location,
                    "Add the `Runtime check:` marker to the rule the callable enforces, or drop the policy ID.",
                )
            )
    return findings


def _population_findings(callables: list[CallableClassification]) -> list[Finding]:
    """ADR-0012/D07: outside the join, an owner-visible callable says what it is and claims no ID."""
    findings: list[Finding] = []
    for entry in callables:
        if entry.in_join_scope:
            continue
        if entry.policy_id:
            findings.append(
                Finding(
                    "error",
                    "canary.policy-id-outside-join",
                    f"{entry.name} claims policy ID {entry.policy_id} from outside the `*_result` join — "
                    f"{_coordinates(entry.policy_id, entry.location, '')}",
                    entry.location,
                    "Leave the policy ID with the one public hook_core result that owns it.",
                )
            )
        elif entry.owner_visible and not entry.classification:
            findings.append(
                Finding(
                    "error",
                    "canary.silent-callable",
                    f"{entry.name} reaches the owner from outside the join with no classification — "
                    f"{_coordinates('', entry.location, '')}",
                    entry.location,
                    "Declare `Runtime classification: operational` with a rationale; silence is not a valid state.",
                )
            )
        elif entry.owner_visible:
            findings.extend(_operational_findings(entry))
    return findings


def check_canary(root: Path) -> list[Finding]:
    """Return findings for every broken relation between guardrail prose and hook callables."""
    markers, findings = _read_prose(root)
    callables = _collect_callables(root)
    findings.extend(_prose_findings(markers))

    claims: dict[str, list[str]] = defaultdict(list)
    for entry in callables:
        if entry.policy_id:
            claims[entry.policy_id].append(entry.location)
        if entry.in_join_scope:
            findings.extend(_classification_findings(entry))
    findings.extend(
        _duplicate_findings(
            claims,
            "canary.duplicate-id",
            "callables",
            "Let one callable own the policy ID; a text builder behind it is classified by its caller.",
        )
    )
    findings.extend(_join_findings(markers, callables))
    findings.extend(_population_findings(callables))

    if not findings:
        joined = len([entry for entry in callables if entry.in_join_scope])
        outside = len([entry for entry in callables if entry.owner_visible])
        findings.append(
            Finding(
                "ok",
                "canary.join",
                f"{len(markers)} policy IDs join guardrail prose to {joined} public hook_core results "
                f"one-to-one, and {outside} owner-visible callables outside the join are classified",
                "guardrails, hooks",
                "Keep every runtime-checked rule joined to its callable by one policy ID on each side.",
            )
        )
    return findings
