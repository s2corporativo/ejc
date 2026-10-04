"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Brain,
  Loader2,
  FileText,
  Network,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Shield,
  Clock,
  Users,
  Scale,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { useAppStore } from "@/lib/store";
import { toast } from "@/hooks/use-toast";
import { GraphVisual } from "./graph-visual";
import type { EpistemicState } from "@/lib/citation_gate";

// ── Tipos ────────────────────────────────────────────────────────────────────
type AssertionKind = "fact" | "inference" | "gap" | "risk" | "rule" | "precedent" | "conclusion";
type SupportStatus = "supported" | "partial" | "absent" | "conflicting";
type ReviewStatus = "pending" | "confirmed" | "corrected" | "rejected";

interface EvidenceRef { id: string; quote: string; sourceKind: string; }
interface Fact { text: string; evidenceRefIds: string[]; confidence: number; }
interface Event { description: string; date: string | null; dateStatus: string; evidenceRefIds: string[]; }
interface Assertion {
  text: string; kind: AssertionKind; evidenceRefIds: string[]; supportStatus: SupportStatus;
}
interface LegalIssue { key: string; title: string; area: string; question: string; risks: string[]; requiredEvidence: string[]; }
interface StoredAssertion {
  id: string; text: string; kind: AssertionKind; supportStatus: SupportStatus;
  reviewStatus: ReviewStatus; evidenceIds: string[]; createdByAi: boolean;
}
interface StoredNode {
  id: string; nodeType: string; label: string; status: string; confidence: number | null;
  sourceEvidenceId: string | null;
}

interface MapResult {
  runId: string;
  snapshotId: string;
  snapshotVersion: number;
  evidence: EvidenceRef[];
  facts: Fact[];
  events: Event[];
  assertions: Assertion[];
  issues: LegalIssue[];
  warnings: string[];
  llmUsed: boolean;
  tokensUsed: number;
}

interface StoredData {
  assertions: StoredAssertion[];
  nodes: StoredNode[];
}

// ── Configs ─────────────────────────────────────────────────────────────────
const KIND_CONFIG: Record<AssertionKind, { label: string; color: string }> = {
  fact: { label: "Fato", color: "text-green-600 border-green-500/50" },
  inference: { label: "Inferência", color: "text-blue-600 border-blue-500/50" },
  gap: { label: "Lacuna", color: "text-amber-600 border-amber-500/50" },
  risk: { label: "Risco", color: "text-red-600 border-red-500/50" },
  rule: { label: "Regra", color: "text-purple-600 border-purple-500/50" },
  precedent: { label: "Precedente", color: "text-cyan-600 border-cyan-500/50" },
  conclusion: { label: "Conclusão", color: "text-emerald-600 border-emerald-500/50" },
};

const REVIEW_CONFIG: Record<ReviewStatus, { label: string; color: string }> = {
  pending: { label: "Pendente", color: "text-amber-600 bg-amber-500/10" },
  confirmed: { label: "Confirmado", color: "text-green-600 bg-green-500/10" },
  corrected: { label: "Corrigido", color: "text-blue-600 bg-blue-500/10" },
  rejected: { label: "Rejeitado", color: "text-red-600 bg-red-500/10" },
};

const NODE_TYPE_CONFIG: Record<string, { label: string; icon: React.ComponentType<{ className?: string }> }> = {
  fact: { label: "Fato", icon: CheckCircle2 },
  rule: { label: "Regra", icon: Scale },
  person: { label: "Pessoa", icon: Users },
  event: { label: "Evento", icon: Clock },
  risk: { label: "Risco", icon: AlertTriangle },
  evidence: { label: "Evidência", icon: Shield },
};

