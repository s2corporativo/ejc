export const FINANCE_STATUS = {
  pendente: "Pendente",
  atrasado: "Em atraso",
  pago: "Pago",
  cancelado: "Cancelado",
} as const;

export const FINANCE_CATEGORIES = [
  "infraestrutura",
  "tecnologia",
  "pessoal",
  "oab",
  "marketing",
  "operacao",
  "fiscal",
  "investimento",
  "outro",
] as const;

export const FINANCE_CATEGORY_LABELS: Record<string, string> = {
  infraestrutura: "Infraestrutura",
  tecnologia: "Tecnologia",
  pessoal: "Pessoal / Pró-labore",
  oab: "OAB / Anuidade",
  marketing: "Marketing",
  operacao: "Operação",
  fiscal: "Fiscal / Contábil",
  investimento: "Investimento",
  outro: "Outros",
};

export function formatCurrency(
  value: number | string | null | undefined,
): string {
  const parsed = Number(value ?? 0);
  return (Number.isFinite(parsed) ? parsed : 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}

export function isFinanceCompetence(
  value: string | null | undefined,
): value is string {
  return !!value && /^\d{4}-(0[1-9]|1[0-2])$/.test(value);
}

export function currentFinanceCompetence(date = new Date()): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

export function nextFinanceCompetence(date = new Date()): string {
  return currentFinanceCompetence(
    new Date(date.getFullYear(), date.getMonth() + 1, 1),
  );
}

export function financeCompetenceLabel(competencia: string): string {
  if (!isFinanceCompetence(competencia)) return competencia;
  const [ano, mes] = competencia.split("-");
  return `${mes}/${ano}`;
}
