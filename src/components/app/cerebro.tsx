"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Brain,
  Loader2,
  Sparkles,
  Users,
  Clock,
  ListChecks,
  DollarSign,
  Scale,
  FileText,
  TrendingUp,
  TrendingDown,
  HelpCircle,
  Target,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ExternalLink,
  ArrowRight,
  Zap,
  Wand2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { useAppStore } from "@/lib/store";
import { toast } from "@/hooks/use-toast";

interface BrainStep {
  id: string;
  name: string;
  status: "pending" | "running" | "done" | "error";
}

interface BrainResult {
  parties: { role: string; name?: string; type: string }[];
  timeline: { date: string; event: string }[];
  requests: string[];
  values: { label: string; amount: string }[];
  legalIssues: { question: string; area: string; relevance: string }[];
  applicableLaw: {
    diploma: string;
    numero: string;
    textoTrecho: string;
    vigente: boolean;
    urlOficial?: string | null;
    applicability: string;
  }[];
  jurisprudence: {
    name: string;
    url: string;
    snippet: string;
    host_name: string;
    favorable: boolean | null;
  }[];
  viability: {
    probability: string;
    strengths: string[];
    weaknesses: string[];
    reasoning: string;
  };
  gaps: { what: string; why: string; question: string }[];
  strategy: {
    proceduralPath: string;
    immediateActions: string[];
    documentsToCollect: string[];
    risks: string[];
    recommendation: string;
  };
  steps: BrainStep[];
  totalTokens: number;
}

const STEP_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  extract: Users,
  issues: Scale,
  law: FileText,
  jurisprudence: ListChecks,
  viability: Target,
  gaps: HelpCircle,
  strategy: Zap,
};

const STEP_DESCS: Record<string, string> = {
  extract: "Extraindo partes, cronologia, pedidos e valores...",
  issues: "Identificando questões jurídicas do caso...",
  law: "Buscando legislação aplicável na base curada...",
  jurisprudence: "Pesquisando jurisprudência dos tribunais...",
  viability: "Analisando forças, fragilidades e probabilidade...",
  gaps: "Identificando lacunas factuais e perguntas...",
  strategy: "Montando estratégia processual recomendada...",
};

const PROB_CONFIG = {
  alta: { color: "text-green-600", bg: "bg-green-500/10 border-green-500/30", label: "Alta probabilidade" },
  média: { color: "text-amber-600", bg: "bg-amber-500/10 border-amber-500/30", label: "Média probabilidade" },
  baixa: { color: "text-red-600", bg: "bg-red-500/10 border-red-500/30", label: "Baixa probabilidade" },
} as const;

