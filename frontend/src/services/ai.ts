import api from "../lib/api";

/**
 * Camada de services do domínio IA (auditoria Fase 4 §2.6 #1).
 *
 * Os paths de endpoint vivem AQUI — páginas e componentes consomem funções
 * tipadas e nunca montam strings de URL. Contratos espelham
 * `backend/app/schemas/ai_skill.py` e `backend/app/routers/ai_skills.py`;
 * qualquer divergência é bug de contrato, não de coincidência.
 */

// ── Catálogo de skills ───────────────────────────────────────────────────────

/** Item de GET /ai/skills/list (SkillListItem do backend). */
export type Skill = {
  id: string;
  name: string;
  display_name: string;
  description?: string | null;
  engine: string;
  area: string;
  functional_group: "analisar" | "produzir" | "revisar" | "preparar";
  requires_case: boolean;
  requires_human_review: boolean;
  oab_restricted: boolean;
};

/** Ação sugerida por contexto (ContextualActionItem do backend). */
export type ContextualAction = Skill & {
  reason: string;
  score: number;
};

/** Resposta de GET /ai/skills/contextual (ContextualActionsResponse). */
export type ContextualActionsResponse = {
  surface: string;
  area?: string | null;
  phase?: string | null;
  document_type?: string | null;
  case_id?: string | null;
  actions: ContextualAction[];
  total_catalog: number;
  selection_method: string;
};

/** GET /ai/skills/list — catálogo completo de skills. */
export async function listarSkills(): Promise<Skill[]> {
  const { data } = await api.get<{ data: Skill[] }>("/ai/skills/list");
  return data.data ?? [];
}

/** Parâmetros de GET /ai/skills/contextual. */
export type AcoesContextuaisParams = {
  surface: string;
  area?: string | null;
  phase?: string | null;
  document_type?: string | null;
  case_id?: string | null;
  /** 1..8 no backend; default 5. */
  limit?: number;
};

/** GET /ai/skills/contextual — ações ranqueadas para a superfície atual. */
export async function acoesContextuais(
  params: AcoesContextuaisParams,
): Promise<ContextualActionsResponse> {
  const { data } = await api.get<ContextualActionsResponse>(
    "/ai/skills/contextual",
    { params },
  );
  return data;
}

// ── Execução de skills ───────────────────────────────────────────────────────

/** Corpo de POST /ai/skills/execute (SkillExecuteRequest do backend). */
export type SkillExecuteRequest = {
  skill_name: string;
  query: string;
  case_id?: string | null;
  usar_rag?: boolean;
  surface?: string | null;
  area?: string | null;
  phase?: string | null;
};

/** Próxima ação sugerida pelo backend (item de `proximas_acoes`). */
export type ProximaAcao = {
  name: string;
  display_name: string;
  description?: string | null;
};

/** Resposta de POST /ai/skills/execute(-doc|transcribe-media). */
export type SkillExecuteResponse = {
  conteudo: string;
  skill: string;
  skill_name?: string | null;
  engine: string;
  is_rascunho: boolean;
  requer_revisao: boolean;
  tokens_usados: number;
  custo_estimado_brl: number;
  processamento?: { modo?: string; blocos?: number } | null;
  transcricao?: string | null;
  ai_log_id?: string | null;
  classificacao?: {
    tipo: string;
    confianca: number;
    sinais: string[];
    metodo: string;
  } | null;
  proximas_acoes?: ProximaAcao[];
  auditoria?: Record<string, unknown> | null;
  aviso_privacidade?: string | null;
  aviso?: string;
};

/**
 * POST /ai/skills/execute — executa uma skill com revisão HITL garantida.
 * O rótulo de rascunho vem do backend (`aviso`, `is_rascunho`); nunca
 * apresente o conteúdo como peça final sem revisão humana.
 */
export async function executarSkill(
  req: SkillExecuteRequest,
): Promise<SkillExecuteResponse> {
  const { data } = await api.post<SkillExecuteResponse>(
    "/ai/skills/execute",
    req,
  );
  return data;
}

/**
 * POST /ai/skills/execute-doc — executa skill sobre documento enviado
 * (multipart). Campos esperados: file, skill_name ("auto" p/ classificação),
 * case_id, surface, area, phase, usar_rag, instrucoes.
 */
export async function executarSkillDocumento(
  formData: FormData,
): Promise<SkillExecuteResponse> {
  const { data } = await api.post<SkillExecuteResponse>(
    "/ai/skills/execute-doc",
    formData,
  );
  return data;
}

/** POST /ai/skills/transcribe-media — transcrição de áudio/vídeo (multipart). */
export async function transcreverMidia(
  formData: FormData,
): Promise<SkillExecuteResponse> {
  const { data } = await api.post<SkillExecuteResponse>(
    "/ai/skills/transcribe-media",
    formData,
  );
  return data;
}
