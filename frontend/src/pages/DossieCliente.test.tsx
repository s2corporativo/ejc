// @vitest-environment jsdom
// Degradação por seção na Ficha Mestra do cliente (Onda 1 da refatoração).
//
// O backend deixou de responder 500 quando UMA agregação do dossiê falha: ele
// devolve 200, a seção vem vazia e o nome dela entra em `secoes_indisponiveis`.
// Sem o aviso abaixo, o advogado leria "0 prazos" como "não há prazo" — a falha
// silenciosa que o padrão de erro do EJC proíbe. Estes testes travam o aviso.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { AvisoSecoesIndisponiveis } from "./DossieCliente";

afterEach(cleanup);

describe("AvisoSecoesIndisponiveis", () => {
  it("não renderiza nada quando todas as seções carregaram", () => {
    const { container } = render(
      <AvisoSecoesIndisponiveis secoes={[]} onRecarregar={() => {}} />,
    );
    expect(container.innerHTML).toBe("");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("nomeia a seção que faltou, em português, no singular", () => {
    render(
      <AvisoSecoesIndisponiveis secoes={["prazos"]} onRecarregar={() => {}} />,
    );
    const aviso = screen.getByRole("status");
    expect(aviso.textContent).toContain("prazos não pôde ser carregada");
    // Diz que o resto é confiável — é isso que permite seguir usando a tela.
    expect(aviso.textContent).toContain(
      "demais dados desta tela estão completos",
    );
  });

  it("traduz a chave técnica da seção para o vocabulário do usuário", () => {
    render(
      <AvisoSecoesIndisponiveis
        secoes={["honorarios"]}
        onRecarregar={() => {}}
      />,
    );
    expect(screen.getByRole("status").textContent).toContain("financeiro");
  });

  it("lista várias seções no plural, com 'e' antes da última", () => {
    render(
      <AvisoSecoesIndisponiveis
        secoes={["prazos", "documentos", "honorarios"]}
        onRecarregar={() => {}}
      />,
    );
    const texto = screen.getByRole("status").textContent ?? "";
    expect(texto).toContain("prazos, documentos e financeiro");
    expect(texto).toContain("puderam ser carregadas");
  });

  it("mantém legível uma seção desconhecida vinda do backend", () => {
    render(
      <AvisoSecoesIndisponiveis
        secoes={["secao_nova"]}
        onRecarregar={() => {}}
      />,
    );
    expect(screen.getByRole("status").textContent).toContain("secao_nova");
  });

  it("oferece nova tentativa sem exigir recarregar a página", () => {
    const onRecarregar = vi.fn();
    render(
      <AvisoSecoesIndisponiveis
        secoes={["casos"]}
        onRecarregar={onRecarregar}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /tentar novamente/i }));
    expect(onRecarregar).toHaveBeenCalledTimes(1);
  });
});
