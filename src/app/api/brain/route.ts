import { NextRequest, NextResponse } from "next/server";
import ZAI from "z-ai-web-dev-sdk";
import { db } from "@/lib/db";
import { logAuditEvent, logUsageEntry } from "@/lib/audit";

export const dynamic = "force-dynamic";
export const maxDuration = 180; // 3 min — análise profunda

// ── Tipos das etapas do Cérebro ──────────────────────────────────────────────

interface BrainStep {
  id: string;
  name: string;
  status: "pending" | "running" | "done" | "error";
  result?: unknown;
  error?: string;
}

interface BrainResult {
  // Etapa 1: Extração estruturada
  parties: { role: string; name?: string; type: string }[];
  timeline: { date: string; event: string }[];
  requests: string[];
  values: { label: string; amount: string }[];

  // Etapa 2: Questões jurídicas
  legalIssues: { question: string; area: string; relevance: "alta" | "média" | "baixa" }[];

  // Etapa 3: Legislação aplicável (da base curada)
  applicableLaw: {
    diploma: string;
    numero: string;
    textoTrecho: string;
    vigente: boolean;
    urlOficial?: string | null;
    applicability: string;
  }[];

  // Etapa 4: Jurisprudência (do web_search)
  jurisprudence: {
    name: string;
    url: string;
    snippet: string;
    host_name: string;
    favorable: boolean | null; // favorável/contrário/incerto
  }[];

  // Etapa 5: Análise de viabilidade
  viability: {
    probability: "alta" | "média" | "baixa";
    strengths: string[];
    weaknesses: string[];
    reasoning: string;
  };

  // Etapa 6: Lacunas e perguntas
  gaps: { what: string; why: string; question: string }[];

  // Etapa 7: Estratégia
  strategy: {
    proceduralPath: string;
    immediateActions: string[];
    documentsToCollect: string[];
    risks: string[];
    recommendation: string;
  };

  // Metadados
  steps: BrainStep[];
  totalTokens: number;
}

