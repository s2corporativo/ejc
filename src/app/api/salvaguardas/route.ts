import { NextRequest, NextResponse } from "next/server";
import { logAuditEvent } from "@/lib/audit";
import { parseJsonBody, truncateForDisplay } from "@/lib/api-helpers";
import { verificarSalvaguardas } from "@/lib/lexvalida_port";

export const dynamic = "force-dynamic";

// POST /api/salvaguardas — verifica texto contra salvaguardas determinísticas
export async function POST(req: NextRequest) {
  const parsed = await parseJsonBody<{ texto?: string }>(req);
  if (!parsed.ok) return NextResponse.json({ error: parsed.error }, { status: 400 });

  const { texto } = parsed.body;
  if (!texto?.trim()) return NextResponse.json({ error: "texto obrigatório" }, { status: 400 });

  const result = verificarSalvaguardas(texto);

  await logAuditEvent({
    action: "salvaguardas_check",
    resource: "document",
    metadata: {
      tamanhoTexto: texto.length,
      preview: truncateForDisplay(texto, 200),
      promessas: result.promessas.length,
      meritoPrescricao: result.meritoPrescricao.length,
      cdc: result.cdc.length,
      totalAlertas: result.promessas.length + result.meritoPrescricao.length + result.cdc.length,
    },
  });

  return NextResponse.json(result);
}
