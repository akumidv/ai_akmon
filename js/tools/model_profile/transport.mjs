/**
 * One completion call — pinned, streamed, and never a model's fault. The JavaScript twin of
 * `tools/model_profile/transport.py` (ADR 0020 D01); the Python module is the reference.
 *
 * - **The envelope is pinned.** The temperature is 0 and the output-token cap is explicit; the knobs
 *   actually sent travel with the answer as the ledger row's `request` field.
 * - **The call streams.** The answer is read as a server-sent-event stream with
 *   `stream_options.include_usage` — the usage is captured, not guessed.
 * - **A transport failure is a deferral, never a wrong answer.** An empty answer, a cut-off answer
 *   (`finish_reason: length`), a timeout, an HTTP error, a dropped or truncated stream are all
 *   deferrals: counted on their own line and never scored as a miss.
 *
 * A channel is anything with `endpoint`, `variant(model)` and an async `complete(model, system,
 * user)`; `runner` knows nothing else. Only `EndpointChannel` exists today: an OpenAI-compatible
 * chat-completions endpoint, reached with `fetch`.
 *
 * Twin note: the Python twin applies the per-call timeout to each socket operation and checks the
 * wall clock between stream lines; this one puts one deadline (`AbortSignal.timeout`) on the whole
 * call, connect and body included.
 *
 * The bearer token lives in a non-enumerable property, out of every representation, and no message
 * raised here quotes it.
 */

import { codePointSort } from "../../common/sort.mjs";
import * as settings from "./settings.mjs";

/** The call produced no answer — the reason names what went wrong; the usage the stream had reported travels along. */
export class TransportError extends Error {
  /**
   * @param {string} message
   * @param {Usage} [usage]
   */
  constructor(message, usage = noUsage()) {
    super(message);
    this.name = "TransportError";
    this.usage = usage;
  }
}

/** The run was interrupted by the owner — not a transport failure, so it is not a deferral. */
export class InterruptedError extends Error {
  constructor() {
    super("the run was interrupted");
    this.name = "InterruptedError";
  }
}

/**
 * The tokens the call cost — read from the stream, never estimated.
 * @typedef {object} Usage
 * @property {number} promptTokens
 * @property {number} completionTokens
 */

/**
 * Where the endpoint is and how it is called; built once, at the entry point. The `token`
 * property is not enumerable.
 * @typedef {object} EndpointConfig
 * @property {string} baseUrl
 * @property {string} token
 * @property {number} temperature
 * @property {number} maxOutputTokens
 * @property {number} timeoutS
 * @property {string} scaffold
 */

/**
 * The knobs a call carries — the envelope, the model and the harness.
 * @typedef {object} RequestVariant
 * @property {string} model
 * @property {number} temperature
 * @property {number} maxOutputTokens
 * @property {number} timeoutS
 * @property {string} scaffold
 */

/**
 * What the model produced.
 * @typedef {object} Answer
 * @property {"answer"} kind
 * @property {string} text
 * @property {Usage} usage
 * @property {number} latencyS
 * @property {RequestVariant} variant
 */

/**
 * Why the call produced no answer — a transport fact, never a model's failure.
 * @typedef {object} Deferral
 * @property {"deferral"} kind
 * @property {string} reason
 * @property {number} latencyS
 * @property {RequestVariant} variant
 * @property {Usage} usage
 */

/**
 * What a call returns: an answer the model produced, or a deferral.
 * @typedef {Answer | Deferral} Completion
 */

/**
 * What `runner` needs from a way of reaching a model.
 * @typedef {object} Channel
 * @property {string} endpoint where the channel sends — the ledger row's `endpoint`
 * @property {(model: string) => RequestVariant} variant
 * @property {(model: string, system: string, user: string) => Promise<Completion>} complete
 */

/**
 * What opens a request: a URL, the request options and a deadline in, a response out.
 * @typedef {(url: string, init: RequestInit, timeoutS: number) => Promise<Response>} Opener
 */

/** @returns {Usage} */
function noUsage() {
  return { promptTokens: 0, completionTokens: 0 };
}

