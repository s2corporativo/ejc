// agent_tools.ts — Tools do agente: leitura (RAG, web_search), motores (skill_router), escrita (evidence)
// Portado do agent/tools/ do EJC para TypeScript.

import { registerTool, type ToolResult, type AgentContext } from "@/lib/agent_loop";
import { ragSearch } from "@/lib/rag_lite";
import { createEvidence } from "@/lib/evidence";

// ── Tool 1: RAG Search (leitura) ──────────────────────────────────────────
// Busca na base curada LegalSource com TF-IDF cosine similarity
registerTool({
  name: "rag_search",
  category: "leitura",
  description: "Busca legislação/súmulas na base curada com TF-IDF. Args: {query: string, topK?: number}",
  async execute(args: Record<string, unknown>, ctx: AgentContext): Promise<ToolResult> {
    const query = String(args.query || "");
    const topK = Number(args.topK) || 5;
    if (!query.trim()) return { success: false, output: { error: "query obrigatória" } };

    const results = await ragSearch(query, topK);
    return {
      success: true,
      output: {
        results: results.map((r) => ({
          diploma: r.source.diploma,
          numero: r.source.numero,
          score: r.score,
          trecho: r.source.textoTrecho.slice(0, 200),
          url: r.source.urlOficial,
        })),
        total: results.length,
      },
      tokensUsed: 0, // RAG não usa LLM tokens
    };
  },
});

// ── Tool 2: Web Search (leitura) ─────────────────────────────────────────
// Busca jurisprudência real na web via z-ai-web-dev-sdk
registerTool({
  name: "web_search",
  category: "leitura",
  description: "Busca jurisprudência/fontes na web. Args: {query: string, num?: number}",
  async execute(args: Record<string, unknown>, _ctx: AgentContext): Promise<ToolResult> {
    const query = String(args.query || "");
    const num = Number(args.num) || 5;
    if (!query.trim()) return { success: false, output: { error: "query obrigatória" } };

    try {
      const ZAI = (await import("z-ai-web-dev-sdk")).default;
      const zai = await ZAI.create();
      const raw = (await zai.functions.invoke("web_search", { query: `jurisprudência ${query}`, num })) as unknown as { url: string; name: string; snippet: string; host_name: string }[];

      return {
        success: true,
        output: {
          results: (Array.isArray(raw) ? raw : []).slice(0, num).map((r) => ({
            name: r.name,
            url: r.url,
            snippet: r.snippet.slice(0, 150),
            source: r.host_name,
          })),
          total: Array.isArray(raw) ? raw.length : 0,
        },
        tokensUsed: 0,
      };
    } catch (e) {
      return { success: false, output: { error: e instanceof Error ? e.message : "web_search falhou" } };
    }
  },
});

// ── Tool 3: Skill Router (motores) ──────────────────────────────────────
// Identifica skills jurídicas relevantes para o caso
registerTool({
  name: "skill_router",
  category: "motores",
  description: "Identifica skills jurídicas relevantes a partir dos fatos. Args: {facts: string}",
  async execute(args: Record<string, unknown>, _ctx: AgentContext): Promise<ToolResult> {
    const facts = String(args.facts || "");
    if (!facts.trim()) return { success: false, output: { error: "facts obrigatório" } };

    try {
      const { routeSkills } = await import("@/lib/skill_router");
      const result = await routeSkills(facts);
      return {
        success: true,
        output: {
          area: result.area,
          issues: result.issues,
          skills: result.matches.map((m) => ({ slug: m.slug, name: m.name, score: m.matchScore, triggers: m.matchedTriggers })),
        },
        tokensUsed: 0,
      };
    } catch (e) {
      return { success: false, output: { error: e instanceof Error ? e.message : "skill_router falhou" } };
    }
  },
});

// ── Tool 4: Create Evidence (escrita) ────────────────────────────────────
// Cria EvidenceRef com hash SHA-256 — requer aprovação humana
registerTool({
  name: "create_evidence",
  category: "escrita",
  description: "Cria uma evidência com hash SHA-256 vinculada ao caso. Args: {quote: string, sourceKind?: string}",
  requiresHumanApproval: true,
  async execute(args: Record<string, unknown>, ctx: AgentContext): Promise<ToolResult> {
    const quote = String(args.quote || "");
    const sourceKind = String(args.sourceKind || "llm_extracted");
    if (!quote.trim()) return { success: false, output: { error: "quote obrigatório" } };

    try {
      const evidence = await createEvidence({
        caseId: ctx.caseId,
        quote,
        sourceKind,
        retrievalMethod: "agent_tool",
      });
      return {
        success: true,
        output: { evidenceId: evidence.id, quoteHash: evidence.quoteHash.slice(0, 16), quote: evidence.quote.slice(0, 100) },
        tokensUsed: 0,
        requiresHuman: true,
        humanReviewData: {
          reason: "review_evidence",
          message: `Evidência criada pelo agente: "${evidence.quote.slice(0, 80)}..." — confirme ou rejeite.`,
          evidenceId: evidence.id,
        },
      };
    } catch (e) {
      return { success: false, output: { error: e instanceof Error ? e.message : "create_evidence falhou" } };
    }
  },
});
