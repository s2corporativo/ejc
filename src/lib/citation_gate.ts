// citation_gate.ts — Gate anti-alucinação de citações jurídicas (portado do EJC)
// Extrai citações do texto, verifica existência contra base curada, fail-closed.

export interface Citation {
  raw: string;          // texto original da citação no documento
  type: "artigo_lei" | "sumula" | "jurisprudencia" | "generica";
  diploma: string;     // CC, CPC, CLT, CP, CDC, CTN, CF, Lei X
  numero: string;       // art. 927, 308, 1.009
  tribunal?: string;    // STJ, STF, TST
  status: "verificada" | "identificada" | "suspeita" | "generica";
  source?: {
    id: string;
    textoTrecho: string;
    vigente: boolean;
    urlOficial?: string | null;
  };
  reason?: string;
}

export interface VerifyResult {
  total: number;
  verificadas: number;
  identificadas: number;
  suspeitas: number;
  genericas: number;
  bloquear: boolean; // fail-closed: bloqueia se houver suspeitas
  citations: Citation[];
}

// ── Padrões de extração de citações ──────────────────────────────────────────

// art. 927 do CC | art. 927, do Código Civil | art. 927 do CPC
const ARTIGO_RE = /\bart(?:\.|igo)?\s*(\d[\d.\-A-Zºª]*)\b,?\s*(?:do|da|do Código|da Lei)?\s*(CC|CPC|CLT|CP|CPP|CDC|CTN|CF|ECA|LC|Lei\s+\d[\d.\-]+)?/gi;

// Súmula 308 do TST | Súmula 308, do STJ | Súmula Vinculante 10
const SUMULA_RE = /\bSúmula\s+(Vinculante\s+)?(\d+),?\s*(?:do|d[oa])?\s*(STJ|STF|TST|TRF)?/gi;

// REsp 1.234.567 | AgInt 1.234.567 | RE 1.234.567 | HC 1.234.567
const JURISPRUD_RE = /\b(REsp|RE|AgInt|AgRg|HC|HD|RHC|RMS|ARE|ADI|ADO|ADC|AO|Pet)\s*(\d[\d.\-]*)/gi;

// ── Extração ──────────────────────────────────────────────────────────────────

export function extractCitations(text: string): Omit<Citation, "status" | "source" | "reason">[] {
  const found: Omit<Citation, "status" | "source" | "reason">[] = [];
  const seen = new Set<string>();

  // Artigos de lei
  let m: RegExpExecArray | null;
  ARTIGO_RE.lastIndex = 0;
  while ((m = ARTIGO_RE.exec(text)) !== null) {
    const numero = m[1].replace(/\s+/g, " ").trim();
    const diploma = (m[2] || "").trim();
    if (!numero) continue;
    const key = `artigo:${diploma}:${numero}`;
    if (seen.has(key)) continue;
    seen.add(key);
    found.push({
      raw: m[0],
      type: "artigo_lei",
      diploma: diploma || "não identificado",
      numero: `art. ${numero}`,
    });
  }

  // Súmulas
  SUMULA_RE.lastIndex = 0;
  while ((m = SUMULA_RE.exec(text)) !== null) {
    const isVinculante = Boolean(m[1]);
    const numero = m[2];
    const tribunal = (m[3] || "").trim();
    if (!numero) continue;
    const key = `sumula:${tribunal}:${numero}`;
    if (seen.has(key)) continue;
    seen.add(key);
    found.push({
      raw: m[0],
      type: "sumula",
      diploma: isVinculante ? "SV" : "Súmula",
      numero: `Súmula ${isVinculante ? "Vinculante " : ""}${numero}`,
      tribunal: tribunal || undefined,
    });
  }

  // Jurisprudência (REsp, RE, HC etc.)
  JURISPRUD_RE.lastIndex = 0;
  while ((m = JURISPRUD_RE.exec(text)) !== null) {
    const tipo = m[1];
    const numero = m[2].replace(/\.$/, "");
    if (!numero) continue;
    const key = `juris:${tipo}:${numero}`;
    if (seen.has(key)) continue;
    seen.add(key);
    // Inferir tribunal pelo tipo
    let tribunal = "STJ";
    if (tipo === "RE" || tipo === "ADI" || tipo === "ADC" || tipo === "ADO" || tipo === "AO" || tipo === "Pet") {
      tribunal = "STF";
    } else if (tipo === "HC" || tipo === "HD" || tipo === "RHC") {
      tribunal = "STJ/STF";
    }
    found.push({
      raw: m[0],
      type: "jurisprudencia",
      diploma: tipo,
      numero,
      tribunal,
    });
  }

  return found;
}

