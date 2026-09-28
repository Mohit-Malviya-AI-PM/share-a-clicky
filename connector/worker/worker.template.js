// Share-a-Clicky remote connector: MCP over Streamable HTTP on Cloudflare Workers.
// Single file, no dependencies, data inlined by build.py.
// Add to HeyClicky: Settings > Integrations > Add custom connector >
//   Server URL: https://<your-worker>.workers.dev/mcp   Authentication: None

const DATA = /*__SHARED_CLICKYS_DATA__*/null;
const SERVER_INFO = { name: "share-a-clicky", version: "0.1.0" };
const SUPPORTED_PROTOCOL_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]; // newest first
const MAX_BODY_BYTES = 64 * 1024;
const MAX_NESTING = 64; // MCP messages are shallow; the Python connector applies the same limit

// Origin policy: this is a public, read-only catalog with no cookies, credentials or user data,
// so any origin may read it (open CORS). The MCP spec's Origin check exists to stop DNS
// rebinding against servers on localhost; the local connector here uses stdio, not HTTP.
const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Accept, Mcp-Session-Id, Mcp-Protocol-Version",
};

function normalizeSlug(rawValue) {
  return String(rawValue ?? "")
    .trim()
    .toLowerCase()
    .replace(/[ _\u2010-\u2015\u2212]/g, "-") // models often type Unicode dashes
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

function findClicky(data, rawValue) {
  const wanted = normalizeSlug(rawValue);
  if (!wanted) return null;
  return data.clickys.find((c) => wanted === c.slug || wanted === normalizeSlug(c.name)) || null;
}

// MCP request ids are strings or integers, never null. Integers beyond 2^53 can't be echoed exactly.
function validRequestId(value) {
  return typeof value === "string" || Number.isSafeInteger(value);
}

// JSON-RPC batching was removed in MCP 2025-06-18; older versions allow it.
function batchAllowed(protocolVersion) {
  return protocolVersion !== "2025-06-18";
}

function nestingDepth(value) {
  let deepest = 0;
  const stack = [[value, 1]];
  while (stack.length) {
    const [node, depth] = stack.pop();
    deepest = Math.max(deepest, depth);
    if (node && typeof node === "object") {
      for (const child of Array.isArray(node) ? node : Object.values(node)) stack.push([child, depth + 1]);
    }
  }
  return deepest;
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function callTool(data, name, args) {
  const safeArgs = isPlainObject(args) ? args : {};
  if (name === "list_shared_clickys") return { text: data.list_text, isError: false };
  const slugText = typeof safeArgs.slug === "string" ? safeArgs.slug : "";
  const clicky = findClicky(data, slugText);
  if (!clicky) {
    const available = data.clickys.map((c) => c.slug).join(", ");
    const asked = slugText.trim() || "(nothing)";
    return { text: `No shared Clicky called '${asked}'. Available ids: ${available}`, isError: true };
  }
  return { text: clicky.connector_response_text, isError: false };
}

function errorResponse(id, code, message) {
  return { jsonrpc: "2.0", id, error: { code, message } };
}

function handleMessage(data, message) {
  if (!isPlainObject(message)) return errorResponse(null, -32600, "Invalid request");
  const method = message.method;
  const hasId = "id" in message;
  const id = hasId ? message.id : null;
  if (typeof method !== "string" || !method) {
    if (hasId && ("result" in message || "error" in message)) return null; // a response from the client
    return errorResponse(id, -32600, "Invalid request: missing method");
  }
  if (!hasId) return null; // notification
  if (!validRequestId(id)) return errorResponse(null, -32600, "Invalid request: id must be a string or an integer");
  if (message.jsonrpc !== "2.0") return errorResponse(id, -32600, 'Invalid request: jsonrpc must be "2.0"');
  if ("params" in message && !isPlainObject(message.params)) {
    return errorResponse(id, -32602, "Invalid params: params must be an object");
  }
  const params = message.params || {};
  let result;
  if (method === "initialize") {
    const requested = params.protocolVersion;
    result = {
      protocolVersion: SUPPORTED_PROTOCOL_VERSIONS.includes(requested) ? requested : SUPPORTED_PROTOCOL_VERSIONS[0],
      capabilities: { tools: { listChanged: false } },
      serverInfo: SERVER_INFO,
      instructions: data.mcp.instructions,
    };
  } else if (method === "ping") {
    result = {};
  } else if (method === "tools/list") {
    result = { tools: data.mcp.tools };
  } else if (method === "tools/call") {
    const name = params.name;
    if (typeof name !== "string" || !name) return errorResponse(id, -32602, "Missing tool name");
    if (!data.mcp.tools.some((tool) => tool.name === name)) return errorResponse(id, -32602, `Unknown tool: ${name}`);
    if ("arguments" in params && !isPlainObject(params.arguments)) {
      return errorResponse(id, -32602, "Invalid params: arguments must be an object");
    }
    const { text, isError } = callTool(data, name, params.arguments);
    result = { content: [{ type: "text", text }], isError };
  } else {
    return errorResponse(id, -32601, `Method not found: ${method}`);
  }
  return { jsonrpc: "2.0", id, result };
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

// Stops reading as soon as the body passes the limit, so a huge upload without a
// Content-Length header can't be buffered into memory. Returns null when too large.
async function readBodyWithLimit(request, limit) {
  if (!request.body) return new Uint8Array(0);
  const reader = request.body.getReader();
  const chunks = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > limit) {
      await reader.cancel().catch(() => {});
      return null;
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes;
}

async function handleRequest(request, data = DATA) {
  const url = new URL(request.url);
  const path = url.pathname.replace(/\/+$/, "") || "/";
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS_HEADERS });

  if (path === "/" && (request.method === "GET" || request.method === "HEAD")) {
    const response = jsonResponse({
      name: "Share-a-Clicky connector (unofficial prototype, not affiliated with HeyClicky)",
      mcp_endpoint: `${url.origin}/mcp`,
      how_to_add: "HeyClicky > Settings > Integrations > Add custom connector > Server URL, Authentication: None",
      shared_clickys: data.clickys.map((c) => c.slug),
      site: data.site_url || null,
    });
    return request.method === "HEAD" ? new Response(null, { status: 200, headers: response.headers }) : response;
  }
  if (path !== "/mcp") return jsonResponse({ error: "Not found. MCP endpoint is /mcp" }, 404);
  if (request.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405, headers: { Allow: "POST", ...CORS_HEADERS } });
  }

  const headerVersion = request.headers.get("MCP-Protocol-Version");
  if (headerVersion !== null && !SUPPORTED_PROTOCOL_VERSIONS.includes(headerVersion)) {
    return jsonResponse(errorResponse(null, -32600, `Unsupported MCP-Protocol-Version: ${headerVersion}`), 400);
  }
  const declaredLength = Number(request.headers.get("Content-Length") || 0);
  if (declaredLength > MAX_BODY_BYTES) {
    return jsonResponse(errorResponse(null, -32600, "Request too large"), 413);
  }
  const bodyBytes = await readBodyWithLimit(request, MAX_BODY_BYTES);
  if (bodyBytes === null) {
    return jsonResponse(errorResponse(null, -32600, "Request too large"), 413);
  }
  let payload;
  try {
    payload = JSON.parse(new TextDecoder().decode(bodyBytes));
    if (nestingDepth(payload) > MAX_NESTING) throw new Error("nesting too deep");
  } catch {
    return jsonResponse(errorResponse(null, -32700, "Parse error"), 400);
  }

  if (Array.isArray(payload)) {
    if (payload.length === 0) return jsonResponse(errorResponse(null, -32600, "Empty batch"), 400);
    if (!batchAllowed(headerVersion)) {
      return jsonResponse(errorResponse(null, -32600, "Batching is not supported in protocol 2025-06-18"), 400);
    }
    const responses = payload.map((m) => handleMessage(data, m)).filter((r) => r !== null);
    return responses.length ? jsonResponse(responses) : new Response(null, { status: 202, headers: CORS_HEADERS });
  }
  if (!isPlainObject(payload)) return jsonResponse(errorResponse(null, -32600, "Invalid request"), 400);
  const response = handleMessage(data, payload);
  return response ? jsonResponse(response) : new Response(null, { status: 202, headers: CORS_HEADERS });
}

export default {
  async fetch(request) {
    try {
      return await handleRequest(request);
    } catch {
      return jsonResponse(errorResponse(null, -32603, "Internal error"), 500);
    }
  },
};
