#!/usr/bin/env python3
"""Run an advisory second-opinion review through the provider the ladder selects.

The provider is chosen by *model priors* (ADR 0024): one walk over the ladder skips the
session's own carrier and every provider that answers with priors or a model already taken, so a
second opinion comes from a different mind or is disclosed as the weaker run it is. This runner
is intentionally explicit: it is called at a verify/align gate, writes the full external review
to the chosen provider's report directory, and prints a short digest. ``--list`` proposes the
ranked candidates without running anything. It is not wired as a blocking hook; owner
verification remains the decision point.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# The tree root, so the shared ``common`` package resolves: it holds the single owner of
# project-root discovery (C73) and is reachable at the same tree-relative depth from the
# mounted tree and from the materialized ``<AITNA_ROOT>/.akmon/`` copy alike.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import routing

from common import jsondata
from common.project_root import resolve_project_root
from common.record import records_package_mode
from common.report_path import create_report, next_report_path, report_prefix, safe_name, task_error


def _so_data() -> dict:
    """The second-opinion runner texts (``second_opinion.json``), read on the call that needs it."""
    return jsondata.read(Path(__file__).parent / "second_opinion.json")


def _gate_data() -> dict:
    """The shared gate-pack texts (``gate.json``), read on the call that needs it."""
    return jsondata.read(Path(__file__).parent / "gate.json")


def _standard_tree_root(project_root: Path) -> Path:
    """The tree ``registry.json`` is read from: the mount for mounted modes, this script's own tree otherwise.

    The rule of ``bin/sync.py::standard_tree_root`` and ``init.py::_standard_tree_root``: in package
    mode there is no ``<AITNA_ROOT>/akmon`` to read, and the recorded ``mount`` field decides, so
    a stale mount directory from a prior mode does not shadow the installed tree.
    """
    mounted = project_root / routing.aitna_root_name() / "akmon"
    if not records_package_mode(project_root) and mounted.is_dir():
        return mounted
    return Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _prompt(gate: str, prompt_text: str) -> str:
    return jsondata.fill(_so_data()["prompt"], {"gate": gate, "material": prompt_text})


def _unavailable_notice(gate: str, rank: int, reason: str) -> str:
    """The skip, stated as a fact plus the one option that is left and what it costs.

    The gate is skipped rather than downgraded to a same-model reviewer: shared weights
    reproduce the author's systematic errors and return a confident agreement, which reads
    exactly like a review and is filed like one. That refusal is the machine's; the weaker
    check is still worth running sometimes, so it is offered here — to a person, with its
    boundary attached — instead of being taken automatically and labelled as diversity.
    """
    lines = _so_data()["unavailable_notice"]
    return "\n".join(
        [
            jsondata.fill(lines[0], {"gate": gate, "rank": rank}),
            jsondata.fill(lines[1], {"reason": reason}),
            lines[2],
            lines[3],
            lines[4],
        ]
    )


def _report_prefix(gate: str, task: str | None) -> str:
    """``[<task>-]<gate>``: the review's name before its ``-<n>.md`` ordinal (C114)."""
    return report_prefix(safe_name(gate) or "gate", task)


def _report_dir_error(root: Path, report_dir: Path, configured: str) -> str | None:
    """The error line for a ``report_dir`` that resolves outside ``root``, else ``None``.

    Reports stay inside the project (C9): the check resolves symlinks and ``..`` first, so an
    absolute path, a ``../outside`` and a link inside the project pointing out are all refused,
    and it runs before the provider is started or any file is written.
    """
    if report_dir.resolve().is_relative_to(root.resolve()):
        return None
    return jsondata.fill(_so_data()["report_dir_outside"], {"report_dir": configured})


def _configured_report_dir(row: Mapping[str, object], provider: str) -> str:
    """The row's ``report_dir`` as written, or the shipped ``.<provider>/second-opinion/`` when it states none (D12)."""
    if "report_dir" in row:
        return str(row["report_dir"])
    return jsondata.fill(_so_data()["default_report_dir"], {"provider": provider})


