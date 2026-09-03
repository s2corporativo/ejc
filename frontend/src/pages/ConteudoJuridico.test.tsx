import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ConteudoJuridico, {
  normalizarConteudo,
  parsearFaq,
  parsearGlossario,
} from "./ConteudoJuridico";

const postMock = vi.fn();
vi.mock("../lib/api", () => ({
  default: { post: (...args: unknown[]) => postMock(...args) },
}));

beforeEach(() => postMock.mockReset());

describe("parse de FAQ/Glossário", () => {
  it("lê JSON com faq[] (inclusive dentro de cerca ```json)", () => {
    const conteudo =
      '```json\n{"faq":[{"pergunta":"Posso cancelar?","resposta":"Sim, em 7 dias."}]}\n```';
    expect(parsearFaq(conteudo)).toEqual([
      { pergunta: "Posso cancelar?", resposta: "Sim, em 7 dias." },
    ]);
  });
  it("texto livre devolve null (fallback para <pre>)", () => {
    expect(parsearFaq("1. Posso cancelar? Sim.")).toBeNull();
    expect(parsearGlossario("Termo: definição")).toBeNull();
  });
  it("glossario[] aceita termo/definicao", () => {
    expect(
      parsearGlossario('{"glossario":[{"termo":"Mora","definicao":"Atraso"}]}'),
    ).toEqual([{ termo: "Mora", definicao: "Atraso" }]);
  });
  it("normalizarConteudo preserva HITL e assume rascunho por padrão", () => {
    const r = normalizarConteudo({ conteudo: "x", log_id: "log-1" });
    expect(r.is_rascunho).toBe(true);
    expect(r.log_id).toBe("log-1");
    expect(r.aviso).toMatch(/Rascunho/);
  });
});

describe("tela FAQ & Glossário (E1)", () => {
  it("mostra faixa âmbar com aviso_hitl e log_id", async () => {
    postMock.mockResolvedValueOnce({
      data: {
        conteudo: '{"faq":[{"pergunta":"P?","resposta":"R."}]}',
        is_rascunho: true,
        aviso: "Rascunho gerado por IA — revisar antes de publicar.",
        aviso_hitl: "Rascunho gerado por IA — revisar antes de publicar.",
        log_id: "log-abc",
      },
    });
    render(<ConteudoJuridico />);
    fireEvent.click(screen.getByRole("button", { name: /Gerar FAQ/ }));
    const faixa = await screen.findByRole("status");
    expect(faixa).toHaveTextContent(/revisão humana obrigatória/i);
    expect(faixa).toHaveTextContent("log-abc");
    expect(screen.getByText("P?")).toBeTruthy();
    expect(postMock).toHaveBeenCalledWith("/conteudo/faq", {
      area: "consumidor",
      quantidade: 6,
    });
  });

  it("erro da IA vira mensagem leiga, sem detail técnico", async () => {
    postMock.mockRejectedValueOnce(
      Object.assign(new Error("x"), {
        response: {
          status: 503,
          data: { detail: "Todos os provedores falharam para task=faq" },
        },
      }),
    );
    render(<ConteudoJuridico />);
    fireEvent.click(screen.getByRole("button", { name: /Gerar glossário/ }));
    const alerta = await screen.findByRole("alert");
    expect(alerta).not.toHaveTextContent(/provedores falharam/);
    expect(alerta).toHaveTextContent(/inteligência artificial não está disponível/i);
  });

  it("select de área vem da taxonomia gerada com rótulos pt-BR", () => {
    render(<ConteudoJuridico />);
    const select = screen.getByLabelText("Área do direito") as HTMLSelectElement;
    const rotulos = Array.from(select.options).map((o) => o.textContent);
    expect(rotulos.slice(0, 2)).toEqual(["Consumidor", "Cível"]);
    expect(rotulos).toContain("Licitações");
  });
});