export function Cerebro() {
  const { setAppTab, setCurrentDocId } = useAppStore();
  const [facts, setFacts] = useState("");
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BrainResult | null>(null);
  const [currentStep, setCurrentStep] = useState(0);

  const SAMPLE = `O cliente João da Silva foi inscrito indevidamente no SERASA em 15/01/2026 pelo Banco XYZ, após já ter quitado o débito de R$ 5.000,00 em 10/12/2025. O cliente possui comprovante de pagamento. Sofreu constrangimento ao tentar obter crédito. Pede indenização por danos morais no valor de R$ 50.000,00. Relação de consumo caracterizada.`;

  async function analyze() {
    if (facts.trim().length < 30) {
      toast({ title: "Descreva os fatos (mín. 30 caracteres)", variant: "destructive" });
      return;
    }
    setLoading(true);
    setResult(null);
    setCurrentStep(0);

    // Simula progressão das etapas enquanto a API processa
    const stepInterval = setInterval(() => {
      setCurrentStep((s) => Math.min(s + 1, 6));
    }, 5000);

    try {
      const res = await fetch("/api/brain", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ facts, title: title || undefined }),
      });
      const data = await res.json();
      clearInterval(stepInterval);
      if (data.error) {
        toast({ title: data.error, variant: "destructive" });
      } else {
        setResult(data);
        setCurrentStep(7);
        toast({
          title: "Análise cerebral concluída",
          description: `${data.steps?.filter((s: BrainStep) => s.status === "done").length || 0}/7 etapas completas`,
        });
      }
    } catch {
      clearInterval(stepInterval);
      toast({ title: "Erro na análise", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="container-juridia py-8">
      <div className="mb-6">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-lg">
            <Brain className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Cérebro</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              IA de entendimento profundo de casos jurídicos — raciocina em 7 etapas
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
              Fatos do caso
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="title" className="text-xs">Título (opcional)</Label>
              <Input
                id="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Ex: Inscrição indevida SERASA"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="facts" className="text-xs">Descrição dos fatos</Label>
              <Textarea
                id="facts"
                rows={10}
                value={facts}
                onChange={(e) => setFacts(e.target.value)}
                placeholder="Descreva os fatos do caso em linguagem natural..."
                className="scrollbar-juridia"
              />
              <p className="text-[10px] text-muted-foreground">{facts.length} caracteres</p>
            </div>
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={() => { setFacts(SAMPLE); setTitle("Inscrição indevida SERASA"); }}>
                Usar exemplo
              </Button>
              <Button variant="ghost" size="sm" onClick={() => { setFacts(""); setResult(null); }}>
                Limpar
              </Button>
            </div>
            <Button onClick={analyze} disabled={loading || facts.trim().length < 30} className="w-full" size="lg">
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Analisando...
                </>
              ) : (
                <>
                  <Sparkles className="mr-2 h-4 w-4" />
                  Analisar caso
                </>
              )}
            </Button>
            <div className="rounded-md border border-dashed border-primary/40 bg-primary/5 p-2.5 text-xs text-muted-foreground">
              <strong className="text-primary">Como funciona:</strong> O cérebro analisa seu caso em 7 etapas: extração → questões jurídicas → legislação → jurisprudência → viabilidade → lacunas → estratégia. Cada etapa usa IA, busca na base curada e pesquisa real.
            </div>
          </CardContent>
        </Card>

        {/* Results */}
        <div className="space-y-4">
          {/* Steps progress */}
          {(loading || result) && (
            <Card>
              <CardContent className="p-4">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="flex items-center gap-2 text-sm font-semibold">
                    <Brain className="h-4 w-4 text-primary" />
                    Etapas do cérebro
                  </h3>
                  {result && (
                    <Badge variant="outline" className="text-[10px]">
                      {result.totalTokens} tokens
                    </Badge>
                  )}
                </div>
                <div className="space-y-2">
                  {(result?.steps || STEPS_PLACEHOLDER).map((step, i) => {
                    const Icon = STEP_ICONS[step.id] || Brain;
                    const isActive = loading && i === currentStep;
                    return (
                      <div key={step.id} className="flex items-center gap-2 text-xs">
                        <div className={`flex h-6 w-6 items-center justify-center rounded-full ${
                          step.status === "done"
                            ? "bg-green-500/20 text-green-600"
                            : step.status === "running" || isActive
                            ? "bg-primary/20 text-primary"
                            : step.status === "error"
                            ? "bg-red-500/20 text-red-600"
                            : "bg-muted text-muted-foreground"
                        }`}>
                          {step.status === "done" ? (
                            <CheckCircle2 className="h-3.5 w-3.5" />
                          ) : step.status === "running" || isActive ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : step.status === "error" ? (
                            <XCircle className="h-3.5 w-3.5" />
                          ) : (
                            <Icon className="h-3.5 w-3.5" />
                          )}
                        </div>
                        <span className={step.status === "done" ? "text-foreground" : "text-muted-foreground"}>
                          {step.name}
                        </span>
                        {(step.status === "running" || isActive) && (
                          <span className="ml-auto animate-pulse text-[10px] text-primary">{STEP_DESCS[step.id]}</span>
                        )}
                      </div>
                    );
                  })}
                </div>
                {loading && (
                  <Progress value={(currentStep / 7) * 100} className="mt-3 h-1" />
                )}
              </CardContent>
            </Card>
          )}

          {!loading && !result && (
            <Card>
              <CardContent className="flex flex-col items-center justify-center gap-3 py-16 text-center">
                <Brain className="h-16 w-16 text-muted-foreground/30" />
                <div>
                  <h3 className="font-semibold">Cérebro jurídico aguardando</h3>
                  <p className="mt-1 text-sm text-muted-foreground max-w-sm">
                    Descreva os fatos do caso e o cérebro fará análise profunda em 7 etapas:
                    partes, questões jurídicas, legislação, jurisprudência, viabilidade,
                    lacunas e estratégia.
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Results sections */}
          {result && (
            <AnimatePresence>
              {/* Viability summary */}
              {result.viability && (
                <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
                  <Card className={`border-2 ${PROB_CONFIG[result.viability.probability as keyof typeof PROB_CONFIG]?.bg || ""}`}>
                    <CardContent className="p-5">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Target className={`h-5 w-5 ${PROB_CONFIG[result.viability.probability as keyof typeof PROB_CONFIG]?.color}`} />
                          <span className="font-semibold">Parecer de viabilidade</span>
                        </div>
                        <Badge variant="outline" className={`text-sm font-bold ${PROB_CONFIG[result.viability.probability as keyof typeof PROB_CONFIG]?.color}`}>
                          {PROB_CONFIG[result.viability.probability as keyof typeof PROB_CONFIG]?.label}
                        </Badge>
                      </div>
                      <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                        {result.viability.reasoning}
                      </p>
                      <div className="mt-4 grid gap-4 sm:grid-cols-2">
                        <div>
                          <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-green-600">
                            <TrendingUp className="h-3 w-3" /> Pontos fortes
                          </div>
                          <ul className="space-y-1 text-xs">
                            {result.viability.strengths.map((s, i) => (
                              <li key={i} className="flex gap-1.5">
                                <CheckCircle2 className="h-3 w-3 shrink-0 text-green-600 mt-0.5" />
                                <span className="text-muted-foreground">{s}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div>
                          <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-red-600">
                            <TrendingDown className="h-3 w-3" /> Fragilidades
                          </div>
                          <ul className="space-y-1 text-xs">
                            {result.viability.weaknesses.map((s, i) => (
                              <li key={i} className="flex gap-1.5">
                                <AlertTriangle className="h-3 w-3 shrink-0 text-red-600 mt-0.5" />
                                <span className="text-muted-foreground">{s}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              )}

              {/* Parties + timeline + requests */}
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="grid gap-4 sm:grid-cols-2">
                {result.parties && result.parties.length > 0 && (
                  <Card>
                    <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2 text-sm"><Users className="h-4 w-4 text-primary" /> Partes</CardTitle></CardHeader>
                    <CardContent className="space-y-1.5 text-xs">
                      {result.parties.map((p, i) => (
                        <div key={i} className="flex justify-between">
                          <Badge variant="outline" className="text-[10px]">{p.role}</Badge>
                          <span className="text-muted-foreground">{p.name || "—"} <span className="text-[10px]">({p.type})</span></span>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                )}
                {result.timeline && result.timeline.length > 0 && (
                  <Card>
                    <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2 text-sm"><Clock className="h-4 w-4 text-primary" /> Cronologia</CardTitle></CardHeader>
                    <CardContent className="space-y-1.5 text-xs">
                      {result.timeline.map((t, i) => (
                        <div key={i} className="flex gap-2">
                          <span className="shrink-0 font-mono text-[10px] text-primary">{t.date}</span>
                          <span className="text-muted-foreground">{t.event}</span>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                )}
              </motion.div>

              {/* Legal issues */}
              {result.legalIssues && result.legalIssues.length > 0 && (
                <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
                  <Card>
                    <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2 text-sm"><Scale className="h-4 w-4 text-primary" /> Questões jurídicas identificadas</CardTitle></CardHeader>
                    <CardContent className="space-y-2">
                      {result.legalIssues.map((q, i) => (
                        <div key={i} className="flex items-start gap-2 rounded-lg border border-border p-2">
                          <Badge variant="outline" className="shrink-0 text-[10px]">{q.area}</Badge>
                          <span className="flex-1 text-xs text-muted-foreground">{q.question}</span>
                          <Badge variant="secondary" className={`text-[10px] ${q.relevance === "alta" ? "text-red-600" : q.relevance === "média" ? "text-amber-600" : "text-muted-foreground"}`}>{q.relevance}</Badge>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                </motion.div>
              )}

              {/* Applicable law */}
              {result.applicableLaw && result.applicableLaw.length > 0 && (
                <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="flex items-center gap-2 text-sm">
                        <FileText className="h-4 w-4 text-primary" /> Legislação aplicável
                        <Badge variant="secondary" className="text-[10px] ml-1">{result.applicableLaw.length}</Badge>
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {result.applicableLaw.map((l, i) => (
                        <div key={i} className="rounded-lg border border-border p-2.5">
                          <div className="mb-1 flex items-center justify-between">
                            <code className="text-xs font-semibold">{l.diploma} {l.numero}</code>
                            {l.urlOficial && (
                              <a href={l.urlOficial} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                                <ExternalLink className="h-3 w-3" />
                              </a>
                            )}
                          </div>
                          <p className="text-[11px] italic text-muted-foreground">&ldquo;{l.textoTrecho.slice(0, 180)}...&rdquo;</p>
                          {!l.vigente && (
                            <Badge variant="outline" className="mt-1 text-[10px] text-red-600 border-red-500/50">não vigente</Badge>
                          )}
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                </motion.div>
              )}

              {/* Jurisprudence */}
              {result.jurisprudence && result.jurisprudence.length > 0 && (
                <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="flex items-center gap-2 text-sm">
                        <ListChecks className="h-4 w-4 text-primary" /> Jurisprudência encontrada
                        <Badge variant="secondary" className="text-[10px] ml-1">{result.jurisprudence.length}</Badge>
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {result.jurisprudence.map((j, i) => (
                        <a key={i} href={j.url} target="_blank" rel="noopener noreferrer" className="block rounded-lg border border-border p-2.5 transition-colors hover:border-primary/40 hover:bg-accent/30">
                          <div className="mb-1 flex items-center justify-between">
                            <span className="text-[10px] text-muted-foreground">{j.host_name}</span>
                            <ExternalLink className="h-3 w-3 text-muted-foreground" />
                          </div>
                          <p className="text-xs font-medium leading-tight">{j.name}</p>
                          <p className="mt-1 text-[11px] text-muted-foreground line-clamp-2">{j.snippet}</p>
                        </a>
                      ))}
                    </CardContent>
                  </Card>
                </motion.div>
              )}

              {/* Gaps + questions */}
              {result.gaps && result.gaps.length > 0 && (
                <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
                  <Card className="border-amber-500/30">
                    <CardHeader className="pb-2">
                      <CardTitle className="flex items-center gap-2 text-sm">
                        <HelpCircle className="h-4 w-4 text-amber-500" /> Lacunas e perguntas
                        <Badge variant="secondary" className="text-[10px] ml-1">{result.gaps.length}</Badge>
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {result.gaps.map((g, i) => (
                        <div key={i} className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-2.5">
                          <div className="mb-1 text-xs font-medium">{g.what}</div>
                          <p className="text-[11px] text-muted-foreground">{g.why}</p>
                          <div className="mt-2 rounded border border-dashed border-amber-500/40 p-2">
                            <span className="text-[10px] uppercase text-amber-600">Pergunta para o cliente:</span>
                            <p className="text-xs">{g.question}</p>
                          </div>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                </motion.div>
              )}

              {/* Strategy */}
              {result.strategy && (
                <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
                  <Card className="border-primary/30">
                    <CardHeader className="pb-2">
                      <CardTitle className="flex items-center gap-2 text-sm">
                        <Zap className="h-4 w-4 text-primary" /> Estratégia recomendada
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <div>
                        <div className="mb-1 text-[10px] uppercase font-semibold text-muted-foreground">Caminho processual</div>
                        <p className="text-sm">{result.strategy.proceduralPath}</p>
                      </div>
                      {result.strategy.immediateActions && result.strategy.immediateActions.length > 0 && (
                        <div>
                          <div className="mb-1 text-[10px] uppercase font-semibold text-muted-foreground">Ações imediatas</div>
                          <ul className="space-y-1 text-xs">
                            {result.strategy.immediateActions.map((a, i) => (
                              <li key={i} className="flex gap-2"><ArrowRight className="h-3 w-3 text-primary mt-0.5 shrink-0" /><span className="text-muted-foreground">{a}</span></li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {result.strategy.documentsToCollect && result.strategy.documentsToCollect.length > 0 && (
                        <div>
                          <div className="mb-1 text-[10px] uppercase font-semibold text-muted-foreground">Documentos a coletar</div>
                          <ul className="space-y-1 text-xs">
                            {result.strategy.documentsToCollect.map((d, i) => (
                              <li key={i} className="flex gap-2"><FileText className="h-3 w-3 text-primary mt-0.5 shrink-0" /><span className="text-muted-foreground">{d}</span></li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {result.strategy.risks && result.strategy.risks.length > 0 && (
                        <div>
                          <div className="mb-1 text-[10px] uppercase font-semibold text-red-600">Riscos</div>
                          <ul className="space-y-1 text-xs">
                            {result.strategy.risks.map((r, i) => (
                              <li key={i} className="flex gap-2"><AlertTriangle className="h-3 w-3 text-red-600 mt-0.5 shrink-0" /><span className="text-muted-foreground">{r}</span></li>
                            ))}
                          </ul>
                        </div>
                      )}
                      <div className="rounded-lg border border-primary/30 bg-primary/5 p-3">
                        <div className="mb-1 text-[10px] uppercase font-semibold text-primary">Recomendação final</div>
                        <p className="text-sm">{result.strategy.recommendation}</p>
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              )}

              {/* Generate minuta from analysis */}
              {result.viability && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                  <Button
                    size="lg"
                    className="w-full"
                    onClick={() => {
                      setAppTab("generator");
                      toast({ title: "Use os fatos do caso no gerador", description: "A análise cerebral serve como contexto" });
                    }}
                  >
                    <Wand2 className="mr-2 h-4 w-4" />
                    Gerar minuta a partir desta análise
                  </Button>
                </motion.div>
              )}
            </AnimatePresence>
          )}
        </div>
      </div>
    </div>
  );
}

const STEPS_PLACEHOLDER: BrainStep[] = [
  { id: "extract", name: "Extração estruturada", status: "pending" },
  { id: "issues", name: "Questões jurídicas", status: "pending" },
  { id: "law", name: "Legislação aplicável", status: "pending" },
  { id: "jurisprudence", name: "Jurisprudência", status: "pending" },
  { id: "viability", name: "Análise de viabilidade", status: "pending" },
  { id: "gaps", name: "Lacunas e perguntas", status: "pending" },
  { id: "strategy", name: "Estratégia recomendada", status: "pending" },
];
