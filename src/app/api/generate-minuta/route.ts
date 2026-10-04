import { NextRequest, NextResponse } from "next/server";
import ZAI from "z-ai-web-dev-sdk";
import { db } from "@/lib/db";
import { pseudonymize, rehydrate } from "@/lib/pseudonymizer";
import { validateResponse, ensureDraftMarker } from "@/lib/ai_governance";
import { logAuditEvent, logUsageEntry } from "@/lib/audit";
import type { GenerateMinutaRequest, GenerateMinutaResponse, DocumentDTO } from "@/lib/types";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

export async function POST(req: NextRequest) {
  let body: GenerateMinutaRequest;
  try {
    body = (await req.json()) as GenerateMinutaRequest;
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }

  if (!body?.templateSlug || !body?.fields) {
    return NextResponse.json({ error: "templateSlug e fields obrigatórios" }, { status: 400 });
  }

  // 1) Carrega template e skills
  const tpl = await db.template.findUnique({ where: { slug: body.templateSlug } });
  if (!tpl) {
    return NextResponse.json({ error: "Template não encontrado" }, { status: 404 });
  }

  const skills = body.skillSlugs?.length
    ? await db.skill.findMany({ where: { slug: { in: body.skillSlugs } } })
    : [];

  // 2) Monta o "inteiro teor" dos fatos a partir dos campos
  const factsBlock = Object.entries(body.fields)
    .filter(([, v]) => v && String(v).trim())
    .map(([k, v]) => `• ${labelFromKey(k)}: ${v}`)
    .join("\n");

  // 3) PSEUDONIMIZAÇÃO REVERSÍVEL LOCAL — antes de enviar à IA (tarja-1 evoluído)
  // Marcadores CONSISTENTES: mesma entidade = mesmo marcador em todo o texto.
  // O mapa NUNCA vai ao provider, NUNCA é logado, NUNCA é persistido.
  const pseudonymization = pseudonymize(factsBlock);

  // 4) Monta prompt
  const skillsBlock = skills.length
    ? `\n\n## Habilidades (skills) aplicadas\n${skills
        .map((s) => `### ${s.name} (# ${s.slug})\n${s.content}`)
        .join("\n\n")}`
    : "";

  // Lista explícita de marcadores disponíveis para o LLM
  const markerList = Object.keys(pseudonymization.map.reverse);
  const markerListStr = markerList.length
    ? `\n\n## Lista EXAUSTIVA de marcadores disponíveis (use APENAS estes)\n${markerList
      .map((m) => `- ${m} → ${describeMarker(m)}`)
      .join("\n")}\n\nNÃO crie novos marcadores. NÃO invente [LOCAL_0001], [PROFISSAO_0001] ou qualquer outro. Se faltar um dado, use ____ (sublinhado) como espaço a preencher manualmente.`
    : "\n\nNenhum marcador foi gerado (não há dados sensíveis detectados). Use ____ para campos a preencher.";

  const userPrompt = `Você está redigindo uma minuta jurídica brasileira usando apenas marcadores no lugar de dados sensíveis (que foram anonimizados localmente antes de chegar a você).

## Tipo de minuta
${tpl.name}

## Diretrizes do template
${tpl.prompt}

## Dados do caso (com marcadores)
${pseudonymization.text}
${skillsBlock}
${markerListStr}

