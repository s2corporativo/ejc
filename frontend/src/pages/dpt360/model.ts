import type { Case, Client, Deadline } from "../../types";

export const BUSINESS_AREAS = new Set([
  "empresarial",
  "tributario",
  "ambiental",
  "administrativo",
  "trabalhista",
  "contratual",
  "societario",
  "licitacoes",
  "digital_lgpd",
  "bancario",
  "agrario",
  "agronegocio",
]);

export const HEALTH_AREAS = [
  "Tributário",
  "Ambiental",
  "Administrativo",
  "Trabalhista",
  "Contratual",
  "LGPD",
  "Governança de IA",
] as const;

export type DptData = {
  companies: Client[];
  cases: Case[];
  deadlines: Deadline[];
  degraded: string[];
  truncated: string[];
};

export type CompanySummary = {
  company: Client;
  cases: Case[];
  deadlines: Deadline[];
  criticalSignals: number;
};

export function extractCollection<T>(payload: unknown): {
  items: T[];
  total: number;
} {
  if (Array.isArray(payload)) return { items: payload as T[], total: payload.length };
  if (!payload || typeof payload !== "object") return { items: [], total: 0 };
  const record = payload as Record<string, unknown>;
  const items = Array.isArray(record.data)
    ? (record.data as T[])
    : Array.isArray(record.items)
      ? (record.items as T[])
      : [];
  const total = typeof record.total === "number" ? record.total : items.length;
  return { items, total };
}

export function isBusinessCase(item: Case): boolean {
  return BUSINESS_AREAS.has(item.area);
}

export function isOpenCase(item: Case): boolean {
  return !["encerrado", "arquivado"].includes(item.status);
}

export function isCriticalCase(item: Case): boolean {
  const risk = (item.risco_nivel || item.risco || "").toLowerCase();
  return isOpenCase(item) && (item.prioridade === "critica" || risk === "alto" || risk === "critico");
}

export function localIsoDate(date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function addLocalDays(base: Date, days: number): string {
  const next = new Date(base.getFullYear(), base.getMonth(), base.getDate() + days);
  return localIsoDate(next);
}

export function deadlineIsPending(item: Deadline): boolean {
  return item.status === "pendente" || item.status === "vencido";
}

export function buildCompanySummaries(data: DptData): CompanySummary[] {
  const caseByCompany = new Map<string, Case[]>();
  for (const item of data.cases.filter(isBusinessCase)) {
    caseByCompany.set(item.client_id, [...(caseByCompany.get(item.client_id) || []), item]);
  }

  const deadlineByCase = new Map<string, Deadline[]>();
  for (const deadline of data.deadlines.filter(deadlineIsPending)) {
    if (!deadline.case_id) continue;
    deadlineByCase.set(deadline.case_id, [
      ...(deadlineByCase.get(deadline.case_id) || []),
      deadline,
    ]);
  }

  return data.companies.map((company) => {
    const cases = caseByCompany.get(company.id) || [];
    const deadlines = cases.flatMap((item) => deadlineByCase.get(item.id) || []);
    return {
      company,
      cases,
      deadlines,
      criticalSignals: cases.filter(isCriticalCase).length,
    };
  });
}

export function nextCompanyDeadlines(data: DptData, days = 7, now = new Date()): Deadline[] {
  const companyIds = new Set(data.companies.map((company) => company.id));
  const companyCaseIds = new Set(
    data.cases
      .filter((item) => companyIds.has(item.client_id) && isBusinessCase(item))
      .map((item) => item.id),
  );
  const end = addLocalDays(now, days);
  return data.deadlines
    .filter(
      (deadline) =>
        Boolean(deadline.case_id && companyCaseIds.has(deadline.case_id)) &&
        deadlineIsPending(deadline) &&
        deadline.data_prazo <= end,
    )
    .sort((a, b) => a.data_prazo.localeCompare(b.data_prazo));
}

export function companyDisplayName(company: Client): string {
  return company.razao_social || company.nome || "Empresa sem razão social";
}
