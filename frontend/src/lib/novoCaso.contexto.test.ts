import { describe, expect, it } from "vitest";
import {
  entradaNovoCasoComCliente,
  NOVO_CASO_DOCUMENTO_PATH,
  NOVO_CASO_MANUAL_PATH,
  resolverModoNovoCaso,
} from "./novoCaso";

describe("novoCaso — porta única", () => {
  it("faz os novos atalhos apontarem para a Entrada Jurídica", () => {
    expect(NOVO_CASO_DOCUMENTO_PATH).toBe("/entrada?modo=documento");
    expect(NOVO_CASO_MANUAL_PATH).toBe("/entrada?modo=manual");
  });

  it("gera entrada vinculada ao cliente com encoding seguro", () => {
    expect(entradaNovoCasoComCliente("cliente 1/2")).toBe(
      "/entrada?client_id=cliente+1%2F2",
    );
  });

  it("mantém a interpretação da rota histórica /casos/novo", () => {
    expect(resolverModoNovoCaso("/casos/novo", "?modo=documento")).toBe(
      "documento",
    );
    expect(resolverModoNovoCaso("/casos/novo", "?modo=manual")).toBe("manual");
    expect(resolverModoNovoCaso("/entrada", "?modo=documento")).toBeNull();
  });
});
