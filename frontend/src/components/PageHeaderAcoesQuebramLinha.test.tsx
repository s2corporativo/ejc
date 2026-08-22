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

  it("quebra linha em telas estreitas e não encolhe em telas largas", () => {
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

    // `shrink-0` SEM prefixo de breakpoint anula o `flex-wrap` em toda largura:
    // o container prende-se a max-content e transborda em vez de quebrar —
    // 116px em /prazos, /agenda, /tarefas e /intimacoes no tablet.
    const tokens = classes.split(/\s+/);
    expect(
      tokens,
      "`shrink-0` incondicional volta a esconder o botão primário em telas estreitas",
    ).not.toContain("shrink-0");

    // Mas remover a trava em TODA largura também custa: sem ela o subtítulo
    // disputa a linha e as ações quebram em duas mesmo a 1440px, onde antes
    // cabiam numa só. Medido: /agenda, /prazos, /tarefas e /intimacoes iam de
    // 647×34 para 540×75 no desktop. `lg:shrink-0` preserva o layout original
    // de 1024px para cima — conferido por medição em cinco larguras.
    expect(
      tokens,
      "sem `lg:shrink-0` as ações quebram linha em telas largas, onde há espaço",
    ).toContain("lg:shrink-0");
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
