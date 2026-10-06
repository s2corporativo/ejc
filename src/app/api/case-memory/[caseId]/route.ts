// /api/case-memory/[caseId] — Retorna a memória do caso (histórico).
// /api/case-memory/list — Lista os últimos casos com memória.

import { NextRequest, NextResponse } from "next/server";
import { getCaseMemory } from "@/lib/case_memory";

export const dynamic = "force-dynamic";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ caseId: string }> },
) {
  const { caseId } = await params;
  const memory = await getCaseMemory(caseId);
  if (!memory) return NextResponse.json({ error: "Sem memória" }, { status: 404 });
  return NextResponse.json(memory);
}