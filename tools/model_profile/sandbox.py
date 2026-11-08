"""The execution sandbox: model-written Python runs in a container, or not at all.

The suite grades answers by **running** them, so the code a model writes is untrusted input
that happens to be executable. The container is a slim CPython image (``profile.json`` names
it and every limit below) with:

* ``--network none`` - the code cannot reach the endpoint, a forge or the internet;
* ``--read-only`` - the image's own filesystem is immutable;
* a tmpfs on ``/tmp`` and a tmpfs on the work directory - the only writable places, and they
  are RAM;
* a memory limit and a process limit - a fork bomb or a memory hog dies, not the host;
* ``--cap-drop ALL`` and ``--security-opt no-new-privileges`` - no Linux capabilities;
* an unprivileged user - the code is nobody in the container;
* **no host mount at all** - the case's files travel in as a tar stream over stdin and never
  exist as a host path inside the container, so there is nothing to escape into.

``container_command`` builds the one argv that carries these flags; a test pins it.

**Docker being unavailable is a refusal, never a fallback.** Running model-written code on the
host because the container runtime is missing would turn a missing dependency into a host
compromise; the tool exits non-zero instead.

**The verdict cannot be forged by the code under test.** The in-container runner is handed a
per-run random nonce in a file it deletes before it imports anything of the model's. It runs
the hidden test with ``sys.stdout`` redirected, so the program's own prints land nowhere, and
then writes one marker line - the nonce and a JSON verdict - on its own line. The host reads
the **last line of stdout only** and accepts it only when it carries that nonce. A program
that prints a fake marker, or leaves a line unterminated, cannot change the verdict; one that
kills the runner before it reports earns "no verdict", which is a failed attempt, not a
passed one. The residual risk is code that digs the nonce out of the runner's memory; that
needs a deliberate attack, and the container still bounds what it can do.

Every run has an explicit wall-clock timeout, passed to ``subprocess.run``, and a container
name so a run killed by its own timeout can be removed.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import secrets
import shlex
import shutil
import subprocess
import tarfile
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import settings

#: What the grader needs from a sandbox run: the program's files, the hidden test's path and
#: the test's own source - the sandbox runs the test out of the workspace, so the source
#: travels with the call.
type TestRunner = Callable[[Mapping[str, str], str, str], SandboxResult]

# The image, the limits, the names the sandbox owns and docker's failure codes are data
# (``profile.json``, read through ``settings.load().sandbox``). The in-container test runner -
# it imports the hidden test and calls every ``test_*`` function it finds, because the image
# carries no pytest and the sandbox has no network to install one - is a Python program of its
# own, ``container_runner.py.txt``, read through ``settings.runner_source()``: both twins ship
# the same file to the container.


class SandboxUnavailableError(RuntimeError):
    """The container runtime is missing or unusable - the run is refused, never downgraded."""


class SandboxError(RuntimeError):
    """The sandbox could not run the code at all - the attempt is not a model's failure."""


class VerdictMissingError(ValueError):
    """The run's stdout carries no verdict line with this run's nonce."""


@dataclass(frozen=True)
class Verdict:
    """What the in-container runner reported: per-test outcomes and a collection error."""

    tests: Mapping[str, str]
    error: str | None


@dataclass(frozen=True)
class SandboxResult:
    """What one sandboxed run produced.

    ``passed`` is the whole verdict the graders need; ``tests`` keeps the per-function
    breakdown so a report can say which check failed, and ``timed_out`` separates a slow
    answer from a wrong one.
    """

    passed: bool
    tests: Mapping[str, str] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False
    duration_s: float = 0.0

    @property
    def failed_tests(self) -> tuple[str, ...]:
        """The names of the hidden-test functions that failed."""
        return tuple(sorted(name for name, outcome in self.tests.items() if outcome != "passed"))


