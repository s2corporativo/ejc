import { NextRequest, NextResponse } from "next/server";
import { logAuditEvent } from "@/lib/audit";
import { parseJsonBody, truncateForDisplay } from "@/lib/api-helpers";
import { vedacaoSurpresa } from "@/lib/lexvalida_port";

export const dynamic = "force-dynamic";

// POST /api/vedacao-surpresa — detecta fundamentos de ofício na decisão ausentes nos autos
export async function POST(req: NextRequest) {
  const parsed = await parseJsonBody<{ textoDecisao?: string; textoAutos?: string }>(req);
  if (!parsed.ok) return NextResponse.json({ error: parsed.error }, { status: 400 });

  const { textoDecisao, textoAutos } = parsed.body;
  if (!textoDecisao?.trim()) return NextResponse.json({ error: "textoDecisao obrigatório" }, { status: 400 });
  if (!textoAutos?.trim()) return NextResponse.json({ error: "textoAutos obrigatório" }, { status: 400 });

  const result = vedacaoSurpresa(textoDecisao, textoAutos);

  await logAuditEvent({
    action: "vedacao_surpresa",
    resource: "document",
    metadata: {
      previewDecisao: truncateForDisplay(textoDecisao, 200),
      previewAutos: truncateForDisplay(textoAutos, 200),
      achados: result.achados.length,
      materias: result.achados.map((a) => a.materia),
    },
  });

  return NextResponse.json(result);
}
