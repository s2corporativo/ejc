"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  BarChart3,
  Loader2,
  Calendar,
  Clock,
  Users,
  Scale,
  FileText,
  Copy,
  Download,
  Sparkles,
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
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { toast } from "@/hooks/use-toast";

interface CaseItem { id: string; title: string; number: string | null; area: string; notes: string | null; }

type Format = "timeline" | "quadro-resumo" | "partes" | "valores" | "riscos";

interface TimelineItem { date: string; event: string; }
interface PartyItem { role: string; name?: string; type: string; }
interface ValueItem { label: string; amount: string; }
interface RiskItem { level: string; description: string; }
interface AnalysisResult {
  parties: PartyItem[];
  timeline: TimelineItem[];
  requests: string[];
  proofs: string[];
  decisions: string[];
  values: ValueItem[];
  risks: RiskItem[];
  nextSteps: string[];
}

const FORMATS: { id: Format; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: "timeline", label: "Timeline", icon: Clock },
  { id: "quadro-resumo", label: "Quadro-resumo", icon: FileText },
  { id: "partes", label: "Partes", icon: Users },
  { id: "valores", label: "Valores", icon: Scale },
  { id: "riscos", label: "Riscos", icon: BarChart3 },
];

export function VisualLaw() {
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCaseId, setSelectedCaseId] = useState<string>("");
  const [format, setFormat] = useState<Format>("timeline");
  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);

  useEffect(() => {
    fetch("/api/cases")
      .then((r) => r.json())
      .then((d) => {
        const list: CaseItem[] = (d.cases || []).map((c: CaseItem) => ({ id: c.id, title: c.title, number: c.number, area: c.area, notes: c.notes }));
        setCases(list);
        if (list.length > 0 && !selectedCaseId) setSelectedCaseId(list[0].id);
      })
      .catch(() => null)
      .finally(() => setLoading(false));
  }, [selectedCaseId]);

  const selectedCase = useMemo(() => cases.find((c) => c.id === selectedCaseId), [cases, selectedCaseId]);

  async function gerar() {
    if (!selectedCase) {
      toast({ title: "Selecione um caso", variant: "destructive" });
      return;
    }
    setAnalyzing(true);
    setAnalysis(null);
    try {
      const facts = selectedCase.notes || `${selectedCase.title} — ${selectedCase.area} — ${selectedCase.number || "sem número"}`;
      const res = await fetch("/api/case-analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ facts, title: selectedCase.title }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Erro");
      setAnalysis(data as AnalysisResult);
      toast({ title: "Visualização gerada", description: `${format} — ${selectedCase.title}` });
    } catch (e) {
      toast({ title: "Erro", description: e instanceof Error ? e.message : "Falha", variant: "destructive" });
    } finally {
      setAnalyzing(false);
    }
  }

  function copyText() {
    if (!analysis) return;
    let text = `# Visual Law — ${selectedCase?.title}\nFormato: ${format}\n\n`;
    if (format === "timeline") {
      text += "## Timeline\n";
      for (const t of analysis.timeline) text += `- ${t.date}: ${t.event}\n`;
    } else if (format === "quadro-resumo") {
      text += "## Quadro-resumo\n";
      text += `- Partes: ${analysis.parties.length}\n`;
      text += `- Pedidos: ${analysis.requests.length}\n`;
      text += `- Provas: ${analysis.proofs.length}\n`;
      text += `- Valores: ${analysis.values.length}\n`;
      text += `- Riscos: ${analysis.risks.length}\n`;
      text += "- Próximos passos:\n";
      for (const s of analysis.nextSteps) text += `  - ${s}\n`;
    } else if (format === "partes") {
      text += "## Partes\n";
      for (const p of analysis.parties) text += `- ${p.role}: ${p.name || "—"} (${p.type})\n`;
    } else if (format === "valores") {
      text += "## Valores\n";
      for (const v of analysis.values) text += `- ${v.label}: ${v.amount}\n`;
    } else if (format === "riscos") {
      text += "## Riscos\n";
      for (const r of analysis.risks) text += `- [${r.level}] ${r.description}\n`;
    }
    navigator.clipboard.writeText(text);
    toast({ title: "Visual copiada", description: "Texto resumido na área de transferência" });
  }

  function downloadMd() {
    if (!analysis) return;
    let md = `# Visual Law — ${selectedCase?.title}\n\n`;
    md += `**Formato:** ${format}\n`;
    if (selectedCase?.number) md += `**Processo:** ${selectedCase.number}\n`;
    if (selectedCase?.area) md += `**Área:** ${selectedCase.area}\n\n`;
    if (format === "timeline" && analysis.timeline.length > 0) {
      md += "## Timeline\n\n";
      for (const t of analysis.timeline) md += `- **${t.date}**: ${t.event}\n`;
      md += "\n";
    }
    if (analysis.parties.length > 0) {
      md += "## Partes\n\n";
      for (const p of analysis.parties) md += `- **${p.role}**: ${p.name || "—"} (${p.type})\n`;
      md += "\n";
    }
    if (analysis.requests.length > 0) {
      md += "## Pedidos\n\n";
      for (const r of analysis.requests) md += `- ${r}\n`;
      md += "\n";
    }
    if (analysis.values.length > 0) {
      md += "## Valores\n\n";
      for (const v of analysis.values) md += `- **${v.label}**: ${v.amount}\n`;
      md += "\n";
    }
    if (analysis.risks.length > 0) {
      md += "## Riscos\n\n";
      for (const r of analysis.risks) md += `- [${r.level.toUpperCase()}] ${r.description}\n`;
      md += "\n";
    }
    if (analysis.nextSteps.length > 0) {
      md += "## Próximos passos\n\n";
      for (const s of analysis.nextSteps) md += `- ${s}\n`;
      md += "\n";
    }
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `visual-law-${selectedCase?.id || "case"}.md`;
    a.click();
    URL.revokeObjectURL(url);
    toast({ title: "Markdown baixado" });
  }

  if (loading) return <div className="flex h-48 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>;

  return (
    <div className="container-juridia py-8">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <BarChart3 className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Visual Law</h1>
            <p className="text-sm text-muted-foreground">Transforma dados do caso em infográficos: timeline, quadro-resumo, partes, valores, riscos.</p>
          </div>
        </div>
      </motion.div>

      {/* Controles */}
      <Card className="mb-6">
        <CardContent className="p-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Caso</label>
              <Select value={selectedCaseId} onValueChange={setSelectedCaseId}>
                <SelectTrigger><SelectValue placeholder="Selecione..." /></SelectTrigger>
                <SelectContent>
                  {cases.length === 0 ? <SelectItem value="_" disabled>Nenhum caso</SelectItem> : cases.map((c) => (
                    <SelectItem key={c.id} value={c.id}>{c.title}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Formato</label>
              <Select value={format} onValueChange={(v) => setFormat(v as Format)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {FORMATS.map((f) => <SelectItem key={f.id} value={f.id}>{f.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end gap-2">
              <Button onClick={gerar} disabled={analyzing || !selectedCase} className="flex-1">
                {analyzing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
                {analyzing ? "Gerando..." : "Gerar"}
              </Button>
              <Button size="icon" variant="outline" onClick={copyText} disabled={!analysis}><Copy className="h-4 w-4" /></Button>
              <Button size="icon" variant="outline" onClick={downloadMd} disabled={!analysis}><Download className="h-4 w-4" /></Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Preview em 2 tabs */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileText className="h-4 w-4 text-primary" /> Preview
            {selectedCase && <Badge variant="secondary" className="text-[10px]">{selectedCase.title}</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="timeline">
            <TabsList>
              <TabsTrigger value="timeline"><Clock className="mr-1 h-3 w-3" /> Timeline</TabsTrigger>
              <TabsTrigger value="quadro-resumo"><FileText className="mr-1 h-3 w-3" /> Quadro-resumo</TabsTrigger>
            </TabsList>

            <TabsContent value="timeline" className="mt-4">
              <AnimatePresence mode="wait">
                {analysis && analysis.timeline.length > 0 ? (
                  <motion.div key="timeline" initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -8 }}>
                    <TimelineView items={analysis.timeline} />
                  </motion.div>
                ) : (
                  <EmptyView analyzing={analyzing} />
                )}
              </AnimatePresence>
            </TabsContent>

            <TabsContent value="quadro-resumo" className="mt-4">
              <AnimatePresence mode="wait">
                {analysis ? (
                  <motion.div key="quadro" initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 8 }} className="space-y-4">
                    <QuadroResumoView analysis={analysis} />
                  </motion.div>
                ) : (
                  <EmptyView analyzing={analyzing} />
                )}
              </AnimatePresence>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}

function EmptyView({ analyzing }: { analyzing: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      {analyzing ? <Loader2 className="h-8 w-8 animate-spin text-primary" /> : <Sparkles className="h-10 w-10 text-muted-foreground/40" />}
      <p className="text-sm text-muted-foreground">
        {analyzing ? "Gerando visualização..." : "Selecione caso, formato e clique em Gerar."}
      </p>
    </div>
  );
}

function TimelineView({ items }: { items: TimelineItem[] }) {
  return (
    <div className="relative pl-6">
      <div className="absolute left-2 top-2 bottom-2 w-px bg-border" />
      <div className="space-y-3">
        {items.map((t, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.08 }}
            className="relative"
          >
            <div className="absolute -left-5 top-1.5 h-2 w-2 rounded-full bg-primary ring-4 ring-background" />
            <div className="rounded-lg border border-border p-3 hover:bg-accent/40">
              <div className="flex items-center gap-2">
                <Calendar className="h-3.5 w-3.5 text-primary" />
                <span className="font-mono text-xs font-semibold text-primary">{t.date}</span>
              </div>
              <div className="mt-1 text-sm">{t.event}</div>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

function QuadroResumoView({ analysis }: { analysis: AnalysisResult }) {
  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatBox label="Partes" value={String(analysis.parties.length)} icon={Users} color="text-cyan-600" bg="bg-cyan-500/10" />
        <StatBox label="Pedidos" value={String(analysis.requests.length)} icon={Scale} color="text-emerald-600" bg="bg-emerald-500/10" />
        <StatBox label="Provas" value={String(analysis.proofs.length)} icon={FileText} color="text-amber-600" bg="bg-amber-500/10" />
        <StatBox label="Valores" value={String(analysis.values.length)} icon={Scale} color="text-purple-600" bg="bg-purple-500/10" />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-lg border border-border p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            <Users className="h-3.5 w-3.5" /> Partes
          </div>
          <div className="space-y-1.5">
            {analysis.parties.length === 0 ? <p className="text-[11px] text-muted-foreground">Nenhuma parte detectada.</p> :
              analysis.parties.map((p, i) => (
                <div key={i} className="flex items-center justify-between text-xs">
                  <span className="font-medium">{p.role}</span>
                  <span className="text-muted-foreground">{p.name || "—"} · {p.type}</span>
                </div>
              ))}
          </div>
        </div>

        <div className="rounded-lg border border-border p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            <Scale className="h-3.5 w-3.5" /> Valores
          </div>
          <div className="space-y-1.5">
            {analysis.values.length === 0 ? <p className="text-[11px] text-muted-foreground">Nenhum valor.</p> :
              analysis.values.map((v, i) => (
                <div key={i} className="flex items-center justify-between text-xs">
                  <span className="font-medium">{v.label}</span>
                  <span className="font-mono">{v.amount}</span>
                </div>
              ))}
          </div>
        </div>

        <div className="rounded-lg border border-border p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            <BarChart3 className="h-3.5 w-3.5" /> Pedidos
          </div>
          <ul className="space-y-1.5 text-xs">
            {analysis.requests.length === 0 ? <li className="text-muted-foreground">Nenhum pedido.</li> :
              analysis.requests.map((r, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-primary" />
                  <span>{r}</span>
                </li>
              ))}
          </ul>
        </div>

        <div className="rounded-lg border border-border p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            <FileText className="h-3.5 w-3.5" /> Próximos passos
          </div>
          <ul className="space-y-1.5 text-xs">
            {analysis.nextSteps.length === 0 ? <li className="text-muted-foreground">Nenhum.</li> :
              analysis.nextSteps.map((s, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-emerald-500" />
                  <span>{s}</span>
                </li>
              ))}
          </ul>
        </div>
      </div>

      {analysis.risks.length > 0 && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-400">
            <BarChart3 className="h-3.5 w-3.5" /> Riscos identificados
          </div>
          <div className="space-y-1.5">
            {analysis.risks.map((r, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <Badge variant="outline" className={`text-[10px] ${
                  r.level === "alto" ? "border-rose-500/40 text-rose-600" :
                  r.level === "médio" || r.level === "medio" ? "border-amber-500/40 text-amber-600" :
                  "border-emerald-500/40 text-emerald-600"
                }`}>{r.level}</Badge>
                <span>{r.description}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function StatBox({ label, value, icon: Icon, color, bg }: { label: string; value: string; icon: React.ComponentType<{ className?: string }>; color: string; bg: string }) {
  return (
    <div className="rounded-lg border border-border p-3">
      <div className={`flex h-7 w-7 items-center justify-center rounded ${bg} ${color}`}>
        <Icon className="h-3.5 w-3.5" />
      </div>
      <div className="mt-2 text-xl font-bold">{value}</div>
      <div className="text-[10px] text-muted-foreground">{label}</div>
    </div>
  );
}
