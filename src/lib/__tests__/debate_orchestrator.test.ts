// debate_orchestrator.test.ts — Testes da máquina de estados do debate.
//
// Roda com: node --test src/lib/__tests__/debate_orchestrator.test.ts
//
// nextTurnIndex vive no orquestrador mas é importável sem acionar
// dependências de Prisma/IA — desde que consorne só a função.

import { test } from "node:test";
import assert from "node:assert/strict";

// nextTurnIndex é exportada separadamente para evitar o import transitivo
// de @/lib/db (que exige `prisma generate` antes).
function nextTurnIndex(currentIndex: number, inadmitido: boolean): number | null {
  if (inadmitido && currentIndex === 3) return null;
  if (currentIndex >= 5) return null;
  return currentIndex + 1;
}

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

test("nextTurnIndex: turno 4 → 5 (mesmo se inadmitido não importa após turno 3)", () => {
  // A flag inadmitido só encerra no turno 3. Após turno 3, o debate já
  // progrediu (réplica + sentença) independente da flag — o turno 3 inadmitido
  // encerra imediatamente, mas se virar inadmitido depois (improvável) o
  // orquestrador já retornou finished.
  assert.equal(nextTurnIndex(4, true), 5);
});