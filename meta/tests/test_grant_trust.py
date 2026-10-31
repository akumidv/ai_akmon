"""C172 — trust in a project's own grant files by an owner-accepted digest (ADR 0025 D04/D05).

The JavaScript twin pins the same vectors in ``js/common/grant_trust.test.mjs`` and
``js/akmon/_trust.test.mjs``; the log lines and diff texts below are written out literally in both so a
drift in either shows as a failing literal, not as a comparison of two moving things.
"""

from __future__ import annotations

import hashlib
import io
from datetime import UTC, datetime
from pathlib import Path

import pytest

from akmon import _trust, cli
from common import grant_trust as gt

_ROOT = Path("/somewhere/proj")  # a project root no store path above sits in
ABC_DIGEST = "edeaaff3f1774ad2888673770c6d64097e391bc362d7d6fb34982ddf0efd18cb"  # sha256 of "abc\n"


def _at(second: int) -> datetime:
    return datetime(2026, 1, 2, 3, 4, second, tzinfo=UTC)


@pytest.fixture
def store(tmp_path) -> gt.TrustStore:
    return gt.resolve_store({"AKMON_TRUST_DIR": str(tmp_path / "store")}, tmp_path / "proj")


def _project(base: Path, name: str = "proj") -> Path:
    root = base / name
    (root / "_aitna" / "akmon").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# project\n", encoding="utf-8")
    return root


def _grant(root: Path, relative: str, text: str) -> gt.GrantFile:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return gt.load_grant(path, root)


# --------------------------------------------------------------------------------------
# the store: resolution order, and that reading never creates it
# --------------------------------------------------------------------------------------


def test_store_resolution_order():
    explicit = gt.resolve_store({"AKMON_TRUST_DIR": "/t", "XDG_STATE_HOME": "/x", "HOME": "/h"}, _ROOT)
    assert (explicit.root, explicit.accepted_dir, explicit.log_path) == (
        Path("/t"),
        Path("/t/accepted"),
        Path("/t/trust.log"),
    )
    assert gt.resolve_store({"XDG_STATE_HOME": "/x", "HOME": "/h"}, _ROOT).root == Path("/x/akmon/trust")
    assert gt.resolve_store({"HOME": "/h"}, _ROOT).root == Path("/h/.local/state/akmon/trust")
    # an empty variable is unset
    assert gt.resolve_store({"AKMON_TRUST_DIR": "", "XDG_STATE_HOME": "", "HOME": "/h"}, _ROOT).root == Path(
        "/h/.local/state/akmon/trust"
    )


def test_store_falls_back_to_the_process_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert gt.resolve_store({}, _ROOT).root == tmp_path / ".local" / "state" / "akmon" / "trust"


def test_a_store_inside_the_project_checkout_is_refused(tmp_path):
    root = _project(tmp_path)
    inside = root / "state" / "trust"
    for environment in (
        {"AKMON_TRUST_DIR": str(inside)},
        {"AKMON_TRUST_DIR": str(root)},
        {"XDG_STATE_HOME": str(root / "xdg")},
        {"HOME": str(root)},
    ):
        with pytest.raises(gt.GrantTrustError, match="inside the project") as excinfo:
            gt.resolve_store(environment, root)
        assert str(root) in str(excinfo.value)
        assert "\n" not in str(excinfo.value)
    assert not inside.exists()


def test_a_store_that_is_a_symlink_into_the_checkout_is_refused(tmp_path):
    root = _project(tmp_path)
    (root / "real").mkdir()
    link = tmp_path / "link"
    link.symlink_to(root / "real")
    with pytest.raises(gt.GrantTrustError, match="inside the project") as excinfo:
        gt.resolve_store({"AKMON_TRUST_DIR": str(link / "trust")}, root)
    assert str(root / "real" / "trust") in str(excinfo.value)


