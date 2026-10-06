// advocate.ts — Persona Advogado (petição inicial + réplica).
//
// System prompt específico + prompt dinâmico construído com base no caso.
// Pseudonimização é aplicada ANTES da chamada externa (já em debate_orchestrator).
// Reidratação é feita no retorno.

import { db } from "@/lib/db";
import ZAI from "z-ai-web-dev-sdk";
import { PERSONAS, type Persona } from "@/lib/personas";
import { searchDoctrine, formatDoctrine } from "@/lib/doctrine_base";
import { ensureDraftMarker } from "@/lib/ai_governance";
import { pseudonymize, rehydrate } from "@/lib/pseudonymizer";

export interface AdvocateTurnInput {
  facts: string;
  lado: "autor" | "reu"; // parte defendida
  nomeParte: string;
  nomeAdversario?: string;
  area: string;
  turno: 1 | 3; // 1 = tese/petição, 3 = réplica
  turnsAnteriores?: { persona: string; content: string }[]; // para réplica
}

export interface AdvocateTurnOutput {
  content: string; // texto em markdown com marcadores
  citations: { diploma: string; numero: string; url: string | null; verified: boolean }[];
  tokensUsed: number;
  latencyMs: number;
}

const PETITION_TEMPLATE = (lado: "autor" | "reu") =>
  lado === "autor"
    ? "PETIÇÃO INICIAL CÍVEL (ou peça equivalente conforme a área)"
    : "CONTESTAÇÃO / PEÇA DE DEFESA";

/** System prompt específico do Advogado (extensão do base). */
const ADVOGADO_EXTRA = `
DIRETRIZES ESPECÍFICAS DA PETIÇÃO:
- Endereçamento ao juízo competente (se cível) ou órgão (se penal, cite Vara/Tribunal do Júri).
- Qualificação das partes com [NOMES] preservados (sistema pseudonimiza).
- Estruture em Markdown com seções: ## I. Endereçamento, ## II. Qualificação, ## III. Fatos, ## IV. Fundamentos, ## V. Provas, ## VI. Pedidos, ## VII. Valor da Causa, ## VIII. Fechos.
- Cite artigos da base local. Se a base for insuficiente, escreva "[BUSCA EM TEMPO REAL NECESSÁRIA: Súmula X do Y]" para que o sistema operacionalize.
- Se réu: estruturar como ## I. Preliminares, ## II. Meritório, ## III. Pedidos, ## IV. Fechos.`;

export async function runAdvocateTurn(input: AdvocateTurnInput): Promise<AdvocateTurnOutput> {
  const persona: Persona = PERSONAS.advogado;
  const start = Date.now();

  // 1) Pseudonimizar fatos e nomes
  const pseudoFacts = pseudonymize(input.facts);

  // 2) Buscar base doutrinária por área
  const doctrine = await searchDoctrine(`${input.facts} ${input.nomeParte} ${input.area ?? ""}`, [input.area], 10);
  const doctrineBlock = doctrine
    .map((d, i) => `[${i + 1}] ${formatDoctrine(d)}`)
    .join("\n\n");

  // 3) Construir prompt dinâmico
  const contextoAdversario = input.turnsAnteriores
    ?.filter((t) => t.persona === "promotor" || t.persona === "juiz")
    .map((t, i) => `### ${t.persona.toUpperCase()} (turno ${i + 1})\n${t.content}`)
    .join("\n\n");

  const userPrompt = `
# CASO
Área jurídica: ${input.area}
Parte defendida: ${input.lado} (${input.nomeParte})
Adversário: ${input.nomeAdversario ?? "[a ser qualificado]"}
Tipo de peça: ${PETITION_TEMPLATE(input.lado)}

# FATOS (pseudonimizados)
${pseudoFacts.text}

# BASE DOUTRINÁRIA (use APENAS estas citações; resto marque como pendente)
${doctrineBlock || "(nenhuma doutrina local encontrada — marque todas as citações como pendente)"}

${contextoAdversario ? `# ARGUMENTOS ANTERIORES (para RÉPLICA)\n${contextoAdversario}\n` : ""}
# TAREFA
${input.turno === 1
  ? "Produza a " + PETITION_TEMPLATE(input.lado) + " completa em markdown. Use tom advocatício firme mas juridicamente correto. Inclua todos os pedidos com base legal."
  : "Produza a RÉPLICA (ou contrarrazões, conforme aplicável) respondendo ponto a ponto os argumentos do Promotor e do Juiz apresentados acima. Admita erros objetivos quando houver. Reforce a tese. Não repita argumentos — apenas rebata e adicione."}

# IMPORTANTE
- Preserve marcadores [NOME_1], [CPF_1] etc. — sistema reidrata.
- Use ____ (4 sublinhados) para dados faltantes; nunca invente.
- Rascunho marcado automaticamente.
`.trim();

  // 4) Chamar LLM
  const zai = await ZAI.create();
  let content = "";
  let tokensUsed = 0;

  try {
    const completion = await zai.chat.completions.create({
      messages: [
        { role: "system", content: persona.systemPrompt + "\n" + ADVOGADO_EXTRA },
        { role: "user", content: userPrompt },
      ],
      thinking: { type: "disabled" },
      temperature: 0.5,
      max_tokens: 3000,
    });
    content = completion.choices[0]?.message?.content || "";
    tokensUsed = (completion as unknown as { usage?: { total_tokens?: number } }).usage?.total_tokens || 0;
  } catch (e) {
    // Fallback mínimo em caso de erro do provider
    content = `## PETIÇÃO (modo offline)

Devido a indisponibilidade temporária do provedor, abaixo segue estrutura esquelética que deve ser complementada pelo advogado:

### I. Endereçamento
EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO DA [VARA] DA COMARCA DE [COMARCA/UF]

### II. Qualificação
${input.nomeParte}, já qualificado nos autos, vem propor a presente ação em face de ${input.nomeAdversario ?? "[adversário]"}.

### III. Fatos
${pseudoFacts.text}

### IV. Fundamentos
[Fundamentar com base doutrinária fornecida]

### V. Pedidos
[Pedidos específicos]

[LOCAL], [DATA].
${input.nomeParte}
Advogado(a)`;
  }

  // 5) Reidratar + rascunho
  const restored = rehydrate(content, pseudoFacts.map);
  const finalContent = ensureDraftMarker(restored);

  // 6) Extrair citações usadas (heurística: menções a "art. X" / "Súmula X")
  const citations: AdvocateTurnOutput["citations"] = [];
  const citedDoctrine = doctrine.filter((d) =>
    finalContent.includes(d.numero) || finalContent.includes(`${d.diploma} ${d.numero}`),
  );
  for (const d of citedDoctrine) {
    citations.push({ diploma: d.diploma, numero: d.numero, url: d.urlOficial, verified: true });
  }

  const latencyMs = Date.now() - start;

  return {
    content: finalContent,
    citations,
    tokensUsed,
    latencyMs,
  };
}
