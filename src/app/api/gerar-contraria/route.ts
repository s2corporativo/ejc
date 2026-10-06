// /api/gerar-contraria — Gera a peça adversária (crítica) de uma petição.
//
// Lê o texto da peça, extrai pontos vulneráveis e propõe reforços. Útil
// para o advogado antecipar o que o adversário vai dizer antes de protocolar.

import { NextRequest, NextResponse } from "next/server";
import { llmCall } from "@/lib/llm";
import { logAuditEvent, logUsageEntry } from "@/lib/audit";
import { ensureDraftMarker } from "@/lib/ai_governance";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

interface Body {
  caseId?: string | null;
  textoPeca: string;       // texto da peça a ser criticada
  areaJuridica?: string;   // penal | civil | consumidor | etc
  parteAdversaria?: string; // réu | autor
  fatosCaso?: string;       // contexto adicional
}

const SISTEMA = `Você é um advogado ADVERSÁRIO brasileiro, especialista em processo civil e penal.
Sua tarefa é produzir a crítica que a PARTE CONTRÁRIA faria à peça abaixo.

Foque em:
  1. Preliminares processuais (art. 337 CPC, art. 395 CPP)
  2. Impugnações aos fatos narrados (pontos fracos, contradições)
  3. Fragilidades probatórias (ausência de provas, prova exclusivamente documental da parte)
  4. Precedentes e súmulas que contrariam a tese
  5. Pedidos vulneráveis (cumulação indevida, iliquidez, coisa julgada)

Responda em JSON estrito no formato:
{
  "preliminares": [{"fundamento": str, "baseLegal": str, "probabilidade": "alta"|"media"|"baixa", "como_reforcar": str}],
  "impugnações_fato": [{"ponto": str, "argumento_adverso": str, "gravidade": "alta"|"media"|"baixa"}],
  "precedentes_contrarios": [{"tipo": "sumula_stj"|"sumula_stf"|"tema_stf"|"repetitivo_stj"|"outro", "numero": str, "tese": str, "como_usa_contra": str}],
  "vulnerabilidades_pedido": [{"pedido": str, "risco": str, "como_reforcar": str}],
  "sugestao_ajuste": str
}

REGRAS:
- NÃO prometa resultado (vedação EOAB)
- Use APENAS jurisprudência conhecida — se incerto, marque como "verificar em base"
- Seja técnico e direto, sem floreios`;

export async function POST(req: NextRequest) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }
  if (!body.textoPeca || body.textoPeca.trim().length < 50) {
    return NextResponse.json(
      { error: "textoPeca obrigatório (mínimo 50 caracteres)" },
      { status: 400 },
    );
  }

  const userPrompt = `## Área: ${body.areaJuridica ?? "cível"}
## Parte adversária simulada: ${body.parteAdversaria ?? "réu"}

${body.fatosCaso ? `## Fatos do caso\n${body.fatosCaso.slice(0, 1500)}\n` : ""}
## Peça a ser criticada (máx 4000 caracteres)
${body.textoPeca.slice(0, 4000)}`;

  try {
    const result = await llmCall(SISTEMA, userPrompt, {
      taskType: body.areaJuridica?.includes("penal") ? "criminal" : "minuta",
      temperature: 0.3,
      maxTokens: 2200,
    });

    // Tentar extrair JSON da resposta
    let parsed: unknown = null;
    const jsonMatch = result.content.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      try {
        parsed = JSON.parse(jsonMatch[0]);
      } catch {
        // Se não parseou, devolver texto cru mesmo (com rascunho)
      }
    }

    await logAuditEvent({
      action: "gerar_contraria",
      resource: "lexvalida_pipeline",
      resourceId: body.caseId ?? null,
      metadata: { area: body.areaJuridica, provider: result.provider, fallback: result.fallback },
    });
    await logUsageEntry({
      type: "debit",
      operation: "gerar_contraria",
      amount: -8,
      reason: "Geração de peça adversária",
      metadata: { caseId: body.caseId, tokens: result.tokensUsed, latencyMs: result.latencyMs },
    });

    return NextResponse.json({
      ok: true,
      parsed,
      raw: ensureDraftMarker(result.content),
      provider: result.provider,
      fallback: result.fallback,
      latencyMs: result.latencyMs,
    });
  } catch (err) {
    return NextResponse.json(
      { error: "Falha ao gerar peça adversária", detail: (err as Error).message },
      { status: 500 },
    );
  }
}