// ARQUIVO GERADO — não edite.
// Fonte: backend/scripts/gerar_tipos_frontend.py (enums de app/models e
// app/core/taxonomia). Regenerar: `npm run types:gerar` (frontend) ou
// `APP_ENV=development python scripts/gerar_tipos_frontend.py` (backend).
// O teste backend/tests/test_tipos_frontend_gerados.py falha quando este
// arquivo diverge do backend.

/** Áreas do direito (enum CaseArea / core.taxonomia.AREAS_CANONICAS). */
export const AREAS_CANONICAS = [
  "civil",
  "trabalhista",
  "consumidor",
  "familia",
  "ambiental",
  "criminal",
  "previdenciario",
  "empresarial",
  "tributario",
  "administrativo",
  "bancario",
  "imobiliario",
  "sucessoes",
  "constitucional",
  "digital_lgpd",
  "transito",
  "saude",
  "medico",
  "agrario",
  "agronegocio",
  "eleitoral",
  "internacional",
  "contratual",
  "societario",
  "licitacoes",
] as const;
export type CaseArea = (typeof AREAS_CANONICAS)[number];

/** Rótulo pt-BR de cada área canônica. */
export const ROTULO_AREA: Record<CaseArea, string> = {
  civil: "Cível",
  trabalhista: "Trabalhista",
  consumidor: "Consumidor",
  familia: "Família",
  ambiental: "Ambiental",
  criminal: "Criminal",
  previdenciario: "Previdenciário",
  empresarial: "Empresarial",
  tributario: "Tributário",
  administrativo: "Administrativo",
  bancario: "Bancário",
  imobiliario: "Imobiliário",
  sucessoes: "Sucessões",
  constitucional: "Constitucional",
  digital_lgpd: "Digital e LGPD",
  transito: "Trânsito",
  saude: "Saúde",
  medico: "Médico",
  agrario: "Agrário",
  agronegocio: "Agronegócio",
  eleitoral: "Eleitoral",
  internacional: "Internacional",
  contratual: "Contratual",
  societario: "Societário",
  licitacoes: "Licitações",
};

/** Áreas em destaque no menu de ramos (casos reais do escritório). */
export const AREAS_DESTAQUE: readonly CaseArea[] = [
  "consumidor",
  "civil",
];

/** Status do caso (enum CaseStatus). */
export const CASE_STATUS = [
  "aberto",
  "em_instrucao",
  "em_producao",
  "protocolado",
  "encerrado",
  "arquivado",
] as const;
export type CaseStatus = (typeof CASE_STATUS)[number];

/** Fase do caso (enum CaseFase). */
export const CASE_FASE = [
  "pre_processual",
  "conhecimento",
  "recursal",
  "execucao",
  "administrativo",
] as const;
export type CaseFase = (typeof CASE_FASE)[number];

/** Prioridade do caso (enum CasePrioridade). */
export const CASE_PRIORIDADE = [
  "baixa",
  "media",
  "alta",
  "critica",
] as const;
export type CasePrioridade = (typeof CASE_PRIORIDADE)[number];

/** Tipo de prazo (enum DeadlineTipo). */
export const DEADLINE_TIPO = [
  "processual",
  "administrativo",
  "interno",
  "audiencia",
  "prescricao",
] as const;
export type DeadlineTipo = (typeof DEADLINE_TIPO)[number];

/** Status de prazo (enum DeadlineStatus). */
export const DEADLINE_STATUS = [
  "pendente",
  "concluido",
  "vencido",
  "cancelado",
] as const;
export type DeadlineStatus = (typeof DEADLINE_STATUS)[number];

/** Prioridade de prazo (enum DeadlinePrioridade). */
export const DEADLINE_PRIORIDADE = [
  "baixa",
  "media",
  "alta",
  "critica",
] as const;
export type DeadlinePrioridade = (typeof DEADLINE_PRIORIDADE)[number];

/** Origem do prazo (coluna deadlines.origem — valores reais gravados). */
export const DEADLINE_ORIGEM = [
  "manual",
  "datajud",
  "importacao_ia",
  "entrada_unica",
] as const;
export type DeadlineOrigem = (typeof DEADLINE_ORIGEM)[number];

/** Papéis de usuário (enum UserRole). */
export const USER_ROLE = [
  "superadmin",
  "admin",
  "socio",
  "advogado",
  "advogado_auxiliar",
  "financeiro",
  "estagiario",
  "secretaria",
  "cliente_externo",
] as const;
export type UserRole = (typeof USER_ROLE)[number];

/** Status de peça (enum PecaStatus). */
export const PECA_STATUS = [
  "rascunho",
  "em_revisao",
  "corrigida",
  "aprovada",
  "final",
  "protocolada",
] as const;
export type PecaStatus = (typeof PECA_STATUS)[number];

/** Tipo de peça (enum PecaTipo). */
export const PECA_TIPO = [
  "peticao_inicial",
  "contestacao",
  "recurso",
  "contrarrazoes",
  "parecer",
  "contrato",
  "procuracao",
  "notificacao_extrajudicial",
  "defesa_ambiental",
  "outro",
] as const;
export type PecaTipo = (typeof PECA_TIPO)[number];

/** Status de revisão humana de output de IA (enum AIStatusHITL). */
export const AI_STATUS_HITL = [
  "gerado",
  "revisado",
  "aplicado",
  "descartado",
] as const;
export type AIStatusHITL = (typeof AI_STATUS_HITL)[number];
