import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const DIR = dirname(fileURLToPath(import.meta.url));
const fonte = readFileSync(join(DIR, "CaseCommandDock.tsx"), "utf-8");

describe("CaseCommandDock — Produção Jurídica", () => {
  it("oferece Produzir peça preservando o contexto do caso", () => {
    expect(fonte).toContain('caminhoAbaCaso(caseId, "pecas")');
    expect(fonte).toContain("&acao=produzir");
    expect(fonte).toContain("Produzir peça");
    expect(fonte).toContain("Fila de peças");
  });

  it("não chama diretamente endpoint de geração pelo dock", () => {
    expect(fonte).not.toContain("/api/pecas/gerar");
    expect(fonte).not.toContain("/pecas/gerar");
  });
});
