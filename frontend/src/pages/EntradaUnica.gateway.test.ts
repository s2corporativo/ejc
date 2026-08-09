import { describe, expect, it } from "vitest";
import {
  destinoModo,
  ehModoEntrada,
  modoPadraoParaRole,
  podeUsarRelato,
} from "./EntradaUnica";

describe("Entrada Única — contrato dos modos", () => {
  it("mantém relato como padrão apenas para advogado+", () => {
    expect(modoPadraoParaRole("advogado")).toBe("relato");
    expect(modoPadraoParaRole("socio")).toBe("relato");
    expect(modoPadraoParaRole("estagiario")).toBe("sala");
    expect(modoPadraoParaRole("advogado_auxiliar")).toBe("sala");
    expect(podeUsarRelato("financeiro")).toBe(false);
  });

  it("aceita apenas os três modos declarados", () => {
    expect(ehModoEntrada("relato")).toBe(true);
    expect(ehModoEntrada("raio-x")).toBe(true);
    expect(ehModoEntrada("sala")).toBe(true);
    expect(ehModoEntrada("qualquer")).toBe(false);
  });

  it("preserva case_id e demais parâmetros ao encaminhar para Raio-X", () => {
    const params = new URLSearchParams(
      "modo=raio-x&case_id=caso-123&origem=tab-resumo",
    );

    expect(destinoModo("raio-x", params)).toBe(
      "/raio-x?case_id=caso-123&origem=tab-resumo",
    );
  });

  it("remove apenas o parâmetro de modo ao encaminhar para Sala Jurídica", () => {
    const params = new URLSearchParams("modo=sala&case_id=caso-456");

    expect(destinoModo("sala", params)).toBe("/sala-juridica?case_id=caso-456");
  });
});
