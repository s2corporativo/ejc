import { afterEach, describe, expect, it, vi } from "vitest";
import api, {
  API_TIMEOUT_LONGO_MS,
  API_TIMEOUT_MS,
  CHAVE_CASO_ATIVO,
  getAccessToken,
  limparCasoAtivo,
  mensagemRateLimit,
  segundosRetryAfter,
  setAccessToken,
} from "./api";
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

// ── FE-02 · access token só em memória ─────────────────────────────────────
describe("api · access token em memória (FE-02)", () => {
  afterEach(() => {
    setAccessToken(null);
    api.defaults.adapter = undefined;
    localStorage.clear();
  });

  it("nunca grava o access em localStorage e envia o Bearer a partir da memória", async () => {
    setAccessToken("tok-memoria");
    let authorization: unknown;
    api.defaults.adapter = async (config) => {
      authorization = config.headers?.Authorization;
      return { data: {}, status: 200, statusText: "OK", headers: {}, config };
    };
    await api.get("/ping");
    expect(authorization).toBe("Bearer tok-memoria");
    expect(localStorage.getItem("ejc_access")).toBeNull();
    expect(getAccessToken()).toBe("tok-memoria");
  });

  it("setAccessToken(null) e string vazia limpam o token", () => {
    setAccessToken("x");
    setAccessToken("   ");
    expect(getAccessToken()).toBeNull();
  });
});

// ── FE-03 · timeout padrão + overrides + 429 ───────────────────────────────
describe("api · timeout e rate limit (FE-03)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    api.defaults.adapter = undefined;
  });

  function capturarTimeout(): { valor: () => number | undefined } {
    let timeout: number | undefined;
    api.defaults.adapter = async (config) => {
      timeout = config.timeout;
      return { data: {}, status: 200, statusText: "OK", headers: {}, config };
    };
    return { valor: () => timeout };
  }

  it("aplica 30 s por padrão", async () => {
    const t = capturarTimeout();
    await api.get("/cases/");
    expect(t.valor()).toBe(API_TIMEOUT_MS);
    expect(API_TIMEOUT_MS).toBe(30_000);
  });

  it("eleva o timeout para rotas de IA e para upload multipart", async () => {
    const t = capturarTimeout();
    await api.post("/ai/chat", { mensagem: "oi" });
    expect(t.valor()).toBe(API_TIMEOUT_LONGO_MS);

    await api.post("/legal-docs/gerar", {});
    expect(t.valor()).toBe(API_TIMEOUT_LONGO_MS);

    await api.post("/raio-x/analisar", {});
    expect(t.valor()).toBe(API_TIMEOUT_LONGO_MS);

    const fd = new FormData();
    fd.append("file", new Blob(["x"]), "a.txt");
    await api.post("/documents/upload", fd);
    expect(t.valor()).toBe(API_TIMEOUT_LONGO_MS);

    await api.post("/qualquer/upload", "raw", {
      headers: { "Content-Type": "multipart/form-data" },
    });
    expect(t.valor()).toBe(API_TIMEOUT_LONGO_MS);
  });

  it("respeita timeout explícito do chamador", async () => {
    const t = capturarTimeout();
    await api.post("/ai/chat", {}, { timeout: 5_000 });
    expect(t.valor()).toBe(5_000);
  });

  it("num 429 dispara toast pt-BR com o Retry-After e rejeita", async () => {
    const spy = vi.spyOn(toast, "error");
    api.defaults.adapter = async (config) => {
      const error = Object.assign(
        new Error("Request failed with status code 429"),
        {
          config,
          isAxiosError: true,
          response: {
            status: 429,
            data: { detail: "Rate limit exceeded" },
            statusText: "",
            headers: { "retry-after": "12" },
            config,
          },
        },
      );
      return Promise.reject(error);
    };
    await expect(api.get("/cases/")).rejects.toMatchObject({
      response: { status: 429 },
    });
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith(
      "Muitas requisições em pouco tempo. Tente novamente em 12 segundos.",
    );
  });

  it("mensagemRateLimit lida com HTTP-date, ausência e 1 segundo", () => {
    expect(mensagemRateLimit(undefined)).toBe(
      "Muitas requisições em pouco tempo. Aguarde um instante e tente novamente.",
    );
    expect(mensagemRateLimit("1")).toBe(
      "Muitas requisições em pouco tempo. Tente novamente em 1 segundo.",
    );
    const daqui30s = new Date(Date.now() + 30_000).toUTCString();
    const seg = segundosRetryAfter(daqui30s);
    expect(seg).toBeGreaterThanOrEqual(29);
    expect(seg).toBeLessThanOrEqual(31);
    expect(segundosRetryAfter("lixo")).toBeNull();
  });
});

// ── FE-07 · caso ativo não sobrevive ao logout ─────────────────────────────
describe("api · limparCasoAtivo (FE-07)", () => {
  it("remove ejc_caso_ativo do sessionStorage", () => {
    sessionStorage.setItem(
      CHAVE_CASO_ATIVO,
      JSON.stringify({ id: "c1", titulo: "Sigiloso" }),
    );
    limparCasoAtivo();
    expect(sessionStorage.getItem(CHAVE_CASO_ATIVO)).toBeNull();
  });
});
