import axios from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";
import api, {
  getAccessToken,
  refreshAccessToken,
  setAccessToken,
} from "./api";

describe("sessão com access token somente em memória", () => {
  afterEach(() => {
    setAccessToken(null);
    vi.restoreAllMocks();
    api.defaults.adapter = undefined;
    localStorage.removeItem("ejc_access");
  });

  it("não persiste o bearer no localStorage", () => {
    setAccessToken("mem-only");
    expect(getAccessToken()).toBe("mem-only");
    expect(localStorage.getItem("ejc_access")).toBeNull();
  });

  it("refresh via cookie atualiza apenas a memória", async () => {
    vi.spyOn(axios, "post").mockResolvedValue({
      data: { access_token: "renovado" },
    } as never);

    await expect(refreshAccessToken()).resolves.toBe("renovado");
    expect(getAccessToken()).toBe("renovado");
    expect(localStorage.getItem("ejc_access")).toBeNull();
  });

  it("requisições concorrentes compartilham um único refresh", async () => {
    let resolver!: (value: unknown) => void;
    const pendente = new Promise((resolve) => {
      resolver = resolve;
    });
    const post = vi.spyOn(axios, "post").mockReturnValue(pendente as never);

    const a = refreshAccessToken();
    const b = refreshAccessToken();
    expect(post).toHaveBeenCalledTimes(1);

    resolver({ data: { access_token: "um-so" } });
    await expect(Promise.all([a, b])).resolves.toEqual(["um-so", "um-so"]);
    expect(getAccessToken()).toBe("um-so");
  });
});
