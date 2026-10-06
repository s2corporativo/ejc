// /api/debate/list — Lista debates por caseId (ou todos se caseId omitido).

import { NextRequest, NextResponse } from "next/server";
import { listDebatesByCase } from "@/lib/debate_audit";
import { db } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const caseId = url.searchParams.get("caseId");
  if (caseId) {
    const debates = await listDebatesByCase(caseId);
    return NextResponse.json({ debates });
  }
  // Sem caseId → últimos 20 debates (modo admin/debug)
  const rows = await db.multiAgentDebate.findMany({
    orderBy: { createdAt: "desc" },
    take: 20,
  });
  return NextResponse.json({ debates: rows });
}