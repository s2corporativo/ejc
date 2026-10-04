import { NextRequest, NextResponse } from "next/server";
import ZAI from "z-ai-web-dev-sdk";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

const STYLE_HINTS: Record<string, string> = {
  formal:
    "Use linguagem jurídica formal tradicional, com citações de artigos (ex: 'art. 927 do CC') e fundamentação completa.",
  sintetico:
    "Seja conciso e direto. Fundamentação essencial apenas, sem prolixidade. Ideal para processos repetitivos.",
  academic:
    "Inclua citações doutrinárias (ex: 'Conforme ensina Maria Helena Diniz...') e jurisprudência detalhada.",
  direto:
    "Use linguagem clara e acessível, sem jargão excessivo. Adequado para audiências de conciliação.",
};

export async function POST(req: NextRequest) {
  let body: {
    instruction?: string;
    currentContent?: string;
    templateName?: string;
    style?: string;
  } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }

  const instruction = (body.instruction || "").trim();
  const currentContent = body.currentContent || "";
  const templateName = body.templateName || "minuta jurídica";
  const style = body.style || "formal";

  if (!instruction) {
    return NextResponse.json({ error: "Instrução obrigatória" }, { status: 400 });
  }

  const styleHint = STYLE_HINTS[style] || STYLE_HINTS.formal;

  const systemPrompt = `Você é a JuridIA, uma IA jurídica brasileira especialista em redação de minutas. Sua tarefa é gerar UM TRECHO de peça jurídica que o usuário pediu. Responda APENAS com o trecho solicitado, sem comentários ou explicações. Use formatação Markdown (### para subtítulos, listas, parágrafos). Estilo: ${styleHint}. Conformidade: CPC, CC, legislação especial, Resolução CNJ 615/2025.`;

  const userPrompt = `## Contexto
Tipo de minuta: ${templateName}

## Conteúdo atual (para contexto)
${currentContent.slice(-1500) || "(documento vazio)"}

## Pedido do usuário
${instruction}

## Resposta
Gere apenas o trecho solicitado, em português jurídico brasileiro, pronto para ser inserido no documento. Não use marcadores [TIPO_0001] — escreva o texto completo com dados genéricos onde necessário (____ para campos a preencher).`;

  try {
    const zai = await ZAI.create();
    const completion = await zai.chat.completions.create({
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userPrompt },
      ],
      thinking: { type: "disabled" },
      temperature: 0.5,
      max_tokens: 1200,
    });

    const suggestion = completion.choices[0]?.message?.content || "";
    return NextResponse.json({
      suggestion,
      tokensUsed:
        (completion as unknown as { usage?: { total_tokens?: number } }).usage
          ?.total_tokens || 0,
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Erro ao gerar sugestão";
    // Fallback offline com trechos pré-formatados
    const fallback = generateFallback(instruction, templateName);
    return NextResponse.json({
      suggestion: fallback,
      offline: true,
      error: msg,
    });
  }
}

function generateFallback(instruction: string, templateName: string): string {
  const lower = instruction.toLowerCase();

  if (lower.includes("fundament")) {
    return `### Fundamentação

O art. 927 do Código Civil estabelece que aquele que, por ato ilícito (arts. 186 e 187), causar dano a outrem, fica obrigado a repará-lo. Tratando-se de responsabilidade objetiva (art. 927, parágrafo único), basta a demonstração da conduta, do dano e do nexo causal.

A jurisprudência do STJ consolidou entendimento no sentido de que a inscrição indevida em cadastros de proteção ao crédito, quando decorrente de conduta ilícita do fornecedor, gera dano moral in re ipsa, prescindindo a comprovação de prejuízo concreto.

No caso em tela, restam caracterizados os pressupostos da responsabilidade civil, impondo-se a condenação do réu ao pagamento de indenização por danos morais, em valor razoável e proporcional à gravidade da conduta.`;
  }
  if (lower.includes("pedido")) {
    return `### Pedidos

1. A procedência integral da ação para condenar o réu ao pagamento de indenização por danos morais;
2. A condenação do réu em honorários advocatícios de 20% sobre o valor da condenação (art. 85, §2º, CPC);
3. A condenação do réu nas custas processuais;
4. A concessão dos benefícios da Justiça Gratuita ao autor, por ser pessoa pobre na acepção jurídica do termo;
5. A produção de todas as provas em direito admitidas, em especial documental e testemunhal.

Dá-se à causa o valor de R$ ____.`;
  }
  if (lower.includes("relat") || lower.includes("fato")) {
    return `### I. Dos Fatos

O autor, devidamente qualificado, manteve relação jurídica com o réu. No entanto, o réu, em conduta contrária ao direito, promoveu ____ que resultou em prejuízos ao autor.

Diante da conduta ilícita, restou configurado o dano, bem como o nexo de causalidade entre a conduta do réu e o prejuízo experimentado pelo autor.

Frustradas as tentativas de resolução amigável, restou ao autor valer-se da via judicial para ver reparado o dano sofrido.`;
  }
  return `### ${templateName}

Trecho sugerido para: ${instruction}

Conforme a legislação aplicável e a jurisprudência dos tribunais superiores, cumpre destacar que ____ (complementar com a fundamentação específica do caso).

Assim, requer-se o que de direito.`;
}