def _decoded(data: bytes) -> str:
    r"""A provider pipe as text: UTF-8 with an undecodable byte as U+FFFD, universal newlines.

    A provider's bytes are its own; a byte that is not UTF-8 must not cost the review its report
    (C120). ``\r\n`` and a lone ``\r`` arrive as ``\n``, as a text-mode pipe reads them (C115).
    """
    return data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def _digest(text: str, limit: int = 1200) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[:limit].rstrip() + _gate_data()["truncation_suffix_report"]


def _model_text(model: str | None) -> str:
    """A model as the report prints it: the id, or ``(default)`` for the carrier's own."""
    return model or "(default)"


def _shown_model(
    registry: dict, stored: Mapping[str, routing.ProviderAliases], target: routing.SecondOpinionTarget
) -> str:
    """The model as the header prints it: ``alias→concrete``, or ``alias→(unresolved)`` without a mapping (D16)."""
    texts = _so_data()["model_shown"]
    suffix = "" if target.effort is None else f"@{target.effort}"
    if target.model is None or not routing.is_model_alias(registry, target.provider, target.model):
        return _model_text(target.model) + suffix
    try:
        concrete = routing.resolve_opinion_model(registry, stored, target.provider, target.model)
    except routing.UnresolvedAliasError:
        return jsondata.fill(texts["unresolved"], {"alias": target.model}) + suffix
    return jsondata.fill(texts["alias"], {"alias": target.model, "concrete": concrete}) + suffix


def _identity(
    registry: dict, stored: Mapping[str, routing.ProviderAliases], target: routing.SecondOpinionTarget, kind: str
) -> dict[str, object]:
    """The report-header fields of one run: provider, priors, carrier, repo, model and how it was chosen (D10)."""
    return {
        "provider": target.provider,
        "priors": target.family or "unknown",
        "carrier": routing.opinion_carrier(registry, target.provider),
        "repo": routing.opinion_repo(registry, target.provider),
        "model": _shown_model(registry, stored, target),
        "kind": kind,
    }


def _ledger_lines(registry: dict, session: routing.SecondOpinionSession, warnings: Sequence[str]) -> list[str]:
    """The lines that travel with every result: pinned-run warnings, the skip ledger and the asks (D08, D10)."""
    summary = _so_data()["summary"]
    lines = [jsondata.fill(summary["warning_line"], {"warning": warning}) for warning in warnings]
    lines += [
        jsondata.fill(summary["skip_line"], {"provider": provider, "reason": reason})
        for provider, reason in routing.opinion_skips(registry, session)
    ]
    lines += [jsondata.fill(summary["ask_line"], {"ask": ask}) for ask in routing.opinion_asks(registry, session)]
    return lines


def _default_mark(registry: dict, target: routing.SecondOpinionTarget, *, default_model: bool) -> str:
    """The listing's note that a candidate runs the carrier's own model (``:default`` or ``--default-model``)."""
    if default_model or routing.ladder_pins_default(registry, target.provider):
        return _so_data()["listing"]["default_pin"]
    return ""


def _alias_asks(
    registry: dict, stored: Mapping[str, routing.ProviderAliases], targets: Sequence[routing.SecondOpinionTarget]
) -> list[str]:
    """One ask per distinct alias among ``targets`` that has no concrete id yet, naming the refresh command (D16)."""
    asks: list[str] = []
    for target in targets:
        if target.model is None or not routing.is_model_alias(registry, target.provider, target.model):
            continue
        try:
            routing.resolve_opinion_model(registry, stored, target.provider, target.model)
        except routing.UnresolvedAliasError:
            ask = jsondata.fill(
                _so_data()["listing"]["alias_ask"], {"provider": target.provider, "model": target.model}
            )
            if ask not in asks:
                asks.append(ask)
    return asks


