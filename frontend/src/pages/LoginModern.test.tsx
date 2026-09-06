// FE-11: renderização da tela de login + estados (vazio, erro, 2ª etapa TOTP,
// sucesso) e a integração com o access token em memória (FE-02).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";

const simulacoes = vi.hoisted(() => ({
  post: vi.fn(),
  setAccessToken: vi.fn(),
  setSession: vi.fn(),
  bootstrap: vi.fn(async () => {}),
}));

vi.mock("../lib/api", () => ({
  default: { post: simulacoes.post, get: vi.fn() },
  setAccessToken: simulacoes.setAccessToken,
  getAccessToken: () => null,
  refreshAccessToken: vi.fn(),
  logout: vi.fn(),
}));
vi.mock("../stores/auth", () => ({
  useAuth: () => ({
    setSession: simulacoes.setSession,
    bootstrap: simulacoes.bootstrap,
  }),
}));
vi.mock("../stores/preferences", () => ({
  usePreferencesStore: { getState: () => ({ homeRoute: "/" }) },
}));
vi.mock("../config/moduleRegistry", () => ({
  canRoleAccessPath: () => true,
}));

import LoginModern from "./LoginModern";

function renderizar(rota = "/login") {
  return render(
    <MemoryRouter initialEntries={[rota]}>
      <Routes>
        <Route path="/login" element={<LoginModern />} />
        <Route path="/" element={<div>Home autenticada</div>} />
        <Route path="/trocar-senha" element={<div>Trocar senha</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

function preencherEEnviar(email = "adv@ejc.adv.br", senha = "segredo-123") {
  fireEvent.change(screen.getByPlaceholderText("seu@escritorio.adv.br"), {
    target: { value: email },
  });
  fireEvent.change(screen.getByPlaceholderText("********"), {
    target: { value: senha },
  });
  fireEvent.click(screen.getByRole("button", { name: /Entrar/ }));
}

function rejeitarCom(detail: string) {
  simulacoes.post.mockRejectedValueOnce(
    Object.assign(new Error("401"), {
      response: { status: 401, data: { detail } },
    }),
  );
}

beforeEach(() => {
  simulacoes.post.mockReset();
  simulacoes.setAccessToken.mockReset();
  simulacoes.setSession.mockReset();
  simulacoes.bootstrap.mockClear();
});
afterEach(() => cleanup());

describe("página /login (LoginModern)", () => {
  it("estado inicial: formulário vazio, sem erro, campos habilitados", () => {
    renderizar();
    expect(screen.getByRole("heading", { name: "Entrar no EJC" })).toBeTruthy();
    const email = screen.getByPlaceholderText(
      "seu@escritorio.adv.br",
    ) as HTMLInputElement;
    expect(email.value).toBe("");
    expect(email.disabled).toBe(false);
    expect(screen.queryByText(/Falha no login/)).toBeNull();
    expect(
      screen.getByRole("link", { name: "Esqueci minha senha" }),
    ).toBeTruthy();
  });

  it("estado de erro: credenciais inválidas mostram o detail do backend", async () => {
    rejeitarCom("E-mail ou senha inválidos");
    renderizar();
    preencherEEnviar();
    expect(await screen.findByText("E-mail ou senha inválidos")).toBeTruthy();
    expect(simulacoes.setAccessToken).not.toHaveBeenCalled();
    expect(simulacoes.setSession).not.toHaveBeenCalled();
  });

  it("segunda etapa: 'TOTP obrigatório' troca a tela para o código de 6 dígitos", async () => {
    rejeitarCom("TOTP obrigatório para este usuário");
    renderizar();
    preencherEEnviar();
    expect(
      await screen.findByRole("heading", { name: "Confirmar autenticação" }),
    ).toBeTruthy();
    expect(screen.getByPlaceholderText("000000")).toBeTruthy();
    const email = screen.getByPlaceholderText(
      "seu@escritorio.adv.br",
    ) as HTMLInputElement;
    expect(email.disabled).toBe(true);
  });

  it("sucesso: guarda o access EM MEMÓRIA (não em localStorage), abre a sessão e navega", async () => {
    simulacoes.post.mockResolvedValueOnce({
      data: {
        access_token: "tok-login",
        user_id: "u1",
        full_name: "Advogada Teste",
        role: "advogado",
      },
    });
    renderizar();
    preencherEEnviar();

    await waitFor(() => {
      expect(simulacoes.setAccessToken).toHaveBeenCalledWith("tok-login");
    });
    expect(localStorage.getItem("ejc_access")).toBeNull();
    expect(simulacoes.setSession).toHaveBeenCalledWith({
      id: "u1",
      email: "adv@ejc.adv.br",
      full_name: "Advogada Teste",
      role: "advogado",
    });
    expect(simulacoes.bootstrap).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Home autenticada")).toBeTruthy();
  });

  it("must_change_password leva a /trocar-senha sem bootstrap", async () => {
    simulacoes.post.mockResolvedValueOnce({
      data: {
        access_token: "tok",
        user_id: "u1",
        full_name: "X",
        role: "advogado",
        must_change_password: true,
      },
    });
    renderizar();
    preencherEEnviar();
    expect(await screen.findByText("Trocar senha")).toBeTruthy();
    expect(simulacoes.bootstrap).not.toHaveBeenCalled();
  });

  it("?motivo=senha-alterada mostra o aviso de sucesso", () => {
    renderizar("/login?motivo=senha-alterada");
    expect(screen.getByRole("status").textContent).toMatch(
      /Senha alterada com sucesso/,
    );
  });
});
