"""One completion call - pinned, streamed, and never a model's fault.

The probe asks a model a question and grades the answer, so the transport has three
properties the measurement depends on:

* **The envelope is pinned.** The temperature is 0 and the output-token cap is explicit: one
  run's pass@1 moves by several points without it, so an unpinned envelope makes two scores
  incomparable. The knobs actually sent travel with the answer, as the ledger row's
  ``request`` field.
* **The call streams.** A proxy may close a non-streamed call before a reasoning model's
  answer can arrive, so the answer is read as a server-sent-event stream with
  ``stream_options.include_usage`` - the usage is captured, not guessed.
* **A transport failure is a deferral, never a wrong answer.** An empty answer, a cut-off
  answer (``finish_reason: length``), a timeout, an HTTP error, a dropped or truncated stream
  (``OSError`` and ``http.client.HTTPException``, ``IncompleteRead`` included) are all
  deferrals: they are counted on their own line and never scored as a miss. Only an answer
  the model actually produced can be wrong.

A channel is anything that satisfies :class:`Channel`: ``runner`` asks it for a pinned
``variant`` and a ``complete`` call and knows nothing else, so another way to reach a model (a
harness CLI, say) is a new class here and no change to ``runner``. Only :class:`EndpointChannel`
exists today: an OpenAI-compatible chat-completions endpoint.

The bearer token lives in a field that keeps it out of every representation, and no message
raised here quotes it.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import settings

# The endpoint's paths, the marker that closes a stream, the direct scaffold's name, the models
# listing's timeout and how much of an error body a message quotes are data (``profile.json``,
# read through ``settings.load().transport``).

#: What opens a request: a request and a per-operation timeout in, a readable response out.
type Opener = Callable[[urllib.request.Request, float], http.client.HTTPResponse]


def urlopen_opener(request: urllib.request.Request, timeout: float) -> http.client.HTTPResponse:
    """The standard opener: ``urllib.request.urlopen``."""
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - the scheme is checked in EndpointConfig


class TransportError(RuntimeError):
    """The call produced no answer - the reason names what went wrong.

    The usage the stream had already reported travels with the error, so a deferral's cost is
    recorded rather than lost.
    """

    def __init__(self, message: str, usage: Usage | None = None) -> None:
        super().__init__(message)
        self.usage = usage or Usage()


@dataclass(frozen=True)
class Usage:
    """The tokens the call cost - read from the stream, never estimated."""

    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class EndpointConfig:
    """Where the endpoint is and how it is called; built once, at the entry point."""

    base_url: str
    token: str = field(repr=False)
    temperature: float = field(default_factory=lambda: settings.load().envelope.temperature)
    max_output_tokens: int = field(default_factory=lambda: settings.load().envelope.max_output_tokens)
    timeout_s: int = field(default_factory=lambda: settings.load().envelope.timeout_s)
    scaffold: str = field(default_factory=lambda: settings.load().transport.direct_scaffold)

    def __post_init__(self) -> None:
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError(f"the endpoint must be an http(s) URL, got {self.base_url!r}")


@dataclass(frozen=True)
class RequestVariant:
    """The knobs a call carries - the envelope, the model and the harness."""

    model: str
    temperature: float
    max_output_tokens: int
    timeout_s: int
    scaffold: str

    def as_dict(self) -> dict[str, object]:
        """The knobs actually sent - the ledger row's ``request``."""
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "timeout_s": self.timeout_s,
            "scaffold": self.scaffold,
        }


@dataclass(frozen=True)
class Answer:
    """What the model produced."""

    text: str
    usage: Usage
    latency_s: float
    variant: RequestVariant


@dataclass(frozen=True)
class Deferral:
    """Why the call produced no answer - a transport fact, never a model's failure.

    The usage is what the stream had reported when it failed: a cut-off answer still spent its
    whole output cap, and that spend belongs in the cost record.
    """

    reason: str
    latency_s: float
    variant: RequestVariant
    usage: Usage = Usage()


