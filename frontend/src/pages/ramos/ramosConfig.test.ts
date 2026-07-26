// Testes de integridade da config dos ramos (auditoria Áreas de Atuação —
// Onda 1): ferramentas da matriz P0 devem estar marcadas como não homologadas
// e a EIRELI (extinta pela Lei 14.195/2021) não pode ser opção de registro novo.
import { describe, expect, it } from "vitest";
import { RAMOS } from "./ramosConfig";

// Matriz de não homologação (Onda 2, Fases A/B): ramo → ids ainda em revisão.
const MATRIZ_P0: Record<string, string[]> = {
  empresarial: ["verificar-cade"],
  penal: ["dosimetria"],
  consumidor: ["devolucao-dobro", "prazos-cdc"],
  previdenciario: ["prazos-previdenciario"],
};

// Ferramentas corrigidas na Onda 2 — o selo deve ter sido retirado.
const LIBERADAS: Record<string, string[]> = {
  empresarial: ["prazos-rj", "juros-mora"],
  civel: ["prazos-contestacao"],
  penal: ["prazos", "anpp", "prescricao", "prescricao-penal"],
  trabalhista: ["prazos", "prescricao"],
  transito: ["prazos-recurso-transito", "pontuacao-cnh"],
  administrativo: ["multa-transito"],
};

describe("ramosConfig — homologação (Onda 1)", () => {
  for (const [ramo, ids] of Object.entries(MATRIZ_P0)) {
    it(`marca as ferramentas P0 do ramo "${ramo}" como não homologadas`, () => {
      const cfg = RAMOS[ramo];
      expect(cfg, `ramo "${ramo}" deve existir em RAMOS`).toBeTruthy();
      for (const id of ids) {
        const ferramenta = cfg.ferramentas.find((f) => f.id === id);
        expect(
          ferramenta,
          `ferramenta "${id}" deve existir no ramo "${ramo}"`,
        ).toBeTruthy();
        expect(
          ferramenta?.homologada,
          `ferramenta "${ramo}/${id}" deve ter homologada: false`,
        ).toBe(false);
      }
    });
  }

  it("ferramentas fora da matriz P0 permanecem homologadas (campo ausente)", () => {
    const negativacao = RAMOS.consumidor.ferramentas.find(
      (f) => f.id === "negativacao-indevida",
    );
    expect(negativacao?.homologada).toBeUndefined();
  });

  for (const [ramo, ids] of Object.entries(LIBERADAS)) {
    it(`ferramentas corrigidas do ramo "${ramo}" não carregam mais o selo`, () => {
      for (const id of ids) {
        const ferramenta = RAMOS[ramo].ferramentas.find((f) => f.id === id);
        expect(
          ferramenta,
          `ferramenta "${id}" deve existir no ramo "${ramo}"`,
        ).toBeTruthy();
        expect(
          ferramenta?.homologada,
          `ferramenta "${ramo}/${id}" não deve mais ter homologada: false`,
        ).toBeUndefined();
      }
    });
  }

  it("horas-extras usa a rota canônica /trabalhista-esp", () => {
    const he = RAMOS.trabalhista.ferramentas.find(
      (f) => f.id === "horas-extras",
    );
    expect(he?.endpoint).toBe("/trabalhista-esp/ferramentas/horas-extras");
  });
});

describe("ramosConfig — tipos societários (empresarial)", () => {
  it("não oferece EIRELI (extinta) para registros novos", () => {
    const campo = RAMOS.empresarial.campos.find(
      (c) => c.nome === "tipo_societario",
    );
    expect(campo).toBeTruthy();
    expect(campo?.opcoes).not.toContain("EIRELI");
    // A SLU (sucessora natural da EIRELI) continua disponível.
    expect(campo?.opcoes).toContain("SLU");
  });
});
