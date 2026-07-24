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
  if (!Array.isArray(meta.tipos) || !Array.isArray(meta.areas)) {
    throw new Error("Tipos ou áreas ausentes no catálogo dos modos.");
  }

  return meta as PecaModosMetaResponse;
}

export async function obterPecaModosMeta(): Promise<PecaModosMetaResponse> {
  const { data } = await api.get<unknown>("/pecas/modos/meta");
  return validarMeta(data);
}

export async function prepararModoPeca(
  payload: PrepararModoPecaRequest,
): Promise<PrepararModoPecaResponse> {
  const { data } = await api.post<PrepararModoPecaResponse>(
    "/pecas/modos/preparar",
    payload,
  );
  return data;
}

export { ENDPOINT_REDACAO_CANONICO };
