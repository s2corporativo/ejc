// Testes de integridade da config dos ramos (auditoria Áreas de Atuação).
// Estado final da Onda 2 (Fases A/B/C): só a dosimetria penal segue sem
// homologação; as demais foram corrigidas no backend e perderam o selo.
// A EIRELI (extinta pela Lei 14.195/2021) não pode ser opção de registro novo.
import { describe, expect, it } from "vitest";
import { RAMOS } from "./ramosConfig";

// Matriz de não homologação — estado FINAL: exatamente 1 ferramenta.
const MATRIZ_P0: Record<string, string[]> = {
  penal: ["dosimetria"],
};

// Ferramentas corrigidas ao longo das Ondas 1-2 — o selo deve ter sido retirado.
const LIBERADAS: Record<string, string[]> = {
  empresarial: ["prazos-rj", "juros-mora", "verificar-cade"],
  civel: ["prazos-contestacao"],
  penal: ["prazos", "anpp", "prescricao", "prescricao-penal"],
  trabalhista: ["prazos", "prescricao"],
  transito: ["prazos-recurso-transito", "pontuacao-cnh"],
  administrativo: ["multa-transito"],
  consumidor: ["devolucao-dobro", "prazos-cdc"],
  previdenciario: ["prazos-previdenciario"],
};

describe("ramosConfig — homologação", () => {
  for (const [ramo, ids] of Object.entries(MATRIZ_P0)) {
    it(`marca as ferramentas em revisão do ramo "${ramo}" como não homologadas`, () => {
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

  it("apenas a dosimetria penal continua selada em todo o registro", () => {
    const seladas = Object.entries(RAMOS).flatMap(([slug, cfg]) =>
      cfg.ferramentas
        .filter((f) => f.homologada === false)
        .map((f) => `${slug}/${f.id}`),
    );
    expect(seladas).toEqual(["penal/dosimetria"]);
  });

  it("ferramentas fora da matriz permanecem homologadas (campo ausente)", () => {
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

describe("ramosConfig — parâmetros extintos nas Ondas 1-2", () => {
  // Nomes de parâmetro que o backend deixou de aceitar; se algum reaparecer
  // na config, a calculadora volta a mandar campo inválido (422/resultado errado).
  const EXTINTOS = [
    "data_distribuicao",
    "houve_ma_fe",
    "valor_cobrado",
    "existe_inscricao_anterior_legitima",
    "pontos_cnh",
    "data_indeferimento",
    "valor_mensal",
    "meses_atraso",
    "aliquota_percentual",
    "tem_patrimonio_afetacao",
    "infracoes_gravissimas_12m",
    "categoria_profissional",
    "data_sentenca",
    "data_denuncia",
    // `data_demissao` fora da lista: saiu da prescrição trabalhista, mas segue
    // válido em /trabalhista-esp/ferramentas/verbas-rescisorias.
  ];

  it("nenhuma ferramenta usa parâmetro extinto", () => {
    const usados = Object.entries(RAMOS).flatMap(([slug, cfg]) =>
      cfg.ferramentas.flatMap((f) =>
        f.campos
          .filter((c) => EXTINTOS.includes(c.nome))
          .map((c) => `${slug}/${f.id}:${c.nome}`),
      ),
    );
    expect(usados).toEqual([]);
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
