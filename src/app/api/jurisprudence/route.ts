import { NextRequest, NextResponse } from "next/server";
import ZAI from "z-ai-web-dev-sdk";
import { db } from "@/lib/db";
import type { JurisprudenceResponse, JurisprudenceResult } from "@/lib/types";

export const dynamic = "force-dynamic";

// Cache em memória (1h) — não usa middleware externo
const cache = new Map<string, { data: JurisprudenceResult[]; ts: number }>();
const TTL = 60 * 60 * 1000;

export async function POST(req: NextRequest) {
  let body: { query?: string; mode?: string } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }
  const query = (body.query || "").trim();
  const mode = body.mode === "keyword" ? "keyword" : "ai";
  if (!query) {
    return NextResponse.json({ error: "Query obrigatória" }, { status: 400 });
  }

  const cacheKey = `${mode}:${query.toLowerCase()}`;
  const cached = cache.get(cacheKey);
  if (cached && Date.now() - cached.ts < TTL) {
    return NextResponse.json({
      query,
      mode,
      results: cached.data,
      cached: true,
    } as JurisprudenceResponse);
  }

  try {
    const zai = await ZAI.create();
    // Modo IA: descrição em linguagem natural + jurisprudência
    // Modo keyword: termos diretos
    const searchQuery =
      mode === "ai"
        ? `jurisprudência STJ STF ${query} ementa precedente`
        : `jurisprudência ${query}`;
    const raw = (await zai.functions.invoke("web_search", {
      query: searchQuery,
      num: 12,
    })) as unknown as JurisprudenceResult[];

    const results: JurisprudenceResult[] = Array.isArray(raw)
      ? raw.slice(0, 12).map((r, i) => ({
          url: r.url,
          name: r.name,
          snippet: r.snippet,
          host_name: r.host_name,
          rank: i + 1,
          date: r.date,
        }))
      : [];

    cache.set(cacheKey, { data: results, ts: Date.now() });

    // Persiste a busca (sem userId anônimo é null)
    try {
      await db.jurisprudenceSearch.create({
        data: {
          query,
          mode,
          results: JSON.stringify(results),
        },
      });
    } catch {
      // não bloquear fluxo se falhar a persistência
    }

    return NextResponse.json({
      query,
      mode,
      results,
      cached: false,
    } as JurisprudenceResponse);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Erro desconhecido";
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
