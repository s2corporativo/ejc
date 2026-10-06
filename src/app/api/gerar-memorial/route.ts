// /api/gerar-memorial — Gera memorial único com peças (petição + contestação + sentença) lado a lado.
//
// Modo "memorial" para o cliente entender visualmente como o caso
// provavelmente transcorreria. Cada peça fica em uma coluna.

import { NextRequest, NextResponse } from "next/server";
import { llmCall } from "@/lib/llm";
import { logAuditEvent } from "@/lib/audit";
import { ensureDraftMarker } from "@/lib/ai_governance";

export const dynamic = "force-dynamic";
export const maxDuration = 240;

interface Body {
  areaJuridica: string;
  fatos: string;
  pedidos?: string;
  contextoAdverso?: string;
}

const SISTEMA = `Você é um sistema de simulação processual que produz um MEMORIAL consolidado em 3 colunas:
1. PETIÇÃO INICIAL (visão do autor)
2. CONTESTAÇÃO (visão do réu + réplica)
3. SENTENÇA (visão do juiz)

Cada coluna deve ser auto-contida (pode ser lida independentemente). Use ## para delimitar seções.

Estrutura:
# MEMORIAL PROCESSUAL SIMULADO

## COLUNA 1 — PETIÇÃO INICIAL (visão do autor)
[sua peça aqui em ~600 tokens]

## COLUNA 2 — CONTESTAÇÃO (visão do réu + réplica do autor)
[peça aqui em ~600 tokens]

## COLUNA 3 — SENTENÇA (visão do juiz)
[fundamentação + dispositivo em ~600 tokens]

Regras:
- NUNCA prometa resultado (vedação EOAB art. 2º §1º)
- Use [NOME_1], [CPF_1] para pseudonimizar
- Cada coluna deve terminar com marcador RASCUNHO
- Indique explicitamente "Esta é uma SIMULAÇÃO, sem valor probatório"`;

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

## Fatos
${body.fatos.slice(0, 3000)}

${body.pedidos ? `## Pedidos principais\n${body.pedidos.slice(0, 1000)}` : ""}
${body.contextoAdverso ? `## Contexto do adversário\n${body.contextoAdverso.slice(0, 1000)}` : ""}`;

  try {
    const result = await llmCall(SISTEMA, userPrompt, { taskType: "minuta", temperature: 0.4, maxTokens: 3500 });

    await logAuditEvent({
      action: "gerar_memorial",
      resource: "memorial_mode",
      resourceId: null,
      metadata: { provider: result.provider, tokens: result.tokensUsed },
    });

    return NextResponse.json({
      ok: true,
      memorial: ensureDraftMarker(result.content),
      provider: result.provider,
      latencyMs: result.latencyMs,
    });
  } catch (err) {
    return NextResponse.json({ error: "Falha", detail: (err as Error).message }, { status: 500 });
  }
}