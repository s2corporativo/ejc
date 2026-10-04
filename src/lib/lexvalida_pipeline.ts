// lexvalida_pipeline.ts — Pipeline de minuta com etapas do LexValida
// PLANEJAR → ROTEIRO → REDIGIR_SECAO → ADERENCIA → CONTRARIA → DISTINGUISHING → AUDITORIA
// Mais: RATIO_DECIDENDI, MOLDE, ESTILO, REFORMULAR

import ZAI from "z-ai-web-dev-sdk";
import { db } from "@/lib/db";
import { ragSearch } from "@/lib/rag_lite";
import {
  SISTEMA_BASE, PLANEJAR, ROTEIRO, REDIGIR_SECAO, ADERENCIA, CONTRARIA,
  DISTINGUISHING, AUDITORIA, RATIO_DECIDENDI, REFORMULAR,
  buildPlanMessage, buildDraftMessage,
} from "@/lib/lexvalida_prompts";
import { logAuditEvent } from "@/lib/audit";

export type PipelinePhase = "planejar" | "roteiro" | "pesquisar" | "redigir" | "verificar_aderencia" | "analise_adversarial" | "distinguishing" | "auditoria";

export interface PipelineStep {
  phase: PipelinePhase;
  status: "pending" | "running" | "done" | "error";
  result?: unknown;
  tokensUsed?: number;
  error?: string;
}

export interface PipelineResult {
  planejamento: {
    resumo_caso: string;
    pontos_chave: string[];
    estrategia: string;
    perguntas: { id: string; pergunta: string; opcoes: string[] }[];
    consultas: { jurisprudencia: string[]; legislacao: string[] };
    alertas: string[];
  } | null;
  roteiro: {
    secoes: { id: string; titulo: string; objetivo: string; pontos: string[] }[];
  } | null;
  pesquisa: {
    jurisprudencia: { id: string; rotulo: string; ementa: string }[];
    legislacao: { id: string; rotulo: string; texto: string }[];
  } | null;
  secoesRedigidas: { id: string; titulo: string; texto: string }[];
  verificacaoAderencia: { classificacao: string; justificativa: string } | null;
  analiseAdversarial: { vulnerabilidades: { ponto: string; argumento_adverso: string; gravidade: string; como_reforcar: string }[] } | null;
  distinguishing: { comparacao: { fato_precedente: string; fato_caso: string; correspondencia: string }[]; conclusao: string; fundamentacao: string } | null;
  auditoria: { injecao: boolean; fabricacao: boolean; confianca: number; justificativa: string } | null;
  steps: PipelineStep[];
  totalTokens: number;
  textoFinal: string;
}

const zai = await ZAI.create();
let totalTokens = 0;

function tok(c: unknown) {
  totalTokens += (c as { usage?: { total_tokens?: number } }).usage?.total_tokens || 0;
}

async function llmCall(system: string, user: string, maxTokens = 1000): Promise<string> {
  const c = await zai.chat.completions.create({
    messages: [
      { role: "system", content: system },
      { role: "user", content: user },
    ],
    thinking: { type: "disabled" },
    temperature: 0.2,
    max_tokens: maxTokens,
  });
  tok(c);
  return c.choices[0]?.message?.content || "";
}

function parseJSON(text: string): Record<string, unknown> | null {
  const match = text.match(/\{[\s\S]*\}/);
  if (!match) return null;
  try { return JSON.parse(match[0]); } catch { return null; }
}

