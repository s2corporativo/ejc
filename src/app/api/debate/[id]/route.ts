// /api/debate/[id] — Retorna debate completo + todos os turnos.

import { NextRequest, NextResponse } from "next/server";
import { getDebate, listDebateTurns } from "@/lib/debate_audit";

export const dynamic = "force-dynamic";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const debate = await getDebate(id);
  if (!debate) {
    return NextResponse.json({ error: "Debate não encontrado" }, { status: 404 });
  }
  const turns = await listDebateTurns(id);
  return NextResponse.json({ debate, turns });
}