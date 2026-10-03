"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  TrendingUp,
  FileText,
  Clock,
  Sparkles,
  Search,
  ArrowRight,
  Zap,
  Target,
  Calendar,
  Star,
  BarChart3,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { useAppStore } from "@/lib/store";
import type { DocumentDTO } from "@/lib/types";
import { useFavoritesCount } from "@/hooks/use-favorites-count";

interface Stats {
  totalUsers: number;
  totalDocuments: number;
  publicInstitutions: number;
  statesServed: number;
  lawOffices: number;
  skills: number;
  templates: number;
  searches: number;
  demo: { plan: string; minutasUsed: number; minutasLimit: number; remaining: number } | null;
}

export function Dashboard() {
  const { setAppTab, setCurrentDocId, user } = useAppStore();
  const [stats, setStats] = useState<Stats | null>(null);
  const [docs, setDocs] = useState<DocumentDTO[]>([]);

  useEffect(() => {
    fetch("/api/stats")
      .then((r) => r.json())
      .then(setStats)
      .catch(() => null);
    fetch("/api/documents")
      .then((r) => r.json())
      .then((d) => setDocs(d.documents || []))
      .catch(() => null);
  }, []);

  const usagePct = stats?.demo
    ? Math.min(100, (stats.demo.minutasUsed / stats.demo.minutasLimit) * 100)
    : 0;

  const todayDocs = docs.filter((d) => {
    const today = new Date().toDateString();
    return new Date(d.createdAt).toDateString() === today;
  });

  // Favorites count from localStorage (via useSyncExternalStore pattern)
  const favCount = useFavoritesCount(docs);

  // Template distribution for chart
  const templateStats = docs.reduce<{ name: string; count: number }[]>((acc, d) => {
    const existing = acc.find((x) => x.name === d.templateName);
    if (existing) existing.count++;
    else acc.push({ name: d.templateName, count: 1 });
    return acc;
  }, []).sort((a, b) => b.count - a.count);

  const planName = stats?.demo
    ? stats.demo.plan === "individual_2"
      ? "Individual II"
      : stats.demo.plan === "individual_1"
      ? "Individual I"
      : stats.demo.plan === "individual_3"
      ? "Individual III"
      : stats.demo.plan
    : "—";

  const quickActions = [
    { label: "Gerar nova minuta", icon: Zap, tab: "generator" as const, color: "text-primary" },
    { label: "Meus clientes", icon: Star, tab: "clients" as const, color: "text-primary" },
    { label: "Pesquisar jurisprudência", icon: Search, tab: "jurisprudence" as const, color: "text-primary" },
    { label: "Resumo do caso", icon: FileText, tab: "case-analysis" as const, color: "text-primary" },
  ];

  return (
    <div className="container-juridia py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight">
          Olá, {user?.name || "Advogado"} 👋
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Aqui está um resumo da sua atividade no JuridIA.
        </p>
      </div>

      {/* Resumo do escritório */}
      <Card className="mb-6 overflow-hidden border-primary/20">
        <div className="relative">
          <div className="absolute inset-0 bg-gradient-to-r from-primary/5 to-accent/10" />
          <CardContent className="relative p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <Badge variant="secondary" className="gap-1">
                  <Sparkles className="h-3 w-3" /> Assistente jurídico ativo
                </Badge>
                <h2 className="mt-3 text-lg font-semibold">Bem-vindo de volta</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {stats?.demo?.minutasUsed || 0} minutas geradas ·{" "}
                  {stats?.templates || 0} templates · {stats?.skills || 0} habilidades
                </p>
                <div className="mt-3 max-w-md">
                  <Progress value={Math.min(100, ((stats?.demo?.minutasUsed || 0) / 200) * 100)} className="h-2" />
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    {200 - (stats?.demo?.minutasUsed || 0)} gerações restantes neste ciclo
                  </p>
                </div>
              </div>
              <div className="flex flex-col items-center gap-1">
                <div className="text-4xl font-bold tracking-tight text-primary">
                  {stats?.demo?.minutasUsed || 0}
                </div>
                <div className="text-xs text-muted-foreground">minutas geradas</div>
              </div>
            </div>
          </CardContent>
        </div>
      </Card>

      {/* Stats grid */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { icon: FileText, label: "Minutas salvas", value: docs.length, sub: `${todayDocs.length} hoje` },
          { icon: Star, label: "Favoritas", value: favCount, sub: "marcadas" },
          { icon: Search, label: "Buscas de jurisprudência", value: stats?.searches || 0, sub: "acumulado" },
          { icon: Sparkles, label: "Habilidades ativas", value: stats?.skills || 0, sub: "skills" },
        ].map((s, i) => (
          <motion.div
            key={s.label}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: i * 0.06 }}
          >
            <Card>
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <s.icon className="h-4 w-4" />
                  </div>
                  <span className="text-xs text-muted-foreground">{s.sub}</span>
                </div>
                <div className="mt-3 text-2xl font-bold">{s.value}</div>
                <div className="mt-0.5 text-xs text-muted-foreground">{s.label}</div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* Activity chart by template */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <BarChart3 className="h-4 w-4 text-primary" />
            Minutas por template
          </CardTitle>
        </CardHeader>
        <CardContent>
          {templateStats.length === 0 ? (
            <div className="py-6 text-center text-sm text-muted-foreground">
              Gere minutas para ver sua distribuição por template.
            </div>
          ) : (
            <div className="space-y-3">
              {templateStats.map((t) => {
                const max = Math.max(...templateStats.map((x) => x.count));
                const pct = max > 0 ? (t.count / max) * 100 : 0;
                return (
                  <div key={t.name} className="flex items-center gap-3">
                    <div className="w-32 shrink-0 truncate text-xs font-medium">
                      {t.name}
                    </div>
                    <div className="relative h-6 flex-1 overflow-hidden rounded-md bg-secondary">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${pct}%` }}
                        transition={{ duration: 0.6, ease: "easeOut" }}
                        className="absolute inset-y-0 left-0 rounded-md bg-gradient-to-r from-primary/70 to-primary"
                      />
                      <span className="absolute inset-0 flex items-center justify-end pr-2 text-xs font-medium text-primary-foreground/90">
                        {t.count}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Quick actions */}
      <div className="mb-6">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Ações rápidas
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {quickActions.map((a, i) => (
            <motion.button
              key={a.label}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.3, delay: i * 0.05 }}
              onClick={() => setAppTab(a.tab)}
              className="group flex items-center gap-3 rounded-xl border border-border bg-card p-4 text-left transition-all hover:border-primary/40 hover:shadow-md"
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-secondary text-muted-foreground transition-colors group-hover:bg-primary/10 group-hover:text-primary">
                <a.icon className="h-5 w-5" />
              </div>
              <span className="flex-1 text-sm font-medium">{a.label}</span>
              <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
            </motion.button>
          ))}
        </div>
      </div>

      {/* Recent activity */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Clock className="h-4 w-4 text-primary" />
              Atividade recente
            </CardTitle>
          </CardHeader>
          <CardContent>
            {docs.length === 0 ? (
              <div className="py-8 text-center text-sm text-muted-foreground">
                <FileText className="mx-auto mb-2 h-8 w-8 opacity-30" />
                Nenhuma minuta gerada ainda.
                <Button
                  size="sm"
                  className="mt-3"
                  onClick={() => setAppTab("generator")}
                >
                  Gerar primeira minuta
                </Button>
              </div>
            ) : (
              <div className="space-y-2">
                {docs.slice(0, 6).map((d) => (
                  <button
                    key={d.id}
                    onClick={() => {
                      setCurrentDocId(d.id);
                      setAppTab("editor");
                    }}
                    className="flex w-full items-center gap-3 rounded-lg border border-border p-3 text-left transition-colors hover:bg-accent/40"
                  >
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                      <FileText className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">{d.title}</div>
                      <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                        <Calendar className="h-3 w-3" />
                        {new Date(d.createdAt).toLocaleDateString("pt-BR", {
                          day: "2-digit",
                          month: "short",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </div>
                    </div>
                    <Badge variant="outline" className="shrink-0 text-[10px]">
                      {d.templateName}
                    </Badge>
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <TrendingUp className="h-4 w-4 text-primary" />
              Produtividade do escritório
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="rounded-lg border border-border p-3">
                <div className="text-xl font-bold">{docs.length}</div>
                <div className="text-[11px] text-muted-foreground">minutas no total</div>
              </div>
              <div className="rounded-lg border border-border p-3">
                <div className="text-xl font-bold">{todayDocs.length}</div>
                <div className="text-[11px] text-muted-foreground">hoje</div>
              </div>
              <div className="rounded-lg border border-border p-3">
                <div className="text-xl font-bold">{favCount}</div>
                <div className="text-[11px] text-muted-foreground">favoritas</div>
              </div>
            </div>
            <div className="rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground">
              <Zap className="mb-1 inline h-3.5 w-3.5 text-primary" />{" "}
              <strong className="text-foreground">Dica:</strong> use{" "}
              <kbd className="rounded border border-border bg-muted px-1 font-mono text-[10px]">⌘K</kbd>{" "}
              para abrir a paleta de comandos e navegar rápido entre as seções.
              Atalhos de tecla única:{" "}
              <kbd className="rounded border border-border bg-muted px-1 font-mono text-[10px]">C</kbd>{" "}
              clientes,{" "}
              <kbd className="rounded border border-border bg-muted px-1 font-mono text-[10px]">G</kbd>{" "}
              gerar,{" "}
              <kbd className="rounded border border-border bg-muted px-1 font-mono text-[10px]">J</kbd>{" "}
              jurisprudência.
            </div>
            <div className="rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground">
              <Sparkles className="mb-1 inline h-3.5 w-3.5 text-primary" />{" "}
              <strong className="text-foreground">Fluxo recomendado:</strong>{" "}
              cadastre o cliente na aba Clientes → crie um caso → gere a minuta
              vinculada → revise no editor → exporte em PDF/DOC.
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
