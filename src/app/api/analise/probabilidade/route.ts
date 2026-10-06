// /api/analise/probabilidade — Decomposição de probabilidade por etapa processual.
//
// Em vez de "alta/média/baixa" genérica, retorna probabilidades separadas:
//   - Admissibilidade (30%, 60%, 90%)
//   - Procedência do pedido principal (40%)
//   - Procedência do pedido subsidiário (60%)
//   - Recurso procedente (50%)
// Cada item com justificativa + principais riscos.

import { NextRequest, NextResponse } from "next/server";
import { llmCall } from "@/lib/llm";
import { logAuditEvent } from "@/lib/audit";
import { ensureDraftMarker } from "@/lib/ai_governance";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

interface Body {
  areaJuridica: string;
  fatos: string;
  pedidos: string;
  tipoPeca?: string;
  provas?: string;
  precedentes?: string;
}

const SISTEMA = `Você é um advogado sênior brasileiro especialista em análise de risco processual.
Sua tarefa é estimar a probabilidade de sucesso de cada etapa processual, COM JUSTIFICATIVA.

Responda em JSON:
{
  "admissibilidade": {
    "probabilidade": 0-100,
    "principais_riscos": [str],
    "fundamentos": [str]
  },
  "procedencia_principal": {
    "probabilidade": 0-100,
    "principais_riscos": [str],
    "fundamentos": [str],
    "valor_estimado": str  // faixa esperada
  },
  "procedencia_subsidiaria": {
    "probabilidade": 0-100,
    "principais_riscos": [str],
    "fundamentos": [str]
  },
  "recurso_procedente": {
    "probabilidade": 0-100,
    "principais_riscos": [str],
    "fundamentos": [str]
  },
  "resumo_executivo": str
}

Regras:
- NUNCA prometa resultado (vedação EOAB)
- Use [NOME_1] para pseudonimizar
- Probabilidades são HIPÓTESES, não certezas
- Apresente MARGEM DE INCERTEZA quando os fatos forem ambíguos`;

export async function POST(req: NextRequest) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }
  if (!body.fatos || !body.areaJuridica) {
    return NextResponse.json({ error: "fatos e areaJuridica obrigatórios" }, { status: 400 });
  }

  const userPrompt = `## Área: ${body.areaJuridica}
${body.tipoPeca ? `## Tipo: ${body.tipoPeca}` : ""}
${body.provas ? `## Provas disponíveis: ${body.provas}` : ""}
${body.precedentes ? `## Precedentes: ${body.precedentes}` : ""}

## Fatos
${body.fatos.slice(0, 2500)}

## Pedidos
${body.pedidos.slice(0, 1000)}`;

  try {
    const result = await llmCall(SISTEMA, userPrompt, { taskType: "analise_caso", temperature: 0.3, maxTokens: 1800 });
    const jsonMatch = result.content.match(/\{[\s\S]*\}/);
    const parsed = jsonMatch ? JSON.parse(jsonMatch[0]) : null;

    await logAuditEvent({
      action: "analise_probabilidade",
      resource: "risk_analysis",
      resourceId: null,
      metadata: { provider: result.provider, parsed: !!parsed },
    });

    return NextResponse.json({
      ok: true,
      parsed,
      raw: ensureDraftMarker(result.content),
      provider: result.provider,
    });
  } catch (err) {
    return NextResponse.json({ error: "Falha", detail: (err as Error).message }, { status: 500 });
  }
}