// ── Intimação DJEN sem caso: vínculo manual + evidência oficial ──────────────
// Auditoria do módulo DJEN (2026-10): comunicação de processo não cadastrado
// (ou de caso encerrado/arquivado) não gerava prazo — "aceitar" exigia caso e
// não havia como vincular. Estes testes travam: o aceite fica bloqueado sem
// caso, o vínculo é feito pela própria tela e a divergência de nº de processo
// exige confirmação explícita; o PDF só vira link se for http(s).
import { describe, it, expect, beforeEach, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const apiGet = vi.fn();
const apiPost = vi.fn();
vi.mock("../../lib/api", () => ({
  __esModule: true,
  default: {
    get: (...a: unknown[]) => apiGet(...a),
    post: (...a: unknown[]) => apiPost(...a),
  },
}));
vi.mock("../../components/Toast", () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}));
vi.mock("../../stores/auth", () => ({
  useAuth: (sel: (s: unknown) => unknown) =>
    sel({ user: { role: "advogado" } }),
}));

import { PrazoSugeridoModal } from "./acoesLegadas";

const SUGESTAO = {
  id: "com-1",
  titulo: "Intimação TJMG",
  dados: { disponivel: false, prazo_sugerido_status: "nenhum" as const },
};

const detalhe = (extra: Record<string, unknown> = {}) => ({
  data: {
    orgao: "1ª Vara Cível",
    texto: "Fica a parte intimada.",
    texto_completo: true,
    link_oficial: "https://comunica.pje.jus.br/pdf/1",
    case_id: null,
    aviso_escopo: "Esta lista reúne apenas comunicações publicadas no DJEN.",
    ...extra,
  },
});

beforeEach(() => {
  apiGet.mockReset();
  apiPost.mockReset();
});

function abrir() {
  return render(
    <PrazoSugeridoModal
      sugestao={SUGESTAO}
      onClose={vi.fn()}
      onResolvido={vi.fn()}
    />,
  );
}

