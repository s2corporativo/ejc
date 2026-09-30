// @vitest-environment jsdom
// TelaEnvio — a marca do escritório aparece nas DUAS variantes da tela
// (a pílula compacta que o Dashboard embute e a linha de identidade da
// variante "full" em /entrada) e o gate de análise não regrediu.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

vi.mock("../../components/Toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import { officeBranding } from "../../config/officeBranding";
import { META_PADRAO } from "./types";
import { podeAnalisar, TelaInicial } from "./TelaEnvio";

function renderizar(variant: "full" | "pill", onAnalisar = () => {}) {
  return render(
    <TelaInicial
      texto=""
      onTexto={() => {}}
      arquivos={[]}
      onArquivos={() => {}}
      meta={META_PADRAO}
      onAnalisar={onAnalisar}
      variant={variant}
    />,
  );
}

beforeEach(() => {
  cleanup();
});

afterEach(() => {
  cleanup();
});

describe("TelaInicial — marca do escritório", () => {
  it("mostra a logomarca na pílula compacta (variante embute no Dashboard)", () => {
    renderizar("pill");

    const marca = document.querySelector(".ejc-entry-pill__spark");
    expect(marca).toBeTruthy();
    expect(marca?.getAttribute("src")).toBe(officeBranding.logoPath);
  });

  it("mostra a logomarca na linha de identidade da variante full", () => {
    renderizar("full");

    expect(screen.getByText("Relate o caso ou anexe os documentos")).toBeTruthy();
    const linha = document.querySelector(".ejc-entry-identity__mark");
    expect(linha?.getAttribute("src")).toBe(officeBranding.logoPath);
  });

  it("mantém o contrato de podeAnalisar (piso de 40 chars OU 1 arquivo)", () => {
    expect(podeAnalisar("curto demais", [])).toBe(false);
    expect(podeAnalisar("a".repeat(39), [])).toBe(false);
    expect(podeAnalisar("a".repeat(40), [])).toBe(true);
    expect(podeAnalisar("", [])).toBe(false);
    const arquivo = new File(["x"], "a.pdf", { type: "application/pdf" });
    expect(podeAnalisar("", [arquivo])).toBe(true);
  });
});
