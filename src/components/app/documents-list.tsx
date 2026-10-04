"use client";

import { useEffect, useState, useMemo } from "react";
import {
  FileText,
  Trash2,
  ArrowRight,
  Plus,
  Search,
  Star,
  Clock,
  Calendar,
  Type,
  Filter,
  AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { DocumentDTO } from "@/lib/types";
import { useAppStore } from "@/lib/store";
import { toast } from "@/hooks/use-toast";
import { motion } from "framer-motion";

type SortKey = "updated" | "created" | "title" | "size";

export function DocumentsList() {
  const { setAppTab, setCurrentDocId } = useAppStore();
  const [docs, setDocs] = useState<DocumentDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState<SortKey>("updated");
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [favorites, setFavorites] = useState<Set<string>>(() => {
    if (typeof window === "undefined") return new Set();
    try {
      const stored = localStorage.getItem("juridia-favorites");
      return new Set(stored ? JSON.parse(stored) : []);
    } catch {
      return new Set();
    }
  });

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

  function toggleFavorite(id: string) {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      try {
        localStorage.setItem("juridia-favorites", JSON.stringify([...next]));
        window.dispatchEvent(new Event("juridia-favorites-changed"));
      } catch {
        // ignore
      }
      return next;
    });
  }

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

  // Full-text search across title, template, content, skills
  const filtered = useMemo(() => {
    const q = filter.toLowerCase().trim();
    let list = docs.filter((d) => {
      if (favoritesOnly && !favorites.has(d.id)) return false;
      if (!q) return true;
      const haystack = [
        d.title,
        d.templateName,
        d.generatedContent,
        d.anonymizedFacts,
        ...(d.skillSlugs || []),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
    list = [...list].sort((a, b) => {
      switch (sort) {
        case "created":
          return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
        case "title":
          return a.title.localeCompare(b.title);
        case "size":
          return b.generatedContent.length - a.generatedContent.length;
        case "updated":
        default:
          return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime();
      }
    });
    // Favorites first when sorting by updated
    if (sort === "updated") {
      list = [...list].sort((a, b) => {
        const fa = favorites.has(a.id) ? 1 : 0;
        const fb = favorites.has(b.id) ? 1 : 0;
        if (fa !== fb) return fb - fa;
        return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime();
      });
    }
    return list;
  }, [docs, filter, favoritesOnly, favorites, sort]);

  const favCount = docs.filter((d) => favorites.has(d.id)).length;
  const totalWords = docs.reduce(
    (sum, d) => sum + d.generatedContent.split(/\s+/).filter(Boolean).length,
    0
  );

  return (
    <div className="container-juridia py-8">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Minutas salvas</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {docs.length} {docs.length === 1 ? "minuta" : "minutas"} ·{" "}
            {favCount} favorita{favCount === 1 ? "" : "s"} ·{" "}
            {totalWords.toLocaleString("pt-BR")} palavras no total
          </p>
        </div>
        <Button onClick={() => setAppTab("generator")}>
          <Plus className="mr-2 h-4 w-4" /> Nova minuta
        </Button>
      </div>

      {/* Filters bar */}
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Buscar em título, conteúdo, skills..."
            className="pl-9"
          />
          {filter && (
            <button
              onClick={() => setFilter("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              aria-label="Limpar busca"
            >
              ✕
            </button>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant={favoritesOnly ? "default" : "outline"}
            size="sm"
            onClick={() => setFavoritesOnly((v) => !v)}
            className="gap-1.5"
          >
            <Star className={`h-3.5 w-3.5 ${favoritesOnly ? "fill-current" : ""}`} />
            Favoritas
            {favCount > 0 && (
              <Badge variant={favoritesOnly ? "secondary" : "outline"} className="ml-1 h-4 px-1 text-[10px]">
                {favCount}
              </Badge>
            )}
          </Button>
          <Select value={sort} onValueChange={(v) => setSort(v as SortKey)}>
            <SelectTrigger className="w-[160px]">
              <Filter className="mr-1.5 h-3.5 w-3.5" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="updated">Mais recentes</SelectItem>
              <SelectItem value="created">Criação</SelectItem>
              <SelectItem value="title">Título (A-Z)</SelectItem>
              <SelectItem value="size">Tamanho</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {filter && (
        <div className="mb-4 flex items-center gap-2 text-xs text-muted-foreground">
          <AlertCircle className="h-3.5 w-3.5" />
          <span>
            {filtered.length} resultado{filtered.length === 1 ? "" : "s"} para &ldquo;{filter}&rdquo;
            {favoritesOnly && " (apenas favoritas)"}
          </span>
        </div>
      )}

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
              <h3 className="font-semibold">
                {filter || favoritesOnly ? "Nenhuma minuta encontrada" : "Nenhuma minuta ainda"}
              </h3>
              <p className="mt-1 text-sm text-muted-foreground">
                {filter || favoritesOnly
                  ? "Tente ajustar a busca ou limpar os filtros."
                  : "Gere sua primeira minuta para vê-la aqui."}
              </p>
            </div>
            {(filter || favoritesOnly) && (
              <Button
                variant="outline"
                onClick={() => {
                  setFilter("");
                  setFavoritesOnly(false);
                }}
              >
                Limpar filtros
              </Button>
            )}
            <Button onClick={() => setAppTab("generator")}>
              <Plus className="mr-2 h-4 w-4" /> Gerar minuta
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((d, i) => {
            const isFav = favorites.has(d.id);
            const words = d.generatedContent.split(/\s+/).filter(Boolean).length;
            const readMin = Math.max(1, Math.round(words / 200));
            return (
              <motion.div
                key={d.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, delay: Math.min(i * 0.04, 0.4) }}
              >
                <Card className="group flex h-full flex-col">
                  <CardContent className="flex flex-1 flex-col p-4">
                    <div className="mb-2 flex items-start justify-between gap-2">
                      <div className="flex flex-wrap gap-1">
                        <Badge variant="secondary" className="text-[10px]">
                          {d.templateName}
                        </Badge>
                        {isFav && (
                          <Badge variant="outline" className="gap-0.5 text-[10px] text-amber-600">
                            <Star className="h-2.5 w-2.5 fill-current" /> Favorita
                          </Badge>
                        )}
                      </div>
                      <button
                        onClick={() => toggleFavorite(d.id)}
                        className="rounded p-1 text-muted-foreground transition-colors hover:text-amber-500"
                        aria-label={isFav ? "Remover dos favoritos" : "Adicionar aos favoritos"}
                      >
                        <Star className={`h-4 w-4 ${isFav ? "fill-amber-400 text-amber-500" : ""}`} />
                      </button>
                    </div>
                    <h3 className="font-semibold leading-tight line-clamp-2">
                      {highlightMatch(d.title, filter)}
                    </h3>
                    <p className="mt-2 flex-1 text-xs text-muted-foreground line-clamp-3">
                      {highlightMatch(
                        d.generatedContent.slice(0, 220).replace(/[#*]/g, ""),
                        filter
                      )}
                      ...
                    </p>
                    <div className="mt-3 flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        {new Date(d.updatedAt).toLocaleDateString("pt-BR")}
                      </span>
                      <span className="flex items-center gap-1">
                        <Type className="h-3 w-3" />
                        {words.toLocaleString("pt-BR")} pal.
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {readMin} min
                      </span>
                    </div>
                    <div className="mt-3 flex items-center justify-end gap-1 border-t border-border pt-2">
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
                  </CardContent>
                </Card>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// Highlight search matches in text
function highlightMatch(text: string, query: string): React.ReactNode {
  if (!query.trim()) return text;
  const q = query.trim();
  const regex = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
  const parts = text.split(regex);
  return parts.map((part, i) =>
    regex.test(part) ? (
      <mark key={i} className="rounded bg-amber-300/60 px-0.5 text-foreground dark:bg-amber-600/40">
        {part}
      </mark>
    ) : (
      <span key={i}>{part}</span>
    )
  );
}
