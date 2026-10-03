import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { logAuditEvent } from "@/lib/audit";

export const dynamic = "force-dynamic";

// GET: lista casos (com option ?clientId=xxx para filtrar)
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const clientId = url.searchParams.get("clientId");
  const status = url.searchParams.get("status");

  const where: { clientId?: string; status?: string } = {};
  if (clientId) where.clientId = clientId;
  if (status) where.status = status;

  const cases = await db.case.findMany({
    where,
    orderBy: { updatedAt: "desc" },
    include: {
      client: { select: { id: true, name: true, color: true } },
      _count: { select: { documents: true } },
    },
  });

  return NextResponse.json({
    cases: cases.map((c) => ({
      id: c.id,
      title: c.title,
      number: c.number,
      area: c.area,
      status: c.status,
      notes: c.notes,
      clientId: c.clientId,
      clientName: c.client?.name,
      clientColor: c.client?.color,
      documentsCount: c._count.documents,
      createdAt: c.createdAt.toISOString(),
      updatedAt: c.updatedAt.toISOString(),
    })),
  });
}

// POST: cria novo caso
export async function POST(req: NextRequest) {
  let body: {
    clientId?: string;
    title?: string;
    number?: string;
    area?: string;
    notes?: string;
  } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }

  if (!body.clientId) {
    return NextResponse.json({ error: "clientId obrigatório" }, { status: 400 });
  }
  if (!body.title?.trim()) {
    return NextResponse.json({ error: "Título do caso obrigatório" }, { status: 400 });
  }

  const newCase = await db.case.create({
    data: {
      clientId: body.clientId,
      title: body.title.trim(),
      number: body.number?.trim() || null,
      area: body.area || "civil",
      notes: body.notes?.trim() || null,
      status: "active",
    },
  });

  await logAuditEvent({
    action: "create_case",
    resource: "case",
    resourceId: newCase.id,
    metadata: { title: newCase.title, clientId: body.clientId },
  });

  return NextResponse.json({
    id: newCase.id,
    title: newCase.title,
    number: newCase.number,
    area: newCase.area,
    status: newCase.status,
    clientId: newCase.clientId,
    createdAt: newCase.createdAt.toISOString(),
  });
}

// PATCH: atualiza caso
export async function PATCH(req: NextRequest) {
  let body: {
    id?: string;
    title?: string;
    number?: string;
    area?: string;
    status?: string;
    notes?: string;
  } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }

  if (!body.id) {
    return NextResponse.json({ error: "id obrigatório" }, { status: 400 });
  }

  const data: {
    title?: string;
    number?: string | null;
    area?: string;
    status?: string;
    notes?: string | null;
  } = {};

  if (body.title !== undefined) data.title = body.title.trim();
  if (body.number !== undefined) data.number = body.number.trim() || null;
  if (body.area !== undefined) data.area = body.area;
  if (body.status !== undefined) data.status = body.status;
  if (body.notes !== undefined) data.notes = body.notes.trim() || null;

  const updated = await db.case.update({
    where: { id: body.id },
    data,
  });

  await logAuditEvent({
    action: "update_case",
    resource: "case",
    resourceId: body.id,
    metadata: { title: updated.title, status: updated.status },
  });

  return NextResponse.json({ ok: true });
}

// DELETE: exclui caso
export async function DELETE(req: NextRequest) {
  const url = new URL(req.url);
  const id = url.searchParams.get("id");
  if (!id) return NextResponse.json({ error: "id obrigatório" }, { status: 400 });

  const c = await db.case.findUnique({ where: { id }, select: { title: true } });
  await db.case.delete({ where: { id } });

  await logAuditEvent({
    action: "delete_case",
    resource: "case",
    resourceId: id,
    metadata: { title: c?.title },
  });

  return NextResponse.json({ ok: true });
}
