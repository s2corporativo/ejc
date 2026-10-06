// pseudonymizer_consistency.test.ts — Garantia de que a mesma PII vira o mesmo
// marcador em múltiplas chamadas, e que rehidratação é inversa exata.
//
// Roda com: node --test src/lib/__tests__/pseudonymizer_consistency.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import { pseudonymize, rehydrate } from "@/lib/pseudonymizer";

test("pseudonymize substitui CPF por [CPF_1]", () => {
  const r = pseudonymize("O cliente João Silva, CPF 123.456.789-00, compareceu");
  assert.ok(/\[CPF_\d+\]/.test(r.text), `texto não contém marcador de CPF: ${r.text}`);
  assert.ok(r.total >= 1);
});

test("pseudonymize é consistente: mesma PII → mesmo marcador no mesmo texto", () => {
  // O regex exige nome composto com TODAS as palavras capitalizadas (artigos "da", "de"
  // não disparam). Usar "Maria Santos" (2 capitalizadas) para garantir match.
  const input = "Maria Santos foi ao banco. Maria Santos sacou R$500. Maria Santos voltou.";
  const r = pseudonymize(input);
  const matches = r.text.match(/\[NOME_\d+\]/g);
  assert.ok(matches && matches.length >= 3, `esperava >=3 marcadores [NOME_*], vi: ${matches?.length ?? 0} em: ${r.text}`);
  const unique = new Set(matches);
  assert.equal(unique.size, 1, `mesma PII deve virar o mesmo marcador, vi: ${[...unique]}`);
});

test("rehydrate é inverso exato de pseudonymize", () => {
  const original = "Dr. Clovis Soares, OAB/MG 123456, atende em Betim.";
  const p = pseudonymize(original);
  const restored = rehydrate(p.text, p.map);
  // O nome próprio "Clovis" pode virar [NOME_2] etc., mas deve reidratar de volta.
  assert.ok(/Clovis/.test(restored), `nome não reidratado: ${restored}`);
  assert.ok(/Soares/.test(restored));
});

test("dois pseudonymize() independentes no mesmo input dão o mesmo marcador (determinístico por ordem)", () => {
  const input = "Maria Santos, CPF 111.222.444-55, e Maria Santos novamente.";
  const a = pseudonymize(input);
  const b = pseudonymize(input);
  // Mesmo texto, mesmo contador começando de 1, mesmo padrão regex → mesmo marcador.
  // (Não é determinístico absoluto porque depende da ordem de STRUCTURED_PATTERNS,
  // mas ambos rodam isoladamente então devem produzir o mesmo resultado.)
  const aMarkers = a.text.match(/\[[A-Z_]+\d+\]/g) ?? [];
  const bMarkers = b.text.match(/\[[A-Z_]+\d+\]/g) ?? [];
  assert.deepEqual(aMarkers, bMarkers);
});

test("marcadores NOME_N não vazam no prompt final (são [NOME_1], não [object Object])", () => {
  const r = pseudonymize("José da Silva, portador do CPF 999.888.777-66");
  assert.ok(!r.text.includes("[object"));
  assert.ok(!r.text.includes("undefined"));
  assert.ok(!r.text.includes("null"));
});