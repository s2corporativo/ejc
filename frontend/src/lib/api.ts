// ── API client com refresh automático ────────────────────
// O access token curto vive SOMENTE em memória. O refresh token vive num
// cookie httpOnly (ejc_refresh) setado/lido pelo backend — por isso TODAS as
// chamadas usam withCredentials para o navegador enviar o cookie.
import axios from "axios";
import { toast } from "../components/Toast";
import type { AuthTokens, Deadline } from "../types";

export const API_BASE_URL = "/api/v1";
const api = axios.create({ baseURL: API_BASE_URL, withCredentials: true });

let accessToken: string | null = null;
const LEGACY_ACCESS_KEY = "ejc_access";

// Limpa eventual token persistido por versões anteriores. O valor nunca é lido.
if (typeof localStorage !== "undefined") {
  try {
    localStorage.removeItem(LEGACY_ACCESS_KEY);
  } catch {
    // Storage indisponível não impede sessão em memória.
  }
}

/** Access token curto somente em memória de módulo. */
export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

api.interceptors.request.use((config) => {
  // Compatibilidade transitória: chamadas antigas que ainda informam /api ou
  // /v1 não podem duplicar o prefixo agora que o cliente usa /api/v1.
  const url = String(config.url || "");
  if (url.startsWith("/api/v1/")) config.url = url.slice("/api/v1".length);
  else if (url.startsWith("/api/")) config.url = url.slice("/api".length);
  else if (url.startsWith("/v1/")) config.url = url.slice("/v1".length);

  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let refreshing: Promise<string> | null = null;

/**
 * Renova o access token usando o refresh que está no cookie httpOnly
 * `ejc_refresh`. Sem body — o cookie carrega o refresh. Mantém o novo access
 * somente em memória. Chamadas concorrentes compartilham a mesma Promise.
 */
export function refreshAccessToken(): Promise<string> {
  refreshing ??= axios
    // Path REAL do backend (prefix "/api" + router "/auth", SEM "/v1" — o
    // "v1" só existe no baseURL do cliente `api`, cujo interceptor de request
    // o remove antes de sair; aqui usamos axios cru de propósito (evita
    // recursão com o interceptor de response que trata 401 refazendo refresh)
    // então o path precisa ser o REAL, não o convencionado do cliente.
    .post<AuthTokens>("/api/auth/refresh", {}, { withCredentials: true })
    .then((res) => {
      const token = res.data.access_token;
      setAccessToken(token);
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

    const needsTwoFactorSetup =
      error.response?.data?.precisa_configurar_2fa ||
      error.response?.data?.detail?.precisa_configurar_2fa;
    if (
      error.response?.status === 403 &&
      needsTwoFactorSetup &&
      window.location.pathname !== "/configurar-2fa"
    ) {
      window.location.href = "/configurar-2fa";
      return Promise.reject(error);
    }

    // 403 "comum" de RBAC: o backend recusou por falta de permissão, sem as
    // flags especiais tratadas acima (troca de senha / 2FA). Avisa o usuário
    // uma única vez com um toast padronizado e rejeita normalmente, para o
    // chamador seguir seu próprio tratamento de erro. Requisições de
    // autenticação ficam de fora (a tela de login trata seus próprios erros).
    if (
      error.response?.status === 403 &&
      !error.response?.data?.must_change_password &&
      !needsTwoFactorSetup &&
      !isAuthenticationRequest
    ) {
      toast.error("Sem permissão para esta ação");
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
// JSON de extração (partes, número/tribunal, área) produzido pela trilha
// canônica: lote da Entrada Universal (/api/entrada-universal/*) +
// POST /cases/{id}/aplicar-extracao.
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

export interface VincularLoteResult {
  ok: boolean;
  batch_id: string;
  case_id: string;
  documentos_vinculados: number;
  documentos_ja_vinculados: number;
  duplicatas_tecnicas_removidas: number;
  copias_isoladas: number;
  /** Itens que NÃO puderam ser vinculados (ex.: arquivo ausente/externo). */
  conflitos: { document_id: string; filename: string; motivo: string }[];
  operacao_idempotente: boolean;
  revisao_obrigatoria: boolean;
}

/**
 * Vincula TODOS os originais de um lote da Entrada Universal ao caso (e ao
 * cliente do caso) via POST /entrada-universal/{batch_id}/vincular-caso.
 * O backend é idempotente e remove duplicatas técnicas recentes (sha256).
 * ATENÇÃO: 200 pode vir com `conflitos` não vazio — o chamador deve exibir
 * esses itens ao usuário em vez de tratar como sucesso pleno.
 */
export async function vincularLoteAoCaso(
  batchId: string,
  caseId: string,
): Promise<VincularLoteResult> {
  const { data } = await api.post<VincularLoteResult>(
    `/entrada-universal/${batchId}/vincular-caso`,
    { case_id: caseId },
  );
  return data;
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
  "concluida" | "em_andamento" | "pendente" | "bloqueada";

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
  setAccessToken(null);
  localStorage.removeItem("ejc_user");
  // Rascunho de intake carrega dados pessoais extraídos de documentos — não
  // pode sobreviver ao fim da sessão (LGPD). Limpa pela CHAVE para não criar
  // ciclo de import em runtime (intakeRascunho importa apenas types daqui).
  localStorage.removeItem("ejc_intake_rascunho");
  window.location.href =
    typeof redirectTo === "string" && redirectTo.startsWith("/login?")
      ? redirectTo
      : "/login";
}

export default api;
