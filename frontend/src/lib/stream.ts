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