export async function runPipeline(params: {
  pedido: string;
  tipoPeca: string;
  autos: string;
  caseId?: string;
  skillsContent?: string;
}): Promise<PipelineResult> {
  const { pedido, tipoPeca, autos, caseId, skillsContent = "" } = params;
  const steps: PipelineStep[] = [];
  const result: Partial<PipelineResult> = { steps, secoesRedigidas: [], totalTokens: 0 };

  // ── ETAPA 1: PLANEJAR ─────────────────────────────────────────────────
  steps.push({ phase: "planejar", status: "running" });
  try {
    const raw = await llmCall(SISTEMA_BASE + "\n\n" + PLANEJAR, buildPlanMessage(pedido, tipoPeca, autos));
    const parsed = parseJSON(raw);
    if (parsed) {
      result.planejamento = {
        resumo_caso: String(parsed.resumo_caso || ""),
        pontos_chave: (parsed.pontos_chave as string[]) || [],
        estrategia: String(parsed.estrategia || ""),
        perguntas: (parsed.perguntas as { id: string; pergunta: string; opcoes: string[] }[]) || [],
        consultas: {
          jurisprudencia: (parsed.consultas as { jurisprudencia?: string[] })?.jurisprudencia || [],
          legislacao: (parsed.consultas as { legislacao?: string[] })?.legislacao || [],
        },
        alertas: (parsed.alertas as string[]) || [],
      };
    }
    steps[0].status = "done";
    steps[0].result = result.planejamento;
  } catch (e) {
    steps[0].status = "error";
    steps[0].error = e instanceof Error ? e.message : "Erro";
  }

  // ── ETAPA 2: ROTEIRO ──────────────────────────────────────────────────
  steps.push({ phase: "roteiro", status: "running" });
  try {
    const raw = await llmCall(SISTEMA_BASE + "\n\n" + ROTEIRO, `## Planejamento\n${JSON.stringify(result.planejamento)}\n\n## Pedido\n${pedido}`);
    const parsed = parseJSON(raw);
    if (parsed) {
      result.roteiro = { secoes: (parsed.secoes as { id: string; titulo: string; objetivo: string; pontos: string[] }[]) || [] };
    }
    steps[1].status = "done";
    steps[1].result = result.roteiro;
  } catch (e) {
    steps[1].status = "error";
    steps[1].error = e instanceof Error ? e.message : "Erro";
  }

  // ── ETAPA 3: PESQUISAR (RAG + web_search) ────────────────────────────
  steps.push({ phase: "pesquisar", status: "running" });
  try {
    const queries = result.planejamento?.consultas || { jurisprudencia: [pedido], legislacao: [pedido] };
    const jurisprudencia: { id: string; rotulo: string; ementa: string }[] = [];
    const legislacao: { id: string; rotulo: string; texto: string }[] = [];

    // RAG para legislação
    for (const q of (queries.legislacao || [pedido]).slice(0, 3)) {
      const ragResults = await ragSearch(q, 5);
      for (const r of ragResults) {
        legislacao.push({
          id: r.source.id,
          rotulo: `${r.source.diploma} ${r.source.numero}`,
          texto: r.source.textoTrecho.slice(0, 300),
        });
      }
    }

    // web_search para jurisprudência
    for (const q of (queries.jurisprudencia || [pedido]).slice(0, 2)) {
      try {
        const raw = (await zai.functions.invoke("web_search", { query: `jurisprudência ${q}`, num: 5 })) as unknown as { url: string; name: string; snippet: string }[];
        if (Array.isArray(raw)) {
          for (const r of raw.slice(0, 5)) {
            jurisprudencia.push({ id: r.url, rotulo: r.name.slice(0, 100), ementa: r.snippet.slice(0, 200) });
          }
        }
      } catch { /* web_search pode falhar */ }
    }

    result.pesquisa = { jurisprudencia, legislacao };
    steps[2].status = "done";
    steps[2].result = { jurisprudenciaCount: jurisprudencia.length, legislacaoCount: legislacao.length };
  } catch (e) {
    steps[2].status = "error";
    steps[2].error = e instanceof Error ? e.message : "Erro";
  }

  // ── ETAPA 4: REDIGIR SEÇÕES ──────────────────────────────────────────
  steps.push({ phase: "redigir", status: "running" });
  try {
    const secoes = result.roteiro?.secoes || [];
    const pesquisa = result.pesquisa || { jurisprudencia: [], legislacao: [] };
    for (const secao of secoes) {
      const raw = await llmCall(
        SISTEMA_BASE + "\n\n" + REDIGIR_SECAO,
        buildDraftMessage(secao, pesquisa, autos, skillsContent),
        800,
      );
      result.secoesRedigidas!.push({ id: secao.id, titulo: secao.titulo, texto: raw });
    }
    steps[3].status = "done";
    steps[3].result = result.secoesRedigidas!.length;
  } catch (e) {
    steps[3].status = "error";
    steps[3].error = e instanceof Error ? e.message : "Erro";
  }

  // ── ETAPA 5: VERIFICAR ADERÊNCIA ─────────────────────────────────────
  steps.push({ phase: "verificar_aderencia", status: "running" });
  try {
    const textoPeca = result.secoesRedigidas?.map((s) => s.texto).join("\n\n") || "";
    const precedente = result.pesquisa?.jurisprudencia?.[0];
    if (precedente) {
      const raw = await llmCall(SISTEMA_BASE + "\n\n" + ADERENCIA,
        `## Afirmação da peça\n${textoPeca.slice(0, 500)}\n\n## Precedente (${precedente.rotulo})\n${precedente.ementa}`);
      const parsed = parseJSON(raw);
      if (parsed) {
        result.verificacaoAderencia = {
          classificacao: String(parsed.classificacao || ""),
          justificativa: String(parsed.justificativa || ""),
        };
      }
    }
    steps[4].status = "done";
    steps[4].result = result.verificacaoAderencia;
  } catch (e) {
    steps[4].status = "error";
    steps[4].error = e instanceof Error ? e.message : "Erro";
  }

  // ── ETAPA 6: ANÁLISE ADVERSARIAL ─────────────────────────────────────
  steps.push({ phase: "analise_adversarial", status: "running" });
  try {
    const textoPeca = result.secoesRedigidas?.map((s) => s.texto).join("\n\n") || "";
    const raw = await llmCall(SISTEMA_BASE + "\n\n" + CONTRARIA,
      `## Peça a criticar\n${textoPeca.slice(0, 1500)}`);
    const parsed = parseJSON(raw);
    if (parsed) {
      result.analiseAdversarial = {
        vulnerabilidades: (parsed.vulnerabilidades as { ponto: string; argumento_adverso: string; gravidade: string; como_reforcar: string }[]) || [],
      };
    }
    steps[5].status = "done";
    steps[5].result = result.analiseAdversarial?.vulnerabilidades.length;
  } catch (e) {
    steps[5].status = "error";
    steps[5].error = e instanceof Error ? e.message : "Erro";
  }

  // ── ETAPA 7: DISTINGUISHING ──────────────────────────────────────────
  steps.push({ phase: "distinguishing", status: "running" });
  try {
    const precedente = result.pesquisa?.jurisprudencia?.[0];
    if (precedente) {
      // Extrai ratio decidendi
      const ratioRaw = await llmCall(SISTEMA_BASE + "\n\n" + RATIO_DECIDENDI,
        `## Precedente (${precedente.rotulo})\n${precedente.ementa}`);
      const ratioParsed = parseJSON(ratioRaw);
      const fatosPrecedente = (ratioParsed?.fatos_materiais as string[]) || [];

      // Compara com fatos do caso
      const distRaw = await llmCall(SISTEMA_BASE + "\n\n" + DISTINGUISHING,
        `## Fatos materiais do precedente\n${fatosPrecedente.map((f, i) => `${i + 1}. ${f}`).join("\n")}\n\n## Fatos do caso\n${autos.slice(0, 500)}`);
      const distParsed = parseJSON(distRaw);
      if (distParsed) {
        result.distinguishing = {
          comparacao: (distParsed.comparacao as { fato_precedente: string; fato_caso: string; correspondencia: string }[]) || [],
          conclusao: String(distParsed.conclusao || ""),
          fundamentacao: String(distParsed.fundamentacao || ""),
        };
      }
    }
    steps[6].status = "done";
    steps[6].result = result.distinguishing?.conclusao;
  } catch (e) {
    steps[6].status = "error";
    steps[6].error = e instanceof Error ? e.message : "Erro";
  }

  // ── ETAPA 8: AUDITORIA DE SEGURANÇA ──────────────────────────────────
  steps.push({ phase: "auditoria", status: "running" });
  try {
    const textoPeca = result.secoesRedigidas?.map((s) => s.texto).join("\n\n") || "";
    const raw = await llmCall(SISTEMA_BASE + "\n\n" + AUDITORIA,
      `## Raciocínio do redator\n${textoPeca.slice(0, 1000)}\n\n## Pedido original\n${pedido}`);
    const parsed = parseJSON(raw);
    if (parsed) {
      result.auditoria = {
        injecao: Boolean(parsed.injecao),
        fabricacao: Boolean(parsed.fabricacao),
        confianca: Number(parsed.confianca) || 0,
        justificativa: String(parsed.justificativa || ""),
      };
    }
    steps[7].status = "done";
    steps[7].result = result.auditoria;
  } catch (e) {
    steps[7].status = "error";
    steps[7].error = e instanceof Error ? e.message : "Erro";
  }

  // ── Monta texto final ─────────────────────────────────────────────────
  const textoFinal = (result.secoesRedigidas || []).map((s) => s.texto).join("\n\n");

  await logAuditEvent({
    action: "lexvalida_pipeline",
    resource: "case",
    resourceId: caseId || null,
    metadata: {
      steps: steps.length,
      done: steps.filter((s) => s.status === "done").length,
      totalTokens,
      secoesRedigidas: result.secoesRedigidas?.length || 0,
      aderencia: result.verificacaoAderencia?.classificacao,
      adversarialCount: result.analiseAdversarial?.vulnerabilidades.length,
      distinguishing: result.distinguishing?.conclusao,
      injecao: result.auditoria?.injecao,
      fabricacao: result.auditoria?.fabricacao,
    },
  });

  return { ...result, steps, totalTokens, textoFinal } as PipelineResult;
}
