// ── Tipos do módulo Visual Law (contrato /visual-law do backend) ─────────────

// GET /visual-law/casos/{case_id}/timeline
export type FaseStatus = "concluida" | "atual" | "futura";

export interface TimelineFase {
  fase: string;
  label: string;
  status: FaseStatus;
}

export type CategoriaEvento =
  | "movimento"
  | "prazo"
  | "documento"
  | "honorario"
  | "atividade";

export interface TimelineEvento {
  data: string;
  categoria: CategoriaEvento;
  tipo: string;
  descricao: string;
}

export type OrigemPasso = "prazo" | "estimativa";

export interface ProximoPasso {
  titulo: string;
  origem: OrigemPasso;
  data_estimada: string | null;
  detalhe: string;
}

export type NivelEstagnacao = "ok" | "atencao" | "critico";

export interface Estagnacao {
  dias_parado: number;
  nivel: NivelEstagnacao;
}

export interface VisualLawTimeline {
  case_id: string;
  fases: TimelineFase[];
  eventos: TimelineEvento[];
  proximos_passos: ProximoPasso[];
  estagnacao: Estagnacao;
}

// GET /visual-law/casos/{case_id}/matriz-risco
export type NivelProbabilidade = "remoto" | "possivel" | "provavel";
export type NivelImpacto = "baixo" | "medio" | "alto" | "indefinido";
export type NivelQuadrante = "baixo" | "moderado" | "elevado" | "critico";
export type TratamentoContabil =
  | "provisionar"
  | "divulgar_em_nota"
  | "nao_divulgar";

export interface MatrizCelula {
  nivel: string;
  label: string;
}

export interface MatrizRiscoResponse {
  probabilidade: {
    nivel: NivelProbabilidade;
    fonte: "risco_cadastrado" | "score_saude";
  };
  impacto: {
    nivel: NivelImpacto;
    valor_causa: number | null;
  };
  quadrante: {
    /** 0..2 — probabilidade (remoto → provável) */
    x: number;
    /** 0..2 — impacto (baixo → alto) */
    y: number;
    nivel: NivelQuadrante;
    tratamento_contabil: TratamentoContabil;
  };
  /** 3 linhas (impacto) × 3 colunas (probabilidade) */
  matriz: MatrizCelula[][];
}

// GET /visual-law/casos/{case_id}/alertas
export type SeveridadeBadge = "info" | "atencao" | "critica";
export type ClassificacaoSaude = "saudavel" | "atencao" | "risco" | "critico";

export interface AlertaBadge {
  codigo: string;
  severidade: SeveridadeBadge;
  label: string;
  detalhe: string;
  pulsante: boolean;
}

export interface AlertasResponse {
  score: number;
  classificacao: ClassificacaoSaude;
  badges: AlertaBadge[];
}

// POST /visual-law/breakeven
export type SelicFonte = "bcb" | "fallback" | "informada";

export interface BreakevenRequest {
  valor_causa: number;
  /** 0..1 */
  prob_exito: number;
  tempo_anos?: number;
  tribunal?: string;
  custas_pct?: number;
  honorarios_sucumbencia_pct?: number;
  selic_anual?: number;
  case_id?: string;
}

export interface BreakevenParametros {
  valor_causa: number;
  prob_exito: number;
  tempo_anos: number;
  tribunal: string | null;
  selic_anual: number;
  selic_fonte: SelicFonte;
  custas_pct: number;
  honorarios_sucumbencia_pct: number;
}

export interface BreakevenResponse {
  parametros: BreakevenParametros;
  valor_esperado: number;
  custos_estimados: number;
  vpl_litigio: number;
  sugestao_acordo: number;
  breakeven: number;
  comparativo: {
    litigio_vpl: number;
    acordo_imediato_equivalente: number;
    custo_do_tempo: number;
  };
  memoria_calculo: string[];
}
