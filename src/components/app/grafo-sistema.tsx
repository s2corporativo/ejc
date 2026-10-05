"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Network,
  Loader2,
  Download,
  Boxes,
  GitBranch,
  Activity,
  ShieldCheck,
  AlertTriangle,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "@/hooks/use-toast";

interface CaseItem { id: string; title: string; }

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
    edgeTypes: Record<string, number>;
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
  contract: "#84cc16",
  obligation: "#a3a3a3",
  request: "#fde047",
  requirement: "#22c55e",
};

const EDGE_COLORS: Record<string, string> = {
  contradicts: "#ef4444",
  denies: "#ef4444",
  supports: "#10b981",
  proves: "#10b981",
  grounds: "#a855f7",
  requires: "#f59e0b",
  depends_on: "#06b6d4",
  represents: "#0ea5e9",
  party_to: "#8b5cf6",
  has_risk: "#ef4444",
  has_request: "#f59e0b",
  occurred_at: "#f97316",
  results_in: "#22c55e",
};

const NODE_LABELS: Record<string, string> = {
  fact: "Fato", rule: "Regra", person: "Pessoa", event: "Evento",
  risk: "Risco", evidence: "Evidência", thesis: "Tese", precedent: "Precedente",
  document: "Documento", entity: "Entidade", contract: "Contrato",
  obligation: "Obrigação", request: "Pedido", requirement: "Requisito",
};

// ── Force-directed layout simplificado ─────────────────────────────────────────
interface PositionedNode extends GraphNode {
  x: number;
  y: number;
}

