"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Network,
  AlertTriangle,
  Calendar,
  DollarSign,
  GitBranch,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface MapaCasoProps {
  caseId: string;
  caseTitle: string;
  caseFacts?: string;
  caseArea?: string;
  caseNumber?: string | null;
  caseValor?: string | null;
}

interface GraphNode {
  id: string;
  nodeType: string;
  label: string;
  description: string | null;
  confidence: number | null;
  status: string;
}

interface GraphEdge {
  id: string;
  fromNodeId: string;
  toNodeId: string;
  edgeType: string;
  polarity: string;
  status: string;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  summary: {
    totalNodes: number;
    totalEdges: number;
    candidates: number;
    confirmed: number;
    rejected: number;
    nodeTypes: Record<string, { total: number; candidate: number; confirmed: number; rejected: number }>;
  };
}

const NODE_COLORS: Record<string, string> = {
  fact: "#10b981",
  rule: "#a855f7",
  person: "#06b6d4",
  event: "#f59e0b",
  risk: "#ef4444",
  evidence: "#0ea5e9",
  thesis: "#8b5cf6",
  precedent: "#14b8a6",
  document: "#f97316",
  entity: "#ec4899",
};

const NODE_LABELS: Record<string, string> = {
  fact: "Fato", rule: "Regra", person: "Pessoa", event: "Evento",
  risk: "Risco", evidence: "Evidência", thesis: "Tese", precedent: "Precedente",
  document: "Documento", entity: "Entidade",
};

// Detecta contradições: arestas contradicts/denies entre pares de nós
interface Contradicao {
  edge: GraphEdge;
  fromNode?: GraphNode;
  toNode?: GraphNode;
}

// Extrai datas de textos livres
function extractDates(text?: string | null): { date: string; event: string }[] {
  if (!text) return [];
  const lines = text.split(/[\n;]+/).map((l) => l.trim()).filter(Boolean);
  const found: { date: string; event: string }[] = [];
  for (const line of lines) {
    const m = line.match(/(\d{1,2}\/\d{1,2}\/\d{2,4})/);
    if (m) found.push({ date: m[1], event: line.replace(m[1], "").trim() || "evento" });
  }
  return found;
}

// Extrai valores (R$)
function extractValues(text?: string | null): { label: string; amount: string }[] {
  if (!text) return [];
  const matches = text.match(/R\$\s*\d[\d.,]*\d{0,2}/gi) || [];
  return matches.map((m, i) => ({ label: i === 0 ? "Valor principal" : `Valor ${i + 1}`, amount: m }));
}

