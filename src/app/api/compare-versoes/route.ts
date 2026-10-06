// /api/compare-versoes — Gera 2 minutas com prompts diferentes para comparação lado-a-lado.

import { NextRequest, NextResponse } from "next/server";
import { llmCall } from "@/lib/llm";
import { logAuditEvent, logUsageEntry } from "@/lib/audit";
import { ensureDraftMarker } from "@/lib/ai_governance";

export const dynamic = "force-dynamic";
export const maxDuration = 180;

interface Body {
  areaJuridica: string;
  fatos: string;
  pedidos?: string;
  precedentes?: string;
  // Diferencial entre as duas versões (estilo/tom)
  enfoqueA?: string; // ex: "foco em precedente vinculante"
  enfoqueB?: string; // ex: "foco em prova documental"
}

const SISTEMA_BASE = `Você é um advogado brasileiro. Produza a PETIÇÃO INICIAL estruturada em markdown, com seções: ## I. Endereçamento, ## II. Qualificação, ## III. Fatos, ## IV. Fundamentos, ## V. Provas, ## VI. Pedidos, ## VII. Fechos.
Use marcadores [NOME_1], [CPF_1] para dados pessoais. NÃO prometa resultado. Marque como RASCUNHO.`;

export async function POST(req: NextRequest) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }
  if (!body.fatos || body.fatos.trim().length < 50) {
    return NextResponse.json({ error: "fatos obrigatório (>= 50 caracteres)" }, { status: 400 });
  }

  const enfoqueA = body.enfoqueA ?? "foco em precedente jurisprudencial e súmulas vinculantes";
  const enfoqueB = body.enfoqueB ?? "foco em prova documental robusta e argumentação principiológica";

  const userPromptA = `Área: ${body.areaJuridica}\nEnfoque: ${enfoqueA}\n${body.precedentes ? `Precedentes sugeridos: ${body.precedentes}\n` : ""}${body.pedidos ? `Pedidos: ${body.pedidos}\n` : ""}\nFatos:\n${body.fatos}`;
  const userPromptB = `Área: ${body.areaJuridica}\nEnfoque: ${enfoqueB}\n${body.precedentes ? `Precedentes sugeridos: ${body.precedentes}\n` : ""}${body.pedidos ? `Pedidos: ${body.pedidos}\n` : ""}\nFatos:\n${body.fatos}`;

  try {
    const [a, b] = await Promise.all([
      llmCall(SISTEMA_BASE, userPromptA, { taskType: "minuta", temperature: 0.3, maxTokens: 2200 }),
      llmCall(SISTEMA_BASE, userPromptB, { taskType: "minuta", temperature: 0.5, maxTokens: 2200 }),
    ]);

    await logAuditEvent({
      action: "compare_versoes",
      resource: "minuta",
      resourceId: null,
      metadata: { enfoqueA, enfoqueB, providerA: a.provider, providerB: b.provider },
    });
    await logUsageEntry({
      type: "debit",
      operation: "compare_versoes",
      amount: -12,
      reason: "Comparação de duas versões de minuta",
      metadata: { providerA: a.provider, providerB: b.provider },
    });

    return NextResponse.json({
      ok: true,
      versaoA: { content: ensureDraftMarker(a.content), provider: a.provider, enfoque: enfoqueA },
      versaoB: { content: ensureDraftMarker(b.content), provider: b.provider, enfoque: enfoqueB },
    });
  } catch (err) {
    return NextResponse.json({ error: "Falha na comparação", detail: (err as Error).message }, { status: 500 });
  }
}