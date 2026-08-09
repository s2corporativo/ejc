import { describe, expect, it } from "vitest";
import {
  ehModoEntrada,
  modoPadraoParaRole,
  modoPermitidoParaRole,
  podeUsarRelato,
} from "./EntradaUnica";

describe("Entrada Jurídica — contrato dos modos", () => {
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

  it("não transforma a fusão visual em ampliação de permissão", () => {
    expect(modoPermitidoParaRole("relato", "advogado")).toBe(true);
    expect(modoPermitidoParaRole("relato", "estagiario")).toBe(false);
    expect(modoPermitidoParaRole("raio-x", "estagiario")).toBe(true);
    expect(modoPermitidoParaRole("sala", "advogado_auxiliar")).toBe(true);
  });
});
