import { NextRequest, NextResponse } from "next/server";
import { logAuditEvent } from "@/lib/audit";
import { parseJsonBody, truncateForDisplay } from "@/lib/api-helpers";
import { classificarDocumento, providenciasPorTipo } from "@/lib/lexvalida_port";

export const dynamic = "force-dynamic";

// POST /api/triagem-documento — classifica tipo de documento + sugere providências
export async function POST(req: NextRequest) {
  const parsed = await parseJsonBody<{ texto?: string; jec?: boolean }>(req);
  if (!parsed.ok) return NextResponse.json({ error: parsed.error }, { status: 400 });

  const { texto, jec } = parsed.body;
  if (!texto?.trim()) return NextResponse.json({ error: "texto obrigatório" }, { status: 400 });

  const triagem = classificarDocumento(texto);
  const providencias = providenciasPorTipo(triagem.tipo, jec === true ? true : triagem.jec);

  await logAuditEvent({
    action: "triagem_documento",
    resource: "document",
    metadata: {
      preview: truncateForDisplay(texto, 200),
      tipo: triagem.tipo,
      rotulo: triagem.rotulo,
      confianca: triagem.confianca,
      jec: triagem.jec,
      alternativas: triagem.alternativas,
      providencias: providencias.length,
    },
  });

  return NextResponse.json({
    ...triagem,
    providencias,
  });
}
