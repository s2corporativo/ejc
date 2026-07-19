import { describe, expect, it } from "vitest";
import {
  caseIdCriadoDaResposta,
  caseIdSeguro,
  casoContextualDaUrl,
  destinoRotaConsolidada,
  deveInjetarCaso,
} from "../FlowEnhancements";

describe("FlowEnhancements — regras puras", () => {
  it("aceita identificadores seguros e recusa valores que poderiam contaminar rota", () => {
    expect(caseIdSeguro("550e8400-e29b-41d4-a716-446655440000")).toBe(
      "550e8400-e29b-41d4-a716-446655440000",
    );
    expect(caseIdSeguro("12345")).toBe("12345");
    expect(caseIdSeguro("../../segredo")).toBeNull();
    expect(caseIdSeguro("id?token=abc")).toBeNull();
    expect(caseIdSeguro(" ")).toBeNull();
  });

  it("registra criação de caso em URLs relativas, legadas e versionadas", () => {
    for (const url of ["/cases/", "/api/cases/", "/api/v1/cases/"]) {
      expect(
        caseIdCriadoDaResposta({
          config: { method: "post", url } as never,
          data: { id: "case-1" },
        }),
      ).toBe("case-1");
    }
    expect(
      caseIdCriadoDaResposta({
        config: { method: "get", url: "/cases/" } as never,
        data: { id: "case-1" },
      }),
    ).toBeNull();
  });

  it("lê o caso contextual da URL sem aceitar valores inválidos", () => {
    expect(casoContextualDaUrl("?caso=case-1")).toBe("case-1");
    expect(casoContextualDaUrl("?caso=../../x")).toBeNull();
    expect(casoContextualDaUrl("?tab=atividades")).toBeNull();
  });

  it("injeta caso apenas em criações contextuais e nunca sobrescreve vínculo explícito", () => {
    expect(
      deveInjetarCaso(
        { method: "post", url: "/api/v1/deadlines/", data: { titulo: "Prazo" } } as never,
        "?caso=case-1",
      ),
    ).toBe("case-1");
    expect(
      deveInjetarCaso(
        {
          method: "post",
          url: "/tasks/",
          data: { titulo: "Tarefa", case_id: "case-2" },
        } as never,
        "?caso=case-1",
      ),
    ).toBeNull();
    expect(
      deveInjetarCaso(
        { method: "patch", url: "/deadlines/", data: { titulo: "Prazo" } } as never,
        "?caso=case-1",
      ),
    ).toBeNull();
  });

  it("consolida a rota histórica de conhecimento na aba canônica", () => {
    expect(destinoRotaConsolidada("/knowledge-hub")).toBe(
      "/inteligencia?tab=conhecimento",
    );
    expect(destinoRotaConsolidada("/inteligencia")).toBeNull();
  });
});
