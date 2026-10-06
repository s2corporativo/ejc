// /api/historico/list — Lista as últimas gerações do usuário/caso.
// /api/historico/save — Salva uma geração no PecaHistory.

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const caseId = url.searchParams.get("caseId");
  const limit = Number(url.searchParams.get("limit") ?? "20");
  const where = caseId ? { caseId } : {};
  const rows = await db.pecaHistory.findMany({
    where,
    orderBy: { createdAt: "desc" },
    take: limit,
    select: {
      id: true,
      caseId: true,
      tipoPeca: true,
      area: true,
      templateSlug: true,
      provider: true,
      tokensUsed: true,
      createdAt: true,
    },
  });
  return NextResponse.json({ items: rows });
}