import { describe, expect, it } from "vitest";
import {
  classificarDocumento,
  validarCnpj,
  validarCpf,
} from "./documento";

describe("validarCpf", () => {
  it("aceita CPF válido com e sem máscara", () => {
    expect(validarCpf("529.982.247-25")).toBe(true);
    expect(validarCpf("52998224725")).toBe(true);
  });
  it("rejeita DV inválido e sequência repetida", () => {
    expect(validarCpf("529.982.247-26")).toBe(false);
    expect(validarCpf("111.111.111-11")).toBe(false);
  });
});

describe("validarCnpj", () => {
  it("aceita CNPJ válido com e sem máscara", () => {
    expect(validarCnpj("12.345.678/0001-95")).toBe(true);
    expect(validarCnpj("12345678000195")).toBe(true);
  });
  it("rejeita DV inválido", () => {
    expect(validarCnpj("12.345.678/0001-96")).toBe(false);
  });
});

describe("classificarDocumento", () => {
  it("vazio é permitido (documento opcional)", () => {
    expect(classificarDocumento("").tipo).toBe("vazio");
  });
  it("11 dígitos válidos vira CPF", () => {
    const r = classificarDocumento("529.982.247-25");
    expect(r).toEqual({ tipo: "cpf", cpf: "52998224725", cnpj: null });
  });
  it("14 dígitos válidos vira CNPJ", () => {
    const r = classificarDocumento("12.345.678/0001-95");
    expect(r).toEqual({ tipo: "cnpj", cpf: null, cnpj: "12345678000195" });
  });
  it("comprimento inválido NÃO trunca — retorna erro explícito", () => {
    const r = classificarDocumento("1234567890123456");
    expect(r.tipo).toBe("erro");
    if (r.tipo === "erro") expect(r.mensagem).toContain("16 dígitos");
  });
  it("DV inválido retorna erro, não payload", () => {
    expect(classificarDocumento("529.982.247-26").tipo).toBe("erro");
    expect(classificarDocumento("12.345.678/0001-96").tipo).toBe("erro");
  });
});
