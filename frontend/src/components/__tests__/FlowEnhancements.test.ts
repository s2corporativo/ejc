import { describe, expect, it } from "vitest";
import {
  canonicalizarSalaDeGuerraUrl,
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

  it("registra somente respostas de criação real de caso", () => {
    expect(
      caseIdCriadoDaResposta({
        config: { method: "post", url: "/cases/" } as never,
        data: { id: "case-1" },
      }),
    ).toBe("case-1");

    expect(
      caseIdCriadoDaResposta({
        config: { method: "post", url: "/api/v1/cases/" } as never,
        data: { id: "case-v1" },
      }),
    ).toBe("case-v1");

    expect(
      caseIdCriadoDaResposta({
        config: { method: "post", url: "/api/cases/" } as never,
        data: { id: "case-legacy" },
      }),
    ).toBe("case-legacy");

    expect(
      caseIdCriadoDaResposta({
        config: { method: "get", url: "/cases/" } as never,
        data: { id: "case-1" },
      }),
    ).toBeNull();

    expect(
      caseIdCriadoDaResposta({
        config: { method: "post", url: "/clients/" } as never,
        data: { id: "client-1" },
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
        {
          method: "post",
          url: "/deadlines/",
          data: { titulo: "Prazo" },
        } as never,
        "?caso=case-1",
      ),
    ).toBe("case-1");

    expect(
      deveInjetarCaso(
        {
          method: "post",
          url: "/api/v1/tasks/",
          data: { titulo: "Tarefa" },
        } as never,
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
        {
          method: "patch",
          url: "/deadlines/",
          data: { titulo: "Prazo" },
        } as never,
        "?caso=case-1",
      ),
    ).toBeNull();

    expect(
      deveInjetarCaso(
        { method: "post", url: "/financeiro/", data: { valor: 10 } } as never,
        "?caso=case-1",
      ),
    ).toBeNull();
  });

  it("migra apenas as operações contextuais da Sala de Guerra para o caso aberto", () => {
    const tela = "/casos/case-1/sala-de-guerra";
    expect(
      canonicalizarSalaDeGuerraUrl(
        "/sala-de-guerra-v3/war-room/simular",
        tela,
      ),
    ).toBe("/cases/case-1/sala-de-guerra/simular-contestacao");
    expect(
      canonicalizarSalaDeGuerraUrl(
        "/api/v1/sala-de-guerra-v3/visual-law/case-1",
        tela,
      ),
    ).toBe("/cases/case-1/sala-de-guerra/visual-law");
    expect(
      canonicalizarSalaDeGuerraUrl(
        "/sala-de-guerra-v3/visual-law/case-1/download",
        tela,
      ),
    ).toBe("/cases/case-1/sala-de-guerra/visual-law/download");
  });

  it("não reescreve Sentinela, outro caso ou chamada fora do workspace", () => {
    const tela = "/casos/case-1/sala-de-guerra";
    expect(
      canonicalizarSalaDeGuerraUrl(
        "/sala-de-guerra-v3/sentinela/auditoria",
        tela,
      ),
    ).toBe("/sala-de-guerra-v3/sentinela/auditoria");
    expect(
      canonicalizarSalaDeGuerraUrl(
        "/sala-de-guerra-v3/visual-law/case-2",
        tela,
      ),
    ).toBe("/sala-de-guerra-v3/visual-law/case-2");
    expect(
      canonicalizarSalaDeGuerraUrl(
        "/sala-de-guerra-v3/war-room/simular",
        "/inteligencia",
      ),
    ).toBe("/sala-de-guerra-v3/war-room/simular");
    expect(
      canonicalizarSalaDeGuerraUrl(
        "/sala-de-guerra-v3/war-room/simular",
        "/casos/../../segredo/sala-de-guerra",
      ),
    ).toBe("/sala-de-guerra-v3/war-room/simular");
  });

  it("consolida a rota histórica de conhecimento na aba canônica", () => {
    expect(destinoRotaConsolidada("/knowledge-hub")).toBe(
      "/inteligencia?tab=conhecimento",
    );
    expect(destinoRotaConsolidada("/inteligencia")).toBeNull();
    expect(destinoRotaConsolidada("/conhecimento")).toBeNull();
  });
});
