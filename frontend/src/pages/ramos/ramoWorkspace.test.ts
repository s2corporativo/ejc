import { describe, expect, it } from "vitest";
import { RAMOS } from "./ramosConfig";
import {
  abasDoWorkspace,
  areasDoWorkspace,
  possuiRegistroEspecializado,
  relacoesDoWorkspace,
  subtituloDoWorkspace,
  tituloDoWorkspace,
} from "./ramoWorkspace";

describe("ramoWorkspace", () => {
  it("preserva a área canônica e somente acrescenta áreas legadas de leitura", () => {
    const cfg = {
      ...RAMOS.bancario,
      areaCaso: "bancario",
      areasLegadas: ["civil", "bancario", "civil"],
    };
    expect(areasDoWorkspace(cfg)).toEqual(["bancario", "civil"]);
  });

  it("não reclassifica especialidades relacionadas", () => {
    const empresarial = relacoesDoWorkspace(RAMOS.empresarial);
    expect(empresarial.map((item) => item.slug)).toContain("societario");
    expect(RAMOS.empresarial.areaCaso).toBe("empresarial");

    const administrativo = relacoesDoWorkspace(RAMOS.administrativo);
    expect(administrativo.map((item) => item.slug)).toContain("licitacoes");
    expect(RAMOS.administrativo.areaCaso).toBe("administrativo");
  });

  it("apresenta Cível como núcleo geral sem remover workspaces próprios", () => {
    expect(tituloDoWorkspace(RAMOS.civel)).toBe("Direito Cível Geral");
    expect(subtituloDoWorkspace(RAMOS.civel)).toContain("workspaces próprios");
    expect(relacoesDoWorkspace(RAMOS.civel).map((item) => item.slug)).toEqual([
      "consumidor",
      "familia",
      "imobiliario",
    ]);
  });

  it("oferece abas conforme as capacidades reais do ramo", () => {
    const bancario = abasDoWorkspace(RAMOS.bancario).map((aba) => aba.id);
    expect(bancario).toContain("visao");
    expect(bancario).toContain("casos");
    expect(bancario).toContain("ferramentas");
    expect(bancario).toContain("analise");
    expect(bancario).toContain("referencias");
  });

  it("não trata ramo externo como registro especializado paralelo", () => {
    const externo = Object.values(RAMOS).find((cfg) => cfg.externo);
    expect(externo).toBeDefined();
    expect(possuiRegistroEspecializado(externo!)).toBe(false);
    expect(abasDoWorkspace(externo!).map((aba) => aba.id)).toContain("casos");
  });
});
