export type FinanceSeverity = "bloqueio" | "revisao" | "alta" | string;
export type FinanceTab =
  "visao" | "honorarios" | "despesas" | "comissoes" | string;

export interface FinanceAction {
  tab?: FinanceTab;
  status?: string;
  focus?: string;
  search?: string;
}

export interface FinanceExceptionRecord {
  id: string;
  label: string;
  value?: number;
  action?: FinanceAction;
}

export interface FinanceExceptionItem {
  codigo: string;
  titulo: string;
  qtd: number;
  valor?: number | string | null;
  severidade: FinanceSeverity;
  acao?: FinanceAction;
  registros?: FinanceExceptionRecord[];
}

export interface FinanceExceptionsResponse {
  competencia: string;
  itens: FinanceExceptionItem[];
  total: number;
  bloqueios?: number;
}

export interface FinanceConsolidated {
  competencia?: string;
  caixa_periodo?: number | string;
  margem_pct?: number | string;
  receitas?: {
    recebido_mes?: number | string;
    a_receber?: number | string;
    atrasado?: number | string;
    previsto?: {
      exito?: number | string;
      sucumbencia?: number | string;
    };
  };
  despesas?: {
    a_pagar?: number | string;
    saidas_caixa_mes?: number | string;
    fixo?: number | string;
    variavel?: number | string;
  };
  fluxo_caixa?: {
    entradas?: number | string;
    saidas?: number | string;
  };
}

export interface RentabilidadeCaso {
  case_id: string;
  client_id?: string | null;
  numero_interno?: string | null;
  caso?: string | null;
  cliente?: string | null;
  recebido?: number | string;
  despesas?: number | string;
  comissoes?: number | string;
  resultado?: number | string;
}

export interface RentabilidadeResponse {
  competencia: string;
  resumo: {
    recebido?: number | string;
    despesas_casos?: number | string;
    comissoes?: number | string;
    resultado_casos?: number | string;
    despesas_escritorio?: number | string;
    resultado_escritorio?: number | string;
  };
  casos: RentabilidadeCaso[];
  clientes?: Array<Record<string, unknown>>;
}

export interface FinanceClosing {
  id?: string;
  competencia: string;
  closed_at?: string;
  fechado?: boolean;
  snapshot?: Record<string, unknown>;
}

export interface PreClosingResponse {
  competencia: string;
  status: string;
  score_integridade: number;
  pode_fechar_persistente: boolean;
  bloqueios: FinanceExceptionItem[];
  revisoes: FinanceExceptionItem[];
  total_bloqueios: number;
  total_revisoes: number;
  snapshot?: Record<string, unknown>;
}

export interface DistributionAvailability {
  competencia: string;
  fechado: boolean;
  resultado_escritorio?: number | string;
  ja_distribuido?: number | string;
  disponivel?: number | string;
}

export interface FinanceApproval {
  id: string;
  entity_type: string;
  entity_id: string;
  amount: number | string;
  status: string;
  solicitado_por_nome?: string | null;
  aprovado_por_nome?: string | null;
}

export interface ReconciliationSuggestion {
  id: string;
  bank_transaction_id: string;
  bank_description?: string | null;
  bank_value?: number | string;
  target_type: "fee_payment" | "office_expense" | "commission_batch";
  target_id: string;
  label?: string | null;
  confidence?: number | string;
  status: string;
}

export interface ReconciliationResponse {
  analise?: { id?: string; arquivo_nome?: string | null };
  total_transacoes?: number;
  confirmados: number;
  pendentes: number;
  sugestoes: ReconciliationSuggestion[];
}

export interface MonthlyReport {
  mes?: string;
  mes_label?: string;
  aviso?: string;
  financeiro?: {
    recebido_mes?: number | string;
    resultado_mes?: number | string;
    pendente?: number | string;
    despesas_pendentes?: number | string;
  };
  casos?: {
    ativos?: number;
    novos_mes?: number;
  };
  prazos?: {
    vencidos_abertos?: number;
  };
}

export interface HonorariosResumo {
  pendente: number;
  atrasado: number;
  recebido_mes: number;
  percentuais_sem_valor?: number;
  escopo?: string;
}

export interface FeePaymentHistory {
  id: string;
  fee_id?: string;
  valor: number;
  estornado?: number;
  data_pagamento?: string;
  forma?: string | null;
  comprovante_doc_id?: string | null;
}

export interface FeeRefundHistory {
  id: string;
  valor: number;
  motivo?: string | null;
  data_estorno?: string;
  fee_payment_id?: string | null;
}

export interface FeeHistoryResponse {
  pagamentos: FeePaymentHistory[];
  estornos: FeeRefundHistory[];
  total_pago?: number;
  total_estornado?: number;
  saldo?: number;
}

export interface FeeRateioCalc {
  fee?: { caso_titulo?: string | null };
  bruto?: number | string;
  despesas_caso?: number | string;
  liquido?: number | string;
  titular?: {
    partner_id?: string | null;
    nome?: string | null;
    valor?: number | string;
  };
  escritorio?: { valor?: number | string };
}

export interface FeeRateioModal<TFee> {
  fee: TFee;
  calc?: FeeRateioCalc;
}

export interface FeeHistoryModal<TFee> {
  fee: TFee;
  loading: boolean;
  data?: FeeHistoryResponse;
}

export interface FeeFormState {
  tipo: string;
  descricao?: string;
  client_id?: string;
  case_id?: string;
  valor?: number | string;
  percentual_exito?: number | string;
  data_vencimento?: string;
}

export interface FeePaymentForm {
  valor?: number | string;
  data_pagamento?: string;
  forma?: string;
  comprovante_doc_id?: string;
}

export interface FeeRefundForm {
  valor?: number | string;
  data_estorno?: string;
  motivo?: string;
}

export interface FeeRefundModal {
  fee_id: string;
  payment_id: string;
  disponivel: number;
}

export interface PixConfig {
  chave?: string;
  nome?: string;
  cidade?: string;
}

export interface PixResult {
  copia_e_cola: string;
  [key: string]: unknown;
}

export interface CommissionSummary {
  a_aprovar?: number | string;
  a_pagar?: number | string;
  paga_periodo?: number | string;
  ajustes_pendentes?: number | string;
  [key: string]: unknown;
}

export interface CommissionLawyerSummary {
  advogado_id?: string | null;
  advogado?: string | null;
  recebido?: number | string;
  comissoes?: number | string;
  comissao_gerada?: number | string;
  comissao_paga?: number | string;
  pago?: number | string;
  saldo?: number | string;
}

export interface CommissionForecast {
  total?: number | string;
  indeterminadas?: number;
  [key: string]: unknown;
}

export interface CommissionConference {
  competencia?: string;
  pronto?: boolean;
  bloqueios?: number;
  itens: FinanceExceptionItem[];
}

export interface CommissionListResponse<TRow> {
  data: TRow[];
  resumo: CommissionSummary;
  por_advogado: CommissionLawyerSummary[];
}
export interface CommissionStatement {
  fechamento?: FinanceClosing | null;
  resumo?: {
    recebido?: number | string;
    comissoes?: number | string;
    pago?: number | string;
    ajustes_pendentes?: number | string;
  };
  por_advogado?: CommissionLawyerSummary[];
  data?: Array<Record<string, unknown>>;
}
