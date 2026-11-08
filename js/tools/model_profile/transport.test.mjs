import { test } from "node:test";
import assert from "node:assert/strict";

import { EndpointChannel, dataOf, fetchOpener, makeEndpointConfig, servedModels, variantRecord } from "./transport.mjs";
import { StubChannel, makeAnswer } from "./support.test.mjs";

/**
 * A response that yields the given SSE lines, then optionally fails — the socket is never opened.
 * @param {string[]} lines
 * @param {Error} [failure]
 * @returns {Response}
 */
function streamResponse(lines, failure) {
  const encoder = new TextEncoder();
  let next = 0;
  const body = new ReadableStream({
    pull(controller) {
      if (next < lines.length) {
        controller.enqueue(encoder.encode(lines[next++]));
      } else if (failure) {
        controller.error(failure);
      } else {
        controller.close();
      }
    },
  });
  return new Response(body, { status: 200 });
}

/** @param {Record<string, unknown>} payload */
const sse = (payload) => `data: ${JSON.stringify(payload)}\n`;

/** @param {import("./transport.mjs").Opener} opener */
const channelOf = (opener) =>
  new EndpointChannel(makeEndpointConfig("https://endpoint.example", "fixture-token"), { opener });

const PARTIAL = [sse({ choices: [{ delta: { content: "partial answer" } }] })];

test("the cut-off path reports the usage it read", async () => {
  const lines = [
    ...PARTIAL,
    sse({ choices: [{ delta: {}, finish_reason: "length" }] }),
    sse({ choices: [], usage: { prompt_tokens: 1200, completion_tokens: 4096 } }),
  ];

  const completion = await channelOf(async () => streamResponse(lines)).complete("probe-model", "system", "user");

  assert.equal(completion.kind, "deferral");
  assert.deepEqual(completion.kind === "deferral" && completion.usage, { promptTokens: 1200, completionTokens: 4096 });
  assert.match(completion.kind === "deferral" ? completion.reason : "", /cut off/);
});

test("a complete stream is an answer with its usage", async () => {
  const lines = [
    ...PARTIAL,
    sse({ choices: [{ delta: { content: " done" }, finish_reason: "stop" }] }),
    sse({ choices: [], usage: { prompt_tokens: 7, completion_tokens: 3 } }),
    "data: [DONE]\n",
  ];

  const completion = await channelOf(async () => streamResponse(lines)).complete("m", "s", "u");

  assert.equal(completion.kind, "answer");
  assert.equal(completion.kind === "answer" && completion.text, "partial answer done");
  assert.deepEqual(completion.kind === "answer" && completion.usage, { promptTokens: 7, completionTokens: 3 });
});

test("a line split across chunks and a final line with no newline are read whole", async () => {
  const text = `${sse({ choices: [{ delta: { content: "ab" } }] })}${sse({ choices: [{ delta: { content: "cd" }, finish_reason: "stop" }] })}`;
  const middle = Math.floor(text.length / 2);

  const completion = await channelOf(async () =>
    streamResponse([text.slice(0, middle), text.slice(middle).trimEnd()]),
  ).complete("m", "s", "u");

  assert.equal(completion.kind === "answer" && completion.text, "abcd");
});

test("the request pins the envelope and streams", async () => {
  /** @type {{url?: string, init?: RequestInit, timeoutS?: number}} */
  const seen = {};

  await channelOf(async (url, init, timeoutS) => {
    Object.assign(seen, { url, init, timeoutS });
    return streamResponse([...PARTIAL, sse({ choices: [{ delta: {}, finish_reason: "stop" }] })]);
  }).complete("probe-model", "sys", "usr");

  assert.equal(seen.url, "https://endpoint.example/v1/chat/completions");
  assert.equal(seen.timeoutS, 180);
  assert.deepEqual(JSON.parse(String(seen.init?.body)), {
    model: "probe-model",
    messages: [
      { role: "system", content: "sys" },
      { role: "user", content: "usr" },
    ],
    temperature: 0,
    max_tokens: 4096,
    stream: true,
    stream_options: { include_usage: true },
  });
  const headers = /** @type {Record<string, string>} */ (seen.init?.headers);
  assert.equal(headers.Authorization, "Bearer fixture-token");
  assert.equal(headers.Accept, "text/event-stream");
});

/** @type {[string, Error][]} */
const BREAKS = [
  ["a reset", Object.assign(new Error("reset by peer"), { code: "ECONNRESET" })],
  ["a truncated body", new TypeError("terminated")],
  ["an io error", new Error("network is unreachable")],
];

for (const [name, failure] of BREAKS) {
  test(`a stream that breaks midway is a deferral that keeps the usage read: ${name}`, async () => {
    const lines = [...PARTIAL, sse({ choices: [], usage: { prompt_tokens: 50, completion_tokens: 8 } })];

    const completion = await channelOf(async () => streamResponse(lines, failure)).complete("m", "s", "u");

    assert.equal(completion.kind, "deferral");
    assert.ok(
      completion.kind === "deferral" && completion.reason.startsWith("the stream broke"),
      JSON.stringify(completion),
    );
    assert.deepEqual(completion.kind === "deferral" && completion.usage, { promptTokens: 50, completionTokens: 8 });
  });
}

test("a call that cannot be opened is a deferral", async () => {
  const refused = Object.assign(new TypeError("fetch failed"), { cause: new Error("connect ECONNREFUSED") });

  const completion = await channelOf(async () => {
    throw refused;
  }).complete("m", "s", "u");

  assert.equal(completion.kind, "deferral");
  assert.match(completion.kind === "deferral" ? completion.reason : "", /could not be reached: connect ECONNREFUSED/);
  assert.deepEqual(completion.kind === "deferral" && completion.usage, { promptTokens: 0, completionTokens: 0 });
});

