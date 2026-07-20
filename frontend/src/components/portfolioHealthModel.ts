import type { HealthIndicator, HealthLevel } from "./caseHealthModel";

export type PortfolioCase = {
  id: string;
  numero_interno?: string | null;
  titulo: string;
  area?: string | null;
  prioridade?: string | null;
  risco?: string | null;
  advogado_responsavel?: string | null;
  last_activity_at?: string | null;
  inactive_days: number;
  score: number;
  level: HealthLevel;
  metrics: Record<string, number>;
  indicators: HealthIndicator[];
  next_recommended_action: string;
  route: string;
};

export type PortfolioResponse = {
  scope: "office" | "assigned";
  stale_days: number;
  limit: number;
  portfolio_total: number;
  returned: number;
  totals: Record<HealthLevel, number>;
  has_more: boolean;
  items: PortfolioCase[];
};

export const PORTFOLIO_LEVEL_LABELS: Record<HealthLevel, string> = {
  critical: "Crítico",
  risk: "Em risco",
  attention: "Atenção",
  healthy: "Saudável",
};

export const PORTFOLIO_LEVEL_TONE: Record<
  HealthLevel,
  "red" | "amber" | "green" | "slate"
> = {
  critical: "red",
  risk: "red",
  attention: "amber",
  healthy: "green",
};

export function principalMotivo(item: PortfolioCase): string {
  return (
    item.indicators?.[0]?.message ||
    item.next_recommended_action ||
    "Sem pendência crítica automática"
  );
}

export function ordenarCarteira(items: PortfolioCase[]): PortfolioCase[] {
  return [...items].sort((a, b) => {
    if (a.score !== b.score) return a.score - b.score;
    const overdueA = a.metrics.overdue_deadlines || 0;
    const overdueB = b.metrics.overdue_deadlines || 0;
    if (overdueA !== overdueB) return overdueB - overdueA;
    const criticalA = a.metrics.deadlines_next_3_days || 0;
    const criticalB = b.metrics.deadlines_next_3_days || 0;
    if (criticalA !== criticalB) return criticalB - criticalA;
    return b.inactive_days - a.inactive_days;
  });
}

export function detalheErroCarteira(error: unknown): string {
  const detail = (
    error as { response?: { data?: { detail?: unknown } } }
  )?.response?.data?.detail;
  return typeof detail === "string" && detail
    ? detail
    : "Não foi possível carregar a saúde operacional da carteira.";
}
