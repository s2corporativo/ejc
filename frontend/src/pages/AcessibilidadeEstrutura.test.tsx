// @vitest-environment jsdom
// Regressão da auditoria funcional de 22/08/2026 (Issue #1237), rodada de
// acessibilidade — prioridade 16 do §71.
//
// Cinco achados medidos no navegador, todos com endereço:
//
//   /            0 <h1>            — a página inicial não tinha título nenhum
//   /documentos  2 <h1> idênticos  — "Documentos" duas vezes
//   /casos       salto h1 -> h3    — "Casos por área do Direito"
//   /documentos  salto h1 -> h3    — "Documentos por tipo"
//   /casos       select sem rótulo — filtro de área do Direito
//
// jsdom não tem motor de layout, então o alvo de toque (WCAG 2.5.8) não cabe
// aqui — aquele foi medido no Chromium (48 botões autônomos abaixo de 24px
// passaram a 0). O que estes testes travam é a ESTRUTURA, que é o que cega o
// leitor de tela: um h1 por página e nenhum salto de nível.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { MemoryRouter } from "react-router";

vi.mock("../lib/api", () => ({
  default: { get: vi.fn().mockResolvedValue({ data: { data: [], total: 0 } }) },
}));
vi.mock("../components/Toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import { PageHeader } from "../components/UI";

describe("estrutura de cabeçalhos — um h1 por página", () => {
  afterEach(cleanup);

  it("PageHeader é a fonte do h1 da página", () => {
    const { container } = render(<PageHeader title="Casos e Processos" />);
    const h1s = container.querySelectorAll("h1");
    expect(h1s).toHaveLength(1);
    expect(h1s[0].textContent).toBe("Casos e Processos");
  });

  it("Documentos NÃO renderiza PageHeader — quem o monta é GestaoDocumental", () => {
    // `Documentos` nunca é rota: `moduleRegistry` aponta /documentos para
    // `GestaoDocumental`, que monta o PageHeader e embute `<Documentos />` na
    // aba. Os dois com PageHeader davam DOIS <h1> "Documentos" na mesma tela.
    //
    // Lido do disco de propósito: a primeira versão deste teste usava
    // `import("./Documentos?raw").catch(() => null)` com retorno antecipado —
    // num ambiente sem `?raw` ele passaria SEM verificar nada. Teste que pode
    // passar por construção não é cobertura.
    const aqui = dirname(fileURLToPath(import.meta.url));
    const fonte = readFileSync(join(aqui, "Documentos.tsx"), "utf-8");
    expect(fonte).not.toMatch(/<PageHeader/);
    // e o de GestaoDocumental precisa continuar lá
    const container = readFileSync(join(aqui, "GestaoDocumental.tsx"), "utf-8");
    expect(container).toMatch(/<PageHeader/);
  });
});

describe("VisualLawDocument — cabeçalho de documento é seção, não página", () => {
  afterEach(cleanup);

  it("usa h2, para não competir com o h1 da página", async () => {
    const { VisualLawDocument } = await import("../components/UI");
    const { container } = render(
      <MemoryRouter>
        <VisualLawDocument title="Petição inicial" />
      </MemoryRouter>,
    );
    expect(container.querySelector("h1")).toBeNull();
    expect(container.querySelector("h2")?.textContent).toBe("Petição inicial");
  });
});
