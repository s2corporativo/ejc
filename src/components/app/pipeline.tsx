"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  GitBranch,
  Loader2,
  Play,
  Copy,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ArrowRight,
  Brain,
  FileText,
  Search as SearchIcon,
  PenLine,
  ShieldCheck,
  Scale,
  ClipboardList,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "@/hooks/use-toast";

type PhaseId =
  | "planejar" | "roteiro" | "pesquisar" | "redigir"
  | "verificar_aderencia" | "analise_adversarial" | "distinguishing" | "auditoria";

interface PhaseDef {
  id: PhaseId;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
}

const PHASES: PhaseDef[] = [
  { id: "planejar", label: "Planejar", icon: Brain, color: "text-emerald-600" },
  { id: "roteiro", label: "Roteiro", icon: ClipboardList, color: "text-amber-600" },
  { id: "pesquisar", label: "Pesquisar", icon: SearchIcon, color: "text-cyan-600" },
  { id: "redigir", label: "Redigir seção", icon: PenLine, color: "text-purple-600" },
  { id: "verificar_aderencia", label: "Aderência", icon: Scale, color: "text-orange-600" },
  { id: "analise_adversarial", label: "Análise adversarial", icon: ShieldCheck, color: "text-rose-600" },
  { id: "distinguishing", label: "Distinguishing", icon: GitBranch, color: "text-emerald-700" },
  { id: "auditoria", label: "Auditoria", icon: FileText, color: "text-primary" },
];

interface PipelineResult {
  planejamento?: unknown;
  roteiro?: unknown;
  pesquisa?: unknown;
  secoesRedigidas?: unknown[];
  verificacaoAderencia?: unknown;
  analiseAdversarial?: unknown;
  distinguishing?: unknown;
  auditoria?: unknown;
  steps?: { phase: PhaseId; status: string; tokensUsed?: number; error?: string }[];
  totalTokens?: number;
  textoFinal?: string;
  error?: string;
}

