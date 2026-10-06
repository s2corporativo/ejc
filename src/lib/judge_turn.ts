// judge_turn.ts — Persona Juiz para o Tribunal multi-agente.
//
// Complementa judge_simulator.ts (análise prévia de admissibilidade/merit) com
// a produção do turno de debate: admissibilidade formal → instrução → sentença.
//
// Diferente do simulateJudge (que retorna JSON estruturado), o runJudgeTurn
// produz markdown no padrão de uma sentença/decisão brasileira.

import ZAI from "z-ai-web-dev-sdk";
import { PERSONAS, type Persona, isCasoPenal } from "@/lib/personas";
import { searchDoctrine, formatDoctrine } from "@/lib/doctrine_base";
import { ensureDraftMarker } from "@/lib/ai_governance";
import { pseudonymize, rehydrate } from "@/lib/pseudonymizer";

export type JudgeRole = "admissibilidade" | "sentenca";

export interface JudgeTurnInput {
  facts: string;
  area: string;
  role: JudgeRole; // 1ª aparição = admissibilidade; 2ª = sentença
  turnsAnteriores?: { persona: string; content: string }[];
  parteAutora?: string;
  parteRe?: string;
}

export interface JudgeTurnOutput {
  content: string;
  artifactKind: "decisao_interlocutoria" | "sentenca";
  inadmitido: boolean; // true se juízo negativo na admissibilidade
  citations: { diploma: string; numero: string; url: string | null; verified: boolean }[];
  tokensUsed: number;
  latencyMs: number;
}

const JUIZ_EXTRA = `
DIRETRIZES ESPECÍFICAS:
- Postura de Estado-juiz: imparcialidade formal, fundamentação exaustiva (art. 489 CPC §1º).
- Não é advogado de nenhuma parte — analise TODOS os argumentos apresentados.
- Em caso penal: observe devido processo legal (art. 5º LIV CF), presunção de inocência (art. 5º LVII CF), in dubio pro reo.

${(role: JudgeRole, area: string) => {
  const penal = isCasoPenal(area);
  if (role === "admissibilidade") {
    return penal
      ? `TURNO 1 — ADMISSIBILIDADE DA DENÚNCIA (CPP art. 395-397):
   - ## I. Pressupostos processuais (jurisdição, competência, ação penal)
   - ## II. Condições de procedibilidade (justa causa, indícios suficientes)
   - ## III. Tipicidade aparente (adequação típica, ilicitude, culpabilidade)
   - ## IV. Análise das alegações da defesa (se houver)
   - ## V. Decisão: RECEBO ou REJEITO a denúncia (CPP art. 395/396)
   - Se REJEITAR, fim do debate — registrar motivo.`
      : `TURNO 1 — ADMISSIBILIDADE DA PETIÇÃO INICIAL (CPC art. 330):
   - ## I. Pressupostos processuais (juízo competente, partes legítimas, interesse)
   - ## II. Condições da ação (possibilidade jurídica, interesse processual, legitimidade)
   - ## III. Requisitos da inicial (CPC art. 319 — pedidos, causa de pedir, valores)
   - ## IV. Análise dos argumentos do Promotor (se caso cível público) ou da parte adversa
   - ## V. Decisão: INADMISSÃO (CPC art. 330) ou prosseguimento
   - Se INADMITIR, fim do debate — registrar motivo.`;
  }
  return penal
    ? `TURNO 2 — SENTENÇA PENAL (CPP art. 381-393):
   - ## I. Relatório (síntese dos atos e alegações)
   - ## II. Fundamentação (análise das provas indiciárias, tipicidade, ilicitude, culpabilidade)
   - ## III. Análise das teses defensivas ponto a ponto
   - ## IV. Correlação entre acusação e condenação (art. 3º CPP — ne reformatio in pejus)
   - ## V. Dispositivo (condenação, absolvição — art. 386 CPP — ou desclassificação)
   - Aplique o in dubio pro reo se houver dúvida razoável.`
    : `TURNO 2 — SENTENÇA CÍVEL (CPC art. 489):
   - ## I. Relatório
   - ## II. Fundamentação (fatos, direito, provas)
   - ## III. Análise das teses de cada parte ponto a ponto (art. 489 §1º I CPC)
   - ## IV. Consequências jurídicas
   - ## V. Dispositivo (procedente/improcedente, com consectários)
   - Fundamente cada conclusão — vedada a fundamentação per relationem genérica.`;
}}`;