/**
 * Build an endpoint configuration, checking the scheme.
 * @param {string} baseUrl
 * @param {string} token
 * @param {Partial<Omit<EndpointConfig, "baseUrl" | "token">>} [overrides]
 * @returns {EndpointConfig}
 */
export function makeEndpointConfig(baseUrl, token, overrides = {}) {
  if (!baseUrl.startsWith("http://") && !baseUrl.startsWith("https://")) {
    throw new TypeError(`the endpoint must be an http(s) URL, got '${baseUrl}'`);
  }
  const envelope = settings.load().envelope;
  const config = {
    baseUrl,
    temperature: envelope.temperature,
    maxOutputTokens: envelope.maxOutputTokens,
    timeoutS: envelope.timeoutS,
    scaffold: settings.load().transport.directScaffold,
    ...overrides,
  };
  Object.defineProperty(config, "token", { value: token, enumerable: false });
  return /** @type {EndpointConfig} */ (config);
}

/**
 * The knobs actually sent — the ledger row's `request`, with the keys the Python twin writes.
 * @param {RequestVariant} variant
 * @returns {Record<string, unknown>}
 */
export function variantRecord(variant) {
  return {
    model: variant.model,
    temperature: variant.temperature,
    max_output_tokens: variant.maxOutputTokens,
    timeout_s: variant.timeoutS,
    scaffold: variant.scaffold,
  };
}

/**
 * The standard opener: `fetch`, under one deadline (and the owner's interrupt, when given).
 * @param {AbortSignal | null} [interrupt]
 * @returns {Opener}
 */
export function fetchOpener(interrupt = null) {
  return (url, init, timeoutS) => {
    const deadline = AbortSignal.timeout(timeoutS * 1000);
    const signal = interrupt === null ? deadline : AbortSignal.any([deadline, interrupt]);
    return fetch(url, { ...init, signal });
  };
}

/**
 * The start of an HTTP error's body — best effort, a broken body is just empty.
 * @param {Response} response
 * @returns {Promise<string>}
 */
async function errorDetail(response) {
  try {
    return (await response.text()).slice(0, settings.load().transport.errorDetailChars);
  } catch {
    return "";
  }
}

/**
 * Open a request, mapping every failure to open it onto a `TransportError`.
 * @param {Opener} opener
 * @param {string} url
 * @param {RequestInit} init
 * @param {number} timeoutS
 * @returns {Promise<Response>}
 */
async function open(opener, url, init, timeoutS) {
  let response;
  try {
    response = await opener(url, init, timeoutS);
  } catch (exc) {
    const error = /** @type {Error & {cause?: Error}} */ (exc);
    throw new TransportError(`the endpoint could not be reached: ${error.cause?.message ?? error.message}`);
  }
  if (!response.ok) {
    throw new TransportError(`the endpoint answered HTTP ${response.status}: ${await errorDetail(response)}`);
  }
  return response;
}

/**
 * The model ids the endpoint serves, asked rather than assumed.
 * @param {EndpointConfig} config
 * @param {Opener} [opener]
 * @returns {Promise<string[]>}
 * @throws {TransportError} the endpoint could not be asked or did not answer with a model list
 */
export async function servedModels(config, opener = fetchOpener()) {
  const init = { headers: { Authorization: `Bearer ${config.token}`, Accept: "application/json" } };
  const timeoutS = settings.load().transport.modelsTimeoutS;
  let payload;
  try {
    const response = await open(opener, config.baseUrl + settings.load().transport.modelsPath, init, timeoutS);
    payload = JSON.parse((await response.text()) || "{}");
  } catch (exc) {
    if (exc instanceof TransportError) {
      throw exc;
    }
    throw new TransportError(`the endpoint's model list could not be read: ${/** @type {Error} */ (exc).message}`);
  }
  const entries = payload !== null && typeof payload === "object" ? payload.data : undefined;
  if (!Array.isArray(entries)) {
    throw new TransportError("the endpoint's model list is not an object with a data array");
  }
  return codePointSort(
    entries
      .filter((entry) => entry !== null && typeof entry === "object" && !Array.isArray(entry) && entry.id)
      .map((entry) => String(entry.id)),
  );
}

