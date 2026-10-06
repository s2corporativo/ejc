// /api/debate/start — Inicia um debate e executa o turno 1 (Advogado).

import { NextRequest, NextResponse } from "next/server";
import { createDebate, updateDebateStatus } from "@/lib/debate_audit";
import { executeTurn1 } from "@/lib/debate_orchestrator";
import { logAuditEvent, logUsageEntry } from "@/lib/audit";
import { ensureDraftMarker } from "@/lib/ai_governance";

export const dynamic = "force-dynamic";
export const maxDuration = 180;

interface StartBody {
  caseId?: string | null;
  ramoJuridico: string;
  facts: string;
  parteAutora: string;
  parteRe: string;
  ladoAdvogado?: "autor" | "reu";
}

export async function POST(req: NextRequest) {
  let body: StartBody;
  try {
    body = (await req.json()) as StartBody;
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }

  if (!body.ramoJuridico || !body.facts || !body.parteAutora || !body.parteRe) {
    return NextResponse.json(
      { error: "Campos obrigatórios: ramoJuridico, facts, parteAutora, parteRe" },
      { status: 400 },
    );
  }

  // Marca como rascunho
  body.facts = ensureDraftMarker(body.facts);

  const debate = await createDebate({
    caseId: body.caseId ?? null,
    ramoJuridico: body.ramoJuridico,
    facts: body.facts,
    parteAutora: body.parteAutora,
    parteRe: body.parteRe,
    ladoAdvogado: body.ladoAdvogado ?? "autor",
  });

  try {
    const turn = await executeTurn1({
      debateId: debate.id,
      caseId: debate.caseId,
      ramoJuridico: body.ramoJuridico,
      facts: body.facts,
      parteAutora: body.parteAutora,
      parteRe: body.parteRe,
      ladoAdvogado: body.ladoAdvogado ?? "autor",
    });

    await logAuditEvent({
      action: "debate_turn",
      resource: "multi_agent_debate",
      resourceId: debate.id,
      metadata: { turn: 1, persona: "advogado", artifactKind: turn.artifactKind },
    });
    await logUsageEntry({
      type: "debit",
      operation: "debate_turn1",
      amount: -5,
      reason: `Turno 1 do debate ${debate.id}`,
      metadata: { debateId: debate.id, caseId: debate.caseId, tokens: turn.tokensUsed, latencyMs: turn.latencyMs },
    });

    return NextResponse.json({
      debateId: debate.id,
      currentTurn: 1,
      turn,
      nextIndex: 2,
    });
  } catch (err) {
    await updateDebateStatus({
      id: debate.id,
      status: "erro",
      inadmissibilidade: `Erro no turno 1: ${(err as Error).message}`,
    });
    return NextResponse.json(
      { error: "Falha ao executar turno 1", debateId: debate.id, detail: (err as Error).message },
      { status: 500 },
    );
  }
}