export const CASE_LIFECYCLE_STATUS = [
  "triagem",
  "em_analise",
  "aguardando_documentos",
  "proposta_apresentada",
  "contratacao_pendente",
  "contratado",
  "em_andamento",
  "suspenso",
  "encerrado",
  "arquivado",
  "nao_contratado",
] as const;

export const TASK_LIFECYCLE_STATUS = [
  "pendente",
  "em_execucao",
  "aguardando_terceiro",
  "concluida",
  "cancelada",
  "vencida",
] as const;

export const DOCUMENT_LIFECYCLE_STATUS = [
  "rascunho",
  "em_elaboracao",
  "em_revisao",
  "aprovado",
  "assinado",
  "protocolado",
  "substituido",
  "arquivado",
] as const;

export const FINANCIAL_LIFECYCLE_STATUS = [
  "previsto",
  "faturado",
  "parcialmente_recebido",
  "recebido",
  "vencido",
  "renegociado",
  "cancelado",
] as const;

export type CaseLifecycleStatus = (typeof CASE_LIFECYCLE_STATUS)[number];
export type TaskLifecycleStatus = (typeof TASK_LIFECYCLE_STATUS)[number];
export type DocumentLifecycleStatus =
  (typeof DOCUMENT_LIFECYCLE_STATUS)[number];
export type FinancialLifecycleStatus =
  (typeof FINANCIAL_LIFECYCLE_STATUS)[number];
