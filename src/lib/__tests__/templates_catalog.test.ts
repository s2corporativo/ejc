// templates_catalog.test.ts — Verifica o catálogo curado de templates.

import { test } from "node:test";
import assert from "node:assert/strict";
import { TEMPLATES, templatesByArea, coreTemplates, totalTemplates } from "@/lib/templates_catalog";

test("Catálogo tem pelo menos 20 templates", () => {
  assert.ok(totalTemplates() >= 20, `esperado >= 20, vi ${totalTemplates()}`);
});

test("Cada template tem slug, nome, área, tipoPeca, campos e tags", () => {
  for (const t of TEMPLATES) {
    assert.ok(t.slug, "slug vazio");
    assert.ok(t.nome, "nome vazio");
    assert.ok(t.area, `área vazia em ${t.slug}`);
    assert.ok(t.tipoPeca, `tipoPeca vazio em ${t.slug}`);
    assert.ok(Array.isArray(t.campos), `campos não-array em ${t.slug}`);
    assert.ok(Array.isArray(t.tags), `tags não-array em ${t.slug}`);
  }
});

test("Slugs são únicos", () => {
  const slugs = TEMPLATES.map((t) => t.slug);
  const unique = new Set(slugs);
  assert.equal(slugs.length, unique.size, "slugs duplicados");
});

test("templatesByArea('civil') retorna templates da área civil", () => {
  const civil = templatesByArea("civil");
  assert.ok(civil.length > 0);
  for (const t of civil) {
    assert.equal(t.area, "civil");
  }
});

test("coreTemplates() retorna apenas os com tag 'core'", () => {
  const core = coreTemplates();
  for (const t of core) {
    assert.ok(t.tags.includes("core"), `${t.slug} deveria ter tag 'core'`);
  }
  assert.ok(core.length > 0);
});

test("Cobertura das 11 áreas jurídicas (incluindo ambiental e digital)", () => {
  const areas = new Set(TEMPLATES.map((t) => t.area));
  const obrigatorias = ["civil", "consumidor", "trabalhista", "previdenciario", "processo_penal", "tributario", "administrativo", "ambiental", "digital"];
  for (const a of obrigatorias) {
    assert.ok(areas.has(a), `área ${a} não tem templates`);
  }
});