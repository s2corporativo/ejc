"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ClipboardCheck,
  Play,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  TrendingUp,
  Clock,
  DollarSign,
  FileText,
  Brain,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { toast } from "@/hooks/use-toast";

interface SampleCase {
  id: string;
  title: string;
  pedido: string;
  tipoPeca: string;
  autos: string;
}

const SAMPLE_CASES: SampleCase[] = [
  {
    id: "case_1",
    title: "Negativação indevida SERASA",
    pedido: "Cliente ajuíza ação de indenização por negativação indevida no SERASA após quitação de débito.",
    tipoPeca: "peticao-inicial-civel",
    autos: "Débito quitado em 15/03/2024. Negativação manteve até 10/06/2024. Danos morais in re ipsa.",
  },
  {
    id: "case_2",
    title: "Dano moral por atraso em voo",
    pedido: "Passageiro requer indenização por dano moral decorrente de atraso de voo superior a 4 horas.",
    tipoPeca: "peticao-inicial-civel",
    autos: "Voo SP→RJ atrasou 6h. Cliente perdeu reunião e compromissos. Comprovantes de tickets e voucher.",
  },
  {
    id: "case_3",
    title: "Vício de produto — geladeira",
    pedido: "Cliente pede troca de geladeira com vício oculto no compressor e devolução em dobro.",
    tipoPeca: "peticao-inicial-civel",
    autos: "Geladeira comprada em 01/2024. Compressor falhou em 05/2024. Fabricante não reparou em 30 dias.",
  },
  {
    id: "case_4",
    title: "Cobrança indevida — plano de saúde",
    pedido: "Autor requer devolução de valores cobrados indevidamente em plano de saúde após fim de carência.",
    tipoPeca: "peticao-inicial-civel",
    autos: "Plano cobrou procedimento coberto. Cliente pagou sob protesto em 03/2024. Recibo e contrato anexos.",
  },
  {
    id: "case_5",
    title: "Trabalhista — horas extras",
    pedido: "Reclamante pede pagamento de horas extras não pagas e reflexos legais.",
    tipoPeca: "peticao-inicial-civel",
    autos: "Trabalhador cumpria 10h/dia em sistema de sobreaviso. Cartão de ponto anexo. Empregadora não pagou.",
  },
  {
    id: "case_6",
    title: "Contestação — dano moral banco",
    pedido: "Réu contesta pedido de dano moral por falha em transferência bancária.",
    tipoPeca: "contestacao-civel",
    autos: "Banco reconstituiu transferência em 24h. Cliente não sofreu prejuízo. Dano moral não configurado.",
  },
  {
    id: "case_7",
    title: "Tutela de urgência — despejo",
    pedido: "Locador pede liminar de despejo por falta de pagamento.",
    tipoPeca: "tutela-urgencia",
    autos: "Inquilino em mora superior a 3 meses. Notificação extrajudicial anexa. Contrato com garantia.",
  },
  {
    id: "case_8",
    title: "Apelação cível — improcedência",
    pedido: "Apelante requer reforma de sentença de improcedência em ação de cobrança.",
    tipoPeca: "apelacao-civel",
    autos: "Sentença negou pedido por ausência de prova documental. Apelante tem faturas e recibos não apreciados.",
  },
  {
    id: "case_9",
    title: "Parecer — Tributário ICMS",
    pedido: "Parecer sobre constitucionalidade de alíquota de ICMS estadual.",
    tipoPeca: "parecer",
    autos: "Estado X majorou alíquota sem Lei Complementar. Parecer para subsidiar ação direta.",
  },
  {
    id: "case_10",
    title: "LGPD — vazamento de dados",
    pedido: "Autor requer indenização por vazamento de dados pessoais em violação à LGPD.",
    tipoPeca: "peticao-inicial-civel",
    autos: "Vazamento expôs 10 mil registros. Cliente teve CPF usado em fraude. ANPD notificada.",
  },
];

type RunStatus = "pending" | "running" | "done" | "error";

interface RunResult {
  caseId: string;
  status: RunStatus;
  tokensUsed?: number;
  sectionsCount?: number;
  adherence?: string;
  vulnerabilities?: number;
  distinguishing?: string;
  auditConfidence?: number;
  error?: string;
  durationMs?: number;
}