def _print_listing(
    registry: dict,
    stored: Mapping[str, routing.ProviderAliases],
    session: routing.SecondOpinionSession,
    *,
    default_model: bool,
) -> None:
    """``--list``: what a run would do — the ranked chain, the last resort or why none exists, the skips and the asks.

    The last resort is the one a run takes (``_last_resort``, rank 2), whether or not the session's
    own priors are known: a session of unknown priors still gets the disclosed same-provider run,
    beside the ask that would make the chain non-empty (ADR 0024/D07, D08). With ``--default-model``
    every candidate is shown unpinned, as the run would take it (D16).
    """
    texts = _so_data()["listing"]
    print(
        jsondata.fill(
            texts["session"],
            {"provider": session.provider, "model": _model_text(session.model), "priors": session.family or "unknown"},
        )
    )
    chain = [_unpinned(target, default_model=default_model) for target in routing.opinion_chain(registry, session)]
    shown = list(chain)
    for rank, target in enumerate(chain, start=routing.OPINION_RANK_SECOND):
        identity = _identity(registry, stored, target, "chain")
        print(
            jsondata.fill(texts["candidate"], {**identity, "rank": rank})
            + _default_mark(registry, target, default_model=default_model)
        )
    if not chain:
        print(texts["empty"])
        last, reason = _last_resort(registry, session, routing.OPINION_RANK_SECOND)
        if last is None:
            print(jsondata.fill(texts["no_last_resort"], {"reason": reason}))
        else:
            last = _unpinned(last, default_model=default_model)
            shown.append(last)
            line = jsondata.fill(texts["last_resort"], _identity(registry, stored, last, "last-resort"))
            print(line + _default_mark(registry, last, default_model=default_model))
    skips = routing.opinion_skips(registry, session)
    if skips:
        print(texts["skipped"])
        for provider, reason in skips:
            print(jsondata.fill(texts["skip"], {"provider": provider, "reason": reason}))
    asks = [*routing.opinion_asks(registry, session), *_alias_asks(registry, stored, shown)]
    if asks:
        print(texts["asks"])
        for ask in asks:
            print(jsondata.fill(texts["ask"], {"ask": ask}))


def _unpinned(target: routing.SecondOpinionTarget, *, default_model: bool) -> routing.SecondOpinionTarget:
    """``target`` as the run takes it: with ``--default-model`` the pin is dropped and the carrier's own model runs."""
    return dataclasses.replace(target, model=None) if default_model else target


def _pinned_choice(
    registry: dict, session: routing.SecondOpinionSession, choice: str
) -> tuple[routing.SecondOpinionTarget, list[str]]:
    """``--provider P[:model]``: the owner's explicit pick, with a warning for each way it fails to be diverse.

    It runs even when it is the session's own provider or answers with the session's priors — an
    owner may want exactly that — but it is disclosed ``kind=pinned`` and never counted as diverse.
    """
    provider, pinned = routing.split_opinion_entry(choice)
    routing.provider_row(registry, provider)
    model, effort = routing.opinion_pick(registry, provider, pinned)
    family = routing.provider_family(registry, provider, model)
    texts = _so_data()["pinned_warnings"]
    values = {"provider": provider, "priors": family or "unknown"}
    warnings = []
    if provider == session.provider:
        warnings.append(jsondata.fill(texts["own_provider"], values))
    elif family is None:
        warnings.append(jsondata.fill(texts["unknown_priors"], values))
    elif family == session.family:
        warnings.append(jsondata.fill(texts["same_priors"], values))
    return routing.SecondOpinionTarget(provider, model, family, effort), warnings


def _last_resort(
    registry: dict, session: routing.SecondOpinionSession, rank: int
) -> tuple[routing.SecondOpinionTarget | None, str]:
    """The last resort and its disclosure note, or ``(None, why nothing can be run)`` for the skip notice.

    The last resort (ADR 0024/D07) applies only to an empty chain at rank 2, and only on the
    session's own provider, which must have a row and be on ``PATH``: otherwise there is nothing
    to run and the notice says exactly that.
    """
    texts = _so_data()["unavailable_reasons"]
    count = len(routing.opinion_chain(registry, session))
    if count or rank != routing.OPINION_RANK_SECOND:
        return None, jsondata.fill(texts["rank_past_chain"], {"count": count, "rank": rank})
    if session.provider not in routing.providers(registry):
        return None, jsondata.fill(texts["no_row"], {"provider": session.provider})
    if not routing.carrier_present(registry, session.provider):
        return None, jsondata.fill(texts["carrier_absent"], {"provider": session.provider})
    note = jsondata.fill(_so_data()["last_resort_note"], {"session_model": _model_text(session.model)})
    return routing.opinion_last_resort(registry, session), note


