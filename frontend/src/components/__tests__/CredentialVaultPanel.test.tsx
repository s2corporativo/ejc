import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";

// O painel busca o status de 2FA em /users/me/security via o api central.
const apiGet = vi.fn();
vi.mock("../../lib/api", () => ({
  __esModule: true,
  default: { get: (...args: unknown[]) => apiGet(...args) },
}));

// Client do cofre mockado — nenhum valor de segredo trafega por aqui de verdade.
const listarCofre = vi.fn();
const cadastrarCredencial = vi.fn();
const revogarCredencial = vi.fn();
const historicoCampo = vi.fn();
const importarEnv = vi.fn();
const testarProvider = vi.fn();
vi.mock("../../lib/cofre", () => ({
  listarCofre: (...a: unknown[]) => listarCofre(...a),
  cadastrarCredencial: (...a: unknown[]) => cadastrarCredencial(...a),
  revogarCredencial: (...a: unknown[]) => revogarCredencial(...a),
  historicoCampo: (...a: unknown[]) => historicoCampo(...a),
  importarEnv: (...a: unknown[]) => importarEnv(...a),
  testarProvider: (...a: unknown[]) => testarProvider(...a),
}));

// Toast mockado para verificar os avisos (o Toaster não é montado nos testes).
const toastError = vi.fn();
const toastSuccess = vi.fn();
vi.mock("../Toast", () => ({
  toast: {
    error: (...a: unknown[]) => toastError(...a),
    success: (...a: unknown[]) => toastSuccess(...a),
    info: vi.fn(),
  },
}));

import CredentialVaultPanel, {
  groupProviders,
  resolveCredentialState,
} from "../CredentialVaultPanel";
import type { CampoStatus, ProviderStatus } from "../../lib/cofre";

function campo(overrides: Partial<CampoStatus> = {}): CampoStatus {
  return {
    field_key: "GROQ_API_KEY",
    tipo: "api_key",
    rotulo: "API Key da Groq",
    obrigatorio: true,
    estado: "ausente",
    ...overrides,
  };
}

const PROVIDERS: ProviderStatus[] = [
  { provider_key: "groq", campos: [campo()] },
  {
    provider_key: "smtp",
    campos: [
      campo({
        field_key: "SMTP_PASSWORD",
        tipo: "senha",
        rotulo: "Senha SMTP",
        estado: "configurada",
        last4: "1234",
        versao: 2,
        origem: "manual",
        updated_at: "2026-07-01T10:00:00Z",
        last_test_status: "invalida",
        last_test_detail: "HTTP 401",
      }),
    ],
  },
];

function mountPanel(totpEnabled = false) {
  listarCofre.mockResolvedValue(PROVIDERS);
  apiGet.mockResolvedValue({ data: { totp_enabled: totpEnabled } });
  return render(<CredentialVaultPanel />);
}

describe("CredentialVaultPanel — helpers puros", () => {
  it("resolveCredentialState prioriza ausente > resultado de teste > configurada", () => {
    expect(resolveCredentialState(campo({ estado: "ausente" }))).toBe(
      "ausente",
    );
    expect(
      resolveCredentialState(
        campo({ estado: "configurada", last_test_status: "invalida" }),
      ),
    ).toBe("invalida");
    expect(resolveCredentialState(campo({ estado: "configurada" }))).toBe(
      "configurada",
    );
  });

  it("groupProviders agrupa pelos grupos institucionais na ordem canônica", () => {
    const grupos = groupProviders(PROVIDERS);
    expect(grupos.map(([g]) => g)).toEqual(["Inteligência", "Comunicação"]);
  });
});

describe("CredentialVaultPanel — render e estados", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renderiza grupos, badges de estado e last4 mascarado", async () => {
    mountPanel();

    expect(await screen.findByText("API Key da Groq")).toBeTruthy();
    // Grupos institucionais
    expect(screen.getByText("Inteligência")).toBeTruthy();
    expect(screen.getByText("Comunicação")).toBeTruthy();
    // Estado ausente (groq) e estado derivado do teste (smtp inválida)
    expect(screen.getByText("Ausente")).toBeTruthy();
    expect(screen.getByText("Inválida")).toBeTruthy();
    // last4 mascarado, nunca o valor
    expect(screen.getByText("••••1234")).toBeTruthy();
  });
});

