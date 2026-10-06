// /api/historico/save — Persiste uma geração de peça para retomar depois.
import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { logAuditEvent } from "@/lib/audit";

export const dynamic = "force-dynamic";

interface Body {
  caseId?: string;
  userId?: string;
  tipoPeca: string;
  area: string;
  templateSlug?: string;
  fatos: string;
  pedidos?: string;
  gerado: string;
  provider: string;
  tokensUsed?: number;
  metadata?: Record<string, unknown>;
}

export async function POST(req: NextRequest) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }
  if (!body.gerado || !body.tipoPeca || !body.area) {
    return NextResponse.json({ error: "gerado, tipoPeca e area obrigatórios" }, { status: 400 });
  }

  const row = await db.pecaHistory.create({
    data: {
      caseId: body.caseId ?? "default-case",
      userId: body.userId ?? null,
      tipoPeca: body.tipoPeca,
      area: body.area,
      templateSlug: body.templateSlug ?? null,
      fatos: body.fatos,
      pedidos: body.pedidos ?? null,
      gerado: body.gerado,
      provider: body.provider,
      tokensUsed: body.tokensUsed ?? 0,
      metadata: JSON.stringify(body.metadata ?? {}),
    },
  });

  await logAuditEvent({
    action: "save_historico",
    resource: "peca_history",
    resourceId: row.id,
    metadata: { tipoPeca: body.tipoPeca, area: body.area },
  });

  return NextResponse.json({ ok: true, id: row.id });
}