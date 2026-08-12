import api from "../../lib/api";

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
  // A1 (auditoria 2026-08-12): qualquer seção truncada no teto próprio ou no
  // recorte agregado do cockpit entra aqui — nunca é apresentado recorte como completo.
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
