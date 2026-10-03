// @vitest-environment jsdom
// Plano ERP/agenda/IA (achado E3): registrar o recebimento e registrar a NFS-e
// eram passos desconectados. Depois do pagamento, a tela oferece o registro da
// nota já preenchido; reembolso de custas não é serviço e não recebe a oferta.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";

const get = vi.fn();
const post = vi.fn();
vi.mock("../lib/api", () => ({
  default: {
    get: (...a: unknown[]) => get(...a),
    post: (...a: unknown[]) => post(...a),
  },
}));
vi.mock("../components/Toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock("qrcode", () => ({ default: { toDataURL: vi.fn() } }));

import Honorarios from "./Honorarios";

function feeRow(tipo: string) {
  return {
    id: "fee-1",
    tipo,
    status: "pendente",
    descricao: "Honorários contratuais — parcela 1",
    valor: 1500,
    client_id: "cli-1",
    client_nome: "Cliente Teste",
    created_at: "2026-10-01T00:00:00Z",
  };
}

let estadoDestino: unknown = undefined;
function Destino() {
  const loc = useLocation();
  estadoDestino = loc.state;
  return <div>tela-nfse</div>;
}

function montar() {
  return render(
    <MemoryRouter initialEntries={["/financeiro?tab=honorarios"]}>
      <Routes>
        <Route path="/financeiro" element={<Honorarios />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function registrarPagamento() {
  fireEvent.click((await screen.findAllByTitle("Registrar pagamento"))[0]);
  await screen.findByText("Valor pago (R$)");
  fireEvent.click(screen.getByText("Confirmar"));
  await waitFor(() =>
    expect(post).toHaveBeenCalledWith(
      "/fees/fee-1/pagamentos",
      expect.objectContaining({ valor: 1500 }),
    ),
  );
}

describe("Honorários — oferta de NFS-e após o recebimento", () => {
  let tipo = "fixo";
  beforeEach(() => {
    estadoDestino = undefined;
    get.mockImplementation((url: string) => {
      if (url === "/fees/fee-1/pagamentos") {
        return Promise.resolve({ data: { saldo: 1500, pagamentos: [] } });
      }
      if (url.startsWith("/fees")) {
        return Promise.resolve({ data: { data: [feeRow(tipo)], total: 1 } });
      }
      return Promise.resolve({ data: { data: [], total: 0 } });
    });
    post.mockResolvedValue({ data: {} });
  });
  afterEach(() => {
    cleanup();
    get.mockReset();
    post.mockReset();
  });

  it("oferece registrar a NFS-e e leva os dados pelo state, fora da URL", async () => {
    tipo = "fixo";
    render(
      <MemoryRouter initialEntries={["/financeiro?tab=honorarios"]}>
        <Routes>
          <Route
            path="/financeiro"
            element={<RotaFinanceiro />}
          />
        </Routes>
      </MemoryRouter>,
    );
    await registrarPagamento();
    fireEvent.click(await screen.findByText("Registrar NFS-e"));

    await screen.findByText("tela-nfse");
    expect(estadoDestino).toEqual({
      notaDoHonorario: {
        fee_id: "fee-1",
        client_id: "cli-1",
        valor: "1500",
        descricao: "Honorários contratuais — parcela 1",
      },
    });
  });

  it("reembolso de custas não recebe a oferta de NFS-e", async () => {
    tipo = "custas_despesas";
    montar();
    await registrarPagamento();
    expect(screen.queryByText("Registrar NFS-e")).toBeNull();
  });

  it("'Agora não' dispensa a oferta", async () => {
    tipo = "fixo";
    montar();
    await registrarPagamento();
    fireEvent.click(await screen.findByText("Agora não"));
    expect(screen.queryByText("Registrar NFS-e")).toBeNull();
  });
});

function RotaFinanceiro() {
  const loc = useLocation();
  return new URLSearchParams(loc.search).get("tab") === "nfse" ? (
    <Destino />
  ) : (
    <Honorarios />
  );
}
