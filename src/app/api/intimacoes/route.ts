import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { logAuditEvent } from "@/lib/audit";
import { parseJsonBody } from "@/lib/api-helpers";
import { extrairEntidades } from "@/lib/assistente";

export const dynamic = "force-dynamic";

// GET /api/intimacoes — lista intimações registradas (via AuditEvent action=intimacao_djen)
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const oabEstado = url.searchParams.get("oabEstado")?.toUpperCase();
  const oabNumero = url.searchParams.get("oabNumero");

  const where: { action: string } = { action: "intimacao_djen" };
  const rows = await db.auditEvent.findMany({
    where,
    orderBy: { createdAt: "desc" },
    take: 200,
  });

  // Filtra por OAB (match pelo metadata.oabEstado/oabNumero) se informado
  let intimo = rows.map((r) => {
    let meta: { conteudo?: string; oab?: string; cnj?: string; prazo?: string; vencimento?: string; caseId?: string } = {};
    try { meta = JSON.parse(r.metadata) as typeof meta; } catch { /* ignore */ }
    return { id: r.id, ...meta, criadoEm: r.createdAt.toISOString() };
  });

  if (oabEstado && oabNumero) {
    intimo = intimo.filter((i) => {
      if (!i.oab) return false;
      const m = i.oab.match(/(\d+)\/([A-Z]{2})/);
      if (!m) return false;
      return m[1] === oabNumero && m[2] === oabEstado;
    });
  }

  await logAuditEvent({
    action: "intimacao_list",
    resource: "intimacao",
    metadata: { filtrouOab: Boolean(oabEstado && oabNumero), total: intimo.length },
  });

  return NextResponse.json({ intimacoes: intimo, total: intimo.length });
}

// POST /api/intimacoes — registra intimação colada (texto da DJEN), extrai prazo + OAB
export async function POST(req: NextRequest) {
  const parsed = await parseJsonBody<{ conteudo?: string; caseId?: string }>(req);
  if (!parsed.ok) return NextResponse.json({ error: parsed.error }, { status: 400 });

  const { conteudo, caseId } = parsed.body;
  if (!conteudo?.trim()) return NextResponse.json({ error: "conteudo obrigatório" }, { status: 400 });
  if (conteudo.length > 100_000) {
    return NextResponse.json({ error: "conteudo muito longo (máx 100000 chars)" }, { status: 400 });
  }

  // Extrai entidades
  const ent = extrairEntidades(conteudo);
  // OAB: usa primeira OAB encontrada
  const oab = ent.oabs[0] || null;
  // CNJ
  const cnj = ent.cnj[0] || null;
  // Prazo: primeiro prazo mencionado (em dias)
  const prazoDias = ent.dias[0]?.dias || null;
  const tipoContagem = ent.dias[0]?.contagem || null;

  const meta = {
    conteudo: conteudo.slice(0, 2000), // armazena apenas trecho (para auditoria, não log completo)
    oab,
    cnj,
    prazoDias,
    tipoContagem,
    caseId: caseId || null,
    // tentativa de vencimento: usa data mais próxima do conteúdo + prazo (heurística)
    vencimento: null as string | null,
  };
  // Tenta calcular vencimento heurístico: se há data + dias
  if (ent.datas.length > 0 && prazoDias) {
    try {
      const base = new Date(ent.datas[0]);
      if (!isNaN(base.getTime())) {
        base.setDate(base.getDate() + prazoDias);
        meta.vencimento = base.toISOString();
      }
    } catch {
      // ignore
    }
  }

  const event = await db.auditEvent.create({
    data: {
      action: "intimacao_djen",
      resource: "intimacao",
      resourceId: caseId || cnj || null,
      metadata: JSON.stringify(meta),
    },
  });

  await logAuditEvent({
    action: "intimacao_parse",
    resource: "intimacao",
    resourceId: event.id,
    metadata: { oab, cnj, prazoDias, tipoContagem, vencimento: meta.vencimento },
  });

  return NextResponse.json({
    id: event.id,
    ...meta,
    criadoEm: event.createdAt.toISOString(),
    // também retorna as entidades extraídas p/ UI
    entidades: {
      cnj: ent.cnj,
      oabs: ent.oabs,
      datas: ent.datas,
      dias: ent.dias,
      tribunais: ent.tribunais,
    },
  });
}
