import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const source = readFileSync(
  new URL("./Jurimetria.tsx", import.meta.url),
  "utf8",
);

describe("Jurimetria — verdade da fonte", () => {
  it("consome os endpoints internos canônicos", () => {
    expect(source).toContain("/jurimetria/interno/stats");
    expect(source).toContain("/jurimetria/interno/benchmarks");
    expect(source).toContain("/jurimetria/interno/analise-prospectiva");
  });

  it("não apresenta DataJud/STJ como benchmark ativo", () => {
    expect(source).not.toContain('label="Base Externa"');
    expect(source).not.toContain("Benchmarks DataJud");
    expect(source).not.toContain("processos DataJud");
    expect(source).toContain("sem benchmark externo ativo");
    expect(source).toContain("não são DataJud/STJ");
  });

  it("explicita classe TPU como referência não filtrante", () => {
    expect(source).toContain("Classe TPU (somente referência)");
    expect(source).toContain("não filtra a base atual");
  });

  it("usa o título real do caso nas lições aprendidas", () => {
    expect(source).toContain('l.titulo || "Caso"');
    expect(source).not.toContain("l.nr_cnj");
  });
});
