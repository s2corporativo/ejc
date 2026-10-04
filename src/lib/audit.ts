import { db } from "@/lib/db";

/**
 * Registra um evento de auditoria (imutável).
 * Chamado por outras APIs quando uma ação relevante acontece.
 */
export async function logAuditEvent(params: {
  action: string;
  resource: string;
  resourceId?: string | null;
  metadata?: Record<string, unknown>;
  userId?: string | null;
  ip?: string | null;
}): Promise<void> {
  try {
    let userId = params.userId;
    if (!userId) {
      const demoUser = await db.user.findUnique({ where: { email: "demo@juridia.com.br" } });
      userId = demoUser?.id;
    }
    await db.auditEvent.create({
      data: {
        userId: userId || null,
        action: params.action,
        resource: params.resource,
        resourceId: params.resourceId || null,
        metadata: JSON.stringify(params.metadata || {}),
        ip: params.ip || null,
      },
    });
  } catch {
    // Não bloquear o fluxo principal se o log falhar
  }
}

/**
 * Registra uma entrada no ledger de uso (imutável).
 * Calcula o novo saldo e armazena.
 */
export async function logUsageEntry(params: {
  type: "debit" | "credit" | "refund" | "adjustment";
  operation: string; // minuta | connect_interaction | search | suggest | case_analysis
  amount: number; // negativo para débito, positivo para crédito
  reason: string;
  metadata?: Record<string, unknown>;
  userId?: string | null;
}): Promise<void> {
  try {
    let userId = params.userId;
    if (!userId) {
      const demoUser = await db.user.findUnique({ where: { email: "demo@juridia.com.br" } });
      userId = demoUser?.id;
    }

    // Pega o saldo mais recente
    const last = await db.usageLedger.findFirst({
      where: { userId: userId || null },
      orderBy: { createdAt: "desc" },
    });
    const prevBalance = last?.balance ?? 200; // default 200 créditos
    const newBalance = prevBalance + params.amount;

    await db.usageLedger.create({
      data: {
        userId: userId || null,
        type: params.type,
        operation: params.operation,
        amount: params.amount,
        balance: newBalance,
        reason: params.reason,
        metadata: JSON.stringify(params.metadata || {}),
      },
    });
  } catch {
    // Não bloquear o fluxo principal
  }
}
