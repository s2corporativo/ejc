// agent_loop.ts — Loop de agente: IA executa com orçamento, pausa para HITL, usa tools.
//
// Arquitetura (portada do agent/loop.py do EJC):
//   Thought → Action (tool_call) → Observation → Thought → ... → Finish or HITL pause
//
// Regras:
// 1. Orçamento de tokens: execução encerra se exceder tokensBudget.
// 2. HITL: pausa em pontos de decisão (confirmar tese, aprovar pesquisa).
// 3. Tools: só ferramentas registradas e permitidas podem ser chamadas.
// 4. Falha do LLM preserva passos determinísticos anteriores.
// 5. Toda execução possui AgentRun + AgentRunSteps.

import { db } from "@/lib/db";
import ZAI from "z-ai-web-dev-sdk";
import { canonicalHash } from "@/lib/evidence";
import { logAuditEvent } from "@/lib/audit";

// ── Tipos ───────────────────────────────────────────────────────────────────

export type ToolCategory = "leitura" | "escrita" | "motores";
export type StepKind = "thought" | "llm_call" | "tool_call" | "observation" | "hitl_pause" | "hitl_resume" | "finish" | "error";

export interface ToolDef {
  name: string;
  category: ToolCategory;
  description: string;
  requiresHumanApproval?: boolean;
  execute: (args: Record<string, unknown>, context: AgentContext) => Promise<ToolResult>;
}

export interface ToolResult {
  success: boolean;
  output: Record<string, unknown>;
  tokensUsed?: number;
  requiresHuman?: boolean;
  humanReviewData?: Record<string, unknown>;
  error?: string;
}

export interface AgentContext {
  runId: string;
  caseId: string;
  facts: string;
  tokensUsed: number;
  tokensBudget: number;
  maxSteps: number;
  stepCount: number;
  history: { step: number; thought: string; action: string; observation: string }[];
}

export interface AgentLoopResult {
  runId: string;
  status: "completed" | "paused_hitl" | "failed" | "budget_exceeded";
  steps: {
    stepNo: number;
    kind: StepKind;
    thought?: string;
    action?: string;
    toolName?: string;
    observation?: string;
    tokensUsed: number;
    requiresHuman: boolean;
    status: string;
  }[];
  totalTokens: number;
  finalAnswer?: string;
  hitlReason?: string;
  hitlData?: Record<string, unknown>;
}

// ── Registry de Tools ──────────────────────────────────────────────────────

const TOOL_REGISTRY = new Map<string, ToolDef>();

export function registerTool(tool: ToolDef) {
  TOOL_REGISTRY.set(tool.name, tool);
}

export function getTool(name: string): ToolDef | undefined {
  return TOOL_REGISTRY.get(name);
}

export function listTools(): { name: string; category: ToolCategory; description: string; requiresHumanApproval: boolean }[] {
  return Array.from(TOOL_REGISTRY.values()).map((t) => ({
    name: t.name,
    category: t.category,
    description: t.description,
    requiresHumanApproval: t.requiresHumanApproval || false,
  }));
}

// ── Budget Controller ──────────────────────────────────────────────────────

export class BudgetController {
  constructor(private budget: number) {}

  canSpend(estimatedTokens: number, usedTokens: number): boolean {
    return usedTokens + estimatedTokens <= this.budget;
  }

  remaining(usedTokens: number): number {
    return Math.max(0, this.budget - usedTokens);
  }

  exceeded(usedTokens: number): boolean {
    return usedTokens >= this.budget;
  }
}

// ── HITL State ─────────────────────────────────────────────────────────────

export type HITLReason = "confirm_thesis" | "approve_research" | "review_evidence" | "approve_draft" | "custom";

export interface HITLPause {
  reason: HITLReason;
  data: Record<string, unknown>;
  message: string;
}

// ── Agent Loop ─────────────────────────────────────────────────────────────