export function Inteligencia() {
  const { brainContext, setBrainContext } = useAppStore();
  const [facts, setFacts] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<MapResult | null>(null);
  const [stored, setStored] = useState<StoredData | null>(null);
  const [activeTab, setActiveTab] = useState<"resumo" | "fatos" | "grafo" | "afirmacoes">("resumo");

  // Carrega dados persistidos ao montar
  useEffect(() => {
    loadStored();
  }, []);

  // Usa brainContext se vier do Cérebro
  useEffect(() => {
    if (brainContext && !facts) {
      setFacts(brainContext);
    }
  }, [brainContext, facts]);

  const loadStored = useCallback(async () => {
    try {
      const res = await fetch("/api/intelligence/map");
      const data = await res.json();
      setStored(data);
    } catch { /* ignore */ }
  }, []);

  async function mapCase() {
    if (facts.trim().length < 30) {
      toast({ title: "Texto insuficiente (mín. 30 caracteres)", variant: "destructive" });
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch("/api/intelligence/map", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ facts, caseId: "default-case" }),
      });
      const data = await res.json();
      if (data.error) {
        toast({ title: data.error, variant: "destructive" });
      } else {
        setResult(data);
        await loadStored(); // recarrega assertions/nodes persistidos
        toast({
          title: "Mapeamento concluído",
          description: `${data.facts?.length || 0} fatos, ${data.issues?.length || 0} questões, ${data.tokensUsed} tokens`,
        });
      }
    } catch {
      toast({ title: "Erro no mapeamento", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }

  async function review(type: "assertion" | "node", id: string, action: "confirm" | "correct" | "reject") {
    try {
      const res = await fetch("/api/intelligence/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type, id, action, caseId: "default-case" }),
      });
      const data = await res.json();
      if (data.error) {
        toast({ title: data.error, variant: "destructive" });
      } else {
        toast({ title: `${action === "confirm" ? "Confirmado" : action === "correct" ? "Corrigido" : "Rejeitado"}` });
        await loadStored();
      }
    } catch {
      toast({ title: "Erro na revisão", variant: "destructive" });
    }
  }

  return (
    <div className="container-juridia py-8">
      <div className="mb-6">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-lg">
            <Network className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Inteligência Jurídica</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Mapeamento verificável: fatos → evidências → grafo → questões → revisão humana
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_2fr]">
        {/* Input */}
        <Card className="h-fit">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FileText className="h-4 w-4 text-primary" />
              Texto do caso
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="intel-facts" className="text-xs">Fatos do caso</Label>
              <Textarea
                id="intel-facts"
                rows={10}
                value={facts}
                onChange={(e) => setFacts(e.target.value)}
                placeholder="Cole aqui o que o cliente contou..."
                className="scrollbar-juridia"
              />
              <p className="text-[10px] text-muted-foreground">{facts.length} caracteres</p>
            </div>
            <Button onClick={mapCase} disabled={loading || facts.trim().length < 30} className="w-full" size="lg">
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Mapeando...
                </>
              ) : (
                <>
                  <Brain className="mr-2 h-4 w-4" />
                  Mapear caso
                </>
              )}
            </Button>
            {brainContext && (
              <div className="rounded-md border border-primary/40 bg-primary/5 p-2 text-xs">
                <strong className="text-primary">Contexto do Cérebro ativo</strong> — os fatos serão usados como evidência.
              </div>
            )}
            <div className="rounded-md border border-dashed border-border p-2.5 text-[10px] text-muted-foreground">
              <Shield className="mr-1 inline h-3 w-3 text-primary" />
              <strong>Verificável:</strong> cada fato aponta para uma evidência com hash SHA-256. A IA não pode inventar
              fatos nem IDs de evidência. Tudo começa como <code>candidate</code> e exige revisão humana.
            </div>
          </CardContent>
        </Card>

        {/* Results */}
        <div className="space-y-4">
          {loading && (
            <div className="flex flex-col items-center justify-center gap-3 py-12">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">
                Mapeamento determinístico + enriquecimento por IA...
              </p>
            </div>
          )}

          {!loading && !result && stored && (stored.assertions.length > 0 || stored.nodes.length > 0) && (
            <StoredView stored={stored} onReview={review} />
          )}

          {!loading && !result && (!stored || (stored.assertions.length === 0 && stored.nodes.length === 0)) && (
            <Card>
              <CardContent className="flex flex-col items-center justify-center gap-3 py-16 text-center">
                <Network className="h-16 w-16 text-muted-foreground/30" />
                <div>
                  <h3 className="font-semibold">Núcleo de inteligência verificável</h3>
                  <p className="mt-1 text-sm text-muted-foreground max-w-sm">
                    Cole os fatos do caso e o sistema extrairá evidências, fatos, eventos e
                    questões jurídicas — tudo rastreável e sujeito a revisão humana.
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          {result && (
            <ResultView result={result} stored={stored} onReview={review} activeTab={activeTab} setActiveTab={setActiveTab} />
          )}
        </div>
      </div>
    </div>
  );
}