#: What a call returns: an answer the model produced, or a deferral.
type Completion = Answer | Deferral


class Channel(Protocol):
    """What ``runner`` needs from a way of reaching a model."""

    @property
    def endpoint(self) -> str:
        """Where the channel sends - the ledger row's ``endpoint``."""
        ...

    def variant(self, model: str) -> RequestVariant:
        """The request variant for ``model`` - the knobs this channel sends."""
        ...

    def complete(self, model: str, system: str, user: str) -> Completion:
        """One completion: an ``Answer`` when the model answered, a ``Deferral`` when it could not."""
        ...


def _error_detail(exc: urllib.error.HTTPError) -> str:
    """The start of an HTTP error's body - best effort, a broken body is just empty."""
    with contextlib.suppress(OSError, http.client.HTTPException):
        return exc.read().decode("utf-8", errors="replace")[: settings.load().transport.error_detail_chars]
    return ""


def _open(opener: Opener, request: urllib.request.Request, timeout_s: float) -> http.client.HTTPResponse:
    """Open a request, mapping every failure to open it onto a ``TransportError``."""
    try:
        return opener(request, timeout_s)
    except urllib.error.HTTPError as exc:
        raise TransportError(f"the endpoint answered HTTP {exc.code}: {_error_detail(exc)}") from exc
    except urllib.error.URLError as exc:
        raise TransportError(f"the endpoint could not be reached: {exc.reason}") from exc
    except (OSError, http.client.HTTPException) as exc:
        raise TransportError(f"the endpoint call failed: {exc!r}") from exc


def served_models(config: EndpointConfig, opener: Opener = urlopen_opener) -> list[str]:
    """The model ids the endpoint serves, asked rather than assumed.

    Raises:
        TransportError: the endpoint could not be asked or did not answer with a model list.
    """
    request = urllib.request.Request(  # noqa: S310 - the scheme is checked in EndpointConfig
        config.base_url + settings.load().transport.models_path,
        headers={"Authorization": f"Bearer {config.token}", "Accept": "application/json"},
    )
    try:
        with _open(opener, request, settings.load().transport.models_timeout_s) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
    except (OSError, http.client.HTTPException, ValueError) as exc:
        raise TransportError(f"the endpoint's model list could not be read: {exc!r}") from exc
    entries = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise TransportError("the endpoint's model list is not an object with a data array")
    return sorted(str(entry["id"]) for entry in entries if isinstance(entry, dict) and entry.get("id"))


def _data_of(raw_line: bytes) -> str | None:
    """The payload of one SSE line - ``None`` when the line carries no payload."""
    line = raw_line.decode("utf-8", errors="replace").strip()
    if not line.startswith("data:"):
        return None
    return line[len("data:") :].strip() or None


def _chunk_of(data: str) -> dict[str, object]:
    """One SSE payload as a chunk."""
    try:
        chunk = json.loads(data)
    except json.JSONDecodeError as exc:
        raise TransportError(f"the stream carried a malformed chunk: {exc}") from exc
    if not isinstance(chunk, dict):
        raise TransportError("the stream carried a chunk that is not an object")
    return chunk


def _usage_of(payload: object) -> Usage:
    """The usage a chunk reports."""
    if not isinstance(payload, dict):
        return Usage()
    return Usage(
        prompt_tokens=int(payload.get("prompt_tokens") or 0),
        completion_tokens=int(payload.get("completion_tokens") or 0),
    )