def test_a_store_outside_the_checkout_is_accepted_even_beside_it(tmp_path):
    root = _project(tmp_path)
    for outside in (tmp_path / "store", tmp_path / "proj-state", tmp_path):
        assert gt.resolve_store({"AKMON_TRUST_DIR": str(outside)}, root).root == outside.resolve()
    link = tmp_path / "out-link"
    link.symlink_to(tmp_path / "store", target_is_directory=True)
    assert gt.resolve_store({"AKMON_TRUST_DIR": str(link)}, root).root == (tmp_path / "store").resolve()


def test_reads_never_create_the_store(tmp_path, store):
    root = _project(tmp_path)
    grant = _grant(root, "_aitna/grants/one.toml", "a\n")
    assert gt.file_trust(grant, store).state is gt.TrustState.NEW
    assert gt.read_log(store) == ()
    assert gt.last_accepted(grant.relative, grant.project, store) is None
    assert gt.trust_report(store) == gt.TrustReport(0, 0, 0, 0, 0, None)
    assert not gt.is_accepted(grant.digest, store)
    assert not store.root.exists()


# --------------------------------------------------------------------------------------
# the default grant set
# --------------------------------------------------------------------------------------


def test_default_grant_files_are_every_regular_file_under_the_grants_directory_sorted(tmp_path):
    root = _project(tmp_path)
    grants = gt.grants_directory(root)
    assert grants == root / "_aitna" / "grants"
    assert gt.list_grant_files(grants) == ()
    _grant(root, "_aitna/grants/b.toml", "b")
    _grant(root, "_aitna/grants/a/z.toml", "z")
    _grant(root, "_aitna/grants/a/deep/y.toml", "y")
    _grant(root, "_aitna/grants/a.toml", "a")
    (grants / "link.toml").symlink_to(grants / "a.toml")
    (grants / "dirlink").symlink_to(grants / "a", target_is_directory=True)
    relative = [path.relative_to(grants).as_posix() for path in gt.list_grant_files(grants)]
    assert relative == ["a.toml", "a/deep/y.toml", "a/z.toml", "b.toml"]


def test_the_grants_directory_follows_the_configured_dev_layer_root(tmp_path):
    (tmp_path / ".aitna-root").write_text("tools/ai\n", encoding="utf-8")
    assert gt.grants_directory(tmp_path) == tmp_path / "tools" / "ai" / "grants"


# --------------------------------------------------------------------------------------
# digest and state
# --------------------------------------------------------------------------------------


def test_digest_is_the_sha256_of_the_bytes(tmp_path):
    path = tmp_path / "f"
    path.write_bytes(b"abc\n")
    assert gt.file_digest(path) == ABC_DIGEST == hashlib.sha256(b"abc\n").hexdigest()


def test_state_is_new_then_trusted_then_changed(tmp_path, store):
    root = _project(tmp_path)
    one = _grant(root, "_aitna/grants/one.toml", "a\n")
    assert gt.file_trust(one, store) == gt.FileTrust(one, gt.TrustState.NEW, None)
    gt.accept(one, store, _at(1))
    assert gt.file_trust(one, store).state is gt.TrustState.TRUSTED
    edited = _grant(root, "_aitna/grants/one.toml", "a\nb\n")
    assert gt.file_trust(edited, store) == gt.FileTrust(edited, gt.TrustState.CHANGED, one.digest)
    other_path = _grant(root, "_aitna/grants/two.toml", "x\n")
    assert gt.file_trust(other_path, store).state is gt.TrustState.NEW


