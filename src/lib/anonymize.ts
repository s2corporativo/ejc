// Utilitário de anonimização local "tarja-1"
// Detecta dados sensíveis no texto e substitui por marcadores [TIPO_0001]
// antes de qualquer conteúdo sair do computador do usuário.
// A desanonimização (restauração) também é local.

export type MarkerMap = Record<string, string>; // marcador -> valor original

export interface AnonymizeResult {
  text: string;          // texto com marcadores
  markers: MarkerMap;    // mapa marcador -> valor original
  counts: Record<string, number>;
  total: number;
}

// Padrões de detecção — dados sensíveis típicos de autos jurídicos brasileiros
const PATTERNS: { type: string; regex: RegExp }[] = [
  // CPF: 000.000.000-00 ou 00000000000
  { type: "CPF", regex: /\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b/g },
  // CNPJ: 00.000.000/0000-00
  { type: "CNPJ", regex: /\b\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}\b/g },
  // RG (comum): RG 00.000.000-0 ou RG 00.000.000
  { type: "RG", regex: /\b(?:RG\s*)?\d{2}\.?\d{3}\.?\d{3}-?\d{1}\b/gi },
  // Telefone: (11) 99999-9999 ou 11 99999-9999
  { type: "TELEFONE", regex: /\b\(?\d{2}\)?[\s-]?\d{4,5}-?\d{4}\b/g },
  // E-mail
  { type: "EMAIL", regex: /\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b/g },
  // CEP: 00000-000
  { type: "CEP", regex: /\b\d{5}-\d{3}\b/g },
  // PIS/PASEP: 000.00000.00-0
  { type: "PIS", regex: /\b\d{3}\.\d{5}\.\d{2}-\d\b/g },
  // Placa de veículo (Mercosul e antiga)
  { type: "PLACA", regex: /\b[A-Z]{3}-?\d[A-Z]\d{2}\b|\b[A-Z]{3}-?\d{4}\b/gi },
  // Conta bancária (ex: 12345-6, agência 1234-5)
  { type: "CONTA", regex: /\b(?:conta|ag(?:ê|e)ncia)\s*:?\s*\d{3,5}-?\d\b/gi },
  // Valor monetário R$ 1.234,56 / R$ 1234,56
  { type: "VALOR", regex: /R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}|R\$\s*\d+(?:,\d{2})?/gi },
];

// Nomes próprios: detecta palavras capitalizadas seguidas de espaço e outra capitalizada
// (heurística simples para nomes compostos brasileiros)
// Não aplica se a palavra está sozinha, ou em lista de stop-words (ex.: EXCELENTÍSSIMO, SENHOR, JUIZ)
const STOP_WORDS = new Set([
  "EXCELENTÍSSIMO", "SENHOR", "SENHORA", "JUIZ", "JUIZA", "DOUTOR", "DOUTORA",
  "DESEMBARGADOR", "DESEMBARGADORA", "MINISTRO", "MINISTRA", "MERITÍSSIMO",
  "VARA", "CÍVEL", "COMARCA", "ESTADO", "FEDERAL", "JUSTIÇA", "TRIBUNAL",
  "AUTOR", "RÉU", "AUTORA", "RÉ", "REQUERENTE", "REQUERIDO", "ADVOGADO", "ADVOGADA",
  "OAB", "ART", "CPC", "CC", "CP", "CPP", "CLT", "CTN", "CDC", "LGPD",
  "STF", "STJ", "TJ", "TRT", "TST", "TRF", "CNJ", "ABRIL", "JANEIRO",
  "FEVEREIRO", "MARÇO", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO",
  "OUTUBRO", "NOVEMBRO", "DEZEMBRO", "VEM", "DECLARO", "PEDIDO", "DIREITO",
]);

const NAME_REGEX = /\b([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+){1,4})\b/g;

export function anonymize(input: string): AnonymizeResult {
  const markers: MarkerMap = {};
  const counts: Record<string, number> = {};
  let text = input;
  const usedValues = new Set<string>();

  const makeMarker = (type: string, value: string): string => {
    if (usedValues.has(value)) {
      // Já marcado — achar marcador existente
      for (const [m, v] of Object.entries(markers)) {
        if (v === value) return m;
      }
    }
    const idx = (counts[type] || 0) + 1;
    counts[type] = idx;
    const marker = `[${type}_${String(idx).padStart(4, "0")}]`;
    markers[marker] = value;
    usedValues.add(value);
    return marker;
  };

  // 1) Padrões estruturados primeiro (mais confiáveis)
  for (const { type, regex } of PATTERNS) {
    text = text.replace(regex, (match) => makeMarker(type, match));
  }

  // 2) Nomes próprios (heurística) — só se não englobar marcador
  let nameMatch: RegExpExecArray | null;
  NAME_REGEX.lastIndex = 0;
  const nameRe = new RegExp(NAME_REGEX);
  while ((nameMatch = nameRe.exec(text)) !== null) {
    const full = nameMatch[0];
    const firstWord = full.split(/\s+/)[0];
    if (STOP_WORDS.has(firstWord.toUpperCase())) continue;
    // não marque se contém marcador
    if (/\[[A-Z_]+\d+\]/.test(full)) continue;
    const marker = makeMarker("NOME", full);
    text = text.replace(full, marker);
    nameRe.lastIndex = 0; // recomeça após substituição
  }

  return {
    text,
    markers,
    counts,
    total: Object.keys(markers).length,
  };
}

// Restauração local: substitui [TIPO_0001] de volta ao valor original
export function deanonymize(text: string, markers: MarkerMap): string {
  let out = text;
  // ordenar por comprimento desc para evitar colisão [NOME_0001] vs [NOME_0002]
  const keys = Object.keys(markers).sort((a, b) => b.length - a.length);
  for (const key of keys) {
    const val = markers[key];
    // escapa regex specials
    const safe = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    out = out.replace(new RegExp(safe, "g"), val);
  }
  return out;
}

// Detecção resumida (sem substituir) para mostrar contagem
export function detect(input: string): { type: string; count: number; sample: string }[] {
  const found: { type: string; count: number; sample: string }[] = [];
  for (const { type, regex } of PATTERNS) {
    const matches = input.match(regex) || [];
    if (matches.length) {
      found.push({ type, count: matches.length, sample: matches[0] });
    }
  }
  const names = input.match(NAME_REGEX) || [];
  const filteredNames = names.filter((n) => !STOP_WORDS.has(n.split(/\s+/)[0].toUpperCase()));
  if (filteredNames.length) {
    found.push({ type: "NOME", count: filteredNames.length, sample: filteredNames[0] });
  }
  return found;
}
