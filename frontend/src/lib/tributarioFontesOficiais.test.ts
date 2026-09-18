import { describe, expect, it } from "vitest";
import {
  FONTES_TRIBUTARIAS_OFICIAIS,
  fontesComAcessoExterno,
  fontesMunicipais,
} from "./tributarioFontesOficiais";

describe("fontes tributárias oficiais", () => {
  it("não classifica portais autenticados como API pública", () => {
    const portais = FONTES_TRIBUTARIAS_OFICIAIS.filter(
      (fonte) => fonte.tipo === "portal" || fonte.tipo === "servico_autenticado",
    );

    expect(portais.length).toBeGreaterThan(0);
    for (const fonte of portais) expect(fonte.apiPublica, fonte.id).toBe(false);
  });

  it("mantém PGFN Dados Abertos separada do REGULARIZE", () => {
    const regularize = FONTES_TRIBUTARIAS_OFICIAIS.find(
      (fonte) => fonte.id === "pgfn-regularize",
    );
    const dados = FONTES_TRIBUTARIAS_OFICIAIS.find(
      (fonte) => fonte.id === "pgfn-dados-abertos",
    );

    expect(regularize?.apiPublica).toBe(false);
    expect(regularize?.status).toBe("verificada");
    expect(dados?.apiPublica).toBe(true);
    expect(dados?.status).toBe("integracao_ejc");
  });

  it("cobre os municípios prioritários sem inventar endpoint de São Joaquim de Bicas", () => {
    for (const municipio of ["Betim", "Contagem", "Belo Horizonte", "Igarapé"]) {
      const fontes = fontesMunicipais(municipio);
      expect(fontes.length, municipio).toBeGreaterThan(0);
      expect(fontes.some((fonte) => fonte.status === "verificada"), municipio).toBe(true);
    }

    const sjb = fontesMunicipais("São Joaquim de Bicas");
    expect(sjb).toHaveLength(1);
    expect(sjb[0].status).toBe("parcial");
    expect(sjb[0].url).toBeUndefined();
    expect(sjb[0].apiPublica).toBe(false);
  });

  it("só oferece acesso externo para fontes verificadas com URL", () => {
    const acessiveis = fontesComAcessoExterno();
    expect(acessiveis.length).toBeGreaterThan(0);
    expect(acessiveis.every((fonte) => Boolean(fonte.url))).toBe(true);
    expect(acessiveis.some((fonte) => fonte.status === "parcial")).toBe(false);
  });
});
