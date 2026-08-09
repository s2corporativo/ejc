import { describe, expect, it } from "vitest";
import type { Case, Client, Deadline } from "../../types";
import {
  buildCompanySummaries,
  companyDisplayName,
  extractCollection,
  isBusinessCase,
  isCriticalCase,
  nextCompanyDeadlines,
  type DptData,
} from "./model";

const company: Client = {
  id: "pj-1",
  tipo: "PJ",
  status: "ativo",
  razao_social: "Empresa Teste Ltda.",
  created_at: "2026-01-01T00:00:00Z",
};

const legalCase: Case = {
  id: "case-1",
  titulo: "Execução fiscal",
  area: "tributario",
  status: "aberto",
  fase: "execucao",
  prioridade: "critica",
  risco: "alto",
  client_id: company.id,
  created_at: "2026-01-02T00:00:00Z",
};

const deadline: Deadline = {
  id: "deadline-1",
  titulo: "Prazo de defesa",
  tipo: "processual",
  prioridade: "critica",
  status: "pendente",
  data_prazo: "2026-08-12",
  case_id: legalCase.id,
  ciencia_confirmada: false,
  confirmado: true,
  origem: "manual",
  origem_documento_id: null,
  created_at: "2026-08-01T00:00:00Z",
};

const data: DptData = {
  companies: [company],
  cases: [legalCase],
  deadlines: [deadline],
  degraded: [],
  truncated: [],
};

describe("DPT 360 — derivação sem score artificial", () => {
  it("considera apenas áreas empresariais explícitas", () => {
    expect(isBusinessCase(legalCase)).toBe(true);
    expect(isBusinessCase({ ...legalCase, area: "familia" })).toBe(false);
  });

  it("reconhece sinal crítico somente em caso não terminal", () => {
    expect(isCriticalCase(legalCase)).toBe(true);
    expect(isCriticalCase({ ...legalCase, status: "encerrado" })).toBe(false);
  });

  it("agrega casos e prazos por empresa sem duplicar cadastro", () => {
    const summaries = buildCompanySummaries(data);
    expect(summaries).toHaveLength(1);
    expect(summaries[0].cases).toEqual([legalCase]);
    expect(summaries[0].deadlines).toEqual([deadline]);
    expect(summaries[0].criticalSignals).toBe(1);
  });

  it("seleciona providências próximas usando a data local informada", () => {
    const now = new Date(2026, 7, 9, 12, 0, 0);
    expect(nextCompanyDeadlines(data, 7, now)).toEqual([deadline]);
    expect(nextCompanyDeadlines(data, 2, now)).toEqual([]);
  });

  it("tolera payload paginado e usa razão social como nome canônico", () => {
    expect(extractCollection<Client>({ data: [company], total: 1 })).toEqual({
      items: [company],
      total: 1,
    });
    expect(companyDisplayName(company)).toBe("Empresa Teste Ltda.");
  });
});