def test_history_is_keyed_by_project_and_path_so_another_projects_file_is_new_not_changed(tmp_path, store):
    first = _project(tmp_path, "first")
    second = _project(tmp_path, "second")
    accepted = _grant(first, "_aitna/grants/one.toml", "a\n")
    gt.accept(accepted, store, _at(1))
    other = _grant(second, "_aitna/grants/one.toml", "a\nb\n")
    assert gt.file_trust(other, store) == gt.FileTrust(other, gt.TrustState.NEW, None)
    assert gt.last_accepted(other.relative, other.project, store) is None
    elsewhere = gt.last_accepted_elsewhere(other.relative, other.project, store)
    assert elsewhere is not None and (elsewhere.project, elsewhere.digest) == ("first", accepted.digest)
    assert gt.last_accepted_elsewhere(accepted.relative, accepted.project, store) is None
    # accepting it is a first acceptance in its project: the log's previous field stays "-"
    assert gt.accept(other, store, _at(2)).previous == "-"
    assert gt.format_event(gt.read_log(store)[-1]).endswith("\t_aitna/grants/one.toml\tsecond\t-")
    changed = _grant(second, "_aitna/grants/one.toml", "a\nc\n")
    assert gt.file_trust(changed, store) == gt.FileTrust(changed, gt.TrustState.CHANGED, other.digest)
    assert gt.record_untrusted(changed, store, _at(3)).previous == other.digest


def test_trust_is_keyed_by_content_not_by_project_or_path(tmp_path, store):
    first = _project(tmp_path, "first")
    clone = _project(tmp_path / "elsewhere", "clone")
    accepted = _grant(first, "_aitna/grants/one.toml", "same text\n")
    gt.accept(accepted, store, _at(1))
    moved = _grant(clone, "_aitna/grants/renamed/other.toml", "same text\n")
    assert moved.digest == accepted.digest
    assert gt.file_trust(moved, store).state is gt.TrustState.TRUSTED


def test_a_file_outside_the_project_or_with_an_unloggable_name_is_refused(tmp_path):
    root = _project(tmp_path)
    outside = tmp_path / "outside.toml"
    outside.write_text("x", encoding="utf-8")
    with pytest.raises(gt.GrantTrustError, match="outside the project root"):
        gt.load_grant(outside, root)
    tabbed = root / "_aitna" / "grants" / "a\tb.toml"
    tabbed.parent.mkdir(parents=True)
    tabbed.write_text("x", encoding="utf-8")
    with pytest.raises(gt.GrantTrustError, match="tab or a line break"):
        gt.load_grant(tabbed, root)


# --------------------------------------------------------------------------------------
# accept, revoke, sightings: the log and the copies
# --------------------------------------------------------------------------------------


def test_accept_keeps_the_bytes_and_logs_one_exact_line(tmp_path, store):
    root = _project(tmp_path)
    grant = _grant(root, "_aitna/grants/one.toml", "abc\n")
    event = gt.accept(grant, store, _at(5))
    assert (store.accepted_dir / ABC_DIGEST).read_bytes() == b"abc\n"
    assert (
        store.log_path.read_text(encoding="utf-8")
        == f"2026-01-02T03:04:05Z\taccept\t{ABC_DIGEST}\t_aitna/grants/one.toml\tproj\t-\n"
    )
    assert gt.format_event(event) + "\n" == store.log_path.read_text(encoding="utf-8")
    assert not list(store.accepted_dir.glob(".*.tmp"))
    with pytest.raises(gt.GrantTrustError, match="already accepted"):
        gt.accept(grant, store, _at(6))
    assert len(gt.read_log(store)) == 1


def test_a_re_acceptance_logs_the_previous_digest_of_the_same_path(tmp_path, store):
    root = _project(tmp_path)
    first = _grant(root, "_aitna/grants/one.toml", "a\n")
    gt.accept(first, store, _at(1))
    second = _grant(root, "_aitna/grants/one.toml", "a\nb\n")
    event = gt.accept(second, store, _at(2))
    assert event.previous == first.digest
    assert gt.last_accepted(second.relative, second.project, store) == second.digest
    # a different path starts its own chain
    assert gt.accept(_grant(root, "_aitna/grants/two.toml", "x\n"), store, _at(3)).previous == "-"


