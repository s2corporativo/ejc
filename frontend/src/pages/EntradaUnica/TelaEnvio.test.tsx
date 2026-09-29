// @vitest-environment jsdom
// TelaEnvio — a identidade do assistente aparece nas DUAS variantes da Tela A:
//   • "pill"  → marca compacta dentro da pílula branca do herói do Dashboard
//                (que é o que `EntradaInteligente embedded` renderiza);
//   • "full"  → linha de identidade acima do campo de relato na tela /entrada.
// Nos dois casos a marca vem de `officeBranding.logoPath` e nunca ocupa mais
// espaço que o glifo que substituía, para a composição não pular.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { officeBranding } from "../../config/officeBranding";
import { TelaInicial, podeAnalisar, MINIMO_RELATO } from "./TelaEnvio";
import type { EntradaMeta } from "./types";

const META: EntradaMeta = {
  maxArquivos: 10,
  maxLoteMb: 50,
  formatos: ["pdf", "docx"],
};

function renderizar(variant: "pill" | "full") {
  return render(
    <TelaInicial
      texto=""
      onTexto={() => {}}
      arquivos={[]}
      onArquivos={() => {}}
      meta={META}
      onAnalisar={() => {}}
      variant={variant}
    />,
  );
}

afterEach(() => cleanup());

describe("TelaInicial — identidade do assistente nas duas variantes", () => {
  it("põe a logomarca dentro da pílula do herói (variant=pill)", () => {
    renderizar("pill");

    const marca = screen.getByRole("img");
    expect(marca.tagName).toBe("IMG");
    expect(marca.getAttribute("src")).toBe(officeBranding.logoPath);
    expect(marca.className).toContain("ejc-entry-pill__spark");
    // A pílula continua sendo a pílula: o mesmo campo de relato e os mesmos
    // dois botões, só a identidade visual mudou.
    expect(screen.getByLabelText("Relato do cliente")).toBeTruthy();
    expect(screen.getByLabelText("Anexar documentos")).toBeTruthy();
    expect(screen.getByLabelText("Analisar relato e documentos")).toBeTruthy();
  });

  it("põe a mesma logomarca na tela cheia (variant=full)", () => {
    renderizar("full");

    const marca = screen.getByRole("img");
    expect(marca.getAttribute("src")).toBe(officeBranding.logoPath);
    expect(screen.getByText("EJC · Inteligência Jurídica")).toBeTruthy();
    expect(screen.getByLabelText("Relato do cliente")).toBeTruthy();
    expect(
      screen.getByLabelText(/Arraste documentos aqui ou clique/),
    ).toBeTruthy();
  });

  it("preserva o contrato de validação da análise", () => {
    // Regressão: mexer no cabeçalho da Tela A não pode afrouxar a validação.
    expect(podeAnalisar("curto", [])).toBe(false);
    expect(podeAnalisar("x".repeat(MINIMO_RELATO), [])).toBe(true);
    expect(podeAnalisar("", [new File([], "a.pdf")])).toBe(true);
  });
});
