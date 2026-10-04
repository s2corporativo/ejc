"use client";

import { useState } from "react";
import {
  Search,
  Loader2,
  ExternalLink,
  Sparkles,
  Gavel,
  FileText,
  Database,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { JurisprudenceResult } from "@/lib/types";
import { toast } from "@/hooks/use-toast";

const SUGGESTED_QUERIES = [
  "indenização por dano moral inscrição indevida em cadastro",
  "responsabilidade objetiva do fornecedor CDC",
  "tutela de urgência em ação de alimentos",
  "decadência em contrato de seguro",
  "inversão do ônus da prova consumidor hipossuficiente",
];

export function Jurisprudence() {
  const [mode, setMode] = useState<"ai" | "keyword">("ai");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<JurisprudenceResult[]>([]);
  const [cached, setCached] = useState(false);

  async function search() {
    if (!query.trim()) {
      toast({ title: "Digite uma busca", variant: "destructive" });
      return;
    }
    setLoading(true);
    setResults([]);
    try {
      const res = await fetch("/api/jurisprudence", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, mode }),
      });
      const data = await res.json();
      setResults(data.results || []);
      setCached(Boolean(data.cached));
      if ((data.results || []).length === 0) {
        toast({ title: "Nenhum resultado encontrado", variant: "destructive" });
      }
    } catch {
      toast({ title: "Erro na busca", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="container-juridia py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">
          JurisprudênciaIA — pesquisa de jurisprudência
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Descreva o caso em linguagem natural e a IA combina busca por palavra
          (BM25) e busca por significado (embeddings) para encontrar o
          precedente certo, com a ementa na íntegra.
        </p>
      </div>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Search className="h-4 w-4 text-primary" />
            Buscar jurisprudência
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <ToggleGroup
              type="single"
              value={mode}
              onValueChange={(v) => v && setMode(v as "ai" | "keyword")}
              className="rounded-lg border border-border bg-card p-1"
            >
              <ToggleGroupItem value="ai" className="gap-1.5 px-3 text-sm">
                <Sparkles className="h-3.5 w-3.5" /> Modo IA
              </ToggleGroupItem>
              <ToggleGroupItem value="keyword" className="gap-1.5 px-3 text-sm">
                <FileText className="h-3.5 w-3.5" /> Modo palavra-chave
              </ToggleGroupItem>
            </ToggleGroup>
          </div>

          {mode === "ai" ? (
            <div className="space-y-1.5">
              <Label htmlFor="q">Descreva o caso</Label>
              <Textarea
                id="q"
                rows={3}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ex: cliente foi inscrito indevidamente em órgão de proteção ao crédito após quitação..."
              />
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label htmlFor="qk">Palavras-chave</Label>
              <Input
                id="qk"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ex: dano moral inscrição indevida STJ"
              />
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {SUGGESTED_QUERIES.map((q) => (
              <button
                key={q}
                onClick={() => setQuery(q)}
                className="rounded-full border border-border bg-card px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
              >
                {q}
              </button>
            ))}
          </div>

          <Button onClick={search} disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Buscando...
              </>
            ) : (
              <>
                <Search className="mr-2 h-4 w-4" /> Pesquisar jurisprudência
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {results.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">
              {results.length} resultados
            </h2>
            {cached && (
              <Badge variant="secondary" className="gap-1">
                <Database className="h-3 w-3" /> Em cache
              </Badge>
            )}
          </div>
          <div className="space-y-3">
            {results.map((r, i) => (
              <Card key={r.url + i} className="overflow-hidden">
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                        <Gavel className="h-3 w-3" />
                        <span className="truncate font-medium">{r.host_name}</span>
                        {r.date && <span>· {r.date}</span>}
                      </div>
                      <h3 className="font-semibold leading-tight">{r.name}</h3>
                      <p className="mt-2 text-sm text-muted-foreground line-clamp-3">
                        {r.snippet}
                      </p>
                    </div>
                    <a
                      href={r.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-accent hover:text-foreground"
                      aria-label="Abrir fonte"
                    >
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