export async function POST(req: NextRequest) {
  let body: { facts?: string; title?: string; caseId?: string } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }

  const facts = (body.facts || "").trim();
  const title = body.title?.trim() || `Análise — ${new Date().toLocaleDateString("pt-BR")}`;

  if (facts.length < 30) {
    return NextResponse.json(
      { error: "Descreva os fatos do caso (mínimo 30 caracteres)" },
      { status: 400 }
    );
  }

  const steps: BrainStep[] = [
    { id: "extract", name: "Extração estruturada", status: "pending" },
    { id: "issues", name: "Questões jurídicas", status: "pending" },
    { id: "law", name: "Legislação aplicável", status: "pending" },
    { id: "jurisprudence", name: "Jurisprudência", status: "pending" },
    { id: "viability", name: "Análise de viabilidade", status: "pending" },
    { id: "gaps", name: "Lacunas e perguntas", status: "pending" },
    { id: "strategy", name: "Estratégia recomendada", status: "pending" },
  ];

  const result: Partial<BrainResult> = { steps };
  let totalTokens = 0;

  const zai = await ZAI.create();

  // ── ETAPA 1: Extração estruturada ──────────────────────────────────────────
  steps[0].status = "running";
  try {
    const completion = await zai.chat.completions.create({
      messages: [
        {
          role: "system",
          content: `Você é um advogado brasileiro sênior analisando um caso. Extraia informações estruturadas em JSON. Responda APENAS com JSON válido, sem markdown. Use marcadores [NOME_0001] se houver dados sensíveis.

{
  "parties": [{"role":"autor|réu|requerente|requerido|terceiro","name":"nome ou null","type":"pessoa física|pessoa jurídica|órgão público"}],
  "timeline": [{"date":"data","event":"evento"}],
  "requests": ["pedido 1"],
  "values": [{"label":"valor da causa|indenização|débito","amount":"R$ X"}]
}`,
        },
        { role: "user", content: facts },
      ],
      thinking: { type: "disabled" },
      temperature: 0.3,
      max_tokens: 800,
    });
    const raw = completion.choices[0]?.message?.content || "";
    const match = raw.match(/\{[\s\S]*\}/);
    if (match) {
      const parsed = JSON.parse(match[0]);
      result.parties = parsed.parties || [];
      result.timeline = parsed.timeline || [];
      result.requests = parsed.requests || [];
      result.values = parsed.values || [];
    }
    totalTokens += (completion as unknown as { usage?: { total_tokens?: number } }).usage?.total_tokens || 0;
    steps[0].status = "done";
    steps[0].result = result.parties;
  } catch (e) {
    steps[0].status = "error";
    steps[0].error = e instanceof Error ? e.message : "Erro";
    result.parties = []; result.timeline = []; result.requests = []; result.values = [];
  }

  // ── ETAPA 2: Questões jurídicas ───────────────────────────────────────────
  steps[1].status = "running";
  try {
    const completion = await zai.chat.completions.create({
      messages: [
        {
          role: "system",
          content: `Você é um advogado brasileiro sênior. Identifique as QUESTÕES JURÍDICAS do caso. Para cada questão, indique a área (civil/penal/trabalhista/tributario/consumer/family/previdenciario) e a relevância (alta/média/baixa). Responda APENAS com JSON: {"legalIssues":[{"question":"...","area":"...","relevance":"alta|média|baixa"}]}`,
        },
        { role: "user", content: `Fatos:\n${facts}\n\nPartes identificadas:\n${JSON.stringify(result.parties)}\nPedidos:\n${JSON.stringify(result.requests)}` },
      ],
      thinking: { type: "disabled" },
      temperature: 0.4,
      max_tokens: 600,
    });
    const raw = completion.choices[0]?.message?.content || "";
    const match = raw.match(/\{[\s\S]*\}/);
    if (match) {
      const parsed = JSON.parse(match[0]);
      result.legalIssues = parsed.legalIssues || [];
    }
    totalTokens += (completion as unknown as { usage?: { total_tokens?: number } }).usage?.total_tokens || 0;
    steps[1].status = "done";
    steps[1].result = result.legalIssues;
  } catch (e) {
    steps[1].status = "error";
    steps[1].error = e instanceof Error ? e.message : "Erro";
    result.legalIssues = [];
  }

  // ── ETAPA 3: Legislação aplicável (base curada LegalSource) ──────────────
  steps[2].status = "running";
  try {
    // Busca fontes relevantes com base nas questões jurídicas + fatos
    const issues = result.legalIssues || [];
    const areas = issues.map((i) => i.area).filter(Boolean);
    const query = `${facts} ${issues.map((i) => i.question).join(" ")}`;

    // Carrega fontes da base curada
    const allSources = await db.legalSource.findMany({
      where: { vigente: true },
      orderBy: [{ diploma: "asc" }, { numero: "asc" }],
    });

    // Seleção heurística: match por diploma/área + palavras-chave
    const keywords = query.toLowerCase();
    const applicableLaw = allSources
      .filter((s) => {
        // Match por menção direta no texto
        if (keywords.includes(s.diploma.toLowerCase())) return true;
        // Match por área: civil→CC/CPC, trabalhista→CLT, consumer→CDC, etc.
        if (areas.includes("civil") && ["CC", "CPC"].includes(s.diploma)) return true;
        if (areas.includes("trabalhista") && s.diploma === "CLT") return true;
        if (areas.includes("consumer") && s.diploma === "CDC") return true;
        if (areas.includes("tributario") && s.diploma === "CTN") return true;
        if (areas.includes("penal") && s.diploma === "CP") return true;
        // Match por palavras do texto no trecho
        const trecho = s.textoTrecho.toLowerCase();
        return keywords.split(" ").some((w) => w.length > 5 && trecho.includes(w));
      })
      .slice(0, 8)
      .map((s) => ({
        diploma: s.diploma,
        numero: s.numero,
        textoTrecho: s.textoTrecho,
        vigente: s.vigente,
        urlOficial: s.urlOficial,
        applicability: `Aplicável: ${s.diploma} ${s.numero} ${s.tribunal || ""}`,
      }));

    result.applicableLaw = applicableLaw;
    steps[2].status = "done";
    steps[2].result = applicableLaw.length;
  } catch (e) {
    steps[2].status = "error";
    steps[2].error = e instanceof Error ? e.message : "Erro";
    result.applicableLaw = [];
  }

  // ── ETAPA 4: Jurisprudência (web_search) ──────────────────────────────────
  steps[3].status = "running";
  try {
    // Constrói query baseada nas questões jurídicas
    const issues = result.legalIssues || [];
    const searchQuery = issues.length > 0
      ? `jurisprudência STJ ${issues.slice(0, 2).map((i) => i.question).join(" ")}`
      : `jurisprudência ${facts.slice(0, 100)}`;

    const raw = (await zai.functions.invoke("web_search", {
      query: searchQuery,
      num: 8,
    })) as unknown as { url: string; name: string; snippet: string; host_name: string }[];

    result.jurisprudence = Array.isArray(raw)
      ? raw.slice(0, 8).map((r) => ({
          name: r.name,
          url: r.url,
          snippet: r.snippet,
          host_name: r.host_name,
          favorable: null, // será determinado na etapa 5
        }))
      : [];
    steps[3].status = "done";
    steps[3].result = result.jurisprudence.length;
  } catch (e) {
    steps[3].status = "error";
    steps[3].error = e instanceof Error ? e.message : "Erro";
    result.jurisprudence = [];
  }

  // ── ETAPA 5: Análise de viabilidade ───────────────────────────────────────
  steps[4].status = "running";
  try {
    const lawContext = (result.applicableLaw || [])
      .map((l) => `${l.diploma} ${l.numero}: ${l.textoTrecho.slice(0, 150)}`)
      .join("\n");
    const jurisContext = (result.jurisprudence || [])
      .map((j) => `- ${j.name}: ${j.snippet.slice(0, 120)}`)
      .join("\n");

    const completion = await zai.chat.completions.create({
      messages: [
        {
          role: "system",
          content: `Você é um advogado brasileiro sênior emitindo um parecer de viabilidade. Analise o caso com base nos fatos, na legislação aplicável e na jurisprudência encontrada. Seja honesto e conservador. NUNCA prometa resultado. Responda APENAS com JSON:

{"probability":"alta|média|baixa","strengths":["ponto forte 1"],"weaknesses":["ponto fraco 1"],"reasoning":"análise fundamentada conectando fatos, lei e jurisprudência"}`,
        },
        {
          role: "user",
          content: `## Fatos\n${facts}\n\n## Legislação aplicável\n${lawContext}\n\n## Jurisprudência\n${jurisContext}\n\n## Pedidos\n${JSON.stringify(result.requests)}`,
        },
      ],
      thinking: { type: "disabled" },
      temperature: 0.4,
      max_tokens: 1000,
    });
    const raw = completion.choices[0]?.message?.content || "";
    const match = raw.match(/\{[\s\S]*\}/);
    if (match) {
      const parsed = JSON.parse(match[0]);
      result.viability = parsed;
    }
    totalTokens += (completion as unknown as { usage?: { total_tokens?: number } }).usage?.total_tokens || 0;
    steps[4].status = "done";
    steps[4].result = result.viability;
  } catch (e) {
    steps[4].status = "error";
    steps[4].error = e instanceof Error ? e.message : "Erro";
    result.viability = { probability: "média", strengths: [], weaknesses: [], reasoning: "Análise indisponível" };
  }

  // ── ETAPA 6: Lacunas e perguntas ──────────────────────────────────────────
  steps[5].status = "running";
  try {
    const completion = await zai.chat.completions.create({
      messages: [
        {
          role: "system",
          content: `Você é um advogado sênior revisando um caso. Identifique LACUNAS factuais/probatórias e faça PERGUNTAS que o advogado deveria fazer ao cliente. Responda APENAS com JSON:

{"gaps":[{"what":"informação faltante","why":"por que é importante","question":"pergunta para o cliente"}]}`,
        },
        {
          role: "user",
          content: `## Fatos\n${facts}\n\n## Questões jurídicas\n${JSON.stringify(result.legalIssues)}\n\n## Análise\n${JSON.stringify(result.viability)}`,
        },
      ],
      thinking: { type: "disabled" },
      temperature: 0.5,
      max_tokens: 800,
    });
    const raw = completion.choices[0]?.message?.content || "";
    const match = raw.match(/\{[\s\S]*\}/);
    if (match) {
      const parsed = JSON.parse(match[0]);
      result.gaps = parsed.gaps || [];
    }
    totalTokens += (completion as unknown as { usage?: { total_tokens?: number } }).usage?.total_tokens || 0;
    steps[5].status = "done";
    steps[5].result = result.gaps;
  } catch (e) {
    steps[5].status = "error";
    steps[5].error = e instanceof Error ? e.message : "Erro";
    result.gaps = [];
  }

  // ── ETAPA 7: Estratégia recomendada ───────────────────────────────────────
  steps[6].status = "running";
  try {
    const completion = await zai.chat.completions.create({
      messages: [
        {
          role: "system",
          content: `Você é um advogado brasileiro sênior sugerindo estratégia processual. Responda APENAS com JSON:

{"strategy":{"proceduralPath":"caminho processual recomendado","immediateActions":["ação 1"],"documentsToCollect":["documento 1"],"risks":["risco 1"],"recommendation":"recomendação final conservadora"}}`,
        },
        {
          role: "user",
          content: `## Fatos\n${facts}\n\n## Legislação\n${JSON.stringify(result.applicableLaw?.map((l) => l.diploma + " " + l.numero))}\n\n## Viabilidade\n${JSON.stringify(result.viability)}\n\n## Lacunas\n${JSON.stringify(result.gaps)}`,
        },
      ],
      thinking: { type: "disabled" },
      temperature: 0.5,
      max_tokens: 1000,
    });
    const raw = completion.choices[0]?.message?.content || "";
    const match = raw.match(/\{[\s\S]*\}/);
    if (match) {
      const parsed = JSON.parse(match[0]);
      result.strategy = parsed.strategy;
    }
    totalTokens += (completion as unknown as { usage?: { total_tokens?: number } }).usage?.total_tokens || 0;
    steps[6].status = "done";
    steps[6].result = result.strategy;
  } catch (e) {
    steps[6].status = "error";
    steps[6].error = e instanceof Error ? e.message : "Erro";
    result.strategy = { proceduralPath: "", immediateActions: [], documentsToCollect: [], risks: [], recommendation: "Análise indisponível" };
  }

  // Auditoria + ledger
  await logAuditEvent({
    action: "brain_analysis",
    resource: "case",
    resourceId: body.caseId || null,
    metadata: { title, totalTokens, stepsCompleted: steps.filter((s) => s.status === "done").length },
  });
  await logUsageEntry({
    type: "debit",
    operation: "brain_analysis",
    amount: -3,
    reason: `Análise cerebral do caso: ${title}`,
    metadata: { totalTokens, caseId: body.caseId },
  });

  return NextResponse.json({ ...result, steps, totalTokens } as BrainResult);
}