/**
 * The payload of one SSE line — `null` when the line carries no payload.
 * @param {string} rawLine
 * @returns {string | null}
 */
export function dataOf(rawLine) {
  const line = rawLine.trim();
  if (!line.startsWith("data:")) {
    return null;
  }
  return line.slice("data:".length).trim() || null;
}

/**
 * One SSE payload as a chunk.
 * @param {string} data
 * @returns {Record<string, any>}
 */
function chunkOf(data) {
  let chunk;
  try {
    chunk = JSON.parse(data);
  } catch (exc) {
    throw new TransportError(`the stream carried a malformed chunk: ${/** @type {Error} */ (exc).message}`);
  }
  if (chunk === null || typeof chunk !== "object" || Array.isArray(chunk)) {
    throw new TransportError("the stream carried a chunk that is not an object");
  }
  return chunk;
}

/**
 * The usage a chunk reports.
 * @param {any} payload
 * @returns {Usage}
 */
function usageOf(payload) {
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
    return noUsage();
  }
  return {
    promptTokens: Math.trunc(Number(payload.prompt_tokens) || 0),
    completionTokens: Math.trunc(Number(payload.completion_tokens) || 0),
  };
}

/** Accumulates the chunks of one stream: the text, the finish reason and the usage. */
export class StreamReader {
  constructor() {
    /** @type {string[]} */
    this.parts = [];
    /** @type {string | null} */
    this.finishReason = null;
    /** @type {Usage} */
    this.usage = noUsage();
    this.sawChunk = false;
  }

  /**
   * Take one chunk in.
   * @param {Record<string, any>} chunk
   */
  feed(chunk) {
    this.sawChunk = true;
    if (chunk.error) {
      const detail = JSON.stringify(chunk.error).slice(0, settings.load().transport.errorDetailChars);
      throw new TransportError(`the stream returned an error: ${detail}`, this.usage);
    }
    const choices = Array.isArray(chunk.choices) ? chunk.choices : [];
    if (choices.length > 0 && choices[0] !== null && typeof choices[0] === "object") {
      this._takeChoice(choices[0]);
    }
    if (chunk.usage) {
      this.usage = usageOf(chunk.usage);
    }
  }

  /**
   * Take the first choice of a chunk in: its text and its finish reason.
   * @param {Record<string, any>} choice
   */
  _takeChoice(choice) {
    const content = (choice.delta ?? {}).content;
    if (typeof content === "string" && content !== "") {
      this.parts.push(content);
    }
    if (choice.finish_reason) {
      this.finishReason = choice.finish_reason;
    }
  }

  /**
   * The answer, once the stream is over — throws when the stream gave none.
   * @param {number} maxOutputTokens
   * @returns {string}
   */
  text(maxOutputTokens) {
    if (!this.sawChunk) {
      throw new TransportError("the stream ended with no chunk", this.usage);
    }
    if (this.finishReason === "length") {
      throw new TransportError(`the answer was cut off by the ${maxOutputTokens}-token cap`, this.usage);
    }
    const text = this.parts.join("").trim();
    if (text === "") {
      throw new TransportError("the endpoint returned an empty answer", this.usage);
    }
    return text;
  }
}

/**
 * The lines of a response body, as they arrive; a final line with no newline is yielded too.
 * @param {Response} response
 * @returns {AsyncGenerator<string>}
 */
async function* linesOf(response) {
  if (response.body === null) {
    return;
  }
  const decoder = new TextDecoder("utf-8");
  let pending = "";
  for await (const piece of /** @type {AsyncIterable<Uint8Array>} */ (/** @type {unknown} */ (response.body))) {
    pending += decoder.decode(piece, { stream: true });
    let newline = pending.indexOf("\n");
    while (newline !== -1) {
      yield pending.slice(0, newline + 1);
      pending = pending.slice(newline + 1);
      newline = pending.indexOf("\n");
    }
  }
  pending += decoder.decode();
  if (pending !== "") {
    yield pending;
  }
}

