// ── Fetch autenticado para streams (SSE) ─────────────────
// axios não expõe o corpo como stream no navegador, então respostas SSE
// (POST → text/event-stream) precisam de fetch cru. Este helper centraliza a
// MESMA lógica de token/refresh do cliente axios (api.ts): injeta o Bearer,
// e num 401 renova o access via cookie httpOnly e repete a requisição uma vez.
import { getAccessToken, refreshAccessToken, logout } from "./api";

function withAuth(init: RequestInit, token: string | null): RequestInit {
  const headers = new Headers(init.headers ?? {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return { ...init, headers, credentials: "include" };
}

/**
 * fetch() autenticado com refresh 401→renova→repete (uma vez). Devolve a
 * Response crua — o chamador consome `response.body` (reader SSE) e trata
 * status/erros conforme a sua semântica.
 */
export async function authFetch(
  url: string,
  init: RequestInit = {},
): Promise<Response> {
  const res = await fetch(url, withAuth(init, getAccessToken()));
  if (res.status !== 401) return res;
  // Access expirado: renova via cookie e repete uma única vez.
  try {
    const token = await refreshAccessToken();
    return await fetch(url, withAuth(init, token));
  } catch {
    // Refresh falhou: sessão expirada. Alinha com o interceptor de api.ts
    // (limpa a sessão e redireciona a /login) em vez de devolver o 401 mudo.
    logout();
    return res;
  }
}

// ── Consumo de SSE via POST ──────────────────────────────
// EventSource só faz GET; para respostas text/event-stream vindas de um POST
// (agente de IA, geração de peça) lemos o corpo cru como stream. Este helper
// centraliza: authFetch (Bearer + refresh) → checagem de status → leitura do
// reader → parse dos frames `event:`/`data:` → callback por evento.

/** Um frame SSE já parseado: nome do evento + payload JSON (objeto). */
export interface SSEEvent {
  event: string;
  data: Record<string, any>;
}

/** Erro de uma requisição SSE não-ok; carrega o HTTP status para o chamador
 *  distinguir casos como 404 (recurso desligado) de erros genéricos. */
export class SSEHttpError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "SSEHttpError";
    this.status = status;
  }
}

/**
 * POST `body` (JSON) para `url` e consome a resposta SSE, chamando `onEvent`
 * a cada frame. Resolve quando o stream termina; propaga AbortError quando
 * `signal` aborta. Em resposta não-ok, lança `SSEHttpError` com o `detail` do
 * backend (desembrulha o aninhamento `detail.detail`/`detail.mensagem`).
 */
export async function streamSSE(
  url: string,
  body: unknown,
  {
    onEvent,
    signal,
  }: { onEvent: (evt: SSEEvent) => void; signal?: AbortSignal },
): Promise<void> {
  const res = await authFetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const raw = (err as Record<string, any>)?.detail;
    const detail =
      typeof raw === "string" ? raw : (raw?.mensagem ?? raw?.detail ?? null);
    throw new SSEHttpError(
      res.status,
      detail ?? `Falha na requisição (HTTP ${res.status}).`,
    );
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    const parts = buf.split("\n\n");
    buf = parts.pop() ?? "";

    for (const part of parts) {
      const event = part.match(/^event:\s*(.+)$/m)?.[1]?.trim();
      const dataLine = part.match(/^data:\s*(.+)$/ms)?.[1]?.trim();
      if (!event || !dataLine) continue; // pings (`: keep-alive`) caem aqui
      let data: Record<string, any> = {};
      try {
        data = JSON.parse(dataLine);
      } catch {
        continue;
      }
      onEvent({ event, data });
    }
  }
}
