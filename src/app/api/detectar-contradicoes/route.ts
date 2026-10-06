// /api/detectar-contradicoes — Compara petição inicial com contestação e lista contradições factuais.
//
// Usa NLP leve (datas, valores, nomes) + LLM para identificar pontos
// onde o réu contradiz o autor e onde o réu introduz versões conflitantes.

import { NextRequest, NextResponse } from "next/server";
import { llmCall } from "@/lib/llm";
import { logAuditEvent } from "@/lib/audit";
import { ensureDraftMarker } from "@/lib/ai_governance";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

interface Body {
  peticaoInicial: string;
  contestacao: string;
  areaJuridica?: string;
}

const SISTEMA = `Você é um juiz brasileiro analisando a PETIÇÃO INICIAL e a CONTESTAÇÃO do mesmo caso.
Identifique CONTRADIÇÕES FACTUAIS entre as duas peças, com foco em:

1. **Datas divergentes** — "ocorreu em 15/03" vs "na verdade foi em 20/03"
2. **Valores divergentes** — "R$ 10.000" vs "R$ 5.000"
3. **Versões diferentes do mesmo fato** — autor diz X, réu diz Y
4. **Nomes ou qualificações divergentes** — partes descritas de modo inconsistente
5. **Causa de pedir inconsistente** — autor aponta causa, réu nega com versão própria

Responda em JSON:
{
  "contradições": [{
    "tipo": "data"|"valor"|"fato"|"nome"|"causa_pedir",
    "trecho_autor": str,
    "trecho_reu": str,
    "gravidade": "alta"|"media"|"baixa",
    "como_resolver": str
  }],
  "convergências": [str],   // pontos em que as duas peças concordam
  "lacuna_probatória": [str] // alegações sem prova de nenhum lado
}

Regras: NÃO invente — use apenas o que está nas peças. NUNCA prometa resultado.`;

export async function POST(req: NextRequest) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }
  if (!body.peticaoInicial || !body.contestacao) {
    return NextResponse.json({ error: "peticaoInicial e contestacao obrigatórios" }, { status: 400 });
  }
  if (body.peticaoInicial.length < 50 || body.contestacao.length < 50) {
    return NextResponse.json({ error: "Peças devem ter >= 50 caracteres" }, { status: 400 });
  }

  const userPrompt = `## Área: ${body.areaJuridica ?? "cível"}

## PETIÇÃO INICIAL
${body.peticaoInicial.slice(0, 3500)}

## CONTESTAÇÃO
${body.contestacao.slice(0, 3500)}

Identifique contradições factuais.`;

  try {
    const result = await llmCall(SISTEMA, userPrompt, { taskType: "analise_caso", temperature: 0.2, maxTokens: 2200 });
    const jsonMatch = result.content.match(/\{[\s\S]*\}/);
    const parsed = jsonMatch ? JSON.parse(jsonMatch[0]) : null;

    await logAuditEvent({
      action: "detectar_contradicoes",
      resource: "analise_pecas",
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
    return NextResponse.json({ error: "Falha na análise", detail: (err as Error).message }, { status: 500 });
  }
}