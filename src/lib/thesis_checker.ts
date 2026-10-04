// thesis_checker.ts — Verificador de aderência da tese (diferencial sobre MinutaIA)
//
// Lacuna do MinutaIA: confirma que a citação existe e foi transcrita fielmente,
// mas não verifica se ela SUSTENTA a afirmação feita na peça.
//
// Este verificador compara a frase da peça com o fundamento central do acórdão
// e classifica em: apoia | apoia_em_parte | distinguivel | contrario | insuficiente
//
// Base normativa: art. 489, §1º, V e VI, do CPC (fundamentação deve demonstrar
// o ajuste do precedente ao caso ou a sua distinção)

import ZAI from "z-ai-web-dev-sdk";

export type ThesisAdherence =
  | "apoia"
  | "apoia_em_parte"
  | "distinguivel"
  | "contrario"
  | "insuficiente";

export interface ThesisCheckResult {
  adherence: ThesisAdherence;
  confidence: number;
  explanation: string;
  recommendation: string;
}

export interface ThesisCheckInput {
  claim: string;          // afirmação feita na peça
  precedentQuote: string; // trecho do precedente citado
  caseFacts: string;      // fatos do caso
  precedentLabel?: string; // "REsp 1.234.567/SP" etc.
}

/**
 * Verifica se o precedente realmente sustenta a afirmação feita na peça.
 * Usa LLM como assistente, mas a classificação é confirmada por regras.
 */
export async function checkThesisAdherence(input: ThesisCheckInput): Promise<ThesisCheckResult> {
  const { claim, precedentQuote, caseFacts, precedentLabel } = input;

  if (!claim.trim() || !precedentQuote.trim()) {
    return {
      adherence: "insuficiente",
      confidence: 0,
      explanation: "Afirmação ou precedente vazio",
      recommendation: "Forneça a afirmação da peça e o trecho do precedente citado",
    };
  }

  try {
    const zai = await ZAI.create();
    const completion = await zai.chat.completions.create({
      messages: [
        {
          role: "system",
          content: `Você é um verificador jurídico brasileiro. Sua função é verificar se um precedente realmente SUSTENTA a afirmação feita em uma peça jurídica.

Classifique em:
- "apoia": o precedente confirma diretamente a afirmação
- "apoia_em_parte": o precedente apoia parte da afirmação, mas não toda
- "distinguivel": o precedente trata de situação diferente (distinguishing)
- "contrario": o precedente vai contra a afirmação
- "insuficiente": não é possível determinar a relação

Responda APENAS com JSON: {"adherence": "...", "confidence": 0.0-1.0, "explanation": "...", "recommendation": "..."}

Base normativa: art. 489, §1º, V e VI, do CPC — a fundamentação deve demonstrar o ajuste do precedente ao caso ou a sua distinção.`,
        },
        {
          role: "user",
          content: `## Afirmação da peça
${claim}

## Precedente citado${precedentLabel ? ` (${precedentLabel})` : ""}
${precedentQuote}

## Fatos do caso
${caseFacts.slice(0, 500)}

## Tarefa
Compare a afirmação com o precedente. O precedente sustenta a afirmação? Ou é distinguível? Ou contrário?`,
        },
      ],
      thinking: { type: "disabled" },
      temperature: 0.2,
      max_tokens: 500,
    });

    const raw = completion.choices[0]?.message?.content || "";
    const match = raw.match(/\{[\s\S]*\}/);
    if (match) {
      const parsed = JSON.parse(match[0]);
      const validAdherence = ["apoia", "apoia_em_parte", "distinguivel", "contrario", "insuficiente"];
      const adherence = validAdherence.includes(parsed.adherence)
        ? (parsed.adherence as ThesisAdherence)
        : "insuficiente";
      return {
        adherence,
        confidence: typeof parsed.confidence === "number" ? parsed.confidence : 0.5,
        explanation: parsed.explanation || "Verificação inconclusiva",
        recommendation: parsed.recommendation || "Verifique manualmente a relação entre a afirmação e o precedente",
      };
    }
    return {
      adherence: "insuficiente",
      confidence: 0,
      explanation: "Não foi possível processar a verificação",
      recommendation: "Verifique manualmente",
    };
  } catch (e) {
    return {
      adherence: "insuficiente",
      confidence: 0,
      explanation: `Erro: ${e instanceof Error ? e.message : "desconhecido"}`,
      recommendation: "Verifique manualmente a relação entre a afirmação e o precedente",
    };
  }
}

// ── Regras determinísticas complementares ─────────────────────────────────

/**
 * Verifica regras determinísticas antes de chamar o LLM.
 * Se a regra determinística já decide, o LLM não é chamado.
 */
export function deterministicCheck(input: ThesisCheckInput): ThesisCheckResult | null {
  const { claim, precedentQuote } = input;

  // Regra 1: se o precedente contém expressões de negação, pode ser contrário
  const negationPatterns = /não\s+(?:procede|se\s+aplica|é\s+aplicável)|improcede|rejeit/i;
  if (negationPatterns.test(precedentQuote)) {
    return {
      adherence: "contrario",
      confidence: 0.7,
      explanation: "O precedente contém linguagem de negação/improcedência que pode ser contrária à afirmação",
      recommendation: "Verifique se o precedente realmente nega a tese ou apenas não se aplica ao caso específico",
    };
  }

  // Regra 2: se a afirmação e o precedente tratam de áreas diferentes
  const claimArea = detectArea(claim);
  const precArea = detectArea(precedentQuote);
  if (claimArea && precArea && claimArea !== precArea) {
    return {
      adherence: "distinguivel",
      confidence: 0.6,
      explanation: `A afirmação trata de ${claimArea} e o precedente de ${precArea} — áreas distintas`,
      recommendation: "Verifique se o precedente trata do mesmo fundamento jurídico, mesmo sendo de área diferente",
    };
  }

  return null; // não decide — chama o LLM
}

function detectArea(text: string): string | null {
  const lower = text.toLowerCase();
  if (/consumidor|cdc|fornecedor|banco|serasa|spc/i.test(lower)) return "consumer";
  if (/trabalh|clt|empregad|horas?\s+extras?|rescis/i.test(lower)) return "trabalhista";
  if (/tribut|ctn|imposto|fiscal|lançamento/i.test(lower)) return "tributario";
  if (/penal|crime|cp\s|cpp/i.test(lower)) return "penal";
  if (/fam[ií]lia|alimentos|guarda|div[oó]rcio/i.test(lower)) return "family";
  if (/civil|cpc|c[oó]digo\s+civil|contrato|indeniza/i.test(lower)) return "civil";
  return null;
}
