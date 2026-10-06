// websearch_live.ts — Wrapper de z-ai-web-dev-sdk com cache em LegalSearchCache.
//
// Para jurisprudência recente (últimos 24 meses), súmulas novas e legislação
// recém-editada. Cache em SQLite por 7 dias para evitar custo repetido.
// Resultados sempre marcados como verified=false — Citation Gate pode
// confirmar posteriormente contra a base curada.

import ZAI from "z-ai-web-dev-sdk";
import { db } from "@/lib/db";

const CACHE_TTL_DAYS = 7;

export interface WebResult {
  name: string;
  title?: string;
  url: string;
  snippet: string;
  host_name: string;
  source: "web_search_cache" | "web_search_fresh";
}

export interface WebSearchOptions {
  query: string;
  area?: string;
  num?: number;
  forceRefresh?: boolean;
}

/**
 * Pesquisa na web com cache automático. Se a mesma query foi feita nos
 * últimos 7 dias, retorna o resultado cacheado. Caso contrário, executa
 * web_search via z-ai-web-dev-sdk e persiste.
 *
 * @param options.query termo de busca (será encodado como "jurisprudência + query + área")
 * @param options.area área jurídica (penal, civil, etc.) para enriquecer a query
 * @param options.num quantidade máxima (default 8)
 * @param options.forceRefresh ignora cache e força nova busca
 */
export async function webSearchCached(options: WebSearchOptions): Promise<WebResult[]> {
  const { query, area, num = 8, forceRefresh = false } = options;
  const normalizedQuery = query.trim().toLowerCase();
  if (normalizedQuery.length < 3) return [];

  // 1) Verifica cache
  if (!forceRefresh) {
    const cached = await db.legalSearchCache.findUnique({ where: { query: normalizedQuery } });
    if (cached && cached.expiresAt > new Date()) {
      try {
        const results = JSON.parse(cached.results) as Omit<WebResult, "source">[];
        return results.map((r) => ({ ...r, source: "web_search_cache" as const }));
      } catch {
        // cache corrompido — ignora e refaz
      }
    }
  }

  // 2) Executa web_search
  const zai = await ZAI.create();
  const enrichedQuery = area ? `jurisprudência ${area} ${query}` : `jurisprudência ${query}`;
  let results: WebResult[] = [];
  try {
    const raw = (await zai.functions.invoke("web_search", {
      query: enrichedQuery,
      num,
    })) as unknown as Array<{ name?: string; title?: string; url: string; snippet: string; host_name?: string }>;
    results = (Array.isArray(raw) ? raw : []).map((r) => ({
      name: r.name || r.title || "Resultado",
      title: r.title,
      url: r.url,
      snippet: r.snippet || "",
      host_name: r.host_name || safeHostname(r.url),
      source: "web_search_fresh" as const,
    }));
  } catch {
    // Falha do web_search — retorna lista vazia
    results = [];
  }

  // 3) Persiste em cache (mesmo se vazio, para evitar retry imediato)
  const expiresAt = new Date(Date.now() + CACHE_TTL_DAYS * 24 * 60 * 60 * 1000);
  try {
    await db.legalSearchCache.upsert({
      where: { query: normalizedQuery },
      create: { query: normalizedQuery, area: area ?? null, results: JSON.stringify(results), expiresAt },
      update: { results: JSON.stringify(results), fetchedAt: new Date(), expiresAt },
    });
  } catch {
    // se persistência falhar, não bloqueia o uso
  }

  return results;
}

function safeHostname(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return "desconhecido";
  }
}

/** Limpa entradas expiradas do cache (manutenção). */
export async function purgeExpiredCache(): Promise<number> {
  const result = await db.legalSearchCache.deleteMany({
    where: { expiresAt: { lt: new Date() } },
  });
  return result.count;
}