def test_revoke_removes_the_copy_logs_it_and_makes_the_file_untrusted(tmp_path, store):
    root = _project(tmp_path)
    grant = _grant(root, "_aitna/grants/one.toml", "abc\n")
    gt.accept(grant, store, _at(1))
    event = gt.revoke(grant.digest, store, _at(9))
    assert not (store.accepted_dir / ABC_DIGEST).exists()
    assert gt.format_event(event) == f"2026-01-02T03:04:09Z\trevoke\t{ABC_DIGEST}\t_aitna/grants/one.toml\tproj\t-"
    assert gt.file_trust(grant, store).state is gt.TrustState.NEW
    with pytest.raises(gt.GrantTrustError, match="not accepted"):
        gt.revoke(grant.digest, store)


def test_last_accepted_skips_a_revoked_digest_and_falls_back_to_an_earlier_one(tmp_path, store):
    root = _project(tmp_path)
    first = _grant(root, "_aitna/grants/one.toml", "1\n")
    second = _grant(root, "_aitna/grants/one.toml", "2\n")
    gt.accept(first, store, _at(1))
    gt.accept(second, store, _at(2))
    gt.revoke(second.digest, store, _at(3))
    assert gt.last_accepted("_aitna/grants/one.toml", "proj", store) == first.digest
    current = _grant(root, "_aitna/grants/one.toml", "3\n")
    assert gt.file_trust(current, store) == gt.FileTrust(current, gt.TrustState.CHANGED, first.digest)


def test_an_untrusted_sighting_is_logged_once_per_digest(tmp_path, store):
    root = _project(tmp_path)
    grant = _grant(root, "_aitna/grants/one.toml", "abc\n")
    first = gt.record_untrusted(grant, store, _at(1))
    assert first is not None
    assert gt.format_event(first) == f"2026-01-02T03:04:01Z\tuntrusted\t{ABC_DIGEST}\t_aitna/grants/one.toml\tproj\t-"
    assert gt.record_untrusted(grant, store, _at(2)) is None
    assert len(gt.read_log(store)) == 1
    # another content at the same path is another digest, and names the accepted predecessor
    gt.accept(grant, store, _at(3))
    changed = _grant(root, "_aitna/grants/one.toml", "abcd\n")
    event = gt.record_untrusted(changed, store, _at(4))
    assert event is not None and event.previous == grant.digest
    # an accepted digest is not an untrusted one
    assert gt.record_untrusted(grant, store, _at(5)) is None


def test_the_log_is_append_only_and_a_malformed_line_names_its_number(tmp_path, store):
    root = _project(tmp_path)
    gt.accept(_grant(root, "_aitna/grants/one.toml", "a\n"), store, _at(1))
    with store.log_path.open("a", encoding="utf-8") as log:
        log.write("not a trust line\n")
    with pytest.raises(gt.GrantTrustError, match=r"trust\.log:2: malformed trust log line"):
        gt.read_log(store)


def test_a_naive_event_time_is_refused(tmp_path, store):
    grant = _grant(_project(tmp_path), "_aitna/grants/one.toml", "a\n")
    with pytest.raises(ValueError, match="timezone"):
        gt.accept(grant, store, datetime(2026, 1, 1))  # noqa: DTZ001 — the naive value is the case under test
    assert not store.root.exists()


def test_resolve_digest_takes_a_unique_prefix_of_at_least_twelve_hex(tmp_path, store):
    grant = _grant(_project(tmp_path), "_aitna/grants/one.toml", "abc\n")
    gt.accept(grant, store, _at(1))
    assert gt.resolve_digest(ABC_DIGEST[:12], store) == ABC_DIGEST
    assert gt.resolve_digest(ABC_DIGEST, store) == ABC_DIGEST
    for bad, message in (
        (ABC_DIGEST[:11], "not a digest"),
        ("0" * 12, "names no accepted digest"),
        ("XYZ" * 5, "not a digest"),
    ):
        with pytest.raises(gt.GrantTrustError, match=message):
            gt.resolve_digest(bad, store)


# --------------------------------------------------------------------------------------
# the report
# --------------------------------------------------------------------------------------


