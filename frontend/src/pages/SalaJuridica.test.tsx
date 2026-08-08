// @vitest-environment jsdom
// Wizard de conversão da Sala Jurídica — os gates éticos são o que impede um
// caso oficial de nascer com conflito não verificado ou duplicando outro.
// Cobre as regressões auditadas:
//   • o preview é refeito para o cliente REALMENTE submetido (não o da
//     abertura do wizard) — preview estático deixava passar conflito de nome
//     recém-digitado;
//   • o 409 do servidor alimenta a UI, senão o bloqueio vira beco sem saída
//     (o checkbox de reconhecimento nunca aparecia);
//   • vincular navega para o case_id DEVOLVIDO pelo backend (idempotência).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";

const getMock = vi.fn();
const postMock = vi.fn();
const patchMock = vi.fn();

vi.mock("../lib/api", () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a),
    patch: (...a: unknown[]) => patchMock(...a),
  },
  getAccessToken: () => null,
  logout: vi.fn(),
  refreshAccessToken: vi.fn(),
}));

vi.mock("../components/Toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock("../stores/auth", () => ({
  useAuth: () => ({ user: { id: "u1", full_name: "Dra. Advogada" } }),
}));

vi.mock("../components/Markdown", () => ({
  default: ({ source }: { source: string }) => <div>{source}</div>,
}));

import SalaJuridica from "./SalaJuridica";

const SESSAO = {
  id: "s1",
  titulo: "Análise preliminar",
  status: "em_analise",
  favorita: false,
  cliente_potencial: null,
  area_sugerida: null,
  workspace_versao: 1,
  convertido_case_id: null,
  frozen: false,
  custo_ia_total: 0,
  workspace_texto: "",
  mensagens: [],
  anexos: [],
  estado: null,
};

const PREVIEW_LIMPO = {
  alertas_conflito: [],
  clientes_possivelmente_duplicados: [],
  casos_ativos_do_cliente: [],
  bloqueia: false,
};

/** Roteia os GETs da página: lista, sessão e preview de conversão. */
function rotearGet(preview: unknown = PREVIEW_LIMPO) {
  getMock.mockImplementation((url: string) => {
    if (url === "/sala-juridica") return Promise.resolve({ data: [SESSAO] });
    if (url === "/sala-juridica/s1") return Promise.resolve({ data: SESSAO });
    if (url.endsWith("/conversao/preview")) {
      return Promise.resolve({ data: preview });
    }
    if (url === "/clients" || url === "/cases") {
      return Promise.resolve({ data: { data: [] } });
    }
    return Promise.resolve({ data: {} });
  });
}

function UrlProbe() {
  const { pathname } = useLocation();
  return <div>URL_ATUAL:{pathname}</div>;
}

