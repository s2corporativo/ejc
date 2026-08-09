import { describe, expect, it } from "vitest";
import { RAMOS } from "./ramosConfig";
import {
  AREAS_CANONICAS,
  configWorkspaceDaArea,
  hubSlugDaArea,
  temWorkspaceEspecializado,
} from "./areasWorkspace";
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

  it("não reclassifica especialidades relacionadas e mantém navegação própria", () => {
    const empresarial = relacoesDoWorkspace(RAMOS.empresarial);
    expect(empresarial.map((item) => item.slug)).toContain("societario");
    expect(
      empresarial.find((item) => item.slug === "societario")?.workspace,
    ).toBe("/areas-de-atuacao/societario");
    expect(
      empresarial.find((item) => item.slug === "contratual")?.workspace,
    ).toBe("/areas-de-atuacao/contratual");
    expect(empresarial.map((item) => item.slug)).not.toContain("dpt360");
    expect(RAMOS.empresarial.areaCaso).toBe("empresarial");

    const administrativo = relacoesDoWorkspace(RAMOS.administrativo);
    expect(administrativo.map((item) => item.slug)).toContain("licitacoes");
    expect(
      administrativo.find((item) => item.slug === "licitacoes")?.workspace,
    ).toBe("/areas-de-atuacao/licitacoes");
    expect(RAMOS.administrativo.areaCaso).toBe("administrativo");

    const familia = relacoesDoWorkspace(RAMOS.familia);
    expect(familia.find((item) => item.slug === "sucessoes")?.workspace).toBe(
      "/areas-de-atuacao/sucessoes",
    );
    expect(RAMOS.familia.areaCaso).toBe("familia");
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

  it("oferece um workspace funcional para as 25 áreas canônicas", () => {
    expect(AREAS_CANONICAS).toHaveLength(25);

    for (const area of AREAS_CANONICAS) {
      const hubSlug = hubSlugDaArea(area.slug);
      expect(hubSlug, area.slug).not.toBeNull();
      const cfg = configWorkspaceDaArea(hubSlug!);
      expect(cfg, area.slug).toBeDefined();
      expect(cfg?.areaCaso, area.slug).toBe(area.slug);
      expect(abasDoWorkspace(cfg!).map((aba) => aba.id)).toContain("casos");
      expect(abasDoWorkspace(cfg!).map((aba) => aba.id)).toContain(
        "referencias",
      );
    }
  });

  it("cria somente uma casca segura para áreas sem implementação especializada", () => {
    for (const slug of ["societario", "sucessoes", "licitacoes"]) {
      expect(temWorkspaceEspecializado(slug)).toBe(false);
      const cfg = configWorkspaceDaArea(slug);
      expect(cfg).toBeDefined();
      expect(cfg?.areaCaso).toBe(slug);
      expect(cfg?.externo).toBe(true);
      expect(cfg?.endpoint).toBe("");
      expect(cfg?.ferramentas).toEqual([]);
      expect(abasDoWorkspace(cfg!).map((aba) => aba.id)).toEqual([
        "visao",
        "casos",
        "referencias",
      ]);
    }
  });
});
