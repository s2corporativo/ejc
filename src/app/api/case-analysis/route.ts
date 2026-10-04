import { NextRequest, NextResponse } from "next/server";
import ZAI from "z-ai-web-dev-sdk";
import { db } from "@/lib/db";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

interface CaseAnalysisResult {
  parties: { role: string; name?: string; type: string }[];
  timeline: { date: string; event: string }[];
  requests: string[];
  proofs: string[];
  decisions: string[];
  values: { label: string; amount: string }[];
  risks: { level: "baixo" | "médio" | "alto"; description: string }[];
  nextSteps: string[];
}

const EMPTY: CaseAnalysisResult = {
  parties: [],
  timeline: [],
  requests: [],
  proofs: [],
  decisions: [],
  values: [],
  risks: [],
  nextSteps: [],
};

export async function POST(req: NextRequest) {
  let body: { facts?: string; title?: string } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }

  const facts = (body.facts || "").trim();
  const title = body.title?.trim() || `Análise de caso — ${new Date().toLocaleDateString("pt-BR")}`;

  if (!facts || facts.length < 30) {
    return NextResponse.json(
      { error: "Descreva os fatos do caso (mínimo 30 caracteres)" },
      { status: 400 }
    );
  }

  const systemPrompt = `Você é a JuridIA, uma IA jurídica brasileira especialista em análise estruturada de casos. Sua tarefa é analisar os fatos de um caso jurídico e extrair informações estruturadas em formato JSON válido. Responda APENAS com JSON válido, sem markdown, sem comentários, sem texto antes ou depois do JSON.

O JSON deve ter exatamente esta estrutura:
{
  "parties": [{"role": "autor|réu|requerente|requerido|apelante|apelado|terceiro", "name": "nome se mencionado, senão null", "type": "pessoa física|pessoa jurídica|órgão público"}],
  "timeline": [{"date": "data mencionada ou 'data não informada'", "event": "evento cronológico"}],
  "requests": ["pedido 1", "pedido 2"],
  "proofs": ["prova 1", "prova 2"],
  "decisions": ["decisão mencionada, se houver"],
  "values": [{"label": "valor da causa|indenização|débito|multa", "amount": "R$ X.XXX,XX"}],
  "risks": [{"level": "baixo|médio|alto", "description": "descrição do risco"}],
  "nextSteps": ["próximo passo 1", "próximo passo 2"]
}

Regras:
- Se não houver informação para um campo, retorne array vazio [].
- Não invente dados. Use apenas o que está nos fatos.
- Para nomes, se houver marcador de anonimização [NOME_0001], use o marcador como name.
- risks deve avaliar riscos jurídicos reais do caso (prescrição, prova difícil, tese divergente, etc.).
- nextSteps deve sugerir ações concretas (juntar documento, avaliar tese, verificar jurisprudência, etc.).
- Resposta em português brasileiro.`;

  const userPrompt = `## Fatos do caso\n${facts}`;

  let result: CaseAnalysisResult = { ...EMPTY };

  try {
    const zai = await ZAI.create();
    const completion = await zai.chat.completions.create({
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userPrompt },
      ],
      thinking: { type: "disabled" },
      temperature: 0.3,
      max_tokens: 2000,
    });

    const raw = completion.choices[0]?.message?.content || "";
    // Extrai JSON mesmo se vier com markdown
    const jsonMatch = raw.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      try {
        const parsed = JSON.parse(jsonMatch[0]);
        result = {
          parties: Array.isArray(parsed.parties) ? parsed.parties : [],
          timeline: Array.isArray(parsed.timeline) ? parsed.timeline : [],
          requests: Array.isArray(parsed.requests) ? parsed.requests : [],
          proofs: Array.isArray(parsed.proofs) ? parsed.proofs : [],
          decisions: Array.isArray(parsed.decisions) ? parsed.decisions : [],
          values: Array.isArray(parsed.values) ? parsed.values : [],
          risks: Array.isArray(parsed.risks) ? parsed.risks : [],
          nextSteps: Array.isArray(parsed.nextSteps) ? parsed.nextSteps : [],
        };
      } catch {
        // JSON inválido, usa fallback
        result = fallbackAnalysis(facts);
      }
    } else {
      result = fallbackAnalysis(facts);
    }
  } catch {
    result = fallbackAnalysis(facts);
  }

  // Persiste a análise
  const demoUser = await db.user.findUnique({ where: { email: "demo@juridia.com.br" } });
  const userId = demoUser?.id;
  try {
    const saved = await db.caseAnalysis.create({
      data: {
        userId,
        title,
        factsInput: facts,
        parties: JSON.stringify(result.parties),
        timeline: JSON.stringify(result.timeline),
        requests: JSON.stringify(result.requests),
        proofs: JSON.stringify(result.proofs),
        decisions: JSON.stringify(result.decisions),
        values: JSON.stringify(result.values),
        risks: JSON.stringify(result.risks),
        nextSteps: JSON.stringify(result.nextSteps),
      },
    });
    return NextResponse.json({ id: saved.id, ...result, title });
  } catch {
    return NextResponse.json({ ...result, title });
  }
}