function layout(nodes: GraphNode[], edges: GraphEdge[], width: number, height: number, iterations = 100): PositionedNode[] {
  if (nodes.length === 0) return [];
  const cx = width / 2;
  const cy = height / 2;
  const positioned: PositionedNode[] = nodes.map((n, i) => {
    const angle = (i / nodes.length) * 2 * Math.PI;
    const r = Math.min(width, height) * 0.35;
    return { ...n, x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r };
  });
  const idx: Record<string, number> = {};
  positioned.forEach((n, i) => { idx[n.id] = i; });
  const k = Math.sqrt((width * height) / Math.max(1, nodes.length));
  for (let iter = 0; iter < iterations; iter++) {
    // Repulsão entre todos os pares
    const forces: { x: number; y: number }[] = positioned.map(() => ({ x: 0, y: 0 }));
    for (let i = 0; i < positioned.length; i++) {
      for (let j = i + 1; j < positioned.length; j++) {
        const dx = positioned[i].x - positioned[j].x;
        const dy = positioned[i].y - positioned[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const force = (k * k) / (dist * dist);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        forces[i].x += fx; forces[i].y += fy;
        forces[j].x -= fx; forces[j].y -= fy;
      }
    }
    // Atração das arestas
    for (const e of edges) {
      const i = idx[e.fromNodeId]; const j = idx[e.toNodeId];
      if (i == null || j == null) continue;
      const dx = positioned[i].x - positioned[j].x;
      const dy = positioned[i].y - positioned[j].y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const force = (dist * dist) / k;
      const fx = (dx / dist) * force * 0.5;
      const fy = (dy / dist) * force * 0.5;
      forces[i].x -= fx; forces[i].y -= fy;
      forces[j].x += fx; forces[j].y += fy;
    }
    // Aplica forças com damping + clamp
    for (let i = 0; i < positioned.length; i++) {
      const fmag = Math.sqrt(forces[i].x ** 2 + forces[i].y ** 2);
      if (fmag > 0) {
        const maxStep = 15;
        const step = Math.min(fmag, maxStep) / fmag;
        positioned[i].x += forces[i].x * step * 0.1;
        positioned[i].y += forces[i].y * step * 0.1;
      }
      // Atrai ao centro
      positioned[i].x += (cx - positioned[i].x) * 0.01;
      positioned[i].y += (cy - positioned[i].y) * 0.01;
      // Clamp dentro dos limites
      const margin = 30;
      positioned[i].x = Math.max(margin, Math.min(width - margin, positioned[i].x));
      positioned[i].y = Math.max(margin, Math.min(height - margin, positioned[i].y));
    }
  }
  return positioned;
}

export function GrafoSistema() {
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedCaseId, setSelectedCaseId] = useState<string>("default-case");
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/cases")
      .then((r) => r.json())
      .then((d) => {
        const list: CaseItem[] = [{ id: "default-case", title: "Caso padrão (default-case)" }, ...(d.cases || []).map((c: { id: string; title: string }) => ({ id: c.id, title: c.title }))];
        setCases(list);
      })
      .catch(() => setCases([{ id: "default-case", title: "Caso padrão" }]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/intelligence/graph?caseId=${encodeURIComponent(selectedCaseId)}`)
      .then((r) => r.json())
      .then((d: GraphData) => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) setData(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [selectedCaseId]);

  const SVG_W = 760;
  const SVG_H = 480;

  const positioned = useMemo(() => {
    if (!data || data.nodes.length === 0) return [];
    return layout(data.nodes, data.edges, SVG_W, SVG_H, 80);
  }, [data]);

  const idx: Record<string, number> = useMemo(() => {
    const m: Record<string, number> = {};
    positioned.forEach((n, i) => { m[n.id] = i; });
    return m;
  }, [positioned]);

  const topHubs = useMemo(() => {
    if (!data) return [];
    const degree: Record<string, number> = {};
    for (const e of data.edges) {
      degree[e.fromNodeId] = (degree[e.fromNodeId] || 0) + 1;
      degree[e.toNodeId] = (degree[e.toNodeId] || 0) + 1;
    }
    const arr = Object.entries(degree)
      .map(([id, deg]) => ({ node: data.nodes.find((n) => n.id === id), degree: deg }))
      .filter((x) => x.node)
      .sort((a, b) => b.degree - a.degree)
      .slice(0, 5);
    return arr;
  }, [data]);

  function exportJSON() {
    if (!data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `grafo-${selectedCaseId}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast({ title: "JSON exportado" });
  }

  return (
    <div className="container-juridia py-8">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="mb-6 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Network className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">Grafo do sistema</h1>
              <p className="text-sm text-muted-foreground">Visualização force-directed do grafo jurídico (nós + arestas).</p>
            </div>
          </div>
          <div className="flex gap-2">
            <Select value={selectedCaseId} onValueChange={setSelectedCaseId}>
              <SelectTrigger className="w-[200px]"><SelectValue /></SelectTrigger>
              <SelectContent>
                {cases.map((c) => <SelectItem key={c.id} value={c.id}>{c.title}</SelectItem>)}
              </SelectContent>
            </Select>
            <Button variant="outline" onClick={exportJSON} disabled={!data}>
              <Download className="mr-2 h-4 w-4" /> Exportar JSON
            </Button>
          </div>
        </div>
      </motion.div>

      {loading ? (
        <div className="flex h-96 items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>
      ) : !data || data.nodes.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <Network className="h-12 w-12 text-muted-foreground/40" />
            <div>
              <h3 className="font-semibold">Nenhum nó encontrado</h3>
              <p className="mt-1 text-sm text-muted-foreground">Execute o Cérebro ou Inteligência para mapear entidades do caso.</p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-4">
          {/* SVG canvas */}
          <Card className="lg:col-span-3">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Network className="h-4 w-4 text-primary" /> Topologia
                <Badge variant="secondary" className="ml-auto text-[10px]">{data.summary.totalNodes} nós · {data.summary.totalEdges} arestas</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto scrollbar-juridia">
                <svg viewBox={`0 0 ${SVG_W} ${SVG_H}`} className="w-full" style={{ minWidth: 600, background: "radial-gradient(circle at center, #fafafa, #f3f4f6)" }}>
                  {/* Arestas */}
                  {data.edges.map((e) => {
                    const i = idx[e.fromNodeId]; const j = idx[e.toNodeId];
                    if (i == null || j == null) return null;
                    const a = positioned[i]; const b = positioned[j];
                    const color = EDGE_COLORS[e.edgeType] || "#a3a3a3";
                    const isHighlighted = hoveredNode === e.fromNodeId || hoveredNode === e.toNodeId;
                    return (
                      <line
                        key={e.id}
                        x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                        stroke={color}
                        strokeWidth={isHighlighted ? 2 : 1}
                        strokeOpacity={isHighlighted ? 1 : 0.5}
                        strokeDasharray={e.polarity === "negative" ? "4 3" : undefined}
                      />
                    );
                  })}
                  {/* Nós */}
                  {positioned.map((n) => {
                    const color = NODE_COLORS[n.nodeType] || "#6b7280";
                    const isHovered = hoveredNode === n.id;
                    const r = n.status === "confirmed" ? 8 : n.status === "rejected" ? 6 : 7;
                    return (
                      <motion.g
                        key={n.id}
                        initial={{ opacity: 0, scale: 0 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ duration: 0.4 }}
                        onMouseEnter={() => setHoveredNode(n.id)}
                        onMouseLeave={() => setHoveredNode(null)}
                        style={{ cursor: "pointer" }}
                      >
                        <circle
                          cx={n.x} cy={n.y} r={isHovered ? r + 2 : r}
                          fill={color}
                          fillOpacity={n.status === "rejected" ? 0.25 : 0.85}
                          stroke={isHovered ? "#000" : color}
                          strokeWidth={isHovered ? 2 : 1}
                        />
                        {n.status === "rejected" && (
                          <line x1={n.x - r} y1={n.y - r} x2={n.x + r} y2={n.y + r} stroke="#ef4444" strokeWidth={1.5} />
                        )}
                        {(isHovered || n.status === "confirmed") && (
                          <text
                            x={n.x + r + 4} y={n.y + 3}
                            fontSize={9}
                            fill="#374151"
                            fontWeight={isHovered ? 600 : 400}
                          >
                            {n.label.length > 28 ? n.label.slice(0, 25) + "..." : n.label}
                          </text>
                        )}
                      </motion.g>
                    );
                  })}
                  {/* Tooltip */}
                  {hoveredNode && (() => {
                    const n = positioned.find((x) => x.id === hoveredNode);
                    if (!n) return null;
                    return (
                      <g>
                        <rect x={n.x + 12} y={n.y - 32} width={Math.max(160, n.label.length * 6 + 24)} height={50} fill="#1f2937" rx={4} />
                        <text x={n.x + 20} y={n.y - 18} fill="#fff" fontSize={10} fontWeight={600}>{n.label}</text>
                        <text x={n.x + 20} y={n.y - 5} fill="#9ca3af" fontSize={9}>
                          {NODE_LABELS[n.nodeType] || n.nodeType} · {n.status}{n.confidence != null ? ` · ${Math.round(n.confidence * 100)}%` : ""}
                        </text>
                      </g>
                    );
                  })()}
                </svg>
              </div>
            </CardContent>
          </Card>

          {/* Sidebar — stats */}
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Activity className="h-4 w-4 text-primary" /> Estatísticas
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-xs">
                <StatLine icon={Boxes} label="Nós totais" value={String(data.summary.totalNodes)} />
                <StatLine icon={GitBranch} label="Arestas totais" value={String(data.summary.totalEdges)} />
                <StatLine icon={ShieldCheck} label="Confirmados" value={String(data.summary.confirmed)} color="text-emerald-600" />
                <StatLine icon={Boxes} label="Candidatos" value={String(data.summary.candidates)} color="text-amber-600" />
                <StatLine icon={AlertTriangle} label="Rejeitados" value={String(data.summary.rejected)} color="text-rose-600" />
              </CardContent>
            </Card>

            {/* Top hubs */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Network className="h-4 w-4 text-primary" /> Top hubs
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {topHubs.length === 0 ? (
                    <p className="py-2 text-center text-xs text-muted-foreground">Nenhum hub.</p>
                  ) : topHubs.map((h, i) => h.node && (
                    <div key={h.node.id} className="flex items-center gap-2 text-xs">
                      <Badge variant="outline" className="text-[10px]">#{i + 1}</Badge>
                      <div className="flex h-2 w-2 rounded-full" style={{ background: NODE_COLORS[h.node.nodeType] || "#6b7280" }} />
                      <span className="flex-1 truncate font-medium">{h.node.label}</span>
                      <span className="font-mono text-muted-foreground">{h.degree}×</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Legenda */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Boxes className="h-4 w-4 text-primary" /> Legenda
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-1.5 text-[10px]">
                  {Object.entries(NODE_LABELS).map(([k, v]) => (
                    <div key={k} className="flex items-center gap-1.5">
                      <div className="h-2.5 w-2.5 rounded-full" style={{ background: NODE_COLORS[k] || "#6b7280" }} />
                      <span>{v}</span>
                    </div>
                  ))}
                </div>
                <div className="mt-3 border-t border-border pt-2">
                  <div className="mb-1 text-[9px] uppercase tracking-wider text-muted-foreground">Arestas</div>
                  <div className="grid grid-cols-1 gap-1 text-[10px]">
                    <div className="flex items-center gap-1.5"><div className="h-px w-5 bg-emerald-500" /> suporte/prova</div>
                    <div className="flex items-center gap-1.5"><div className="h-px w-5 bg-rose-500" /> contradição/nega</div>
                    <div className="flex items-center gap-1.5"><div className="h-px w-5 bg-purple-500" /> fundamenta</div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

function StatLine({ icon: Icon, label, value, color }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string; color?: string }) {
  return (
    <div className="flex items-center gap-2">
      <Icon className={`h-3.5 w-3.5 ${color || "text-muted-foreground"}`} />
      <span className="flex-1 text-muted-foreground">{label}</span>
      <span className={`font-mono font-semibold ${color || ""}`}>{value}</span>
    </div>
  );
}
