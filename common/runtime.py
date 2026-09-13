#!/usr/bin/env python3
"""What akmon needs on a host, and the one owner of every optional-harness command (C57, §7).

Two things live here because both are *declarations* a consumer's tooling reads, not checks:

**The runtime contract.** Akmon requires a POSIX shell and ``python3`` on PATH. The Codex route
additionally requires ``git``, because the generated Codex wiring resolves the project root
through ``$(git rev-parse --show-toplevel)`` while the Claude wiring uses the harness-provided
``$CLAUDE_PROJECT_DIR``. ``claude`` and ``codex`` are optional: akmon never requires a harness to
be installed. **Windows is unsupported**, not merely untested — a scope declaration, deliberately
not a machine-checked rule, so its lack of a seeded violation reads as a property rather than a
gap.

Each entry names its **population**, and the two populations are joined to different sources:
generated wiring is derived from the command strings ``sync`` emits, own tooling from
:data:`HARNESS_COMMANDS` below. Neither join scans the source tree for binaries, which is why a
tool akmon runs during development — ``uv``, ``pytest`` — is not silently promoted into a
consumer-facing requirement. The declaration's coverage of binaries invoked outside both joins is
an open question tracked separately (A20).

**The harness-command map.** One declarative owner for the executable name *and* every operation
akmon invokes on an optional harness: the version query ``sync`` uses to pick a generated
inventory (C46), the non-interactive review invocation the second-opinion tool runs, and later
the Codex app-server route (C70). The registry keeps second-opinion *policy* — which model flag,
which report directory — and refers to this map by harness name rather than naming a binary.

The ownership is exact, and narrower than "one place builds the command": this map owns the
**executable and the operation prefix**, and nothing else may spell either. A caller may append
its own *policy tail* — ``routing.second_opinion_command`` adds the registry's ``model_flag`` and
the prompt — because a model pin and a prompt are policy the registry owns, not facts about how
a vendor's CLI is invoked. What the map forbids is a second answer to "what is this harness
called" or "how is this operation spelled".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

#: The two populations. A runtime belongs to exactly one.
GENERATED_WIRING = "generated-wiring"
OWN_TOOLING = "akmon-own-tooling"

#: The shell that runs every generated command string. It has no executable name of its own:
#: the wiring is delivered *as a command line*, so the carrier is implied by that shape.
POSIX_SHELL = "POSIX shell"

#: Modalities. ``required-on:<route>`` names the vendor route that needs the runtime.
REQUIRED = "required"
OPTIONAL = "optional"
REQUIRED_ON = "required-on:"


@dataclass(frozen=True)
class RuntimeDeclaration:
    binary: str
    population: str
    modality: str


DECLARED_RUNTIMES: tuple[RuntimeDeclaration, ...] = (
    RuntimeDeclaration(POSIX_SHELL, GENERATED_WIRING, REQUIRED),
    RuntimeDeclaration("python3", GENERATED_WIRING, REQUIRED),
    RuntimeDeclaration("git", GENERATED_WIRING, REQUIRED_ON + "codex"),
    RuntimeDeclaration("claude", OWN_TOOLING, OPTIONAL),
    RuntimeDeclaration("codex", OWN_TOOLING, OPTIONAL),
)


@dataclass(frozen=True)
class HarnessCommands:
    """One optional harness: its executable name and the argv tail of each operation."""

    binary: str
    operations: Mapping[str, tuple[str, ...]]


#: The sole owner of every optional-harness executable name and operation prefix — not of the
#: whole argv. Adding an operation here is how a new caller reaches a harness; spelling an
#: executable or an operation anywhere else is a second owner and is rejected by the C57 checker.
#: A caller appending its own policy tail is not: ``routing.second_opinion_command`` adds the
#: registry's ``model_flag`` and the prompt after this prefix.
HARNESS_COMMANDS: Mapping[str, HarnessCommands] = {
    "claude": HarnessCommands(
        binary="claude",
        operations={
            "version": ("--version",),
            # Non-interactive review: prompt in, plain text out.
            "review": ("-p", "--output-format", "text"),
        },
    ),
    "codex": HarnessCommands(
        binary="codex",
        operations={
            "version": ("--version",),
            "review": ("exec",),
            # C70: the app-server listens on stdio by default; the caller then speaks bounded
            # JSON-RPC ``hooks/list`` over that pipe (common/codex_hooks.py), not a second argv.
            "hooks-list": ("app-server",),
        },
    ),
}


def harness_binaries() -> tuple[str, ...]:
    """Every optional-harness executable name akmon knows how to invoke."""
    return tuple(sorted(spec.binary for spec in HARNESS_COMMANDS.values()))


def harness_command(harness: str, operation: str, *extra: str) -> list:
    """The argv for ``operation`` on ``harness``, plus any caller-supplied tail.

    The single constructor of the *executable-plus-operation prefix*, not of the whole argv: a
    caller may pass a policy tail through ``extra``. A caller that needs a different operation
    adds it to :data:`HARNESS_COMMANDS` rather than assembling a prefix of its own — that
    indirection is the accepted cost of having one place to look when a harness changes its
    interface.
    """
    try:
        spec = HARNESS_COMMANDS[harness]
    except KeyError:
        raise ValueError(f"unknown harness {harness!r}; known: {', '.join(sorted(HARNESS_COMMANDS))}") from None
    try:
        tail = spec.operations[operation]
    except KeyError:
        raise ValueError(
            f"harness {harness!r} declares no operation {operation!r}; known: {', '.join(sorted(spec.operations))}"
        ) from None
    return [spec.binary, *tail, *extra]


def version_command(harness: str) -> list:
    """The harness-version query. ``sync`` reads it to pick a generated inventory (C46)."""
    return harness_command(harness, "version")


def codex_hooks_list_command() -> list:
    """The bounded ``codex app-server`` invocation C70 speaks ``hooks/list`` JSON-RPC over.

    The sole spelling of the Codex binary name for this route (§7): a caller reaches it through
    this function rather than writing ``"codex"`` itself, so the executable name has exactly one
    owner even for the one route that talks a persistent-process protocol instead of a one-shot
    argv.
    """
    return harness_command("codex", "hooks-list")
