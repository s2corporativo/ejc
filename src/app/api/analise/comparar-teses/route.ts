// /api/analise/comparar-teses — Compara 2 teses opostas sobre o mesmo caso.
//
// Usado para entender divergência jurisprudencial ou posições
// antagônicas do Promotor e da Defesa no mesmo caso.

import { NextRequest, NextResponse } from "next/server";
import { llmCall } from "@/lib/llm";
import { logAuditEvent } from "@/lib/audit";
import { ensureDraftMarker } from "@/lib/ai_governance";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

interface Body {
  caso: string;
  teseA: string;        // ex: "A ré praticou furto qualificado"
  teseB: string;        // ex: "Não houve furto, mas mera apropriação de bem abandonado"
  fundamentosA?: string;
  fundamentosB?: string;
  precedentesA?: string;
  precedentesB?: string;
}

const SISTEMA = `Você é um jurista brasileiro sênior. Compare 2 TESES OPOSTAS sobre o mesmo caso.
Para cada tese, avalie: (a) força argumentativa, (b) precedentes alinhados, (c) riscos.

Responda em JSON:
{
  "teseA": {
    "forca": 0-100,
    "precedentes_favoraveis": [str],
    "precedentes_contra": [str],
    "principais_pontos_fracos": [str]
  },
  "teseB": {
    "forca": 0-100,
    "precedentes_favoraveis": [str],
    "precedentes_contra": [str],
    "principais_pontos_fracos": [str]
  },
  "convergencias": [str],  // pontos em que as duas teses concordam
  "divergencias_estruturais": [str],  // onde elas se afastam em premissas
  "qual_tese_mais_provavel": "A"|"B"|"empate",
  "fundamentacao_comparativa": str
}

Regras:
- NUNCA prometa resultado
- Use a jurisprudência dominante quando existir
- Marque [VERIFICAR] para precedentes duvidosos`;

export async function POST(req: NextRequest) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }
  if (!body.caso || !body.teseA || !body.teseB) {
    return NextResponse.json({ error: "caso, teseA e teseB obrigatórios" }, { status: 400 });
  }

  const userPrompt = `## CASO
${body.caso.slice(0, 2000)}

## TESE A
${body.teseA}
${body.fundamentosA ? `\nFundamentos: ${body.fundamentosA}` : ""}
${body.precedentesA ? `\nPrecedentes: ${body.precedentesA}` : ""}

## TESE B
${body.teseB}
${body.fundamentosB ? `\nFundamentos: ${body.fundamentosB}` : ""}
${body.precedentesB ? `\nPrecedentes: ${body.precedentesB}` : ""}`;

  try {
    const result = await llmCall(SISTEMA, userPrompt, { taskType: "analise_caso", temperature: 0.3, maxTokens: 2000 });
    const jsonMatch = result.content.match(/\{[\s\S]*\}/);
    const parsed = jsonMatch ? JSON.parse(jsonMatch[0]) : null;

    await logAuditEvent({
      action: "comparar_teses",
      resource: "comparative_analysis",
      resourceId: null,
      metadata: { provider: result.provider },
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