## Instruções finais
- Redija a minuta em português jurídico brasileiro, completa e formal.
- Preserve TODOS os marcadores da lista acima exatamente como aparecem. Reuse-os quantas vezes precisar.
- NUNCA crie marcadores novos. Se um campo (ex: profissão, endereço, data) não tiver marcador, escreva ____ no lugar.
- Use formatação Markdown (cabeçalhos ##, listas, ênfase) para que o documento seja legível.
- Estruture em seções claras (Endereçamento, Qualificação, Fatos, Fundamentos, Pedidos etc.).
- Para datas, use ____ de ____________ de ______.`;

  // 5) Chama o LLM
  let generated = "";
  let tokensUsed = 0;
  try {
    const zai = await ZAI.create();
    const completion = await zai.chat.completions.create({
      messages: [
        {
          role: "system",
          content:
            "Você é a JuridIA, uma IA jurídica brasileira especialista em redação de minutas e peças processuais. Sua saída é sempre em português do Brasil, em linguagem jurídica formal, com conformidade ao CPC, CC, legislação especial e Resolução CNJ 615/2025. Você nunca escreve dados sensíveis inventados: usa apenas os marcadores [TIPO_000X] fornecidos.",
        },
        { role: "user", content: userPrompt },
      ],
      thinking: { type: "disabled" },
      temperature: 0.6,
      max_tokens: 3000,
    });
    generated = completion.choices[0]?.message?.content || "";
    tokensUsed = (completion as unknown as { usage?: { total_tokens?: number } }).usage?.total_tokens || 0;
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Falha ao gerar minuta";
    // fallback offline — gera um esboço estruturado com os campos
    generated = fallbackDraft(tpl.name, pseudonymization.text, skills);
  }

  // 6) DESANONIMIZAÇÃO LOCAL — restaura marcadores no retorno
  const restoredContent = rehydrate(generated, pseudonymization.map);

  // 6.5) RESPONSE VALIDATOR — valida saída contra regras jurídicas inegociáveis
  const validation = validateResponse(restoredContent);
  const finalContent = ensureDraftMarker(restoredContent);

  // 7) Persiste
  const title = body.title?.trim() || `${tpl.name} — ${new Date().toLocaleDateString("pt-BR")}`;
  const demoUser = await db.user.findUnique({ where: { email: "demo@juridia.com.br" } });
  const userId = demoUser?.id || (await ensureDemoUser()).id;

  const doc = await db.document.create({
    data: {
      userId,
      title,
      templateSlug: tpl.slug,
      templateName: tpl.name,
      rawFacts: factsBlock,
      anonymizedFacts: pseudonymization.text,
      markers: JSON.stringify(Object.fromEntries(pseudonymization.map.reverse)),
      generatedContent: finalContent,
      skillSlugs: JSON.stringify(skills.map((s) => s.slug)),
      status: "generated",
      batchId: body.batchId || null,
    },
  });

  // incrementa uso do demo
  await db.user.update({
    where: { id: userId },
    data: { minutasUsed: { increment: 1 } },
  });

  // Registra evento de auditoria + entrada no ledger de uso (imutáveis)
  await logAuditEvent({
    action: "generate_minuta",
    resource: "document",
    resourceId: doc.id,
    metadata: {
      templateSlug: tpl.slug,
      templateName: tpl.name,
      skillSlugs: skills.map((s) => s.slug),
      markersCount: pseudonymization.total,
      validationViolations: validation.violations.length,
      validationErrors: validation.violations.filter((v) => v.severity === "error").length,
      tokensUsed,
      anonymized: true,
    },
    userId,
  });
  await logUsageEntry({
    type: "debit",
    operation: "minuta",
    amount: -1,
    reason: `Geração de ${tpl.name}`,
    metadata: { documentId: doc.id, templateSlug: tpl.slug, tokensUsed },
    userId,
  });

  const documentDTO: DocumentDTO = {
    id: doc.id,
    title: doc.title,
    templateSlug: doc.templateSlug,
    templateName: doc.templateName,
    anonymizedFacts: doc.anonymizedFacts,
    generatedContent: doc.generatedContent,
    skillSlugs: safeParseArr(doc.skillSlugs),
    status: doc.status,
    batchId: doc.batchId,
    createdAt: doc.createdAt.toISOString(),
    updatedAt: doc.updatedAt.toISOString(),
  };

  return NextResponse.json({
    document: documentDTO,
    rawMarkers: pseudonymization.map.reverse,
    tokensUsed,
  } as GenerateMinutaResponse);
}

async function ensureDemoUser() {
  const u = await db.user.create({
    data: {
      email: "demo@juridia.com.br",
      name: "Advogado Demo",
      plan: "individual_2",
      minutasUsed: 0,
      minutasLimit: 200,
    },
  });
  return u;
}

function safeParseArr(raw: string | null): string[] {
  if (!raw) return [];
  try {
    return JSON.parse(raw) as string[];
  } catch {
    return [];
  }
}

function labelFromKey(key: string): string {
  return key
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/^./, (c) => c.toUpperCase());
}

function fallbackDraft(templateName: string, anonFacts: string, skills: { name: string }[]): string {
  const skillList = skills.length
    ? skills.map((s) => `- ${s.name}`).join("\n")
    : "(nenhuma habilidade selecionada)";
  return `## ${templateName}

> ⚠️ Modo offline — a geração via IA falhou. Abaixo um esboço estruturado com os dados anonimizados. Refaça a geração quando a IA estiver disponível.

### I. Endereçamento
EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA [VARA]

### II. Qualificação
[NOME_0001], já devidamente qualificado, vem respeitosamente à presença de Vossa Excelência propor a presente ação em face de [NOME_0002], também qualificado, pelos fatos e fundamentos a seguir.

### III. Fatos
${anonFacts}

### IV. Do Direito
Fundamentação jurídica a complementar.

### V. Habilidades aplicadas
${skillList}

### VI. Pedidos
1. [PEDIDO_PRINCIPAL]
2. Condenação em honorários advocatícios
3. Procedência dos pedidos

### VII. Valor da causa
R$ [VALOR_0001].

Dá-se à causa o valor de R$ [VALOR_0001].

[PETICIONAMENTO_ELETRÔNICO]
Termos em que pede deferimento.

[LOCAL], [DATA].

[ADVOGADO] — OAB/[UF] [OAB_NUM]
`;
}

// Descreve o tipo de dado que um marcador representa, para o LLM entender o contexto
function describeMarker(marker: string): string {
  const match = marker.match(/^\[([A-Z_]+)_(\d+)\]$/);
  if (!match) return "dado anonimizado";
  const type = match[1];
  const descriptions: Record<string, string> = {
    CPF: "número de CPF",
    CNPJ: "número de CNPJ",
    RG: "número de RG/identidade",
    TELEFONE: "número de telefone",
    EMAIL: "endereço de e-mail",
    CEP: "CEP",
    PIS: "número PIS/PASEP",
    PLACA: "placa de veículo",
    CONTA: "conta/agência bancária",
    VALOR: "valor monetário em R$",
    NOME: "nome de pessoa/empresa",
  };
  return descriptions[type] || "dado sensível";
}
