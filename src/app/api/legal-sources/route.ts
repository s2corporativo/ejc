import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { logAuditEvent } from "@/lib/audit";

export const dynamic = "force-dynamic";

// GET: lista fontes jurídicas curadas (com filtros opcionais)
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const tipo = url.searchParams.get("tipo");
  const diploma = url.searchParams.get("diploma");

  const where: { tipo?: string; diploma?: { contains: string } } = {};
  if (tipo) where.tipo = tipo;
  if (diploma) where.diploma = { contains: diploma };

  const sources = await db.legalSource.findMany({
    where,
    orderBy: [{ diploma: "asc" }, { numero: "asc" }],
    take: 500,
  });

  return NextResponse.json({
    sources: sources.map((s) => ({
      id: s.id,
      tipo: s.tipo,
      diploma: s.diploma,
      numero: s.numero,
      tribunal: s.tribunal,
      textoTrecho: s.textoTrecho,
      vigente: s.vigente,
      urlOficial: s.urlOficial,
      hashConteudo: s.hashConteudo,
      dataConsulta: s.dataConsulta?.toISOString(),
      revisadoPor: s.revisadoPor,
      createdAt: s.createdAt.toISOString(),
      updatedAt: s.updatedAt.toISOString(),
    })),
    total: sources.length,
  });
}

// POST: cria nova fonte jurídica
export async function POST(req: NextRequest) {
  let body: {
    tipo?: string;
    diploma?: string;
    numero?: string;
    tribunal?: string;
    textoTrecho?: string;
    vigente?: boolean;
    urlOficial?: string;
    revisadoPor?: string;
  } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }

  if (!body.tipo || !body.diploma || !body.numero) {
    return NextResponse.json(
      { error: "tipo, diploma e numero obrigatórios" },
      { status: 400 }
    );
  }

  try {
    const source = await db.legalSource.create({
      data: {
        tipo: body.tipo,
        diploma: body.diploma,
        numero: body.numero,
        tribunal: body.tribunal || null,
        textoTrecho: body.textoTrecho || "",
        vigente: body.vigente ?? true,
        urlOficial: body.urlOficial || null,
        dataConsulta: body.urlOficial ? new Date() : null,
        revisadoPor: body.revisadoPor || "curador",
      },
    });

    await logAuditEvent({
      action: "create_legal_source",
      resource: "legal_source",
      resourceId: source.id,
      metadata: { tipo: body.tipo, diploma: body.diploma, numero: body.numero },
    });

    return NextResponse.json({
      id: source.id,
      tipo: source.tipo,
      diploma: source.diploma,
      numero: source.numero,
      tribunal: source.tribunal,
      vigente: source.vigente,
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Erro ao criar fonte";
    // Unique constraint = já existe
    if (msg.includes("Unique constraint")) {
      return NextResponse.json(
        { error: "Fonte já existe na base curada" },
        { status: 409 }
      );
    }
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

// PATCH: atualiza fonte (ex: marcar como não vigente)
export async function PATCH(req: NextRequest) {
  let body: {
    id?: string;
    textoTrecho?: string;
    vigente?: boolean;
    urlOficial?: string;
    revisadoPor?: string;
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
    textoTrecho?: string;
    vigente?: boolean;
    urlOficial?: string;
    revisadoPor?: string;
    dataConsulta?: Date;
  } = {};

  if (body.textoTrecho !== undefined) data.textoTrecho = body.textoTrecho;
  if (body.vigente !== undefined) data.vigente = body.vigente;
  if (body.urlOficial !== undefined) {
    data.urlOficial = body.urlOficial;
    data.dataConsulta = new Date();
  }
  if (body.revisadoPor !== undefined) data.revisadoPor = body.revisadoPor;

  const updated = await db.legalSource.update({
    where: { id: body.id },
    data,
  });

  await logAuditEvent({
    action: "update_legal_source",
    resource: "legal_source",
    resourceId: body.id,
    metadata: { diploma: updated.diploma, numero: updated.numero, vigente: updated.vigente },
  });

  return NextResponse.json({ ok: true });
}

// DELETE: exclui fonte
export async function DELETE(req: NextRequest) {
  const url = new URL(req.url);
  const id = url.searchParams.get("id");
  if (!id) return NextResponse.json({ error: "id obrigatório" }, { status: 400 });

  const src = await db.legalSource.findUnique({ where: { id }, select: { diploma: true, numero: true } });
  await db.legalSource.delete({ where: { id } });

  await logAuditEvent({
    action: "delete_legal_source",
    resource: "legal_source",
    resourceId: id,
    metadata: { diploma: src?.diploma, numero: src?.numero },
  });

  return NextResponse.json({ ok: true });
}
