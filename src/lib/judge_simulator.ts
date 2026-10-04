// judge_simulator.ts — Simulação do julgador (diferencial sobre MinutaIA)
//
// Lacuna do MinutaIA: simula o ADVERSÁRIO (peça contrária), não o JULGADOR.
// Este módulo simula o julgador: verifica admissibilidade e mérito ANTES do protocolo.
//
// Base normativa:
// - Competência: art. 42-62 do CPC
// - Legitimidade: art. 17 do CPC (partes e interessados)
// - Interesse processual: art. 17, §1º do CPC
// - Condições da ação: art. 17 + art. 325 do CPC
// - Valor da causa: art. 291-294 do CPC
// - Prescrição: art. 337, §1º do CPC (preliminar)
// - Preliminares: art. 337 do CPC (inciso I a XIV)
// - Indeferimento da inicial: art. 330 do CPC
// - Conclusão/sentença: art. 489 do CPC

import ZAI from "z-ai-web-dev-sdk";

export interface JudgeSimulationResult {
  admissibilidade: {
    competencia: { status: "ok" | "risco" | "erro"; detail: string };
    legitimidade: { status: "ok" | "risco" | "erro"; detail: string };
    interesse: { status: "ok" | "risco" | "erro"; detail: string };
    valorCausa: { status: "ok" | "risco" | "erro"; detail: string };
    prescricao: { status: "ok" | "risco" | "erro"; detail: string };
    preliminares: { status: "ok" | "risco" | "erro"; detail: string };
  };
  merito: {
    probabilidade: "alta" | "media" | "baixa";
    pontos_fortes: string[];
    pontos_fracos: string[];
    fundamentos_necessarios: string[];
    provas_essenciais: string[];
  };
  recomendacao: string;
  risks: string[];
}

/**
 * Simula o julgador: verifica admissibilidade e mérito da peça.
 * Diferencial: MinutaIA só simula o adversário, não o juiz.
 */
export async function simulateJudge(params: {
  caseFacts: string;
  claim: string;
  area: string;
  valorCausa?: string;
  documentoTexto?: string;
}): Promise<JudgeSimulationResult> {
  const { caseFacts, claim, area, valorCausa, documentoTexto } = params;

  // ── Verificações determinísticas primeiro ──────────────────────────────
  const admissibilidade: JudgeSimulationResult["admissibilidade"] = {
    competencia: checkDeterministic("competencia", caseFacts),
    legitimidade: checkDeterministic("legitimidade", caseFacts),
    interesse: checkDeterministic("interesse", caseFacts),
    valorCausa: valorCausa
      ? { status: "ok", detail: `Valor informado: ${valorCausa}` }
      : { status: "risco", detail: "Valor da causa não informado" },
    prescricao: { status: "risco", detail: "Verificar prescrição com calculadora determinística" },
    preliminares: { status: "ok", detail: "Sem preliminares aparentes (verificar art. 337 CPC)" },
  };

  // ── Análise de mérito via LLM ──────────────────────────────────────────
  try {
    const zai = await ZAI.create();
    const completion = await zai.chat.completions.create({
      messages: [
        {
          role: "system",
          content: `Você é um juiz brasileiro simulando o julgamento de uma ação antes do protocolo. Sua função é identificar riscos de admissibilidade e mérito.

Responda APENAS com JSON:
{
  "probabilidade": "alta|media|baixa",
  "pontos_fortes": ["..."],
  "pontos_fracos": ["..."],
  "fundamentos_necessarios": ["..."],
  "provas_essenciais": ["..."],
  "recomendacao": "...",
  "risks": ["..."]
}

Regras:
- NUNCA prometa resultado (art. 2º §1º EOAB)
- Verifique competência (art. 42-62 CPC), legitimidade (art. 17 CPC)
- Verifique prescrição (art. 337 §1º CPC)
- Verifique valor da causa (art. 291-294 CPC)
- Identifique preliminares (art. 337 CPC)
- Avalie mérito com base nos fatos, não em opinião pessoal`,
        },
        {
          role: "user",
          content: `## Fatos do caso
${caseFacts}

## Área: ${area}

## Pedidos/tese
${claim}

## ${documentoTexto ? `Minuta produzida:\n${documentoTexto.slice(0, 1000)}` : "Sem minuta (análise prévia)"}`,
        },
      ],
      thinking: { type: "disabled" },
      temperature: 0.3,
      max_tokens: 800,
    });

    const raw = completion.choices[0]?.message?.content || "";
    const match = raw.match(/\{[\s\S]*\}/);
    if (match) {
      const parsed = JSON.parse(match[0]);
      return {
        admissibilidade,
        merito: {
          probabilidade: parsed.probabilidade || "media",
          pontos_fortes: parsed.pontos_fortes || [],
          pontos_fracos: parsed.pontos_fracos || [],
          fundamentos_necessarios: parsed.fundamentos_necessarios || [],
          provas_essenciais: parsed.provas_essenciais || [],
        },
        recomendacao: parsed.recomendacao || "Verifique manualmente",
        risks: parsed.risks || [],
      };
    }
  } catch {
    // Falha do LLM — retorna apenas verificação determinística
  }

  return {
    admissibilidade,
    merito: {
      probabilidade: "media",
      pontos_fortes: [],
      pontos_fracos: [],
      fundamentos_necessarios: ["Verificar fundamentos normativos"],
      provas_essenciais: ["Verificar provas documentais"],
    },
    recomendacao: "Verificação determinística concluída. Análise de mérito indisponível.",
    risks: ["IA indisponível para análise de mérito"],
  };
}

function checkDeterministic(
  tipo: string,
  facts: string
): { status: "ok" | "risco" | "erro"; detail: string } {
  const lower = facts.toLowerCase();

  switch (tipo) {
    case "competencia":
      if (/vara\s+(?:c[ií]vel|criminal|trabalhista|fazenda|fam[ií]lia)/i.test(facts)) {
        return { status: "ok", detail: "Competência aparente nos fatos" };
      }
      return { status: "risco", detail: "Competência não identificada — verifique art. 42-62 CPC" };

    case "legitimidade":
      if (/autor|requerente|r[eé]u|requerido/i.test(facts)) {
        return { status: "ok", detail: "Partes identificadas nos fatos" };
      }
      return { status: "risco", detail: "Legitimidade das partes não clara — verifique art. 17 CPC" };

    case "interesse":
      if (/pedido|pretens|necessidade|urg[eê]ncia/i.test(facts)) {
        return { status: "ok", detail: "Interesse processual aparente (pedido + necessidade)" };
      }
      return { status: "risco", detail: "Interesse processual não claro — verifique utilidade e necessidade" };

    default:
      return { status: "ok", detail: "OK" };
  }
}