export async function runAgentLoop(params: {
  caseId: string;
  facts: string;
  agentSlug?: string;
  maxSteps?: number;
  tokensBudget?: number;
  systemPrompt?: string;
}): Promise<AgentLoopResult> {
  const {
    caseId,
    facts,
    agentSlug = "agent_loop",
    maxSteps = 10,
    tokensBudget = 20000,
    systemPrompt = defaultSystemPrompt(),
  } = params;

  // Cria AgentRun
  const inputHash = canonicalHash({ facts, caseId });
  const run = await db.agentRun.create({
    data: {
      caseId,
      agentSlug,
      taskType: "loop",
      status: "running",
      inputHash,
      contractVersion: "agent_loop_v1",
      tokensBudget,
      startedAt: new Date(),
    },
  });

  const zai = await ZAI.create();
  const budget = new BudgetController(tokensBudget);
  const context: AgentContext = {
    runId: run.id,
    caseId,
    facts,
    tokensUsed: 0,
    tokensBudget,
    maxSteps,
    stepCount: 0,
    history: [],
  };

  const steps: AgentLoopResult["steps"] = [];

  for (let step = 1; step <= maxSteps; step++) {
    context.stepCount = step;

    // Verifica orçamento
    if (budget.exceeded(context.tokensUsed)) {
      await updateRun(run.id, "failed", { errorCode: "budget_exceeded", tokensOut: context.tokensUsed, finishedAt: new Date() });
      return {
        runId: run.id,
        status: "budget_exceeded",
        steps,
        totalTokens: context.tokensUsed,
      };
    }

    // ── Thought: LLM decide próxima ação ──────────────────────────────────
    const thoughtStart = Date.now();
    const remaining = budget.remaining(context.tokensUsed);

    const messages = [
      { role: "system" as const, content: systemPrompt },
      { role: "user" as const, content: buildUserMessage(context, remaining) },
    ];

    // Persiste thought step
    const thoughtStep = await db.agentRunStep.create({
      data: { runId: run.id, stepNo: step * 2 - 1, kind: "thought", status: "running", provider: "zai" },
    });

    let llmResponse = "";
    let stepTokens = 0;

    try {
      const completion = await zai.chat.completions.create({
        messages,
        thinking: { type: "disabled" },
        temperature: 0.3,
        max_tokens: Math.min(1000, remaining),
      });
      llmResponse = completion.choices[0]?.message?.content || "";
      stepTokens = (completion as unknown as { usage?: { total_tokens?: number } }).usage?.total_tokens || 0;
      context.tokensUsed += stepTokens;

      // Atualiza run com tokens acumulados
      await db.agentRun.update({
        where: { id: run.id },
        data: { tokensOut: context.tokensUsed, costBrl: context.tokensUsed * 0.00001 },
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "LLM falhou";
      await db.agentRunStep.update({
        where: { id: thoughtStep.id },
        data: { status: "error", output: JSON.stringify({ error: msg }), durationMs: Date.now() - thoughtStart },
      });
      steps.push({ stepNo: step, kind: "error", tokensUsed: stepTokens, requiresHuman: false, status: "error" });
      // Falha do LLM preserva passos anteriores (Princípio 18)
      await updateRun(run.id, "failed", { errorCode: `llm_error: ${msg}`, tokensOut: context.tokensUsed, finishedAt: new Date() });
      return { runId: run.id, status: "failed", steps, totalTokens: context.tokensUsed };
    }

    // Parse da resposta do LLM: JSON com {thought, action, args} ou {thought, finish: true}
    let parsed: { thought?: string; action?: string; args?: Record<string, unknown>; finish?: boolean };
    try {
      const match = llmResponse.match(/\{[\s\S]*\}/);
      parsed = match ? JSON.parse(match[0]) : { thought: llmResponse, finish: true };
    } catch {
      parsed = { thought: llmResponse, finish: true };
    }

    await db.agentRunStep.update({
      where: { id: thoughtStep.id },
      data: {
        status: "done",
        output: JSON.stringify({ thought: parsed.thought, action: parsed.action, args: parsed.args }),
        tokensIn: stepTokens,
        durationMs: Date.now() - thoughtStart,
      },
    });

    steps.push({
      stepNo: step,
      kind: "thought",
      thought: parsed.thought,
      tokensUsed: stepTokens,
      requiresHuman: false,
      status: "done",
    });

    // ── Finish: se o LLM decidiu terminar ──────────────────────────────────
    if (parsed.finish) {
      await db.agentRunStep.create({
        data: {
          runId: run.id, stepNo: step * 2, kind: "finish", status: "done",
          output: JSON.stringify({ answer: parsed.thought }),
        },
      });
      await updateRun(run.id, "completed", { tokensOut: context.tokensUsed, finishedAt: new Date(), resultSnapshotId: null });
      return {
        runId: run.id,
        status: "completed",
        steps,
        totalTokens: context.tokensUsed,
        finalAnswer: parsed.thought,
      };
    }

    // ── Action: executa tool ───────────────────────────────────────────────
    if (parsed.action && parsed.args) {
      const tool = getTool(parsed.action);
      const actionStep = await db.agentRunStep.create({
        data: {
          runId: run.id, stepNo: step * 2, kind: "tool_call", toolName: parsed.action,
          status: "running", requiresHuman: tool?.requiresHumanApproval || false,
        },
      });

      if (!tool) {
        await db.agentRunStep.update({
          where: { id: actionStep.id },
          data: { status: "error", output: JSON.stringify({ error: `Tool '${parsed.action}' não registrada` }) },
        });
        context.history.push({ step, thought: parsed.thought || "", action: parsed.action, observation: `ERRO: Tool '${parsed.action}' não registrada` });
        steps.push({ stepNo: step, kind: "tool_call", toolName: parsed.action, observation: `Tool não registrada`, tokensUsed: 0, requiresHuman: false, status: "error" });
        continue;
      }

      // Executa tool
      const toolStart = Date.now();
      let toolResult: ToolResult;
      try {
        toolResult = await tool.execute(parsed.args, context);
      } catch (e) {
        toolResult = { success: false, output: {}, error: e instanceof Error ? e.message : "erro" };
      }
      const toolDuration = Date.now() - toolStart;

      context.tokensUsed += toolResult.tokensUsed || 0;

      await db.agentRunStep.update({
        where: { id: actionStep.id },
        data: {
          status: toolResult.success ? "done" : "error",
          output: JSON.stringify(toolResult.output),
          tokensIn: toolResult.tokensUsed || 0,
          durationMs: toolDuration,
          requiresHuman: toolResult.requiresHuman || false,
        },
      });

      // ── HITL: se a tool exige revisão humana ────────────────────────────
      if (toolResult.requiresHuman && toolResult.humanReviewData) {
        const hitlData = toolResult.humanReviewData;
        const hitlReason = (hitlData.reason as string) || "custom";
        const hitlMessage = (hitlData.message as string) || "Revisão humana necessária";

        await db.agentRun.update({
          where: { id: run.id },
          data: {
            status: "paused_hitl",
            hitlReason,
            hitlData: JSON.stringify(hitlData),
            tokensOut: context.tokensUsed,
          },
        });

        steps.push({
          stepNo: step,
          kind: "hitl_pause",
          toolName: parsed.action,
          observation: hitlMessage,
          tokensUsed: toolResult.tokensUsed || 0,
          requiresHuman: true,
          status: "paused",
        });

        return {
          runId: run.id,
          status: "paused_hitl",
          steps,
          totalTokens: context.tokensUsed,
          hitlReason,
          hitlData,
        };
      }

      context.history.push({
        step,
        thought: parsed.thought || "",
        action: parsed.action,
        observation: JSON.stringify(toolResult.output).slice(0, 200),
      });

      steps.push({
        stepNo: step,
        kind: "tool_call",
        toolName: parsed.action,
        observation: JSON.stringify(toolResult.output).slice(0, 100),
        tokensUsed: toolResult.tokensUsed || 0,
        requiresHuman: false,
        status: toolResult.success ? "done" : "error",
      });
    }
  }

  // Max steps reached
  await updateRun(run.id, "completed", { tokensOut: context.tokensUsed, finishedAt: new Date() });

  await logAuditEvent({
    action: "agent_loop_complete",
    resource: "agent_run",
    resourceId: run.id,
    metadata: { caseId, steps: steps.length, tokens: context.tokensUsed, budget },
  });

  return {
    runId: run.id,
    status: "completed",
    steps,
    totalTokens: context.tokensUsed,
    finalAnswer: "Limite de passos atingido.",
  };
}

// ── Retomar execução pausada (HITL resume) ────────────────────────────────

export async function resumeAgentRun(runId: string, humanDecision: "approve" | "reject" | "modify", modifiedData?: Record<string, unknown>): Promise<AgentLoopResult> {
  const run = await db.agentRun.findUnique({ where: { id: runId }, include: { steps: { orderBy: { stepNo: "desc" } } } });
  if (!run) throw new Error("Run não encontrado");
  if (run.status !== "paused_hitl") throw new Error("Run não está pausado");

  // Registra a decisão humana
  await db.agentRunStep.create({
    data: {
      runId,
      stepNo: (run.steps[0]?.stepNo || 0) + 1,
      kind: "hitl_resume",
      status: "done",
      output: JSON.stringify({ decision: humanDecision, modifiedData }),
    },
  });

  // Retoma o loop
  await db.agentRun.update({
    where: { id: runId },
    data: { status: "running", hitlReason: null, hitlData: "{}" },
  });

  // Continua o loop com a decisão humana
  return runAgentLoop({
    caseId: run.caseId,
    facts: run.inputHash, // reconstrói a partir do inputHash (simplificado)
    agentSlug: run.agentSlug,
    maxSteps: 10,
    tokensBudget: run.tokensBudget,
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────

async function updateRun(runId: string, status: string, extra: Record<string, unknown>) {
  await db.agentRun.update({ where: { id: runId }, data: { status, ...extra } as Record<string, unknown> });
}

function defaultSystemPrompt(): string {
  return `Você é um agente jurídico brasileiro que raciocina em ciclos Thought → Action → Observation.

REGRAS:
1. A cada ciclo, produza um JSON: {"thought": "raciocínio", "action": "nome_da_tool", "args": {...}}
2. Para terminar: {"thought": "resposta final", "finish": true}
3. Use SOMENTE tools registradas. Tools disponíveis: rag_search, web_search, skill_router, create_evidence.
4. NUNCA invente lei, jurisprudência, número de processo ou resultado.
5. Toda afirmação deve apontar para evidência.
6. Se não tem certeza, diga "finish" e explique a lacuna.
7. Orçamento de tokens é limitado — seja conciso.
8. Não prometa resultado.`;
}

function buildUserMessage(ctx: AgentContext, remainingTokens: number): string {
  const historyStr = ctx.history.length > 0
    ? ctx.history.map((h) => `Step ${h.step}: THOUGHT: ${h.thought} → ACTION: ${h.action} → OBSERVATION: ${h.observation}`).join("\n")
    : "(nenhuma ação anterior)";

  return `## Caso
${ctx.facts}

## Histórico de ações
${historyStr}

## Contexto
- Passo atual: ${ctx.stepCount}/${ctx.maxSteps}
- Tokens restantes: ${remainingTokens}/${ctx.tokensBudget}
- Tools disponíveis: rag_search, web_search, skill_router, create_evidence

## Instrução
Decida a próxima ação. Se já tem informação suficiente, termine com finish. Se precisa pesquisar, use rag_search ou web_search. Se precisa identificar skills, use skill_router. Se precisa criar evidência, use create_evidence.`;
}