export function Homologacao() {
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<Record<string, RunResult>>({});

  async function runAll() {
    setRunning(true);
    setResults({});
    const initial: Record<string, RunResult> = {};
    for (const c of SAMPLE_CASES) initial[c.id] = { caseId: c.id, status: "pending" };
    setResults(initial);

    // Executa casos sequencialmente (para visualizar progressão)
    const newResults = { ...initial };
    for (const c of SAMPLE_CASES) {
      setResults((s) => ({ ...s, [c.id]: { ...s[c.id], status: "running" } }));
      const start = Date.now();
      try {
        const res = await fetch("/api/lexvalida/pipeline", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pedido: c.pedido, tipoPeca: c.tipoPeca, autos: c.autos, caseId: c.id }),
        });
        const data = await res.json();
        const durationMs = Date.now() - start;
        if (!res.ok) {
          newResults[c.id] = { caseId: c.id, status: "error", error: data.error || `HTTP ${res.status}`, durationMs };
        } else {
          newResults[c.id] = {
            caseId: c.id,
            status: "done",
            tokensUsed: data.totalTokens || 0,
            sectionsCount: data.secoesRedigidas?.length || 0,
            adherence: data.verificacaoAderencia?.classificacao || "—",
            vulnerabilities: data.analiseAdversarial?.vulnerabilidades?.length || 0,
            distinguishing: data.distinguishing?.conclusao || "—",
            auditConfidence: data.auditoria?.confianca != null ? Math.round(data.auditoria.confianca * 100) : null,
            durationMs,
          };
        }
        setResults({ ...newResults });
      } catch (e) {
        const durationMs = Date.now() - start;
        newResults[c.id] = {
          caseId: c.id,
          status: "error",
          error: e instanceof Error ? e.message : "Falha",
          durationMs,
        };
        setResults({ ...newResults });
      }
    }

    setRunning(false);
    const done = Object.values(newResults).filter((r) => r.status === "done").length;
    toast({ title: "Homologação concluída", description: `${done}/${SAMPLE_CASES.length} casos processados com sucesso` });
  }

  const metrics = (() => {
    const arr = Object.values(results);
    const done = arr.filter((r) => r.status === "done");
    const errors = arr.filter((r) => r.status === "error");
    const totalTokens = done.reduce((s, r) => s + (r.tokensUsed || 0), 0);
    const totalSections = done.reduce((s, r) => s + (r.sectionsCount || 0), 0);
    const totalVulns = done.reduce((s, r) => s + (r.vulnerabilities || 0), 0);
    const avgDuration = done.length ? Math.round(done.reduce((s, r) => s + (r.durationMs || 0), 0) / done.length / 1000) : 0;
    const avgAudit = done.filter((r) => r.auditConfidence != null);
    const avgConfidence = avgAudit.length ? Math.round(avgAudit.reduce((s, r) => s + (r.auditConfidence || 0), 0) / avgAudit.length) : null;
    return {
      doneCount: done.length,
      errorCount: errors.length,
      pendingCount: arr.filter((r) => r.status === "pending" || r.status === "running").length,
      totalTokens,
      totalSections,
      totalVulns,
      avgDuration,
      avgConfidence,
    };
  })();

  return (
    <div className="container-juridia py-8">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="mb-6 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <ClipboardCheck className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">Homologação end-to-end</h1>
              <p className="text-sm text-muted-foreground">10 casos executados no pipeline completo — métricas consolidadas para auditoria.</p>
            </div>
          </div>
          <Button onClick={runAll} disabled={running} size="lg">
            {running ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
            {running ? "Executando..." : "Executar 10 casos"}
          </Button>
        </div>
      </motion.div>

      {/* Métricas */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard icon={CheckCircle2} label="Casos completos" value={`${metrics.doneCount}/${SAMPLE_CASES.length}`} color="text-emerald-600" bg="bg-emerald-500/10" />
        <MetricCard icon={AlertTriangle} label="Erros" value={String(metrics.errorCount)} color="text-rose-600" bg="bg-rose-500/10" />
        <MetricCard icon={FileText} label="Tokens totais" value={metrics.totalTokens.toLocaleString("pt-BR")} color="text-cyan-600" bg="bg-cyan-500/10" />
        <MetricCard icon={TrendingUp} label="Seções redigidas" value={String(metrics.totalSections)} color="text-purple-600" bg="bg-purple-500/10" />
        <MetricCard icon={Brain} label="Vulnerabilidades adversariais" value={String(metrics.totalVulns)} color="text-amber-600" bg="bg-amber-500/10" />
        <MetricCard icon={Clock} label="Duração média" value={`${metrics.avgDuration}s`} color="text-orange-600" bg="bg-orange-500/10" />
        <MetricCard icon={ClipboardCheck} label="Confiança média (auditoria)" value={metrics.avgConfidence != null ? `${metrics.avgConfidence}%` : "—"} color="text-emerald-700" bg="bg-emerald-500/5" />
        <MetricCard icon={DollarSign} label="Custo estimado" value={`R$ ${((metrics.totalTokens / 1000) * 0.012).toFixed(2)}`} color="text-primary" bg="bg-primary/10" />
      </div>

      {/* Progresso geral */}
      {running && (
        <Card className="mb-6 border-primary/30">
          <CardContent className="p-4">
            <div className="mb-2 flex items-center justify-between text-xs">
              <span className="font-semibold">Progresso da homologação</span>
              <span className="font-mono text-muted-foreground">
                {metrics.doneCount + metrics.errorCount}/{SAMPLE_CASES.length} · {Math.round(((metrics.doneCount + metrics.errorCount) / SAMPLE_CASES.length) * 100)}%
              </span>
            </div>
            <Progress value={((metrics.doneCount + metrics.errorCount) / SAMPLE_CASES.length) * 100} className="h-2" />
          </CardContent>
        </Card>
      )}

      <Tabs defaultValue="cases">
        <TabsList>
          <TabsTrigger value="cases">Casos individuais</TabsTrigger>
          <TabsTrigger value="summary">Resumo consolidado</TabsTrigger>
        </TabsList>

        <TabsContent value="cases" className="mt-4">
          <div className="grid gap-3 lg:grid-cols-2">
            {SAMPLE_CASES.map((c, i) => {
              const r = results[c.id] || { caseId: c.id, status: "pending" as const };
              return (
                <motion.div
                  key={c.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.03 }}
                >
                  <Card className={r.status === "done" ? "border-emerald-500/30" : r.status === "error" ? "border-rose-500/30" : r.status === "running" ? "border-primary/30" : ""}>
                    <CardContent className="p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <Badge variant="outline" className="text-[10px]">#{i + 1}</Badge>
                            <Badge variant="secondary" className="text-[10px]">{c.tipoPeca}</Badge>
                            {r.status === "done" && <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />}
                            {r.status === "running" && <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />}
                            {r.status === "error" && <XCircle className="h-3.5 w-3.5 text-rose-600" />}
                            {r.status === "pending" && <div className="h-1.5 w-1.5 rounded-full bg-muted-foreground/30" />}
                          </div>
                          <h3 className="mt-2 text-sm font-semibold">{c.title}</h3>
                          <p className="mt-1 text-[11px] text-muted-foreground line-clamp-2">{c.pedido}</p>
                          {r.status === "done" && (
                            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
                              <span><FileText className="mr-1 inline h-2.5 w-2.5" />{r.tokensUsed} tok</span>
                              <span><Brain className="mr-1 inline h-2.5 w-2.5" />{r.sectionsCount} seções</span>
                              <span><TrendingUp className="mr-1 inline h-2.5 w-2.5" />aderência: {r.adherence}</span>
                              <span><AlertTriangle className="mr-1 inline h-2.5 w-2.5" />{r.vulnerabilities} vuln</span>
                              {r.auditConfidence != null && <span className="text-emerald-700 dark:text-emerald-400"><ClipboardCheck className="mr-1 inline h-2.5 w-2.5" />{r.auditConfidence}%</span>}
                              {r.durationMs != null && <span className="font-mono"><Clock className="mr-1 inline h-2.5 w-2.5" />{(r.durationMs / 1000).toFixed(1)}s</span>}
                            </div>
                          )}
                          {r.status === "error" && (
                            <p className="mt-2 text-[10px] text-rose-700 dark:text-rose-400">{r.error}</p>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              );
            })}
          </div>
        </TabsContent>

        <TabsContent value="summary" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <ClipboardCheck className="h-4 w-4 text-primary" /> Resumo consolidado
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <SummaryItem label="Casos executados" value={`${metrics.doneCount + metrics.errorCount}/${SAMPLE_CASES.length}`} />
                <SummaryItem label="Sucesso" value={`${metrics.doneCount} (${Math.round((metrics.doneCount / Math.max(1, metrics.doneCount + metrics.errorCount)) * 100)}%)`} />
                <SummaryItem label="Falhas" value={String(metrics.errorCount)} />
                <SummaryItem label="Tokens consumidos" value={metrics.totalTokens.toLocaleString("pt-BR")} />
                <SummaryItem label="Seções redigidas" value={String(metrics.totalSections)} />
                <SummaryItem label="Vulnerabilidades adversariais" value={String(metrics.totalVulns)} />
                <SummaryItem label="Duração média" value={`${metrics.avgDuration}s`} />
                <SummaryItem label="Confiança média (auditoria)" value={metrics.avgConfidence != null ? `${metrics.avgConfidence}%` : "—"} />
                <SummaryItem label="Custo estimado" value={`R$ ${((metrics.totalTokens / 1000) * 0.012).toFixed(2)}`} />
              </div>
              <div className="mt-6 rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground">
                <AlertTriangle className="mr-1 inline h-3.5 w-3.5 text-amber-600" />
                <strong>Critérios de homologação:</strong> taxa de sucesso ≥ 80% · confiança média (auditoria) ≥ 85% · 0 casos com injeção de prompt · 0 casos com fabricação de dados.
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function MetricCard({ icon: Icon, label, value, color, bg }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string; color: string; bg: string }) {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
      <Card>
        <CardContent className="p-4">
          <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${bg} ${color}`}>
            <Icon className="h-4 w-4" />
          </div>
          <div className="mt-3 text-2xl font-bold">{value}</div>
          <div className="mt-0.5 text-xs text-muted-foreground">{label}</div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border p-3">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1 text-lg font-bold">{value}</div>
    </div>
  );
}
