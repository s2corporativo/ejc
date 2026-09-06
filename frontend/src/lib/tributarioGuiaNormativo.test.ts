import { describe, expect, it } from "vitest";
import {
  GUIA_TRIBUTARIO_DATA_BASE,
  REGRAS_CARF,
  REGRAS_JUDICIAIS,
  REGRAS_MG,
  REGRAS_MUNICIPAIS,
  REGRAS_PAF_FEDERAL,
} from "./tributarioGuiaNormativo";

function texto(obj: unknown): string {
  return JSON.stringify(obj).toLowerCase();
}

describe("guia tributário normativo", () => {
  it("mantém data-base explícita", () => {
    expect(GUIA_TRIBUTARIO_DATA_BASE).toBe("2026-09-06");
  });

  it("usa 20 dias úteis como regra geral atual do PAF federal", () => {
    const impugnacao = REGRAS_PAF_FEDERAL.find(
      (regra) => regra.tema === "Impugnação do lançamento",
    );
    const recurso = REGRAS_PAF_FEDERAL.find(
      (regra) => regra.tema === "Recurso voluntário ao CARF",
    );

    expect(impugnacao?.regra).toContain("20 dias úteis");
    expect(impugnacao?.regra).toContain("31/03/2026");
    expect(recurso?.regra).toContain("20 dias úteis");
  });

  it("não reintroduz empate automaticamente favorável ao contribuinte", () => {
    const carf = texto(REGRAS_CARF);
    expect(carf).toContain("voto de qualidade");
    expect(carf).not.toContain("empate → favorável ao contribuinte");
    expect(carf).not.toContain("automaticamente em favor do contribuinte");
  });

  it("usa TRF6 para a Justiça Federal em Minas Gerais", () => {
    const mg = texto(REGRAS_MG);
    expect(mg).toContain("6ª região");
    expect(mg).not.toContain("trf1");
  });

  it("não admite prazo municipal genérico por analogia", () => {
    const municipais = texto(REGRAS_MUNICIPAIS);
    expect(municipais).toContain("não existe prazo municipal genérico");
    expect(municipais).toContain("norma processual vigente");
  });

  it("não ancora MS e anulatória automaticamente no fim do PAF", () => {
    const judiciais = texto(REGRAS_JUDICIAIS);
    expect(judiciais).toContain("não cria, por si só");
    expect(judiciais).toContain("não usar no guia um prazo automático de 5 anos");
  });
});
