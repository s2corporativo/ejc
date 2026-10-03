"use client";

import { useEffect, useState } from "react";
import {
  Layers,
  Loader2,
  Play,
  CheckCircle2,
  FileText,
  ArrowRight,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { DocumentDTO } from "@/lib/types";
import { useAppStore } from "@/lib/store";
import { toast } from "@/hooks/use-toast";

interface BatchItem {
  id: string;
  caseLabel: string;
  autor: string;
  reu: string;
  valor: string;
  status: "pending" | "approved" | "running" | "done" | "error";
  docId?: string;
}

export function Batch() {
  const { setAppTab, setCurrentDocId } = useAppStore();
  const [items, setItems] = useState<BatchItem[]>([
    { id: "1", caseLabel: "Processo 0001", autor: "João Silva", reu: "Banco XYZ", valor: "R$ 10.000,00", status: "pending" },
    { id: "2", caseLabel: "Processo 0002", autor: "Maria Santos", reu: "Banco XYZ", valor: "R$ 12.000,00", status: "pending" },
    { id: "3", caseLabel: "Processo 0003", autor: "Pedro Alves", reu: "Banco XYZ", valor: "R$ 15.000,00", status: "pending" },
  ]);
  const [templateSlug, setTemplateSlug] = useState("peticao-inicial-civil");
  const [templates, setTemplates] = useState<{ slug: string; name: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    fetch("/api/templates")
      .then((r) => r.json())
      .then((d) => setTemplates((d.templates || []).map((t: { slug: string; name: string }) => ({ slug: t.slug, name: t.name }))))
      .catch(() => null);
  }, []);

  function addRow() {
    const id = String(Date.now());
    setItems((s) => [
      ...s,
      {
        id,
        caseLabel: `Processo ${String(s.length + 1).padStart(4, "0")}`,
        autor: "",
        reu: "",
        valor: "",
        status: "pending",
      },
    ]);
  }

  function update(id: string, patch: Partial<BatchItem>) {
    setItems((s) => s.map((it) => (it.id === id ? { ...it, ...patch } : it)));
  }

  function remove(id: string) {
    setItems((s) => s.filter((it) => it.id !== id));
  }

  async function approveFirstThenRun() {
    const first = items.find((i) => i.status === "pending");
    if (!first) {
      toast({ title: "Adicione casos ao lote", variant: "destructive" });
      return;
    }
    if (!first.autor || !first.reu) {
      toast({
        title: "Preencha autor e réu no primeiro caso",
        variant: "destructive",
      });
      return;
    }
    setLoading(true);
    setProgress(5);

    // 1) Gera a primeira minuta (modelo)
    update(first.id, { status: "running" });
    setProgress(15);
    try {
      const res = await fetch("/api/generate-minuta", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          templateSlug,
          fields: {
            tipoAcao: "Indenização por danos morais",
            competencia: "1ª Vara Cível",
            autor: first.autor,
            reu: first.reu,
            fatos: `O autor foi vítima de conduta ilícita por parte do réu, gerando dano moral. Valor da causa: ${first.valor}`,
            pedidos: "Procedência da ação com condenação em danos morais",
            valorCausa: first.valor,
          },
          skillSlugs: [],
          title: `${first.caseLabel} — Ação Indenizatória`,
          batchId: "batch-" + Date.now(),
        }),
      });
      const data = await res.json();
      update(first.id, { status: "approved", docId: data.document.id });
      setProgress(35);

      // 2) Gera as demais seguindo o modelo
      const others = items.filter((i) => i.id !== first.id && i.status === "pending");
      for (let i = 0; i < others.length; i++) {
        const it = others[i];
        if (!it.autor || !it.reu) continue;
        update(it.id, { status: "running" });
        const p = 35 + Math.round(((i + 1) / others.length) * 60);
        setProgress(p);
        try {
          const res2 = await fetch("/api/generate-minuta", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              templateSlug,
              fields: {
                tipoAcao: "Indenização por danos morais",
                competencia: "1ª Vara Cível",
                autor: it.autor,
                reu: it.reu,
                fatos: `O autor foi vítima de conduta ilícita por parte do réu, gerando dano moral. Valor da causa: ${it.valor}`,
                pedidos: "Procedência da ação com condenação em danos morais",
                valorCausa: it.valor,
              },
              skillSlugs: [],
              title: `${it.caseLabel} — Ação Indenizatória`,
              batchId: "batch-" + Date.now(),
            }),
          });
          const d2 = await res2.json();
          update(it.id, { status: "done", docId: d2.document.id });
        } catch {
          update(it.id, { status: "error" });
        }
      }
      setProgress(100);
      toast({
        title: "Lote concluído",
        description: `${items.length} minutas geradas com o estilo do primeiro modelo.`,
      });
    } catch (e) {
      toast({ title: "Erro ao gerar lote", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }

  const doneCount = items.filter((i) => i.status === "approved" || i.status === "done").length;

  return (
    <div className="container-juridia py-8">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Geração em lote</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Geração em etapas: aprove a primeira minuta do lote e saiba como
            serão todas as outras.
          </p>
        </div>
        <Badge variant="secondary" className="gap-1">
          <Layers className="h-3 w-3" /> {items.length} casos · {doneCount} prontas
        </Badge>
      </div>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-base">Template do lote</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {templates.map((t) => (
              <button
                key={t.slug}
                onClick={() => setTemplateSlug(t.slug)}
                className={`rounded-lg border px-3 py-1.5 text-sm transition-all ${
                  templateSlug === t.slug
                    ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                    : "border-border bg-card hover:border-primary/40"
                }`}
              >
                {t.name}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {loading && (
        <Card className="mb-6">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
              Gerando lote... {progress}%
            </div>
            <Progress value={progress} className="mt-3" />
            <p className="mt-2 text-xs text-muted-foreground">
              A IA gera primeiro a minuta modelo, você aprova, e ela replica o
              estilo para os demais casos.
            </p>
          </CardContent>
        </Card>
      )}

      <div className="space-y-3">
        {items.map((it) => (
          <Card key={it.id} className="overflow-hidden">
            <CardContent className="grid gap-3 p-4 md:grid-cols-[1.5fr_1.5fr_1fr_auto_auto] md:items-center">
              <div>
                <Label className="text-xs text-muted-foreground">Caso</Label>
                <Input
                  value={it.caseLabel}
                  onChange={(e) => update(it.id, { caseLabel: e.target.value })}
                  className="mt-0.5"
                  disabled={it.status !== "pending"}
                />
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Autor (anonimizado)</Label>
                <Input
                  value={it.autor}
                  onChange={(e) => update(it.id, { autor: e.target.value })}
                  className="mt-0.5"
                  placeholder="Nome do autor"
                  disabled={it.status !== "pending"}
                />
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Réu (anonimizado)</Label>
                <Input
                  value={it.reu}
                  onChange={(e) => update(it.id, { reu: e.target.value })}
                  className="mt-0.5"
                  placeholder="Nome do réu"
                  disabled={it.status !== "pending"}
                />
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Valor</Label>
                <Input
                  value={it.valor}
                  onChange={(e) => update(it.id, { valor: e.target.value })}
                  className="mt-0.5"
                  placeholder="R$ 0.000,00"
                  disabled={it.status !== "pending"}
                />
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge status={it.status} />
                {it.docId && (
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label="Abrir minuta"
                    onClick={() => {
                      setCurrentDocId(it.docId!);
                      setAppTab("editor");
                    }}
                  >
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                )}
                {it.status === "pending" && items.length > 1 && (
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label="Remover"
                    onClick={() => remove(it.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <Button variant="outline" onClick={addRow} disabled={loading}>
          <FileText className="mr-2 h-4 w-4" /> Adicionar caso
        </Button>
        <Button onClick={approveFirstThenRun} disabled={loading}>
          {loading ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Play className="mr-2 h-4 w-4" />
          )}
          Gerar lote
        </Button>
      </div>

      {doneCount > 0 && (
        <Card className="mt-6 bg-primary/5">
          <CardContent className="flex items-center gap-3 p-4">
            <CheckCircle2 className="h-5 w-5 text-primary" />
            <div className="text-sm">
              <strong>Lote gerado.</strong> Abra cada minuta no editor para
              revisar — a estrutura, tese, jurisprudência e estilo foram
              herdadas do caso modelo.
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: BatchItem["status"] }) {
  const map: Record<BatchItem["status"], { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
    pending: { label: "Pendente", variant: "outline" },
    approved: { label: "Aprovado", variant: "default" },
    running: { label: "Gerando...", variant: "secondary" },
    done: { label: "Concluído", variant: "default" },
    error: { label: "Erro", variant: "destructive" },
  };
  const c = map[status];
  return <Badge variant={c.variant} className="text-[10px]">{c.label}</Badge>;
}
