// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import {
  AIFactualityLegend,
  HumanValidationStatus,
  RiskBadge,
  SourceCitation,
  StatusBadge,
} from "./UI";

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

describe("HumanValidationStatus", () => {
  it("rotula o estado do ciclo de validação", () => {
    render(<HumanValidationStatus value="parcialmente_validado" />);
    expect(screen.getByText("Parcialmente validado")).toBeTruthy();
  });

  it("assume 'Não revisado' quando ausente", () => {
    render(<HumanValidationStatus value={null} />);
    expect(screen.getByText("Não revisado")).toBeTruthy();
  });
});

describe("AIFactualityLegend", () => {
  it("separa fato documental, inferência e lacuna", () => {
    render(<AIFactualityLegend />);
    expect(screen.getByText("Consta nos documentos")).toBeTruthy();
    expect(screen.getByText("Inferência da IA")).toBeTruthy();
    expect(screen.getByText("Não confirmado / lacuna")).toBeTruthy();
  });
});

describe("SourceCitation", () => {
  it("renderiza link quando há href", () => {
    render(
      <SourceCitation
        tipo="Precedente"
        titulo="STJ REsp 1.657.156"
        href="https://example.test/acordao"
      />,
    );
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("https://example.test/acordao");
  });
});
