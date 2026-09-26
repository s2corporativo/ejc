import { describe, expect, it } from "vitest";
import { rotaModuloSugerido } from "./IntakeAnalise";

describe("rotaModuloSugerido", () => {
  const caseId = "case-123";

  it("leva módulos Core para a aba do mesmo caso", () => {
    expect(rotaModuloSugerido("prazos", caseId)).toBe(
      "/casos/case-123?tab=prazos",
    );
    expect(rotaModuloSugerido("documentos", caseId)).toBe(
      "/casos/case-123?tab=documentos",
    );
    expect(rotaModuloSugerido("pecas", caseId)).toBe(
      "/casos/case-123?tab=pecas",
    );
    expect(rotaModuloSugerido("checklists", caseId)).toBe(
      "/casos/case-123?tab=checklists",
    );
  });

  it("abre ramo especializado preservando o case_id e a aba de ferramentas", () => {
    expect(rotaModuloSugerido("ramos/tributario", caseId)).toBe(
      "/areas-de-atuacao/tributario?case_id=case-123&tab=ferramentas",
    );
  });

  it("não inventa destino para módulo sem rota contextual confirmada", () => {
    expect(rotaModuloSugerido("workflow", caseId)).toBeNull();
    expect(rotaModuloSugerido("ramos/../../admin", caseId)).toBeNull();
    expect(rotaModuloSugerido("ramos/tributarioo", caseId)).toBeNull();
    expect(rotaModuloSugerido("", caseId)).toBeNull();
  });
});
