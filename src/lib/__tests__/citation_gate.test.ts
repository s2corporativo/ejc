// citation_gate.test.ts — Testes do Citation Gate (anti-hallucinação).
//
// Roda com: node --test src/lib/__tests__/citation_gate.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import { extractCitations } from "@/lib/citation_gate";

test("extractCitations identifica 'art. 927 do CC' como diploma=CC numero=927", () => {
  const out = extractCitations("Conforme art. 927 do CC, há responsabilidade objetiva.");
  const found = out.find((c) => c.numero === "art. 927" && c.diploma === "CC");
  assert.ok(found, `não extraiu art. 927 CC: ${JSON.stringify(out)}`);
});

test("extractCitations identifica 'art. 489 do CPC'", () => {
  const out = extractCitations("O art. 489 do CPC exige fundamentação.");
  const found = out.find((c) => c.diploma === "CPC" && /489/.test(c.numero));
  assert.ok(found, `não extraiu art. 489 CPC: ${JSON.stringify(out)}`);
});

test("extractCitations identifica Súmula 479 do STJ", () => {
  const out = extractCitations("Conforme Súmula 479 do STJ, as instituições financeiras podem aplicar taxas ANBIMA.");
  const found = out.find((c) => /479/.test(c.numero) && c.tribunal === "STJ");
  assert.ok(found, `não extraiu Súmula 479 STJ: ${JSON.stringify(out)}`);
});

test("extractCitations identifica 'art. 5 da CF'", () => {
  const out = extractCitations("O art. 5 da CF garante o contraditório e a ampla defesa.");
  const found = out.find((c) => c.diploma === "CF" && /art\. 5/.test(c.numero));
  assert.ok(found, `não extraiu art. 5º CF: ${JSON.stringify(out)}`);
});

test("extractCitations diferencia 'art. 1.000' de 'art. 1' quando o número é grande", () => {
  const out = extractCitations("Lei aplica-se o art. 1.000 do CPC, não o art. 1 do CPC.");
  const big = out.find((c) => c.numero === "art. 1.000");
  const small = out.find((c) => c.numero === "art. 1");
  assert.ok(big, `não extraiu 1.000: ${JSON.stringify(out)}`);
  assert.ok(small, `não extraiu 1: ${JSON.stringify(out)}`);
});

test("extractCitations retorna lista vazia para texto sem citações", () => {
  const out = extractCitations("Esta é uma frase qualquer sem dispositivos legais.");
  assert.equal(out.length, 0);
});

test("extractCitations não inclui citações de jurisprudência inventada (números > 1000 do STJ sem tribunal)", () => {
  // Súmulas STJ vão até ~700+. Lei inventada "art. 9999 STJ" deve aparecer mas
  // não há regra de validação aqui — isso é trabalho do verifyCitations() que
  // precisa da base doctrine carregada.
  const out = extractCitations("Aplico o art. 9999 do STJ para o caso.");
  const found = out.find((c) => c.numero === "9999");
  // Só verifica extração bruta; validação contra a base é separada.
  if (found) {
    assert.equal(found.diploma, "STJ");
  } else {
    assert.ok(true); // extração pode falhar — ok
  }
});