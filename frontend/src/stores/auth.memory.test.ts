import axios from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";
import api, { getAccessToken, setAccessToken } from "../lib/api";
import { useAuth } from "./auth";

function ok(config: any, data: unknown) {
  return Promise.resolve({
    data,
    status: 200,
    statusText: "OK",
    headers: {},
    config,
  });
}

describe("auth bootstrap com bearer em memória", () => {
  afterEach(() => {
    setAccessToken(null);
    useAuth.setState({ user: null, status: "initializing" });
    api.defaults.adapter = undefined;
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("restaura a sessão após reload usando somente o refresh cookie", async () => {
    setAccessToken(null);
    localStorage.setItem(
      "ejc_user",
      JSON.stringify({ id: "u1", email: "u@example.com", role: "advogado" }),
    );

    vi.spyOn(axios, "post").mockResolvedValue({
      data: { access_token: "novo-access" },
    } as never);

    api.defaults.adapter = async (config) => {
      if (config.url === "/users/me") {
        return ok(config, {
          id: "u1",
          email: "u@example.com",
          full_name: "Usuário Teste",
          role: "advogado",
        }) as any;
      }
      if (config.url === "/users/me/security") {
        return ok(config, { permissions: ["cases:read"] }) as any;
      }
      throw new Error("URL inesperada: " + config.url);
    };

    await useAuth.getState().bootstrap();

    expect(getAccessToken()).toBe("novo-access");
    expect(localStorage.getItem("ejc_access")).toBeNull();
    expect(useAuth.getState().status).toBe("authenticated");
    expect(useAuth.getState().user).toMatchObject({
      id: "u1",
      role: "advogado",
      permissions: ["cases:read"],
    });
  });
});