export async function runJudgeTurn(input: JudgeTurnInput): Promise<JudgeTurnOutput> {
  const persona: Persona = PERSONAS.juiz;
  const start = Date.now();
  const penal = isCasoPenal(input.area);

  // 1) Pseudonimizar
  const pseudoFacts = pseudonymize(input.facts);

  // 2) Buscar base doutrinária por área
  const areas = penal
    ? ["penal", "processo_penal", "constitucional"]
    : ["civil", "processo_civil", "constitucional", input.area];
  const doctrine = await searchDoctrine(input.facts, areas, 12);
  const doctrineBlock = doctrine.map((d, i) => `[${i + 1}] ${formatDoctrine(d)}`).join("\n\n");

  // 3) Construir contexto adverso
  const contexto = (input.turnsAnteriores ?? [])
    .filter((t) => t.persona === "advogado" || t.persona === "promotor")
    .map((t, i) => `### ${t.persona.toUpperCase()} (turno ${i + 1})\n${t.content}`)
    .join("\n\n");

  // 4) Construir prompt
  const userPrompt = `
# CASO
Área: ${input.area}
Tipo: ${penal ? "PENAL" : "CÍVEL/ADMINISTRATIVO"}
${input.parteAutora ? `Parte autora: ${input.parteAutora}` : ""}
${input.parteRe ? `Parte ré: ${input.parteRe}` : ""}

# FATOS (pseudonimizados)
${pseudoFacts.text}

# BASE DOUTRINÁRIA
${doctrineBlock || "(nenhuma doutrina local encontrada)"}

# MANIFESTAÇÕES ANTERIORES
${contexto || "(sem manifestações anteriores)"}

# TAREFA
${
  input.role === "admissibilidade"
    ? "Analise a ADMISSIBILIDADE da peça inicial (cível) ou da denúncia (penal). Identifique pressupostos processuais, condições da ação/procedibilidade e requisitos formais. Decida pelo recebimento ou rejeição."
    : "Produza a SENTENÇA. Relatório → Fundamentação (analise ponto a ponto cada argumento do Advogado e do Promotor) → Dispositivo. Aplique jurisprudência e súmulas pertinentes. NÃO prometa resultado ao cliente."
}
`.trim();

  // 5) Chamar LLM
  const zai = await ZAI.create();
  let content = "";
  let tokensUsed = 0;

  try {
    const completion = await zai.chat.completions.create({
      messages: [
        { role: "system", content: persona.systemPrompt + "\n" + JUIZ_EXTRA },
        { role: "user", content: userPrompt },
      ],
      thinking: { type: "disabled" },
      temperature: 0.3,
      max_tokens: 3500,
    });
    content = completion.choices[0]?.message?.content || "";
    tokensUsed = (completion as unknown as { usage?: { total_tokens?: number } }).usage?.total_tokens || 0;
  } catch {
    content = `## ${input.role === "admissibilidade" ? "DECISÃO INTERLOCUTÓRIA" : "SENTENÇA"} (modo offline)

Devido a indisponibilidade temporária do provedor, segue estrutura esquelética:

### I. Relatório
${pseudoFacts.text}

### II. Fundamentação
[Análise dos pressupostos processuais e condições da ação conforme o caso]

### III. Dispositivo
[Decisão]`;
  }

  // 6) Reidratar + rascunho
  const restored = rehydrate(content, pseudoFacts.map);
  const finalContent = ensureDraftMarker(restored);

  // 7) Detectar inadmissão (heurística simples)
  const inadmitido = input.role === "admissibilidade"
    && /REJEITO|INADMITO|INDEFIRO\s+a\s+inicial|REJEIÇÃO\s+DA\s+DEN[ÚU]NCIA/i.test(finalContent);

  // 8) Citações usadas
  const citations: JudgeTurnOutput["citations"] = [];
  const citedDoctrine = doctrine.filter((d) =>
    finalContent.includes(d.numero) || finalContent.includes(`${d.diploma} ${d.numero}`),
  );
  for (const d of citedDoctrine) {
    citations.push({ diploma: d.diploma, numero: d.numero, url: d.urlOficial, verified: true });
  }

  return {
    content: finalContent,
    artifactKind: input.role === "admissibilidade" ? "decisao_interlocutoria" : "sentenca",
    inadmitido,
    citations,
    tokensUsed,
    latencyMs: Date.now() - start,
  };
}