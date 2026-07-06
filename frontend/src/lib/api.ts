// ── API client com refresh automático ────────────────────
import axios from "axios";
import type { Deadline } from "../types";

const api = axios.create({ baseURL: "/api" });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("ejc_access");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let refreshing: Promise<string> | null = null;

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config;
    // Troca de senha obrigatória: backend bloqueia tudo com 403+flag
    if (
      error.response?.status === 403 &&
      error.response?.data?.must_change_password &&
      window.location.pathname !== "/trocar-senha"
    ) {
      window.location.href = "/trocar-senha";
      return Promise.reject(error);
    }
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      const rt = localStorage.getItem("ejc_refresh");
      if (!rt) {
        logout();
        return Promise.reject(error);
      }
      try {
        refreshing ??= axios
          .post("/api/auth/refresh", { refresh_token: rt })
          .then((res) => {
            localStorage.setItem("ejc_access", res.data.access_token);
            localStorage.setItem("ejc_refresh", res.data.refresh_token);
            return res.data.access_token as string;
          })
          .finally(() => {
            refreshing = null;
          });
        const newToken = await refreshing;
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

export function logout() {
  const rt = localStorage.getItem("ejc_refresh");
  if (rt) axios.post("/api/auth/logout", { refresh_token: rt }).catch(() => {});
  localStorage.removeItem("ejc_access");
  localStorage.removeItem("ejc_refresh");
  localStorage.removeItem("ejc_user");
  window.location.href = "/login";
}

export default api;
