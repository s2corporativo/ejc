// ── Tipos do EJC ─────────────────────────────────────────
export interface User {
  id: string;
  email: string;
  full_name: string;
  role: string;
  phone?: string;
  oab_number?: string;
  is_active?: boolean;
  /** Path da foto de perfil (ex.: "/users/{id}/avatar", sem prefixo /api). */
  avatar_url?: string | null;
}
export interface Client {
  id: string;
  tipo: "PF" | "PJ";
  status: string;
  nome?: string;
  cpf?: string;
  razao_social?: string;
  cnpj?: string;
  email?: string;
  telefone?: string;
  whatsapp?: string;
  cidade?: string;
  estado?: string;
  created_at: string;
}
export interface ProcessoPrincipal {
  id: string;
  numero_cnj?: string;
  instancia?: string;
  tribunal?: string;
  comarca?: string;
  vara?: string;
  classe?: string;
  fase?: string;
  valor_causa?: number;
  status?: string;
}
export interface Case {
  id: string;
  numero_interno?: string;
  titulo: string;
  area: string;
  status: string;
  fase: string;
  prioridade: string;
  risco?: string;
  risco_nivel?: string;
  numero_processo?: string;
  tribunal?: string;
  comarca?: string;
  vara?: string;
  parte_contraria?: string;
  valor_causa?: number;
  client_id: string;
  advogado_responsavel_id?: string;
  descricao_fatos?: string;
  tese_principal?: string;
  pontos_fortes?: string;
  pontos_fracos?: string;
  observacoes?: string;
  tipo_acao_prescricao?: string;
  data_prescricao?: string;
  archived_at?: string;
  archive_reason?: string;
  created_at: string;
  case_type?: string;
  extrajudicial_type?: string;
  has_judicial_process?: boolean;
  linked_judicial_case_id?: string;
  kanban_column?: string;
  kanban_position?: number;
  processo_principal?: ProcessoPrincipal;
}
export interface Deadline {
  id: string;
  titulo: string;
  tipo: string;
  prioridade: string;
  status: string;
  data_prazo: string;
  data_intimacao?: string;
  base_legal?: string;
  case_id?: string;
  responsavel_id?: string;
  ciencia_confirmada: boolean;
  confirmado: boolean;
  origem: "manual" | "datajud" | "importacao_ia";
  origem_documento_id: string | null;
  dias_restantes?: number;
  urgencia?: string;
  created_at: string;
}
export interface LegalDoc {
  id: string;
  titulo: string;
  tipo_peca: string;
  status: string;
  versao: number;
  ai_generated: boolean;
  human_reviewed: boolean;
  case_id?: string;
  conteudo?: string;
  validacao_juridica?: {
    status: string;
    apto_fluxo: boolean;
    score?: number | null;
    score_minimo?: number;
    veredito?: string | null;
    ai_log_id?: string | null;
    hitl?: string | null;
    motivo?: string;
  };
  created_at: string;
}
export interface Fee {
  id: string;
  tipo: string;
  status: string;
  descricao: string;
  valor?: number;
  data_vencimento?: string;
  data_pagamento?: string;
  client_id: string;
  case_id?: string;
  created_at: string;
}
export interface EnvCase {
  id: string;
  case_id: string;
  orgao_autuador: string;
  numero_auto: string;
  data_ciencia?: string;
  data_prazo_defesa?: string;
  status_defesa: string;
  valor_multa?: number;
  created_at: string;
}
// ── Autenticação ─────────────────────────────────────────
export interface AuthTokens {
  access_token: string;
  token_type?: string;
}
export interface LoginResponse extends AuthTokens {
  user_id: string;
  full_name: string;
  role: string;
  must_change_password?: boolean;
}

// ── Diário Oficial (IDs UUID string, alinhados ao modelo canônico) ──
export interface DiarioOficialKeyword {
  id: string;
  keyword: string;
  ativo: boolean;
}
export interface DiarioOficialAlerta {
  id: string;
  keyword: string;
  titulo: string;
  trecho: string;
  data_publicacao: string;
  fonte: string;
  lido: boolean;
  case_id?: string;
  /** Backend marca aqui quando a vinculação ao caso foi automática (nº CNJ). */
  observacao?: string | null;
}
export interface Paged<T> {
  data: T[];
  total: number;
  page: number;
  page_size: number;
}
