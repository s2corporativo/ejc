// case_memory.ts — Memória persistente de longo prazo por caso.
//
// Quando o usuário gera uma peça / debate / análise, salvamos:
//   - resumo do caso (caseFacts resumido em ~200 tokens)
//   - teses discutidas (lista de strings)
//   - decisões tomadas (pedidos, área, valor da causa)
//   - último acesso
//
// Na próxima sessão, podemos oferecer "Continuar caso X" como atalho.

import { db } from "@/lib/db";

export interface CaseMemory {
  caseId: string;
  resumo: string;
  teses: string[];
  decisoes: Record<string, unknown>;
  totalGeracoes: number;
  ultimoAcesso: Date;
}

export async function saveCaseMemory(input: {
  caseId: string;
  resumo: string;
  teses?: string[];
  decisao?: Record<string, unknown>;
}): Promise<void> {
  // Idempotent upsert por caseId
  const existing = await db.caseMemory.findUnique({ where: { caseId: input.caseId } });
  if (existing) {
    await db.caseMemory.update({
      where: { caseId: input.caseId },
      data: {
        resumo: input.resumo,
        teses: JSON.stringify([...JSON.parse(existing.teses) as string[], ...(input.teses ?? [])].slice(-50)),
        decisoes: JSON.stringify({ ...(JSON.parse(existing.decisoes) as Record<string, unknown>), ...input.decisao }),
        totalGeracoes: existing.totalGeracoes + 1,
        ultimoAcesso: new Date(),
      },
    });
  } else {
    await db.caseMemory.create({
      data: {
        caseId: input.caseId,
        resumo: input.resumo,
        teses: JSON.stringify(input.teses ?? []),
        decisoes: JSON.stringify(input.decisao ?? {}),
        totalGeracoes: 1,
      },
    });
  }
}

export async function getCaseMemory(caseId: string): Promise<CaseMemory | null> {
  const row = await db.caseMemory.findUnique({ where: { caseId } });
  if (!row) return null;
  return {
    caseId: row.caseId,
    resumo: row.resumo,
    teses: JSON.parse(row.teses),
    decisoes: JSON.parse(row.decisoes),
    totalGeracoes: row.totalGeracoes,
    ultimoAcesso: row.ultimoAcesso,
  };
}

export async function listRecentCaseMemory(limit: number = 10): Promise<CaseMemory[]> {
  const rows = await db.caseMemory.findMany({
    orderBy: { ultimoAcesso: "desc" },
    take: limit,
  });
  return rows.map((row) => ({
    caseId: row.caseId,
    resumo: row.resumo,
    teses: JSON.parse(row.teses),
    decisoes: JSON.parse(row.decisoes),
    totalGeracoes: row.totalGeracoes,
    ultimoAcesso: row.ultimoAcesso,
  }));
}