def ensure_available() -> None:
    """Raise ``SandboxUnavailableError`` unless a container runtime can run the suite.

    The check is the runtime's own answer, not a guess from a binary on the path: a
    ``docker`` on the path with no daemon behind it is not a sandbox.
    """
    binary = shutil.which("docker")
    if binary is None:
        raise SandboxUnavailableError(
            "docker is not on the PATH: model-written code is only ever run in a container, "
            "never on the host, so the probe is refused rather than downgraded"
        )
    try:
        completed = subprocess.run(
            [binary, "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=settings.load().sandbox.docker_command_timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SandboxUnavailableError(f"docker could not be reached: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[: settings.load().sandbox.detail_chars]
        raise SandboxUnavailableError(f"docker is installed but its daemon is not usable: {detail}")


def _as_text(payload: bytes | str | None) -> str:
    """A subprocess stream as text - the tar stream makes the capture binary."""
    if payload is None:
        return ""
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace")
    return payload


def _add_file(archive: tarfile.TarFile, path: str, payload: bytes) -> None:
    info = tarfile.TarInfo(path)
    info.size = len(payload)
    info.mode = 0o644
    info.mtime = 0
    archive.addfile(info, io.BytesIO(payload))


def tar_stream(files: Mapping[str, str], nonce: str) -> bytes:
    """The case's files as a tar stream, with the in-container runner and the nonce beside them.

    Raises:
        SandboxError: the case carries a file named like one the sandbox adds itself.
    """
    config = settings.load().sandbox
    reserved = sorted({config.runner_file, config.nonce_file}.intersection(files))
    if reserved:
        raise SandboxError(f"the case carries a file the sandbox reserves: {', '.join(reserved)}")
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for path in sorted(files):
            _add_file(archive, path, files[path].encode("utf-8"))
        _add_file(archive, config.runner_file, settings.runner_source().encode("utf-8"))
        _add_file(archive, config.nonce_file, nonce.encode("utf-8"))
    return buffer.getvalue()


def container_command(name: str, test_path: str) -> list[str]:
    """The ``docker run`` invocation: the isolation envelope, in one place."""
    config = settings.load().sandbox
    work_dir = config.work_dir
    script = (
        f"tar -xf - -C {work_dir} --no-same-owner --no-same-permissions "
        f"&& exec python -B {work_dir}/{config.runner_file} {shlex.quote(test_path)} {work_dir} {config.result_prefix}"
    )
    return [
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        f"/tmp:rw,noexec,nosuid,size={config.workspace_size}",  # noqa: S108 - container tmpfs
        "--tmpfs",
        f"{work_dir}:rw,size={config.workspace_size},mode=1777",
        "--memory",
        config.memory_limit,
        "--pids-limit",
        config.pids_limit,
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        config.container_user,
        "--workdir",
        work_dir,
        config.image,
        "sh",
        "-c",
        script,
    ]


def parse_verdict(stdout: str, nonce: str) -> Verdict:
    """The runner's verdict: the last line of ``stdout``, accepted only with this run's nonce.

    Raises:
        VerdictMissingError: the last line is not a verdict line carrying ``nonce``, or its
            JSON is not a verdict.
    """
    lines = stdout.rstrip("\r\n").split("\n")
    last = lines[-1]
    head = f"{settings.load().sandbox.result_prefix} {nonce} "
    if not last.startswith(head):
        raise VerdictMissingError("the last line of stdout is not this run's verdict line")
    try:
        payload = json.loads(last[len(head) :])
    except json.JSONDecodeError as exc:
        raise VerdictMissingError(f"the verdict line is not valid JSON: {exc}") from exc
    tests = payload.get("tests") if isinstance(payload, dict) else None
    error = payload.get("error") if isinstance(payload, dict) else None
    well_formed = isinstance(tests, dict) and all(
        isinstance(name, str) and outcome in ("passed", "failed") for name, outcome in tests.items()
    )
    if not well_formed or not (error is None or isinstance(error, str)):
        raise VerdictMissingError("the verdict line does not have the shape of a verdict")
    return Verdict(tests=dict(tests), error=error)


def run_hidden_test(
    files: Mapping[str, str],
    test_path: str,
    *,
    timeout_s: int | None = None,
    extra_files: Mapping[str, str] | None = None,
) -> SandboxResult:
    """Run the hidden test at ``test_path`` against ``files`` inside the container.

    ``files`` is the program under test - the buggy files, or the patched ones. ``extra_files``
    (the hidden test itself) is added to the workspace under its own path.

    A run that ends without a verdict because the *program* ended it (a crash, an out-of-memory
    kill, an ``os._exit``) is a failed result; one that ends without a verdict because *docker*
    failed is a ``SandboxError``.

    Raises:
        SandboxUnavailableError: no usable container runtime.
        SandboxError: the container could not be started or docker itself failed.
    """
    ensure_available()
    timeout_s = settings.load().sandbox.default_timeout_s if timeout_s is None else timeout_s
    workspace = {**files, **(extra_files or {})}
    nonce = secrets.token_hex(16)
    name = f"model-profile-{uuid.uuid4().hex[:12]}"
    payload = tar_stream(workspace, nonce)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            container_command(name, test_path),
            input=payload,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        _remove_container(name)
        return SandboxResult(
            passed=False,
            stdout=_as_text(exc.stdout),
            stderr=f"the sandboxed run exceeded its {timeout_s}s limit",
            exit_code=-1,
            timed_out=True,
            duration_s=time.monotonic() - started,
        )
    except OSError as exc:
        raise SandboxError(f"the sandbox could not be started: {exc}") from exc
    return _result_of(completed, nonce, time.monotonic() - started)


def _result_of(completed: subprocess.CompletedProcess[bytes], nonce: str, duration_s: float) -> SandboxResult:
    """The result of a finished container run - a missing verdict is the program's, unless docker failed."""
    detail_chars = settings.load().sandbox.detail_chars
    stdout = _as_text(completed.stdout)
    stderr = _as_text(completed.stderr)
    try:
        verdict = parse_verdict(stdout, nonce)
    except VerdictMissingError as exc:
        if completed.returncode in settings.load().sandbox.docker_failure_codes:
            raise SandboxError(
                f"the sandboxed run produced no verdict (exit code {completed.returncode}): "
                f"{(stderr or stdout).strip()[:detail_chars]}"
            ) from exc
        return SandboxResult(
            passed=False,
            stdout=stdout,
            stderr=(
                f"no verdict from the program's run (exit code {completed.returncode}): {stderr.strip()[:detail_chars]}"
            ),
            exit_code=completed.returncode,
            duration_s=duration_s,
        )
    return SandboxResult(
        passed=bool(verdict.tests) and verdict.error is None and all(o == "passed" for o in verdict.tests.values()),
        tests=verdict.tests,
        stdout=stdout,
        stderr=stderr if verdict.error is None else f"{stderr}\n{verdict.error}".strip(),
        exit_code=completed.returncode,
        duration_s=duration_s,
    )


def _remove_container(name: str) -> None:
    """Remove a container left behind by a timed-out run - best effort, never fatal."""
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):
        subprocess.run(
            ["docker", "rm", "--force", name],
            capture_output=True,
            text=True,
            timeout=settings.load().sandbox.docker_command_timeout_s,
            check=False,
        )


_FENCE = re.compile(r"```python\n(.*?)```", re.DOTALL)


def extract_python_block(answer: str) -> str | None:
    """The one fenced ```python block of an answer, or ``None`` when there is not exactly one."""
    blocks = _FENCE.findall(answer)
    if len(blocks) != 1:
        return None
    return blocks[0]
