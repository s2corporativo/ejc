// @vitest-environment jsdom
// Regressão da auditoria funcional de 22/08/2026 (Issue #1237), rodada de
// responsividade. O container de ações do `PageHeader` tinha
// `flex shrink-0 flex-wrap`: as duas últimas classes se anulam, porque
// `shrink-0` prende o container à largura de max-content e ele TRANSBORDA em
// vez de quebrar a linha.
//
// Medido no Chromium, antes da correção:
//   /prazos  tablet  (820px)  -> 116px de transbordo horizontal
//   /casos   celular (390px)  ->  28px, cortando o botão primário
//                                 "Novo caso por documento" — inalcançável
//
// jsdom não tem motor de layout, então não dá para medir transbordo aqui. O que
// este teste protege é o contrato de classes que causou o defeito: a ausência de
// `shrink-0` e a presença de `flex-wrap` no container de ações.
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import { PageHeader } from "./UI";

function containerDeAcoes(html: HTMLElement): HTMLElement {
  const botao = html.querySelector("button");
  expect(botao, "o cabeçalho precisa renderizar as ações").toBeTruthy();
  return botao!.parentElement as HTMLElement;
}

describe("PageHeader — a linha de ações precisa poder quebrar", () => {
  afterEach(cleanup);

  it("o container de ações quebra linha e não fica preso a max-content", () => {
    const { container } = render(
      <PageHeader
        title="Casos e Processos"
        actions={
          <>
            <button>Cadastro manual</button>
            <button>Novo caso por documento</button>
          </>
        }
      />,
    );
    const classes = containerDeAcoes(container).className;
    expect(classes).toContain("flex-wrap");
    expect(
      classes,
      "`shrink-0` anula o `flex-wrap`: o container para de quebrar linha e " +
        "transborda, escondendo o botão primário em telas estreitas",
    ).not.toContain("shrink-0");
  });

  it("sem ações, nenhum container extra é renderizado", () => {
    const { container } = render(<PageHeader title="Sem ações" />);
    expect(container.querySelector("button")).toBeNull();
  });

  it("o título continua sendo o h1 da página", () => {
    const { container } = render(<PageHeader title="Casos e Processos" />);
    const h1 = container.querySelector("h1");
    expect(h1?.textContent).toBe("Casos e Processos");
  });
});
