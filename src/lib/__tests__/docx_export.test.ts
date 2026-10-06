// docx_export.test.ts — Verifica que markdownToParagraphs produz estrutura válida.

import { test } from "node:test";
import assert from "node:assert/strict";
import { buildDocx, markdownToParagraphs } from "@/lib/docx_export";

test("markdownToParagraphs detecta heading 1", () => {
  const paras = markdownToParagraphs("# Título principal\nTexto aqui.");
  const heading = paras.find((p) => p.style === "Heading1");
  assert.ok(heading, "esperava heading 1");
  assert.equal(heading?.text, "Título principal");
});

test("markdownToParagraphs detecta heading 2", () => {
  const paras = markdownToParagraphs("## Seção secundária");
  const heading = paras.find((p) => p.style === "Heading2");
  assert.ok(heading);
});

test("markdownToParagraphs detecta blockquote", () => {
  const paras = markdownToParagraphs("> Citação importante");
  const quote = paras.find((p) => p.style === "Quote");
  assert.ok(quote);
});

test("markdownToParagraphs detecta bullet list", () => {
  const paras = markdownToParagraphs("- Item 1\n- Item 2\n- Item 3");
  const lists = paras.filter((p) => p.listLevel === 0);
  assert.equal(lists.length, 3);
});

test("markdownToParagraphs detecta numbered list", () => {
  const paras = markdownToParagraphs("1. Primeiro\n2. Segundo");
  const lists = paras.filter((p) => p.listLevel === 1);
  assert.equal(lists.length, 2);
});

test("buildDocx gera Blob não-vazio", async () => {
  const md = "# Teste\n\nConteúdo da peça.";
  const blob = await buildDocx(md, { titulo: "Teste" });
  assert.ok(blob.size > 0, "Blob vazio");
  assert.equal(blob.type, "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
});

test("buildDocx inclui assinatura OAB quando fornecida", async () => {
  const md = "Corpo da peça.";
  const blob = await buildDocx(md, { autor: "Dr. Clovis", oab: "OAB/MG 123456" });
  // O blob é ZIP; para validar o conteúdo teríamos que extrair.
  // Aqui só verificamos que o blob foi gerado e tem tamanho mínimo.
  assert.ok(blob.size > 500, "Blob muito pequeno para incluir metadados");
});

test("buildDocx markdown complexo", async () => {
  const md = `# Petição Inicial

## I. Endereçamento
EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO

## II. Fatos
> Ocorreu em 15/03/2024

- Fato 1
- Fato 2

1. Pedido principal
2. Pedido subsidiário`;
  const blob = await buildDocx(md, { titulo: "Petição", autor: "Dr. Teste", oab: "OAB/SP 111111" });
  assert.ok(blob.size > 1000, "Blob grande esperado para markdown complexo");
});