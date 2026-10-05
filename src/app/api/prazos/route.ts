import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { logAuditEvent } from "@/lib/audit";
import { parseJsonBody, MAX_PRAZO_DIAS } from "@/lib/api-helpers";
import { calculateDeadline } from "@/lib/legal_calculator";

export const dynamic = "force-dynamic";

// GET /api/prazos?caseId=xxx — lista deadlines
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const caseId = url.searchParams.get("caseId");
  const from = url.searchParams.get("from");
  const to = url.searchParams.get("to");

  const where: { caseId?: string; vencimento?: { gte?: Date; lte?: Date } } = {};
  if (caseId) where.caseId = caseId;
  if (from || to) {
    where.vencimento = {};
    if (from) where.vencimento.gte = new Date(from);
    if (to) where.vencimento.lte = new Date(to);
  }

  const deadlines = await db.caseDeadline.findMany({
    where,
    orderBy: { vencimento: "asc" },
    take: 200,
  });

  return NextResponse.json({
    prazos: deadlines.map((d) => ({
      id: d.id,
      caseId: d.caseId,
      tipo: d.tipo,
      descricao: d.descricao,
      marcoInicial: d.marcoInicial.toISOString(),
      prazoDias: d.prazoDias,
      tipoContagem: d.tipoContagem,
      vencimento: d.vencimento.toISOString(),
      observacoes: d.observacoes,
      diasRestantes: Math.ceil((d.vencimento.getTime() - Date.now()) / 86400000),
      createdAt: d.createdAt.toISOString(),
    })),
    total: deadlines.length,
  });
}

// POST /api/prazos — calcula prazo e armazena
export async function POST(req: NextRequest) {
  const parsed = await parseJsonBody<{
    caseId?: string;
    tipo?: string;
    descricao?: string;
    marcoInicial?: string;
    prazoDias?: number;
    tipoContagem?: string;
    observacoes?: string;
  }>(req);
  if (!parsed.ok) return NextResponse.json({ error: parsed.error }, { status: 400 });

  const { caseId, tipo, descricao, marcoInicial, prazoDias, tipoContagem, observacoes } = parsed.body;
  if (!descricao?.trim()) return NextResponse.json({ error: "descricao obrigatória" }, { status: 400 });
  if (!marcoInicial) return NextResponse.json({ error: "marcoInicial obrigatório" }, { status: 400 });
  const prazo = Number(prazoDias);
  if (!prazo || prazo <= 0) return NextResponse.json({ error: "prazoDias inválido" }, { status: 400 });
  if (prazo > MAX_PRAZO_DIAS) return NextResponse.json({ error: `prazoDias acima do limite (${MAX_PRAZO_DIAS})` }, { status: 400 });

  const marco = new Date(marcoInicial);
  if (isNaN(marco.getTime())) return NextResponse.json({ error: "marcoInicial inválido" }, { status: 400 });

  const tipoCont = (tipoContagem as "uteis" | "corridos") || "uteis";
  const result = calculateDeadline(marco, prazo, tipoCont);

  const deadline = await db.caseDeadline.create({
    data: {
      caseId: caseId || "default-case",
      tipo: tipo || "outro",
      descricao: descricao.trim(),
      marcoInicial: marco,
      prazoDias: prazo,
      tipoContagem: tipoCont,
      vencimento: result.vencimento,
      observacoes: observacoes?.trim() || null,
    },
  });

  await logAuditEvent({
    action: "prazo_create",
    resource: "case_deadline",
    resourceId: deadline.id,
    metadata: {
      caseId: deadline.caseId,
      tipo: deadline.tipo,
      prazoDias: prazo,
      tipoContagem: tipoCont,
      vencimento: deadline.vencimento.toISOString(),
    },
  });

  return NextResponse.json({
    id: deadline.id,
    caseId: deadline.caseId,
    tipo: deadline.tipo,
    descricao: deadline.descricao,
    marcoInicial: deadline.marcoInicial.toISOString(),
    prazoDias: deadline.prazoDias,
    tipoContagem: deadline.tipoContagem,
    vencimento: deadline.vencimento.toISOString(),
    observacoes: deadline.observacoes,
    observacoesCalculo: result.observacoes,
    diasUteis: result.diasUteis,
    diasCorridos: result.diasCorridos,
  });
}

// PATCH /api/prazos
export async function PATCH(req: NextRequest) {
  const parsed = await parseJsonBody<{
    id?: string;
    tipo?: string;
    descricao?: string;
    prazoDias?: number;
    tipoContagem?: string;
    observacoes?: string;
  }>(req);
  if (!parsed.ok) return NextResponse.json({ error: parsed.error }, { status: 400 });

  const { id, tipo, descricao, prazoDias, tipoContagem, observacoes } = parsed.body;
  if (!id) return NextResponse.json({ error: "id obrigatório" }, { status: 400 });

  const existing = await db.caseDeadline.findUnique({ where: { id } });
  if (!existing) return NextResponse.json({ error: "Prazo não encontrado" }, { status: 404 });

  const data: Record<string, unknown> = {};
  if (tipo !== undefined) data.tipo = tipo;
  if (descricao !== undefined) data.descricao = descricao.trim();
  if (observacoes !== undefined) data.observacoes = observacoes?.trim() || null;

  // Se mudou prazoDias ou tipoContagem, recalcula vencimento
  let novoPrazo = existing.prazoDias;
  let novoCont = existing.tipoContagem as "uteis" | "corridos";
  if (prazoDias !== undefined) {
    const n = Number(prazoDias);
    if (n > 0 && n <= MAX_PRAZO_DIAS) {
      data.prazoDias = n;
      novoPrazo = n;
    } else {
      return NextResponse.json({ error: "prazoDias inválido" }, { status: 400 });
    }
  }
  if (tipoContagem !== undefined) {
    data.tipoContagem = tipoContagem;
    novoCont = tipoContagem as "uteis" | "corridos";
  }
  if (prazoDias !== undefined || tipoContagem !== undefined) {
    const r = calculateDeadline(existing.marcoInicial, novoPrazo, novoCont);
    data.vencimento = r.vencimento;
  }

  const updated = await db.caseDeadline.update({ where: { id }, data });

  await logAuditEvent({
    action: "prazo_update",
    resource: "case_deadline",
    resourceId: id,
    metadata: { ...data, prevPrazoDias: existing.prazoDias, prevTipoContagem: existing.tipoContagem },
  });

  return NextResponse.json({
    id: updated.id,
    vencimento: updated.vencimento.toISOString(),
    prazoDias: updated.prazoDias,
    tipoContagem: updated.tipoContagem,
  });
}

// DELETE /api/prazos?id=xxx
export async function DELETE(req: NextRequest) {
  const url = new URL(req.url);
  const id = url.searchParams.get("id");
  if (!id) return NextResponse.json({ error: "id obrigatório" }, { status: 400 });

  const existing = await db.caseDeadline.findUnique({ where: { id }, select: { caseId: true, descricao: true } });
  if (!existing) return NextResponse.json({ error: "Prazo não encontrado" }, { status: 404 });

  await db.caseDeadline.delete({ where: { id } });

  await logAuditEvent({
    action: "prazo_delete",
    resource: "case_deadline",
    resourceId: id,
    metadata: { caseId: existing.caseId, descricao: existing.descricao },
  });

  return NextResponse.json({ ok: true });
}
