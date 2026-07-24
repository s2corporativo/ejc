import api from "./api";

import type {
  ModoProducao,
  PecaModosMetaResponse,
  PrepararModoPecaRequest,
  PrepararModoPecaResponse,
} from "../types/pecaWorkflow";

const MODOS_VALIDOS: ModoProducao[] = ["livre", "guiado", "molde", "agente"];
const ENDPOINT_REDACAO_CANONICO = "/api/pecas/gerar";

function validarMeta(data: unknown): PecaModosMetaResponse {
  if (!data || typeof data !== "object") {
    throw new Error("Catálogo dos modos de produção inválido.");
  }

  const meta = data as Partial<PecaModosMetaResponse>;
  if (meta.hitl_obrigatorio !== true) {
    throw new Error("O backend não confirmou a revisão humana obrigatória.");
  }
  if (meta.endpoint_redacao !== ENDPOINT_REDACAO_CANONICO) {
    throw new Error("Endpoint de redação divergente do pipeline canônico.");
  }
  if (!Array.isArray(meta.modos)) {
    throw new Error("Lista de modos ausente no catálogo.");
  }

  const recebidos = new Set(meta.modos.map((modo) => modo?.value));
  if (
    meta.modos.length !== MODOS_VALIDOS.length ||
    MODOS_VALIDOS.some((modo) => !recebidos.has(modo))
  ) {
    throw new Error("O catálogo não contém os quatro modos controlados.");
  }

  const agente = meta.modos.find((modo) => modo.value === "agente");
  if (agente?.exige_caso !== true || agente.exige_aprovacao !== true) {
    throw new Error("O Modo Agente não confirmou seus bloqueios obrigatórios.");
  }

  if (
    !Array.isArray(meta.tipos) ||
    !meta.tipos.length ||
    !Array.isArray(meta.areas) ||
    !meta.areas.length
  ) {
    throw new Error("Tipos ou áreas ausentes no catálogo dos modos.");
  }

  return meta as PecaModosMetaResponse;
}

function validarPreparacao(data: unknown): PrepararModoPecaResponse {
  if (!data || typeof data !== "object") {
    throw new Error("Resposta de preparação do modo inválida.");
  }

  const resultado = data as Partial<PrepararModoPecaResponse>;
  if (!resultado.modo || !MODOS_VALIDOS.includes(resultado.modo)) {
    throw new Error("Modo inválido na resposta de preparação.");
  }
  if (
    typeof resultado.pronto_para_redacao !== "boolean" ||
    typeof resultado.exige_aprovacao !== "boolean" ||
    typeof resultado.tipo_peca !== "string" ||
    typeof resultado.area_direito !== "string" ||
    typeof resultado.instrucoes_pipeline !== "string"
  ) {
    throw new Error("Contrato incompleto na resposta de preparação.");
  }

  const listas = [
    resultado.bloqueios,
    resultado.alertas,
    resultado.documentos_considerados,
    resultado.etapas,
    resultado.checklist_revisao,
  ];
  if (listas.some((lista) => !Array.isArray(lista))) {
    throw new Error("Listas obrigatórias ausentes na preparação do modo.");
  }

  if (resultado.pronto_para_redacao && resultado.bloqueios!.length > 0) {
    throw new Error("Preparação contraditória: modo pronto com bloqueios ativos.");
  }
  if (
    resultado.modo === "agente" &&
    (resultado.exige_aprovacao !== true ||
      (resultado.pronto_para_redacao && !resultado.case_id))
  ) {
    throw new Error("O Modo Agente não confirmou caso e aprovação obrigatórios.");
  }

  return resultado as PrepararModoPecaResponse;
}

export async function obterPecaModosMeta(): Promise<PecaModosMetaResponse> {
  const { data } = await api.get<unknown>("/pecas/modos/meta");
  return validarMeta(data);
}

export async function prepararModoPeca(
  payload: PrepararModoPecaRequest,
): Promise<PrepararModoPecaResponse> {
  const { data } = await api.post<unknown>("/pecas/modos/preparar", payload);
  return validarPreparacao(data);
}

export { ENDPOINT_REDACAO_CANONICO };