function renderizar() {
  return render(
    <MemoryRouter initialEntries={["/sala-juridica"]}>
      <Routes>
        <Route
          path="/sala-juridica"
          element={
            <>
              <SalaJuridica />
              <UrlProbe />
            </>
          }
        />
        <Route path="/casos/:id" element={<UrlProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

/** Abre o wizard "Transformar em caso" de uma sessão já carregada. */
async function abrirWizard() {
  await waitFor(() => {
    expect(screen.getAllByText("Análise preliminar").length).toBeGreaterThan(0);
  });
  fireEvent.click(screen.getByRole("button", { name: /Transformar em caso/i }));
  await waitFor(() => {
    expect(screen.getByText(/conferência obrigatória/i)).toBeTruthy();
  });
}

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  patchMock.mockReset();
  patchMock.mockResolvedValue({ data: {} });
  // jsdom não implementa scrollTo em elementos; a Sala rola o chat a cada
  // mensagem nova e sem o stub o efeito derruba a árvore.
  Element.prototype.scrollTo = vi.fn();
});

afterEach(cleanup);

describe("Sala Jurídica — wizard pré-preenche área e fatos da sessão", () => {
  // Achado da auditoria (docs/PLANO_FUSAO_CASO_UNICO.md §4.3-2): o wizard
  // nunca aplicava a área sugerida pela conversa — o caso sempre nascia
  // "civil". E o fallback de fatos usava `??`, que não cobre string vazia:
  // com extração automática ligada mas sem resultado (resumo === ""), o
  // texto do workspace era descartado.
  it("aplica area_sugerida da sessão, não o default civil", async () => {
    rotearGet();
    getMock.mockImplementation((url: string) => {
      if (url === "/sala-juridica")
        return Promise.resolve({
          data: [{ ...SESSAO, area_sugerida: "trabalhista" }],
        });
      if (url === "/sala-juridica/s1")
        return Promise.resolve({
          data: { ...SESSAO, area_sugerida: "trabalhista" },
        });
      if (url.endsWith("/conversao/preview"))
        return Promise.resolve({ data: PREVIEW_LIMPO });
      if (url === "/clients" || url === "/cases")
        return Promise.resolve({ data: { data: [] } });
      return Promise.resolve({ data: {} });
    });
    renderizar();
    await abrirWizard();

    expect(screen.getByDisplayValue("Trabalhista")).toBeTruthy();
  });

  it("cai para workspace_texto quando o resumo do estado é string vazia", async () => {
    getMock.mockImplementation((url: string) => {
      const sessaoComEstadoVazio = {
        ...SESSAO,
        estado: { resumo: "" },
        workspace_texto: "Relato do cliente colado na área de trabalho.",
      };
      if (url === "/sala-juridica")
        return Promise.resolve({ data: [sessaoComEstadoVazio] });
      if (url === "/sala-juridica/s1")
        return Promise.resolve({ data: sessaoComEstadoVazio });
      if (url.endsWith("/conversao/preview"))
        return Promise.resolve({ data: PREVIEW_LIMPO });
      if (url === "/clients" || url === "/cases")
        return Promise.resolve({ data: { data: [] } });
      return Promise.resolve({ data: {} });
    });
    renderizar();
    await abrirWizard();

    // Placeholder específico do textarea de fatos do wizard — o workspace
    // principal também exibe o mesmo texto, então getByDisplayValue
    // encontraria os dois.
    const fatos = screen.getByPlaceholderText(
      "Fatos do caso (pré-preenchidos da análise — confira e ajuste)",
    ) as HTMLTextAreaElement;
    expect(fatos.value).toBe("Relato do cliente colado na área de trabalho.");
  });
});

describe("Sala Jurídica — wizard de conversão", () => {
  it("consulta o preview para o nome digitado, não para o da abertura", async () => {
    rotearGet();
    renderizar();
    await abrirWizard();

    fireEvent.change(screen.getByPlaceholderText("Nome do novo cliente"), {
      target: { value: "Construtora Beta" },
    });

    // Debounce de 400ms na página: o preview acompanha o que será submetido.
    await waitFor(
      () => {
        const chamadas = getMock.mock.calls.filter(([url]: [string]) =>
          String(url).endsWith("/conversao/preview"),
        );
        expect(chamadas.length).toBeGreaterThan(0);
        const ultima = chamadas[chamadas.length - 1];
        expect(ultima[1]?.params?.nome_cliente).toBe("Construtora Beta");
      },
      { timeout: 3000 },
    );
  });

  it("exibe o alerta de conflito devolvido pelo preview", async () => {
    rotearGet({
      ...PREVIEW_LIMPO,
      alertas_conflito: [
        {
          tipo: "CONFLITO_cliente_e_parte_contraria",
          nome: "Banco Alfa",
          mensagem: "O cliente informado figura como PARTE CONTRÁRIA.",
          protegido: false,
        },
      ],
      bloqueia: true,
    });
    renderizar();
    await abrirWizard();

    await waitFor(() => {
      expect(
        screen.getByText(/Alertas de conflito de interesses/i),
      ).toBeTruthy();
      expect(screen.getByText(/figura como PARTE CONTRÁRIA/i)).toBeTruthy();
    });
  });

  it("o 409 do servidor revela o checkbox de duplicidade (não vira beco sem saída)", async () => {
    // Preview limpo: nada aparece até o servidor recusar.
    rotearGet();
    postMock.mockRejectedValue({
      response: {
        data: {
          detail: {
            mensagem: "Há cliente possivelmente duplicado",
            clientes_possivelmente_duplicados: [
              { id: "c9", nome: "Construtora Beta Ltda", protegido: false },
            ],
          },
        },
      },
    });
    renderizar();
    await abrirWizard();

    fireEvent.change(screen.getByPlaceholderText("Nome do novo cliente"), {
      target: { value: "Construtora Beta" },
    });
    // Marca as confirmações pelo nome acessível; a página contém outros
    // checkboxes e a ordem do DOM não faz parte do contrato do wizard.
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: /Verifiquei conflito de interesses e duplicidade de casos/i,
      }),
    );
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: /Revisei fatos, provas, pendências e documentos/i,
      }),
    );
    const confirmar = screen.getByRole("button", {
      name: /Confirmar conversão/i,
    });
    await waitFor(() => {
      expect((confirmar as HTMLButtonElement).disabled).toBe(false);
    });
    fireEvent.click(confirmar);

    // Prova que o servidor foi consultado antes de esperar o estado do 409.
    await waitFor(() => {
      expect(postMock).toHaveBeenCalledTimes(1);
    });

    // O achado do 409 entra no estado: painel + checkbox de reconhecimento.
    await waitFor(() => {
      expect(
        screen.getByText(/Cliente possivelmente já cadastrado/i),
      ).toBeTruthy();
      expect(
        screen.getByText(/confirmo a criação de um novo cliente/i),
      ).toBeTruthy();
    });
  });

  it("vincular navega para o case_id devolvido pelo backend (idempotência)", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/sala-juridica") return Promise.resolve({ data: [SESSAO] });
      if (url === "/sala-juridica/s1") return Promise.resolve({ data: SESSAO });
      if (url === "/cases") {
        return Promise.resolve({
          data: { data: [{ id: "caso-escolhido", titulo: "Caso A" }] },
        });
      }
      return Promise.resolve({ data: {} });
    });
    // Corrida: outra aba já vinculou a sessão a OUTRO caso.
    postMock.mockResolvedValue({
      data: { case_id: "caso-ja-vinculado", ja_convertido: true },
    });
    renderizar();

    await waitFor(() => {
      expect(screen.getAllByText("Análise preliminar").length).toBeGreaterThan(
        0,
      );
    });
    fireEvent.click(screen.getByRole("button", { name: /Vincular a caso/i }));
    fireEvent.change(screen.getByPlaceholderText(/Buscar caso por título/i), {
      target: { value: "Caso" },
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Caso A/i })).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /Caso A/i }));
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    fireEvent.click(screen.getByRole("button", { name: /Confirmar vínculo/i }));

    await waitFor(() => {
      expect(
        screen.getByText("URL_ATUAL:/casos/caso-ja-vinculado"),
      ).toBeTruthy();
    });
  });
});
