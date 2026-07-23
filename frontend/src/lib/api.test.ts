import { afterEach, describe, expect, it, vi } from "vitest";
import api from "./api";
import { toast } from "../components/Toast";

// Exercita o interceptor de resposta REAL do cliente `api`: um adapter mockado
// rejeita com uma resposta HTTP simulada, sem rede. Assim validamos o novo
// tratamento GLOBAL de 403 sem tocar no fluxo de 401/refresh nem nos 403
// especiais (troca de senha obrigatória / configuração de 2FA).
function rejectWith(status: number, data: unknown) {
  api.defaults.adapter = async (config) => {
    const error = Object.assign(
      new Error(`Request failed with status code ${status}`),
      {
        config,
        isAxiosError: true,
        response: { status, data, statusText: "", headers: {}, config },
      },
    );
    return Promise.reject(error);
  };
}

describe("api · tratamento global de 403", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    api.defaults.adapter = undefined;
    // O ramo must_change_password lê window.location.pathname; volta à raiz.
    window.history.replaceState({}, "", "/");
  });

  it("dispara toast padronizado e rejeita num 403 de RBAC comum", async () => {
    const spy = vi.spyOn(toast, "error");
    rejectWith(403, {});

    await expect(api.get("/qualquer-endpoint")).rejects.toMatchObject({
      response: { status: 403 },
    });

    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith("Sem permissão para esta ação");
  });

  it("NÃO dispara o toast comum quando o 403 é must_change_password", async () => {
    // Já em /trocar-senha: o ramo especial não redireciona (evita navegação
    // hard no jsdom) e o toast genérico não deve entrar.
    window.history.replaceState({}, "", "/trocar-senha");
    const spy = vi.spyOn(toast, "error");
    rejectWith(403, { must_change_password: true });

    await expect(api.get("/protegido")).rejects.toMatchObject({
      response: { status: 403 },
    });

    expect(spy).not.toHaveBeenCalled();
  });

  it("NÃO dispara o toast comum quando o 403 exige configurar 2FA", async () => {
    window.history.replaceState({}, "", "/configurar-2fa");
    const spy = vi.spyOn(toast, "error");
    rejectWith(403, { precisa_configurar_2fa: true });

    await expect(api.get("/protegido")).rejects.toMatchObject({
      response: { status: 403 },
    });

    expect(spy).not.toHaveBeenCalled();
  });

  it("não interfere num 200 de sucesso", async () => {
    const spy = vi.spyOn(toast, "error");
    api.defaults.adapter = async (config) => ({
      data: { ok: true },
      status: 200,
      statusText: "OK",
      headers: {},
      config,
    });

    await expect(api.get("/ok")).resolves.toMatchObject({
      data: { ok: true },
    });

    expect(spy).not.toHaveBeenCalled();
  });
});