/** One pinned, streamed completion call against an OpenAI-compatible endpoint. */
export class EndpointChannel {
  /**
   * @param {EndpointConfig} config
   * @param {{opener?: Opener, interrupt?: AbortSignal | null}} [options] `interrupt` is the owner's Ctrl-C
   */
  constructor(config, { opener, interrupt = null } = {}) {
    this._config = config;
    this._interrupt = interrupt;
    this._opener = opener ?? fetchOpener(interrupt);
  }

  /** The full URL of the chat completion — the ledger row's `endpoint`. */
  get endpoint() {
    return this._config.baseUrl + settings.load().transport.completionsPath;
  }

  /**
   * The request variant for `model` — the knobs this channel sends.
   * @param {string} model
   * @returns {RequestVariant}
   */
  variant(model) {
    return {
      model,
      temperature: this._config.temperature,
      maxOutputTokens: this._config.maxOutputTokens,
      timeoutS: this._config.timeoutS,
      scaffold: this._config.scaffold,
    };
  }

  /**
   * One completion: an answer when the model answered, a deferral when it could not. Every transport
   * failure — an HTTP error, a timeout, a broken or truncated stream, an empty or cut-off answer —
   * is a deferral.
   * @param {string} model
   * @param {string} system
   * @param {string} user
   * @returns {Promise<Completion>}
   * @throws {InterruptedError} the owner interrupted the run during the call
   */
  async complete(model, system, user) {
    const variant = this.variant(model);
    const started = performance.now();
    try {
      const [text, usage] = await this._stream(model, system, user, variant);
      return { kind: "answer", text, usage, latencyS: (performance.now() - started) / 1000, variant };
    } catch (exc) {
      if (this._interrupt?.aborted) {
        throw new InterruptedError();
      }
      if (!(exc instanceof TransportError)) {
        throw exc;
      }
      return {
        kind: "deferral",
        reason: exc.message,
        latencyS: (performance.now() - started) / 1000,
        variant,
        usage: exc.usage,
      };
    }
  }

  /**
   * The request — the pinned envelope, written out in full.
   * @param {string} model
   * @param {string} system
   * @param {string} user
   * @param {RequestVariant} variant
   * @returns {RequestInit}
   */
  _request(model, system, user, variant) {
    const body = {
      model,
      messages: [
        { role: "system", content: system },
        { role: "user", content: user },
      ],
      temperature: variant.temperature,
      max_tokens: variant.maxOutputTokens,
      stream: true,
      stream_options: { include_usage: true },
    };
    return {
      method: "POST",
      body: JSON.stringify(body),
      headers: {
        Authorization: `Bearer ${this._config.token}`,
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
    };
  }

  /**
   * Read the answer off the stream, with the usage it reports.
   * @param {string} model
   * @param {string} system
   * @param {string} user
   * @param {RequestVariant} variant
   * @returns {Promise<[string, Usage]>}
   */
  async _stream(model, system, user, variant) {
    const response = await open(
      this._opener,
      this.endpoint,
      this._request(model, system, user, variant),
      variant.timeoutS,
    );
    const reader = new StreamReader();
    try {
      for await (const rawLine of linesOf(response)) {
        const data = dataOf(rawLine);
        if (data === null) {
          continue;
        }
        if (data === settings.load().transport.doneSentinel) {
          break;
        }
        reader.feed(chunkOf(data));
      }
    } catch (exc) {
      throw streamFailure(exc, reader, variant);
    }
    return [reader.text(variant.maxOutputTokens), reader.usage];
  }
}

/**
 * The `TransportError` a failed stream becomes, carrying the usage the stream had reported.
 * @param {unknown} exc
 * @param {StreamReader} reader
 * @param {RequestVariant} variant
 * @returns {TransportError}
 */
function streamFailure(exc, reader, variant) {
  if (exc instanceof TransportError) {
    if (exc.usage.promptTokens === 0 && exc.usage.completionTokens === 0) {
      exc.usage = reader.usage;
    }
    return exc;
  }
  const error = /** @type {Error} */ (exc);
  if (error.name === "TimeoutError") {
    return new TransportError(`the stream outlasted its ${variant.timeoutS}s limit`, reader.usage);
  }
  return new TransportError(`the stream broke: ${error.message}`, reader.usage);
}