class _StreamReader:
    """Accumulates the chunks of one stream: the text, the finish reason and the usage."""

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.finish_reason: str | None = None
        self.usage = Usage()
        self.saw_chunk = False

    def feed(self, chunk: dict[str, object]) -> None:
        """Take one chunk in."""
        self.saw_chunk = True
        if chunk.get("error"):
            detail = json.dumps(chunk["error"])[: settings.load().transport.error_detail_chars]
            raise TransportError(f"the stream returned an error: {detail}", self.usage)
        choices = chunk.get("choices") or []
        choice = choices[0] if choices and isinstance(choices[0], dict) else None
        if choice is not None:
            delta = choice.get("delta") or {}
            if delta.get("content"):
                self.parts.append(delta["content"])
            if choice.get("finish_reason"):
                self.finish_reason = choice["finish_reason"]
        if chunk.get("usage"):
            self.usage = _usage_of(chunk["usage"])

    def text(self, max_output_tokens: int) -> str:
        """The answer, once the stream is over - raises when the stream gave none."""
        if not self.saw_chunk:
            raise TransportError("the stream ended with no chunk", self.usage)
        if self.finish_reason == "length":
            raise TransportError(f"the answer was cut off by the {max_output_tokens}-token cap", self.usage)
        text = "".join(self.parts).strip()
        if not text:
            raise TransportError("the endpoint returned an empty answer", self.usage)
        return text


class EndpointChannel:
    """One pinned, streamed completion call against an OpenAI-compatible endpoint."""

    def __init__(self, config: EndpointConfig, opener: Opener = urlopen_opener) -> None:
        self._config = config
        self._opener = opener

    @property
    def endpoint(self) -> str:
        """The full URL of the chat completion - the ledger row's ``endpoint``."""
        return self._config.base_url + settings.load().transport.completions_path

    def variant(self, model: str) -> RequestVariant:
        """The request variant for ``model`` - the knobs this channel sends."""
        return RequestVariant(
            model=model,
            temperature=self._config.temperature,
            max_output_tokens=self._config.max_output_tokens,
            timeout_s=self._config.timeout_s,
            scaffold=self._config.scaffold,
        )

    def complete(self, model: str, system: str, user: str) -> Completion:
        """One completion: an ``Answer`` when the model answered, a ``Deferral`` when it could not.

        Every transport failure - an HTTP error, a timeout, a broken or truncated stream, an
        empty or cut-off answer - is a deferral. Only an answer the model produced is an answer.
        """
        variant = self.variant(model)
        started = time.monotonic()
        try:
            text, usage = self._stream(model, system, user, variant)
        except TransportError as exc:
            return Deferral(reason=str(exc), latency_s=time.monotonic() - started, variant=variant, usage=exc.usage)
        return Answer(text=text, usage=usage, latency_s=time.monotonic() - started, variant=variant)

    def _request(self, model: str, system: str, user: str, variant: RequestVariant) -> urllib.request.Request:
        """The request - the pinned envelope, written out in full."""
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": variant.temperature,
            "max_tokens": variant.max_output_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        return urllib.request.Request(  # noqa: S310 - the scheme is checked in EndpointConfig
            self.endpoint,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._config.token}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
        )

    def _stream(self, model: str, system: str, user: str, variant: RequestVariant) -> tuple[str, Usage]:
        """Read the answer off the stream, with the usage it reports."""
        started = time.monotonic()
        response = _open(self._opener, self._request(model, system, user, variant), variant.timeout_s)
        reader = _StreamReader()
        try:
            with response:
                for raw_line in response:
                    if time.monotonic() - started > variant.timeout_s:
                        raise TransportError(f"the stream outlasted its {variant.timeout_s}s limit", reader.usage)
                    data = _data_of(raw_line)
                    if data is None:
                        continue
                    if data == settings.load().transport.done_sentinel:
                        break
                    reader.feed(_chunk_of(data))
        except TransportError as exc:
            exc.usage = reader.usage if not (exc.usage.prompt_tokens or exc.usage.completion_tokens) else exc.usage
            raise
        except (OSError, http.client.HTTPException) as exc:
            raise TransportError(f"the stream broke: {exc!r}", reader.usage) from exc
        return reader.text(variant.max_output_tokens), reader.usage
