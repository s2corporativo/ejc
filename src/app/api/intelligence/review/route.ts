import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { logAuditEvent } from "@/lib/audit";

export const dynamic = "force-dynamic";

// POST /api/intelligence/review — revisa uma assertion ou node (HITL)
// Princípio 9: Confirmação jurídica depende de revisão humana.
// Princípio 10: Confirmação exige evidência (node sem source_evidence_id não pode ser confirmado).
export async function POST(req: NextRequest) {
  let body: {
    type?: "assertion" | "node";
    id?: string;
    action?: "confirm" | "correct" | "reject";
    caseId?: string;
    correctedText?: string;
  } = {};
  try { body = await req.json(); } catch { return NextResponse.json({ error: "JSON inválido" }, { status: 400 }); }

  if (!body.type || !body.id || !body.action) {
    return NextResponse.json({ error: "type, id, action obrigatórios" }, { status: 400 });
  }

  const caseId = body.caseId || "default-case";
  const reviewer = "advogado";

  if (body.type === "assertion") {
    const assertion = await db.legalAssertion.findUnique({ where: { id: body.id } });
    if (!assertion) return NextResponse.json({ error: "Assertion não encontrada" }, { status: 404 });

    // Princípio 11: assertion com support=absent não pode ser confirmada
    if (body.action === "confirm" && assertion.supportStatus === "absent") {
      return NextResponse.json({
        error: "Assertion com suporte ausente não pode ser confirmada — adicione evidência primeiro"
      }, { status: 422 });
    }

    const newReviewStatus = body.action === "confirm" ? "confirmed" : body.action === "correct" ? "corrected" : "rejected";
    const updated = await db.legalAssertion.update({
      where: { id: body.id },
      data: {
        reviewStatus: newReviewStatus,
        reviewedBy: reviewer,
        reviewedAt: new Date(),
        ...(body.correctedText ? { text: body.correctedText } : {}),
      },
    });

    await logAuditEvent({
      action: `review_assertion_${body.action}`,
      resource: "assertion",
      resourceId: body.id,
      metadata: { caseId, kind: assertion.kind, newStatus: newReviewStatus },
    });

    return NextResponse.json({ ok: true, reviewStatus: newReviewStatus });
  }

  if (body.type === "node") {
    const node = await db.graphNode.findUnique({ where: { id: body.id } });
    if (!node) return NextResponse.json({ error: "Node não encontrado" }, { status: 404 });

    // Princípio 10: Confirmação exige evidência
    if (body.action === "confirm" && !node.sourceEvidenceId) {
      return NextResponse.json({
        error: "Confirmação exige evidência — node sem source_evidence_id não pode ser confirmado"
      }, { status: 422 });
    }

    const newStatus = body.action === "confirm" ? "confirmed" : "rejected";
    const updated = await db.graphNode.update({
      where: { id: body.id },
      data: {
        status: newStatus,
        reviewedBy: reviewer,
        reviewedAt: new Date(),
      },
    });

    await logAuditEvent({
      action: `review_node_${body.action}`,
      resource: "node",
      resourceId: body.id,
      metadata: { caseId, nodeType: node.nodeType, newStatus },
    });

    return NextResponse.json({ ok: true, status: newStatus });
  }

  return NextResponse.json({ error: "Tipo inválido (use 'assertion' ou 'node')" }, { status: 400 });
}
