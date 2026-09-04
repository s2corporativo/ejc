// @vitest-environment jsdom
// Regressão do pente-fino E2E (§5.2): a lista plana de integrações repete a
// mesma chave ("infosimples", "indices_bcb") — inclusive dentro do MESMO
// grupo, porque o backend concatena registries distintos — e a página emitia
// "Encountered two children with the same key" no console.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import api from "../lib/api";
import CentralDiagnostico from "./CentralDiagnostico";

vi.mock("../lib/api", () => ({
  default: {
    get: vi.fn(),
  },
}));

const getMock = vi.mocked(api.get);

const PAYLOAD = {
  gerado_em: "2026-08-30T12:00:00Z",
  status_geral: "ok",
  resumo: { ok: 1, alerta: 0, erro: 0, desligado: 0 },
  aviso: "",
  subsistemas: [
    {
      nome: "Integrações externas",
      status: "ok",
      detalhe: "Todas configuradas.",
      acao_sugerida: "",
      latencia_ms: 12,
      itens: [
        // Mesmo chave + mesmo grupo (caso real do payload de produção).
        {
          chave: "infosimples",
          label: "Infosimples (consultas pagas)",
          grupo: "Jurídico",
          status: "ok",
          detalhe: "",
          acao_sugerida: "",
        },
        {
          chave: "infosimples",
          label: "Infosimples (registro duplicado)",
          grupo: "Jurídico",
          status: "ok",
          detalhe: "",
          acao_sugerida: "",
        },
        // Mesma chave em grupos distintos.
        {
          chave: "indices_bcb",
          label: "Índices BCB (Financeiro)",
          grupo: "Financeiro",
          status: "ok",
          detalhe: "",
          acao_sugerida: "",
        },
        {
          chave: "indices_bcb",
          label: "Índices BCB (Jurídico)",
          grupo: "Jurídico",
          status: "ok",
          detalhe: "",
          acao_sugerida: "",
        },
      ],
    },
  ],
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

describe("CentralDiagnostico — chaves de integrações", () => {
  it("renderiza a mesma chave em grupos distintos sem warning de key duplicada", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => {});
    getMock.mockResolvedValueOnce({ data: PAYLOAD });

    render(<CentralDiagnostico />);

    await waitFor(() =>
      expect(screen.getByText("Integrações externas")).toBeTruthy(),
    );
    // Os quatro itens aparecem — nenhum é descartado por colisão de key.
    expect(screen.getByText("Infosimples (consultas pagas)")).toBeTruthy();
    expect(screen.getByText("Infosimples (registro duplicado)")).toBeTruthy();
    expect(screen.getByText("Índices BCB (Financeiro)")).toBeTruthy();
    expect(screen.getByText("Índices BCB (Jurídico)")).toBeTruthy();

    const keyWarnings = consoleError.mock.calls.filter((call) =>
      call.some(
        (arg) =>
          typeof arg === "string" &&
          arg.includes("two children with the same key"),
      ),
    );
    expect(keyWarnings).toEqual([]);
  });
});