// ── Verificação contra base curada ──────────────────────────────────────────────

// Verifica citações contra a base de fontes jurídicas (passada como parâmetro)
export function verifyCitations(
  text: string,
  legalSources: {
    id: string;
    tipo: string;
    diploma: string;
    numero: string;
    tribunal: string | null;
    textoTrecho: string;
    vigente: boolean;
    urlOficial: string | null;
  }[]
): VerifyResult {
  const extracted = extractCitations(text);
  const citations: Citation[] = [];

  for (const ext of extracted) {
    const match = legalSources.find((s) => {
      if (s.tipo !== ext.type) {
        // artigo_lei pode ter tipo "artigo_lei" na base
        if (ext.type === "artigo_lei" && s.tipo !== "artigo_lei") return false;
        if (ext.type === "sumula" && s.tipo !== "sumula") return false;
        if (ext.type === "jurisprudencia" && s.tipo !== "jurisprudencia") return false;
      }
      // Comparar diploma (case-insensitive, normalizar "Lei X")
      const sDiploma = s.diploma.trim().toLowerCase();
      const extDiploma = ext.diploma.trim().toLowerCase();
      const diplomaMatch =
        sDiploma === extDiploma ||
        sDiploma.includes(extDiploma) ||
        extDiploma.includes(sDiploma) ||
        (ext.type === "artigo_lei" && sDiploma.includes("código") && extDiploma.includes("cc"));
      if (!diplomaMatch) return false;
      // Comparar número (normalizar "art. 927" vs "927")
      const sNum = s.numero.replace(/^art\.\s*/i, "").trim();
      const extNum = ext.numero.replace(/^art\.\s*/i, "").trim();
      if (sNum !== extNum) return false;
      // Comparar tribunal (se ambos tiverem)
      if (ext.tribunal && s.tribunal) {
        const sT = s.tribunal.toLowerCase();
        const eT = ext.tribunal.toLowerCase();
        if (!sT.includes(eT) && !eT.includes(sT)) return false;
      }
      return true;
    });

    if (match) {
      if (match.vigente) {
        citations.push({
          ...ext,
          status: "verificada",
          source: {
            id: match.id,
            textoTrecho: match.textoTrecho,
            vigente: match.vigente,
            urlOficial: match.urlOficial,
          },
          reason: "Fonte encontrada na base curada e vigente",
        });
      } else {
        citations.push({
          ...ext,
          status: "suspeita",
          source: {
            id: match.id,
            textoTrecho: match.textoTrecho,
            vigente: match.vigente,
            urlOficial: match.urlOficial,
          },
          reason: "Fonte encontrada na base, MAS marcada como NÃO vigente — verificar revogação",
        });
      }
    } else if (ext.type === "jurisprudencia") {
      // Jurisprudência não curada = identificada (não bloqueia, mas marca)
      citations.push({
        ...ext,
        status: "identificada",
        reason: "Jurisprudência identificada mas não consta na base curada — conferir fonte oficial",
      });
    } else if (ext.diploma === "não identificado") {
      citations.push({
        ...ext,
        status: "generica",
        reason: "Citação de artigo sem identificar o diploma legal",
      });
    } else {
      // Artigo/súmula não encontrado na base = suspeita (fail-closed)
      citations.push({
        ...ext,
        status: "suspeita",
        reason: "Citação não encontrada na base curada — pode ser alucinação ou base incompleta",
      });
    }
  }

  const verificadas = citations.filter((c) => c.status === "verificada").length;
  const identificadas = citations.filter((c) => c.status === "identificada").length;
  const suspeitas = citations.filter((c) => c.status === "suspeita").length;
  const genericas = citations.filter((c) => c.status === "generica").length;

  return {
    total: citations.length,
    verificadas,
    identificadas,
    suspeitas,
    genericas,
    bloquear: suspeitas > 0, // fail-closed: bloqueia aprovação se houver suspeitas
    citations,
  };
}

// ── Status labels ─────────────────────────────────────────────────────────────

export const STATUS_LABELS: Record<Citation["status"], { label: string; color: string; icon: string }> = {
  verificada: { label: "Verificada", color: "text-green-600 border-green-500/50", icon: "✓" },
  identificada: { label: "Identificada", color: "text-blue-600 border-blue-500/50", icon: "?" },
  suspeita: { label: "Suspeita", color: "text-red-600 border-red-500/50", icon: "⚠" },
  generica: { label: "Genérica", color: "text-amber-600 border-amber-500/50", icon: "○" },
};
