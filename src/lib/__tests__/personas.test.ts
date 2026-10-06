// personas.test.ts — Testes focado da 5 turnos + inadmissão.
//
// Roda com: node --test src/lib/__tests__/personas.test.ts
// Usa node --test (built-in) + node:assert/strict. Zero deps.

import { test } from "node:test";
import assert from "node:assert/strict";
import { PERSONAS, DEBATE_TURNS, isCasoPenal } from "@/lib/personas";

test("PERSONAS tem exatamente 3 personas: advogado, juiz, promotor", () => {
  assert.deepEqual(
    Object.keys(PERSONAS).sort(),
    ["advogado", "juiz", "promotor"],
  );
});

test("Cada persona tem systemPrompt > 200 caracteres (não vazio)", () => {
  for (const [slug, p] of Object.entries(PERSONAS)) {
    assert.ok(p.systemPrompt.length > 200, `systemPrompt vazio em ${slug}`);
    assert.ok(Array.isArray(p.baseAreas) && p.baseAreas.length > 0, `baseAreas vazio em ${slug}`);
    assert.ok(typeof p.artifactKind === "string", `artifactKind ausente em ${slug}`);
    assert.ok(typeof p.color === "string", `color ausente em ${slug}`);
  }
});

test("DEBATE_TURNS tem 5 turnos na ordem correta", () => {
  assert.equal(DEBATE_TURNS.length, 5);
  const expected = [
    { turnNumber: 1, persona: "advogado", subRole: "tese" },
    { turnNumber: 2, persona: "promotor", subRole: "contrario" },
    { turnNumber: 3, persona: "juiz", subRole: "admissibilidade" },
    { turnNumber: 4, persona: "advogado", subRole: "replica" },
    { turnNumber: 5, persona: "juiz", subRole: "sentenca" },
  ];
  for (let i = 0; i < 5; i++) {
    assert.equal(DEBATE_TURNS[i].turnNumber, expected[i].turnNumber);
    assert.equal(DEBATE_TURNS[i].persona, expected[i].persona);
    assert.equal(DEBATE_TURNS[i].subRole, expected[i].subRole);
  }
});

test("isCasoPenal detecta penal e processo_penal", () => {
  assert.equal(isCasoPenal("penal"), true);
  assert.equal(isCasoPenal("processo_penal"), true);
  assert.equal(isCasoPenal("civil"), false);
  assert.equal(isCasoPenal("consumidor"), false);
  assert.equal(isCasoPenal("ambiental"), false);
  assert.equal(isCasoPenal("digital"), false);
});

test("System prompts proíbem promessa de resultado (vedação OAB)", () => {
  for (const [slug, p] of Object.entries(PERSONAS)) {
    // Cada persona deve conter a regra explícita "NUNCA prometa"
    assert.ok(
      /NUNCA\s+prometa|N[ãa]o\s+prometa|nunca\s+garanta|N[ãa]o\s+garanta/i.test(p.systemPrompt),
      `systemPrompt de ${slug} não contém vedação explícita de promessa de resultado`,
    );
  }
});

test("System prompts exigem preservar marcadores [NOME_X] (pseudonimização)", () => {
  for (const [slug, p] of Object.entries(PERSONAS)) {
    const hasMarkerAwareness =
      /\[NOME|\[CPF|\[RG|Marcador|marcador/i.test(p.systemPrompt);
    assert.ok(hasMarkerAwareness, `systemPrompt de ${slug} não menciona preservação de marcadores`);
  }
});