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
  coverage: "complete";
  notes: string[];
};

export async function getDptDashboard(): Promise<DptDashboard> {
  const response = await api.get<DptDashboard>("/dpt360/dashboard");
  return response.data;
}
