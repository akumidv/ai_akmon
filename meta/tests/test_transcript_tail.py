"""A19: the transcript scanners read from the end and answer what the forward scan answered.

The forward scanners A19 replaced are kept below as the oracle, verbatim but for their names, and
the equivalence is carried in two layers. The tail reader yields the lines a forward text-mode read
yields, at block sizes small enough that every line, every multi-byte character and every
``\\r\\n`` straddles a block boundary; each scanner then gives the forward answer on every
transcript of a small exhaustive corpus. The one intended difference is pinned rather than
hidden: the forward scan raised on a line that is not UTF-8, losing every other line, and the tail
scan skips that line instead.

The remaining carriers pin what the owner chose (A19 option (a)): the read stays bounded on a large
transcript whose answer is near the end, a role declared early is still found (a record-count
bound would forget it), and the model-routing hook reads the transcript once per run, not twice.
"""

from __future__ import annotations

import importlib.util
import io
import itertools
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

import routing  # noqa: E402


def _forward_active_role(transcript_path):
    """``routing.active_role`` as it stood before A19."""
    if not transcript_path:
        return None
    path = Path(transcript_path)
    if not path.is_file():
        return None
    role = None
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if "agent:" not in line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict) or entry.get("type") != "assistant" or entry.get("isSidechain"):
                    continue
                match = routing._ROLE_DECL_RE.match(routing._assistant_text(entry))
                if match:
                    role = match.group(1).casefold()
    except OSError:
        return None
    return role


def _forward_last_main_turn(transcript_path):
    """``routing._last_main_turn`` as it stood before A19."""
    if not transcript_path:
        return None, None
    path = Path(transcript_path)
    if not path.is_file():
        return None, None
    model_id = None
    usage = None
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if '"model"' not in line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict) or entry.get("type") != "assistant" or entry.get("isSidechain"):
                    continue
                message = entry.get("message")
                model = message.get("model") if isinstance(message, dict) else None
                if isinstance(model, str) and model and not model.startswith("<"):
                    model_id = model
                    entry_usage = message.get("usage")
                    usage = entry_usage if isinstance(entry_usage, dict) else None
    except OSError:
        return None, None
    return model_id, usage


def _record(kind: str, message: dict, *, sidechain: bool = False, ascii_only: bool = True) -> bytes:
    entry = {"type": kind, "message": message}
    if sidechain:
        entry["isSidechain"] = True
    return json.dumps(entry, ensure_ascii=ascii_only).encode("utf-8")


# One line each, chosen so that every branch of both scanners is taken and each line matches at
# least one pre-filter. The raw-emoji line is multi-byte UTF-8, so a small block splits a character.
_LINES = {
    "main": _record(
        "assistant", {"model": "claude-opus-4-8", "usage": {"input_tokens": 7}, "content": "🧭 agent: review — a"}
    ),
    "main-raw": _record(
        "assistant", {"model": "claude-fable-5", "content": "🧭 agent: Engineer — b"}, ascii_only=False
    ),
    "side": _record("assistant", {"model": "claude-haiku-4-5", "content": "🧭 agent: learn"}, sidechain=True),
    "synthetic": _record("assistant", {"model": "<synthetic>", "content": "quoted `🧭 agent: architect`"}),
    "user": _record("user", {"content": '"model" agent: release'}),
    "torn": b'{"type": "assistant", "message": {"model": "claude-opus-4-8", "content": "\\ud83e\\udded agent: x',
    "empty": b"",
    "not-utf8": b'\xff{"type": "assistant", "message": {"model": "m", "content": "agent: x"}}',
}
_BREAKS = (b"\n", b"\r\n", b"\r")


def _transcripts():
    """Every sequence of up to two (line, break) pairs, plus every three-line run under ``\\n``.

    Each is taken with and without a break after its last line — a torn tail has none.
    """
    pairs = list(itertools.product(_LINES, _BREAKS))
    shapes = [shape for length in range(3) for shape in itertools.product(pairs, repeat=length)]
    shapes += [tuple((name, b"\n") for name in names) for names in itertools.product(_LINES, repeat=3)]
    for shape in shapes:
        body = b"".join(_LINES[name] + brk for name, brk in shape)
        yield body
        if shape:
            yield body[: -len(shape[-1][1])]


def _decodes(line: bytes) -> bool:
    try:
        line.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


@pytest.mark.parametrize("block", [1, 2, 3, 7])
def test_tail_reader_yields_the_lines_a_forward_text_read_yields(monkeypatch, block):
    """Empty lines are left out on both sides: the tail reader may yield one where a ``\\r\\n``
    straddles a block, and no pre-filter ever matches an empty line."""
    monkeypatch.setattr(routing, "_TAIL_BLOCK_BYTES", block)
    checked = 0
    for body in _transcripts():
        if not _decodes(body):
            continue
        forward = [line.rstrip("\n") for line in io.TextIOWrapper(io.BytesIO(body), encoding="utf-8")]
        tail = list(routing._lines_from_end(io.BytesIO(body), b""))[::-1]
        assert [line for line in tail if line] == [line for line in forward if line], body
        checked += 1
    assert checked > 1_000  # the corpus did not silently shrink


