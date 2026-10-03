"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  FileSearch,
  Users,
  Clock,
  ListChecks,
  FileCheck,
  Gavel,
  DollarSign,
  AlertTriangle,
  ArrowRight,
  Loader2,
  Sparkles,
  History,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { useAppStore } from "@/lib/store";
import { toast } from "@/hooks/use-toast";

interface CaseAnalysisResult {
  id?: string;
  title: string;
  parties: { role: string; name?: string; type: string }[];
  timeline: { date: string; event: string }[];
  requests: string[];
  proofs: string[];
  decisions: string[];
  values: { label: string; amount: string }[];
  risks: { level: "baixo" | "médio" | "alto"; description: string }[];
  nextSteps: string[];
}

export function CaseAnalysis() {
  const [facts, setFacts] = useState("");
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CaseAnalysisResult | null>(null);
  const [history, setHistory] = useState<CaseAnalysisResult[]>([]);

  useEffect(() => {
    fetch("/api/case-analysis")
      .then((r) => r.json())
      .then((d) => setHistory(d.analyses || []))
      .catch(() => null);
  }, []);

  async function analyze() {
    if (facts.trim().length < 30) {
      toast({ title: "Descreva os fatos (mín. 30 caracteres)", variant: "destructive" });
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch("/api/case-analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ facts, title: title || undefined }),
      });
      const data = await res.json();
      if (data.error) {
        toast({ title: data.error, variant: "destructive" });
      } else {
        setResult(data);
        toast({ title: "Análise concluída", description: "Resumo estruturado gerado pela IA" });
      }
    } catch {
      toast({ title: "Erro ao analisar caso", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }

  const SAMPLE = `EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA 3ª VARA CÍVEL DA COMARCA DE SÃO PAULO

João Carlos da Silva, brasileiro, casado, advogado, CPF 123.456.789-09, portador do RG 12.345.678-9, residente na Rua das Flores, 123, São Paulo - SP, vem propor AÇÃO INDENIZATÓRIA em face de Banco XYZ S.A., inscrita no CNPJ 00.000.000/0001-00, pelos fatos a seguir. O autor foi inscrito indevidamente no SERASA em 15/01/2026, após quitação do débito em 10/12/2025 no valor de R$ 5.000,00. O autor pleiteia indenização por danos morais no valor de R$ 50.000,00.`;

  const cards = result
    ? [
        { icon: Users, title: "Partes", items: result.parties.map((p) => `${p.role}: ${p.name || "não identificado"} (${p.type})`), color: "text-blue-600" },
        { icon: Clock, title: "Cronologia", items: result.timeline.map((t) => `${t.date} — ${t.event}`) },
        { icon: ListChecks, title: "Pedidos", items: result.requests },
        { icon: FileCheck, title: "Provas", items: result.proofs },
        { icon: Gavel, title: "Decisões", items: result.decisions.length > 0 ? result.decisions : ["Nenhuma decisão registrada"] },
        { icon: DollarSign, title: "Valores", items: result.values.map((v) => `${v.label}: ${v.amount}`) },
      ]
    : [];

  return (
    <div className="container-juridia py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Resumo avançado do caso</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          A IA analisa os fatos e extrai informações estruturadas: partes, cronologia,
          pedidos, provas, decisões, valores, riscos e próximos passos.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_2fr]">
        {/* Input */}
        <Card className="h-fit">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FileSearch className="h-4 w-4 text-primary" />
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
                placeholder="Ex: Ação indenizatória — inscrição indevida"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="facts" className="text-xs">Descrição dos fatos</Label>
              <Textarea
                id="facts"
                rows={10}
                value={facts}
                onChange={(e) => setFacts(e.target.value)}
                placeholder="Cole aqui os fatos do caso..."
                className="scrollbar-juridia"
              />
            </div>
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={() => setFacts(SAMPLE)}>
                Usar exemplo
              </Button>
              <Button variant="ghost" size="sm" onClick={() => { setFacts(""); setResult(null); }}>
                Limpar
              </Button>
            </div>
            <Button onClick={analyze} disabled={loading || facts.trim().length < 30} className="w-full">
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Analisando com IA...
                </>
              ) : (
                <>
                  <Sparkles className="mr-2 h-4 w-4" />
                  Analisar caso
                </>
              )}
            </Button>
            <p className="text-xs text-muted-foreground">
              💡 A análise extrai cards estruturados que podem ser usados como contexto
              na geração de minutas.
            </p>
          </CardContent>
        </Card>

        {/* Results */}
        <div className="space-y-4">
          {loading && (
            <div className="grid gap-4 sm:grid-cols-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="rounded-xl border border-border bg-card p-4">
                  <div className="mb-3 h-5 w-24 animate-pulse rounded bg-muted" />
                  <div className="space-y-1.5">
                    <div className="h-3 w-full animate-pulse rounded bg-muted" />
                    <div className="h-3 w-4/5 animate-pulse rounded bg-muted" />
                    <div className="h-3 w-2/3 animate-pulse rounded bg-muted" />
                  </div>
                </div>
              ))}
            </div>
          )}

          {!loading && !result && (
            <Card>
              <CardContent className="flex flex-col items-center justify-center gap-3 py-16 text-center">
                <FileSearch className="h-12 w-12 text-muted-foreground/40" />
                <div>
                  <h3 className="font-semibold">Nenhuma análise ainda</h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Descreva os fatos do caso e clique em &ldquo;Analisar caso&rdquo;.
                  </p>
                </div>
                {history.length > 0 && (
                  <div className="mt-4 w-full max-w-md">
                    <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
                      <History className="h-3.5 w-3.5" />
                      Análises anteriores
                    </div>
                    <div className="space-y-1.5">
                      {history.slice(0, 5).map((h) => (
                        <button
                          key={h.id}
                          onClick={() => setResult(h)}
                          className="flex w-full items-center justify-between rounded-lg border border-border p-2 text-left text-sm transition-colors hover:bg-accent/40"
                        >
                          <span className="truncate">{h.title}</span>
                          <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {!loading && result && (
            <>
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                className="rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm"
              >
                <strong className="text-primary">Análise gerada:</strong> {result.title}
              </motion.div>

              <div className="grid gap-4 sm:grid-cols-2">
                {cards.map((card, i) => (
                  <motion.div
                    key={card.title}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3, delay: i * 0.08 }}
                  >
                    <Card className="h-full">
                      <CardHeader className="pb-2">
                        <CardTitle className="flex items-center gap-2 text-sm">
                          <card.icon className="h-4 w-4 text-primary" />
                          {card.title}
                          <Badge variant="outline" className="ml-auto text-[10px]">
                            {card.items.length}
                          </Badge>
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        {card.items.length === 0 ? (
                          <p className="text-xs text-muted-foreground">Nenhuma informação extraída</p>
                        ) : (
                          <ul className="space-y-1.5 text-xs">
                            {card.items.map((item, idx) => (
                              <li key={idx} className="flex gap-2">
                                <span className="text-primary">•</span>
                                <span className="text-muted-foreground">{item}</span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </CardContent>
                    </Card>
                  </motion.div>
                ))}
              </div>

              {/* Riscos */}
              {result.risks.length > 0 && (
                <Card className="border-amber-500/30">
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center gap-2 text-sm">
                      <AlertTriangle className="h-4 w-4 text-amber-500" />
                      Riscos identificados
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {result.risks.map((r, i) => (
                        <div key={i} className="flex items-start gap-2 rounded-lg border border-border p-2">
                          <Badge
                            variant="outline"
                            className={`shrink-0 text-[10px] ${
                              r.level === "alto"
                                ? "border-red-500/50 text-red-600"
                                : r.level === "médio"
                                ? "border-amber-500/50 text-amber-600"
                                : "border-green-500/50 text-green-600"
                            }`}
                          >
                            {r.level}
                          </Badge>
                          <span className="text-xs text-muted-foreground">{r.description}</span>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Próximos passos */}
              {result.nextSteps.length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center gap-2 text-sm">
                      <ArrowRight className="h-4 w-4 text-primary" />
                      Próximos passos sugeridos
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ol className="space-y-2">
                      {result.nextSteps.map((step, i) => (
                        <li key={i} className="flex items-start gap-2 text-xs">
                          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-bold text-primary">
                            {i + 1}
                          </span>
                          <span className="pt-0.5 text-muted-foreground">{step}</span>
                        </li>
                      ))}
                    </ol>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