def test_report_counts_the_log_and_the_median_wait(tmp_path, store):
    root = _project(tmp_path)
    one, two, three = (_grant(root, f"_aitna/grants/{name}.toml", name) for name in ("one", "two", "three"))
    gt.record_untrusted(one, store, _at(0))
    gt.record_untrusted(two, store, _at(10))
    gt.record_untrusted(three, store, _at(20))  # sighted, never accepted
    gt.accept(one, store, _at(30))  # waited 30 s
    gt.accept(two, store, _at(50))  # waited 40 s
    edited = _grant(root, "_aitna/grants/one.toml", "one edited")
    gt.accept(edited, store, _at(55))  # a re-acceptance, never sighted
    gt.revoke(two.digest, store, _at(58))
    assert gt.trust_report(store) == gt.TrustReport(
        accepts=3, reaccepts=1, revokes=1, untrusted_digests=3, accepted_after_sighting=2, median_seconds=35.0
    )


def test_reaccepts_are_counted_per_project_and_path(tmp_path, store):
    first = _project(tmp_path, "first")
    second = _project(tmp_path, "second")
    gt.accept(_grant(first, "_aitna/grants/one.toml", "a\n"), store, _at(1))
    gt.accept(_grant(second, "_aitna/grants/one.toml", "a\nb\n"), store, _at(2))  # a new file, not a re-acceptance
    assert gt.trust_report(store).reaccepts == 0
    gt.accept(_grant(first, "_aitna/grants/one.toml", "a\nc\n"), store, _at(3))
    assert gt.trust_report(store) == gt.TrustReport(3, 1, 0, 0, 0, None)


def test_report_median_of_an_odd_count(tmp_path, store):
    root = _project(tmp_path)
    grants = [_grant(root, f"_aitna/grants/{n}.toml", n) for n in "abc"]
    for index, grant in enumerate(grants):
        gt.record_untrusted(grant, store, _at(index))
    for index, wait in enumerate((5, 7, 40)):
        gt.accept(grants[index], store, _at(index + wait))
    assert gt.trust_report(store).median_seconds == 7.0


# --------------------------------------------------------------------------------------
# the diff
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (
            b"a\nb\nc\nd\ne\nf\ng\nh\n",
            b"a\nb\nc\nD\ne\nf\ng\nh\n",
            "--- old\n+++ new\n@@ -1,7 +1,7 @@\n a\n b\n c\n-d\n+D\n e\n f\n g\n",
        ),
        (b"a\n", b"a\nb\n", "--- old\n+++ new\n@@ -1 +1,2 @@\n a\n+b\n"),
        (b"", b"x\n", "--- old\n+++ new\n@@ -0,0 +1 @@\n+x\n"),
        (b"x\n", b"", "--- old\n+++ new\n@@ -1 +0,0 @@\n-x\n"),
        (b"same\n", b"same\n", ""),
        (b"same\n", b"same", ""),
        (
            b"1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12\n",
            b"1\nTWO\n3\n4\n5\n6\n7\n8\n9\n10\n11\nTWELVE\n",
            "--- old\n+++ new\n@@ -1,5 +1,5 @@\n 1\n-2\n+TWO\n 3\n 4\n 5\n"
            "@@ -9,4 +9,4 @@\n 9\n 10\n 11\n-12\n+TWELVE\n",
        ),
    ],
)
def test_unified_diff_vectors(old, new, expected):
    assert gt.unified_diff(old, new, "old", "new") == expected


# --------------------------------------------------------------------------------------
# the command line, through its one seam
# --------------------------------------------------------------------------------------


