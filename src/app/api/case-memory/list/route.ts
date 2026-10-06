// /api/case-memory/list — Lista os últimos casos com memória.
import { NextRequest, NextResponse } from "next/server";
import { listRecentCaseMemory } from "@/lib/case_memory";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const limit = Number(url.searchParams.get("limit") ?? "20");
  const items = await listRecentCaseMemory(limit);
  return NextResponse.json({ items });
}