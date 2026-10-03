"use client";

import { useEffect, useState } from "react";
import {
  FileText,
  Loader2,
  Trash2,
  ArrowRight,
  Plus,
  Search,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { DocumentDTO } from "@/lib/types";
import { useAppStore } from "@/lib/store";
import { toast } from "@/hooks/use-toast";

export function DocumentsList() {
  const { setAppTab, setCurrentDocId } = useAppStore();
  const [docs, setDocs] = useState<DocumentDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");

  async function reload() {
    setLoading(true);
    try {
      const res = await fetch("/api/documents");
      const data = await res.json();
      setDocs(data.documents || []);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, []);

  async function remove(id: string) {
    if (!confirm("Excluir esta minuta?")) return;
    try {
      await fetch(`/api/documents?id=${id}`, { method: "DELETE" });
      setDocs((d) => d.filter((x) => x.id !== id));
      toast({ title: "Minuta excluída" });
    } catch {
      toast({ title: "Erro ao excluir", variant: "destructive" });
    }
  }

  const filtered = docs.filter(
    (d) =>
      d.title.toLowerCase().includes(filter.toLowerCase()) ||
      d.templateName.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className="container-juridia py-8">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Minutas salvas</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Todas as minutas geradas com a IA, com anonimização local.
          </p>
        </div>
        <Button onClick={() => setAppTab("generator")}>
          <Plus className="mr-2 h-4 w-4" /> Nova minuta
        </Button>
      </div>

      <div className="mb-4 relative max-w-md">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filtrar minutas..."
          className="pl-9"
        />
      </div>

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="rounded-xl border border-border bg-card p-4">
              <div className="mb-2 flex justify-between">
                <div className="h-5 w-20 animate-pulse rounded bg-muted" />
                <div className="h-5 w-16 animate-pulse rounded bg-muted" />
              </div>
              <div className="mb-2 h-5 w-3/4 animate-pulse rounded bg-muted" />
              <div className="space-y-1.5">
                <div className="h-3 w-full animate-pulse rounded bg-muted" />
                <div className="h-3 w-5/6 animate-pulse rounded bg-muted" />
                <div className="h-3 w-2/3 animate-pulse rounded bg-muted" />
              </div>
              <div className="mt-4 flex justify-between">
                <div className="h-3 w-16 animate-pulse rounded bg-muted" />
                <div className="h-6 w-16 animate-pulse rounded bg-muted" />
              </div>
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <FileText className="h-12 w-12 text-muted-foreground/40" />
            <div>
              <h3 className="font-semibold">Nenhuma minuta encontrada</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Gere sua primeira minuta para vê-la aqui.
              </p>
            </div>
            <Button onClick={() => setAppTab("generator")}>
              <Plus className="mr-2 h-4 w-4" /> Gerar minuta
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((d) => (
            <Card key={d.id} className="group flex flex-col">
              <CardContent className="flex flex-1 flex-col p-4">
                <div className="mb-2 flex items-start justify-between gap-2">
                  <Badge variant="secondary" className="text-[10px]">
                    {d.templateName}
                  </Badge>
                  <Badge variant="outline" className="text-[10px]">
                    {d.status}
                  </Badge>
                </div>
                <h3 className="font-semibold leading-tight line-clamp-2">
                  {d.title}
                </h3>
                <p className="mt-2 flex-1 text-xs text-muted-foreground line-clamp-3">
                  {d.generatedContent.slice(0, 200).replace(/[#*]/g, "")}...
                </p>
                <div className="mt-3 flex items-center justify-between">
                  <span className="text-[10px] text-muted-foreground">
                    {new Date(d.updatedAt).toLocaleDateString("pt-BR")}
                  </span>
                  <div className="flex gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => remove(d.id)}
                      aria-label="Excluir"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => {
                        setCurrentDocId(d.id);
                        setAppTab("editor");
                      }}
                    >
                      Abrir
                      <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
