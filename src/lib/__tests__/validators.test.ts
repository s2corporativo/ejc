// validators.test.ts — Testes dos validadores determinísticos pré-geração.

import { test } from "node:test";
import assert from "node:assert/strict";
import { validatePeticao, summarizeIssues } from "@/lib/validators";

test("Detecta valor da causa ausente", () => {
  const issues = validatePeticao({
    fatos: "Fatos do caso de teste para validar o sistema. " + "x".repeat(100),
    area: "civil",
    templateSlug: "pet-inicial-civel",
  });
  const errors = issues.filter((i) => i.severity === "error");
  assert.ok(errors.some((e) => e.rule === "VALOR_CAUSA_OBRIGATORIO"));
});

test("Detecta partes ausentes", () => {
  const issues = validatePeticao({
    fatos: "Houve um acidente automobilístico. " + "x".repeat(100),
    valorCausa: "R$ 10.000,00",
    area: "civil",
    templateSlug: "pet-inicial-civel",
  });
  const warnings = issues.filter((i) => i.severity === "warning");
  assert.ok(warnings.some((w) => w.rule === "PARTES_AUTOR"));
  assert.ok(warnings.some((w) => w.rule === "PARTES_REU"));
});

test("Detecta OAB do signatário", () => {
  const issues = validatePeticao({
    fatos: "João foi réu em ação de cobrança. " + "x".repeat(100),
    valorCausa: "R$ 5.000,00",
    area: "civil",
    templateSlug: "pet-inicial-civel",
  });
  const warnings = issues.filter((i) => i.severity === "warning");
  assert.ok(warnings.some((w) => w.rule === "OAB_SIGNATARIO"));
});

test("Aceita peça completa (sem issues error)", () => {
  const issues = validatePeticao({
    fatos: `O autor João da Silva, OAB/MG 123456, ajuizou ação de cobrança contra o réu. Comarca de Betim - MG, em 15/03/2024. ` + "x".repeat(200),
    valorCausa: "R$ 10.000,00",
    pedidos: "Condenação ao pagamento de R$ 10.000,00 mais juros e correção monetária desde 15/03/2024",
    area: "civil",
    templateSlug: "pet-inicial-civel",
  });
  const errors = issues.filter((i) => i.severity === "error");
  assert.equal(errors.length, 0, `esperado 0 errors, vi: ${errors.map((e) => e.rule).join(", ")}`);
});

test("Detecta área inválida", () => {
  const issues = validatePeticao({
    fatos: "Fatos " + "x".repeat(200),
    valorCausa: "R$ 1.000,00",
    area: "area_inexistente",
    templateSlug: "qualquer",
  });
  const errors = issues.filter((i) => i.severity === "error");
  assert.ok(errors.some((e) => e.rule === "AREA_INVALIDA"));
});

test("summarizeIssues conta corretamente", () => {
  const issues = [
    { rule: "x", severity: "error" as const, message: "" },
    { rule: "y", severity: "warning" as const, message: "" },
    { rule: "z", severity: "info" as const, message: "" },
    { rule: "w", severity: "error" as const, message: "" },
  ];
  const s = summarizeIssues(issues);
  assert.equal(s.errors, 2);
  assert.equal(s.warnings, 1);
  assert.equal(s.infos, 1);
});