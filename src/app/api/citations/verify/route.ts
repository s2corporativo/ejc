import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { verifyCitations } from "@/lib/citation_gate";
import { logAuditEvent } from "@/lib/audit";

export const dynamic = "force-dynamic";

// POST: verifica citações de um texto contra a base curada
export async function POST(req: NextRequest) {
  let body: { text?: string; documentId?: string } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }

  const text = (body.text || "").trim();
  if (!text || text.length < 20) {
    return NextResponse.json(
      { error: "Texto muito curto (mín. 20 caracteres)" },
      { status: 400 }
    );
  }

  // Carrega TODAS as fontes curadas para verificação
  const sources = await db.legalSource.findMany({
    orderBy: [{ diploma: "asc" }, { numero: "asc" }],
  });

  const result = verifyCitations(text, sources);

  // Registra evento de auditoria
  await logAuditEvent({
    action: "verify_citations",
    resource: "document",
    resourceId: body.documentId || null,
    metadata: {
      total: result.total,
      verificadas: result.verificadas,
      suspeitas: result.suspeitas,
      bloquear: result.bloquear,
    },
  });

  return NextResponse.json(result);
}
