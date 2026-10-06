// /api/simular-reu — Simula a defesa/contestação que o réu apresentaria.
//
// Diferente de /api/gerar-contraria (que faz crítica genérica), este
// endpoint produz a CONTESTAÇÃO estruturada no padrão do CPC art. 341-343.

import { NextRequest, NextResponse } from "next/server";
import { llmCall } from "@/lib/llm";
import { logAuditEvent, logUsageEntry } from "@/lib/audit";
import { ensureDraftMarker } from "@/lib/ai_governance";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

interface Body {
  caseId?: string | null;
  fatosCaso: string;       // narrativa do autor
  areaJuridica?: string;
  pedidosAutor?: string;
  reuFicticio?: string;    // nome do réu (opcional)
}

const SISTEMA = `Você é o advogado do RÉU em um processo brasileiro.
Sua tarefa é redigir a CONTESTAÇÃO com base nos fatos narrados e nos pedidos do autor.

A contestação deve ter:
  ## I. Endereçamento (juízo competente)
  ## II. Qualificação do réu (use ____ se faltarem dados)
  ## III. Síntese fática (visão do réu)
  ## IV. Preliminares (art. 337 CPC — todas as aplicáveis)
  ## V. Meritório (impugnação específica ponto a ponto)
  ## VI. Direito aplicável (artigos + súmulas)
  ## VII. Provas a produzir (inicial: documental + testemunhal se aplicável)
  ## VIII. Pedidos (improcedência + inversão de ônus se cabível)
  ## IX. Fechos

REGRAS:
- NUNCA invente dados dos autos. Use ____ para informações que não constam nos fatos
- Citações só da base curada; se duvidoso, marque "[VERIFICAR]"
- Vedação de promessa de resultado (art. 2º §1º EOAB)
- Use pseudonimização: substitua nomes reais por [NOME_1] etc.
- Marque o texto como RASCUNHO (sujeito a revisão humana)`;

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
${body.reuFicticio ? `## Réu: ${body.reuFicticio}` : "## Réu: a ser qualificado"}
${body.pedidosAutor ? `## Pedidos do autor\n${body.pedidosAutor.slice(0, 1500)}` : ""}

## Fatos narrados pelo autor
${body.fatosCaso.slice(0, 3000)}`;

  try {
    const result = await llmCall(SISTEMA, userPrompt, {
      taskType: body.areaJuridica?.includes("penal") ? "criminal" : "minuta",
      temperature: 0.3,
      maxTokens: 2800,
    });

    await logAuditEvent({
      action: "simular_reu",
      resource: "lexvalida_pipeline",
      resourceId: body.caseId ?? null,
      metadata: { area: body.areaJuridica, provider: result.provider, fallback: result.fallback },
    });
    await logUsageEntry({
      type: "debit",
      operation: "simular_reu",
      amount: -10,
      reason: "Simulação de contestação",
      metadata: { caseId: body.caseId, tokens: result.tokensUsed, latencyMs: result.latencyMs },
    });

    return NextResponse.json({
      ok: true,
      contestacao: ensureDraftMarker(result.content),
      provider: result.provider,
      fallback: result.fallback,
      latencyMs: result.latencyMs,
    });
  } catch (err) {
    return NextResponse.json(
      { error: "Falha ao simular réu", detail: (err as Error).message },
      { status: 500 },
    );
  }
}