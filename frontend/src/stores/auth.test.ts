// Bootstrap da sessão com access token SÓ em memória (FE-02), limpeza do
// caso ativo no logout (FE-07) e persistência parcial do usuário (FE-08).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { User } from "../types";

const simulacoes = vi.hoisted(() => {
  let token: string | null = null;
  return {
    get: vi.fn(),
    refresh: vi.fn(),
    limparCasoAtivo: vi.fn(),
    getAccessToken: () => token,
    setAccessToken: (t: string | null) => {
      token = t;
    },
  };
});

vi.mock("../lib/api", () => ({
  default: { get: simulacoes.get },
  getAccessToken: simulacoes.getAccessToken,
  setAccessToken: simulacoes.setAccessToken,
  refreshAccessToken: simulacoes.refresh,
  limparCasoAtivo: simulacoes.limparCasoAtivo,
  logout: vi.fn(),
}));
vi.mock("../lib/intakeRascunho", () => ({
  RASCUNHO_KEY: "ejc_intake_rascunho",
}));
vi.mock("./cadastroManual", () => ({ limparCadastroManual: vi.fn() }));

const USUARIO_COMPLETO: User = {
  id: "u1",
  email: "advogado@ejc.adv.br",
  full_name: "Advogada Teste",
  role: "advogado",
  permissions: ["casos"],
  phone: "+55 31 99999-0000",
  oab_number: "MG 123456",
  avatar_url: "/users/u1/avatar",
  djen_oab_numero: "123456",
  djen_oab_uf: "MG",
};

async function carregarStore() {
  vi.resetModules();
  return (await import("./auth")).useAuth;
}

beforeEach(() => {
  simulacoes.get.mockReset();
  simulacoes.refresh.mockReset();
  simulacoes.limparCasoAtivo.mockReset();
  simulacoes.setAccessToken(null);
  localStorage.clear();
  sessionStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("auth · bootstrap reidrata o access pelo refresh (FE-02)", () => {
  it("com usuário persistido e sem token, chama /auth/refresh e depois /users/me", async () => {
    localStorage.setItem(
      "ejc_user",
      JSON.stringify({
        id: "u1",
        full_name: "Advogada Teste",
        role: "advogado",
      }),
    );
    simulacoes.refresh.mockImplementation(async () => {
      simulacoes.setAccessToken("novo-access");
      return "novo-access";
    });
    simulacoes.get.mockImplementation((url: string) => {
      if (url === "/users/me")
        return Promise.resolve({ data: USUARIO_COMPLETO });
      if (url === "/users/me/security")
        return Promise.resolve({ data: { permissions: ["casos", "prazos"] } });
      return Promise.reject(new Error(`GET inesperado ${url}`));
    });

    const useAuth = await carregarStore();
    expect(useAuth.getState().status).toBe("initializing");

    await useAuth.getState().bootstrap();

    expect(simulacoes.refresh).toHaveBeenCalledTimes(1);
    expect(simulacoes.get).toHaveBeenCalledWith("/users/me");
    expect(useAuth.getState().status).toBe("authenticated");
    expect(useAuth.getState().user?.permissions).toEqual(["casos", "prazos"]);
    expect(simulacoes.getAccessToken()).toBe("novo-access");
  });

  it("sem indício de sessão anterior NÃO bate no refresh e fica unauthenticated", async () => {
    const useAuth = await carregarStore();
    expect(useAuth.getState().status).toBe("unauthenticated");
    await useAuth.getState().bootstrap();
    expect(simulacoes.refresh).not.toHaveBeenCalled();
    expect(simulacoes.get).not.toHaveBeenCalled();
    expect(useAuth.getState().status).toBe("unauthenticated");
  });

  it("refresh recusado (cookie expirado) derruba a sessão local", async () => {
    localStorage.setItem(
      "ejc_user",
      JSON.stringify({ id: "u1", full_name: "X", role: "advogado" }),
    );
    sessionStorage.setItem("ejc_caso_ativo", JSON.stringify({ id: "c1" }));
    simulacoes.refresh.mockRejectedValue(new Error("401"));

    const useAuth = await carregarStore();
    await useAuth.getState().bootstrap();

    expect(useAuth.getState().status).toBe("unauthenticated");
    expect(useAuth.getState().user).toBeNull();
    expect(localStorage.getItem("ejc_user")).toBeNull();
    expect(simulacoes.limparCasoAtivo).toHaveBeenCalled();
    expect(simulacoes.get).not.toHaveBeenCalled();
  });

  it("com token já em memória vai direto ao /users/me", async () => {
    simulacoes.setAccessToken("tok");
    simulacoes.get.mockImplementation((url: string) =>
      url === "/users/me"
        ? Promise.resolve({ data: USUARIO_COMPLETO })
        : Promise.resolve({ data: {} }),
    );
    const useAuth = await carregarStore();
    await useAuth.getState().bootstrap();
    expect(simulacoes.refresh).not.toHaveBeenCalled();
    expect(useAuth.getState().status).toBe("authenticated");
  });
});

describe("auth · persistência parcial do usuário (FE-08)", () => {
  it("grava só id/full_name/role/permissions/avatar_url em ejc_user", async () => {
    const useAuth = await carregarStore();
    useAuth.getState().setSession(USUARIO_COMPLETO);

    const salvo = JSON.parse(localStorage.getItem("ejc_user") || "{}");
    expect(salvo).toEqual({
      id: "u1",
      full_name: "Advogada Teste",
      role: "advogado",
      permissions: ["casos"],
      avatar_url: "/users/u1/avatar",
    });
    expect(salvo).not.toHaveProperty("email");
    expect(salvo).not.toHaveProperty("phone");
    expect(salvo).not.toHaveProperty("oab_number");
    expect(salvo).not.toHaveProperty("djen_oab_numero");
    // Em memória o usuário segue completo.
    expect(useAuth.getState().user?.email).toBe("advogado@ejc.adv.br");
  });

  it("updateUser mantém o recorte ao persistir", async () => {
    const useAuth = await carregarStore();
    useAuth.getState().setSession(USUARIO_COMPLETO);
    useAuth.getState().updateUser({ phone: "novo", avatar_url: "/a2" });
    const salvo = JSON.parse(localStorage.getItem("ejc_user") || "{}");
    expect(salvo.avatar_url).toBe("/a2");
    expect(salvo).not.toHaveProperty("phone");
  });
});

describe("auth · clearSession (FE-07)", () => {
  it("limpa token, usuário e caso ativo", async () => {
    simulacoes.setAccessToken("tok");
    const useAuth = await carregarStore();
    useAuth.getState().setSession(USUARIO_COMPLETO);

    useAuth.getState().clearSession();

    expect(simulacoes.getAccessToken()).toBeNull();
    expect(localStorage.getItem("ejc_user")).toBeNull();
    expect(simulacoes.limparCasoAtivo).toHaveBeenCalledTimes(1);
    expect(useAuth.getState().status).toBe("unauthenticated");
  });
});
