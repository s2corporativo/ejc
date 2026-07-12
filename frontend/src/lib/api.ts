// ── API client com refresh automático ────────────────────
// O access token curto vive em localStorage (ejc_access). O refresh token
// vive num cookie httpOnly (ejc_refresh) setado/lido pelo backend — por isso
// TODAS as chamadas usam withCredentials para o navegador enviar o cookie.
import axios from "axios";
import type { AuthTokens, Deadline } from "../types";

const api = axios.create({ baseURL: "/api", withCredentials: true });

/** Access token curto atualmente em localStorage (ou null). */
export function getAccessToken(): string | null {
  return localStorage.getItem("ejc_access");
}

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let refreshing: Promise<string> | null = null;

/**
 * Renova o access token usando o refresh que está no cookie httpOnly
 * `ejc_refresh`. Sem body — o cookie carrega o refresh. Grava apenas o novo
 * access em localStorage. Chamadas concorrentes compartilham a mesma Promise.
 */
export function refreshAccessToken(): Promise<string> {
  refreshing ??= axios
    .post<AuthTokens>("/api/auth/refresh", {}, { withCredentials: true })
    .then((res) => {
      const token = res.data.access_token;
      localStorage.setItem("ejc_access", token);
      return token;
    })
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config;
    const requestUrl = String(original?.url || "");
    const isAuthenticationRequest =
      requestUrl.includes("/auth/login") ||
      requestUrl.includes("/auth/refresh") ||
      requestUrl.includes("/auth/recuperar-senha") ||
      requestUrl.includes("/auth/redefinir-senha");

    // Troca de senha obrigatória: backend bloqueia tudo com 403+flag
    if (
      error.response?.status === 403 &&
      error.response?.data?.must_change_password &&
      window.location.pathname !== "/trocar-senha"
    ) {
      window.location.href = "/trocar-senha";
      return Promise.reject(error);
    }

    // Só tenta refresh quando a requisição realmente partiu de uma sessão com
    // access token. Erros 401 de login (senha incorreta ou desafio TOTP) devem
    // chegar à tela de autenticação, sem logout ou redirecionamento automático.
    if (
      error.response?.status === 401 &&
      !isAuthenticationRequest &&
      getAccessToken() &&
      original &&
      !original._retry
    ) {
      original._retry = true;
      try {
        const newToken = await refreshAccessToken();
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      } catch {
        logout();
      }
    }
    return Promise.reject(error);
  },
);

// ── Materialização da extração de IA no caso ──────────────
// JSON produzido por /documentos-ia/analisar (partes, número/tribunal, área).
export interface ExtracaoPayload {
  identificacao_processual?: Record<string, unknown> | null;
  partes?: Record<string, unknown> | null;
  classificacao?: Record<string, unknown> | null;
}

// Resposta de POST /cases/{id}/aplicar-extracao (idêntica em preview e aplicação).
export interface AplicarExtracaoResult {
  aplicado: boolean;
  dry_run: boolean;
  ok: boolean;
  partes_criadas: number;
  areas_criadas: number;
  prazos_criados: number;
  campos_preenchidos: string[];
  aviso: string;
}

/**
 * Materializa no caso os dados extraídos por IA de um documento.
 * `dryRun: true` → preview (nada é persistido; devolve o que SERIA aplicado).
 * `dryRun: false` (padrão) → aplica e persiste.
 */
export async function aplicarExtracao(
  caseId: string,
  extracao: ExtracaoPayload,
  { dryRun = false }: { dryRun?: boolean } = {},
): Promise<AplicarExtracaoResult> {
  const { data } = await api.post<AplicarExtracaoResult>(
    `/cases/${caseId}/aplicar-extracao`,
    extracao,
    { params: { dry_run: dryRun } },
  );
  return data;
}

/**
 * Confirma um prazo sugerido pela IA (ou não-confirmado). O backend seta
 * `confirmado=true` e devolve o deadline atualizado. Ownership é checado.
 */
export async function confirmarPrazo(deadlineId: string): Promise<Deadline> {
  const { data } = await api.patch<Deadline>(
    `/deadlines/${deadlineId}/confirmar`,
  );
  return data;
}

// `redirectTo` permite chegar ao /login com contexto (ex.: ?motivo=senha-alterada
// após a troca de senha obrigatória) — o redirect é hard, então toasts não
// sobrevivem. Tipado como `unknown` porque logout também é usado direto como
// onClick handler (recebe MouseEvent, que é ignorado).
export function logout(redirectTo?: unknown) {
  // O backend limpa o cookie httpOnly ejc_refresh; o cookie vai junto via withCredentials.
  axios.post("/api/auth/logout", {}, { withCredentials: true }).catch(() => {});
  localStorage.removeItem("ejc_access");
  localStorage.removeItem("ejc_user");
  window.location.href =
    typeof redirectTo === "string" && redirectTo.startsWith("/login?")
      ? redirectTo
      : "/login";
}

export default api;
