import crypto from "node:crypto";

// Chave PUBLICA Ed25519 do relay DJEN. Nao e segredo.
// A chave privada correspondente existe apenas no ambiente operacional do EJC.
const PUBLIC_KEY = Buffer.from(
  "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUNvd0JRWURLMlZ3QXlFQXF5QmZobndGUzVMR2VBL0tXanN2dTNwaGZhSUhXR0NBQ0w3VHM1dElNZ0k9Ci0tLS0tRU5EIFBVQkxJQyBLRVktLS0tLQo=",
  "base64",
).toString("utf8");

const ALLOWED = new Set([
  "numeroOab",
  "ufOab",
  "dataDisponibilizacaoInicio",
  "dataDisponibilizacaoFim",
  "itensPorPagina",
  "pagina",
  "numeroProcesso",
]);

function canonicalQuery(url) {
  const seen = new Set();
  const pairs = [];
  for (const [key, value] of url.searchParams.entries()) {
    if (!ALLOWED.has(key) || seen.has(key)) {
      throw new Error("query_invalida");
    }
    seen.add(key);
    pairs.push([key, value]);
  }
  pairs.sort((a, b) => a[0].localeCompare(b[0]));
  return new URLSearchParams(pairs).toString();
}

function unauthorized(res) {
  res.statusCode = 401;
  res.setHeader("content-type", "application/json");
  res.setHeader("cache-control", "no-store");
  res.end(JSON.stringify({ ok: false, error: "unauthorized" }));
}

export default async function handler(req, res) {
  if (req.method !== "GET") {
    res.statusCode = 405;
    res.setHeader("allow", "GET");
    return res.end();
  }

  let url;
  let canonical;
  try {
    url = new URL(req.url, "https://relay.invalid");
    canonical = canonicalQuery(url);
  } catch {
    res.statusCode = 400;
    res.setHeader("content-type", "application/json");
    res.setHeader("cache-control", "no-store");
    return res.end(JSON.stringify({ ok: false, error: "query_invalida" }));
  }

  const ts = req.headers["x-ejc-timestamp"];
  const sig = req.headers["x-ejc-signature"];
  if (!ts || !sig || !/^\d{10,13}$/.test(String(ts))) {
    return unauthorized(res);
  }

  const rawTs = Number(ts);
  const tsMs = String(ts).length === 10 ? rawTs * 1000 : rawTs;
  if (!Number.isFinite(tsMs) || Math.abs(Date.now() - tsMs) > 120_000) {
    return unauthorized(res);
  }

  let signature;
  try {
    signature = Buffer.from(String(sig), "base64url");
  } catch {
    return unauthorized(res);
  }

  const payload = Buffer.from(String(ts) + "\n" + canonical, "utf8");
  let valid = false;
  try {
    valid = crypto.verify(null, payload, PUBLIC_KEY, signature);
  } catch {
    valid = false;
  }
  if (!valid) {
    return unauthorized(res);
  }

  const upstream = new URL(
    "https://comunicaapi.pje.jus.br/api/v1/comunicacao",
  );
  for (const [key, value] of [...url.searchParams.entries()].sort((a, b) =>
    a[0].localeCompare(b[0])
  )) {
    upstream.searchParams.append(key, value);
  }

  try {
    const response = await fetch(upstream, {
      method: "GET",
      headers: {
        accept: "application/json",
        "user-agent": "EJC-DJEN-Relay/1.0",
      },
      redirect: "error",
      cache: "no-store",
    });
    const body = await response.arrayBuffer();
    res.statusCode = response.status;
    res.setHeader(
      "content-type",
      response.headers.get("content-type") || "application/json",
    );
    res.setHeader("cache-control", "no-store");
    res.setHeader("x-ejc-relay-region", process.env.VERCEL_REGION || "unknown");
    return res.end(Buffer.from(body));
  } catch {
    res.statusCode = 502;
    res.setHeader("content-type", "application/json");
    res.setHeader("cache-control", "no-store");
    res.setHeader("x-ejc-relay-region", process.env.VERCEL_REGION || "unknown");
    return res.end(JSON.stringify({ ok: false, error: "upstream_unavailable" }));
  }
}