describe("PrazoSugeridoModal — evidência e vínculo", () => {
  it("sem caso: mostra texto oficial/aviso e bloqueia o aceite do prazo", async () => {
    apiGet.mockResolvedValueOnce(detalhe());
    abrir();

    expect(await screen.findByText(/Fica a parte intimada/)).toBeTruthy();
    expect(screen.getByText(/apenas comunicações publicadas no DJEN/)).toBeTruthy();
    expect(screen.getByText("Sem caso vinculado")).toBeTruthy();
    const link = screen.getByText("Abrir PDF oficial") as HTMLAnchorElement;
    expect(link.getAttribute("rel")).toContain("noopener");

    fireEvent.change(document.querySelector('input[type="date"]')!, {
      target: { value: "2026-12-01" },
    });
    const aceitar = screen.getByText("Aceitar e criar prazo") as HTMLButtonElement;
    expect(aceitar.disabled).toBe(true);
  });

  it("com caso: não oferece vínculo e permite aceitar", async () => {
    apiGet.mockResolvedValueOnce(detalhe({ case_id: "case-1" }));
    abrir();
    await screen.findByText(/Fica a parte intimada/);
    expect(screen.queryByText("Sem caso vinculado")).toBeNull();
    fireEvent.change(document.querySelector('input[type="date"]')!, {
      target: { value: "2026-12-01" },
    });
    expect(
      (screen.getByText("Aceitar e criar prazo") as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("vincula pelo caso buscado (inclui arquivados) e libera o aceite", async () => {
    apiGet
      .mockResolvedValueOnce(detalhe()) // detalhe inicial
      .mockResolvedValueOnce({
        data: { data: [{ id: "case-9", titulo: "Caso Arquivado", numero_processo: "123" }] },
      }) // busca de casos
      .mockResolvedValueOnce(detalhe({ case_id: "case-9" })); // recarga
    apiPost.mockResolvedValueOnce({ data: { case_id: "case-9" } });
    abrir();

    await screen.findByText("Sem caso vinculado");
    fireEvent.change(screen.getByPlaceholderText("Título ou nº do processo"), {
      target: { value: "arquiv" },
    });
    fireEvent.click(screen.getByText("Buscar"));
    expect(apiGet).toHaveBeenCalledWith(
      "/cases/",
      expect.objectContaining({
        params: expect.objectContaining({ arquivo: "todos" }),
      }),
    );
    fireEvent.click(await screen.findByText("Vincular"));

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith("/intimacoes/com-1/vincular-caso", {
        case_id: "case-9",
        confirmar_divergencia: false,
      }),
    );
    await waitFor(() => expect(screen.queryByText("Sem caso vinculado")).toBeNull());
  });

  it("divergência de nº de processo exige confirmação explícita", async () => {
    apiGet
      .mockResolvedValueOnce(detalhe())
      .mockResolvedValueOnce({
        data: { data: [{ id: "case-9", titulo: "Outro", numero_processo: "999" }] },
      });
    apiPost
      .mockRejectedValueOnce({
        response: {
          status: 422,
          data: { detail: "O número do processo da comunicação difere do cadastrado no caso." },
        },
      })
      .mockResolvedValueOnce({ data: { case_id: "case-9" } });
    apiGet.mockResolvedValueOnce(detalhe({ case_id: "case-9" }));
    abrir();

    await screen.findByText("Sem caso vinculado");
    fireEvent.change(screen.getByPlaceholderText("Título ou nº do processo"), {
      target: { value: "outro" },
    });
    fireEvent.click(screen.getByText("Buscar"));
    fireEvent.click(await screen.findByText("Vincular"));
    fireEvent.click(await screen.findByText("Confirmar divergência"));

    await waitFor(() =>
      expect(apiPost).toHaveBeenLastCalledWith("/intimacoes/com-1/vincular-caso", {
        case_id: "case-9",
        confirmar_divergencia: true,
      }),
    );
  });

  it("link com esquema perigoso não vira âncora", async () => {
    apiGet.mockResolvedValueOnce(detalhe({ link_oficial: "javascript:alert(1)" }));
    abrir();
    await screen.findByText(/Fica a parte intimada/);
    expect(screen.queryByText("Abrir PDF oficial")).toBeNull();
  });

  it("vencimento passado exige marcar a confirmação e a envia na requisição", async () => {
    apiGet.mockResolvedValueOnce(detalhe({ case_id: "case-1" }));
    apiPost.mockResolvedValueOnce({
      data: { criado: true, data_prazo: "2020-01-10" },
    });
    abrir();
    await screen.findByText(/Fica a parte intimada/);

    fireEvent.change(document.querySelector('input[type="date"]')!, {
      target: { value: "2020-01-10" },
    });
    const aceitar = screen.getByText("Aceitar e criar prazo") as HTMLButtonElement;
    expect(aceitar.disabled).toBe(true); // sem confirmar, bloqueado
    expect(screen.getByText(/já passou/)).toBeTruthy();

    fireEvent.click(screen.getByRole("checkbox"));
    expect(aceitar.disabled).toBe(false);
    fireEvent.click(aceitar);

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith("/intimacoes/com-1/aceitar-prazo", {
        data_prazo: "2020-01-10",
        confirmar_prazo_vencido: true,
      }),
    );
  });

  it("vencimento futuro não mostra confirmação nem envia o campo", async () => {
    apiGet.mockResolvedValueOnce(detalhe({ case_id: "case-1" }));
    apiPost.mockResolvedValueOnce({ data: { criado: true, data_prazo: "2999-01-10" } });
    abrir();
    await screen.findByText(/Fica a parte intimada/);
    fireEvent.change(document.querySelector('input[type="date"]')!, {
      target: { value: "2999-01-10" },
    });
    expect(screen.queryByRole("checkbox")).toBeNull();
    fireEvent.click(screen.getByText("Aceitar e criar prazo"));
    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith("/intimacoes/com-1/aceitar-prazo", {
        data_prazo: "2999-01-10",
      }),
    );
  });
});