def _forward_or_skipped(scan, path: Path, body: bytes):
    """The forward answer; where the forward scan raised on a line that is not UTF-8, the forward
    answer for the same transcript with those lines removed — which is what the tail scan owes."""
    try:
        return scan(path)
    except UnicodeDecodeError:
        kept = b"\n".join(line for line in routing._LINE_BREAK.split(body) if _decodes(line))
        path.write_bytes(kept)
        try:
            return scan(path)
        finally:
            path.write_bytes(body)


def test_tail_scans_agree_with_the_forward_scans(tmp_path):
    path = tmp_path / "t.jsonl"
    checked = 0
    for body in _transcripts():
        path.write_bytes(body)
        assert routing.last_main_turn(path) == _forward_or_skipped(_forward_last_main_turn, path, body), body
        assert routing.active_role(path) == _forward_or_skipped(_forward_active_role, path, body), body
        checked += 1
    assert checked > 2_000  # the corpus did not silently shrink


def test_tail_scan_skips_a_line_that_is_not_utf8_where_the_forward_scan_raised(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_bytes(_LINES["main"] + b"\n" + _LINES["not-utf8"] + b"\n")
    with pytest.raises(UnicodeDecodeError):
        _forward_last_main_turn(path)
    assert routing.last_main_turn(path) == ("claude-opus-4-8", {"input_tokens": 7})
    assert routing.active_role(path) == "review"


class _CountingReader:
    """A binary file handle that counts the bytes read through it."""

    def __init__(self, handle, counter: list[int]):
        self._handle = handle
        self._counter = counter

    def read(self, size=-1):
        data = self._handle.read(size)
        self._counter.append(len(data))
        return data

    def seek(self, *args):
        return self._handle.seek(*args)

    def tell(self):
        return self._handle.tell()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._handle.close()


def _count_reads(monkeypatch) -> list[int]:
    counter: list[int] = []
    original = Path.open

    def counting_open(self, mode="r", *args, **kwargs):
        handle = original(self, mode, *args, **kwargs)
        return _CountingReader(handle, counter) if mode == "rb" else handle

    monkeypatch.setattr(Path, "open", counting_open)
    return counter


def _long_transcript(path: Path, *, head: bytes = b"", tail: bytes = b"") -> None:
    filler = _record("user", {"content": '"model" agent: nothing ' + "x" * 200})
    path.write_bytes(head + (filler + b"\n") * 20_000 + tail)


def test_tail_scan_reads_a_bounded_tail_whatever_the_transcript_size(tmp_path, monkeypatch):
    path = tmp_path / "t.jsonl"
    _long_transcript(path, tail=_LINES["main"] + b"\n")
    assert path.stat().st_size > 4_000_000
    counter = _count_reads(monkeypatch)
    assert routing.last_main_turn(path) == ("claude-opus-4-8", {"input_tokens": 7})
    assert sum(counter) <= 2 * routing._TAIL_BLOCK_BYTES
    counter.clear()
    assert routing.active_role(path) == "review"
    assert sum(counter) <= 2 * routing._TAIL_BLOCK_BYTES


def test_a_role_declared_at_the_start_of_a_long_transcript_is_still_found(tmp_path, monkeypatch):
    """Option (a) is the exact scan: no record-count bound, so an early declaration survives, at
    the cost of reading the whole file when nothing later qualifies."""
    path = tmp_path / "t.jsonl"
    _long_transcript(path, head=_LINES["main"] + b"\n")
    counter = _count_reads(monkeypatch)
    assert routing.active_role(path) == "review"
    assert sum(counter) == path.stat().st_size


def _load_hook():
    spec = importlib.util.spec_from_file_location("model_routing_hook", _AKMON / "hooks" / "model-routing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("event", ["SessionStart", "UserPromptSubmit"])
def test_the_model_routing_hook_reads_the_transcript_once_per_run(tmp_path, monkeypatch, event):
    root = tmp_path / "proj"
    routing_dir = root / "_aitna" / "akmon" / "tools" / "model_routing"
    routing_dir.mkdir(parents=True)
    (routing_dir / "registry.json").write_bytes((_ROUTING_DIR / "registry.json").read_bytes())
    (root / "AGENTS.md").write_text("x", encoding="utf-8")
    transcript = tmp_path / "t.jsonl"
    transcript.write_bytes(_LINES["main"] + b"\n")
    hook = _load_hook()
    reads = []
    original = routing.last_main_turn

    def counting(path):
        reads.append(path)
        return original(path)

    monkeypatch.setattr(routing, "last_main_turn", counting)
    hook.model_routing_result(root, {"hook_event_name": event, "transcript_path": str(transcript), "session_id": "s"})
    assert reads == [str(transcript)]
