import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

export const dynamic = "force-dynamic";

// GET /api/cases/hearings?caseId=xxx
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const caseId = url.searchParams.get("caseId");
  if (!caseId) return NextResponse.json({ error: "caseId obrigatório" }, { status: 400 });

  const audiencias = await db.caseHearing.findMany({
    where: { caseId },
    orderBy: { data: "asc" },
  });

  return NextResponse.json({
    audiencias: audiencias.map((a) => ({
      id: a.id,
      data: a.data.toISOString(),
      tipo: a.tipo,
      local: a.local,
      orgao: a.orgao,
      status: a.status,
      resultado: a.resultado,
      observacoes: a.observacoes,
    })),
  });
}

// POST
export async function POST(req: NextRequest) {
  let body: { caseId?: string; data?: string; tipo?: string; local?: string; orgao?: string; observacoes?: string } = {};
  try { body = await req.json(); } catch { return NextResponse.json({ error: "JSON inválido" }, { status: 400 }); }

  if (!body.caseId || !body.data) return NextResponse.json({ error: "caseId e data obrigatórios" }, { status: 400 });

  const aud = await db.caseHearing.create({
    data: {
      caseId: body.caseId,
      data: new Date(body.data),
      tipo: body.tipo || "outra",
      local: body.local || null,
      orgao: body.orgao || null,
      observacoes: body.observacoes || null,
    },
  });

  return NextResponse.json({ id: aud.id, ok: true });
}

// PATCH (atualizar status/resultado)
export async function PATCH(req: NextRequest) {
  let body: { id?: string; status?: string; resultado?: string; observacoes?: string } = {};
  try { body = await req.json(); } catch { return NextResponse.json({ error: "JSON inválido" }, { status: 400 }); }

  if (!body.id) return NextResponse.json({ error: "id obrigatório" }, { status: 400 });

  const data: Record<string, unknown> = {};
  if (body.status !== undefined) data.status = body.status;
  if (body.resultado !== undefined) data.resultado = body.resultado;
  if (body.observacoes !== undefined) data.observacoes = body.observacoes;

  await db.caseHearing.update({ where: { id: body.id }, data });
  return NextResponse.json({ ok: true });
}

// DELETE
export async function DELETE(req: NextRequest) {
  const url = new URL(req.url);
  const id = url.searchParams.get("id");
  if (!id) return NextResponse.json({ error: "id obrigatório" }, { status: 400 });
  await db.caseHearing.delete({ where: { id } });
  return NextResponse.json({ ok: true });
}
