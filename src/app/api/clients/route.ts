import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { logAuditEvent } from "@/lib/audit";

export const dynamic = "force-dynamic";

// GET: lista clientes do escritório
export async function GET() {
  const clients = await db.client.findMany({
    orderBy: { updatedAt: "desc" },
    include: {
      _count: { select: { cases: true } },
    },
  });

  // Conta documentos por cliente (via cases)
  const clientsWithStats = await Promise.all(
    clients.map(async (c) => {
      const cases = await db.case.findMany({
        where: { clientId: c.id },
        select: { id: true },
      });
      const caseIds = cases.map((cs) => cs.id);
      const docCount = await db.document.count({
        where: { caseId: { in: caseIds } },
      });
      return {
        id: c.id,
        name: c.name,
        email: c.email,
        phone: c.phone,
        document: c.document,
        notes: c.notes,
        color: c.color,
        casesCount: c._count.cases,
        documentsCount: docCount,
        createdAt: c.createdAt.toISOString(),
        updatedAt: c.updatedAt.toISOString(),
      };
    })
  );

  return NextResponse.json({ clients: clientsWithStats });
}

// POST: cria novo cliente
export async function POST(req: NextRequest) {
  let body: {
    name?: string;
    email?: string;
    phone?: string;
    document?: string;
    notes?: string;
    color?: string;
  } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }

  if (!body.name?.trim()) {
    return NextResponse.json({ error: "Nome obrigatório" }, { status: 400 });
  }

  const demoUser = await db.user.findUnique({ where: { email: "demo@juridia.com.br" } });

  const client = await db.client.create({
    data: {
      userId: demoUser?.id,
      name: body.name.trim(),
      email: body.email?.trim() || null,
      phone: body.phone?.trim() || null,
      document: body.document?.trim() || null,
      notes: body.notes?.trim() || null,
      color: body.color || "",
    },
  });

  await logAuditEvent({
    action: "create_client",
    resource: "client",
    resourceId: client.id,
    metadata: { name: client.name },
  });

  return NextResponse.json({
    id: client.id,
    name: client.name,
    email: client.email,
    phone: client.phone,
    document: client.document,
    notes: client.notes,
    color: client.color,
    createdAt: client.createdAt.toISOString(),
  });
}

// PATCH: atualiza cliente
export async function PATCH(req: NextRequest) {
  let body: {
    id?: string;
    name?: string;
    email?: string;
    phone?: string;
    document?: string;
    notes?: string;
    color?: string;
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
    name?: string;
    email?: string | null;
    phone?: string | null;
    document?: string | null;
    notes?: string | null;
    color?: string;
  } = {};

  if (body.name !== undefined) data.name = body.name.trim();
  if (body.email !== undefined) data.email = body.email.trim() || null;
  if (body.phone !== undefined) data.phone = body.phone.trim() || null;
  if (body.document !== undefined) data.document = body.document.trim() || null;
  if (body.notes !== undefined) data.notes = body.notes.trim() || null;
  if (body.color !== undefined) data.color = body.color;

  const updated = await db.client.update({
    where: { id: body.id },
    data,
  });

  await logAuditEvent({
    action: "update_client",
    resource: "client",
    resourceId: body.id,
    metadata: { name: updated.name },
  });

  return NextResponse.json({ ok: true });
}

// DELETE: exclui cliente
export async function DELETE(req: NextRequest) {
  const url = new URL(req.url);
  const id = url.searchParams.get("id");
  if (!id) return NextResponse.json({ error: "id obrigatório" }, { status: 400 });

  const client = await db.client.findUnique({ where: { id }, select: { name: true } });
  await db.client.delete({ where: { id } });

  await logAuditEvent({
    action: "delete_client",
    resource: "client",
    resourceId: id,
    metadata: { name: client?.name },
  });

  return NextResponse.json({ ok: true });
}
