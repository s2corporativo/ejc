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
  prazos?: Array<Record<string, unknown>> | null;
  origem_documento_id?: string | null;
  /** Lote persistido pela Entrada Universal; nunca é enviado ao schema legado. */
  batch_id?: string | null;
  [key: string]: unknown;
}

export interface DocumentoIntakeResultPayload {
  tipo_documento?: string | null;
  confianca_classificacao?: number | null;
  cliente?: Record<string, unknown> | null;
  caso?: Record<string, unknown> | null;
  partes?: Array<Record<string, unknown>>;
  pedidos?: Array<Record<string, unknown>>;
  provas?: Array<Record<string, unknown>>;
  prazos?: Array<Record<string, unknown>>;
  riscos?: Array<Record<string, unknown>>;
  teses?: Array<Record<string, unknown>>;
  pendencias?: Array<Record<string, unknown>>;
  resumo_fatos?: string | null;
  necessita_revisao_humana?: boolean;
  [key: string]: unknown;
}

export interface AplicarAcoesDocumentoResult {
  ok: boolean;
  prazos_criados: string[];
  tarefas_criadas: string[];
  aviso: string;
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
 * Vincula TODOS os originais de um lote da Entrada Universal ao caso (e ao
 * cliente do caso) via POST /entrada-universal/{batch_id}/vincular-caso.
 * O backend é idempotente e remove duplicatas técnicas recentes (sha256).
 */
export async function vincularLoteAoCaso(
  batchId: string,
  caseId: string,
): Promise<void> {
  await api.post(`/entrada-universal/${batchId}/vincular-caso`, {
    case_id: caseId,
  });
}

/**
 * Materializa no caso os dados extraídos por IA de um documento.
 * `dryRun: true` → preview (nada é persistido; devolve o que SERIA aplicado).
 * `dryRun: false` (padrão) → aplica e persiste.
 *
 * Quando a extração nasceu na Entrada Universal, vincula antes todos os
 * originais do lote ao caso. A operação de vínculo é idempotente.
 */
export async function aplicarExtracao(
  caseId: string,
  extracao: ExtracaoPayload,
  { dryRun = false }: { dryRun?: boolean } = {},
): Promise<AplicarExtracaoResult> {
  const batchId = extracao.batch_id;
  if (typeof batchId === "string" && batchId) {
    await vincularLoteAoCaso(batchId, caseId);
  }
  // O endpoint legado usa um modelo Pydantic fechado. Metadados ricos da
  // Entrada Universal ficam no lote e só os campos materializáveis seguem.
  const payloadLegado = {
    identificacao_processual: extracao.identificacao_processual ?? null,
    partes: extracao.partes ?? null,
    classificacao: extracao.classificacao ?? null,
    prazos: extracao.prazos ?? null,
    origem_documento_id: extracao.origem_documento_id ?? null,
  };
  const { data } = await api.post<AplicarExtracaoResult>(
    `/cases/${caseId}/aplicar-extracao`,
    payloadLegado,
    { params: { dry_run: dryRun } },
  );
  return data;
}

/**
 * Depois da revisão humana, materializa prazos e pendências da análise na
 * jornada do caso. O backend cria tudo como rascunho auditável.
 */
export async function aplicarAcoesDocumento(
  caseId: string,
  intakeResult: DocumentoIntakeResultPayload,
): Promise<AplicarAcoesDocumentoResult> {
  const { data } = await api.post<AplicarAcoesDocumentoResult>(
    "/documentos-ia/aplicar-acoes",
    {
      case_id: caseId,
      intake_result: intakeResult,
      criar_prazos: true,
      criar_tarefas: true,
      criar_alerta: true,
    },
  );
  return data;
}

// ── Raio-X · Análise "advogado sênior" (IA agêntica) ──────
// Segunda camada, aditiva e cara, movida pelo módulo agêntico (SOMENTE leitura,
// sem HITL). Atrás de AI_AGENT_ENABLED: flag OFF → status "indisponivel".
// Ver backend/app/services/raio_x_advogado_service.py.
export interface CriticaAdversarial {
  disponivel: boolean;
  nota_robustez?: number | null;
  relatorio?: string | null;
  alertas?: string[];
  aviso?: string | null;
}

export interface AnaliseAdvogadoResult {
  /** "ok" | "indisponivel" | "erro" | outros status propagados do agente. */
  status: string;
  analise?: string | null;
  is_rascunho?: boolean;
  critica_adversarial?: CriticaAdversarial | null;
  custo_estimado_brl?: number | null;
  alertas?: string[];
  revisao_obrigatoria?: boolean;
  detalhe?: string | null;
}

/** Análise do advogado (IA) do Raio-X CONTEXTUAL de um caso existente. */
export async function analiseAdvogadoContextual(
  caseId: string,
): Promise<AnaliseAdvogadoResult> {
  const { data } = await api.post<AnaliseAdvogadoResult>(
    `/raio-x/contextual/${caseId}/analise-advogado`,
  );
  return data;
}

/** Análise do advogado (IA) de uma análise preliminar por documentos.
 *  Exige caso vinculado no backend (senão HTTP 409). */
export async function analiseAdvogadoPorAnalise(
  analiseId: string,
): Promise<AnaliseAdvogadoResult> {
  const { data } = await api.post<AnaliseAdvogadoResult>(
    `/raio-x/${analiseId}/analise-advogado`,
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

// ── Orquestrador Jurídico do Caso (§16) ───────────────────
// Máquina de estados derivada dos ARTEFATOS reais do caso (backend:
// app/services/legal_case_orchestrator.py). Tudo que a IA produz é rascunho
// sujeito à revisão do advogado — atos jurídicos nunca são executados aqui.

export interface OrquestradorAcao {
  acao: string;
  metodo: string;
  endpoint: string;
  /** Documentação dos campos esperados (strings descritivas do backend). */
  payload_esperado: Record<string, unknown>;
  /** false ⇒ ato de aprovação humana — o /avancar nunca executa. */
  executavel_via_orquestrador: boolean;
}

export interface OrquestradorPendencia {
  /** "base_fatica" | "aprovacao_humana" | "checklist" | "prazo" | "ato_externo" */
  tipo: string;
  detalhe: string;
  endpoint?: string;
  /** Itens pendentes quando tipo="checklist". */
  itens?: Array<Record<string, unknown>>;
}

export interface OrquestradorProximoPasso {
  estado: string;
  estado_rotulo: string;
  passo_recomendado: string;
  acoes_disponiveis: OrquestradorAcao[];
  pendencias_bloqueantes: OrquestradorPendencia[];
}

export type OrquestradorEtapaStatus =
  | "concluida"
  | "em_andamento"
  | "pendente"
  | "bloqueada";

export interface OrquestradorEtapa {
  etapa: string;
  rotulo: string;
  status: OrquestradorEtapaStatus;
}

export interface OrquestradorEvento {
  versao: number;
  origem: string;
  estado?: string | null;
  resumo?: string | null;
  congelado: boolean;
  criado_em?: string | null;
}

export interface OrquestradorVisao {
  case_id: string;
  estado: string;
  estado_rotulo: string;
  estados: string[];
  proximo_passo: OrquestradorProximoPasso;
  jornada: OrquestradorEtapa[];
  linha_do_tempo: OrquestradorEvento[];
}

export interface OrquestradorAvancarResult {
  executado: boolean;
  acao: string;
  /** true quando a ação é ato jurídico — nada foi executado. */
  requer_aprovacao_humana?: boolean;
  instrucao?: string;
  endpoint_humano?: string;
  estado_anterior?: string | null;
  estado?: string | null;
  resultado?: unknown;
}

/** Visão consolidada: estado + próximo passo + pendências + jornada + linha do tempo. */
export async function visaoOrquestrador(
  caseId: string,
): Promise<OrquestradorVisao> {
  const { data } = await api.get<OrquestradorVisao>(
    `/cases/${caseId}/orquestrador`,
  );
  return data;
}

/**
 * Executa UMA transição da máquina de estados (advogado+; rate limit 10/min).
 * 422 devolve detail estruturado ({mensagem, acoes_validas?|erros?}); atos de
 * aprovação humana voltam com requer_aprovacao_humana=true SEM executar nada.
 */
export async function avancarOrquestrador(
  caseId: string,
  acao: string,
  params?: Record<string, unknown>,
): Promise<OrquestradorAvancarResult> {
  const { data } = await api.post<OrquestradorAvancarResult>(
    `/cases/${caseId}/orquestrador/avancar`,
    { acao, params: params ?? null },
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
