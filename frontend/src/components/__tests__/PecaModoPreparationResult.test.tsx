import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PecaModoPreparationResult from "../PecaModoPreparationResult";
import type { PrepararModoPecaResponse } from "../../types/pecaWorkflow";

function resultado(
  parcial: Partial<PrepararModoPecaResponse> = {},
): PrepararModoPecaResponse {
  return {
    modo: "livre",
    case_id: "caso-1",
    tipo_peca: "contestacao",
    area_direito: "civil",
    pronto_para_redacao: true,
    exige_aprovacao: false,
    bloqueios: [],
    alertas: [],
    documentos_considerados: [],
    molde: null,
    campos_estruturados: {},
    etapas: [],
    instrucoes_pipeline: "INSTRUÇÃO INTERNA QUE NÃO DEVE SER EXIBIDA",
    checklist_revisao: [],
    ...parcial,
  };
}

describe("PecaModoPreparationResult", () => {
  it("exibe bloqueios retornados pelo backend", () => {
    render(
      <PecaModoPreparationResult
        resultado={resultado({
          pronto_para_redacao: false,
          bloqueios: ["Aprovar estrutura e teses antes da redação."],
        })}
      />,
    );

    expect(screen.getByText("Redação bloqueada")).toBeTruthy();
    expect(
      screen.getByText("Aprovar estrutura e teses antes da redação."),
    ).toBeTruthy();
  });

  it("confirma preparação sem sugerir aprovação automática da peça", () => {
    render(<PecaModoPreparationResult resultado={resultado()} />);

    expect(screen.getByText("Modo preparado")).toBeTruthy();
    expect(screen.getByText(/revisão humana antes de qualquer uso/i)).toBeTruthy();
    expect(
      screen.queryByText("INSTRUÇÃO INTERNA QUE NÃO DEVE SER EXIBIDA"),
    ).toBeNull();
  });

  it("exibe alertas, plano do Agente e aprovação obrigatória", () => {
    render(
      <PecaModoPreparationResult
        resultado={resultado({
          modo: "agente",
          exige_aprovacao: true,
          alertas: ["Confirmar a prova documental."],
          documentos_considerados: [{ documento_id: "doc-1" }],
          etapas: [
            {
              ordem: 1,
              codigo: "documentos",
              titulo: "Documentos considerados",
              objetivo: "Fixar o corpus autorizado.",
              exige_aprovacao: false,
            },
            {
              ordem: 9,
              codigo: "aprovacao",
              titulo: "Aprovação do advogado",
              objetivo: "Aprovar estrutura e teses.",
              exige_aprovacao: true,
            },
          ],
        })}
      />,
    );

    expect(screen.getByText("Pontos de atenção")).toBeTruthy();
    expect(screen.getByText("Confirmar a prova documental.")).toBeTruthy();
    expect(screen.getByText("Plano do Agente")).toBeTruthy();
    expect(screen.getByText("Aprovação do advogado")).toBeTruthy();
    expect(screen.getByText("Aprovação obrigatória")).toBeTruthy();
    expect(screen.getByText("1 documento(s)")).toBeTruthy();
  });

  it("exibe checklist sem marcá-lo automaticamente como concluído", () => {
    render(
      <PecaModoPreparationResult
        resultado={resultado({
          checklist_revisao: [
            "Confirmar nomes e números do processo.",
            "Eliminar resíduos do caso anterior.",
          ],
        })}
      />,
    );

    expect(screen.getByText("Checklist obrigatório de revisão")).toBeTruthy();
    expect(
      screen.getByText("Confirmar nomes e números do processo."),
    ).toBeTruthy();
    expect(screen.getByText("Eliminar resíduos do caso anterior.")).toBeTruthy();
  });
});
