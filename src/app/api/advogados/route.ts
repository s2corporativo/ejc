import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { logAuditEvent } from "@/lib/audit";
import {
  parseJsonBody,
  normalizeOAB,
  normalizeUF,
  formatOAB,
  PLAN_LIMITS,
  VALID_PLANS,
  VALID_UFS,
  isPrismaUniqueViolation,
} from "@/lib/api-helpers";

export const dynamic = "force-dynamic";

// GET /api/advogados — lista advogados cadastrados
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const plan = url.searchParams.get("plan");
  const uf = url.searchParams.get("uf")?.toUpperCase();

  const where: { plan?: string; oabEstado?: string } = {};
  if (plan && VALID_PLANS.has(plan)) where.plan = plan;
  if (uf && VALID_UFS.has(uf)) where.oabEstado = uf;

  const advogados = await db.user.findMany({
    where,
    orderBy: { createdAt: "desc" },
    take: 200,
    select: {
      id: true,
      email: true,
      name: true,
      oabNumero: true,
      oabEstado: true,
      plan: true,
      minutasUsed: true,
      minutasLimit: true,
      createdAt: true,
      updatedAt: true,
    },
  });

  return NextResponse.json({
    advogados: advogados.map((a) => ({
      ...a,
      oabFormatado: formatOAB(a.oabNumero, a.oabEstado),
      limitePlano: PLAN_LIMITS[a.plan] ?? PLAN_LIMITS.free,
    })),
  });
}

// POST /api/advogados — cadastra novo advogado
export async function POST(req: NextRequest) {
  const parsed = await parseJsonBody<{
    email?: string;
    name?: string;
    oabNumero?: string;
    oabEstado?: string;
    plan?: string;
  }>(req);
  if (!parsed.ok) return NextResponse.json({ error: parsed.error }, { status: 400 });

  const { email, name, oabNumero, oabEstado, plan } = parsed.body;
  if (!email?.trim()) return NextResponse.json({ error: "email obrigatório" }, { status: 400 });

  const uf = normalizeUF(oabEstado);
  const numero = normalizeOAB(oabNumero);
  if (oabNumero && (!uf || !numero || !VALID_UFS.has(uf))) {
    return NextResponse.json({ error: "OAB inválida: informe número e UF válida (ex: OAB/SP 123456)" }, { status: 400 });
  }
  const plano = plan && VALID_PLANS.has(plan) ? plan : "free";

  // Verifica unicidade de email
  const existsEmail = await db.user.findUnique({ where: { email: email.trim().toLowerCase() } });
  if (existsEmail) return NextResponse.json({ error: "email já cadastrado" }, { status: 409 });

  try {
    const user = await db.user.create({
      data: {
        email: email.trim().toLowerCase(),
        name: name?.trim() || null,
        oabNumero: numero || null,
        oabEstado: uf || null,
        plan: plano,
        minutasLimit: PLAN_LIMITS[plano] ?? PLAN_LIMITS.free,
      },
    });

    await logAuditEvent({
      action: "advogado_create",
      resource: "user",
      resourceId: user.id,
      metadata: { email: user.email, oab: formatOAB(user.oabNumero, user.oabEstado), plan: user.plan },
    });

    return NextResponse.json({
      id: user.id,
      email: user.email,
      name: user.name,
      oabFormatado: formatOAB(user.oabNumero, user.oabEstado),
      plan: user.plan,
    });
  } catch (e) {
    if (isPrismaUniqueViolation(e)) {
      return NextResponse.json({ error: "Já existe advogado com esta OAB (estado+numero)" }, { status: 409 });
    }
    throw e;
  }
}

// PATCH /api/advogados — atualiza dados do advogado
export async function PATCH(req: NextRequest) {
  const parsed = await parseJsonBody<{
    id?: string;
    name?: string;
    oabNumero?: string;
    oabEstado?: string;
    plan?: string;
  }>(req);
  if (!parsed.ok) return NextResponse.json({ error: parsed.error }, { status: 400 });

  const { id, name, oabNumero, oabEstado, plan } = parsed.body;
  if (!id) return NextResponse.json({ error: "id obrigatório" }, { status: 400 });

  const existing = await db.user.findUnique({ where: { id } });
  if (!existing) return NextResponse.json({ error: "Advogado não encontrado" }, { status: 404 });

  const data: { name?: string; oabNumero?: string; oabEstado?: string; plan?: string; minutasLimit?: number } = {};
  if (name !== undefined) data.name = name.trim() || null;
  if (oabNumero !== undefined || oabEstado !== undefined) {
    const numero = normalizeOAB(oabNumero ?? existing.oabNumero ?? "");
    const uf = normalizeUF(oabEstado ?? existing.oabEstado ?? "");
    if (!VALID_UFS.has(uf)) return NextResponse.json({ error: "UF inválida" }, { status: 400 });
    data.oabNumero = numero || null;
    data.oabEstado = uf || null;
  }
  if (plan !== undefined) {
    if (!VALID_PLANS.has(plan)) return NextResponse.json({ error: "plan inválido" }, { status: 400 });
    data.plan = plan;
    data.minutasLimit = PLAN_LIMITS[plan] ?? PLAN_LIMITS.free;
  }

  try {
    const updated = await db.user.update({ where: { id }, data });
    await logAuditEvent({
      action: "advogado_update",
      resource: "user",
      resourceId: updated.id,
      metadata: { email: updated.email, oab: formatOAB(updated.oabNumero, updated.oabEstado), plan: updated.plan },
    });
    return NextResponse.json({ ok: true, oabFormatado: formatOAB(updated.oabNumero, updated.oabEstado) });
  } catch (e) {
    if (isPrismaUniqueViolation(e)) {
      return NextResponse.json({ error: "Já existe advogado com esta OAB (estado+numero)" }, { status: 409 });
    }
    throw e;
  }
}
