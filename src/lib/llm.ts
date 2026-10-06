// llm.ts — Wrapper compartilhado de LLM com fallback multi-provider.
//
// Substitui a função `llmCall` privada em lexvalida_pipeline.ts por uma
// versão pública que:
//   1. Tenta o provider primário (zai)
//   2. Em caso de falha, tenta o próximo provider elegível
//   3. Aplica sanitização (pseudonimização) ANTES da chamada
//   4. Reidrata o resultado
//   5. Marca como rascunho (ensureDraftMarker)
//
// Fail-closed: se nenhum provider está elegível, lança erro estruturado.

import ZAI from "z-ai-web-dev-sdk";
import { PROVIDERS, resolveProviders, ensureDraftMarker } from "@/lib/ai_governance";
import { pseudonymize, rehydrate } from "@/lib/pseudonymizer";

// Acesso a process.env pode não existir em alguns runners (ex: edge). Wrapper seguro.
function getEnv(key: string): string | undefined {
  try {
    // @ts-expect-error — process pode não estar declarado dependendo do tsconfig
    return typeof process !== "undefined" && process && process.env ? process.env[key] : undefined;
  } catch {
    return undefined;
  }
}

export interface LlmCallOptions {
  taskType: string; // ex: "minuta", "debate_advogado", "analise_caso"
  temperature?: number;
  maxTokens?: number;
  // Se true, NÃO pseudonimiza (para providers locais onde LGPD não exige)
  skipPseudonymization?: boolean;
  // Se true, NÃO aplica ensureDraftMarker (casos extremos)
  skipDraftMarker?: boolean;
}

export interface LlmCallResult {
  content: string;
  tokensUsed: number;
  provider: string; // qual provider respondeu
  fallback: boolean; // se houve fallback do primário
  latencyMs: number;
  pseudonymizationApplied: boolean;
}

/**
 * Wrapper público de LLM. Pseudonimiza antes, reidrata depois, marca como
 * rascunho, e tenta fallback automático entre providers.
 */
export async function llmCall(
  systemPrompt: string,
  userPrompt: string,
  options: LlmCallOptions = { taskType: "default" },
): Promise<LlmCallResult> {
  const start = Date.now();
  const providers = resolveProviders(options.taskType);

  if (providers.length === 0) {
    throw new Error(
      `Nenhum provider elegível para taskType='${options.taskType}'. ` +
        `Verifique AI_ENABLED, AI_EXTERNAL_PROVIDERS_ALLOWED e o registry PROVIDERS.`,
    );
  }

  // Pseudonimização antes de qualquer chamada externa
  let effectiveUser = userPrompt;
  let pseudoMap: ReturnType<typeof pseudonymize>["map"] | null = null;
  if (!options.skipPseudonymization) {
    const p = pseudonymize(userPrompt);
    effectiveUser = p.text;
    pseudoMap = p.map;
  }

  // Tenta cada provider em ordem até um funcionar
  let lastError: Error | null = null;
  for (let i = 0; i < providers.length; i++) {
    const provider = providers[i];
    const fallback = i > 0;
    try {
      const content = await callProvider(
        provider.name,
        systemPrompt,
        effectiveUser,
        options.temperature ?? 0.3,
        options.maxTokens ?? 1500,
      );
      // Reidratação
      let finalContent = pseudoMap ? rehydrate(content, pseudoMap) : content;
      if (!options.skipDraftMarker) {
        finalContent = ensureDraftMarker(finalContent);
      }
      const tokensUsed = 0; // será preenchido em callProvider quando disponível
      return {
        content: finalContent,
        tokensUsed,
        provider: provider.name,
        fallback,
        latencyMs: Date.now() - start,
        pseudonymizationApplied: !options.skipPseudonymization,
      };
    } catch (e) {
      lastError = e as Error;
      console.error(`[llm] provider ${provider.name} falhou:`, (e as Error).message);
      // tenta o próximo
    }
  }

  throw new Error(
    `Todos os providers falharam para taskType='${options.taskType}'. ` +
      `Último erro: ${lastError?.message || "desconhecido"}`,
  );
}

async function callProvider(
  providerName: string,
  system: string,
  user: string,
  temperature: number,
  maxTokens: number,
): Promise<string> {
  switch (providerName) {
    case "zai": {
      const zai = await ZAI.create();
      const c = await zai.chat.completions.create({
        messages: [
          { role: "system", content: system },
          { role: "user", content: user },
        ],
        thinking: { type: "disabled" },
        temperature,
        max_tokens: maxTokens,
      });
      return c.choices[0]?.message?.content || "";
    }
    case "ollama": {
      // Endpoint local (configurável via env). Implementação mínima.
      const baseUrl = getEnv("OLLAMA_BASE_URL") || "http://localhost:11434";
      const model = getEnv("OLLAMA_MODEL") || "llama3";
      const res = await fetch(`${baseUrl}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model,
          messages: [
            { role: "system", content: system },
            { role: "user", content: user },
          ],
          stream: false,
          options: { temperature, num_predict: maxTokens },
        }),
      });
      if (!res.ok) throw new Error(`Ollama ${res.status}: ${await res.text()}`);
      const data = (await res.json()) as { message?: { content?: string } };
      return data.message?.content || "";
    }
    case "anthropic": {
      const apiKey = getEnv("ANTHROPIC_API_KEY");
      if (!apiKey) throw new Error("ANTHROPIC_API_KEY não configurada");
      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": apiKey,
          "anthropic-version": "2023-06-01",
        },
        body: JSON.stringify({
          model: "claude-haiku-4-5-20251001",
          max_tokens: maxTokens,
          temperature,
          system,
          messages: [{ role: "user", content: user }],
        }),
      });
      if (!res.ok) throw new Error(`Anthropic ${res.status}: ${await res.text()}`);
      const data = (await res.json()) as { content?: { text?: string }[] };
      return data.content?.[0]?.text || "";
    }
    case "groq": {
      const apiKey = getEnv("GROQ_API_KEY");
      if (!apiKey) throw new Error("GROQ_API_KEY não configurada");
      const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify({
          model: "llama-3.1-70b-versatile",
          messages: [
            { role: "system", content: system },
            { role: "user", content: user },
          ],
          temperature,
          max_tokens: maxTokens,
        }),
      });
      if (!res.ok) throw new Error(`Groq ${res.status}: ${await res.text()}`);
      const data = (await res.json()) as { choices?: { message?: { content?: string } }[] };
      return data.choices?.[0]?.message?.content || "";
    }
    case "maritaca": {
      const apiKey = getEnv("MARITACA_API_KEY");
      if (!apiKey) throw new Error("MARITACA_API_KEY não configurada");
      const res = await fetch("https://chat.maritaca.ai/api/v1/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify({
          model: "sabia-3",
          messages: [
            { role: "system", content: system },
            { role: "user", content: user },
          ],
          temperature,
          max_tokens: maxTokens,
        }),
      });
      if (!res.ok) throw new Error(`Maritaca ${res.status}: ${await res.text()}`);
      const data = (await res.json()) as { choices?: { message?: { content?: string } }[] };
      return data.choices?.[0]?.message?.content || "";
    }
    default:
      throw new Error(`Provider '${providerName}' não implementado em llm.ts`);
  }
}

/** Versão sync de quais providers estão configurados. */
export function listConfiguredProviders(): string[] {
  return Object.values(PROVIDERS)
    .filter((p) => p.enabled)
    .map((p) => p.name);
}