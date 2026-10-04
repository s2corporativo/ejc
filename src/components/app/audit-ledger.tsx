"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  History,
  Wallet,
  TrendingDown,
  TrendingUp,
  ScrollText,
  Activity,
  Coins,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

interface AuditEntry {
  id: string;
  action: string;
  resource: string;
  resourceId: string | null;
  metadata: Record<string, unknown>;
  createdAt: string;
}

interface LedgerEntry {
  id: string;
  type: string;
  operation: string;
  amount: number;
  balance: number;
  reason: string;
  createdAt: string;
}

const ACTION_LABELS: Record<string, string> = {
  generate_minuta: "Geração de minuta",
  edit_document: "Edição de documento",
  delete_document: "Exclusão de documento",
  search_jurisprudence: "Busca de jurisprudência",
  anonymize: "Anonimização local",
  login: "Login",
  suggest: "Sugestão de IA",
};

export function AuditLedger() {
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [summary, setSummary] = useState<{
    currentBalance: number;
    totalDebit: number;
    totalCredit: number;
    byOperation: Record<string, { count: number; total: number }>;
  } | null>(null);

  useEffect(() => {
    fetch("/api/audit?limit=50")
      .then((r) => r.json())
      .then((d) => setAudit(d.events || []))
      .catch(() => null);
    fetch("/api/usage-ledger")
      .then((r) => r.json())
      .then((d) => {
        setLedger(d.entries || []);
        setSummary(d.summary || null);
      })
      .catch(() => null);
  }, []);

  return (
    <div className="container-juridia py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Auditoria & Créditos</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Trilha de auditoria imutável e ledger de uso de créditos — transparência
          total das operações.
        </p>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card className="border-primary/30">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Coins className="h-4 w-4" />
                </div>
                <span className="text-xs text-muted-foreground">saldo atual</span>
              </div>
              <div className="mt-3 text-3xl font-bold text-primary">
                {summary.currentBalance}
              </div>
              <div className="mt-0.5 text-xs text-muted-foreground">créditos</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-red-500/10 text-red-600">
                  <TrendingDown className="h-4 w-4" />
                </div>
                <span className="text-xs text-muted-foreground">consumidos</span>
              </div>
              <div className="mt-3 text-2xl font-bold">
                {summary.totalDebit}
              </div>
              <div className="mt-0.5 text-xs text-muted-foreground">débitos</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-green-500/10 text-green-600">
                  <TrendingUp className="h-4 w-4" />
                </div>
                <span className="text-xs text-muted-foreground">recebidos</span>
              </div>
              <div className="mt-3 text-2xl font-bold">
                {summary.totalCredit}
              </div>
              <div className="mt-0.5 text-xs text-muted-foreground">créditos</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-500/10 text-blue-600">
                  <Activity className="h-4 w-4" />
                </div>
                <span className="text-xs text-muted-foreground">operações</span>
              </div>
              <div className="mt-3 text-2xl font-bold">
                {Object.values(summary.byOperation).reduce((s, v) => s + v.count, 0)}
              </div>
              <div className="mt-0.5 text-xs text-muted-foreground">total</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Usage by operation */}
      {summary && Object.keys(summary.byOperation).length > 0 && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Activity className="h-4 w-4 text-primary" />
              Consumo por operação
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {Object.entries(summary.byOperation).map(([op, data]) => (
                <div key={op} className="rounded-lg border border-border p-3">
                  <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    {op}
                  </div>
                  <div className="mt-1 flex items-baseline justify-between">
                    <span className="text-lg font-bold">{data.count}</span>
                    <span className="text-xs text-muted-foreground">{data.total} créditos</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <Tabs defaultValue="ledger">
        <TabsList>
          <TabsTrigger value="ledger" className="gap-1.5">
            <Wallet className="h-3.5 w-3.5" /> Ledger de uso
          </TabsTrigger>
          <TabsTrigger value="audit" className="gap-1.5">
            <History className="h-3.5 w-3.5" /> Trilha de auditoria
          </TabsTrigger>
        </TabsList>

        <TabsContent value="ledger" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <ScrollText className="h-4 w-4 text-primary" />
                Ledger de uso (imutável)
                <Badge variant="outline" className="ml-auto text-[10px]">
                  {ledger.length} entradas
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {ledger.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  Nenhuma operação registrada ainda. Gere minutas para ver o consumo.
                </p>
              ) : (
                <div className="space-y-1.5">
                  {ledger.map((e, i) => (
                    <motion.div
                      key={e.id}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: Math.min(i * 0.02, 0.5) }}
                      className="flex items-center gap-3 rounded-lg border border-border p-2.5 text-xs"
                    >
                      <Badge
                        variant="outline"
                        className={`shrink-0 text-[10px] ${
                          e.type === "debit"
                            ? "border-red-500/50 text-red-600"
                            : e.type === "credit"
                            ? "border-green-500/50 text-green-600"
                            : "border-amber-500/50 text-amber-600"
                        }`}
                      >
                        {e.type === "debit" ? "−" : "+"}{Math.abs(e.amount)}
                      </Badge>
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-medium">{e.reason}</div>
                        <div className="text-[10px] text-muted-foreground">
                          {new Date(e.createdAt).toLocaleString("pt-BR")} · {e.operation}
                        </div>
                      </div>
                      <div className="shrink-0 text-right">
                        <div className="font-mono text-xs font-bold">{e.balance}</div>
                        <div className="text-[10px] text-muted-foreground">saldo</div>
                      </div>
                    </motion.div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="audit" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <History className="h-4 w-4 text-primary" />
                Eventos de auditoria (imutáveis)
                <Badge variant="outline" className="ml-auto text-[10px]">
                  {audit.length} eventos
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {audit.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  Nenhum evento registrado. Ações como gerar, editar e excluir
                  minutas serão registradas aqui.
                </p>
              ) : (
                <div className="space-y-1.5 max-h-[500px] overflow-y-auto scrollbar-juridia">
                  {audit.map((e, i) => (
                    <motion.div
                      key={e.id}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: Math.min(i * 0.01, 0.4) }}
                      className="flex items-start gap-3 rounded-lg border border-border p-2.5 text-xs"
                    >
                      <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                        <Activity className="h-3 w-3" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="font-medium">
                          {ACTION_LABELS[e.action] || e.action}
                        </div>
                        <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                          <span>{new Date(e.createdAt).toLocaleString("pt-BR")}</span>
                          <span>·</span>
                          <span className="rounded bg-secondary px-1.5 py-0.5">{e.resource}</span>
                          {e.resourceId && (
                            <>
                              <span>·</span>
                              <span className="font-mono">{e.resourceId.slice(0, 12)}…</span>
                            </>
                          )}
                        </div>
                        {Object.keys(e.metadata).length > 0 && (
                          <div className="mt-1 font-mono text-[10px] text-muted-foreground">
                            {JSON.stringify(e.metadata).slice(0, 120)}
                          </div>
                        )}
                      </div>
                    </motion.div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
