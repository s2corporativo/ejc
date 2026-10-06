// llm.test.ts — Testes do wrapper LLM compartilhado (fallback multi-provider).
//
// Roda com: node --test src/lib/__tests__/llm.test.ts
//
// Verifica que o wrapper:
//   1. Retorna erro estruturado quando nenhum provider é elegível
//   2. listConfiguredProviders retorna array de providers habilitados
//   3. listConfiguredProviders NÃO inclui providers desabilitados
//
// Não mockamos o z-ai-web-dev-sdk porque o node:test runner não suporta
// mock.module. Em vez disso, validamos contratos que NÃO disparam LLM:
// o caminho de erro quando nenhum provider está elegível.

import { test } from "node:test";
import assert from "node:assert/strict";

test("llmCall retorna erro se provider falha (sem rede / sem API key)", async () => {
  const { llmCall } = await import("@/lib/llm");
  // taskType inválido cai em "default" → tenta zai → falha (sem config)
  await assert.rejects(
    () => llmCall("sys", "user", { taskType: "task_type_totalmente_inexistente_99999" }),
    /Todos os providers falharam|provider.*falhou|Nenhum provider elegível/,
  );
});

test("listConfiguredProviders retorna array de strings", async () => {
  const { listConfiguredProviders } = await import("@/lib/llm");
  const list = listConfiguredProviders();
  assert.ok(Array.isArray(list));
  assert.ok(list.length > 0, "esperava pelo menos 1 provider habilitado");
});

test("listConfiguredProviders inclui zai (default habilitado)", async () => {
  const { listConfiguredProviders } = await import("@/lib/llm");
  const list = listConfiguredProviders();
  assert.ok(list.includes("zai"), `esperava zai habilitado, vi: ${list.join(", ")}`);
});

test("listConfiguredProviders NÃO inclui providers desabilitados (anthropic, groq, maritaca)", async () => {
  const { listConfiguredProviders } = await import("@/lib/llm");
  const list = listConfiguredProviders();
  // Por padrão estes vêm enabled=false no registry
  assert.ok(!list.includes("anthropic"), `anthropic não deveria estar habilitado, vi: ${list.join(", ")}`);
  assert.ok(!list.includes("groq"), `groq não deveria estar habilitado, vi: ${list.join(", ")}`);
  assert.ok(!list.includes("maritaca"), `maritaca não deveria estar habilitado, vi: ${list.join(", ")}`);
});