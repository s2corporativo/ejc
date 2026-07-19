// Testes do parser SSE (streamSSE): os streams legados (peça/bancário) emitem
// frames terminados em `\n\n`; o EventSourceResponse do sse-starlette (agente)
// termina linhas em `\r\n` → frames fecham com `\r\n\r\n`. O parser precisa
// aceitar os dois framings e não descartar o frame final sem terminador.
import { afterEach, describe, expect, it, vi } from "vitest";
import { streamSSE, type SSEEvent } from "./stream";

// streamSSE → authFetch → token/refresh de api.ts; aqui isolamos o parser.
vi.mock("./api", () => ({
  getAccessToken: () => null,
  refreshAccessToken: vi.fn(),
  logout: vi.fn(),
}));

/** Response fake cujo body entrega `chunks` em leituras sucessivas. */
function sseResponse(chunks: string[]): Response {
  const enc = new TextEncoder();
  const fila = [...chunks];
  const body = {
    getReader: () => ({
      read: async () =>
        fila.length > 0
          ? { done: false as const, value: enc.encode(fila.shift()!) }
          : { done: true as const, value: undefined },
    }),
  };
  return { ok: true, status: 200, body } as unknown as Response;
}

async function coletar(chunks: string[]): Promise<SSEEvent[]> {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => sseResponse(chunks)),
  );
  const eventos: SSEEvent[] = [];
  await streamSSE("/api/teste/stream", {}, { onEvent: (e) => eventos.push(e) });
  return eventos;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("streamSSE — framing LF (\\n\\n, streams legados)", () => {
  it("parseia frames event/data separados por \\n\\n", async () => {
    const eventos = await coletar([
      'event: passo\ndata: {"passo":1}\n\n',
      'event: final\ndata: {"status":"ok"}\n\n',
    ]);
    expect(eventos).toEqual([
      { event: "passo", data: { passo: 1 } },
      { event: "final", data: { status: "ok" } },
    ]);
  });

  it("junta frames quebrados no meio entre chunks", async () => {
    const eventos = await coletar([
      "event: passo\nda",
      'ta: {"passo":1}\n\nevent: final\ndata: {"st',
      'atus":"ok"}\n\n',
    ]);
    expect(eventos).toEqual([
      { event: "passo", data: { passo: 1 } },
      { event: "final", data: { status: "ok" } },
    ]);
  });

  it("ignora pings/comentários (`: keep-alive`)", async () => {
    const eventos = await coletar([
      ': keep-alive\n\nevent: passo\ndata: {"passo":1}\n\n',
    ]);
    expect(eventos).toEqual([{ event: "passo", data: { passo: 1 } }]);
  });
});

describe("streamSSE — framing CRLF (\\r\\n\\r\\n, sse-starlette)", () => {
  it("parseia frames event/data separados por \\r\\n\\r\\n", async () => {
    const eventos = await coletar([
      'event: passo\r\ndata: {"passo":1}\r\n\r\n',
      'event: confirmacao_requerida\r\ndata: {"token":null,"args_hash":"h"}\r\n\r\n',
    ]);
    expect(eventos).toEqual([
      { event: "passo", data: { passo: 1 } },
      {
        event: "confirmacao_requerida",
        data: { token: null, args_hash: "h" },
      },
    ]);
  });

  it("junta frames CRLF quebrados no meio entre chunks (inclusive no separador)", async () => {
    const eventos = await coletar([
      'event: passo\r\ndata: {"passo":1}\r\n\r',
      '\nevent: final\r\ndata: {"status":"ok"}\r\n\r\n',
    ]);
    expect(eventos).toEqual([
      { event: "passo", data: { passo: 1 } },
      { event: "final", data: { status: "ok" } },
    ]);
  });
});

describe("streamSSE — frame final sem terminador", () => {
  it("processa o resíduo do buffer ao fim do stream (LF)", async () => {
    const eventos = await coletar([
      'event: passo\ndata: {"passo":1}\n\nevent: final\ndata: {"status":"ok"}',
    ]);
    expect(eventos).toEqual([
      { event: "passo", data: { passo: 1 } },
      { event: "final", data: { status: "ok" } },
    ]);
  });

  it("processa o resíduo do buffer ao fim do stream (CRLF)", async () => {
    const eventos = await coletar([
      'event: final\r\ndata: {"status":"ok"}\r\n',
    ]);
    expect(eventos).toEqual([{ event: "final", data: { status: "ok" } }]);
  });
});
