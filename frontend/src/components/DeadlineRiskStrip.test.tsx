// @vitest-environment jsdom
// Regressão da auditoria funcional de 22/08/2026 (Issue #1237), encontrada na
// passagem pela interface renderizada: o dashboard exibia, lado a lado,
// "0 vencido(s)" neste radar e "3 prazos vencidos" no card de Prioridades.
//
// Causa: `status` no backend é igualdade exata, e o job das 07:10
// (`scheduler._marcar_prazos_vencidos`) move o prazo estourado de "pendente"
// para "vencido". Buscando só "pendente", o radar nunca recebia um prazo
// vencido — contava zero por construção, todo dia depois das 07:10. É o número
// que este componente existe para mostrar.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";

const get = vi.fn();
vi.mock("../lib/api", () => ({
  default: { get: (...a: unknown[]) => get(...a) },
}));
vi.mock("../stores/auth", () => ({
  useAuth: (sel: (s: unknown) => unknown) =>
    sel({ user: { role: "advogado" } }),
}));

import DeadlineRiskStrip from "./DeadlineRiskStrip";

const VENCIDO = {
  id: "v1",
  data_prazo: "2026-05-29",
  data_intimacao: "2026-05-24",
  dias_restantes: -85,
  confirmado: true,
  ciencia_confirmada: true,
};
const PENDENTE = {
  id: "p1",
  data_prazo: "2026-12-01",
  dias_restantes: 40,
  confirmado: true,
  ciencia_confirmada: true,
};

function responder(porStatus: Record<string, unknown[]>) {
  get.mockImplementation(
    (url: string, cfg?: { params?: { status?: string } }) => {
      if (url !== "/deadlines/")
        return Promise.reject(new Error("rota inesperada"));
      return Promise.resolve({
        data: { data: porStatus[cfg?.params?.status ?? ""] ?? [] },
      });
    },
  );
}

describe("DeadlineRiskStrip — prazo vencido não pode sumir do radar", () => {
  afterEach(() => {
    cleanup();
    get.mockReset();
  });

  it("conta o prazo que o job das 07:10 marcou como 'vencido'", async () => {
    responder({ pendente: [PENDENTE], vencido: [VENCIDO] });
    render(
      <MemoryRouter>
        <DeadlineRiskStrip />
      </MemoryRouter>,
    );
    // Antes da correção o componente pedia só `status=pendente` e este texto
    // seria "0 vencido(s)" — com o prazo estourado presente no banco.
    await waitFor(() => expect(screen.getByText("1 vencido(s)")).toBeTruthy());
  });

  it("busca as duas faixas em aberto, pendente e vencido", async () => {
    responder({ pendente: [], vencido: [] });
    render(
      <MemoryRouter>
        <DeadlineRiskStrip />
      </MemoryRouter>,
    );
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    const status = get.mock.calls
      .map((c) => (c[1] as { params?: { status?: string } })?.params?.status)
      .sort();
    expect(status).toEqual(["pendente", "vencido"]);
  });

  it("sem prazo estourado, o radar segue mostrando zero", async () => {
    responder({ pendente: [PENDENTE], vencido: [] });
    render(
      <MemoryRouter>
        <DeadlineRiskStrip />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("0 vencido(s)")).toBeTruthy());
  });
});
