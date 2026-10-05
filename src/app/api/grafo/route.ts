import { NextRequest, NextResponse } from "next/server";
import { logAuditEvent } from "@/lib/audit";
import { buildSystemGraph, buildCaseGraph } from "@/lib/graph-agent";

export const dynamic = "force-dynamic";

// GET /api/grafo?view=system|case&caseId=xxx
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const view = url.searchParams.get("view") || "system";
  const caseId = url.searchParams.get("caseId") || "";

  if (view === "system") {
    const graph = await buildSystemGraph();
    await logAuditEvent({
      action: "grafo_query",
      resource: "graph",
      metadata: { view: "system", nodes: graph.stats.totalNodes, edges: graph.stats.totalEdges },
    });
    return NextResponse.json(graph);
  }

  if (view === "case") {
    if (!caseId) {
      return NextResponse.json({ error: "caseId obrigatório para view=case" }, { status: 400 });
    }
    const graph = await buildCaseGraph(caseId);
    await logAuditEvent({
      action: "grafo_query",
      resource: "graph",
      resourceId: caseId,
      metadata: { view: "case", nodes: graph.stats.totalNodes, edges: graph.stats.totalEdges },
    });
    return NextResponse.json(graph);
  }

  return NextResponse.json({ error: "view inválido: use 'system' ou 'case'" }, { status: 400 });
}
