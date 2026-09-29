// @vitest-environment jsdom
// Identidade visual do assistente da Entrada Única.
//
// O mockup aprovado pelo Titular desenhava uma ilustração de pássaro ("Sabiá")
// no slot do assistente; a decisão dele foi trocar esse slot pela marca do
// escritório. Estes testes travam as duas propriedades que sustentam essa
// decisão:
//   (a) a identidade vem SEMPRE de `officeBranding.logoPath`, com `alt`
//       descritivo (a auditoria de acessibilidade reprova `<img>` sem `alt`);
//   (b) se a imagem não carregar, o slot vira o monograma tipográfico "DT" —
//       a marca não pode quebrar o layout do herói.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { officeBranding } from "../../config/officeBranding";
import { IdentidadeAssistente } from "./IdentidadeAssistente";

afterEach(() => cleanup());

describe("IdentidadeAssistente — logomarca do escritório", () => {
  it("usa officeBranding.logoPath com alt descritivo, sem caminho hardcoded", () => {
    render(<IdentidadeAssistente variante="heroi" className="ejc-x" />);

    const img = screen.getByRole("img");
    expect(img.tagName).toBe("IMG");
    expect(img.getAttribute("src")).toBe(officeBranding.logoPath);
    // `alt` nunca vazio: descreve a marca, não é decoração silenciosa.
    expect(img.getAttribute("alt")).toBeTruthy();
    expect(img.getAttribute("alt")).toContain(officeBranding.officeName);
    // A classe de layout do chamador é preservada (a base é somada, não trocada).
    expect(img.className).toContain("ejc-assistente");
    expect(img.className).toContain("ejc-x");
    expect(img.getAttribute("data-variante")).toBe("heroi");
  });

  it("marca a variante pill sem mudar a origem do asset", () => {
    render(<IdentidadeAssistente variante="pill" />);

    const img = screen.getByRole("img");
    expect(img.getAttribute("src")).toBe(officeBranding.logoPath);
    expect(img.getAttribute("data-variante")).toBe("pill");
  });

  it("cai no monograma tipográfico DT quando a imagem falha", () => {
    render(<IdentidadeAssistente variante="heroi" className="ejc-x" />);

    const img = screen.getByRole("img");
    fireEvent.error(img);

    // O <img> some: sobrou o fallback, que continua sendo uma "imagem" para o
    // leitor de tela (mesmo rótulo) e ocupa o mesmo espaço no herói.
    const fallback = screen.getByRole("img");
    expect(fallback.tagName).toBe("SPAN");
    expect(fallback.textContent).toBe("DT");
    expect(fallback.getAttribute("aria-label")).toContain(
      officeBranding.officeName,
    );
    expect(fallback.className).toContain("ejc-assistente--fallback");
    expect(fallback.className).toContain("ejc-x");
    expect(document.querySelector("img")).toBeNull();
  });

  it("não tenta reverter o fallback se outro erro de imagem chegar", () => {
    render(<IdentidadeAssistente variante="pill" />);

    fireEvent.error(screen.getByRole("img"));
    const fallback = screen.getByRole("img");

    fireEvent.error(fallback);
    expect(screen.getByRole("img").textContent).toBe("DT");
  });
});
