// pseudonymizer.ts — Pseudonimização REVERSÍVEL e CONSISTENTE de PII (LGPD art. 33/46)
// Portado do pseudonymizer.py do EJC para TypeScript.
//
// Diferente de anonymize.ts (mascaramento IRREVERSÍVEL), aqui cada entidade
// recebe um marcador CONSISTENTE por TIPO+ÍNDICE ([CPF_1], [CLIENTE_1]):
// a MESMA entidade vira o MESMO marcador em todo o texto.
//
// O mapa (marcador → valor real) permite REIDRATAR a resposta localmente.
// O mapa NUNCA vai ao provider, NUNCA é logado, NUNCA é persistido.

export interface PseudonymMap {
  forward: Map<string, string>; // valor real → marcador
  reverse: Map<string, string>; // marcador → valor real
}

export interface PseudonymizeResult {
  text: string;        // texto pseudonimizado (só marcadores)
  map: PseudonymMap;   // mapa para reidratação (EM MEMÓRIA, nunca logado)
  counts: Record<string, number>;
  total: number;
}

// ── Padrões de detecção (reutilizados de anonymize.ts) ──────────────────────

interface DetectionPattern {
  type: string;
  regex: RegExp;
}

const STRUCTURED_PATTERNS: DetectionPattern[] = [
  { type: "CPF", regex: /\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b/g },
  { type: "CNPJ", regex: /\b\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}\b/g },
  { type: "RG", regex: /\b(?:RG\s*)?\d{2}\.?\d{3}\.?\d{3}-?\d{1}\b/gi },
  { type: "TELEFONE", regex: /\b\(?\d{2}\)?[\s-]?\d{4,5}-?\d{4}\b/g },
  { type: "EMAIL", regex: /\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b/g },
  { type: "CEP", regex: /\b\d{5}-\d{3}\b/g },
  { type: "PIS", regex: /\b\d{3}\.\d{5}\.\d{2}-\d\b/g },
  { type: "PLACA", regex: /\b[A-Z]{3}-?\d[A-Z]\d{2}\b|\b[A-Z]{3}-?\d{4}\b/gi },
  { type: "CONTA", regex: /\b(?:conta|ag(?:ê|e)ncia)\s*:?\s*\d{3,5}-?\d\b/gi },
  { type: "VALOR", regex: /R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}|R\$\s*\d+(?:,\d{2})?/gi },
];

const NAME_REGEX = /\b([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+){1,4})\b/g;

const STOP_WORDS = new Set([
  "EXCELENTÍSSIMO", "SENHOR", "SENHORA", "JUIZ", "JUIZA", "DOUTOR", "DOUTORA",
  "DESEMBARGADOR", "DESEMBARGADORA", "MINISTRO", "MINISTRA", "MERITÍSSIMO",
  "VARA", "CÍVEL", "COMARCA", "ESTADO", "FEDERAL", "JUSTIÇA", "TRIBUNAL",
  "AUTOR", "RÉU", "AUTORA", "RÉ", "REQUERENTE", "REQUERIDO", "ADVOGADO", "ADVOGADA",
  "OAB", "ART", "CPC", "CC", "CP", "CPP", "CLT", "CTN", "CDC", "LGPD",
  "STF", "STJ", "TJ", "TRT", "TST", "TRF", "CNJ", "ABRIL", "JANEIRO",
  "FEVEREIRO", "MARÇO", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO",
  "OUTUBRO", "NOVEMBRO", "DEZEMBRO", "VEM", "DECLARO", "PEDIDO", "DIREITO",
  "BANCO", "SERASA", "SPC", "BRASIL", "SÃO", "PAULO", "RIO", "JANEIRO",
  "CONTRATO", "CLÁUSULA", "PARTES", "CONTRATANTE", "CONTRATADA",
]);

// ── Pseudonimização ──────────────────────────────────────────────────────────

/**
 * Pseudonimiza texto: substitui PII por marcadores CONSISTENTES e REVERSÍVEIS.
 * A mesma entidade sempre recebe o mesmo marcador em todo o texto.
 */
export function pseudonymize(input: string): PseudonymizeResult {
  const forward = new Map<string, string>(); // valor real → marcador
  const reverse = new Map<string, string>(); // marcador → valor real
  const counts: Record<string, number> = {};
  let text = input;

  // Helper: atribui ou reutiliza marcador consistente
  const assignMarker = (type: string, value: string): string => {
    const existing = forward.get(value);
    if (existing) return existing;

    const idx = (counts[type] || 0) + 1;
    counts[type] = idx;
    const marker = `[${type}_${idx}]`;
    forward.set(value, marker);
    reverse.set(marker, value);
    return marker;
  };

  // 1) Padrões estruturados (CPF, CNPJ, etc.) — processar por tipo, do mais específico ao mais genérico
  for (const { type, regex } of STRUCTURED_PATTERNS) {
    const re = new RegExp(regex.source, regex.flags);
    let match: RegExpExecArray | null;
    while ((match = re.exec(text)) !== null) {
      const value = match[0];
      const marker = assignMarker(type, value);
      text = text.slice(0, match.index) + marker + text.slice(match.index + value.length);
      re.lastIndex = match.index + marker.length;
    }
  }

  // 2) Nomes próprios (heurística com stop-words)
  const nameRe = new RegExp(NAME_REGEX.source, NAME_REGEX.flags);
  let nameMatch: RegExpExecArray | null;
  while ((nameMatch = nameRe.exec(text)) !== null) {
    const full = nameMatch[0];
    const firstWord = full.split(/\s+/)[0];
    if (STOP_WORDS.has(firstWord.toUpperCase())) continue;
    if (/\[[A-Z_]+\d+\]/.test(full)) continue;
    const marker = assignMarker("NOME", full);
    text = text.slice(0, nameMatch.index) + marker + text.slice(nameMatch.index + full.length);
    nameRe.lastIndex = nameMatch.index + marker.length;
  }

  return {
    text,
    map: { forward, reverse },
    counts,
    total: forward.size,
  };
}

/**
 * Reidrata texto pseudonimizado: substitui marcadores de volta aos valores reais.
 * DEVE ser executado LOCALMENTE, nunca no provider externo.
 */
export function rehydrate(text: string, map: PseudonymMap): string {
  let out = text;
  // Ordenar por comprimento descrescente para evitar colisão ([NOME_1] vs [NOME_10])
  const markers = Array.from(map.reverse.keys()).sort((a, b) => b.length - a.length);
  for (const marker of markers) {
    const value = map.reverse.get(marker);
    if (value) {
      // Escapa regex specials no marcador
      const safe = marker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      out = out.replace(new RegExp(safe, "g"), value);
    }
  }
  return out;
}

// ── Compatibilidade com anonymize.ts (mantém a interface) ────────────────────

export type MarkerMap = Record<string, string>;

export function anonymizeCompat(input: string): {
  text: string;
  markers: MarkerMap;
  counts: Record<string, number>;
  total: number;
} {
  const result = pseudonymize(input);
  const markers: MarkerMap = {};
  result.map.reverse.forEach((value, key) => {
    markers[key] = value;
  });
  return {
    text: result.text,
    markers,
    counts: result.counts,
    total: result.total,
  };
}

export function deanonymizeCompat(text: string, markers: MarkerMap): string {
  const reverse = new Map<string, string>();
  for (const [marker, value] of Object.entries(markers)) {
    reverse.set(marker, value);
  }
  return rehydrate(text, { forward: new Map(), reverse });
}
