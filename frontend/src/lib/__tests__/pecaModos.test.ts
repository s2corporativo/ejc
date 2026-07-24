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
  tipos: [],
  areas: [],
  limites: { documentos_considerados: 100 },
  hitl_obrigatorio: true,
  endpoint_redacao: "/api/pecas/gerar",
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

  it("envia a preparação ao endpoint que não redige a peça", async () => {
    const resposta = {
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
    post.mockResolvedValue({ data: resposta });

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
});
