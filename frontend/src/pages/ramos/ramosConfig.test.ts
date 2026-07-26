// Testes de integridade da config dos ramos (auditoria Áreas de Atuação —
// Onda 1): ferramentas da matriz P0 devem estar marcadas como não homologadas
// e a EIRELI (extinta pela Lei 14.195/2021) não pode ser opção de registro novo.
import { describe, expect, it } from "vitest";
import { RAMOS } from "./ramosConfig";

// Matriz P0 do relatório de auditoria: ramo → ids de ferramentas em revisão.
const MATRIZ_P0: Record<string, string[]> = {
  empresarial: ["prazos-rj", "juros-mora", "verificar-cade"],
  civel: ["prazos-contestacao"],
  penal: ["prazos", "anpp", "prescricao", "prescricao-penal", "dosimetria"],
  trabalhista: ["prazos", "prescricao"],
  transito: ["prazos-recurso-transito", "pontuacao-cnh"],
  administrativo: ["multa-transito"],
  consumidor: ["devolucao-dobro", "prazos-cdc"],
  previdenciario: ["prazos-previdenciario"],
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
