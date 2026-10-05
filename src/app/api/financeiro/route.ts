import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { logAuditEvent } from "@/lib/audit";
import { parseJsonBody } from "@/lib/api-helpers";

export const dynamic = "force-dynamic";

// Honorarios CRUD usando AuditEvent com action=honorario_*
// (schema não tem tabela dedicada — armazenamos no AuditEvent.metadata como JSON)
// Campos: descricao, valor, vencimento, status (pendente|pago|atrasado), caseId

interface Honorario {
  id: string;
  caseId: string | null;
  descricao: string;
  valor: number;
  vencimento: string | null;
  status: string;
  createdAt: string;
}

function rowToHonorario(h: { id: string; action: string; resourceId: string | null; metadata: string; createdAt: Date }): Honorario {
  let meta: { caseId?: string; descricao?: string; valor?: number; vencimento?: string; status?: string } = {};
  try { meta = JSON.parse(h.metadata) as typeof meta; } catch { /* ignore */ }
  return {
    id: h.id,
    caseId: meta.caseId || null,
    descricao: meta.descricao || "Honorário",
    valor: typeof meta.valor === "number" ? meta.valor : 0,
    vencimento: meta.vencimento || null,
    status: meta.status || "pendente",
    createdAt: h.createdAt.toISOString(),
  };
}

// GET /api/financeiro?caseId=xxx&status=yyy&export=csv
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const caseId = url.searchParams.get("caseId");
  const status = url.searchParams.get("status");
  const exportCsv = url.searchParams.get("export") === "csv";

  const where: { action: { in: string[] }; resourceId?: string } = {
    action: { in: ["honorario_create", "honorario_update"] },
  };
  if (caseId) where.resourceId = caseId;

  const rows = await db.auditEvent.findMany({
    where,
    orderBy: { createdAt: "desc" },
    take: 500,
  });

  let honorarios = rows.map(rowToHonorario);
  if (status) honorarios = honorarios.filter((h) => h.status === status);

  // dedup por id mais recente (action update sobrepõe create se for mesmo resourceId)
  const byId = new Map<string, Honorario>();
  for (const h of honorarios) {
    byId.set(h.id, h);
  }
  honorarios = Array.from(byId.values());

  if (exportCsv) {
    const header = "id,caseId,descricao,valor,vencimento,status,createdAt\n";
    const linhas = honorarios.map((h) =>
      [
        h.id,
        h.caseId || "",
        `"${(h.descricao || "").replace(/"/g, '""')}"`,
        h.valor.toFixed(2),
        h.vencimento || "",
        h.status,
        h.createdAt,
      ].join(",")
    );
    const csv = header + linhas.join("\n");
    return new Response(csv, {
      headers: {
        "content-type": "text/csv; charset=utf-8",
        "content-disposition": "attachment; filename=honorarios.csv",
      },
    });
  }

  return NextResponse.json({
    honorarios,
    total: honorarios.length,
    soma: honorarios.reduce((acc, h) => acc + h.valor, 0),
    pagos: honorarios.filter((h) => h.status === "pago").reduce((acc, h) => acc + h.valor, 0),
    pendentes: honorarios.filter((h) => h.status === "pendente").reduce((acc, h) => acc + h.valor, 0),
    atrasados: honorarios.filter((h) => h.status === "atrasado").reduce((acc, h) => acc + h.valor, 0),
  });
}

// POST /api/financeiro
export async function POST(req: NextRequest) {
  const parsed = await parseJsonBody<{
    caseId?: string;
    descricao?: string;
    valor?: number | string;
    vencimento?: string;
    status?: string;
  }>(req);
  if (!parsed.ok) return NextResponse.json({ error: parsed.error }, { status: 400 });

  const { caseId, descricao, valor, vencimento, status } = parsed.body;
  if (!descricao?.trim()) return NextResponse.json({ error: "descricao obrigatória" }, { status: 400 });
  if (valor === undefined || valor === null) return NextResponse.json({ error: "valor obrigatório" }, { status: 400 });

  const valorNum = typeof valor === "string" ? parseFloat(valor.replace(/\./g, "").replace(",", ".")) : Number(valor);
  if (!isFinite(valorNum)) return NextResponse.json({ error: "valor inválido" }, { status: 400 });

  const meta = {
    caseId: caseId || null,
    descricao: descricao.trim(),
    valor: valorNum,
    vencimento: vencimento || null,
    status: status || "pendente",
  };

  const event = await db.auditEvent.create({
    data: {
      action: "honorario_create",
      resource: "financeiro",
      resourceId: caseId || null,
      metadata: JSON.stringify(meta),
    },
  });

  await logAuditEvent({
    action: "honorario_create",
    resource: "financeiro",
    resourceId: event.id,
    metadata: meta,
  });

  return NextResponse.json({ id: event.id, ...meta, createdAt: event.createdAt.toISOString() });
}

// PATCH /api/financeiro
export async function PATCH(req: NextRequest) {
  const parsed = await parseJsonBody<{
    id?: string;
    caseId?: string;
    descricao?: string;
    valor?: number | string;
    vencimento?: string;
    status?: string;
  }>(req);
  if (!parsed.ok) return NextResponse.json({ error: parsed.error }, { status: 400 });

  const { id, caseId, descricao, valor, vencimento, status } = parsed.body;
  if (!id) return NextResponse.json({ error: "id obrigatório" }, { status: 400 });

  const existing = await db.auditEvent.findUnique({ where: { id } });
  if (!existing) return NextResponse.json({ error: "Honorário não encontrado" }, { status: 404 });

  let meta: { caseId?: string | null; descricao?: string; valor?: number; vencimento?: string | null; status?: string } = {};
  try { meta = JSON.parse(existing.metadata) as typeof meta; } catch { /* ignore */ }
  if (caseId !== undefined) meta.caseId = caseId || null;
  if (descricao !== undefined) meta.descricao = descricao.trim();
  if (valor !== undefined) {
    const valorNum = typeof valor === "string" ? parseFloat(valor.replace(/\./g, "").replace(",", ".")) : Number(valor);
    if (!isFinite(valorNum)) return NextResponse.json({ error: "valor inválido" }, { status: 400 });
    meta.valor = valorNum;
  }
  if (vencimento !== undefined) meta.vencimento = vencimento || null;
  if (status !== undefined) meta.status = status;

  const event = await db.auditEvent.create({
    data: {
      action: "honorario_update",
      resource: "financeiro",
      resourceId: id,
      metadata: JSON.stringify(meta),
    },
  });

  await logAuditEvent({
    action: "honorario_update",
    resource: "financeiro",
    resourceId: id,
    metadata: meta,
  });

  return NextResponse.json({ ok: true, updatedAt: event.createdAt.toISOString(), ...meta });
}

// DELETE /api/financeiro?id=xxx
export async function DELETE(req: NextRequest) {
  const url = new URL(req.url);
  const id = url.searchParams.get("id");
  if (!id) return NextResponse.json({ error: "id obrigatório" }, { status: 400 });

  const existing = await db.auditEvent.findUnique({ where: { id } });
  if (!existing) return NextResponse.json({ error: "Honorário não encontrado" }, { status: 404 });

  // Marca como deletado (cria novo evento de auditoria com action honorario_delete)
  await db.auditEvent.create({
    data: {
      action: "honorario_delete",
      resource: "financeiro",
      resourceId: id,
      metadata: JSON.stringify({ deletedAt: new Date().toISOString(), originalAction: existing.action }),
    },
  });

  await logAuditEvent({
    action: "honorario_delete",
    resource: "financeiro",
    resourceId: id,
  });

  return NextResponse.json({ ok: true });
}
