// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { RiskBadge, StatusBadge } from "./UI";

afterEach(cleanup);

describe("StatusBadge", () => {
  it("mapeia o vocabulário canônico com rótulo padronizado", () => {
    render(<StatusBadge value="em_revisao" />);
    expect(screen.getByText("Em revisão")).toBeTruthy();
  });

  it("normaliza acento, caixa e separadores para a mesma entrada", () => {
    render(<StatusBadge value="Aguardando Documento" />);
    expect(screen.getByText("Aguardando documento")).toBeTruthy();
  });

  it("trata sinônimo legado (triagem → Em análise)", () => {
    render(<StatusBadge value="triagem" />);
    expect(screen.getByText("Em análise")).toBeTruthy();
  });

  it("preserva status legado fora do vocabulário canônico", () => {
    render(<StatusBadge value="ativo" />);
    expect(screen.getByText("ativo")).toBeTruthy();
  });

  it("mostra 'sem status' quando vazio", () => {
    render(<StatusBadge value={null} />);
    expect(screen.getByText("sem status")).toBeTruthy();
  });
});

describe("RiskBadge", () => {
  it("rotula grau de risco conhecido", () => {
    render(<RiskBadge value="medio" />);
    expect(screen.getByText("Risco médio")).toBeTruthy();
  });

  it("faz fallback para grau desconhecido sem quebrar", () => {
    render(<RiskBadge value="altíssimo" />);
    expect(screen.getByText(/Risco/)).toBeTruthy();
  });
});
