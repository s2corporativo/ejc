// debate_audit.ts — Persistência dos debates multi-agente (Tribunal).
//
// Salva cada DebateTurn e consulta a sequência completa de um debate.
// Encapsula a complexidade do Prisma (cliente) para que o orchestrator
// permaneça em lógica pura.

import { db } from "@/lib/db";
import type { PersonaSlug } from "@/lib/personas";

export interface DebateTurnRecord {
  id: string;
  debateId: string;
  turnNumber: number;
  persona: PersonaSlug;
  subRole: string; // "tese" | "contrario" | "admissibilidade" | "replica" | "sentenca"
  content: string;
  citations: { diploma: string; numero: string; url: string | null; verified: boolean }[];
  tokensUsed: number;
  latencyMs: number;
  status: string; // "ok" | "error"
  createdAt: Date;
}

export interface SaveDebateTurnInput {
  debateId: string;
  turnNumber: number;
  persona: PersonaSlug;
  subRole: string;
  content: string;
  citations: { diploma: string; numero: string; url: string | null; verified: boolean }[];
  tokensUsed: number;
  latencyMs: number;
  status?: string;
}

export async function saveDebateTurn(input: SaveDebateTurnInput): Promise<DebateTurnRecord> {
  const row = await db.debateTurn.create({
    data: {
      debateId: input.debateId,
      turnNumber: input.turnNumber,
      persona: input.persona,
      subRole: input.subRole,
      content: input.content,
      citations: JSON.stringify(input.citations),
      tokensUsed: input.tokensUsed,
      latencyMs: input.latencyMs,
      status: input.status ?? "ok",
    },
  });

  return {
    id: row.id,
    debateId: row.debateId,
    turnNumber: row.turnNumber,
    persona: row.persona as PersonaSlug,
    subRole: row.subRole,
    content: row.content,
    citations: JSON.parse(row.citations),
    tokensUsed: row.tokensUsed,
    latencyMs: row.latencyMs,
    status: row.status,
    createdAt: row.createdAt,
  };
}

export async function listDebateTurns(debateId: string): Promise<DebateTurnRecord[]> {
  const rows = await db.debateTurn.findMany({
    where: { debateId },
    orderBy: { turnNumber: "asc" },
  });

  return rows.map((row) => ({
    id: row.id,
    debateId: row.debateId,
    turnNumber: row.turnNumber,
    persona: row.persona as PersonaSlug,
    subRole: row.subRole,
    content: row.content,
    citations: JSON.parse(row.citations),
    tokensUsed: row.tokensUsed,
    latencyMs: row.latencyMs,
    status: row.status,
    createdAt: row.createdAt,
  }));
}

export interface MultiAgentDebateRecord {
  id: string;
  caseId: string;
  userId: string | null;
  ramoJuridico: string;
  area: string;
  title: string;
  factsInput: string;
  parteConfig: unknown;
  status: string;
  inadmissibilidade: string | null;
  veredito: string | null;
  totalTokens: number;
  hipoteseFinal: string | null;
  createdAt: Date;
  updatedAt: Date;
}

export async function createDebate(input: {
  caseId?: string | null;
  ramoJuridico: string;
  facts: string;
  parteAutora: string;
  parteRe: string;
  ladoAdvogado: "autor" | "reu";
}): Promise<MultiAgentDebateRecord> {
  const row = await db.multiAgentDebate.create({
    data: {
      caseId: input.caseId ?? "default-case",
      ramoJuridico: input.ramoJuridico,
      area: input.ramoJuridico,
      title: `Debate ${input.ramoJuridico} — ${input.parteAutora} vs ${input.parteRe}`.slice(0, 200),
      factsInput: input.facts,
      parteConfig: JSON.stringify({
        lado: input.ladoAdvogado,
        parteAutora: input.parteAutora,
        parteRe: input.parteRe,
        nomeAdversario: input.ladoAdvogado === "autor" ? input.parteRe : input.parteAutora,
      }),
      status: "em_andamento",
    },
  });

  return mapDebate(row);
}

export async function getDebate(id: string): Promise<MultiAgentDebateRecord | null> {
  const row = await db.multiAgentDebate.findUnique({ where: { id } });
  return row ? mapDebate(row) : null;
}

export async function listDebatesByCase(caseId: string): Promise<MultiAgentDebateRecord[]> {
  const rows = await db.multiAgentDebate.findMany({
    where: { caseId },
    orderBy: { createdAt: "desc" },
  });
  return rows.map(mapDebate);
}

export async function updateDebateStatus(input: {
  id: string;
  status: string;
  inadmitido?: boolean;
  inadmissibilidade?: string;
  veredito?: string;
  hipoteseFinal?: string;
}): Promise<void> {
  await db.multiAgentDebate.update({
    where: { id: input.id },
    data: {
      status: input.status,
      inadmissibilidade: input.inadmitido ? (input.inadmissibilidade ?? "Inadmitido pelo Juiz no turno 3") : input.inadmissibilidade,
      veredito: input.veredito ?? null,
      hipoteseFinal: input.hipoteseFinal ?? null,
    },
  });
}

function mapDebate(row: {
  id: string;
  caseId: string;
  userId: string | null;
  ramoJuridico: string;
  area: string;
  title: string;
  factsInput: string;
  parteConfig: string;
  status: string;
  inadmissibilidade: string | null;
  veredito: string | null;
  totalTokens: number;
  hipoteseFinal: string | null;
  createdAt: Date;
  updatedAt: Date;
}): MultiAgentDebateRecord {
  return {
    id: row.id,
    caseId: row.caseId,
    userId: row.userId,
    ramoJuridico: row.ramoJuridico,
    area: row.area,
    title: row.title,
    factsInput: row.factsInput,
    parteConfig: row.parteConfig ? JSON.parse(row.parteConfig) : null,
    status: row.status,
    inadmissibilidade: row.inadmissibilidade,
    veredito: row.veredito,
    totalTokens: row.totalTokens,
    hipoteseFinal: row.hipoteseFinal,
    createdAt: row.createdAt,
    updatedAt: row.updatedAt,
  };
}