export function MapaCaso({ caseId, caseTitle, caseFacts, caseArea, caseNumber, caseValor }: MapaCasoProps) {
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/intelligence/graph?caseId=${encodeURIComponent(caseId)}`)
      .then((r) => r.json())
      .then((d: GraphData) => { if (!cancelled) setGraph(d); })
      .catch(() => { if (!cancelled) setGraph(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [caseId]);

  const contradições: Contradicao[] = useMemo(() => {
    if (!graph) return [];
    return graph.edges
      .filter((e) => e.edgeType === "contradicts" || e.edgeType === "denies" || e.polarity === "negative")
      .map((e) => ({
        edge: e,
        fromNode: graph.nodes.find((n) => n.id === e.fromNodeId),
        toNode: graph.nodes.find((n) => n.id === e.toNodeId),
      }))
      .filter((c) => c.fromNode && c.toNode);
  }, [graph]);

  const timelineDates = useMemo(() => extractDates(caseFacts), [caseFacts]);
  const valores = useMemo(() => {
    const extracted = extractValues(caseFacts);
    if (caseValor) extracted.unshift({ label: "Valor da causa", amount: caseValor });
    return extracted;
  }, [caseFacts, caseValor]);

  const stats = useMemo(() => {
    if (!graph) return { nodes: 0, edges: 0, confirmed: 0, contradictions: 0, candidates: 0 };
    return {
      nodes: graph.summary.totalNodes,
      edges: graph.summary.totalEdges,
      confirmed: graph.summary.confirmed,
      candidates: graph.summary.candidates,
      contradictions: contradições.length,
    };
  }, [graph, contradições]);

  // Layout simples em círculo para o mini-grafo
  const miniGraph = useMemo(() => {
    if (!graph) return { nodes: [] as (GraphNode & { x: number; y: number })[], edges: [] as GraphEdge[] };
    const nodes = graph.nodes.slice(0, 20); // máximo 20 no mini
    const nodeIds = new Set(nodes.map((n) => n.id));
    const edges = graph.edges.filter((e) => nodeIds.has(e.fromNodeId) && nodeIds.has(e.toNodeId));
    const cx = 130; const cy = 110; const r = 80;
    const positioned = nodes.map((n, i) => {
      const angle = (i / Math.max(1, nodes.length)) * 2 * Math.PI;
      return { ...n, x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r };
    });
    return { nodes: positioned, edges };
  }, [graph]);

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
      <Card className="border-primary/20">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Network className="h-4 w-4 text-primary" />
            Mapa do caso
            <Badge variant="secondary" className="ml-auto text-[10px]">{caseArea || "civil"}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Header com stats */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            <HeaderStat icon={Network} label="Nós" value={String(stats.nodes)} color="text-cyan-600" bg="bg-cyan-500/10" />
            <HeaderStat icon={GitBranch} label="Arestas" value={String(stats.edges)} color="text-purple-600" bg="bg-purple-500/10" />
            <HeaderStat icon={CheckCircle2} label="Confirmados" value={String(stats.confirmed)} color="text-emerald-600" bg="bg-emerald-500/10" />
            <HeaderStat icon={Clock} label="Candidatos" value={String(stats.candidates)} color="text-amber-600" bg="bg-amber-500/10" />
            <HeaderStat icon={AlertTriangle} label="Contradições" value={String(stats.contradictions)} color="text-rose-600" bg="bg-rose-500/10" />
          </div>

          {loading ? (
            <div className="flex h-32 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div>
          ) : (
            <>
              {/* Contradições */}
              {contradições.length > 0 && (
                <div className="rounded-lg border border-rose-500/30 bg-rose-500/5 p-3">
                  <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-rose-700 dark:text-rose-400">
                    <AlertTriangle className="h-3.5 w-3.5" /> Contradições detectadas ({contradições.length})
                  </div>
                  <div className="space-y-1.5">
                    {contradições.slice(0, 4).map((c, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs">
                        <XCircle className="h-3 w-3 text-rose-600" />
                        <span className="font-medium truncate">{c.fromNode?.label || "?"}</span>
                        <span className="text-muted-foreground">→[{c.edge.edgeType}]→</span>
                        <span className="font-medium truncate">{c.toNode?.label || "?"}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="grid gap-3 lg:grid-cols-2">
                {/* Timeline */}
                <div className="rounded-lg border border-border p-3">
                  <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    <Calendar className="h-3.5 w-3.5" /> Cronologia
                  </div>
                  {timelineDates.length === 0 ? (
                    <p className="py-2 text-center text-[11px] text-muted-foreground">Sem datas detectadas nos fatos.</p>
                  ) : (
                    <div className="relative pl-4 max-h-40 overflow-y-auto scrollbar-juridia">
                      <div className="absolute left-1 top-2 bottom-2 w-px bg-border" />
                      <div className="space-y-1.5">
                        {timelineDates.map((d, i) => (
                          <div key={i} className="relative">
                            <div className="absolute -left-3.5 top-1.5 h-1.5 w-1.5 rounded-full bg-primary ring-2 ring-background" />
                            <div className="text-[11px]">
                              <span className="font-mono text-primary">{d.date}</span>
                              <span className="ml-2 text-muted-foreground">{d.event}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* Valores */}
                <div className="rounded-lg border border-border p-3">
                  <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    <DollarSign className="h-3.5 w-3.5" /> Valores
                  </div>
                  {valores.length === 0 ? (
                    <p className="py-2 text-center text-[11px] text-muted-foreground">Nenhum valor detectado.</p>
                  ) : (
                    <div className="space-y-1">
                      {valores.map((v, i) => (
                        <div key={i} className="flex items-center justify-between text-[11px]">
                          <span className="text-muted-foreground">{v.label}</span>
                          <span className="font-mono font-medium">{v.amount}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Mini-grafo */}
              <div className="rounded-lg border border-border p-3">
                <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  <Network className="h-3.5 w-3.5" /> Grafo de entidades
                </div>
                {miniGraph.nodes.length === 0 ? (
                  <p className="py-2 text-center text-[11px] text-muted-foreground">Nenhuma entidade mapeada. Execute o Cérebro ou Inteligência.</p>
                ) : (
                  <svg viewBox="0 0 260 220" className="w-full" style={{ maxHeight: 220 }}>
                    {/* Arestas */}
                    {miniGraph.edges.map((e) => {
                      const a = miniGraph.nodes.find((n) => n.id === e.fromNodeId);
                      const b = miniGraph.nodes.find((n) => n.id === e.toNodeId);
                      if (!a || !b) return null;
                      return (
                        <line
                          key={e.id}
                          x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                          stroke={e.polarity === "negative" ? "#ef4444" : "#a855f7"}
                          strokeWidth={1}
                          strokeOpacity={0.6}
                          strokeDasharray={e.polarity === "negative" ? "3 2" : undefined}
                        />
                      );
                    })}
                    {/* Nós */}
                    {miniGraph.nodes.map((n) => (
                      <g key={n.id}>
                        <circle
                          cx={n.x} cy={n.y} r={5}
                          fill={NODE_COLORS[n.nodeType] || "#6b7280"}
                          fillOpacity={n.status === "rejected" ? 0.3 : 0.85}
                          stroke="#fff"
                          strokeWidth={1}
                        />
                        {n.status === "confirmed" && (
                          <circle cx={n.x} cy={n.y} r={7} fill="none" stroke="#10b981" strokeWidth={1} />
                        )}
                        <text
                          x={n.x + 7} y={n.y + 3}
                          fontSize={7}
                          fill="#374151"
                        >
                          {n.label.length > 22 ? n.label.slice(0, 20) + "..." : n.label}
                        </text>
                      </g>
                    ))}
                  </svg>
                )}
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}

function HeaderStat({ icon: Icon, label, value, color, bg }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string; color: string; bg: string }) {
  return (
    <div className="rounded-lg border border-border p-2 text-center">
      <div className={`mx-auto mb-1 flex h-6 w-6 items-center justify-center rounded ${bg} ${color}`}>
        <Icon className="h-3 w-3" />
      </div>
      <div className="text-sm font-bold">{value}</div>
      <div className="text-[9px] text-muted-foreground">{label}</div>
    </div>
  );
}
