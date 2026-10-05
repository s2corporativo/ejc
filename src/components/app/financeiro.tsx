"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Wallet,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Download,
  FileText,
  PieChart,
  BarChart3,
  Loader2,
  Receipt,
  Clock,
  CheckCircle2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "@/hooks/use-toast";

interface CaseItem {
  id: string;
  title: string;
  valor: string | null;
  area: string;
  responsavel: string | null;
  clientName?: string;
  resultado: string | null;
  status: string;
}

interface AccountItem {
  id: string;
  description: string;
  amount: number;
  due: string;
  category: string;
  status: "receber" | "recebido" | "previsto";
  caseTitle?: string;
}

const fmtMoeda = (n: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(n);

const STORAGE_KEY = "juridia-accounts";

function loadAccounts(): AccountItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as AccountItem[]) : seedAccounts();
  } catch { return []; }
}

function saveAccounts(items: AccountItem[]) {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

function seedAccounts(): AccountItem[] {
  const today = new Date();
  const mk = (days: number) => new Date(today.getTime() + days * 86400000).toISOString().slice(0, 10);
  const items: AccountItem[] = [
    { id: "acc_1", description: "Honorários contratuais — Caso A", amount: 8000, due: mk(5), category: "Honorários", status: "receber", caseTitle: "Ação indenizatória" },
    { id: "acc_2", description: "Honorários sucumbenciais — Caso B", amount: 4500, due: mk(-2), category: "Sucumbência", status: "recebido", caseTitle: "Recurso de apelação" },
    { id: "acc_3", description: "Honorários contratuais — Caso C", amount: 12000, due: mk(15), category: "Honorários", status: "previsto", caseTitle: "Contrato empresarial" },
    { id: "acc_4", description: "Honorários de êxito — Caso D", amount: 18000, due: mk(45), category: "Êxito", status: "previsto", caseTitle: "Recoverança tributária" },
    { id: "acc_5", description: "Honorários contratuais — Caso E", amount: 3500, due: mk(-15), category: "Honorários", status: "recebido", caseTitle: "Trabalhista" },
    { id: "acc_6", description: "Consultoria — Caso F", amount: 2500, due: mk(2), category: "Consultoria", status: "receber", caseTitle: "LGPD" },
    { id: "acc_7", description: "Honorários contratuais — Caso G", amount: 6000, due: mk(8), category: "Honorários", status: "receber", caseTitle: "Família" },
    { id: "acc_8", description: "Honorários de êxito — Caso H", amount: 22000, due: mk(60), category: "Êxito", status: "previsto", caseTitle: "Recuperação judicial" },
  ];
  saveAccounts(items);
  return items;
}

export function Financeiro() {
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"todos" | "receber" | "recebido" | "previsto">("todos");

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch("/api/cases").then((r) => r.json()).then((d) => d.cases || []).catch(() => []),
      Promise.resolve(loadAccounts()),
    ]).then(([cs, accs]) => {
      if (cancelled) return;
      setCases(cs);
      setAccounts(accs);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, []);

  const kpis = useMemo(() => {
    const aReceber = accounts.filter((a) => a.status === "receber").reduce((s, a) => s + a.amount, 0);
    const recebido = accounts.filter((a) => a.status === "recebido").reduce((s, a) => s + a.amount, 0);
    const previsto = accounts.filter((a) => a.status === "previsto").reduce((s, a) => s + a.amount, 0);
    const vencidas = accounts.filter((a) => a.status === "receber" && new Date(a.due) < new Date()).length;
    return { aReceber, recebido, previsto, vencidas, total: aReceber + recebido + previsto };
  }, [accounts]);

  const filtered = useMemo(() => {
    const today = new Date();
    return accounts
      .filter((a) => filter === "todos" || a.status === filter)
      .sort((a, b) => new Date(a.due).getTime() - new Date(b.due).getTime());
  }, [accounts, filter]);

  const byCategory = useMemo(() => {
    const map: Record<string, number> = {};
    for (const a of accounts) {
      map[a.category] = (map[a.category] || 0) + a.amount;
    }
    return Object.entries(map).sort((a, b) => b[1] - a[1]);
  }, [accounts]);

  const monthlyBars = useMemo(() => {
    const months: { label: string; recebido: number; previsto: number }[] = [];
    const today = new Date();
    for (let i = 5; i >= 0; i--) {
      const d = new Date(today.getFullYear(), today.getMonth() - i, 1);
      const label = d.toLocaleDateString("pt-BR", { month: "short" });
      const recebido = accounts.filter((a) => a.status === "recebido" && new Date(a.due).getMonth() === d.getMonth() && new Date(a.due).getFullYear() === d.getFullYear()).reduce((s, a) => s + a.amount, 0);
      const previsto = accounts.filter((a) => (a.status === "previsto" || a.status === "receber") && new Date(a.due).getMonth() === d.getMonth() && new Date(a.due).getFullYear() === d.getFullYear()).reduce((s, a) => s + a.amount, 0);
      months.push({ label, recebido, previsto });
    }
    return months;
  }, [accounts]);

  const maxMonthly = Math.max(...monthlyBars.map((m) => Math.max(m.recebido, m.previsto)), 1);
  const totalCat = byCategory.reduce((s, [, v]) => s + v, 0) || 1;
  const PIE_COLORS = ["#10b981", "#f59e0b", "#06b6d4", "#a855f7", "#ec4899", "#f97316"];

  function exportCSV() {
    const headers = ["Descrição", "Valor", "Vencimento", "Categoria", "Status", "Caso"];
    const rows = filtered.map((a) => [a.description, a.amount.toFixed(2), a.due, a.category, a.status, a.caseTitle || ""]);
    const csv = [headers, ...rows].map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `juridia-financeiro-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast({ title: "CSV exportado" });
  }

  function exportPDF() {
    const win = window.open("", "_blank");
    if (!win) {
      toast({ title: "Bloqueador de pop-up", description: "Permita pop-ups para gerar o PDF", variant: "destructive" });
      return;
    }
    const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Relatório financeiro</title>
<style>body{font-family: Arial, sans-serif; padding: 40px;} h1{color: #10b981;} table{width:100%;border-collapse:collapse;margin-top:20px} th,td{border:1px solid #ccc;padding:8px;text-align:left} th{background:#f3f4f6}</style>
</head><body>
<h1>Relatório financeiro — JuridIA</h1>
<p>Emissão: ${new Date().toLocaleString("pt-BR")}</p>
<table>
<tr><th>Descrição</th><th>Valor</th><th>Vencimento</th><th>Categoria</th><th>Status</th></tr>
${filtered.map((a) => `<tr><td>${a.description}</td><td>${fmtMoeda(a.amount)}</td><td>${new Date(a.due).toLocaleDateString("pt-BR")}</td><td>${a.category}</td><td>${a.status}</td></tr>`).join("")}
</table>
<h2 style="margin-top:30px">Resumo</h2>
<p>A receber: <strong>${fmtMoeda(kpis.aReceber)}</strong></p>
<p>Recebido: <strong>${fmtMoeda(kpis.recebido)}</strong></p>
<p>Previsto: <strong>${fmtMoeda(kpis.previsto)}</strong></p>
</body></html>`;
    win.document.write(html);
    win.document.close();
    win.focus();
    setTimeout(() => { win.print(); }, 250);
  }

  if (loading) return <div className="flex h-48 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>;

  return (
    <div className="container-juridia py-8">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="mb-6 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Wallet className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">Financeiro</h1>
              <p className="text-sm text-muted-foreground">Contas a receber, recebidas e previstas — exportação CSV/PDF.</p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={exportCSV}><Download className="mr-2 h-4 w-4" /> CSV</Button>
            <Button size="sm" variant="outline" onClick={exportPDF}><FileText className="mr-2 h-4 w-4" /> PDF</Button>
          </div>
        </div>
      </motion.div>

      {/* KPIs */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { icon: Clock, label: "A receber", value: kpis.aReceber, color: "text-amber-600", bg: "bg-amber-500/10" },
          { icon: CheckCircle2, label: "Recebido", value: kpis.recebido, color: "text-emerald-600", bg: "bg-emerald-500/10" },
          { icon: TrendingUp, label: "Previsto", value: kpis.previsto, color: "text-cyan-600", bg: "bg-cyan-500/10" },
          { icon: TrendingDown, label: "Vencidas", value: kpis.vencidas, color: "text-rose-600", bg: "bg-rose-500/10", isCount: true },
        ].map((s, i) => (
          <motion.div key={s.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}>
            <Card>
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${s.bg} ${s.color}`}>
                    <s.icon className="h-4 w-4" />
                  </div>
                </div>
                <div className="mt-3 text-2xl font-bold">{s.isCount ? s.value : fmtMoeda(s.value)}</div>
                <div className="mt-0.5 text-xs text-muted-foreground">{s.label}</div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Bar chart: recebido vs previsto */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <BarChart3 className="h-4 w-4 text-primary" /> Recebido vs Previsto (6 meses)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-end gap-3 h-48">
              {monthlyBars.map((m, i) => (
                <div key={i} className="flex flex-1 flex-col items-center gap-1">
                  <div className="flex h-full w-full items-end justify-center gap-1">
                    <motion.div initial={{ height: 0 }} animate={{ height: `${(m.recebido / maxMonthly) * 100}%` }} transition={{ duration: 0.6, delay: i * 0.05 }} className="w-2.5 rounded-t bg-emerald-500" title={`Recebido: ${fmtMoeda(m.recebido)}`} />
                    <motion.div initial={{ height: 0 }} animate={{ height: `${(m.previsto / maxMonthly) * 100}%` }} transition={{ duration: 0.6, delay: i * 0.05 + 0.1 }} className="w-2.5 rounded-t bg-cyan-500" title={`Previsto: ${fmtMoeda(m.previsto)}`} />
                  </div>
                  <span className="text-[9px] text-muted-foreground">{m.label}</span>
                </div>
              ))}
            </div>
            <div className="mt-3 flex items-center justify-center gap-4 text-[10px] text-muted-foreground">
              <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-emerald-500" /> Recebido</span>
              <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-cyan-500" /> Previsto</span>
            </div>
          </CardContent>
        </Card>

        {/* Pie: por categoria */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <PieChart className="h-4 w-4 text-primary" /> Por categoria
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-4">
              {/* Pie chart SVG */}
              <svg viewBox="-1.6 -1.6 3.2 3.2" className="h-32 w-32 -rotate-90">
                {(() => {
                  const total = totalCat || 1;
                  const cumulative = byCategory.reduce<number[]>((acc, cur) => {
                    const prev = acc.length > 0 ? acc[acc.length - 1] : 0;
                    return [...acc, prev + cur[1]];
                  }, []);
                  const computed = byCategory.map(([, v], i) => {
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
                        fill={PIE_COLORS[i % PIE_COLORS.length]}
                        stroke="#fff"
                        strokeWidth="0.02"
                      />
                    );
                  });
                })()}
              </svg>
              <div className="flex-1 space-y-1.5">
                {byCategory.map(([cat, v], i) => (
                  <div key={cat} className="flex items-center justify-between gap-2 text-xs">
                    <span className="flex items-center gap-2">
                      <span className="h-2.5 w-2.5 rounded-sm" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                      <span className="font-medium">{cat}</span>
                    </span>
                    <span className="font-mono text-muted-foreground">{fmtMoeda(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabela de contas */}
      <Card className="mt-6">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-base">
              <Receipt className="h-4 w-4 text-primary" /> Contas
            </CardTitle>
            <Select value={filter} onValueChange={(v) => setFilter(v as typeof filter)}>
              <SelectTrigger className="w-[140px]"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos</SelectItem>
                <SelectItem value="receber">A receber</SelectItem>
                <SelectItem value="recebido">Recebido</SelectItem>
                <SelectItem value="previsto">Previsto</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto scrollbar-juridia">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                  <th className="py-2 pr-3">Descrição</th>
                  <th className="py-2 pr-3">Caso</th>
                  <th className="py-2 pr-3">Categoria</th>
                  <th className="py-2 pr-3">Vencimento</th>
                  <th className="py-2 pr-3">Status</th>
                  <th className="py-2 pr-3 text-right">Valor</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((a) => {
                  const isOverdue = a.status === "receber" && new Date(a.due) < new Date();
                  return (
                    <tr key={a.id} className="border-b last:border-0 hover:bg-accent/30">
                      <td className="py-2 pr-3 font-medium">{a.description}</td>
                      <td className="py-2 pr-3 text-xs text-muted-foreground">{a.caseTitle || "—"}</td>
                      <td className="py-2 pr-3 text-xs">{a.category}</td>
                      <td className="py-2 pr-3 text-xs font-mono">{new Date(a.due).toLocaleDateString("pt-BR")}</td>
                      <td className="py-2 pr-3">
                        <Badge variant="outline" className={`text-[10px] ${
                          a.status === "recebido" ? "border-emerald-500/40 text-emerald-600" :
                          a.status === "receber" ? (isOverdue ? "border-rose-500/40 text-rose-600" : "border-amber-500/40 text-amber-600") :
                          "border-cyan-500/40 text-cyan-600"
                        }`}>
                          {a.status === "recebido" ? "Recebido" : a.status === "receber" ? (isOverdue ? "Vencido" : "A receber") : "Previsto"}
                        </Badge>
                      </td>
                      <td className="py-2 pr-3 text-right font-mono font-medium">{fmtMoeda(a.amount)}</td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="border-t-2 bg-secondary/30">
                  <td colSpan={5} className="py-2 pr-3 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground">Total</td>
                  <td className="py-2 pr-3 text-right font-mono font-bold">{fmtMoeda(filtered.reduce((s, a) => s + a.amount, 0))}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
