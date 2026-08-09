import api from "../../lib/api";

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
  por_area: Record<string, number>;
  empresas_potencialmente_impactadas: number;
  itens: DptRadarItem[];
  fontes_ativas: string[];
  dependencias_pendentes: string[];
  regra_impacto: string;
};

export async function getDptRadarToday(hours = 24): Promise<DptRadarToday> {
  const response = await api.get<DptRadarToday>("/dpt360/radar/today", { params: { hours } });
  return response.data;
}