class _Terminal:
    """A fake process: captured streams, a scripted terminal, a project on disk."""

    def __init__(self, tmp_path: Path, *, interactive: bool = True, answers: list[str] | None = None) -> None:
        self.root = _project(tmp_path)
        self.out, self.err = io.StringIO(), io.StringIO()
        self.prompts: list[str] = []
        self._answers = list(answers or [])
        self.io = _trust.TrustIO(
            {"AKMON_TRUST_DIR": str(tmp_path / "store")}, self.root, self.out, self.err, interactive, self._ask
        )
        self.store = gt.resolve_store(self.io.environ, self.root)

    def _ask(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self._answers:
            raise EOFError
        return self._answers.pop(0)

    def run(self, *argv: str) -> int:
        self.out.seek(0)
        self.out.truncate()
        self.err.seek(0)
        self.err.truncate()
        return _trust.main(argv, self.io)

    def grant(self, name: str, text: str) -> gt.GrantFile:
        return _grant(self.root, f"_aitna/grants/{name}", text)


def _without_a_project_root(term: _Terminal, tmp_path: Path) -> Path:
    bare = tmp_path / "bare"
    bare.mkdir()
    term.io = _trust.TrustIO(term.io.environ, bare, term.out, term.err, interactive=True, ask=term._ask)
    return bare


def test_accept_with_no_project_root_refuses_and_records_nothing(tmp_path):
    term = _Terminal(tmp_path / "t", answers=["y"])
    bare = _without_a_project_root(term, tmp_path)
    assert term.run("accept") == 2
    assert "no project root at or above" in term.err.getvalue()
    assert term.prompts == []
    assert list(bare.iterdir()) == []
    assert not (tmp_path / "t" / "store").exists()


def test_revoke_with_no_project_root_refuses_and_records_nothing(tmp_path):
    term = _Terminal(tmp_path / "t")
    bare = _without_a_project_root(term, tmp_path)
    assert term.run("revoke", "_aitna/grants/one.toml") == 2
    assert "no project root at or above" in term.err.getvalue()
    assert list(bare.iterdir()) == []
    assert not (tmp_path / "t" / "store").exists()


def test_status_lists_state_short_digest_and_path_and_exits_one_while_untrusted(tmp_path):
    term = _Terminal(tmp_path)
    one, two = term.grant("one.toml", "abc\n"), term.grant("two.toml", "x\n")
    gt.accept(one, term.store, _at(1))
    assert term.run("status") == 1
    assert term.out.getvalue() == (
        f"trusted  {ABC_DIGEST[:12]}  _aitna/grants/one.toml\nnew      {two.digest[:12]}  _aitna/grants/two.toml\n"
    )
    gt.accept(two, term.store, _at(2))
    assert term.run("status") == 0
    assert term.run("status", "_aitna/grants/one.toml") == 0
    assert term.out.getvalue() == f"trusted  {ABC_DIGEST[:12]}  _aitna/grants/one.toml\n"


def test_status_takes_paths_relative_to_the_cwd_and_directories(tmp_path):
    term = _Terminal(tmp_path)
    term.grant("sub/one.toml", "x\n")
    term.io = _trust.TrustIO(term.io.environ, term.root / "_aitna", term.out, term.err, interactive=True, ask=term._ask)
    assert term.run("status", "grants/sub") == 1
    assert term.out.getvalue().endswith("  _aitna/grants/sub/one.toml\n")
    assert term.run("status", "grants/missing.toml") == 2
    assert "no such file or directory" in term.err.getvalue()


def test_status_says_so_in_one_line_when_there_is_nothing_to_check(tmp_path):
    term = _Terminal(tmp_path)
    assert term.run("status") == 0
    assert term.out.getvalue() == "akmon trust: no grant files under _aitna/grants/\n"
    assert not term.store.root.exists()


def test_diff_shows_the_whole_file_when_new_and_the_change_when_changed(tmp_path):
    term = _Terminal(tmp_path)
    first = term.grant("one.toml", "a\nb\n")
    assert term.run("diff") == 0
    assert (
        term.out.getvalue()
        == "=== _aitna/grants/one.toml: new, no earlier version accepted; the whole file follows ===\na\nb\n"
    )
    gt.accept(first, term.store, _at(1))
    assert term.run("diff") == 0
    assert term.out.getvalue() == "akmon trust: every grant file is trusted; nothing to show\n"
    changed = term.grant("one.toml", "a\nB\n")
    assert term.run("diff") == 0
    assert term.out.getvalue() == (
        f"=== _aitna/grants/one.toml: changed since {first.digest[:12]} ===\n"
        f"--- _aitna/grants/one.toml (accepted {first.digest[:12]})\n"
        f"+++ _aitna/grants/one.toml (now {changed.digest[:12]})\n"
        "@@ -1,2 +1,2 @@\n a\n-b\n+B\n"
    )
    assert not (term.store.root / "trust.log").read_text(encoding="utf-8").count("untrusted")


def test_diff_of_a_file_new_to_this_project_names_the_project_that_accepted_the_path(tmp_path):
    term = _Terminal(tmp_path)
    other = _project(tmp_path, "other")
    accepted = _grant(other, "_aitna/grants/one.toml", "a\nb\n")
    gt.accept(accepted, term.store, _at(1))
    new = term.grant("one.toml", "a\nB\n")
    assert gt.file_trust(new, term.store).state is gt.TrustState.NEW
    assert term.run("status") == 1
    assert term.out.getvalue().startswith("new      ")
    assert term.run("diff") == 0
    assert term.out.getvalue() == (
        f"=== _aitna/grants/one.toml: new in this project; last accepted in project other as {accepted.digest[:12]}, "
        "the change since that version follows ===\n"
        f"--- _aitna/grants/one.toml (accepted in project other, {accepted.digest[:12]})\n"
        f"+++ _aitna/grants/one.toml (now {new.digest[:12]})\n"
        "@@ -1,2 +1,2 @@\n a\n-b\n+B\n"
    )


def test_the_command_refuses_a_store_inside_the_project_in_one_line(tmp_path):
    term = _Terminal(tmp_path)
    inside = term.root / "state"
    term.io = _trust.TrustIO(
        {"AKMON_TRUST_DIR": str(inside)}, term.root, term.out, term.err, interactive=True, ask=term._ask
    )
    assert term.run("status") == 2
    assert term.err.getvalue() == (
        f"akmon trust: the trust store {inside} is inside the project {term.root}; "
        "set AKMON_TRUST_DIR to a directory outside the checkout (ADR 0025/D05)\n"
    )
    assert not inside.exists()


def test_accept_refuses_without_a_terminal_and_writes_nothing(tmp_path):
    term = _Terminal(tmp_path, interactive=False, answers=["y"])
    term.grant("one.toml", "a\n")
    assert term.run("accept") == 2
    assert "acceptance needs an interactive terminal" in term.err.getvalue()
    assert "ADR 0025/D05" in term.err.getvalue()
    assert term.prompts == []
    assert not term.store.root.exists()


def test_accept_shows_each_untrusted_file_then_asks_and_records_the_answers(tmp_path):
    term = _Terminal(tmp_path, answers=["y", "n"])
    one, two = term.grant("one.toml", "abc\n"), term.grant("two.toml", "x\n")
    assert term.run("accept") == 1
    assert term.prompts == ["accept _aitna/grants/one.toml? [y/N] ", "accept _aitna/grants/two.toml? [y/N] "]
    assert gt.is_accepted(one.digest, term.store)
    assert not gt.is_accepted(two.digest, term.store)
    assert "_aitna/grants/one.toml: accepted " + ABC_DIGEST[:12] in term.out.getvalue()
    assert "_aitna/grants/two.toml: not accepted" in term.out.getvalue()
    # trusted files are not asked about again; end of input counts as no
    assert term.run("accept") == 1
    assert term.prompts[2:] == ["accept _aitna/grants/two.toml? [y/N] "]
    assert "_aitna/grants/one.toml: already trusted" in term.out.getvalue()


def test_accept_only_takes_a_y_or_yes(tmp_path):
    term = _Terminal(tmp_path, answers=["", "yes", "Y"])
    for name in ("a.toml", "b.toml", "c.toml"):
        term.grant(name, name)
    assert term.run("accept") == 1
    assert [term.store.accepted_dir.exists(), len(list(term.store.accepted_dir.iterdir()))] == [True, 2]


def test_accept_has_no_yes_flag(tmp_path):
    term = _Terminal(tmp_path, answers=["y"])
    term.grant("one.toml", "a\n")
    assert term.run("accept", "--yes") == 2
    assert "takes no options" in term.err.getvalue()
    assert not term.store.root.exists()


def test_accept_records_what_was_shown_when_the_file_changes_before_the_answer(tmp_path):
    term = _Terminal(tmp_path)
    term.grant("one.toml", "shown\n")

    def swap(prompt: str) -> str:
        term.grant("one.toml", "swapped after the owner looked\n")
        return "y"

    term.io = _trust.TrustIO(term.io.environ, term.root, term.out, term.err, interactive=True, ask=swap)
    assert term.run("accept") == 0
    swapped = term.grant("one.toml", "swapped after the owner looked\n")
    assert gt.file_trust(swapped, term.store).state is gt.TrustState.CHANGED
    assert gt.file_trust(term.grant("one.toml", "shown\n"), term.store).state is gt.TrustState.TRUSTED


def test_revoke_by_digest_prefix_or_by_path(tmp_path):
    term = _Terminal(tmp_path)
    first = term.grant("one.toml", "abc\n")
    gt.accept(first, term.store, _at(1))
    assert term.run("revoke", ABC_DIGEST[:12]) == 0
    assert term.out.getvalue() == f"revoked {ABC_DIGEST[:12]} (_aitna/grants/one.toml)\n"
    gt.accept(first, term.store, _at(2))
    assert term.run("revoke", "_aitna/grants/one.toml") == 0
    assert not gt.is_accepted(first.digest, term.store)
    # a path whose current content is not accepted revokes the last accepted version of that path
    gt.accept(first, term.store, _at(3))
    term.grant("one.toml", "changed\n")
    assert term.run("revoke", "_aitna/grants/one.toml") == 0
    assert not gt.is_accepted(first.digest, term.store)
    assert term.run("revoke", "_aitna/grants/one.toml") == 2
    assert "no accepted version to revoke" in term.err.getvalue()
    assert term.run("revoke", "0" * 12) == 2
    assert term.run("revoke") == 2


def test_report_prints_the_summary(tmp_path):
    term = _Terminal(tmp_path)
    assert term.run("report") == 0
    assert term.out.getvalue() == (
        "accepts: 0\nre-accepts: 0\nrevokes: 0\nuntrusted digests sighted: 0\n"
        "sighted digests later accepted: 0\nmedian seconds from sighting to acceptance: -\n"
    )
    one = term.grant("one.toml", "a\n")
    gt.record_untrusted(one, term.store, _at(0))
    gt.accept(one, term.store, _at(30))
    assert term.run("report") == 0
    assert term.out.getvalue() == (
        "accepts: 1\nre-accepts: 0\nrevokes: 0\nuntrusted digests sighted: 1\n"
        "sighted digests later accepted: 1\nmedian seconds from sighting to acceptance: 30.0\n"
    )
    assert term.run("report", "extra") == 2


def test_usage_errors_exit_two(tmp_path):
    term = _Terminal(tmp_path)
    assert term.run() == 2
    assert term.run("frobnicate") == 2
    assert "unknown command 'frobnicate'" in term.err.getvalue()
    assert term.run("--help") == 0
    assert term.out.getvalue().startswith("usage: akmon trust")


def test_the_cli_dispatches_trust_through_the_process(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    _grant(root, "_aitna/grants/one.toml", "a\n")
    monkeypatch.chdir(root)
    monkeypatch.setenv("AKMON_TRUST_DIR", str(tmp_path / "store"))
    assert cli.main(["trust", "status"]) == 1
    assert capsys.readouterr().out.startswith("new      ")
    # pytest's stdin is not a terminal
    assert cli.main(["trust", "accept"]) == 2
    assert "acceptance needs an interactive terminal" in capsys.readouterr().err
    assert not (tmp_path / "store").exists()