def _build_parser() -> argparse.ArgumentParser:
    """The command line: the gate to review, who is asking, and which rank or provider to run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, help="Project root. Defaults to cwd or a parent with AGENTS.md.")
    parser.add_argument(
        "--provider",
        help="Run this provider, optionally pinned as P[:model], instead of the ladder's choice; "
        "it is disclosed as kind=pinned and never counted as diverse.",
    )
    parser.add_argument(
        "--rank",
        type=int,
        default=routing.OPINION_RANK_SECOND,
        help="Chain rank to run: 2 second opinion, 3 third, 4 arbiter.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the ranked candidate chain, the skip ledger and the asks, then exit without running.",
    )
    parser.add_argument(
        "--default-model",
        action="store_true",
        help="Run the selected provider on the carrier's own configured model: the pin is dropped for this run. "
        "Not with --provider P:model.",
    )
    parser.add_argument("--session-provider", help="The provider (harness) the working session runs on.")
    parser.add_argument("--session-model", help="The model the working session runs on.")
    parser.add_argument("--session-family", help="The priors (model family) of the working session, when not declared.")
    parser.add_argument(
        "--orchestrator-vendor",
        help="Deprecated alias of --session-provider: a vendor whose registry block names its `carrier`.",
    )
    parser.add_argument("--gate", help="Verify gate name, e.g. design-align or code-verify.")
    parser.add_argument("--gate-pack", type=Path, help="Path to a built gate-pack markdown file (see gate_pack.py).")
    parser.add_argument(
        "--task",
        help="Task id the review belongs to; the report is <report_dir>/[<task>-]<gate>-<n>.md, n the next ordinal.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the command and target report path without running it.",
    )
    return parser


def _session_provider(registry: dict, args: argparse.Namespace) -> str | None:
    """The provider the session names on the command line: ``--session-provider``, else the deprecated vendor alias.

    Raises ``ValueError`` for a vendor the registry gives no ``carrier``, so the owner is told to
    name the provider instead of the alias resolving to nothing.
    """
    if args.session_provider or not args.orchestrator_vendor:
        return args.session_provider
    block = registry.get(args.orchestrator_vendor)
    carrier = block.get("carrier") if isinstance(block, dict) else None
    if not carrier:
        raise ValueError(jsondata.fill(_so_data()["errors"]["unknown_vendor"], {"vendor": args.orchestrator_vendor}))
    return str(carrier)


def _write_report(report_dir: Path, prefix: str, header: Sequence[str], output: str) -> Path:
    """The report file: the header line and the ledger first, so the filed review carries its own provenance."""
    return create_report(report_dir, prefix, "\n".join(header) + "\n\n" + output + "\n")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: pick the provider by priors and run it against a gate pack, or list the candidates."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    errors = _so_data()["errors"]
    if (task_problem := task_error(args.task)) is not None:
        parser.error(task_problem)
    if args.rank < routing.OPINION_RANK_SECOND:
        parser.error(jsondata.fill(errors["bad_rank"], {"rank": args.rank}))
    if not args.list and not (args.gate and args.gate_pack):
        parser.error(errors["missing_gate"])

    root, root_notice = resolve_project_root(args.project_root)
    if root_notice:
        print(root_notice, file=sys.stderr)
    config = _read_json(root / routing.local_config_rel())
    try:
        registry = routing.load_registry(_standard_tree_root(root), root)
        routing.refuse_retired_keys(registry, config, project_root=root)
        stored = routing.read_model_aliases(root)
        session = routing.resolve_session(
            registry,
            config,
            provider=_session_provider(registry, args),
            model=args.session_model,
            family=args.session_family,
        )
        if args.list:
            _print_listing(registry, stored, session, default_model=args.default_model)
            return 0
        return _run(root, registry, stored, session, args)
    except routing.RetiredKeyError as exc:
        print(f"second-opinion: {exc}", file=sys.stderr)
        return 2
    except (ValueError, KeyError) as exc:
        print(f"second-opinion: {exc.args[0]}", file=sys.stderr)
        return 2


@dataclass(frozen=True)
class _Choice:
    """What a run will use: the target, how it was chosen (D10's ``kind``), and the warnings that travel with it."""

    target: routing.SecondOpinionTarget
    kind: str
    warnings: tuple[str, ...] = ()


def _choose(registry: dict, session: routing.SecondOpinionSession, args: argparse.Namespace) -> _Choice | str:
    """The run's choice — pinned, the chain's rank, or the disclosed last resort — else the reason nothing can run."""
    if args.provider:
        _, pinned = routing.split_opinion_entry(args.provider)
        if args.default_model and routing.split_model_effort(pinned)[0] not in (None, routing.default_model_token()):
            raise ValueError(jsondata.fill(_so_data()["errors"]["default_with_pin"], {"entry": args.provider}))
        target, warnings = _pinned_choice(registry, session, args.provider)
        choice = _Choice(target, "pinned", tuple(warnings))
    elif (target := routing.resolve_opinion_chain(registry, session, rank=args.rank)) is not None:
        choice = _Choice(target, "chain")
    else:
        target, text = _last_resort(registry, session, args.rank)
        if target is None:
            return text
        choice = _Choice(target, "last-resort", (text,))
    return dataclasses.replace(choice, target=_unpinned(choice.target, default_model=args.default_model))


def _run(
    root: Path,
    registry: dict,
    stored: Mapping[str, routing.ProviderAliases],
    session: routing.SecondOpinionSession,
    args: argparse.Namespace,
) -> int:
    """Choose the target, build its command, and print it (``--dry-run``) or run it and file the report.

    An alias is replaced by its concrete id before the command is built, and an alias with no id
    refuses the run, dry or not: the carrier is never sent a name it rejects (ADR 0024/D16).
    """
    choice = _choose(registry, session, args)
    if isinstance(choice, str):
        notice = _unavailable_notice(args.gate, args.rank, choice)
        print("\n".join([notice, *_ledger_lines(registry, session, [])]))
        return 0
    target = choice.target
    row = routing.provider_row(registry, target.provider)
    configured = _configured_report_dir(row, target.provider)
    report_dir = root / configured
    if (outside := _report_dir_error(root, report_dir, configured)) is not None:
        print(outside, file=sys.stderr)
        return 2
    # The resolved form, so the report line is always a path under the (resolved) root.
    report_dir = report_dir.resolve()
    prompt = _prompt(args.gate, args.gate_pack.read_text(encoding="utf-8"))
    model = routing.resolve_opinion_model(registry, stored, target.provider, target.model)
    command = routing.opinion_command(registry, target.provider, model=model, effort=target.effort, prompt=prompt)
    prefix = _report_prefix(args.gate, args.task)
    identity = _identity(registry, stored, target, choice.kind)
    summary = _so_data()["summary"]
    ledger = _ledger_lines(registry, session, choice.warnings)

    if args.dry_run:
        print(" ".join(command))
        print(jsondata.fill(summary["report_line"], {"path": next_report_path(report_dir, prefix).relative_to(root)}))
        print(jsondata.fill(summary["provider_line"], identity))
        for line in ledger:
            print(line)
        return 0

    # A prompt that travels as an argument leaves the carrier no use for stdin, and an inherited open
    # pipe can hold one forever (`opencode run` does): its stdin is the null device, which is EOF.
    feed = (
        {"input": prompt.encode("utf-8")}
        if str(row.get("prompt", "argv")) == "stdin"
        else {"stdin": subprocess.DEVNULL}
    )
    try:
        completed = subprocess.run(command, cwd=root, capture_output=True, check=False, **feed)
    except OSError as exc:
        print(jsondata.fill(_so_data()["errors"]["not_run"], {"command": command[0], "reason": exc}), file=sys.stderr)
        return 2
    output = _decoded(completed.stdout).strip()
    if stderr := _decoded(completed.stderr).strip():
        output = f"{output}\n\n[stderr]\n{stderr}".strip()
    result = jsondata.fill(summary["result_line"], {**identity, "gate": args.gate, "exit": completed.returncode})
    report = _write_report(report_dir, prefix, [result, *ledger], output)
    print(result)
    print(jsondata.fill(summary["report_line"], {"path": report.relative_to(root)}))
    for line in ledger:
        print(line)
    if output:
        print("")
        print(_digest(output))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