test("an HTTP error is a deferral naming the status but never the token", async () => {
  const completion = await channelOf(async () => new Response("upstream timed out", { status: 524 })).complete(
    "m",
    "s",
    "u",
  );

  assert.equal(completion.kind, "deferral");
  const reason = completion.kind === "deferral" ? completion.reason : "";
  assert.ok(reason.includes("HTTP 524"));
  assert.ok(reason.includes("upstream timed out"));
  assert.ok(!reason.includes("fixture-token"));
});

/** @type {[string, string[], string][]} */
const BROKEN_STREAMS = [
  ["no chunk", [], "no chunk"],
  ["an empty answer", [sse({ choices: [{ delta: { content: "  " }, finish_reason: "stop" }] })], "empty answer"],
  ["a non-text content only", [sse({ choices: [{ delta: { content: 7 }, finish_reason: "stop" }] })], "empty answer"],
  ["a malformed chunk", ["data: {not json\n"], "malformed chunk"],
  ["an error chunk", [sse({ error: { message: "overloaded" } })], "returned an error"],
];

for (const [name, lines, reason] of BROKEN_STREAMS) {
  test(`an empty or broken stream is a deferral: ${name}`, async () => {
    const completion = await channelOf(async () => streamResponse(lines)).complete("m", "s", "u");

    assert.equal(completion.kind, "deferral");
    assert.ok(completion.kind === "deferral" && completion.reason.includes(reason), JSON.stringify(completion));
  });
}

test("a stream that outlasts its limit is a deferral", async () => {
  const deadline = new DOMException("The operation was aborted due to timeout", "TimeoutError");

  const completion = await channelOf(async () => streamResponse(PARTIAL, deadline)).complete("m", "s", "u");

  assert.equal(completion.kind, "deferral");
  assert.match(completion.kind === "deferral" ? completion.reason : "", /outlasted its 180s limit/);
});

test("the real opener ends a call that outlives its deadline", async () => {
  const { createServer } = await import("node:http");
  const server = createServer((_request, response) => {
    response.writeHead(200, { "Content-Type": "text/event-stream" });
    response.write(PARTIAL[0]);
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(undefined)));
  try {
    const { port } = /** @type {import("node:net").AddressInfo} */ (server.address());
    const config = makeEndpointConfig(`http://127.0.0.1:${port}`, "t", { timeoutS: 0.2 });

    const completion = await new EndpointChannel(config, { opener: fetchOpener() }).complete("m", "s", "u");

    assert.equal(completion.kind, "deferral");
    assert.match(completion.kind === "deferral" ? completion.reason : "", /outlasted its 0.2s limit/);
  } finally {
    server.closeAllConnections();
    server.close();
  }
});

test("the token stays out of every representation", () => {
  const config = makeEndpointConfig("https://endpoint.example", "fixture-token");

  assert.ok(!JSON.stringify(config).includes("fixture-token"));
  assert.ok(!JSON.stringify({ ...config }).includes("fixture-token"));
  assert.ok(!Object.keys(config).includes("token"));
  assert.ok(!String(Object.entries(config)).includes("fixture-token"));
});

test("an endpoint that is not http is refused", () => {
  assert.throws(() => makeEndpointConfig("file:///etc/passwd", "t"), /http/);
});

test("served models lists the ids the endpoint reports", async () => {
  const body = JSON.stringify({ data: [{ id: "b-model" }, { id: "a-model" }, { object: "no id" }] });
  /** @type {Record<string, unknown>} */
  const seen = {};

  const models = await servedModels(makeEndpointConfig("https://endpoint.example", "t"), async (url, init) => {
    Object.assign(seen, { url, auth: /** @type {Record<string, string>} */ (init.headers).Authorization });
    return new Response(body);
  });

  assert.deepEqual(models, ["a-model", "b-model"]);
  assert.deepEqual(seen, { url: "https://endpoint.example/v1/models", auth: "Bearer t" });
});

test("served models throws a transport error when the endpoint is down or answers wrongly", async () => {
  const config = makeEndpointConfig("https://endpoint.example", "t");

  await assert.rejects(
    servedModels(config, async () => {
      throw new TypeError("fetch failed");
    }),
    { name: "TransportError" },
  );
  await assert.rejects(
    servedModels(config, async () => new Response("{}")),
    /not an object with a data array/,
  );
  await assert.rejects(
    servedModels(config, async () => new Response("<html>")),
    { name: "TransportError" },
  );
});

test("the channel interface is all the runner needs", () => {
  const channel = new StubChannel(() => makeAnswer("pkg/mod.py:compute"));

  assert.ok(channel.endpoint.endsWith("/chat/completions"));
  assert.equal(channel.variant("m").model, "m");
});

test("the variant record carries the keys the ledger row's request has", () => {
  const channel = channelOf(async () => streamResponse([]));

  assert.deepEqual(variantRecord(channel.variant("m")), {
    model: "m",
    temperature: 0,
    max_output_tokens: 4096,
    timeout_s: 180,
    scaffold: "direct",
  });
});

test("an SSE line carries a payload only after data:", () => {
  assert.equal(dataOf("data: {}\n"), "{}");
  assert.equal(dataOf(": keep-alive\n"), null);
  assert.equal(dataOf("data:\n"), null);
  assert.equal(dataOf("event: ping\n"), null);
});
