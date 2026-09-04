import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const DIR = dirname(fileURLToPath(import.meta.url));
const fonte = readFileSync(join(DIR, "TabPecas.tsx"), "utf-8");

describe("TabPecas — Produção Jurídica contextual", () => {
  it("reutiliza o gerador e a fila canônicos, sem endpoint paralelo", () => {
    expect(fonte).toContain('import Pecas from "../Pecas"');
    expect(fonte).toContain('import PecaGeneratorModal from "../../components/PecaGeneratorModal"');
    expect(fonte).toContain("caseId={caseId}");
    expect(fonte).toContain("<Pecas key={refreshKey} />");
    expect(fonte).not.toContain("/pecas/gerar");
    expect(fonte).not.toContain("/legal-docs/");
  });

  it("aceita deep-link de produção e volta para a aba canônica", () => {
    expect(fonte).toContain('searchParams.get("acao") !== "produzir"');
    expect(fonte).toContain('setSearchParams({ tab: "pecas" }, { replace: true })');
    expect(fonte).toContain("Produzir peça a partir deste caso");
  });

  it("mantém revisão humana explícita na comunicação da tela", () => {
    expect(fonte).toContain("revisão humana");
    expect(fonte).toContain("HITL, aprovação e protocolo");
  });
});
