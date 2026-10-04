import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

export const dynamic = "force-dynamic";

// GET /api/agent/runs — lista execuções do agente
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const caseId = url.searchParams.get("caseId") || "default-case";
  const status = url.searchParams.get("status");

  const where: { caseId?: string; status?: string } = { caseId };
  if (status) where.status = status;

  const runs = await db.agentRun.findMany({
    where,
    orderBy: { createdAt: "desc" },
    take: 20,
    include: { steps: { orderBy: { stepNo: "asc" } } },
  });

  return NextResponse.json({
    runs: runs.map((r) => ({
      id: r.id,
      caseId: r.caseId,
      agentSlug: r.agentSlug,
      taskType: r.taskType,
      status: r.status,
      tokensIn: r.tokensIn,
      tokensOut: r.tokensOut,
      tokensBudget: r.tokensBudget,
      costBrl: r.costBrl,
      hitlReason: r.hitlReason,
      hitlData: r.hitlData ? JSON.parse(r.hitlData) : null,
      errorCode: r.errorCode,
      startedAt: r.startedAt?.toISOString(),
      finishedAt: r.finishedAt?.toISOString(),
      createdAt: r.createdAt.toISOString(),
      stepsCount: r.steps.length,
      steps: r.steps.map((s) => ({
        id: s.id,
        stepNo: s.stepNo,
        kind: s.kind,
        toolName: s.toolName,
        status: s.status,
        tokensIn: s.tokensIn,
        tokensOut: s.tokensOut,
        durationMs: s.durationMs,
        requiresHuman: s.requiresHuman,
        output: JSON.parse(s.output || "{}"),
        createdAt: s.createdAt.toISOString(),
      })),
    })),
  });
}

// GET /api/agent/runs/{id} — detalhe de uma execução
export async function POST(req: NextRequest) {
  const url = new URL(req.url);
  const runId = url.searchParams.get("id");

  // Se tem id, é um resume
  if (runId) {
    let body: { decision?: "approve" | "reject" | "modify"; modifiedData?: Record<string, unknown> } = {};
    try { body = await req.json(); } catch { /* pode ser vazio */ }

    try {
      const { resumeAgentRun } = await import("@/lib/agent_loop");
      const result = await resumeAgentRun(runId, body.decision || "approve", body.modifiedData);
      return NextResponse.json(result);
    } catch (e) {
      return NextResponse.json({ error: e instanceof Error ? e.message : "Erro ao retomar" }, { status: 500 });
    }
  }

  // Senão, cria nova execução
  let body: { facts?: string; caseId?: string; maxSteps?: number; tokensBudget?: number } = {};
  try { body = await req.json(); } catch { return NextResponse.json({ error: "JSON inválido" }, { status: 400 }); }

  const facts = (body.facts || "").trim();
  if (facts.length < 30) {
    return NextResponse.json({ error: "Fatos insuficientes (mín. 30 caracteres)" }, { status: 400 });
  }

  try {
    // Importa tools (registra no registry)
    await import("@/lib/agent_tools");
    const { runAgentLoop } = await import("@/lib/agent_loop");

    const result = await runAgentLoop({
      caseId: body.caseId || "default-case",
      facts,
      maxSteps: body.maxSteps || 8,
      tokensBudget: body.tokensBudget || 20000,
    });

    return NextResponse.json(result);
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : "Erro no agent loop" }, { status: 500 });
  }
}
