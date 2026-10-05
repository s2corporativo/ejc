"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  CalendarClock,
  Plus,
  Trash2,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Briefcase,
  Gavel,
  FileText,
  Hourglass,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { toast } from "@/hooks/use-toast";

// ── Tipos ───────────────────────────────────────────────────────────────────
interface CaseItem { id: string; title: string; number: string | null; clientName?: string; }

interface Deadline {
  id: string;
  caseId: string;
  caseTitle: string;
  tipo: string;
  descricao: string;
  marcoInicial: string;
  prazoDias: number;
  tipoContagem: "uteis" | "corridos";
  vencimento: string;
  createdAt: string;
}

const TIPO_LABELS: Record<string, string> = {
  contestacao: "Contestação",
  recurso: "Recurso",
  intimacao: "Intimação",
  audiencia: "Audiência",
  outro: "Outro",
};

const STORAGE_KEY = "juridia-deadlines";

function loadDeadlines(): Deadline[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Deadline[]) : [];
  } catch { return []; }
}

function saveDeadlines(items: Deadline[]) {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

// Cálculo determinístico do vencimento (dias úteis/corridos, sem feriados locais)
function calcularVencimento(marcoStr: string, dias: number, tipo: "uteis" | "corridos"): Date {
  const v = new Date(marcoStr + "T12:00:00");
  if (tipo === "corridos") {
    v.setDate(v.getDate() + dias);
  } else {
    let added = 0;
    while (added < dias) {
      v.setDate(v.getDate() + 1);
      const day = v.getDay();
      if (day !== 0 && day !== 6) added++;
    }
  }
  // Prorrogação: fim de semana → próximo útil
  while (v.getDay() === 0 || v.getDay() === 6) v.setDate(v.getDate() + 1);
  return v;
}

interface StatusInfo {
  label: string;
  color: string;
  bg: string;
  icon: React.ComponentType<{ className?: string }>;
}

function getStatus(deadline: Deadline): StatusInfo {
  const hoje = new Date();
  hoje.setHours(0, 0, 0, 0);
  const venc = new Date(deadline.vencimento);
  venc.setHours(0, 0, 0, 0);
  const diff = Math.round((venc.getTime() - hoje.getTime()) / (1000 * 60 * 60 * 24));
  if (diff < 0) return { label: `Vencido há ${Math.abs(diff)} dias`, color: "text-rose-700 dark:text-rose-400", bg: "border-rose-500/50 bg-rose-500/5", icon: AlertTriangle };
  if (diff === 0) return { label: "Vence hoje", color: "text-amber-700 dark:text-amber-400", bg: "border-amber-500/50 bg-amber-500/5", icon: Clock };
  if (diff <= 3) return { label: `Vence em ${diff} dias`, color: "text-amber-700 dark:text-amber-400", bg: "border-amber-500/40 bg-amber-500/5", icon: Clock };
  return { label: `Faltam ${diff} dias`, color: "text-emerald-700 dark:text-emerald-400", bg: "border-emerald-500/40 bg-emerald-500/5", icon: CheckCircle2 };
}

export function Prazos() {
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [deadlines, setDeadlines] = useState<Deadline[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("todos");
  const [dialogOpen, setDialogOpen] = useState(false);

  const [form, setForm] = useState({
    caseId: "",
    tipo: "contestacao",
    descricao: "",
    marcoInicial: "",
    prazoDias: "15",
    tipoContagem: "uteis" as "uteis" | "corridos",
  });

  async function loadCases() {
    try {
      const res = await fetch("/api/cases");
      const data = await res.json();
      setCases((data.cases || []).map((c: { id: string; title: string; number: string | null; clientName?: string }) => ({ id: c.id, title: c.title, number: c.number, clientName: c.clientName })));
    } catch { /* ignore */ }
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch("/api/cases").then((r) => r.json()).catch(() => ({ cases: [] })),
      Promise.resolve(loadDeadlines()),
    ]).then(([data, dl]) => {
      if (cancelled) return;
      setCases((data.cases || []).map((c: { id: string; title: string; number: string | null; clientName?: string }) => ({ id: c.id, title: c.title, number: c.number, clientName: c.clientName })));
      setDeadlines(dl);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, []);

  function persist(items: Deadline[]) {
    setDeadlines(items);
    saveDeadlines(items);
  }

  async function addDeadline() {
    if (!form.caseId) { toast({ title: "Selecione um caso", variant: "destructive" }); return; }
    if (!form.marcoInicial || !form.prazoDias) { toast({ title: "Marco inicial e prazo obrigatórios", variant: "destructive" }); return; }
    if (!form.descricao.trim()) { toast({ title: "Descrição obrigatória", variant: "destructive" }); return; }
    const c = cases.find((c) => c.id === form.caseId);
    const venc = calcularVencimento(form.marcoInicial, Number(form.prazoDias), form.tipoContagem);
    const novo: Deadline = {
      id: `dl_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      caseId: form.caseId,
      caseTitle: c?.title || "(caso)",
      tipo: form.tipo,
      descricao: form.descricao.trim(),
      marcoInicial: form.marcoInicial,
      prazoDias: Number(form.prazoDias),
      tipoContagem: form.tipoContagem,
      vencimento: venc.toISOString(),
      createdAt: new Date().toISOString(),
    };
    persist([novo, ...deadlines]);
    setDialogOpen(false);
    setForm({ caseId: "", tipo: "contestacao", descricao: "", marcoInicial: "", prazoDias: "15", tipoContagem: "uteis" });
    toast({ title: "Prazo registrado", description: `Vencimento: ${venc.toLocaleDateString("pt-BR")}` });
  }

  function delDeadline(id: string) {
    persist(deadlines.filter((d) => d.id !== id));
    toast({ title: "Prazo removido" });
  }

  const filtered = useMemo(() => {
    const hoje = new Date();
    hoje.setHours(0, 0, 0, 0);
    return deadlines.filter((d) => {
      const venc = new Date(d.vencimento);
      venc.setHours(0, 0, 0, 0);
      const diff = Math.round((venc.getTime() - hoje.getTime()) / (1000 * 60 * 60 * 24));
      if (filter === "vencido") return diff < 0;
      if (filter === "proximo") return diff >= 0 && diff <= 3;
      if (filter === "vigente") return diff > 3;
      return true;
    });
  }, [deadlines, filter]);

  const stats = useMemo(() => {
    const hoje = new Date();
    hoje.setHours(0, 0, 0, 0);
    return {
      vencido: deadlines.filter((d) => new Date(d.vencimento) < hoje).length,
      proximo: deadlines.filter((d) => {
        const venc = new Date(d.vencimento);
        const diff = Math.round((venc.getTime() - hoje.getTime()) / (1000 * 60 * 60 * 24));
        return diff >= 0 && diff <= 3;
      }).length,
      vigente: deadlines.filter((d) => {
        const venc = new Date(d.vencimento);
        const diff = Math.round((venc.getTime() - hoje.getTime()) / (1000 * 60 * 60 * 24));
        return diff > 3;
      }).length,
    };
  }, [deadlines]);

  return (
    <div className="container-juridia py-8">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="mb-6 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <CalendarClock className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">Prazos processuais</h1>
              <p className="text-sm text-muted-foreground">Contagem determinística (art. 219/224 CPC) — IA nunca confirma prazo.</p>
            </div>
          </div>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button><Plus className="mr-2 h-4 w-4" /> Novo prazo</Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle>Registrar prazo</DialogTitle>
              </DialogHeader>
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">Caso</Label>
                  <Select value={form.caseId} onValueChange={(v) => setForm(s => ({ ...s, caseId: v }))}>
                    <SelectTrigger><SelectValue placeholder="Selecione..." /></SelectTrigger>
                    <SelectContent>
                      {cases.length === 0 ? <SelectItem value="_" disabled>Nenhum caso cadastrado</SelectItem> : cases.map((c) => (
                        <SelectItem key={c.id} value={c.id}>{c.title}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Tipo</Label>
                    <Select value={form.tipo} onValueChange={(v) => setForm(s => ({ ...s, tipo: v }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>{Object.entries(TIPO_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Contagem</Label>
                    <Select value={form.tipoContagem} onValueChange={(v) => setForm(s => ({ ...s, tipoContagem: v as "uteis" | "corridos" }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="uteis">Dias úteis</SelectItem>
                        <SelectItem value="corridos">Dias corridos</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Marco inicial</Label>
                    <Input type="date" value={form.marcoInicial} onChange={(e) => setForm(s => ({ ...s, marcoInicial: e.target.value }))} />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Prazo (dias)</Label>
                    <Input type="number" value={form.prazoDias} onChange={(e) => setForm(s => ({ ...s, prazoDias: e.target.value }))} />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Descrição</Label>
                  <Textarea rows={2} value={form.descricao} onChange={(e) => setForm(s => ({ ...s, descricao: e.target.value }))} placeholder="Ex: Contestação no prazo de 15 dias úteis..." />
                </div>
                <Button onClick={addDeadline} className="w-full">Registrar prazo</Button>
                <p className="text-[10px] text-muted-foreground">⚠ Não considera feriados locais nem suspensões do tribunal — confira manualmente.</p>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </motion.div>

      {/* KPI cards coloridos */}
      <div className="mb-4 grid grid-cols-3 gap-3">
        <Card className="border-emerald-500/30 bg-emerald-500/5">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <CheckCircle2 className="h-5 w-5 text-emerald-600" />
              <span className="text-2xl font-bold text-emerald-700 dark:text-emerald-400">{stats.vigente}</span>
            </div>
            <div className="mt-1 text-xs text-muted-foreground">Vigentes (&gt;3 dias)</div>
          </CardContent>
        </Card>
        <Card className="border-amber-500/30 bg-amber-500/5">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <Clock className="h-5 w-5 text-amber-600" />
              <span className="text-2xl font-bold text-amber-700 dark:text-amber-400">{stats.proximo}</span>
            </div>
            <div className="mt-1 text-xs text-muted-foreground">Próximos (0-3 dias)</div>
          </CardContent>
        </Card>
        <Card className="border-rose-500/30 bg-rose-500/5">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <AlertTriangle className="h-5 w-5 text-rose-600" />
              <span className="text-2xl font-bold text-rose-700 dark:text-rose-400">{stats.vencido}</span>
            </div>
            <div className="mt-1 text-xs text-muted-foreground">Vencidos</div>
          </CardContent>
        </Card>
      </div>

      {/* Filtro */}
      <div className="mb-4 flex flex-wrap gap-2">
        {[
          { id: "todos", label: "Todos" },
          { id: "vencido", label: "Vencidos" },
          { id: "proximo", label: "Próximos" },
          { id: "vigente", label: "Vigentes" },
        ].map((f) => (
          <Button
            key={f.id}
            variant={filter === f.id ? "default" : "outline"}
            size="sm"
            onClick={() => setFilter(f.id)}
          >
            {f.label}
          </Button>
        ))}
      </div>

      {loading ? (
        <div className="flex h-48 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <Hourglass className="h-12 w-12 text-muted-foreground/40" />
            <div>
              <h3 className="font-semibold">Nenhum prazo registrado</h3>
              <p className="mt-1 text-sm text-muted-foreground">Clique em <strong>Novo prazo</strong> para registrar o primeiro.</p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          <AnimatePresence initial={false}>
            {filtered.map((d, i) => {
              const status = getStatus(d);
              const Icon = status.icon;
              return (
                <motion.div
                  key={d.id}
                  layout
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ delay: Math.min(i * 0.03, 0.3) }}
                >
                  <Card className={`${status.bg}`}>
                    <CardContent className="p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge variant="outline" className={`text-[10px] ${status.color} ${status.bg}`}>
                              <Icon className="mr-1 h-2.5 w-2.5" /> {status.label}
                            </Badge>
                            <Badge variant="secondary" className="text-[10px]">{TIPO_LABELS[d.tipo] || d.tipo}</Badge>
                            {d.tipoContagem === "uteis" ? (
                              <Badge variant="outline" className="text-[10px]"><Briefcase className="mr-1 h-2.5 w-2.5" /> Dias úteis</Badge>
                            ) : (
                              <Badge variant="outline" className="text-[10px]"><Clock className="mr-1 h-2.5 w-2.5" /> Dias corridos</Badge>
                            )}
                          </div>
                          <div className="mt-2 text-sm font-medium">{d.descricao}</div>
                          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                            <span className="flex items-center gap-1"><Briefcase className="h-3 w-3" /> {d.caseTitle}</span>
                            <span className="flex items-center gap-1"><Gavel className="h-3 w-3" /> Marco: {new Date(d.marcoInicial + "T12:00:00").toLocaleDateString("pt-BR")}</span>
                            <span className="flex items-center gap-1 font-mono"><CalendarClock className="h-3 w-3" /> Vencimento: {new Date(d.vencimento).toLocaleDateString("pt-BR")}</span>
                            <span className="flex items-center gap-1"><FileText className="h-3 w-3" /> {d.prazoDias} dias</span>
                          </div>
                        </div>
                        <Button size="icon" variant="ghost" onClick={() => delDeadline(d.id)} title="Excluir"><Trash2 className="h-4 w-4" /></Button>
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
