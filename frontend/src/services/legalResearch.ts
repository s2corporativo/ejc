import api from "../lib/api";

export type FontePesquisaJuridica = {
  chunk_id?: string | null;
  doc_id?: string | null;
  titulo?: string | null;
  categoria?: string | null;
  fonte?: string | null;
  tribunal?: string | null;
  confianca?: string | null;
  conteudo?: string | null;
  similarity?: number | null;
  score?: number | null;
  autoridade?: { code?: string; label?: string; official?: boolean } | null;
  citacao?: Record<string, unknown> | null;
};

export type PesquisaJuridicaResponse = {
  query: string;
  modo: string;
  pipeline: string;
  resultados: FontePesquisaJuridica[];
};

export async function pesquisarFontesJuridicas(
  query: string,
  limite = 10,
): Promise<PesquisaJuridicaResponse> {
  const { data } = await api.get<PesquisaJuridicaResponse>("/rag/buscar", {
    params: { q: query, limite },
  });
  return {
    query: data.query ?? query,
    modo: data.modo ?? "desconhecido",
    pipeline: data.pipeline ?? "governado",
    resultados: Array.isArray(data.resultados) ? data.resultados : [],
  };
}

export type CitacaoVerificada = {
  citacao: string;
  tipo: string;
  encontrada: boolean;
  fonte?: string | null;
  trecho?: string | null;
  status:
    | "verificada"
    | "identificada"
    | "suspeita"
    | "generica"
    | "possivelmente_desatualizada"
    | string;
  tribunal?: string | null;
  numero?: string | null;
  orgao?: string | null;
  relator?: string | null;
  data?: string | null;
  fonte_verificacao?: string | null;
  aviso?: string | null;
  vigencia_pendente?: boolean;
};

export type VerificacaoCitacoesResponse = {
  total: number;
  confirmadas: number;
  nao_encontradas: number;
  citacoes: CitacaoVerificada[];
  aviso: string;
  score: number | null;
  contagem_status?: Record<string, number>;
  avisos?: string[];
};

export async function verificarCitacoesJuridicas(
  texto: string,
  consultarDatajud: boolean,
): Promise<VerificacaoCitacoesResponse> {
  const { data } = await api.post<VerificacaoCitacoesResponse>(
    "/ai/citacoes/verificar",
    { texto, consultar_datajud: consultarDatajud },
  );
  return {
    ...data,
    citacoes: Array.isArray(data.citacoes) ? data.citacoes : [],
    avisos: Array.isArray(data.avisos) ? data.avisos : [],
  };
}