export async function GET() {
  const items = await db.caseAnalysis.findMany({
    orderBy: { createdAt: "desc" },
    take: 20,
  });
  return NextResponse.json({
    analyses: items.map((a) => ({
      id: a.id,
      title: a.title,
      factsInput: a.factsInput,
      parties: safeParse(a.parties),
      timeline: safeParse(a.timeline),
      requests: safeParse(a.requests),
      proofs: safeParse(a.proofs),
      decisions: safeParse(a.decisions),
      values: safeParse(a.values),
      risks: safeParse(a.risks),
      nextSteps: safeParse(a.nextSteps),
      createdAt: a.createdAt.toISOString(),
    })),
  });
}

function safeParse(raw: string | null): unknown[] {
  if (!raw) return [];
  try {
    const v = JSON.parse(raw);
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

function fallbackAnalysis(facts: string): CaseAnalysisResult {
  // Heurística simples baseada em keywords
  const lower = facts.toLowerCase();
  const parties: { role: string; type: string }[] = [];

  if (lower.includes("autor")) parties.push({ role: "autor", type: "pessoa física" });
  if (lower.includes("réu") || lower.includes("reu")) parties.push({ role: "réu", type: "pessoa jurídica" });
  if (lower.includes("apelante")) parties.push({ role: "apelante", type: "pessoa física" });
  if (lower.includes("apelado")) parties.push({ role: "apelado", type: "pessoa jurídica" });

  const requests: string[] = [];
  if (lower.includes("indenização") || lower.includes("indenizacao")) requests.push("Indenização por danos morais");
  if (lower.includes("cobranç") || lower.includes("cobranc")) requests.push("Cobrança de valores devidos");
  if (lower.includes("tutela") || lower.includes("liminar")) requests.push("Concessão de tutela de urgência");
  if (lower.includes("devoluç")) requests.push("Devolução de valores");
  if (requests.length === 0) requests.push("Procedência dos pedidos formulados");

  const proofs: string[] = [];
  if (lower.includes("documento")) proofs.push("Documentos anexos");
  if (lower.includes("comprovante")) proofs.push("Comprovantes");
  if (lower.includes("contrato")) proofs.push("Contrato");
  if (lower.includes("fatura") || lower.includes("nota fiscal")) proofs.push("Faturas/notas fiscais");
  if (proofs.length === 0) proofs.push("Documentação a juntar");

  const values: { label: string; amount: string }[] = [];
  const valMatch = facts.match(/R\$\s*\d[\d.,]*\d{0,2}/gi);
  if (valMatch) {
    valMatch.slice(0, 3).forEach((v, i) => {
      values.push({ label: i === 0 ? "Valor da causa" : `Valor ${i + 1}`, amount: v });
    });
  }

  const risks: { level: "baixo" | "médio" | "alto"; description: string }[] = [];
  if (lower.includes("prescriç") || lower.includes("prescric")) {
    risks.push({ level: "alto", description: "Risco de prescrição — verificar prazos" });
  }
  if (lower.includes("sem prova") || lower.includes("dificil prova") || lower.includes("difícil prova")) {
    risks.push({ level: "alto", description: "Dificuldade probatória identificada" });
  }
  if (risks.length === 0) {
    risks.push({ level: "médio", description: "Avaliar jurisprudência dos tribunais superiores sobre a tese" });
  }

  const nextSteps = [
    "Revisar fatos e qualificação das partes",
    "Verificar jurisprudência aplicável nos tribunais superiores",
    "Confirmar competência e foro",
    "Avaliar necessidade de tutela de urgência",
    "Preparar provas documentais",
  ];

  return {
    parties: parties.length > 0 ? parties : [{ role: "autor", type: "pessoa física" }],
    timeline: [{ date: "data não informada", event: "Fatos descritos na peça" }],
    requests,
    proofs,
    decisions: [],
    values,
    risks,
    nextSteps,
  };
}
