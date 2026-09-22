import api from "../../lib/api";

export type DptCompany = {
  id: string;
  nome: string;
  status: string;
  cidade?: string | null;
  estado?: string | null;
  casos: number;
  casos_abertos: number;
  sinais_criticos: number;
  providencias_proximas: number;
};

export type DptCase = {
  id: string;
  client_id: string;
  titulo: string;
  area: string;
  status: string;
  prioridade: string;
  risco?: string | null;
  proxima_acao?: string | null;
  proxima_acao_prazo?: string | null;
};

export type DptDeadline = {
  id: string;
  case_id: string;
  titulo: string;
  data_prazo: string;
  status: string;
  prioridade: string;
  confirmado: boolean;
};

export type DptPriority = {
  tipo: "prazo" | "caso";
  nivel: "critico" | "alto" | "atencao";
  company_id: string;
  company_name: string;
  case_id: string;
  title: string;
  detail: string;
  canonical_path: string;
  due_date?: string | null;
  confirmado?: boolean | null;
};

export type DptDashboard = {
  generated_at: string;
  metrics: {
    empresas_acompanhadas: number;
    riscos_criticos: number;
    providencias_proximas: number;
    mudancas_juridicas_hoje: number | null;
    empresas_potencialmente_impactadas: number | null;
    diagnosticos_pendentes: number | null;
  };
  companies: DptCompany[];
  cases: DptCase[];
  deadlines: DptDeadline[];
  priorities: DptPriority[];
  radar_por_area?: Record<string, number> | null;
  coverage: "complete" | "partial";
  notes: string[];
};

export type DptHealthArea = {
  area: string;
  classificacao:
    "Regular" | "Atenção" | "Alto Risco" | "Crítico" | "Não avaliado";
  justificativa: string;
  evidencias: number;
};

export type DptTwinDimension = {
  key: string;
  label: string;
  status: "com_dados" | "sem_dados" | "nao_aplicavel";
  registros: number;
  note?: string | null;
  canonical_path?: string | null;
};

export type DptCompanyProfile = {
  id: string;
  nome: string;
  status: string;
  cidade?: string | null;
  estado?: string | null;
  generated_at: string;
  health: DptHealthArea[];
  twin: DptTwinDimension[];
  areas_com_casos: string[];
  casos_abertos: number;
  prazos_pendentes: number;
  documentos: number;
  sociedades: number;
  operacoes_lgpd: number;
  operacoes_lgpd_alto_risco: number;
  autos_ambientais: number;
  notes: string[];
};

export type DptAction = "conselho" | "preflight" | "diagnostico";

export type DptActionResponse = {
  action: DptAction;
  client_id: string;
  conteudo: string;
  estruturado?: Record<string, unknown> | null;
  fontes: Array<Record<string, unknown>>;
  citacoes: unknown[];
  alertas: string[];
  critica_adversarial?: Record<string, unknown> | null;
  is_rascunho: boolean;
  requer_revisao: boolean;
  status_hitl: string;
  aviso_hitl: string;
  log_id?: string | null;
};

export type DptDiagnosticKind =
  | "completo"
  | "tributario"
  | "ambiental"
  | "administrativo"
  | "trabalhista"
  | "contratual"
  | "lgpd"
  | "governanca_ia";

export type DptDiagnosticReadiness = {
  client_id: string;
  tipo: DptDiagnosticKind;
  generated_at: string;
  areas: Array<{
    area: string;
    estado: "com_evidencias" | "nao_avaliado";
    evidencias_disponiveis: Array<{
      tipo: string;
      presente: boolean;
      quantidade?: number | null;
    }>;
    lacunas_preliminares: string[];
    regra: string;
  }>;
  pode_iniciar_analise: boolean;
  persistencia: "nao_habilitada_nesta_pilha";
  motivo_persistencia: string;
  hitl: "obrigatorio";
};

export type DptOpportunityQueueItem = {
  intake_id: string;
  status: string;
  created_at?: string | null;
  origem?: string | null;
  urgencia_declarada?: string | null;
};

export async function getDptDashboard(): Promise<DptDashboard> {
  const response = await api.get<DptDashboard>("/dpt360/dashboard");
  return response.data;
}

export async function getDptCompanyProfile(
  clientId: string,
): Promise<DptCompanyProfile> {
  const response = await api.get<DptCompanyProfile>(
    `/dpt360/companies/${clientId}`,
  );
  return response.data;
}

export async function getDptDiagnosticReadiness(
  clientId: string,
  kind: DptDiagnosticKind,
): Promise<DptDiagnosticReadiness> {
  const response = await api.get<DptDiagnosticReadiness>(
    `/dpt360/diagnostics/readiness/${clientId}`,
    { params: { kind } },
  );
  return response.data;
}

export async function getDptOpportunityQueue(
  limit = 100,
): Promise<DptOpportunityQueueItem[]> {
  const response = await api.get<DptOpportunityQueueItem[]>(
    "/dpt360/intake/opportunities",
    { params: { limit } },
  );
  return response.data;
}

export async function runDptAction(payload: {
  action: DptAction;
  client_id: string;
  question: string;
  area?: string;
}): Promise<DptActionResponse> {
  const response = await api.post<DptActionResponse>(
    "/dpt360/actions",
    payload,
  );
  return response.data;
}

export type DptRadarImpact = {
  client_id: string;
  empresa: string;
  aderencia: "alta" | "media" | "baixa";
  fundamento: string;
  status: "possivel_impacto";
};

export type DptRadarItem = {
  id: string;
  fonte?: string | null;
  titulo?: string | null;
  resumo?: string | null;
  link?: string | null;
  data_publicacao?: string | null;
  area: string;
  estado_conhecimento: string;
  vigencia: string;
  rag: string;
  impactos: DptRadarImpact[];
};

export type DptRadarToday = {
  generated_at: string;
  periodo_horas: number;
  total_publicacoes: number;
  publicacoes_classificadas: number;
  por_area: Record<string, number>;
  empresas_potencialmente_impactadas: number;
  itens: DptRadarItem[];
  fontes_ativas: string[];
  dependencias_pendentes: string[];
  regra_impacto: string;
  cobertura: "completa" | "parcial";
};

export async function getDptRadarToday(hours = 24): Promise<DptRadarToday> {
  const response = await api.get<DptRadarToday>("/dpt360/radar/today", {
    params: { hours },
  });
  return response.data;
}

export type DptExecutiveReport = {
  client_id: string;
  empresa: string;
  periodo_dias: number;
  generated_at: string;
  status: "rascunho";
  requer_revisao: boolean;
  cobertura_completa: boolean;
  cobertura_notas: string[];
  situacao_juridica: Array<Record<string, unknown>>;
  principais_riscos: Array<Record<string, unknown>>;
  providencias_futuras: Array<Record<string, unknown>>;
  pendencias: Record<string, unknown>;
  casos: Array<Record<string, unknown>>;
  mudancas_juridicas_relevantes: Array<Record<string, unknown>>;
  recomendacoes: string[];
  proximos_passos: string[];
  nota: string;
  cobertura: "completa" | "parcial";
  notas_cobertura: string[];
};

export async function getDptExecutiveReport(
  clientId: string,
  days = 30,
): Promise<DptExecutiveReport> {
  const response = await api.get<DptExecutiveReport>(
    `/dpt360/reports/executive/${clientId}`,
    { params: { days } },
  );
  return response.data;
}
