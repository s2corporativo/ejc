// /api/debate/next — Avança para o próximo turno do debate.
//
// Recebe o debateId e o nextIndex; carrega os turnos anteriores do banco
// e despacha para o executor do orquestrador.

import { NextRequest, NextResponse } from "next/server";
import { getDebate, listDebateTurns, updateDebateStatus } from "@/lib/debate_audit";
import { executeTurn, nextTurnIndex } from "@/lib/debate_orchestrator";
import { logAuditEvent, logUsageEntry } from "@/lib/audit";

export const dynamic = "force-dynamic";
export const maxDuration = 180;

interface NextBody {
  debateId: string;
}

export async function POST(req: NextRequest) {
  let body: NextBody;
  try {
    body = (await req.json()) as NextBody;
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }

  if (!body.debateId) {
    return NextResponse.json({ error: "debateId obrigatório" }, { status: 400 });
  }

  const debate = await getDebate(body.debateId);
  if (!debate) {
    return NextResponse.json({ error: "Debate não encontrado" }, { status: 404 });
  }

  if (debate.status === "concluido" || debate.status === "inadmitido" || debate.status === "cancelado" || debate.status === "erro") {
    return NextResponse.json(
      { error: "Debate já encerrado", status: debate.status, inadmitido: !!debate.inadmissibilidade },
      { status: 409 },
    );
  }

  const turns = await listDebateTurns(debate.id);
  const currentIndex = turns.length > 0 ? turns[turns.length - 1].turnNumber : 0;
  const next = nextTurnIndex(currentIndex, !!debate.inadmissibilidade);
  if (!next) {
    return NextResponse.json(
      { error: "Não há próximo turno", currentIndex, inadmitido: !!debate.inadmissibilidade },
      { status: 409 },
    );
  }

  const cfg = (debate.parteConfig ?? {}) as { lado?: "autor" | "reu"; parteAutora?: string; parteRe?: string };
  const ladoAdvogado = cfg.lado ?? "autor";
  const parteAutora = cfg.parteAutora ?? "[AUTOR]";
  const parteRe = cfg.parteRe ?? "[REU]";

  try {
    const turn = await executeTurn({
      debateId: debate.id,
      ramoJuridico: debate.ramoJuridico,
      facts: debate.factsInput,
      parteAutora,
      parteRe,
      ladoAdvogado,
      nextIndex: next,
      turnsAnteriores: turns,
    });

    await logAuditEvent({
      action: "debate_turn",
      resource: "multi_agent_debate",
      resourceId: debate.id,
      metadata: { turn: next, persona: turn.persona, artifactKind: turn.artifactKind },
    });
    await logUsageEntry({
      type: "debit",
      operation: `debate_turn${next}`,
      amount: -5,
      reason: `Turno ${next} do debate ${debate.id}`,
      metadata: { debateId: debate.id, caseId: debate.caseId, tokens: turn.tokensUsed, latencyMs: turn.latencyMs },
    });

    // Encerrar debate se inadmitido ou sentença finalizada
    if (turn.finished) {
      await updateDebateStatus({
        id: debate.id,
        status: turn.inadmitido ? "inadmitido" : "concluido",
        inadmitido: turn.inadmitido,
      });
    }

    return NextResponse.json({
      debateId: debate.id,
      currentTurn: turn.index,
      turn,
      nextIndex: nextTurnIndex(turn.index, !!turn.inadmitido),
      finished: !!turn.finished,
    });
  } catch (err) {
    await updateDebateStatus({
      id: debate.id,
      status: "erro",
      inadmissibilidade: `Erro no turno ${next}: ${(err as Error).message}`,
    });
    return NextResponse.json(
      { error: `Falha ao executar turno ${next}`, detail: (err as Error).message },
      { status: 500 },
    );
  }
}