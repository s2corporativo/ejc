import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { logAuditEvent } from "@/lib/audit";

export const dynamic = "force-dynamic";

// GET /api/produtividade — ranking + stats
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const dias = Math.min(parseInt(url.searchParams.get("dias") || "30", 10), 365);
  const desde = new Date(Date.now() - dias * 86400000);

  // 1. Casos por responsável (advogado)
  const cases = await db.case.findMany({
    where: { updatedAt: { gte: desde } },
    select: { id: true, responsavel: true, status: true, prioridade: true, area: true, valor: true },
  });

  const porAdvogado = new Map<string, { casos: number; ativos: number; encerrados: number; alto: number }>();
  for (const c of cases) {
    const r = c.responsavel || "Sem responsável";
    const e = porAdvogado.get(r) || { casos: 0, ativos: 0, encerrados: 0, alto: 0 };
    e.casos++;
    if (c.status === "ativo") e.ativos++;
    if (c.status === "encerrado") e.encerrados++;
    if (c.prioridade === "alta") e.alto++;
    porAdvogado.set(r, e);
  }

  const ranking = Array.from(porAdvogado.entries())
    .map(([adv, s]) => ({ advogado: adv, ...s, taxaEncerramento: s.casos > 0 ? Math.round((s.encerrados / s.casos) * 100) : 0 }))
    .sort((a, b) => b.casos - a.casos);

  // 2. Áreas mais atendidas
  const porArea = new Map<string, number>();
  for (const c of cases) {
    porArea.set(c.area, (porArea.get(c.area) || 0) + 1);
  }
  const areasRank = Array.from(porArea.entries())
    .map(([area, n]) => ({ area, casos: n }))
    .sort((a, b) => b.casos - a.casos);

  // 3. Movimentações no período (proxy de produtividade = andamentos)
  const movimentos = await db.caseMovement.findMany({
    where: { data: { gte: desde } },
    select: { id: true, tipo: true, caseId: true, criadoPor: true },
  });
  const porTipoMov = new Map<string, number>();
  for (const m of movimentos) {
    porTipoMov.set(m.tipo, (porTipoMov.get(m.tipo) || 0) + 1);
  }
  const tiposMovRank = Array.from(porTipoMov.entries())
    .map(([tipo, n]) => ({ tipo, count: n }))
    .sort((a, b) => b.count - a.count);

  // 4. Documentos gerados no período
  const documentos = await db.document.findMany({
    where: { createdAt: { gte: desde } },
    select: { id: true, templateSlug: true, status: true },
  });
  const porTemplate = new Map<string, number>();
  for (const d of documentos) {
    porTemplate.set(d.templateSlug, (porTemplate.get(d.templateSlug) || 0) + 1);
  }
  const templatesRank = Array.from(porTemplate.entries())
    .map(([slug, n]) => ({ template: slug, count: n }))
    .sort((a, b) => b.count - a.count);

  await logAuditEvent({
    action: "produtividade_query",
    resource: "case",
    metadata: {
      dias,
      totalCasos: cases.length,
      totalMovimentos: movimentos.length,
      totalDocumentos: documentos.length,
      advogadosAtivos: ranking.length,
    },
  });

  return NextResponse.json({
    janelaDias: dias,
    desde: desde.toISOString(),
    ranking,
    areas: areasRank,
    tiposMovimento: tiposMovRank,
    templates: templatesRank,
    resumo: {
      totalCasos: cases.length,
      totalMovimentos: movimentos.length,
      totalDocumentos: documentos.length,
      advogadosAtivos: ranking.length,
      mediaCasosPorAdvogado: ranking.length > 0 ? Math.round((cases.length / ranking.length) * 10) / 10 : 0,
    },
  });
}
