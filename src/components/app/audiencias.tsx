"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Gavel,
  Plus,
  Trash2,
  Calendar,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Briefcase,
  Clock,
  MapPin,
  Building2,
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

interface CaseItem { id: string; title: string; }

interface Audiencia {
  id: string;
  data: string;
  tipo: string;
  local: string | null;
  orgao: string | null;
  status: string;
  resultado: string | null;
  observacoes: string | null;
  caseId?: string;
  caseTitle?: string;
}

const TIPO_LABELS: Record<string, string> = {
  conciliacao: "Conciliação",
  instrucao: "Instrução",
  julgamento: "Julgamento",
  oitiva: "Oitiva",
  outra: "Outra",
};

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  agendada: { label: "Agendada", color: "text-amber-600 border-amber-500/40 bg-amber-500/5" },
  realizada: { label: "Realizada", color: "text-emerald-600 border-emerald-500/40 bg-emerald-500/5" },
  cancelada: { label: "Cancelada", color: "text-rose-600 border-rose-500/40 bg-rose-500/5" },
  redesignada: { label: "Redesignada", color: "text-cyan-600 border-cyan-500/40 bg-cyan-500/5" },
};

const WEEKDAYS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const MONTHS = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];

export function Audiencias() {
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [audiencias, setAudiencias] = useState<Audiencia[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"lista" | "calendario">("lista");
  const [currentMonth, setCurrentMonth] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const [dialogOpen, setDialogOpen] = useState(false);
  const [preselectedDate, setPreselectedDate] = useState<string>("");

  const [form, setForm] = useState({
    caseId: "",
    data: "",
    tipo: "conciliacao",
    local: "",
    orgao: "",
    observacoes: "",
  });

  async function load() {
    setLoading(true);
    try {
      const [cRes, ...aRes] = await Promise.all([
        fetch("/api/cases"),
        ...[].map(() => null),
      ]);
      const cData = await cRes.json();
      const caseList: CaseItem[] = (cData.cases || []).map((c: { id: string; title: string }) => ({ id: c.id, title: c.title }));
      setCases(caseList);
      // Busca audiências de cada caso (paralelo, limitado)
      const all: Audiencia[] = [];
      await Promise.all(
        caseList.slice(0, 20).map(async (c) => {
          try {
            const r = await fetch(`/api/cases/hearings?caseId=${c.id}`);
            const d = await r.json();
            for (const a of d.audiencias || []) {
              all.push({ ...a, caseId: c.id, caseTitle: c.title });
            }
          } catch { /* ignore */ }
        })
      );
      all.sort((a, b) => new Date(a.data).getTime() - new Date(b.data).getTime());
      setAudiencias(all);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  function openNew(date?: string) {
    setForm({ caseId: cases[0]?.id || "", data: date ? date : "", tipo: "conciliacao", local: "", orgao: "", observacoes: "" });
    setPreselectedDate(date || "");
    setDialogOpen(true);
  }

  async function addAudiencia() {
    if (!form.caseId) { toast({ title: "Selecione um caso", variant: "destructive" }); return; }
    if (!form.data) { toast({ title: "Data obrigatória", variant: "destructive" }); return; }
    try {
      await fetch("/api/cases/hearings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ caseId: form.caseId, data: form.data, tipo: form.tipo, local: form.local, orgao: form.orgao, observacoes: form.observacoes }),
      });
      toast({ title: "Audiência agendada" });
      setDialogOpen(false);
      load();
    } catch {
      toast({ title: "Erro ao agendar", variant: "destructive" });
    }
  }

  async function delAudiencia(id: string) {
    try {
      await fetch(`/api/cases/hearings?id=${id}`, { method: "DELETE" });
      setAudiencias((cur) => cur.filter((a) => a.id !== id));
      toast({ title: "Audiência removida" });
    } catch { /* ignore */ }
  }

  // ── Calendário ─────────────────────────────────────────────────────────────
  const monthMatrix = useMemo(() => {
    const first = new Date(currentMonth.getFullYear(), currentMonth.getMonth(), 1);
    const start = new Date(first);
    start.setDate(start.getDate() - first.getDay());
    const weeks: Date[][] = [];
    for (let w = 0; w < 6; w++) {
      const days: Date[] = [];
      for (let d = 0; d < 7; d++) {
        const day = new Date(start);
        day.setDate(start.getDate() + w * 7 + d);
        days.push(day);
      }
      weeks.push(days);
    }
    return weeks;
  }, [currentMonth]);

  const audienciasByDay = useMemo(() => {
    const map: Record<string, Audiencia[]> = {};
    for (const a of audiencias) {
      const key = new Date(a.data).toDateString();
      if (!map[key]) map[key] = [];
      map[key].push(a);
    }
    return map;
  }, [audiencias]);

  const prevMonth = () => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1));
  const nextMonth = () => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1));

  const today = new Date();
  const upcoming = useMemo(() => {
    const now = Date.now();
    return audiencias.filter((a) => new Date(a.data).getTime() >= now).slice(0, 8);
  }, [audiencias]);

  return (
    <div className="container-juridia py-8">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="mb-6 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Gavel className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">Audiências</h1>
              <p className="text-sm text-muted-foreground">Calendário e lista de audiências — conciliação, instrução, julgamento, oitiva.</p>
            </div>
          </div>
          <div className="flex gap-2">
            <div className="flex overflow-hidden rounded-md border border-border">
              <Button variant={view === "lista" ? "default" : "ghost"} size="sm" onClick={() => setView("lista")}>Lista</Button>
              <Button variant={view === "calendario" ? "default" : "ghost"} size="sm" onClick={() => setView("calendario")}>Calendário</Button>
            </div>
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button onClick={() => openNew()}><Plus className="mr-2 h-4 w-4" /> Agendar</Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-md">
                <DialogHeader>
                  <DialogTitle>Agendar audiência {preselectedDate && `(${new Date(preselectedDate).toLocaleDateString("pt-BR")})`}</DialogTitle>
                </DialogHeader>
                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Caso</Label>
                    <Select value={form.caseId} onValueChange={(v) => setForm(s => ({ ...s, caseId: v }))}>
                      <SelectTrigger><SelectValue placeholder="Selecione..." /></SelectTrigger>
                      <SelectContent>
                        {cases.length === 0 ? <SelectItem value="_" disabled>Nenhum caso</SelectItem> : cases.map((c) => (
                          <SelectItem key={c.id} value={c.id}>{c.title}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <Label className="text-xs">Data e hora</Label>
                      <Input type="datetime-local" value={form.data} onChange={(e) => setForm(s => ({ ...s, data: e.target.value }))} />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs">Tipo</Label>
                      <Select value={form.tipo} onValueChange={(v) => setForm(s => ({ ...s, tipo: v }))}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>{Object.entries(TIPO_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <Label className="text-xs">Local</Label>
                      <Input value={form.local} onChange={(e) => setForm(s => ({ ...s, local: e.target.value }))} placeholder="Endereço/Fórum" />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs">Vara/Órgão</Label>
                      <Input value={form.orgao} onChange={(e) => setForm(s => ({ ...s, orgao: e.target.value }))} placeholder="1ª Vara Cível" />
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Observações</Label>
                    <Textarea rows={2} value={form.observacoes} onChange={(e) => setForm(s => ({ ...s, observacoes: e.target.value }))} />
                  </div>
                  <Button onClick={addAudiencia} className="w-full">Agendar</Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </motion.div>

      {loading ? (
        <div className="flex h-48 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
      ) : view === "lista" ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Clock className="h-4 w-4 text-primary" /> Próximas audiências
              </CardTitle>
            </CardHeader>
            <CardContent>
              {upcoming.length === 0 ? (
                <div className="py-8 text-center text-sm text-muted-foreground">Nenhuma audiência agendada.</div>
              ) : (
                <div className="space-y-2 max-h-[60vh] overflow-y-auto scrollbar-juridia">
                  <AnimatePresence initial={false}>
                    {upcoming.map((a, i) => (
                      <motion.div key={a.id} layout initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 8 }} transition={{ delay: Math.min(i * 0.03, 0.3) }}>
                        <AudienciaCard a={a} onDelete={() => delAudiencia(a.id)} />
                      </motion.div>
                    ))}
                  </AnimatePresence>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Gavel className="h-4 w-4 text-primary" /> Todas as audiências
              </CardTitle>
            </CardHeader>
            <CardContent>
              {audiencias.length === 0 ? (
                <div className="py-8 text-center text-sm text-muted-foreground">Nenhuma audiência registrada.</div>
              ) : (
                <div className="space-y-2 max-h-[60vh] overflow-y-auto scrollbar-juridia">
                  {audiencias.map((a, i) => (
                    <motion.div key={a.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i * 0.02, 0.3) }}>
                      <AudienciaCard a={a} onDelete={() => delAudiencia(a.id)} />
                    </motion.div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      ) : (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-base">
                <Calendar className="h-4 w-4 text-primary" />
                {MONTHS[currentMonth.getMonth()]} {currentMonth.getFullYear()}
              </CardTitle>
              <div className="flex items-center gap-1">
                <Button size="icon" variant="ghost" onClick={prevMonth}><ChevronLeft className="h-4 w-4" /></Button>
                <Button size="sm" variant="ghost" onClick={() => { const d = new Date(); setCurrentMonth(new Date(d.getFullYear(), d.getMonth(), 1)); }}>Hoje</Button>
                <Button size="icon" variant="ghost" onClick={nextMonth}><ChevronRight className="h-4 w-4" /></Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-7 gap-1 text-center text-[10px] uppercase tracking-wider text-muted-foreground">
              {WEEKDAYS.map((d) => <div key={d} className="py-1">{d}</div>)}
            </div>
            <div className="grid grid-cols-7 gap-1">
              {monthMatrix.flat().map((day, idx) => {
                const isCurrentMonth = day.getMonth() === currentMonth.getMonth();
                const isToday = day.toDateString() === today.toDateString();
                const dayKey = day.toDateString();
                const dayAud = audienciasByDay[dayKey] || [];
                return (
                  <button
                    key={idx}
                    onClick={() => openNew(day.toISOString().slice(0, 10) + "T09:00")}
                    className={`relative aspect-square rounded-md border p-1 text-left text-xs transition-colors hover:border-primary/40 hover:bg-accent ${
                      isCurrentMonth ? "border-border bg-card" : "border-border/50 bg-secondary/30 text-muted-foreground"
                    } ${isToday ? "ring-1 ring-primary/40" : ""}`}
                  >
                    <div className={`font-mono text-[10px] ${isToday ? "font-bold text-primary" : ""}`}>{day.getDate()}</div>
                    <div className="mt-0.5 flex flex-wrap gap-0.5">
                      {dayAud.slice(0, 3).map((a) => (
                        <div key={a.id} className={`h-1.5 w-1.5 rounded-full ${
                          a.tipo === "conciliacao" ? "bg-emerald-500" :
                          a.tipo === "instrucao" ? "bg-amber-500" :
                          a.tipo === "julgamento" ? "bg-rose-500" :
                          a.tipo === "oitiva" ? "bg-cyan-500" : "bg-purple-500"
                        }`} title={`${TIPO_LABELS[a.tipo] || a.tipo} — ${new Date(a.data).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`} />
                      ))}
                    </div>
                    {dayAud.length > 3 && <div className="absolute bottom-0.5 right-1 text-[8px] text-muted-foreground">+{dayAud.length - 3}</div>}
                  </button>
                );
              })}
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-3 text-[10px] text-muted-foreground">
              <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Conciliação</span>
              <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-amber-500" /> Instrução</span>
              <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-rose-500" /> Julgamento</span>
              <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-cyan-500" /> Oitiva</span>
              <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-purple-500" /> Outra</span>
              <span className="ml-auto">Clique em um dia para agendar</span>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function AudienciaCard({ a, onDelete }: { a: Audiencia; onDelete: () => void }) {
  const status = STATUS_CONFIG[a.status] || { label: a.status, color: "text-muted-foreground" };
  const date = new Date(a.data);
  return (
    <div className="flex items-start gap-3 rounded-lg border border-border p-3 transition-colors hover:bg-accent/40">
      <div className="flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-lg bg-primary/10 text-primary">
        <span className="font-mono text-[10px] uppercase leading-none">{date.toLocaleDateString("pt-BR", { month: "short" })}</span>
        <span className="font-bold leading-none">{date.getDate()}</span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary" className="text-[10px]">{TIPO_LABELS[a.tipo] || a.tipo}</Badge>
          <Badge variant="outline" className={`text-[10px] ${status.color}`}>{status.label}</Badge>
          {a.caseTitle && <span className="flex items-center gap-1 truncate text-[10px] text-muted-foreground"><Briefcase className="h-2.5 w-2.5" /> {a.caseTitle}</span>}
        </div>
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span className="flex items-center gap-1 font-mono"><Clock className="h-3 w-3" /> {date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</span>
          {a.local && <span className="flex items-center gap-1"><MapPin className="h-3 w-3" /> {a.local}</span>}
          {a.orgao && <span className="flex items-center gap-1"><Building2 className="h-3 w-3" /> {a.orgao}</span>}
        </div>
        {a.observacoes && <p className="mt-1 text-[10px] italic text-muted-foreground">{a.observacoes}</p>}
        {a.resultado && <p className="mt-1 text-[10px] font-medium text-emerald-700 dark:text-emerald-400">Resultado: {a.resultado}</p>}
      </div>
      <Button size="icon" variant="ghost" onClick={onDelete} className="h-7 w-7"><Trash2 className="h-3.5 w-3.5" /></Button>
    </div>
  );
}
