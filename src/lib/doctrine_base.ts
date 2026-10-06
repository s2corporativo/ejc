// doctrine_base.ts — Carga e busca na base local de doutrina (LegalDoctrine).
//
// Complementa rag_lite.ts (que busca em LegalSource primária) com:
//   - súmulas numeradas
//   - enunciados
//   - temas de repercussão geral (STF)
//   - repetitivos (STJ)
//   - legislação específica (LGPD, MCI, ambiental)
//
// Implementação: TF-IDF próprio (mesma estratégia do rag_lite) por
// simplicidade e para evitar acoplar com a implementação existente.
// Em produção, substituir por pgvector ou FAISS quando o volume crescer.

import { db } from "@/lib/db";

export interface DoctrineHit {
  document_id: string;
  area: string;
  diploma: string;
  numero: string;
  tribunal: string | null;
  titulo: string;
  textoTrecho: string;
  urlOficial: string | null;
  score: number;
  matchedTerms: string[];
}

/** Tokeniza texto removendo acentos e pontuação. */
function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^\w\s]/g, " ")
    .split(/\s+/)
    .filter((w) => w.length > 2)
    .slice(0, 500);
}

/** Term frequency normalizado. */
function termFreq(tokens: string[]): Map<string, number> {
  const tf = new Map<string, number>();
  for (const t of tokens) tf.set(t, (tf.get(t) || 0) + 1);
  const total = tokens.length || 1;
  for (const [k, v] of tf) tf.set(k, v / total);
  return tf;
}

/** IDF cache (lazy) sobre todas as doutrinas ativas. */
let idfCache: Map<string, number> | null = null;
let docCountCache = 0;
let docsCache: Array<{
  id: string;
  area: string;
  diploma: string;
  numero: string;
  tribunal: string | null;
  titulo: string;
  textoTrecho: string;
  urlOficial: string | null;
  tokens: string[];
}> | null = null;

async function ensureCache(): Promise<void> {
  if (idfCache && docsCache) return;
  const sources = await db.legalDoctrine.findMany({
    where: { ativo: true },
    select: {
      id: true,
      area: true,
      diploma: true,
      numero: true,
      tribunal: true,
      titulo: true,
      textoTrecho: true,
      urlOficial: true,
    },
  });
  docsCache = sources.map((s) => {
    const combined = `${s.diploma} ${s.numero} ${s.titulo} ${s.textoTrecho}`;
    return {
      id: s.id,
      area: s.area,
      diploma: s.diploma,
      numero: s.numero,
      tribunal: s.tribunal,
      titulo: s.titulo,
      textoTrecho: s.textoTrecho,
      urlOficial: s.urlOficial,
      tokens: tokenize(combined),
    };
  });
  docCountCache = docsCache.length || 1;
  const df = new Map<string, number>();
  for (const doc of docsCache) {
    const unique = new Set(doc.tokens);
    for (const t of unique) df.set(t, (df.get(t) || 0) + 1);
  }
  idfCache = new Map();
  for (const [term, count] of df) {
    idfCache.set(term, Math.log(1 + docCountCache / count));
  }
}

/** Cosine similarity entre dois vetores TF-IDF. */
function cosine(a: Map<string, number>, b: Map<string, number>): number {
  let dot = 0;
  let na = 0;
  let nb = 0;
  for (const [k, v] of a) {
    if (v === 0) continue;
    na += v * v;
    const w = b.get(k);
    if (w) dot += v * w;
  }
  for (const [, v] of b) nb += v * v;
  if (na === 0 || nb === 0) return 0;
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}

/**
 * Busca doutrina (súmula, tema, repetitivo, lei) por similaridade TF-IDF.
 *
 * @param query texto da consulta (normalmente: fatos do caso + questões jurídicas)
 * @param areas subset de áreas a considerar (default: todas)
 * @param topK quantos resultados devolver (default 8)
 */
export async function searchDoctrine(
  query: string,
  areas?: string[],
  topK: number = 8,
): Promise<DoctrineHit[]> {
  await ensureCache();
  if (!docsCache || docsCache.length === 0) return [];

  const queryTokens = tokenize(query);
  if (queryTokens.length === 0) return [];

  // IDF ponderado pela query
  const queryTf = termFreq(queryTokens);
  const queryVec = new Map<string, number>();
  for (const [t, tf] of queryTf) {
    const idf = idfCache?.get(t) || 0;
    queryVec.set(t, tf * idf);
  }

  const hits: DoctrineHit[] = [];
  const filtered = areas && areas.length > 0 ? docsCache.filter((d) => areas.includes(d.area)) : docsCache;
  for (const doc of filtered) {
    const docTf = termFreq(doc.tokens);
    const docVec = new Map<string, number>();
    for (const [t, tf] of docTf) {
      const idf = idfCache?.get(t) || 0;
      docVec.set(t, tf * idf);
    }
    const score = cosine(queryVec, docVec);
    if (score > 0) {
      const matchedTerms = queryTokens.filter((t) => doc.tokens.includes(t)).slice(0, 5);
      hits.push({
        document_id: doc.id,
        area: doc.area,
        diploma: doc.diploma,
        numero: doc.numero,
        tribunal: doc.tribunal,
        titulo: doc.titulo,
        textoTrecho: doc.textoTrecho,
        urlOficial: doc.urlOficial,
        score,
        matchedTerms,
      });
    }
  }

  hits.sort((a, b) => b.score - a.score);
  return hits.slice(0, topK);
}

/** Formata hit em string legível para incluir no prompt. */
export function formatDoctrine(hit: DoctrineHit): string {
  const tribunal = hit.tribunal ? ` ${hit.tribunal}` : "";
  const url = hit.urlOficial ? `\nURL oficial: ${hit.urlOficial}` : "";
  return `[${hit.diploma}${tribunal} ${hit.numero}] ${hit.titulo}\n${hit.textoTrecho}${url}`;
}

/** Limpa cache (usado por scripts de seed ou atualizações). */
export function clearDoctrineCache(): void {
  idfCache = null;
  docsCache = null;
  docCountCache = 0;
}