// ── ResultView ───────────────────────────────────────────────────────────────
function ResultView({
  result,
  stored,
  onReview,
  activeTab,
  setActiveTab,
}: {
  result: MapResult;
  stored: StoredData | null;
  onReview: (t: "assertion" | "node", id: string, a: "confirm" | "correct" | "reject") => void;
  activeTab: "resumo" | "fatos" | "grafo" | "afirmacoes";
  setActiveTab: (t: "resumo" | "fatos" | "grafo" | "afirmacoes") => void;
}) {
  const tabs = [
    { id: "resumo" as const, label: "Resumo", icon: Brain },
    { id: "fatos" as const, label: "Fatos & Eventos", icon: FileText },
    { id: "grafo" as const, label: "Grafo", icon: Network },
    { id: "afirmacoes" as const, label: "Afirmações", icon: Scale },
  ];

  return (
    <>
      {/* Summary */}
      <Card className="border-primary/30 bg-primary/5">
        <CardContent className="p-4">
          <div className="grid grid-cols-4 gap-3 text-center">
            <Stat label="Evidências" value={result.evidence.length} icon={Shield} />
            <Stat label="Fatos" value={result.facts.length} icon={CheckCircle2} />
            <Stat label="Questões" value={result.issues.length} icon={Scale} />
            <Stat label="Tokens" value={result.tokensUsed} icon={Brain} />
          </div>
          {result.llmUsed ? (
            <p className="mt-2 text-center text-[10px] text-green-600">✓ Enriquecido por IA + determinístico</p>
          ) : (
            <p className="mt-2 text-center text-[10px] text-amber-600">⚠ Apenas determinístico (IA indisponível — fatos preservados)</p>
          )}
        </CardContent>
      </Card>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-border">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === t.id ? "border-b-2 border-primary text-primary" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <t.icon className="h-4 w-4" />
            {t.label}
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        {activeTab === "resumo" && (
          <motion.div key="resumo" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-3">
            {result.warnings.length > 0 && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-700 dark:text-amber-400">
                {result.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
              </div>
            )}
            {result.issues.length > 0 ? (
              result.issues.map((issue, i) => (
                <Card key={i}>
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <Badge variant="outline" className="text-[10px]">{issue.area}</Badge>
                      <span className="text-sm font-semibold">{issue.title}</span>
                    </div>
                    <p className="mt-2 text-xs text-muted-foreground">{issue.question}</p>
                    <div className="mt-2 grid gap-2 sm:grid-cols-2">
                      <div>
                        <div className="text-[10px] font-semibold uppercase text-muted-foreground">Evidências necessárias</div>
                        <ul className="mt-1 space-y-0.5 text-[11px] text-muted-foreground">
                          {issue.requiredEvidence.map((e, j) => <li key={j}>• {e}</li>)}
                        </ul>
                      </div>
                      <div>
                        <div className="text-[10px] font-semibold uppercase text-red-600">Riscos</div>
                        <ul className="mt-1 space-y-0.5 text-[11px] text-muted-foreground">
                          {issue.risks.map((r, j) => <li key={j}>• {r}</li>)}
                        </ul>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))
            ) : (
              <p className="py-4 text-center text-sm text-muted-foreground">Nenhuma questão jurídica identificada.</p>
            )}
          </motion.div>
        )}

        {activeTab === "fatos" && (
          <motion.div key="fatos" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-3">
            {result.facts.length === 0 && result.events.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">Nenhum fato ou evento extraído.</p>
            ) : (
              <>
                {result.facts.map((f, i) => (
                  <Card key={i}>
                    <CardContent className="p-3">
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-sm text-muted-foreground">{f.text}</span>
                        <Badge variant="outline" className="text-[10px]">conf: {f.confidence.toFixed(2)}</Badge>
                      </div>
                      <div className="mt-1 text-[10px] text-primary">
                        📎 Evidência: {f.evidenceRefIds.join(", ")}
                      </div>
                    </CardContent>
                  </Card>
                ))}
                {result.events.map((e, i) => (
                  <Card key={`ev-${i}`}>
                    <CardContent className="p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <span className="text-sm text-muted-foreground">{e.description}</span>
                          {e.date && <span className="ml-2 font-mono text-[10px] text-primary">{e.date}</span>}
                        </div>
                        <Badge variant="secondary" className="text-[10px]">{e.dateStatus}</Badge>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </>
            )}
          </motion.div>
        )}

        {activeTab === "grafo" && (
          <motion.div key="grafo" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-3">
            <GraphVisual caseId="default-case" />
            {/* Lista de nós para review (mantém a funcionalidade de confirmar/rejeitar) */}
            {stored?.nodes && stored.nodes.filter((n) => n.status === "candidate").length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <Network className="h-4 w-4 text-primary" />
                    Nós pendentes de revisão
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {stored.nodes.filter((n) => n.status === "candidate").map((n, i) => {
                    const cfg = NODE_TYPE_CONFIG[n.nodeType] || NODE_TYPE_CONFIG.fact;
                    const Icon = cfg.icon;
                    return (
                      <div key={n.id} className="flex items-center gap-2 rounded-lg border border-border p-2">
                        <Icon className="h-4 w-4 text-primary" />
                        <span className="flex-1 truncate text-xs">{n.label}</span>
                        <Badge variant="outline" className="text-[10px]">{cfg.label}</Badge>
                        <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => onReview("node", n.id, "confirm")}>
                          <CheckCircle2 className="h-3 w-3 text-green-600" />
                        </Button>
                        <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => onReview("node", n.id, "reject")}>
                          <XCircle className="h-3 w-3 text-red-600" />
                        </Button>
                      </div>
                    );
                  })}
                </CardContent>
              </Card>
            )}
          </motion.div>
        )}

        {activeTab === "afirmacoes" && (
          <motion.div key="afirmacoes" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-2">
            {stored?.assertions?.length === 0 && (
              <p className="py-4 text-center text-sm text-muted-foreground">Nenhuma afirmação registrada.</p>
            )}
            {stored?.assertions?.map((a, i) => {
              const kindCfg = KIND_CONFIG[a.kind] || KIND_CONFIG.inference;
              const revCfg = REVIEW_CONFIG[a.reviewStatus] || REVIEW_CONFIG.pending;
              return (
                <Card key={a.id} className={a.reviewStatus === "confirmed" ? "border-green-500/40" : a.reviewStatus === "rejected" ? "opacity-50" : ""}>
                  <CardContent className="p-3">
                    <div className="flex items-start justify-between gap-2">
                      <span className="flex-1 text-sm text-muted-foreground">{a.text}</span>
                      <Badge variant="outline" className={`text-[10px] ${kindCfg.color}`}>{kindCfg.label}</Badge>
                    </div>
                    <div className="mt-2 flex items-center justify-between">
                      <div className="flex gap-1.5">
                        <Badge variant="secondary" className={`text-[10px] ${revCfg.color}`}>
                          {revCfg.label}
                        </Badge>
                        <Badge variant="outline" className="text-[10px]">{a.supportStatus}</Badge>
                        {a.createdByAi && <Badge variant="outline" className="text-[10px] text-blue-600">IA</Badge>}
                      </div>
                      {a.reviewStatus === "pending" && (
                        <div className="flex gap-1">
                          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => onReview("assertion", a.id, "confirm")} title="Confirmar">
                            <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
                          </Button>
                          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => onReview("assertion", a.id, "reject")} title="Rejeitar">
                            <XCircle className="h-3.5 w-3.5 text-red-600" />
                          </Button>
                        </div>
                      )}
                    </div>
                    {a.evidenceIds.length > 0 && (
                      <div className="mt-1 text-[10px] text-primary">📎 {a.evidenceIds.length} evidência(s)</div>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

function StoredView({ stored, onReview }: { stored: StoredData; onReview: (t: "assertion" | "node", id: string, a: "confirm" | "correct" | "reject") => void }) {
  const pendingAssertions = stored.assertions.filter((a) => a.reviewStatus === "pending");
  const candidateNodes = stored.nodes.filter((n) => n.status === "candidate");

  return (
    <>
      <Card className="border-amber-500/30">
        <CardContent className="p-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-amber-600">
            <AlertTriangle className="h-4 w-4" />
            Revisão humana pendente
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {pendingAssertions.length} afirmação(ões) e {candidateNodes.length} nó(s) aguardando confirmação.
          </p>
        </CardContent>
      </Card>

      {candidateNodes.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm"><Network className="h-4 w-4 text-primary" /> Nós do grafo (rascunho)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {candidateNodes.slice(0, 10).map((n, i) => {
              const cfg = NODE_TYPE_CONFIG[n.nodeType] || NODE_TYPE_CONFIG.fact;
              const Icon = cfg.icon;
              return (
                <div key={n.id} className="flex items-center gap-2 rounded-lg border border-border p-2">
                  <Icon className="h-4 w-4 text-primary" />
                  <span className="flex-1 truncate text-xs">{n.label}</span>
                  <Badge variant="outline" className="text-[10px]">{cfg.label}</Badge>
                  <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => onReview("node", n.id, "confirm")}>
                    <CheckCircle2 className="h-3 w-3 text-green-600" />
                  </Button>
                  <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => onReview("node", n.id, "reject")}>
                    <XCircle className="h-3 w-3 text-red-600" />
                  </Button>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {pendingAssertions.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm"><Scale className="h-4 w-4 text-primary" /> Afirmações pendentes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {pendingAssertions.slice(0, 10).map((a, i) => {
              const kindCfg = KIND_CONFIG[a.kind] || KIND_CONFIG.inference;
              return (
                <div key={a.id} className="flex items-center gap-2 rounded-lg border border-border p-2">
                  <span className="flex-1 truncate text-xs text-muted-foreground">{a.text}</span>
                  <Badge variant="outline" className={`text-[10px] ${kindCfg.color}`}>{kindCfg.label}</Badge>
                  <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => onReview("assertion", a.id, "confirm")}>
                    <CheckCircle2 className="h-3 w-3 text-green-600" />
                  </Button>
                  <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => onReview("assertion", a.id, "reject")}>
                    <XCircle className="h-3 w-3 text-red-600" />
                  </Button>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}
    </>
  );
}

function Stat({ label, value, icon: Icon }: { label: string; value: number; icon: React.ComponentType<{ className?: string }> }) {
  return (
    <div>
      <Icon className="mx-auto mb-1 h-4 w-4 text-primary" />
      <div className="text-lg font-bold">{value}</div>
      <div className="text-[10px] text-muted-foreground">{label}</div>
    </div>
  );
}
