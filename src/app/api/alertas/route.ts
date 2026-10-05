import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { logAuditEvent } from "@/lib/audit";

export const dynamic = "force-dynamic";

// GET /api/alertas — alertas urgentes (prazos/audiências/honorários ≤3 dias)
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const dias = Math.min(parseInt(url.searchParams.get("dias") || "3", 10), 30);
  const agora = new Date();
  const limite = new Date(agora.getTime() + dias * 86400000);

  // Prazos vencendo
  const prazos = await db.caseDeadline.findMany({
    where: {
      vencimento: { lte: limite },
    },
    orderBy: { vencimento: "asc" },
    take: 100,
  });

  // Audiências próximas
  const audiencias = await db.caseHearing.findMany({
    where: {
      data: { gte: agora, lte: limite },
      status: "agendada",
    },
    orderBy: { data: "asc" },
    take: 100,
  });

  // Honorários (via AuditEvent action=honorario_*) — vencimento no metadata
  const honorarios = await db.auditEvent.findMany({
    where: {
      OR: [{ action: "honorario_create" }, { action: "honorario_update" }],
    },
    orderBy: { createdAt: "desc" },
    take: 200,
  });

  const honorariosAlertas = honorarios
    .map((h) => {
      let meta: { descricao?: string; valor?: number; vencimento?: string; status?: string; caseId?: string } = {};
      try { meta = JSON.parse(h.metadata) as typeof meta; } catch { /* ignore */ }
      return { id: h.id, ...meta, criadoEm: h.createdAt.toISOString() };
    })
    .filter((hh) => {
      if (!hh.vencimento) return false;
      const v = new Date(hh.vencimento);
      return v >= agora && v <= limite && hh.status !== "pago";
    });

  // Caso título lookup
  const caseIds = new Set<string>([
    ...prazos.map((p) => p.caseId),
    ...audiencias.map((a) => a.caseId),
    ...honorariosAlertas.map((h) => h.caseId).filter(Boolean) as string[],
  ]);
  const cases = caseIds.size > 0
    ? await db.case.findMany({ where: { id: { in: Array.from(caseIds) } }, select: { id: true, title: true, number: true } })
    : [];
  const caseMap = new Map(cases.map((c) => [c.id, c]));

  const alertas = [
    ...prazos.map((p) => ({
      tipo: "prazo",
      id: p.id,
      caseId: p.caseId,
      caseTitle: caseMap.get(p.caseId)?.title || "",
      caseNumber: caseMap.get(p.caseId)?.number || "",
      descricao: p.descricao,
      vencimento: p.vencimento.toISOString(),
      prazoDias: p.prazoDias,
      tipoContagem: p.tipoContagem,
      diasRestantes: Math.ceil((p.vencimento.getTime() - agora.getTime()) / 86400000),
    })),
    ...audiencias.map((a) => ({
      tipo: "audiencia",
      id: a.id,
      caseId: a.caseId,
      caseTitle: caseMap.get(a.caseId)?.title || "",
      caseNumber: caseMap.get(a.caseId)?.number || "",
      descricao: `Audiência de ${a.tipo}`,
      vencimento: a.data.toISOString(),
      prazoDias: null,
      tipoContagem: null,
      diasRestantes: Math.ceil((a.data.getTime() - agora.getTime()) / 86400000),
      local: a.local,
      orgao: a.orgao,
    })),
    ...honorariosAlertas.map((h) => ({
      tipo: "honorario",
      id: h.id,
      caseId: h.caseId || "",
      caseTitle: "",
      caseNumber: "",
      descricao: h.descricao || "Honorário",
      vencimento: h.vencimento,
      prazoDias: null,
      tipoContagem: null,
      diasRestantes: h.vencimento ? Math.ceil((new Date(h.vencimento).getTime() - agora.getTime()) / 86400000) : null,
      valor: h.valor,
      status: h.status,
    })),
  ].sort((a, b) => {
    const va = new Date(a.vencimento).getTime();
    const vb = new Date(b.vencimento).getTime();
    return va - vb;
  });

  await logAuditEvent({
    action: "alertas_query",
    resource: "case",
    metadata: { dias, total: alertas.length, prazos: prazos.length, audiencias: audiencias.length, honorarios: honorariosAlertas.length },
  });

  return NextResponse.json({
    alertas,
    total: alertas.length,
    janelaDias: dias,
    agora: agora.toISOString(),
    limite: limite.toISOString(),
  });
}
