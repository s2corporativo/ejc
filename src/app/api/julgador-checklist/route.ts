import { NextRequest, NextResponse } from "next/server";
import { logAuditEvent } from "@/lib/audit";
import { parseJsonBody } from "@/lib/api-helpers";
import { simularJulgador, listarChecklists, tipoCanonico } from "@/lib/lexvalida_port";

export const dynamic = "force-dynamic";

// GET /api/julgador-checklist — lista checklists disponíveis
export async function GET() {
  return NextResponse.json({
    checklists: listarChecklists(),
    aliases: [
      { chave: "tutela", canon: "tutela_urgencia" },
      { chave: "liminar", canon: "tutela_urgencia" },
      { chave: "contestacao", canon: "contestacao" },
      { chave: "defesa", canon: "contestacao" },
      { chave: "apelacao", canon: "recurso" },
      { chave: "recurso", canon: "recurso" },
      { chave: "agravo", canon: "recurso" },
      { chave: "embargos", canon: "recurso" },
      { chave: "sentenca", canon: "sentenca" },
      { chave: "decisao", canon: "sentenca" },
      { chave: "peticao inicial", canon: "peticao_inicial" },
      { chave: "inicial", canon: "peticao_inicial" },
      { chave: "acao", canon: "peticao_inicial" },
    ],
  });
}

// POST /api/julgador-checklist — simula julgador sobre texto
export async function POST(req: NextRequest) {
  const parsed = await parseJsonBody<{ texto?: string; tipoPeca?: string }>(req);
  if (!parsed.ok) return NextResponse.json({ error: parsed.error }, { status: 400 });

  const { texto, tipoPeca } = parsed.body;
  if (!texto?.trim()) return NextResponse.json({ error: "texto obrigatório" }, { status: 400 });
  if (!tipoPeca?.trim()) return NextResponse.json({ error: "tipoPeca obrigatório" }, { status: 400 });

  const canon = tipoCanonico(tipoPeca);
  if (!canon) {
    return NextResponse.json({
      tipo: tipoPeca,
      checklist: [],
      pendencias: [],
      nota: "Sem checklist estrutural cadastrado para este tipo de peça.",
      canonico: null,
    });
  }

  const result = simularJulgador(texto, tipoPeca);
  await logAuditEvent({
    action: "julgador_simular",
    resource: "document",
    metadata: {
      tipoPeca,
      canonico: canon,
      atendidos: result.checklist.filter((c) => c.atendido).length,
      pendencias: result.pendencias.length,
    },
  });

  return NextResponse.json({ ...result, canonico: canon });
}