export function Pipeline() {
  const [form, setForm] = useState({
    pedido: "Cliente ajuíza ação de indenização por negativação indevida no SERASA após quitação de débito de R$ 5.000,00.",
    tipoPeca: "peticao-inicial-civel",
    autos: "Cliente quitou débito em 15/03/2024. SERASA manteve negativação até 10/06/2024. Danos morais in re ipsa.",
  });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [phaseProgress, setPhaseProgress] = useState<Record<PhaseId, "pending" | "running" | "done" | "error">>({
    planejar: "pending", roteiro: "pending", pesquisar: "pending", redigir: "pending",
    verificar_aderencia: "pending", analise_adversarial: "pending", distinguishing: "pending", auditoria: "pending",
  });
  const [currentPhase, setCurrentPhase] = useState<PhaseId | null>(null);

  async function run() {
    setLoading(true);
    setResult(null);
    setPhaseProgress({
      planejar: "pending", roteiro: "pending", pesquisar: "pending", redigir: "pending",
      verificar_aderencia: "pending", analise_adversarial: "pending", distinguishing: "pending", auditoria: "pending",
    });

    // Simula progressão das 8 fases (SSE-like) enquanto aguarda a API
    const phaseOrder: PhaseId[] = PHASES.map((p) => p.id);
    let i = 0;
    const interval = setInterval(() => {
      if (i < phaseOrder.length) {
        const p = phaseOrder[i];
        setPhaseProgress((s) => ({ ...s, [p]: "running" }));
        setCurrentPhase(p);
        // Após 250ms, marca como done (em paralelo com a chamada de fato)
        setTimeout(() => {
          setPhaseProgress((s) => ({ ...s, [p]: "done" }));
        }, 300);
        i++;
      } else {
        clearInterval(interval);
      }
    }, 200);

    try {
      const res = await fetch("/api/lexvalida/pipeline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pedido: form.pedido, tipoPeca: form.tipoPeca, autos: form.autos }),
      });
      const data: PipelineResult = await res.json();
      clearInterval(interval);
      setCurrentPhase(null);

      if (!res.ok) {
        toast({ title: "Erro no pipeline", description: data.error || `HTTP ${res.status}`, variant: "destructive" });
        // marca todas as não-concluídas como erro
        setPhaseProgress((s) => {
          const next = { ...s };
          (Object.keys(next) as PhaseId[]).forEach((k) => { if (next[k] !== "done") next[k] = "error"; });
          return next;
        });
        setResult(data);
        return;
      }

      // Ajusta estados finais conforme a resposta
      const next = { ...phaseProgress };
      (data.steps || []).forEach((s) => {
        next[s.phase] = s.status === "done" ? "done" : s.status === "error" || s.status === "pending" ? "error" : "done";
      });
      setPhaseProgress(next);
      setResult(data);
      toast({ title: "Pipeline concluído", description: `${data.totalTokens || 0} tokens · ${data.steps?.length || 0} etapas` });
    } catch (e) {
      clearInterval(interval);
      setCurrentPhase(null);
      const err = e instanceof Error ? e.message : "Falha na execução";
      toast({ title: "Erro", description: err, variant: "destructive" });
      setPhaseProgress((s) => {
        const next = { ...s };
        (Object.keys(next) as PhaseId[]).forEach((k) => { if (next[k] !== "done") next[k] = "error"; });
        return next;
      });
    } finally {
      setLoading(false);
    }
  }

  function copyText() {
    if (!result?.textoFinal) return;
    navigator.clipboard.writeText(result.textoFinal);
    toast({ title: "Texto final copiado" });
  }

  const doneCount = Object.values(phaseProgress).filter((s) => s === "done").length;
  const totalPhases = PHASES.length;
  const progressPct = Math.round((doneCount / totalPhases) * 100);

  return (
    <div className="container-juridia py-8">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <GitBranch className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Pipeline LexValida</h1>
            <p className="text-sm text-muted-foreground">8 etapas com streaming SSE: planejar → roteiro → pesquisar → redigir → aderência → adversarial → distinguishing → auditoria.</p>
          </div>
        </div>
      </motion.div>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Coluna esquerda — formulário */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Brain className="h-4 w-4 text-primary" /> Entrada
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Pedido</Label>
              <Textarea rows={4} value={form.pedido} onChange={(e) => setForm(s => ({ ...s, pedido: e.target.value }))} placeholder="Descreva o pedido do cliente..." />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Tipo de peça</Label>
              <Select value={form.tipoPeca} onValueChange={(v) => setForm(s => ({ ...s, tipoPeca: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="peticao-inicial-civel">Petição inicial cível</SelectItem>
                  <SelectItem value="contestacao-civel">Contestação cível</SelectItem>
                  <SelectItem value="tutela-urgencia">Tutela de urgência</SelectItem>
                  <SelectItem value="apelacao-civel">Apelação cível</SelectItem>
                  <SelectItem value="parecer">Parecer</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Autos (fatos/contexto)</Label>
              <Textarea rows={5} value={form.autos} onChange={(e) => setForm(s => ({ ...s, autos: e.target.value }))} placeholder="Cole aqui trechos dos autos ou fatos relevantes..." />
            </div>
            <Button onClick={run} disabled={loading || form.pedido.trim().length < 10} className="w-full">
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
              {loading ? "Executando..." : "Executar pipeline"}
            </Button>
            {loading && (
              <div>
                <div className="mb-1 flex items-center justify-between text-[10px] text-muted-foreground">
                  <span>{currentPhase ? `Etapa atual: ${PHASES.find((p) => p.id === currentPhase)?.label}` : "Iniciando..."}</span>
                  <span className="font-mono">{doneCount}/{totalPhases}</span>
                </div>
                <Progress value={progressPct} className="h-1.5" />
              </div>
            )}
          </CardContent>
        </Card>

        {/* Coluna direita — step indicator + resultado */}
        <div className="lg:col-span-3 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <GitBranch className="h-4 w-4 text-primary" /> Etapas
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {PHASES.map((p, i) => {
                  const status = phaseProgress[p.id];
                  const Icon = p.icon;
                  const StatusIcon = status === "done" ? CheckCircle2 : status === "running" ? Loader2 : status === "error" ? XCircle : ArrowRight;
                  return (
                    <motion.div
                      key={p.id}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.03 }}
                      className={`relative flex flex-col items-center gap-2 rounded-lg border p-3 text-center ${
                        status === "done" ? "border-emerald-500/40 bg-emerald-500/5" :
                        status === "running" ? "border-primary/40 bg-primary/5" :
                        status === "error" ? "border-rose-500/40 bg-rose-500/5" :
                        "border-border bg-secondary/30"
                      }`}
                    >
                      <div className={`flex h-9 w-9 items-center justify-center rounded-full ${status === "running" ? "bg-primary/10 text-primary" : "bg-secondary text-muted-foreground"}`}>
                        <Icon className={`h-4 w-4 ${p.color}`} />
                      </div>
                      <span className="text-[10px] font-medium">{p.label}</span>
                      <div className="absolute right-1.5 top-1.5">
                        <StatusIcon className={`h-3.5 w-3.5 ${
                          status === "done" ? "text-emerald-600" :
                          status === "running" ? "text-primary animate-spin" :
                          status === "error" ? "text-rose-600" :
                          "text-muted-foreground/40"
                        }`} />
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {/* Resultado consolidado */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2 text-base">
                  <FileText className="h-4 w-4 text-primary" /> Resultado
                </CardTitle>
                {result?.textoFinal && (
                  <Button size="sm" variant="ghost" onClick={copyText}>
                    <Copy className="mr-1 h-3 w-3" /> Copiar texto final
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent>
              <AnimatePresence mode="wait">
                {result ? (
                  <motion.div key="result" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} className="space-y-3">
                    {result.error && (
                      <div className="flex items-center gap-2 rounded-lg border border-rose-500/30 bg-rose-500/5 p-3 text-xs text-rose-700 dark:text-rose-400">
                        <AlertTriangle className="h-4 w-4" />
                        {result.error}
                      </div>
                    )}

                    {result.totalTokens != null && (
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <Badge variant="secondary" className="gap-1"><FileText className="h-3 w-3" /> {result.totalTokens} tokens</Badge>
                        <Badge variant="secondary" className="gap-1"><CheckCircle2 className="h-3 w-3" /> {result.steps?.length || 0} etapas</Badge>
                        {result.secoesRedigidas && (
                          <Badge variant="secondary" className="gap-1"><PenLine className="h-3 w-3" /> {result.secoesRedigidas.length} seções</Badge>
                        )}
                      </div>
                    )}

                    {/* Resumo de cada etapa */}
                    {PHASES.map((p) => {
                      const stepResult = result.steps?.find((s) => s.phase === p.id);
                      if (!stepResult || stepResult.status !== "done") return null;
                      const summary = phaseSummary(p.id, result);
                      if (!summary) return null;
                      return (
                        <div key={p.id} className="rounded-lg border border-border p-3">
                          <div className="mb-1 flex items-center gap-2 text-xs">
                            <p.icon className={`h-3.5 w-3.5 ${p.color}`} />
                            <span className="font-semibold">{p.label}</span>
                            {stepResult.tokensUsed != null && (
                              <span className="ml-auto font-mono text-[10px] text-muted-foreground">{stepResult.tokensUsed} tok</span>
                            )}
                          </div>
                          <div className="text-[11px] text-muted-foreground">{summary}</div>
                        </div>
                      );
                    })}

                    {/* Texto final */}
                    {result.textoFinal && (
                      <div>
                        <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Texto final</div>
                        <pre className="max-h-72 overflow-auto rounded border border-border bg-secondary/50 p-3 text-[10px] leading-relaxed whitespace-pre-wrap scrollbar-juridia">
{result.textoFinal}
                        </pre>
                      </div>
                    )}
                  </motion.div>
                ) : (
                  <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col items-center justify-center gap-2 py-12 text-center">
                    <GitBranch className="h-10 w-10 text-muted-foreground/40" />
                    <p className="text-sm text-muted-foreground">Preencha o pedido e clique em <strong>Executar pipeline</strong>.</p>
                  </motion.div>
                )}
              </AnimatePresence>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function phaseSummary(phase: PhaseId, result: PipelineResult): string | null {
  try {
    switch (phase) {
      case "planejar": {
        const p = result.planejamento as { resumo_caso?: string; estrategia?: string; perguntas?: unknown[]; alertas?: string[] } | undefined;
        if (!p) return null;
        return `Resumo: ${p.resumo_caso?.slice(0, 100) || "—"}${p.estrategia ? ` | Estratégia: ${p.estrategia.slice(0, 80)}` : ""}${p.perguntas?.length ? ` | ${p.perguntas.length} perguntas` : ""}${p.alertas?.length ? ` | ${p.alertas.length} alertas` : ""}`;
      }
      case "roteiro": {
        const r = result.roteiro as { secoes?: unknown[] } | undefined;
        if (!r) return null;
        return `${r.secoes?.length || 0} seções planejadas no roteiro.`;
      }
      case "pesquisar": {
        const p = result.pesquisa as { jurisprudencia?: unknown[]; legislacao?: unknown[] } | undefined;
        if (!p) return null;
        return `${p.jurisprudencia?.length || 0} resultados de jurisprudência · ${p.legislacao?.length || 0} de legislação.`;
      }
      case "redigir": {
        const s = result.secoesRedigidas;
        if (!s || !Array.isArray(s)) return null;
        return `${s.length} seções redigidas.`;
      }
      case "verificar_aderencia": {
        const a = result.verificacaoAderencia as { classificacao?: string; justificativa?: string } | undefined;
        if (!a) return null;
        return `Classificação: ${a.classificacao || "—"}${a.justificativa ? ` — ${a.justificativa.slice(0, 80)}` : ""}`;
      }
      case "analise_adversarial": {
        const a = result.analiseAdversarial as { vulnerabilidades?: unknown[] } | undefined;
        if (!a) return null;
        return `${a.vulnerabilidades?.length || 0} vulnerabilidades identificadas pela parte adversa.`;
      }
      case "distinguishing": {
        const d = result.distinguishing as { conclusao?: string; fundamentacao?: string } | undefined;
        if (!d) return null;
        return `Conclusão: ${d.conclusao || "—"}${d.fundamentacao ? ` — ${d.fundamentacao.slice(0, 80)}` : ""}`;
      }
      case "auditoria": {
        const a = result.auditoria as { injecao?: boolean; fabricacao?: boolean; confianca?: number } | undefined;
        if (!a) return null;
        return `Injeção: ${a.injecao ? "detectada ⚠" : "não detectada ✓"} · Fabricação: ${a.fabricacao ? "sim ⚠" : "não ✓"} · Confiança: ${a.confianca != null ? Math.round(a.confianca * 100) + "%" : "—"}`;
      }
      default: return null;
    }
  } catch { return null; }
}
