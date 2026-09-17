import { describe, expect, it } from "vitest";
import {
  GUIA_TRIBUTARIO_DATA_BASE,
  REGRAS_CARF,
  REGRAS_CREDITOS,
  REGRAS_CTN_2026,
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

  it("incorpora a LC 236/2026 vigente desde 04/09/2026", () => {
    const ctn = texto(REGRAS_CTN_2026);
    expect(ctn).toContain("lc 236/2026");
    expect(ctn).toContain("04/09/2026");
    expect(ctn).toContain("art. 150");
    expect(ctn).toContain("art. 151");
    expect(ctn).toContain("art. 168");
    expect(ctn).toContain("art. 174");
    expect(ctn).toContain("211-a/211-b");
  });

  it("não reintroduz empate automaticamente favorável ao contribuinte", () => {
    const carf = texto(REGRAS_CARF);
    expect(carf).toContain("voto de qualidade");
    expect(carf).toContain("não é proclamado automaticamente em favor do contribuinte");
    expect(carf).not.toContain("empate → favorável ao contribuinte");
    expect(carf).not.toContain("voto de qualidade invertido");
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
    expect(municipais).toContain("211-a/211-b");
  });

  it("não ancora MS e anulatória automaticamente no fim do PAF", () => {
    const judiciais = texto(REGRAS_JUDICIAIS);
    expect(judiciais).toContain("não cria, por si só");
    expect(judiciais).toContain("não usar no guia um prazo automático de 5 anos");
    expect(judiciais).toContain("temas 566-571");
  });

  it("não trata emissão de NF-e como termo universal de prescrição", () => {
    const creditos = texto(REGRAS_CREDITOS);
    expect(creditos).toContain("data de emissão da nf-e não é termo inicial universal");
    expect(creditos).toContain("não deve chamar notas antigas de prescritas");
  });
});
