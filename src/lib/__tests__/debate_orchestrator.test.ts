// debate_orchestrator.test.ts — Testes da máquina de estados do debate.
//
// Roda com: node --test src/lib/__tests__/debate_orchestrator.test.ts
//
// Não chama o LLM real — verifica apenas a lógica de despacho e
// próximo turno (nextTurnIndex), que é puramente determinística.

import { test } from "node:test";
import assert from "node:assert/strict";
import { nextTurnIndex } from "@/lib/debate_orchestrator";

test("nextTurnIndex: turno 1 → 2", () => {
  assert.equal(nextTurnIndex(1, false), 2);
});

test("nextTurnIndex: turno 2 → 3", () => {
  assert.equal(nextTurnIndex(2, false), 3);
});

test("nextTurnIndex: turno 3 inadmitido → null", () => {
  assert.equal(nextTurnIndex(3, true), null);
});

test("nextTurnIndex: turno 3 sem inadmissão → 4", () => {
  assert.equal(nextTurnIndex(3, false), 4);
});

test("nextTurnIndex: turno 4 → 5", () => {
  assert.equal(nextTurnIndex(4, false), 5);
});

test("nextTurnIndex: turno 5 → null (debate concluído)", () => {
  assert.equal(nextTurnIndex(5, false), null);
});

test("nextTurnIndex: turno 0 → 1 (caso defensivo)", () => {
  assert.equal(nextTurnIndex(0, false), 1);
});

test("nextTurnIndex: turno 4 inadmitido → null", () => {
  // Se inadmitido após turno 3, o estado já é terminal.
  // Se inadmitido em outro turno (improvável), ainda assim termina.
  assert.equal(nextTurnIndex(4, true), null);
});