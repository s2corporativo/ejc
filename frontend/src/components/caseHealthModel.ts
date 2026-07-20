export type HealthLevel = "healthy" | "attention" | "risk" | "critical";

export type HealthIndicator = {
  code: string;
  severity: "low" | "medium" | "high" | "critical";
  message: string;
  recommended_action: string;
  count?: number;
};

export type CaseHealth = {
  score: number;
  level: HealthLevel;
  last_activity_at: string;
  inactive_days: number;
  next_recommended_action: string;
  metrics: Record<string, number>;
  indicators: HealthIndicator[];
};

export type TimelineItem = {
  id: string;
  kind: string;
  title: string;
  description?: string | null;
  status?: string | null;
  source: string;
  occurred_at: string;
};

export type TimelineResponse = {
  items: TimelineItem[];
  truncated: boolean;
  has_more: boolean;
  saturated_sources: string[];
};

export const LEVEL_LABELS: Record<HealthLevel, string> = {
  healthy: "Saudável",
  attention: "Atenção",
  risk: "Em risco",
  critical: "Crítico",
};

export const SEVERITY_LABELS: Record<HealthIndicator["severity"], string> = {
  low: "Informativo",
  medium: "Atenção",
  high: "Alto",
  critical: "Crítico",
};

export const SOURCE_LABELS: Record<string, string> = {
  case_movimentos: "Andamento",
  processes: "Processo",
  documents: "Documento",
  deadlines: "Prazo",
  tasks: "Tarefa",
  atendimentos: "Atendimento",
  legal_docs: "Peça",
};

export function detalheErroSaude(error: unknown): string {
  const detail = (
    error as { response?: { data?: { detail?: unknown } } }
  )?.response?.data?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (
    detail &&
    typeof detail === "object" &&
    typeof (detail as { mensagem?: unknown }).mensagem === "string"
  ) {
    return (detail as { mensagem: string }).mensagem;
  }
  return "Não foi possível carregar a saúde operacional do caso.";
}

export function formatarDataEvento(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Data não informada";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(parsed);
}

export function ordenarIndicadores(
  indicators: HealthIndicator[],
): HealthIndicator[] {
  const rank: Record<HealthIndicator["severity"], number> = {
    critical: 4,
    high: 3,
    medium: 2,
    low: 1,
  };
  return [...indicators].sort(
    (a, b) => rank[b.severity] - rank[a.severity],
  );
}
