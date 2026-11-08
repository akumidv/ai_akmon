"""Harness settings files whose ``env`` an agent never writes (ADR 0031/D07, D-C203-ACTOR-WRITE).

A harness settings file's ``env`` block reaches the hook process (M239), so an agent that could write it
could set the actor of the next session. The guard (policy ``privilege.no-escalation``, every actor) denies
that write on two routes, and this module is the one owner of what they both need:

- **the files** — ``.claude/settings*.json`` and ``.codex/config.toml``, matched on the last two segments of
  a path, so the project's file at any depth and the user's (``~/.claude/settings.json``) are one rule;
- **the edit route** (Claude's ``Edit``/``Write``/``MultiEdit``): :func:`edit_reason` computes the file's
  content after the edit and answers a reason when the parsed ``env`` of a JSON file differs from the
  current one — a Codex ``config.toml`` when any ``env`` or ``shell_environment_policy`` text changes; an
  edit that leaves ``env`` identical passes;
- **the shell route**: :func:`write_reason` is the text for a command the guard found writing one of the
  files (the command-word parsing lives in ``hooks/hook_core.py`` beside the commit guard's).

The file list, the shell programs that write their operands and the texts are
``common/harness_settings.json``'s, shared with the JavaScript twin ``js/common/harness_settings.mjs``.
Nothing here reads the environment or a file of its own accord: the entry point passes the current content.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from common import jsondata

# A settings file is named by its directory and its file name.
_PATH_SEGMENTS = 2
_TOML_HEADER = re.compile(r"^\[\[?\s*(.+?)\s*\]\]?\s*(?:#.*)?$")
_TOML_KEY = re.compile(r"""^([A-Za-z0-9_.\-"' ]+?)\s*=""")


def read_data() -> dict[str, Any]:
    """The harness-settings data file beside this module: the files, the shell programs, the texts."""
    return jsondata.read(Path(__file__).parent / "harness_settings.json")


def _glob(pattern: str) -> re.Pattern[str]:
    """The regular expression of a file-name pattern: ``*`` is any run of characters, the rest is literal."""
    return re.compile(".*".join(re.escape(part) for part in pattern.split("*")), re.DOTALL)


def file_format(path: str, data: Mapping[str, Any]) -> str | None:
    """``json`` or ``toml`` when ``path`` names a harness settings file, else ``None``.

    Only the last two segments count (``.claude/settings.local.json``): the directory a project sits in, or
    the home directory, does not.
    """
    parts = [part for part in path.split("/") if part not in ("", ".")]
    if len(parts) < _PATH_SEGMENTS:
        return None
    directory, name = parts[-2], parts[-1]
    for entry in data["files"]:
        if directory == entry["directory"] and _glob(entry["pattern"]).fullmatch(name):
            return entry["format"]
    return None


def write_reason(path: str, data: Mapping[str, Any]) -> str:
    """The reason for a shell command that writes the harness settings file ``path``."""
    return jsondata.fill(data["texts"]["bash"], {"path": path})


def _same(first: Any, second: Any) -> bool:
    """Whether two parsed JSON values are the same: by type (``true`` is not ``1``) and, for numbers, by value."""
    if isinstance(first, bool) or isinstance(second, bool):
        return isinstance(first, bool) and isinstance(second, bool) and first == second
    if isinstance(first, dict) and isinstance(second, dict):
        return first.keys() == second.keys() and all(_same(first[key], second[key]) for key in first)
    if isinstance(first, list) and isinstance(second, list):
        return len(first) == len(second) and all(_same(one, other) for one, other in zip(first, second, strict=True))
    if isinstance(first, (int, float)) and isinstance(second, (int, float)):
        return first == second
    return type(first) is type(second) and first == second


def json_env(text: str | None) -> Any:
    """The ``env`` of a JSON settings file's text; ``{}`` for no file, no ``env``, an empty one or no object.

    A file that does not parse delivers no ``env`` to anything, so it holds none.
    """
    if text is None:
        return {}
    try:
        document = json.loads(text)
    except ValueError:
        return {}
    env = document.get("env") if isinstance(document, dict) else None
    return env if env else {}


def _key_segments(key: str) -> list[str]:
    return [segment.strip().strip("\"'") for segment in key.split(".")]


def toml_env_lines(text: str | None, names: Sequence[str]) -> list[str]:
    """The lines of a Codex ``config.toml`` text that belong to an ``env`` or ``shell_environment_policy`` table.

    A table whose dotted name has a segment in ``names`` (``[env]``, ``[mcp_servers.x.env]``,
    ``[shell_environment_policy.set]``), and a key at any level whose first segment is one (``env = { ... }``,
    ``shell_environment_policy.inherit = "none"``), with the lines that continue a value. Blank lines and
    comment-only lines are not text that changes anything, and are left out.
    """
    kept: list[str] = []
    in_table = False
    belongs = False
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        header = _TOML_HEADER.match(line)
        key = None if header else _TOML_KEY.match(line)
        if header:
            in_table = any(segment in names for segment in _key_segments(header.group(1)))
            belongs = in_table
        elif key:
            belongs = in_table or _key_segments(key.group(1))[0] in names
        if belongs:
            kept.append(line)
    return kept


def env_changed(file_kind: str, before: str | None, after: str | None, data: Mapping[str, Any]) -> bool:
    """Whether the ``env`` of a settings file of ``file_kind`` (``json`` or ``toml``) differs between two texts."""
    if file_kind == "toml":
        names = data["toml_env_names"]
        return toml_env_lines(before, names) != toml_env_lines(after, names)
    return not _same(json_env(before), json_env(after))


def _apply_edit(text: str, edit: Any) -> str | None:
    """``text`` after one ``old_string``/``new_string`` edit, or ``None`` when the edit cannot apply."""
    if not isinstance(edit, Mapping):
        return None
    old, new = edit.get("old_string"), edit.get("new_string")
    if not isinstance(old, str) or not isinstance(new, str):
        return None
    if old == "":  # only a file that has no text yet is written by an edit with nothing to replace
        return None if text else new
    if old not in text:
        return None
    return text.replace(old, new) if edit.get("replace_all") is True else text.replace(old, new, 1)


def edited_text(tool_input: Mapping[str, Any], current: str | None) -> str | None:
    """The file's text after the edit ``tool_input`` asks for, or ``None`` when the edit cannot apply.

    ``Write`` carries ``content``; ``MultiEdit`` an ordered list ``edits``; ``Edit`` one ``old_string``
    and ``new_string`` (every occurrence with ``replace_all``, else the first). An edit whose
    ``old_string`` is not in the text (or is empty and the text is not) fails in the harness, so it changes
    nothing here.
    """
    if "content" in tool_input:
        content = tool_input["content"]
        return content if isinstance(content, str) else None
    edits = tool_input.get("edits") if "edits" in tool_input else [tool_input]
    if not isinstance(edits, list):
        return None
    text: str | None = current or ""
    for edit in edits:
        text = _apply_edit(text, edit)
        if text is None:
            return None
    return text


def edit_reason(
    tool_input: Mapping[str, Any], read_current: Callable[[str], str | None], data: Mapping[str, Any]
) -> str | None:
    """The reason to deny an ``Edit``/``Write``/``MultiEdit`` of a harness settings file's ``env``, else ``None``.

    ``read_current`` answers a path's present text, ``None`` when there is no file: the entry point reads the
    file, this function reads nothing. A file that is not a harness settings file, an edit that cannot apply
    and an edit that leaves ``env`` identical all pass.
    """
    path = tool_input.get("file_path")
    file_kind = file_format(path, data) if isinstance(path, str) else None
    if file_kind is None:
        return None
    current = read_current(path)
    after = edited_text(tool_input, current)
    if after is None or not env_changed(file_kind, current, after, data):
        return None
    return jsondata.fill(data["texts"]["edit"], {"path": path})
