"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  BarChart3,
  TrendingUp,
  FileText,
  Award,
  Plus,
  Trash2,
  Loader2,
  Percent,
  Target,
  Clock,
  Users,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { toast } from "@/hooks/use-toast";

interface CaseItem { id: string; title: string; area: string; responsavel: string | null; resultado: string | null; createdAt: string; }
interface DocItem { id: string; title: string; templateSlug: string; templateName: string; createdAt: string; }

interface Advogado {
  id: string;
  nome: string;
  oab: string;
  oabUf: string;
  especialidade: string;
  casosAtivos: number;
  docsGerados: number;
  custoMensal: number;
}

const STORAGE_KEY = "juridia-advogados";

function loadAdvogados(): Advogado[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Advogado[]) : seedAdvogados();
  } catch { return []; }
}

function saveAdvogados(items: Advogado[]) {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

function seedAdvogados(): Advogado[] {
  const items: Advogado[] = [
    { id: "adv_1", nome: "Ana Carolina Souza", oab: "123456", oabUf: "SP", especialidade: "Cível", casosAtivos: 12, docsGerados: 48, custoMensal: 12000 },
    { id: "adv_2", nome: "Bruno Lima", oab: "234567", oabUf: "RJ", especialidade: "Trabalhista", casosAtivos: 18, docsGerados: 67, custoMensal: 10000 },
    { id: "adv_3", nome: "Clara Mendes", oab: "345678", oabUf: "MG", especialidade: "Consumidor", casosAtivos: 9, docsGerados: 31, custoMensal: 8000 },
    { id: "adv_4", nome: "Diego Alves", oab: "456789", oabUf: "SP", especialidade: "Tributário", casosAtivos: 6, docsGerados: 22, custoMensal: 15000 },
  ];
  saveAdvogados(items);
  return items;
}

const fmtMoeda = (n: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(n);

export function Produtividade() {
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [advogados, setAdvogados] = useState<Advogado[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [oabDialogOpen, setOabDialogOpen] = useState(false);

  const [form, setForm] = useState({ nome: "", oab: "", oabUf: "SP", especialidade: "Cível", custoMensal: "" });

  useEffect(() => {
    Promise.all([
      fetch("/api/cases").then((r) => r.json()).catch(() => ({ cases: [] })),
      fetch("/api/documents").then((r) => r.json()).catch(() => ({ documents: [] })),
    ]).then(([c, d]) => {
      setCases(c.cases || []);
      setDocs(d.documents || []);
      setAdvogados(loadAdvogados());
    }).finally(() => setLoading(false));
  }, []);

  // ── KPIs ────────────────────────────────────────────────────────────────────
  const kpis = useMemo(() => {
    const now = new Date();
    const month = now.getMonth();
    const year = now.getFullYear();
    const docsThisMonth = docs.filter((d) => { const dt = new Date(d.createdAt); return dt.getMonth() === month && dt.getFullYear() === year; }).length;
    const casesActive = cases.length;
    const avgCusto = advogados.reduce((s, a) => s + a.custoMensal, 0) / Math.max(1, advogados.length);
    return {
      docsTotal: docs.length,
      docsThisMonth,
      casesActive,
      avgCusto: isNaN(avgCusto) ? 0 : avgCusto,
    };
  }, [docs, cases, advogados]);

  // ── Bar chart mensal ─────────────────────────────────────────────────────────
  const monthlyBars = useMemo(() => {
    const months: { label: string; total: number }[] = [];
    const today = new Date();
    for (let i = 5; i >= 0; i--) {
      const d = new Date(today.getFullYear(), today.getMonth() - i, 1);
      const label = d.toLocaleDateString("pt-BR", { month: "short" });
      const total = docs.filter((doc) => { const dt = new Date(doc.createdAt); return dt.getMonth() === d.getMonth() && dt.getFullYear() === d.getFullYear(); }).length;
      months.push({ label, total });
    }
    return months;
  }, [docs]);

  const maxMonthly = Math.max(...monthlyBars.map((m) => m.total), 1);

  // ── Cost series ───────────────────────────────────────────────────────────────
  const costSeries = useMemo(() => {
    const months: { label: string; custo: number }[] = [];
    const today = new Date();
    for (let i = 5; i >= 0; i--) {
      const d = new Date(today.getFullYear(), today.getMonth() - i, 1);
      const label = d.toLocaleDateString("pt-BR", { month: "short" });
      const custo = advogados.reduce((s, a) => s + a.custoMensal, 0);
      months.push({ label, custo });
    }
    return months;
  }, [advogados]);
  const maxCost = Math.max(...costSeries.map((m) => m.custo), 1);

  // ── Top templates ────────────────────────────────────────────────────────────
  const topTemplates = useMemo(() => {
    const map: Record<string, number> = {};
    for (const d of docs) map[d.templateName] = (map[d.templateName] || 0) + 1;
    return Object.entries(map).map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count).slice(0, 5);
  }, [docs]);

  // ── Top skills (do advogados por especialidade) ───────────────────────────────
  const topSkills = useMemo(() => {
    const map: Record<string, number> = {};
    for (const a of advogados) map[a.especialidade] = (map[a.especialidade] || 0) + a.docsGerados;
    return Object.entries(map).map(([name, total]) => ({ name, total })).sort((a, b) => b.total - a.total).slice(0, 5);
  }, [advogados]);

  // ── Pie: desfechos ─────────────────────────────────────────────────────────────
  const desfechos = useMemo(() => {
    const map: Record<string, number> = {};
    for (const c of cases) {
      const r = c.resultado || "pendente";
      map[r] = (map[r] || 0) + 1;
    }
    return Object.entries(map).map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count);
  }, [cases]);

  // ── Pie: casos por área ────────────────────────────────────────────────────────
  const casesByArea = useMemo(() => {
    const map: Record<string, number> = {};
    for (const c of cases) map[c.area] = (map[c.area] || 0) + 1;
    return Object.entries(map).map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count);
  }, [cases]);

  // ── Ranking advogados ───────────────────────────────────────────────────────────
  const ranking = useMemo(() => {
    return [...advogados].sort((a, b) => (b.docsGerados + b.casosAtivos * 5) - (a.docsGerados + a.casosAtivos * 5));
  }, [advogados]);

  const PIE_COLORS = ["#10b981", "#f59e0b", "#06b6d4", "#a855f7", "#ec4899", "#f97316"];

  function addAdvogado() {
    if (!form.nome.trim() || !form.oab.trim()) {
      toast({ title: "Nome e OAB obrigatórios", variant: "destructive" });
      return;
    }
    const novo: Advogado = {
      id: `adv_${Date.now()}`,
      nome: form.nome.trim(),
      oab: form.oab.trim(),
      oabUf: form.oabUf,
      especialidade: form.especialidade,
      casosAtivos: 0,
      docsGerados: 0,
      custoMensal: Number(form.custoMensal) || 0,
    };
    const next = [...advogados, novo];
    setAdvogados(next);
    saveAdvogados(next);
    setDialogOpen(false);
    setOabDialogOpen(false);
    setForm({ nome: "", oab: "", oabUf: "SP", especialidade: "Cível", custoMensal: "" });
    toast({ title: "Advogado cadastrado", description: `${novo.nome} — OAB ${novo.oabUf} ${novo.oab}` });
  }

  function delAdvogado(id: string) {
    const next = advogados.filter((a) => a.id !== id);
    setAdvogados(next);
    saveAdvogados(next);
    toast({ title: "Advogado removido" });
  }

  if (loading) return <div className="flex h-48 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>;

  return (
    <div className="container-juridia py-8">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="mb-6 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <BarChart3 className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">Produtividade</h1>
              <p className="text-sm text-muted-foreground">KPIs, séries temporais, ranking de advogados e desfechos.</p>
            </div>
          </div>
          <Dialog open={oabDialogOpen} onOpenChange={setOabDialogOpen}>
            <DialogTrigger asChild>
              <Button><Plus className="mr-2 h-4 w-4" /> Cadastrar advogado</Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle>Cadastrar advogado</DialogTitle>
              </DialogHeader>
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">Nome</Label>
                  <Input value={form.nome} onChange={(e) => setForm(s => ({ ...s, nome: e.target.value }))} placeholder="Ex: Ana Carolina Souza" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">OAB (somente dígitos)</Label>
                    <Input value={form.oab} onChange={(e) => setForm(s => ({ ...s, oab: e.target.value.replace(/\D/g, "") }))} placeholder="123456" inputMode="numeric" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">UF</Label>
                    <Input value={form.oabUf} onChange={(e) => setForm(s => ({ ...s, oabUf: e.target.value.toUpperCase().slice(0, 2) }))} maxLength={2} placeholder="SP" />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Especialidade</Label>
                  <Input value={form.especialidade} onChange={(e) => setForm(s => ({ ...s, especialidade: e.target.value }))} placeholder="Cível" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Custo mensal (R$)</Label>
                  <Input type="number" step="0.01" value={form.custoMensal} onChange={(e) => setForm(s => ({ ...s, custoMensal: e.target.value }))} placeholder="10000.00" />
                </div>
                <p className="text-[10px] text-muted-foreground">⚠ OAB é validada no backend em produção (formato numérico + UF única).</p>
                <Button onClick={addAdvogado} className="w-full">Cadastrar</Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </motion.div>

      {/* KPIs */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { icon: FileText, label: "Minutas totais", value: String(kpis.docsTotal), sub: `${kpis.docsThisMonth} este mês`, color: "text-emerald-600", bg: "bg-emerald-500/10" },
          { icon: Target, label: "Casos ativos", value: String(kpis.casesActive), sub: "no momento", color: "text-amber-600", bg: "bg-amber-500/10" },
          { icon: Users, label: "Advogados", value: String(advogados.length), sub: "cadastrados", color: "text-cyan-600", bg: "bg-cyan-500/10" },
          { icon: TrendingUp, label: "Custo médio/adv", value: fmtMoeda(kpis.avgCusto), sub: "por mês", color: "text-purple-600", bg: "bg-purple-500/10" },
        ].map((s, i) => (
          <motion.div key={s.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}>
            <Card>
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${s.bg} ${s.color}`}>
                    <s.icon className="h-4 w-4" />
                  </div>
                  <span className="text-[10px] text-muted-foreground">{s.sub}</span>
                </div>
                <div className="mt-3 text-2xl font-bold">{s.value}</div>
                <div className="mt-0.5 text-xs text-muted-foreground">{s.label}</div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Bar chart mensal */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <BarChart3 className="h-4 w-4 text-primary" /> Minutas por mês
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-end gap-3 h-44">
              {monthlyBars.map((m, i) => (
                <div key={i} className="flex flex-1 flex-col items-center gap-1">
                  <motion.div
                    initial={{ height: 0 }}
                    animate={{ height: `${(m.total / maxMonthly) * 100}%` }}
                    transition={{ duration: 0.6, delay: i * 0.05 }}
                    className="w-8 rounded-t bg-gradient-to-t from-primary/60 to-primary"
                    title={`${m.total} minutas`}
                  />
                  <span className="text-[9px] text-muted-foreground">{m.label}</span>
                  <span className="text-[9px] font-mono">{m.total}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Cost series */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <TrendingUp className="h-4 w-4 text-primary" /> Custo mensal total
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-end gap-3 h-44">
              {costSeries.map((m, i) => (
                <div key={i} className="flex flex-1 flex-col items-center gap-1">
                  <motion.div
                    initial={{ height: 0 }}
                    animate={{ height: `${(m.custo / maxCost) * 100}%` }}
                    transition={{ duration: 0.6, delay: i * 0.05 }}
                    className="w-8 rounded-t bg-gradient-to-t from-purple-500/60 to-purple-500"
                    title={fmtMoeda(m.custo)}
                  />
                  <span className="text-[9px] text-muted-foreground">{m.label}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Top skills */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Award className="h-4 w-4 text-primary" /> Top especialidades
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {topSkills.length === 0 ? (
              <p className="py-6 text-center text-xs text-muted-foreground">Cadastre advogados para ver ranking.</p>
            ) : topSkills.map((s, i) => {
              const max = Math.max(...topSkills.map((x) => x.total));
              return (
                <div key={s.name} className="flex items-center gap-3">
                  <Badge variant="outline" className="text-[10px]">#{i + 1}</Badge>
                  <div className="w-32 truncate text-xs font-medium">{s.name}</div>
                  <div className="relative h-4 flex-1 overflow-hidden rounded bg-secondary">
                    <motion.div initial={{ width: 0 }} animate={{ width: `${(s.total / max) * 100}%` }} transition={{ duration: 0.6, delay: i * 0.05 }} className="absolute inset-y-0 left-0 rounded bg-gradient-to-r from-emerald-500/70 to-emerald-500" />
                  </div>
                  <span className="font-mono text-xs font-semibold">{s.total}</span>
                </div>
              );
            })}
          </CardContent>
        </Card>

        {/* Top templates */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FileText className="h-4 w-4 text-primary" /> Top templates
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {topTemplates.length === 0 ? (
              <p className="py-6 text-center text-xs text-muted-foreground">Nenhuma minuta gerada ainda.</p>
            ) : topTemplates.map((s, i) => {
              const max = Math.max(...topTemplates.map((x) => x.count));
              return (
                <div key={s.name} className="flex items-center gap-3">
                  <Badge variant="outline" className="text-[10px]">#{i + 1}</Badge>
                  <div className="w-32 truncate text-xs font-medium">{s.name}</div>
                  <div className="relative h-4 flex-1 overflow-hidden rounded bg-secondary">
                    <motion.div initial={{ width: 0 }} animate={{ width: `${(s.count / max) * 100}%` }} transition={{ duration: 0.6, delay: i * 0.05 }} className="absolute inset-y-0 left-0 rounded bg-gradient-to-r from-cyan-500/70 to-cyan-500" />
                  </div>
                  <span className="font-mono text-xs font-semibold">{s.count}</span>
                </div>
              );
            })}
          </CardContent>
        </Card>

        {/* Pie desfechos */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Percent className="h-4 w-4 text-primary" /> Desfechos
            </CardTitle>
          </CardHeader>
          <CardContent>
            <PieMini data={desfechos} colors={PIE_COLORS} />
          </CardContent>
        </Card>

        {/* Pie casos por área */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <BarChart3 className="h-4 w-4 text-primary" /> Casos por área
            </CardTitle>
          </CardHeader>
          <CardContent>
            <PieMini data={casesByArea} colors={PIE_COLORS} />
          </CardContent>
        </Card>
      </div>

      {/* Ranking advogados */}
      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Award className="h-4 w-4 text-primary" /> Ranking de advogados
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {ranking.map((a, i) => {
              const score = a.docsGerados + a.casosAtivos * 5;
              const maxScore = Math.max(...ranking.map((x) => x.docsGerados + x.casosAtivos * 5), 1);
              return (
                <motion.div
                  key={a.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.04 }}
                  className="flex items-center gap-3 rounded-lg border border-border p-3"
                >
                  <Badge variant={i < 3 ? "default" : "secondary"} className="text-[10px]">#{i + 1}</Badge>
                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10 text-primary font-bold text-xs">
                    {a.nome.split(" ").slice(0, 2).map((n) => n[0]).join("")}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold truncate">{a.nome}</span>
                      <Badge variant="outline" className="text-[10px]">OAB {a.oabUf} {a.oab}</Badge>
                      <Badge variant="outline" className="text-[10px]">{a.especialidade}</Badge>
                    </div>
                    <div className="mt-1 text-[10px] text-muted-foreground">
                      {a.casosAtivos} casos ativos · {a.docsGerados} minutas geradas · {fmtMoeda(a.custoMensal)}/mês
                    </div>
                  </div>
                  <div className="hidden sm:block w-32">
                    <Progress value={(score / maxScore) * 100} className="h-2" />
                  </div>
                  <span className="font-mono text-sm font-bold text-primary">{score}</span>
                  <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => delAdvogado(a.id)}><Trash2 className="h-3.5 w-3.5" /></Button>
                </motion.div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function PieMini({ data, colors }: { data: { name: string; count: number }[]; colors: string[] }) {
  const total = data.reduce((s, d) => s + d.count, 0) || 1;
  if (data.length === 0) {
    return <div className="py-6 text-center text-xs text-muted-foreground">Sem dados.</div>;
  }
  return (
    <div className="flex items-center gap-4">
      <svg viewBox="-1.6 -1.6 3.2 3.2" className="h-28 w-28 -rotate-90">
        {(() => {
          const cumulative = data.reduce<number[]>((acc, d) => {
            const prev = acc.length > 0 ? acc[acc.length - 1] : 0;
            return [...acc, prev + d.count];
          }, []);
          const computed = data.map((d, i) => {
            const start = (i > 0 ? cumulative[i - 1] : 0) / total;
            const end = cumulative[i] / total;
            return { start, end, large: end - start > 0.5 ? 1 : 0, i };
          });
          return computed.map(({ start, end, large, i }) => {
            const startAngle = start * 2 * Math.PI;
            const endAngle = end * 2 * Math.PI;
            const x1 = Math.cos(startAngle), y1 = Math.sin(startAngle);
            const x2 = Math.cos(endAngle), y2 = Math.sin(endAngle);
            return (
              <path
                key={i}
                d={`M 0 0 L ${x1.toFixed(3)} ${y1.toFixed(3)} A 1 1 0 ${large} 1 ${x2.toFixed(3)} ${y2.toFixed(3)} Z`}
                fill={colors[i % colors.length]}
                stroke="#fff"
                strokeWidth="0.02"
              />
            );
          });
        })()}
      </svg>
      <div className="flex-1 space-y-1">
        {data.map((d, i) => (
          <div key={d.name} className="flex items-center justify-between gap-2 text-xs">
            <span className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: colors[i % colors.length] }} />
              <span className="font-medium">{d.name}</span>
            </span>
            <span className="font-mono text-muted-foreground">{d.count} ({Math.round((d.count / total) * 100)}%)</span>
          </div>
        ))}
      </div>
    </div>
  );
}
