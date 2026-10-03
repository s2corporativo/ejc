import { NextResponse } from "next/server";
import { db } from "@/lib/db";

export const dynamic = "force-dynamic";

// GET: lista o ledger de uso imutável
export async function GET() {
  const entries = await db.usageLedger.findMany({
    orderBy: { createdAt: "desc" },
    take: 100,
  });

  const totalDebit = entries
    .filter((e) => e.type === "debit")
    .reduce((sum, e) => sum + Math.abs(e.amount), 0);
  const totalCredit = entries
    .filter((e) => e.type === "credit")
    .reduce((sum, e) => sum + e.amount, 0);

  const currentBalance = entries.length > 0 ? entries[0].balance : 0;

  // Agrupa por operação
  const byOperation = entries.reduce<Record<string, { count: number; total: number }>>(
    (acc, e) => {
      if (!acc[e.operation]) acc[e.operation] = { count: 0, total: 0 };
      acc[e.operation].count++;
      acc[e.operation].total += Math.abs(e.amount);
      return acc;
    },
    {}
  );

  return NextResponse.json({
    entries: entries.map((e) => ({
      id: e.id,
      type: e.type,
      operation: e.operation,
      amount: e.amount,
      balance: e.balance,
      reason: e.reason,
      metadata: safeParse(e.metadata),
      createdAt: e.createdAt.toISOString(),
    })),
    summary: {
      currentBalance,
      totalDebit,
      totalCredit,
      byOperation,
    },
  });
}

function safeParse(raw: string | null): Record<string, unknown> {
  if (!raw) return {};
  try {
    return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return {};
  }
}
