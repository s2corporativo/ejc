import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const DIR = dirname(fileURLToPath(import.meta.url));
const fonte = readFileSync(join(DIR, "Pecas.tsx"), "utf-8");

describe("Peças — Workspace Jurídico", () => {
  it("permite editar pelo PATCH canônico e não cria endpoint paralelo", () => {
    expect(fonte).toContain("Workspace Jurídico");
    expect(fonte).toContain('api.patch(`/legal-docs/${view.id}`, {');
    expect(fonte).toContain("conteudo: conteudoEdicao");
    expect(fonte).toContain("Salvar nova versão");
    expect(fonte).not.toContain("/workspace/pecas");
  });

  it("bloqueia edição de versão final ou protocolada", () => {
    expect(fonte).toContain('view.status === "final" || view.status === "protocolada"');
    expect(fonte).toContain('view.status !== "final" && view.status !== "protocolada"');
    expect(fonte).toContain("Versão final ou protocolada não pode ser editada");
  });

  it("explicita que nova versão exige nova validação/revisão", () => {
    expect(fonte).toContain("Validação e revisão devem ser refeitas antes da aprovação");
    expect(fonte).toContain("Salve ou cancele a edição antes de revisar");
  });

  it("mantém inteligência separada do texto", () => {
    expect(fonte).toContain("Inteligência jurídica");
    expect(fonte).toContain("Jurisprudência e citações");
    expect(fonte).toContain("Crítica da peça");
    expect(fonte).toContain("A IA não altera a peça sem ação explícita do advogado");
  });
});
