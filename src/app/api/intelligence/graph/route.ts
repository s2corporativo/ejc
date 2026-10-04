import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

export const dynamic = "force-dynamic";

// GET /api/intelligence/graph?caseId=xxx — retorna nós e arestas do grafo jurídico
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const caseId = url.searchParams.get("caseId") || "default-case";

  const [nodes, edges] = await Promise.all([
    db.graphNode.findMany({
      where: { caseId },
      orderBy: { createdAt: "desc" },
      take: 100,
    }),
    db.graphEdge.findMany({
      where: { caseId },
      orderBy: { createdAt: "desc" },
      take: 200,
    }),
  ]);

  // Conta por tipo e status
  const nodeTypes: Record<string, { total: number; candidate: number; confirmed: number; rejected: number }> = {};
  for (const n of nodes) {
    if (!nodeTypes[n.nodeType]) nodeTypes[n.nodeType] = { total: 0, candidate: 0, confirmed: 0, rejected: 0 };
    nodeTypes[n.nodeType].total++;
    nodeTypes[n.nodeType][n.status as "candidate" | "confirmed" | "rejected"]++;
  }

  const edgeTypes: Record<string, number> = {};
  for (const e of edges) {
    edgeTypes[e.edgeType] = (edgeTypes[e.edgeType] || 0) + 1;
  }

  return NextResponse.json({
    nodes: nodes.map((n) => ({
      id: n.id,
      nodeType: n.nodeType,
      label: n.label,
      description: n.description,
      confidence: n.confidence,
      status: n.status,
      sourceEvidenceId: n.sourceEvidenceId,
      payload: JSON.parse(n.payload || "{}"),
      createdAt: n.createdAt.toISOString(),
    })),
    edges: edges.map((e) => ({
      id: e.id,
      fromNodeId: e.fromNodeId,
      toNodeId: e.toNodeId,
      edgeType: e.edgeType,
      polarity: e.polarity,
      weight: e.weight,
      status: e.status,
      sourceEvidenceId: e.sourceEvidenceId,
    })),
    summary: {
      totalNodes: nodes.length,
      totalEdges: edges.length,
      candidates: nodes.filter((n) => n.status === "candidate").length,
      confirmed: nodes.filter((n) => n.status === "confirmed").length,
      rejected: nodes.filter((n) => n.status === "rejected").length,
      nodeTypes,
      edgeTypes,
    },
  });
}

// POST /api/intelligence/graph — cria aresta (GraphEdge) — IA só pode criar candidate
export async function POST(req: NextRequest) {
  let body: {
    caseId?: string;
    fromNodeId?: string;
    toNodeId?: string;
    edgeType?: string;
    polarity?: string;
  } = {};
  try { body = await req.json(); } catch { return NextResponse.json({ error: "JSON inválido" }, { status: 400 }); }

  if (!body.fromNodeId || !body.toNodeId || !body.edgeType) {
    return NextResponse.json({ error: "fromNodeId, toNodeId, edgeType obrigatórios" }, { status: 400 });
  }

  if (body.fromNodeId === body.toNodeId) {
    return NextResponse.json({ error: "fromNodeId e toNodeId não podem ser iguais" }, { status: 422 });
  }

  const caseId = body.caseId || "default-case";

  // Valida que ambos os nós pertencem ao mesmo caso (Princípio: bloquear vínculos cruzados)
  const [fromNode, toNode] = await Promise.all([
    db.graphNode.findUnique({ where: { id: body.fromNodeId } }),
    db.graphNode.findUnique({ where: { id: body.toNodeId } }),
  ]);

  if (!fromNode || !toNode) {
    return NextResponse.json({ error: "Nó não encontrado" }, { status: 404 });
  }

  if (fromNode.caseId !== caseId || toNode.caseId !== caseId) {
    return NextResponse.json({ error: "Nós pertencem a casos diferentes — vínculo cruzado bloqueado" }, { status: 422 });
  }

  // IA só pode criar candidate (Princípio: IA nunca cria confirmed)
  const edge = await db.graphEdge.create({
    data: {
      caseId,
      fromNodeId: body.fromNodeId,
      toNodeId: body.toNodeId,
      edgeType: body.edgeType,
      polarity: body.polarity || "neutral",
      status: "candidate",
    },
  });

  return NextResponse.json({ id: edge.id, status: "candidate" });
}
