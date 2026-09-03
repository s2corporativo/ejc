// @vitest-environment jsdom
// Ficha viva da tese (§5 do Legal Drafting 2.0) — o painel existe para impedir
// duas leituras erradas que a listagem do Banco de Teses produz hoje:
//
//   • "100% de êxito" numa ficha usada UMA vez — número verdadeiro, conclusão
//     falsa, e é por ele que o advogado escolhe a tese da peça;
//   • ficha sem nenhuma fonte verificada parecendo tão sólida quanto uma
//     lastreada.
//
// Também trava a degradação: o painel não pode sumir porque UMA das três
// chamadas falhou — a confiança é o dado que muda a decisão.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../lib/api", () => ({ default: { get } }));

import FichaVivaPanel from "./FichaVivaPanel";

afterEach(() => {
  cleanup();
  get.mockReset();
});

const CONF_ALTA = {
  rotulo: "alta",
  taxa_sucesso: 0.8,
  casos_decididos: 10,
  vezes_venceu: 8,
  vezes_perdeu: 2,
  amostra_minima: 5,
  explicacao: "8 de 10 caso(s) decidido(s).",
};

const CONF_UM_CASO = {
  rotulo: "amostra_insuficiente",
  taxa_sucesso: 1.0,
  casos_decididos: 1,
  vezes_venceu: 1,
  vezes_perdeu: 0,
  amostra_minima: 5,
  explicacao:
    "1 de 1 caso(s) decidido(s). Amostra abaixo de 5 — a taxa é verdadeira, mas não sustenta conclusão sobre a ficha.",
};

const SEM_FONTES = {
  cobertura: {
    total: 0,
    verificadas: 0,
    nao_verificadas: 0,
    elementos_cobertos: [],
    elementos_sem_fonte: ["contra_argumento", "fundamentacao", "gatilho", "jurisprudencia"],
  },
  fontes: [],
};

function mockRotas(conf: unknown, fontes: unknown, versoes: unknown) {
  get.mockImplementation((url: string) => {
    if (url.includes("/confianca")) return Promise.resolve({ data: conf });
    if (url.includes("/fontes")) return Promise.resolve({ data: fontes });
    if (url.includes("/versoes")) return Promise.resolve({ data: { versoes } });
    return Promise.reject(new Error("rota inesperada"));
  });
}

describe("FichaVivaPanel", () => {
  it("uma vitória em um caso não é apresentada como confiança", async () => {
    mockRotas(CONF_UM_CASO, SEM_FONTES, []);
    render(<FichaVivaPanel teseId="t1" />);

    await waitFor(() =>
      expect(screen.getByText("Amostra insuficiente")).toBeTruthy(),
    );
    // A taxa aparece — omiti-la esconderia informação verdadeira —, mas
    // acompanhada do motivo pelo qual ela não conclui nada.
    expect(screen.getByText("100% de êxito")).toBeTruthy();
    expect(
      screen.getByText(/não sustentam conclusão sobre a ficha/),
    ).toBeTruthy();
  });

  it("amostra suficiente mostra confiança alta", async () => {
    mockRotas(CONF_ALTA, SEM_FONTES, []);
    render(<FichaVivaPanel teseId="t1" />);
    await waitFor(() => expect(screen.getByText("Confiança alta")).toBeTruthy());
    expect(screen.getByText("80% de êxito")).toBeTruthy();
  });

  it("ficha sem fonte alguma diz isso explicitamente", async () => {
    mockRotas(CONF_ALTA, SEM_FONTES, []);
    render(<FichaVivaPanel teseId="t1" />);
    await waitFor(() =>
      expect(
        screen.getByText(/Nenhum elemento desta ficha tem fonte registrada/),
      ).toBeTruthy(),
    );
  });

  it("mostra o lastro verificado e o trecho da fonte", async () => {
    mockRotas(CONF_ALTA, {
      cobertura: {
        total: 2,
        verificadas: 1,
        nao_verificadas: 1,
        elementos_cobertos: ["fundamentacao", "jurisprudencia"],
        elementos_sem_fonte: ["contra_argumento", "gatilho"],
      },
      fontes: [
        {
          id: "f1",
          elemento: "fundamentacao",
          referencia: "art. 42, par. único, CDC",
          trecho: "O consumidor cobrado em quantia indevida tem direito à repetição do indébito.",
          fonte_url: "https://exemplo.fictic.io/cdc",
          status_verificacao: "verificada",
        },
      ],
    }, []);
    render(<FichaVivaPanel teseId="t1" />);

    await waitFor(() => expect(screen.getByText("1/2 verificada(s)")).toBeTruthy());
    const link = screen.getByText("art. 42, par. único, CDC");
    expect(link.getAttribute("href")).toBe("https://exemplo.fictic.io/cdc");
    expect(screen.getByText(/Sem fonte: contra_argumento, gatilho/)).toBeTruthy();
  });

  it("mostra o histórico com os campos alterados", async () => {
    mockRotas(CONF_ALTA, SEM_FONTES, [
      {
        id: "v2",
        versao: 2,
        resumo_mudanca: "Acrescentado julgado de suporte.",
        criado_em: "2026-09-01T12:00:00Z",
        mudou: { jurisprudencia: { de: null, para: "Julgado fictício" } },
      },
    ]);
    render(<FichaVivaPanel teseId="t1" />);

    await waitFor(() =>
      expect(screen.getByText("Acrescentado julgado de suporte.")).toBeTruthy(),
    );
    expect(screen.getByText("v2")).toBeTruthy();
    expect(screen.getByText(/Campos alterados: jurisprudencia/)).toBeTruthy();
  });

  it("recomendação de revisão aparece em destaque", async () => {
    mockRotas(
      {
        ...CONF_ALTA,
        revisao: {
          precisa_revisao: true,
          gatilho_largo: false,
          total_overrides: 2,
          por_motivo: { jurisprudencia_virou: 2 },
          recomendacoes: [
            "2 recusa(s) por erro na ficha ou mudança de orientação — revise fundamentação e jurisprudência.",
          ],
        },
      },
      SEM_FONTES,
      [],
    );
    render(<FichaVivaPanel teseId="t1" />);
    await waitFor(() =>
      expect(screen.getByText(/revise fundamentação e jurisprudência/)).toBeTruthy(),
    );
  });

  it("uma chamada que falha não derruba as outras", async () => {
    // O histórico não vir não pode esconder a confiança, que é o dado que
    // muda a decisão do advogado.
    get.mockImplementation((url: string) => {
      if (url.includes("/versoes")) return Promise.reject(new Error("500"));
      if (url.includes("/confianca")) return Promise.resolve({ data: CONF_ALTA });
      return Promise.resolve({ data: SEM_FONTES });
    });
    render(<FichaVivaPanel teseId="t1" />);

    await waitFor(() => expect(screen.getByText("Confiança alta")).toBeTruthy());
    expect(screen.getByText(/Sem histórico registrado/)).toBeTruthy();
  });

  it("todas falhando mostra estado de erro, não tela vazia", async () => {
    get.mockRejectedValue(new Error("500"));
    render(<FichaVivaPanel teseId="t1" />);
    await waitFor(() =>
      expect(screen.getByText("Ficha viva indisponível")).toBeTruthy(),
    );
  });
});
