// Tests for the Cloudflare Worker connector. Run: node --test tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const WORKER_PATH = path.join(ROOT, "connector", "worker", "worker.js");

// The deployed file only has a default export (Cloudflare rejects non-class named
// exports). For tests, expose the internals by appending named exports to a copy.
const source = readFileSync(WORKER_PATH, "utf8");
const testCopy = path.join(mkdtempSync(path.join(tmpdir(), "sac-")), "worker.test.mjs");
writeFileSync(testCopy, source + "\nexport { DATA, handleMessage, handleRequest, callTool, normalizeSlug };\n");
const worker = await import(pathToFileURL(testCopy).href);
const { DATA, handleMessage } = worker;

const BASE = "https://sac.example.workers.dev";
const post = (body, pathname = "/mcp") =>
  worker.default.fetch(new Request(BASE + pathname, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json, text/event-stream" },
    body: typeof body === "string" ? body : JSON.stringify(body),
  }));

test("deployed file has only a default export", () => {
  const exportLines = source.split("\n").filter((line) => /^export\b/.test(line));
  assert.deepEqual(exportLines, ["export default {"]);
});

test("initialize over HTTP echoes protocol version", async () => {
  const response = await post({ jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2025-06-18" } });
  assert.equal(response.status, 200);
  assert.match(response.headers.get("Content-Type"), /application\/json/);
  const body = await response.json();
  assert.equal(body.result.protocolVersion, "2025-06-18");
  assert.equal(body.result.serverInfo.name, "share-a-clicky");
});

test("notification returns 202 with no body", async () => {
  const response = await post({ jsonrpc: "2.0", method: "notifications/initialized" });
  assert.equal(response.status, 202);
  assert.equal(await response.text(), "");
});

test("tools/call get_shared_clicky returns setup plus hand-off rule", async () => {
  const response = await post({ jsonrpc: "2.0", id: 3, method: "tools/call",
    params: { name: "get_shared_clicky", arguments: { slug: "Job Hunter" } } });
  const body = await response.json();
  assert.equal(body.result.isError, false);
  const text = body.result.content[0].text;
  assert.match(text, /Name: Job Hunter/);
  assert.match(text, /Do not try to operate the HeyClicky app/);
});

test("unknown slug is a tool error listing ids", async () => {
  const body = await (await post({ jsonrpc: "2.0", id: 4, method: "tools/call",
    params: { name: "get_shared_clicky", arguments: {} } })).json();
  assert.equal(body.result.isError, true);
  assert.match(body.result.content[0].text, /Available ids: job-hunter/);
});

test("batch returns only request responses", async () => {
  const body = await (await post([
    { jsonrpc: "2.0", id: 1, method: "ping" },
    { jsonrpc: "2.0", method: "notifications/initialized" },
    { jsonrpc: "2.0", id: 2, method: "tools/list" },
  ])).json();
  assert.deepEqual(body.map((r) => r.id), [1, 2]);
});

test("HTTP edge cases from review", async () => {
  assert.equal((await post("null")).status, 400);
  assert.equal((await post("42")).status, 400);
  const clientResponse = await post({ jsonrpc: "2.0", id: 5, result: {} });
  assert.equal(clientResponse.status, 202);
  const multibyte = JSON.stringify({ jsonrpc: "2.0", id: 1, method: "ping", params: { pad: "é".repeat(40 * 1024) } });
  assert.ok(multibyte.length < 64 * 1024 && new TextEncoder().encode(multibyte).length > 64 * 1024);
  assert.equal((await post(multibyte)).status, 413);
  const declaredTooBig = await worker.default.fetch(new Request(BASE + "/mcp", {
    method: "POST", headers: { "Content-Length": String(10 * 1024 * 1024) }, body: "{}" }));
  assert.equal(declaredTooBig.status, 413);
  assert.equal((await post({ jsonrpc: "2.0", id: 1, method: "ping" }, "/mcp/")).status, 200);
  const head = await worker.default.fetch(new Request(BASE + "/", { method: "HEAD" }));
  assert.equal(head.status, 200);
  const unknownTool = await (await post({ jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "nope" } })).json();
  assert.equal(unknownTool.error.code, -32602);
});

test("HTTP edge cases", async () => {
  assert.equal((await post("{not json")).status, 400);
  assert.equal((await post([])).status, 400);
  assert.equal((await post("x".repeat(70 * 1024))).status, 413);
  assert.equal((await post({ jsonrpc: "2.0", id: 1, method: "ping" }, "/other")).status, 404);
  const getMcp = await worker.default.fetch(new Request(BASE + "/mcp"));
  assert.equal(getMcp.status, 405);
  assert.equal(getMcp.headers.get("Allow"), "POST");
  const options = await worker.default.fetch(new Request(BASE + "/mcp", { method: "OPTIONS" }));
  assert.equal(options.status, 204);
  const home = await (await worker.default.fetch(new Request(BASE + "/"))).json();
  assert.equal(home.mcp_endpoint, BASE + "/mcp");
  assert.ok(home.shared_clickys.includes("job-hunter"));
  const unknownMethod = await (await post({ jsonrpc: "2.0", id: 9, method: "resources/list" })).json();
  assert.equal(unknownMethod.error.code, -32601);
});

test("protocol rules from the 2025-06-18 spec", async () => {
  const withVersion = (body, version) => worker.default.fetch(new Request(BASE + "/mcp", {
    method: "POST",
    headers: { "Content-Type": "application/json", "MCP-Protocol-Version": version },
    body: JSON.stringify(body),
  }));
  const bad = await withVersion({ jsonrpc: "2.0", id: 1, method: "ping" }, "1999-01-01");
  assert.equal(bad.status, 400);
  assert.equal((await bad.json()).error.code, -32600);
  assert.equal((await withVersion({ jsonrpc: "2.0", id: 1, method: "ping" }, "2025-06-18")).status, 200);
  const batchNew = await withVersion([{ jsonrpc: "2.0", id: 1, method: "ping" }], "2025-06-18");
  assert.equal(batchNew.status, 400);
  const batchOld = await withVersion([{ jsonrpc: "2.0", id: 1, method: "ping" }], "2025-03-26");
  assert.deepEqual((await batchOld.json()).map((r) => r.id), [1]);
  const nullId = await (await post({ jsonrpc: "2.0", id: null, method: "ping" })).json();
  assert.equal(nullId.error.code, -32600);
  const tools = (await (await post({ jsonrpc: "2.0", id: 2, method: "tools/list" })).json()).result.tools;
  assert.ok(tools.every((t) => t.annotations.readOnlyHint === true && t.annotations.destructiveHint === false));
});

test("oversized body without Content-Length is refused without buffering it all", async () => {
  let pulled = 0;
  const chunk = new Uint8Array(16 * 1024).fill(32);
  const stream = new ReadableStream({
    pull(controller) {
      pulled += chunk.byteLength;
      if (pulled > 50 * 1024 * 1024) controller.close();
      else controller.enqueue(chunk);
    },
  });
  const response = await worker.default.fetch(new Request(BASE + "/mcp", {
    method: "POST", body: stream, duplex: "half", headers: { "Content-Type": "application/json" } }));
  assert.equal(response.status, 413);
  assert.ok(pulled < 1024 * 1024, `read ${pulled} bytes before refusing`);
});

test("Worker and local Python connector give identical answers", () => {
  const messages = [
    { jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2025-03-26" } },
    { jsonrpc: "2.0", id: 2, method: "initialize" },
    { jsonrpc: "2.0", method: "notifications/initialized" },
    { jsonrpc: "2.0", id: 3, method: "tools/list" },
    { jsonrpc: "2.0", id: 4, method: "ping" },
    { jsonrpc: "2.0", id: 5, method: "tools/call", params: { name: "list_shared_clickys", arguments: {} } },
    ...["job-hunter", "Job Hunter", " FOLLOW_UP_KEEPER ", "weekly--wins", "follow\u2011up\u2011keeper", "job\u2013hunter", "", "nope"].map((slug, i) => ({
      jsonrpc: "2.0", id: 10 + i, method: "tools/call", params: { name: "get_shared_clicky", arguments: { slug } } })),
    { jsonrpc: "2.0", id: 20, method: "tools/call", params: { name: "get_shared_clicky" } },
    { jsonrpc: "2.0", id: 21, method: "tools/call", params: { name: "nope", arguments: {} } },
    { jsonrpc: "2.0", id: 22, method: "resources/list" },
    ["not", "an", "object"],
    { jsonrpc: "2.0", id: 23, method: "tools/call", params: {} },
    { jsonrpc: "2.0", id: 24, method: "tools/call", params: { name: "get_shared_clicky", arguments: { slug: ["job-hunter"] } } },
    { jsonrpc: "2.0", id: 25, method: "tools/call", params: { name: "get_shared_clicky", arguments: { slug: 0 } } },
    { jsonrpc: "2.0", id: 26, method: "tools/call", params: { name: "get_shared_clicky", arguments: { slug: true } } },
    { jsonrpc: "2.0", id: 27, method: "initialize", params: { protocolVersion: [] } },
    { jsonrpc: "2.0", id: 28, method: "initialize", params: { protocolVersion: "1999-01-01" } },
    { jsonrpc: "2.0", id: 29, result: {} },
    { jsonrpc: "2.0", id: 30 },
    { jsonrpc: "2.0" },
    { jsonrpc: "2.0", id: 31, method: "tools/call", params: { name: "get_shared_clicky", arguments: "job-hunter" } },
    { jsonrpc: "2.0", id: null, method: "ping" },
    { jsonrpc: "2.0", id: true, method: "ping" },
    { jsonrpc: "2.0", id: { a: 1 }, method: "ping" },
    { jsonrpc: "2.0", id: 1.5, method: "ping" },
    { jsonrpc: "2.0", id: 9007199254740993, method: "ping" },
    { jsonrpc: "2.0", id: -7, method: "ping" },
    { jsonrpc: "2.0", id: "abc", method: "ping" },
    { jsonrpc: "1.0", id: 40, method: "ping" },
    { id: 41, method: "ping" },
    { jsonrpc: "2.0", id: 42, method: "ping", params: [] },
    { jsonrpc: "2.0", id: 43, method: "tools/call", params: "x" },
    { jsonrpc: "2.0", id: 44, method: "tools/call", params: { name: "list_shared_clickys", arguments: null } },
  ];
  const script = `
import json, sys
sys.path.insert(0, ${JSON.stringify(path.join(ROOT, "connector", "local"))})
import share_a_clicky_mcp as m
data = m.load_data()
print(json.dumps([m.handle_message(data, msg) for msg in json.load(sys.stdin)]))
`;
  const pythonResults = JSON.parse(execFileSync("python3", ["-c", script], { input: JSON.stringify(messages), env: { ...process.env, SHARE_A_CLICKY_LOG: "off" } }));
  const workerResults = messages.map((m) => handleMessage(DATA, m));
  assert.deepEqual(workerResults, pythonResults);
});

test("raw input: stdio and HTTP transports answer the same bodies", async () => {
  const raw = [
    "{not json",
    '{"jsonrpc":"2.0","id":NaN,"method":"ping"}',
    "[".repeat(5000) + "]".repeat(5000),
    "null",
    "42",
    "[]",
    JSON.stringify([{ jsonrpc: "2.0", id: 1, method: "ping" }, { jsonrpc: "2.0", method: "notifications/initialized" }]),
    JSON.stringify({ jsonrpc: "2.0", id: "a", method: "ping", params: { pad: "x".repeat(70 * 1024) } }),
    JSON.stringify({ jsonrpc: "2.0", id: null, method: "ping" }),
    JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }),
    JSON.stringify({ jsonrpc: "2.0", id: 7, method: "tools/call", params: { name: "get_shared_clicky", arguments: { slug: "weekly wins" } } }),
  ];
  const script = `
import io, json, sys
sys.path.insert(0, ${JSON.stringify(path.join(ROOT, "connector", "local"))})
import share_a_clicky_mcp as m
data = m.load_data()
results = []
for line in json.load(sys.stdin):
    out = io.StringIO()
    m.serve(io.StringIO(line + "\\n"), out, data)
    text = out.getvalue().strip()
    results.append(json.loads(text) if text else None)
print(json.dumps(results))
`;
  const stdio = JSON.parse(execFileSync("python3", ["-c", script], { input: JSON.stringify(raw), env: { ...process.env, SHARE_A_CLICKY_LOG: "off" } }));
  const http = [];
  for (const body of raw) {
    const response = await post(body);
    http.push(response.status === 202 ? null : await response.json());
  }
  assert.deepEqual(http, stdio);
});
