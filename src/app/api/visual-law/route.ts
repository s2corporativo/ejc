import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { logAuditEvent } from "@/lib/audit";
import { parseJsonBody } from "@/lib/api-helpers";

export const dynamic = "force-dynamic";

// POST /api/visual-law — gera timeline + quadro-resumo HTML/MD
// Body: { caseId?: string, format: "html"|"md" }
export async function POST(req: NextRequest) {
  const parsed = await parseJsonBody<{ caseId?: string; format?: "html" | "md" }>(req);
  if (!parsed.ok) return NextResponse.json({ error: parsed.error }, { status: 400 });

  const { caseId, format = "md" } = parsed.body;
  if (!caseId) return NextResponse.json({ error: "caseId obrigatório" }, { status: 400 });

  const c = await db.case.findUnique({
    where: { id: caseId },
    include: {
      client: true,
      documents: { orderBy: { createdAt: "asc" } },
      movimentos: { orderBy: { data: "asc" }, take: 200 },
      audiencias: { orderBy: { data: "asc" }, take: 100 },
    },
  });
  if (!c) return NextResponse.json({ error: "Caso não encontrado" }, { status: 404 });

  const deadlines = await db.caseDeadline.findMany({
    where: { caseId },
    orderBy: { vencimento: "asc" },
    take: 100,
  });

  // Timeline unificada
  interface TimelineItem { data: string; tipo: string; descricao: string; fonte: string }
  const timeline: TimelineItem[] = [];
  for (const m of c.movimentos) {
    timeline.push({ data: m.data.toISOString(), tipo: m.tipo, descricao: m.descricao, fonte: "movimento" });
  }
  for (const a of c.audiencias) {
    timeline.push({
      data: a.data.toISOString(),
      tipo: "audiencia",
      descricao: `${a.tipo}${a.orgao ? ` (${a.orgao})` : ""}${a.local ? ` @ ${a.local}` : ""}`,
      fonte: "audiencia",
    });
  }
  for (const d of deadlines) {
    timeline.push({
      data: d.vencimento.toISOString(),
      tipo: "prazo",
      descricao: `${d.descricao} (${d.prazoDias} ${d.tipoContagem})`,
      fonte: "deadline",
    });
  }
  timeline.sort((a, b) => new Date(a.data).getTime() - new Date(b.data).getTime());

  const fmtDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleDateString("pt-BR");
    } catch {
      return iso.slice(0, 10);
    }
  };

  // Quadro-resumo (KPIs)
  const quadro = {
    titulo: c.title,
    cliente: c.client?.name || "—",
    area: c.area,
    status: c.status,
    responsavel: c.responsavel || "—",
    valor: c.valor || "—",
    totalMovimentos: c.movimentos.length,
    totalAudiencias: c.audiencias.length,
    totalPrazos: deadlines.length,
    totalDocumentos: c.documents.length,
    proximaAudiencia: c.audiencias.find((a) => a.data.getTime() >= Date.now())?.data.toISOString() || null,
    proximoPrazo: deadlines.find((d) => d.vencimento.getTime() >= Date.now())?.vencimento.toISOString() || null,
  };

  let output: string;
  if (format === "html") {
    const tlHtml = timeline
      .map((it) => `      <li><time datetime="${it.data}">${fmtDate(it.data)}</time> <strong>${it.tipo}</strong> — ${it.descricao} <em>(${it.fonte})</em></li>`)
      .join("\n");
    output = `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Mapa do Caso — ${escapeHtml(c.title)}</title>
  <style>
    body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 16px; }
    h1 { font-size: 1.6rem; }
    .quadro { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 24px; background: #f8f8f8; padding: 16px; border-radius: 8px; }
    .quadro div { font-size: 0.9rem; }
    .quadro strong { display: block; color: #666; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }
    ul.timeline { list-style: none; padding-left: 16px; border-left: 2px solid #ddd; }
    ul.timeline li { margin-bottom: 8px; padding-left: 12px; position: relative; }
    ul.timeline li::before { content: "●"; position: absolute; left: -8px; color: #888; }
    time { color: #999; font-family: monospace; }
  </style>
</head>
<body>
  <h1>${escapeHtml(c.title)}</h1>
  <p>Caso <code>${c.number || "—"}</code> · ${escapeHtml(c.area)} · ${escapeHtml(c.status)}</p>
  <h2>Quadro-resumo</h2>
  <div class="quadro">
    <div><strong>Cliente</strong> ${escapeHtml(quadro.cliente)}</div>
    <div><strong>Responsável</strong> ${escapeHtml(quadro.responsavel)}</div>
    <div><strong>Valor</strong> ${escapeHtml(quadro.valor || "—")}</div>
    <div><strong>Movimentos</strong> ${quadro.totalMovimentos}</div>
    <div><strong>Audiências</strong> ${quadro.totalAudiencias}</div>
    <div><strong>Prazos</strong> ${quadro.totalPrazos}</div>
    <div><strong>Documentos</strong> ${quadro.totalDocumentos}</div>
    <div><strong>Próxima audiência</strong> ${quadro.proximaAudiencia ? fmtDate(quadro.proximaAudiencia) : "—"}</div>
    <div><strong>Próximo prazo</strong> ${quadro.proximoPrazo ? fmtDate(quadro.proximoPrazo) : "—"}</div>
  </div>
  <h2>Timeline</h2>
  <ul class="timeline">
${tlHtml || "      <li>—</li>"}
  </ul>
</body>
</html>`;
  } else {
    const tlMd = timeline
      .map((it) => `- ${fmtDate(it.data)} **${it.tipo}** — ${it.descricao} *(${it.fonte})*`)
      .join("\n");
    output = `# Mapa do Caso — ${c.title}

**Caso:** \`${c.number || "—"}\` · ${c.area} · ${c.status}

## Quadro-resumo

| Campo | Valor |
|---|---|
| Cliente | ${quadro.cliente} |
| Responsável | ${quadro.responsavel} |
| Valor | ${quadro.valor || "—"} |
| Movimentos | ${quadro.totalMovimentos} |
| Audiências | ${quadro.totalAudiencias} |
| Prazos | ${quadro.totalPrazos} |
| Documentos | ${quadro.totalDocumentos} |
| Próxima audiência | ${quadro.proximaAudiencia ? fmtDate(quadro.proximaAudiencia) : "—"} |
| Próximo prazo | ${quadro.proximoPrazo ? fmtDate(quadro.proximoPrazo) : "—"} |

## Timeline

${tlMd || "_(sem eventos)_"}
`;
  }

  await logAuditEvent({
    action: "visual_law_gen",
    resource: "case",
    resourceId: c.id,
    metadata: {
      format,
      totalTimeline: timeline.length,
      totalQuadro: Object.keys(quadro).length,
    },
  });

  return new NextResponse(output, {
    headers: {
      "content-type": format === "html" ? "text/html; charset=utf-8" : "text/markdown; charset=utf-8",
    },
  });
}

function escapeHtml(s: string): string {
  return (s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
