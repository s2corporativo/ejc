// prosecutor.ts — Persona Promotor de Justiça (Ministério Público).
//
// Em caso penal: produz denúncia com tipificação, indícios, materialidade.
// Em caso cível: produz parecer ministerial apontando riscos à parte
// fraca, ao erário ou ao interesse difuso/coletivo.

import ZAI from "z-ai-web-dev-sdk";
import { PERSONAS, type Persona, isCasoPenal } from "@/lib/personas";
import { searchDoctrine, formatDoctrine } from "@/lib/doctrine_base";
import { ensureDraftMarker } from "@/lib/ai_governance";
import { pseudonymize, rehydrate } from "@/lib/pseudonymizer";

export interface ProsecutorTurnInput {
  facts: string;
  area: string;
  nomeVitima?: string; // para caso penal
  nomeAutor?: string;  // para caso cível
  nomeAdversario?: string;
  turnAnteriorAdvogado?: string; // para embasar contrarrazões
}

export interface ProsecutorTurnOutput {
  content: string;
  artifactKind: "denuncia" | "parecer";
  citations: { diploma: string; numero: string; url: string | null; verified: boolean }[];
  tokensUsed: number;
  latencyMs: number;
}

const PROMOTOR_EXTRA = `
DIRETRIZES ESPECÍFICAS:
${(area: string) => isCasoPenal(area)
  ? `CASO PENAL — DENÚNCIA:
   - ## I. Tipificação penal (artigos do CP com tipicidade objetiva, subjetiva e ilicitude)
   - ## II. Indícios de autoria e materialidade (extraídos dos fatos)
   - ## III. Classificação jurídica (doloso, culposo, preterdoloso)
   - ## IV. Causas de aumento/diminuição de pena
   - ## V. Pedidos: recebimento da denúncia, citação, instrução
   - Use SEMPRE dados com indícios suficientes (não crie prova). Se insuficiente, peça diligências.`
  : `CASO CÍVEL/ADMINISTRATIVO — PARECER MINISTERIAL:
   - ## I. Legitimidade do MP
   - ## II. Análise do caso (parte fraca, interesse difuso, erário)
   - ## III. Fundamentação jurídica (lei + jurisprudência)
   - ## IV. Conclusão ministerial (pela procedência/improcedência/parcial)
   - Vista obrigatória em processos que envolvam interesse público.`}
- Sejam firmes mas juridicamente corretos. Não inventem prova.`;

export async function runProsecutorTurn(input: ProsecutorTurnInput): Promise<ProsecutorTurnOutput> {
  const persona: Persona = PERSONAS.promotor;
  const start = Date.now();
  const penal = isCasoPenal(input.area);

  // 1) Pseudonimizar
  const pseudoFacts = pseudonymize(input.facts);

  // 2) Buscar base doutrinária (penalistas ou cíveis)
  const areas = penal ? ["penal", "processo_penal", "constitucional"] : ["civil", "processo_civil", "constitucional", input.area];
  const doctrine = await searchDoctrine(input.facts, areas, 10);
  const doctrineBlock = doctrine.map((d, i) => `[${i + 1}] ${formatDoctrine(d)}`).join("\n\n");

  // 3) Construir prompt
  const turnoAdvogado = input.turnAnteriorAdvogado
    ? `\n# TURNO ANTERIOR — ADVOGADO\n${input.turnAnteriorAdvogado}\n`
    : "";

  const userPrompt = `
# CASO
Área: ${input.area}
Tipo: ${penal ? "PENAL — DENÚNCIA" : "CÍVEL/ADMINISTRATIVO — PARECER"}
${input.nomeVitima ? `Vítima: ${input.nomeVitima}` : ""}
${input.nomeAutor ? `Autor: ${input.nomeAutor}` : ""}
Adversário: ${input.nomeAdversario ?? "[a ser qualificado]"}

# FATOS (pseudonimizados)
${pseudoFacts.text}
${turnoAdvogado}
# BASE DOUTRINÁRIA
${doctrineBlock || "(nenhuma doutrina local encontrada)"}

# TAREFA
${penal
  ? "Produza a DENÚNCIA em markdown. Inclua tipificação, indícios de autoria/materialidade, classificação, e pedido de recebimento e citação."
  : "Produza o PARECER MINISTERIAL em markdown. Posicione-se sobre a procedência dos pedidos com base no interesse público."}
`.trim();

  // 4) Chamar LLM
  const zai = await ZAI.create();
  let content = "";
  let tokensUsed = 0;

  try {
    const completion = await zai.chat.completions.create({
      messages: [
        { role: "system", content: persona.systemPrompt + "\n" + PROMOTOR_EXTRA },
        { role: "user", content: userPrompt },
      ],
      thinking: { type: "disabled" },
      temperature: 0.4,
      max_tokens: 3000,
    });
    content = completion.choices[0]?.message?.content || "";
    tokensUsed = (completion as unknown as { usage?: { total_tokens?: number } }).usage?.total_tokens || 0;
  } catch {
    content = `## ${penal ? "DENÚNCIA" : "PARECER MINISTERIAL"} (modo offline)

Devido a indisponibilidade temporária do provedor, segue estrutura esquelética:

### I. ${penal ? "Tipificação" : "Legitimidade do MP"}
[Preencher]

### II. Análise dos fatos
${pseudoFacts.text}

### III. Fundamentação
[Base doutrinária]

### IV. Pedidos
[Pedidos ministeriais]`;
  }

  // 5) Reidratar + rascunho
  const restored = rehydrate(content, pseudoFacts.map);
  const finalContent = ensureDraftMarker(restored);

  // 6) Citações usadas
  const citations: ProsecutorTurnOutput["citations"] = [];
  const citedDoctrine = doctrine.filter((d) =>
    finalContent.includes(d.numero) || finalContent.includes(`${d.diploma} ${d.numero}`),
  );
  for (const d of citedDoctrine) {
    citations.push({ diploma: d.diploma, numero: d.numero, url: d.urlOficial, verified: true });
  }

  return {
    content: finalContent,
    artifactKind: penal ? "denuncia" : "parecer",
    citations,
    tokensUsed,
    latencyMs: Date.now() - start,
  };
}
