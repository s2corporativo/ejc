// /api/sugerir-precedentes — Sugere súmulas/temas enquanto o usuário digita.
//
// Usa TF-IDF da base doctrine (LegalDoctrine) para encontrar os 5
// precedentes mais relevantes para o texto atual. Retorna em <100ms.

import { NextRequest, NextResponse } from "next/server";
import { searchDoctrine } from "@/lib/doctrine_base";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  let body: { texto: string; area?: string };
  try {
    body = (await req.json()) as { texto: string; area?: string };
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }
  if (!body.texto || body.texto.trim().length < 10) {
    return NextResponse.json({ precedents: [] });
  }
  const areas = body.area ? [body.area, "constitucional", "processo_civil"] : undefined;
  const hits = await searchDoctrine(body.texto, areas, 5);
  return NextResponse.json({
    precedents: hits.map((h) => ({
      diploma: h.diploma,
      numero: h.numero,
      titulo: h.titulo,
      trecho: h.textoTrecho.slice(0, 200),
      url: h.urlOficial,
      score: Math.round(h.score * 100) / 100,
    })),
  });
}