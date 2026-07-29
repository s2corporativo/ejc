// ── Tipos do EJC ─────────────────────────────────────────
export interface User {
  id: string;
  email: string;
  full_name: string;
  role: string;
  permissions?: string[];
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
  proxima_acao?: string;
  proxima_acao_prazo?: string;
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
/**
 * Mini-formulário OPCIONAL de honorários enviado na abertura do caso
 * (objeto `honorarios` no POST /cases/). Quando informado, alimenta o
 * contrato de prestação de serviços gerado automaticamente; se omitido,
 * o caso abre sem honorários e o contrato nasce com lacunas. Todos os
 * campos são opcionais (number | null / string | null).
 */
export interface CasoHonorariosInput {
  valor_contratual: number | null;
  percentual_exito: number | null;
  forma_pagamento: string | null;
  observacoes: string | null;
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
  codigo_peca?: string | null;
  area?: string | null;
  ai_generated: boolean;
  human_reviewed: boolean;
  case_id?: string | null;
  revisor_id?: string | null;
  conteudo?: string;
  /** Só no detalhe (LegalDocDetail): observações da revisão humana. */
  notas_revisao?: string | null;
  /** Só no detalhe (LegalDocDetail): comprovante de protocolo (FLX-070). */
  numero_protocolo?: string | null;
  protocolado_em?: string | null;
  protocolo_tribunal?: string | null;
  protocolo_comprovante_doc_id?: string | null;
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
  refresh_token?: string;
  token_type?: string;
}
export interface LoginResponse extends AuthTokens {
  user_id: string;
  full_name: string;
  role: string;
  must_change_password?: boolean;
  precisa_configurar_2fa?: boolean;
}

// ── NFS-e (notas fiscais de serviço) ─────────────────────
export type NfseStatus =
  "rascunho" | "processando" | "autorizada" | "rejeitada" | "cancelada";
export interface NfseStatusInfo {
  enabled: boolean;
  configured: boolean;
  ambiente?: string | null;
  provedor?: string | null;
  manual_disponivel: boolean;
  emissor_nacional_url?: string | null;
}
export interface NotaFiscal {
  id: string;
  fee_id?: string | null;
  client_id?: string | null;
  /** "manual" = nota emitida fora do sistema e registrada aqui. */
  provider: string;
  provider_id?: string | null;
  referencia?: string | null;
  ambiente?: string | null;
  status: NfseStatus;
  numero?: string | null;
  chave_acesso?: string | null;
  /** Backend serializa Decimal como string (ou null). */
  valor?: string | null;
  descricao?: string | null;
  pdf_url?: string | null;
  xml_url?: string | null;
  mensagem_erro?: string | null;
  data_emissao?: string | null;
  competencia?: string | null;
  motivo_cancelamento?: string | null;
  tem_pdf: boolean;
  tem_xml: boolean;
}
export interface NotaFiscalListResponse {
  items: NotaFiscal[];
  total: number;
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
