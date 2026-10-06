// /api/analyze-juiz — Análise prévia do juiz sobre uma peça ou caso.
//
// Diferente do /api/debate (multi-agente), este endpoint produz a análise
// individual do Estado-juiz em um único turno: admissibilidade + mérito
// + dispositivo sugerido.

import { NextRequest, NextResponse } from "next/server";
import { llmCall } from "@/lib/llm";
import { logAuditEvent, logUsageEntry } from "@/lib/audit";
import { ensureDraftMarker } from "@/lib/ai_governance";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

interface Body {
  caseId?: string | null;
  fatosCaso: string;
  textoPeca?: string;        // opcional — se informada, análise de admissibilidade
  areaJuridica?: string;
  tipoPeca?: "peticao_inicial" | "contestacao" | "recurso" | "denuncia";
}

const SISTEMA = `Você é um juiz brasileiro, especializado em análise processual.
Sua tarefa é produzir a ANÁLISE PRÉVIA do caso, antes do protocolo/protocolada a peça.

## I. ADMISSIBILIDADE
   - Competência (CPC art. 42-62)
   - Legitimidade (CPC art. 17)
   - Interesse processual (CPC art. 17 §1º)
   - Pressupostos processuais
   - Condições da ação
${(tipoPeca: string, area: string) => tipoPeca ? `   - Requisitos específicos da ${tipoPeca} (CPC art. 319 / CPP art. 395-397)` : ""}
   - Veredito: ADMITIDA / INADMITIDA (com motivo)

## II. MÉRITO
   - Probabilidade de procedência: alta | media | baixa
   - 3 pontos fortes da tese
   - 3 pontos fracos / riscos
   - Provas essenciais a produzir
   - Fundamentos normativos principais

## III. CONSECTÁRIOS
   - Honorários advocatícios (sucumbência)
   - Custas processuais
   - Prequestionamento para recurso

REGRAS:
- NUNCA prometa resultado (vedação EOAB art. 2º §1º)
- Marque o texto como RASCUNHO (revisão humana)
- Use pseudonimização: [NOME_1], [CPF_1]`;

export async function POST(req: NextRequest) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }
  if (!body.fatosCaso || body.fatosCaso.trim().length < 50) {
    return NextResponse.json(
      { error: "fatosCaso obrigatório (mínimo 50 caracteres)" },
      { status: 400 },
    );
  }

  const userPrompt = `## Área: ${body.areaJuridica ?? "cível"}
${body.tipoPeca ? `## Tipo de peça analisada: ${body.tipoPeca}` : ""}

## Fatos do caso
${body.fatosCaso.slice(0, 3000)}
${body.textoPeca ? `\n## Peça apresentada\n${body.textoPeca.slice(0, 4000)}` : ""}`;

  try {
    const result = await llmCall(SISTEMA, userPrompt, {
      taskType: body.areaJuridica?.includes("penal") ? "criminal" : "analise_caso",
      temperature: 0.2,
      maxTokens: 2500,
    });

    await logAuditEvent({
      action: "analyze_juiz",
      resource: "judge_simulator",
      resourceId: body.caseId ?? null,
      metadata: { area: body.areaJuridica, tipoPeca: body.tipoPeca, provider: result.provider, fallback: result.fallback },
    });
    await logUsageEntry({
      type: "debit",
      operation: "analyze_juiz",
      amount: -8,
      reason: "Análise prévia do juiz",
      metadata: { caseId: body.caseId, tokens: result.tokensUsed, latencyMs: result.latencyMs },
    });

    return NextResponse.json({
      ok: true,
      analise: ensureDraftMarker(result.content),
      provider: result.provider,
      fallback: result.fallback,
      latencyMs: result.latencyMs,
    });
  } catch (err) {
    return NextResponse.json(
      { error: "Falha na análise do juiz", detail: (err as Error).message },
      { status: 500 },
    );
  }
}