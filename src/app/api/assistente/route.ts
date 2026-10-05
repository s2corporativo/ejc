import { NextRequest, NextResponse } from "next/server";
import { logAuditEvent } from "@/lib/audit";
import { parseJsonBody, truncateForDisplay } from "@/lib/api-helpers";
import { classificar, listarIntencoes } from "@/lib/assistente";

export const dynamic = "force-dynamic";

// GET /api/assistente — lista intenções cadastradas
export async function GET() {
  return NextResponse.json({
    intencoes: listarIntencoes(),
    total: Object.keys(listarIntencoes()).length,
  });
}

// POST /api/assistente — classifica intenção + extrai entidades
export async function POST(req: NextRequest) {
  const parsed = await parseJsonBody<{ texto?: string }>(req);
  if (!parsed.ok) return NextResponse.json({ error: parsed.error }, { status: 400 });

  const { texto } = parsed.body;
  if (!texto?.trim()) return NextResponse.json({ error: "texto obrigatório" }, { status: 400 });

  const result = classificar(texto);

  await logAuditEvent({
    action: "assistente_classify",
    resource: "assistente",
    metadata: {
      preview: truncateForDisplay(texto, 200),
      intencao: result.intencao,
      confianca: result.confianca,
      candidatas: result.candidatas,
      entidades: {
        cnj: result.entidades.cnj.length,
        oabs: result.entidades.oabs.length,
        datas: result.entidades.datas.length,
        dias: result.entidades.dias.length,
        valores: result.entidades.valores.length,
        dispositivos: result.entidades.dispositivos.length,
        sumulas: result.entidades.sumulas.length,
        tribunais: result.entidades.tribunais.length,
        tipoPeca: result.entidades.tipoPeca,
        area: result.entidades.area,
      },
    },
  });

  return NextResponse.json(result);
}
