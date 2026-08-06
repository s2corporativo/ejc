import { afterEach, describe, expect, it, vi } from "vitest";
import api, { API_BASE_URL } from "./api";
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

// Regressão do prefixo /v1 duplicado (fatia 652-A): o interceptor de request
// já não reescreve /api, /api/v1 ou /v1 do path informado — remover essa poda
// era seguro só porque nenhuma chamada real do repositório ainda os usa. Este
// teste trava o comportamento atual: o path chega ao adapter exatamente como
// foi escrito pela chamada, sem reescrita alguma.
describe("api · request não reescreve o path informado", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    api.defaults.adapter = undefined;
  });

  function capturarUrlEnviada(path: string): Promise<string> {
    return new Promise((resolve) => {
      api.defaults.adapter = async (config) => {
        resolve(String(config.url));
        return {
          data: {},
          status: 200,
          statusText: "OK",
          headers: {},
          config,
        };
      };
      void api.get(path);
    });
  }

  it("baseURL do cliente é o contrato público /api/v1", () => {
    expect(API_BASE_URL).toBe("/api/v1");
  });

  it("path relativo comum chega intacto ao adapter", async () => {
    await expect(capturarUrlEnviada("/despesas")).resolves.toBe("/despesas");
  });

  it("path que por engano reintroduza /v1 NÃO é mais podado", async () => {
    // Antes da fatia 652-A esta chamada seria reescrita para "/v1/despesas"
    // (compensando o prefixo duplicado nos routers). Hoje o cliente resolve
    // /api/v1/v1/despesas — um 404, não um sucesso silencioso — porque o
    // defeito de roteamento que a poda compensava foi corrigido na origem.
    await expect(capturarUrlEnviada("/v1/despesas")).resolves.toBe(
      "/v1/despesas",
    );
  });
});
