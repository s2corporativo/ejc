import { NextRequest, NextResponse } from "next/server";
import ZAI from "z-ai-web-dev-sdk";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

interface MoldeChange {
  operation: "replace" | "add" | "remove";
  anchor: string;       // trecho exato do documento-base
  replacement?: string;  // novo trecho (para replace/add)
  reason: string;        // justificativa
}

export async function POST(req: NextRequest) {
  let body: {
    baseDocument?: string;
    instruction?: string;
    templateName?: string;
  } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }

  const baseDocument = body.baseDocument || "";
  const instruction = (body.instruction || "").trim();
  const templateName = body.templateName || "minuta jurídica";

  if (!baseDocument || baseDocument.length < 50) {
    return NextResponse.json(
      { error: "Documento-base muito curto (mínimo 50 caracteres)" },
      { status: 400 }
    );
  }
  if (!instruction) {
    return NextResponse.json(
      { error: "Instrução obrigatória (o que alterar no documento)" },
      { status: 400 }
    );
  }

  const systemPrompt = `Você é a JuridIA operando em Modo Molde. Sua tarefa é analisar um documento-base jurídico e uma instrução do advogado, e produzir uma LISTA de alterações estruturadas que devem ser aplicadas ao documento.

NÃO reescreva o documento inteiro. Produza apenas as alterações necessárias, cada uma com:
- operation: "replace" (substituir trecho), "add" (adicionar após o anchor), "remove" (remover o trecho)
- anchor: o trecho EXATO do documento-base que deve ser localizado (mínimo 10 caracteres, máximo 200)
- replacement: o novo trecho (para "replace" e "add"; null para "remove")
- reason: justificativa curta da alteração

REGRAS CRÍTICAS:
1. O anchor DEVE ser um trecho que existe literalmente no documento-base. Não invente.
2. Se a instrução não se aplicar a nenhum trecho existente, use "add" com um anchor no final de uma seção relevante.
3. Preserve marcadores [TIPO_0001] existentes no documento.
4. Máximo de 10 alterações por resposta.
5. Responda APENAS com JSON válido, sem markdown, sem texto antes/depois.

Formato da resposta:
{
  "changes": [
    {
      "operation": "replace",
      "anchor": "trecho exato do documento-base...",
      "replacement": "novo trecho...",
      "reason": "motivo da alteração"
    }
  ]
}`;

  const userPrompt = `## Tipo de documento
${templateName}

## Documento-base
${baseDocument.slice(0, 8000)}

## Instrução do advogado
${instruction}`;

  try {
    const zai = await ZAI.create();
    const completion = await zai.chat.completions.create({
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userPrompt },
      ],
      thinking: { type: "disabled" },
      temperature: 0.4,
      max_tokens: 2000,
    });

    const raw = completion.choices[0]?.message?.content || "";
    const jsonMatch = raw.match(/\{[\s\S]*\}/);
    let changes: MoldeChange[] = [];

    if (jsonMatch) {
      try {
        const parsed = JSON.parse(jsonMatch[0]);
        if (Array.isArray(parsed.changes)) {
          changes = parsed.changes
            .filter(
              (c: MoldeChange) =>
                c.operation &&
                c.anchor &&
                typeof c.anchor === "string" &&
                c.anchor.length >= 5
            )
            .slice(0, 10)
            .map((c: MoldeChange) => ({
              operation: c.operation,
              anchor: c.anchor.slice(0, 300),
              replacement: c.replacement || null,
              reason: c.reason || "",
            }));
        }
      } catch {
        // JSON inválido
      }
    }

    // Validação: cada anchor deve existir (parcialmente) no documento-base
    const validated = changes.filter((c) => {
      const anchorShort = c.anchor.slice(0, 40).toLowerCase();
      return baseDocument.toLowerCase().includes(anchorShort);
    });

    return NextResponse.json({
      changes: validated.length > 0 ? validated : changes,
      total: validated.length > 0 ? validated.length : changes.length,
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Erro no Modo Molde";
    return NextResponse.json({ error: msg, changes: [] }, { status: 500 });
  }
}
