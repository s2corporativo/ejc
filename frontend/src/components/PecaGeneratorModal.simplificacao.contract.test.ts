import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const DIR = dirname(fileURLToPath(import.meta.url));
const fonte = readFileSync(join(DIR, "PecaGeneratorModal.tsx"), "utf-8");

describe("PecaGeneratorModal — superfície simplificada", () => {
  it("usa Guiado como padrão e mantém Livre em opções avançadas", () => {
    expect(fonte).toContain('type ModoVisivel = "guiado" | "livre"');
    expect(fonte).toContain('useState<ModoVisivel>("guiado")');
    expect(fonte).toContain("Opções avançadas");
    expect(fonte).toContain("Preenchimento guiado");
    expect(fonte).toContain("Preenchimento livre");
  });

  it("não oferece Molde ou Agente como escolhas operacionais", () => {
    expect(fonte).not.toContain('setModo("molde")');
    expect(fonte).not.toContain('setModo("agente")');
    expect(fonte).not.toContain('id: "molde"');
    expect(fonte).not.toContain('id: "agente"');
  });

  it("preserva o contrato estruturado com o backend", () => {
    expect(fonte).toContain("const modoProducao = {");
    expect(fonte).toContain("modo_producao: modoProducao");
    expect(fonte).toContain("aprovado_para_redacao");
    expect(fonte).toContain("bloqueios");
    expect(fonte).not.toContain("[modo_producao=");
  });
});