describe("CredentialVaultPanel — modal de cadastro exige senha e não vaza o segredo", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  async function abrirCadastro() {
    mountPanel();
    const card = (await screen.findByText("API Key da Groq")).closest(".card");
    fireEvent.click(
      within(card as HTMLElement).getByRole("button", { name: /Cadastrar/ }),
    );
    return within(await screen.findByRole("dialog"));
  }

  it("não chama a API sem a senha atual", async () => {
    const dialog = await abrirCadastro();
    // Preenche só o segredo, sem a senha atual.
    fireEvent.change(dialog.getByPlaceholderText(/valor do segredo/i), {
      target: { value: "sk-teste-123" },
    });
    fireEvent.click(dialog.getByRole("button", { name: /Cadastrar/ }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(cadastrarCredencial).not.toHaveBeenCalled();
  });

  it("envia o segredo pela API e NÃO o renderiza em nenhum lugar após o submit", async () => {
    const SEGREDO = "sk-super-secreto-XYZ-987";
    cadastrarCredencial.mockResolvedValue({
      id: "1",
      provider_key: "groq",
      field_key: "GROQ_API_KEY",
      tipo: "api_key",
      last4: "987",
      versao: 1,
      ativo: true,
      origem: "manual",
      overlay_aplicado: true,
    });

    const dialog = await abrirCadastro();
    fireEvent.change(dialog.getByPlaceholderText(/valor do segredo/i), {
      target: { value: SEGREDO },
    });
    fireEvent.change(dialog.getByPlaceholderText(/Confirme sua identidade/i), {
      target: { value: "minha-senha" },
    });
    fireEvent.click(dialog.getByRole("button", { name: /Cadastrar/ }));

    await waitFor(() =>
      expect(cadastrarCredencial).toHaveBeenCalledWith(
        "groq",
        "GROQ_API_KEY",
        SEGREDO,
        { senha_atual: "minha-senha", codigo_totp: undefined },
      ),
    );

    // O modal fecha após o sucesso...
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    // ...o segredo não aparece no texto renderizado...
    expect(document.body.textContent).not.toContain(SEGREDO);
    // ...nem sobrevive no `value` de NENHUM input controlado (textContent não
    // cobre value de input — esta varredura é o que realmente prova a limpeza).
    document.querySelectorAll("input").forEach((input) => {
      expect((input as HTMLInputElement).value).not.toContain(SEGREDO);
    });

    // Reabrir o modal deve trazer o campo do segredo VAZIO (estado local do
    // modal foi descartado ao desmontar; nada persistiu em estado global).
    const card = (await screen.findByText("API Key da Groq")).closest(".card");
    fireEvent.click(
      within(card as HTMLElement).getByRole("button", { name: /Cadastrar/ }),
    );
    const reaberto = within(await screen.findByRole("dialog"));
    const campoSegredo = reaberto.getByPlaceholderText(
      /valor do segredo/i,
    ) as HTMLInputElement;
    expect(campoSegredo.value).toBe("");
  });
});

describe("CredentialVaultPanel — botão Testar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  async function headerDo(providerLabel: string) {
    mountPanel();
    const header = (await screen.findByText(providerLabel)).closest("div");
    return within(header as HTMLElement);
  }

  it("sucesso atualiza o badge do provider com o estado retornado (sem valor no DOM)", async () => {
    // SMTP começa "Inválida" (last_test_status); o teste ao vivo devolve OK.
    testarProvider.mockResolvedValue({
      provider_key: "smtp",
      estado: "configurada",
      detalhe: "Conexão SMTP estabelecida (login aceito).",
      last_test_at: "2026-07-19T12:00:00Z",
      campos_atualizados: 1,
    });

    const header = await headerDo("E-mail (SMTP)");
    expect(screen.getByText("Inválida")).toBeTruthy();

    fireEvent.click(header.getByRole("button", { name: /Testar/ }));

    await waitFor(() => expect(testarProvider).toHaveBeenCalledWith("smtp"));
    // Chamado APENAS com o provider_key — nenhum corpo/segredo trafega.
    expect(testarProvider.mock.calls[0]).toEqual(["smtp"]);
    // Badge migra de Inválida → Configurada com o veredito do teste.
    expect(await screen.findByText("Configurada")).toBeTruthy();
    expect(screen.queryByText("Inválida")).toBeNull();
    // O `detalhe` retornado passa a ser exibido no card.
    expect(
      screen.getByText(/Conexão SMTP estabelecida \(login aceito\)\./),
    ).toBeTruthy();
    expect(toastSuccess).toHaveBeenCalled();
  });

  it("falha no teste mostra toast de erro e não derruba o painel", async () => {
    testarProvider.mockRejectedValue({
      response: { data: { detail: "Timeout ao conectar." } },
    });

    const header = await headerDo("Groq");
    fireEvent.click(header.getByRole("button", { name: /Testar/ }));

    await waitFor(() => expect(testarProvider).toHaveBeenCalledWith("groq"));
    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith("Timeout ao conectar."),
    );
    // Painel segue de pé (o rótulo do provider continua renderizado).
    expect(screen.getByText("Groq")).toBeTruthy();
  });
});
