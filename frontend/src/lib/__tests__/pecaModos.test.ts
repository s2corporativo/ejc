import { beforeEach, describe, expect, it, vi } from "vitest";

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock("../api", () => ({
  default: { get, post },
}));

import {
  ENDPOINT_REDACAO_CANONICO,
  obterPecaModosMeta,
  prepararModoPeca,
} from "../pecaModos";

const metaValida = {
  modos: [
    {
      value: "livre",
      label: "Livre",
      descricao: "Instrução direta.",
      exige_caso: false,
      exige_aprovacao: false,
    },
    {
      value: "guiado",
      label: "Guiado",
      descricao: "Formulário estruturado.",
      exige_caso: false,
      exige_aprovacao: false,
    },
    {
      value: "molde",
      label: "Molde",
      descricao: "Estrutura versionada.",
      exige_caso: false,
      exige_aprovacao: false,
    },
    {
      value: "agente",
      label: "Agente",
      descricao: "Plano com aprovação.",
      exige_caso: true,
      exige_aprovacao: true,
    },
  ],
  tipos: [
    {
      value: "contestacao",
      label: "Contestação",
      grupo: "defesas",
      campos_guiados: ["fatos_impugnados", "pedidos"],
    },
  ],
  areas: [{ value: "civil", label: "Civil" }],
  limites: { documentos_considerados: 100 },
  hitl_obrigatorio: true,
  endpoint_redacao: "/api/pecas/gerar",
};

const preparacaoValida = {
  modo: "livre",
  case_id: null,
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
  instrucoes_pipeline: "Impugnar especificamente os fatos.",
  checklist_revisao: [],
};

describe("pecaModos", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  it("aceita o catálogo completo com HITL e endpoint canônico", async () => {
    get.mockResolvedValue({ data: metaValida });

    const meta = await obterPecaModosMeta();

    expect(get).toHaveBeenCalledWith("/pecas/modos/meta");
    expect(meta.modos.map((modo) => modo.value)).toEqual([
      "livre",
      "guiado",
      "molde",
      "agente",
    ]);
    expect(meta.tipos[0].campos_guiados).toEqual([
      "fatos_impugnados",
      "pedidos",
    ]);
    expect(ENDPOINT_REDACAO_CANONICO).toBe("/api/pecas/gerar");
  });

  it("recusa catálogo que não confirme revisão humana", async () => {
    get.mockResolvedValue({
      data: { ...metaValida, hitl_obrigatorio: false },
    });

    await expect(obterPecaModosMeta()).rejects.toThrow(
      "revisão humana obrigatória",
    );
  });

  it("recusa endpoint de redação divergente", async () => {
    get.mockResolvedValue({
      data: { ...metaValida, endpoint_redacao: "/api/pecas/gerar-v2" },
    });

    await expect(obterPecaModosMeta()).rejects.toThrow(
      "pipeline canônico",
    );
  });

  it("recusa catálogo incompleto", async () => {
    get.mockResolvedValue({
      data: { ...metaValida, modos: metaValida.modos.slice(0, 3) },
    });

    await expect(obterPecaModosMeta()).rejects.toThrow(
      "quatro modos controlados",
    );
  });

  it("recusa Agente sem caso e aprovação obrigatórios", async () => {
    get.mockResolvedValue({
      data: {
        ...metaValida,
        modos: metaValida.modos.map((modo) =>
          modo.value === "agente"
            ? { ...modo, exige_aprovacao: false }
            : modo,
        ),
      },
    });

    await expect(obterPecaModosMeta()).rejects.toThrow(
      "bloqueios obrigatórios",
    );
  });

  it("recusa catálogo sem tipos ou áreas utilizáveis", async () => {
    get.mockResolvedValue({ data: { ...metaValida, tipos: [] } });

    await expect(obterPecaModosMeta()).rejects.toThrow(
      "Tipos ou áreas ausentes",
    );
  });

  it("envia a preparação ao endpoint que não redige a peça", async () => {
    post.mockResolvedValue({ data: preparacaoValida });

    const resultado = await prepararModoPeca({
      modo: "livre",
      tipo_peca: "contestacao",
      area_direito: "civil",
      instrucao_livre: "Impugnar especificamente os fatos.",
    });

    expect(post).toHaveBeenCalledWith("/pecas/modos/preparar", {
      modo: "livre",
      tipo_peca: "contestacao",
      area_direito: "civil",
      instrucao_livre: "Impugnar especificamente os fatos.",
    });
    expect(resultado.pronto_para_redacao).toBe(true);
  });

  it("recusa preparação pronta com bloqueios ativos", async () => {
    post.mockResolvedValue({
      data: {
        ...preparacaoValida,
        bloqueios: ["Aprovação pendente."],
      },
    });

    await expect(
      prepararModoPeca({
        modo: "livre",
        tipo_peca: "contestacao",
        area_direito: "civil",
      }),
    ).rejects.toThrow("modo pronto com bloqueios ativos");
  });

  it("recusa Modo Agente pronto sem caso vinculado", async () => {
    post.mockResolvedValue({
      data: {
        ...preparacaoValida,
        modo: "agente",
        case_id: null,
        exige_aprovacao: true,
      },
    });

    await expect(
      prepararModoPeca({
        modo: "agente",
        tipo_peca: "contestacao",
        area_direito: "civil",
      }),
    ).rejects.toThrow("caso e aprovação obrigatórios");
  });

  it("recusa resposta sem listas obrigatórias", async () => {
    const { alertas: _alertas, ...incompleta } = preparacaoValida;
    post.mockResolvedValue({ data: incompleta });

    await expect(
      prepararModoPeca({
        modo: "livre",
        tipo_peca: "contestacao",
        area_direito: "civil",
      }),
    ).rejects.toThrow("Listas obrigatórias ausentes");
  });
});
