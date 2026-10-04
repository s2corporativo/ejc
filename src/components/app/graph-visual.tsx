"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Network, Loader2, Shield, CheckCircle2, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";

interface GraphNodeData {
  id: string;
  nodeType: string;
  label: string;
  description: string | null;
  confidence: number | null;
  status: string;
  sourceEvidenceId: string | null;
  payload: Record<string, unknown>;
}

interface GraphEdgeData {
  id: string;
  fromNodeId: string;
  toNodeId: string;
  edgeType: string;
  polarity: string;
  status: string;
}

const NODE_COLORS: Record<string, string> = {
  fact: "#22c55e",
  rule: "#a855f7",
  person: "#3b82f6",
  event: "#f59e0b",
  risk: "#ef4444",
  evidence: "#06b6d4",
  thesis: "#8b5cf6",
  precedent: "#0ea5e9",
};

const NODE_LABELS: Record<string, string> = {
  fact: "Fato", rule: "Regra", person: "Pessoa", event: "Evento",
  risk: "Risco", evidence: "Evidência", thesis: "Tese", precedent: "Precedente",
};

export function GraphVisual({ caseId = "default-case" }: { caseId?: string }) {
  const [nodes, setNodes] = useState<GraphNodeData[]>([]);
  const [edges, setEdges] = useState<GraphEdgeData[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<GraphNodeData | null>(null);

  useEffect(() => {
    loadGraph();
  }, [caseId]);

  async function loadGraph() {
    setLoading(true);
    try {
      const res = await fetch(`/api/intelligence/graph?caseId=${caseId}`);
      const data = await res.json();
      setNodes(data.nodes || []);
      setEdges(data.edges || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }

  if (loading) {
    return (
      <div className="flex h-48 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  if (nodes.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
          <Network className="h-12 w-12 text-muted-foreground/30" />
          <p className="text-sm text-muted-foreground">Grafo vazio — execute o mapeamento de caso para gerar nós.</p>
        </CardContent>
      </Card>
    );
  }

  // Layout: posiciona nós em círculo agrupados por tipo
  const byType: Record<string, GraphNodeData[]> = {};
  for (const n of nodes) {
    if (!byType[n.nodeType]) byType[n.nodeType] = [];
    byType[n.nodeType].push(n);
  }

  const types = Object.keys(byType);
  const radius = 180;
  const centerX = 250;
  const centerY = 250;
  const positions: Record<string, { x: number; y: number }> = {};

  let angle = 0;
  const angleStep = (2 * Math.PI) / Math.max(nodes.length, 1);
  for (const type of types) {
    for (const node of byType[type]) {
      const r = radius - (types.indexOf(type) * 20);
      positions[node.id] = {
        x: centerX + Math.cos(angle) * r,
        y: centerY + Math.sin(angle) * r,
      };
      angle += angleStep;
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
      {/* Graph SVG */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Network className="h-4 w-4 text-primary" />
            Knowledge Graph
            <Badge variant="outline" className="ml-auto text-[10px]">
              {nodes.length} nós · {edges.length} arestas
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="relative overflow-auto rounded-lg border border-border bg-secondary/20" style={{ minHeight: "400px" }}>
            <svg width="500" height="500" className="mx-auto" style={{ maxWidth: "100%" }}>
              {/* Edges */}
              {edges.map((e) => {
                const from = positions[e.fromNodeId];
                const to = positions[e.toNodeId];
                if (!from || !to) return null;
                const color = e.polarity === "positive" ? "#22c55e" : e.polarity === "negative" ? "#ef4444" : "#94a3b8";
                return (
                  <line
                    key={e.id}
                    x1={from.x} y1={from.y} x2={to.x} y2={to.y}
                    stroke={color} strokeWidth={e.status === "confirmed" ? 2 : 1}
                    strokeDasharray={e.status === "candidate" ? "4 2" : "none"}
                    opacity={0.6}
                  />
                );
              })}
              {/* Nodes */}
              {nodes.map((n) => {
                const pos = positions[n.id];
                if (!pos) return null;
                const color = NODE_COLORS[n.nodeType] || "#64748b";
                const r = n.status === "confirmed" ? 22 : n.status === "rejected" ? 16 : 18;
                return (
                  <g key={n.id} className="cursor-pointer" onClick={() => setSelected(n)}>
                    <circle
                      cx={pos.x} cy={pos.y} r={r}
                      fill={n.status === "rejected" ? "#f1f5f9" : color}
                      fillOpacity={n.status === "confirmed" ? 1 : 0.3}
                      stroke={color} strokeWidth={2}
                      opacity={n.status === "rejected" ? 0.4 : 1}
                    />
                    {n.status === "confirmed" && (
                      <circle cx={pos.x + r - 4} cy={pos.y - r + 4} r={6} fill="#22c55e" stroke="white" strokeWidth={1.5} />
                    )}
                    <text
                      x={pos.x} y={pos.y + r + 12}
                      textAnchor="middle" className="text-[8px] fill-muted-foreground"
                      style={{ fontSize: "8px" }}
                    >
                      {n.label.slice(0, 25)}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
          {/* Legend */}
          <div className="mt-2 flex flex-wrap gap-2">
            {types.map((t) => (
              <Badge key={t} variant="outline" className="gap-1 text-[10px]">
                <span className="h-2 w-2 rounded-full" style={{ background: NODE_COLORS[t] || "#64748b" }} />
                {NODE_LABELS[t] || t} ({byType[t].length})
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Node detail panel */}
      {selected && (
        <motion.div initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }}>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Network className="h-4 w-4 text-primary" />
                Detalhe do nó
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              <div>
                <span className="text-muted-foreground">Tipo: </span>
                <Badge variant="outline" className="text-[10px]" style={{ color: NODE_COLORS[selected.nodeType] }}>
                  {NODE_LABELS[selected.nodeType] || selected.nodeType}
                </Badge>
              </div>
              <div>
                <span className="text-muted-foreground">Status: </span>
                {selected.status === "confirmed" ? (
                  <Badge variant="outline" className="gap-1 text-[10px] text-green-600"><CheckCircle2 className="h-2.5 w-2.5" /> Confirmado</Badge>
                ) : selected.status === "rejected" ? (
                  <Badge variant="outline" className="gap-1 text-[10px] text-red-600"><XCircle className="h-2.5 w-2.5" /> Rejeitado</Badge>
                ) : (
                  <Badge variant="outline" className="gap-1 text-[10px] text-amber-600"><Shield className="h-2.5 w-2.5" /> Candidato</Badge>
                )}
              </div>
              <div>
                <span className="text-muted-foreground">Texto: </span>
                <p className="mt-1 rounded border border-border bg-secondary/30 p-2">{selected.label}</p>
              </div>
              {selected.description && (
                <div>
                  <span className="text-muted-foreground">Descrição: </span>
                  <p className="text-muted-foreground">{selected.description}</p>
                </div>
              )}
              {selected.confidence != null && (
                <div><span className="text-muted-foreground">Confiança: </span>{selected.confidence.toFixed(2)}</div>
              )}
              {selected.sourceEvidenceId && (
                <div className="flex items-center gap-1 text-primary">
                  <Shield className="h-3 w-3" /> Evidência vinculada: {selected.sourceEvidenceId.slice(0, 12)}...
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>
      )}
    </div>
  );
}
