import api from "./api";

export type ThesisSide = "ataque" | "defesa" | "ambos";

export interface NationalThesis {
  id: string;
  chave_canonica: string;
  titulo: string;
  area: string;
  subarea?: string | null;
  instituto?: string | null;
  tema?: string | null;
  subtema?: string | null;
  situacao_fatica?: string | null;
  tipo: string;
  lado: ThesisSide;
  parte_favorecida?: string | null;
  procedimento?: string | null;
  instancia?: string | null;
  tese_principal: string;
  fundamento_resumido?: string | null;
  argumento_juridico?: string | null;
  raciocinio_juridico?: string | null;
  pressupostos: unknown[];
  fatos_necessarios: unknown[];
  elementos_demonstrar: unknown[];
  fatos_impeditivos: unknown[];
  excecoes: unknown[];
  fundamentacao_legal: unknown[];
  estrategia: Record<string, unknown>;
  provas_necessarias: unknown[];
  documentos_necessarios: unknown[];
  argumento_adversario?: string | null;
  resposta_adversaria?: string | null;
  riscos: unknown[];
  score_forca: number;
  status: string;
  versao: number;
  vigente: boolean;
  recomendavel: boolean;
  origem: string;
  criada_em?: string | null;
  revisada_em?: string | null;
}

export interface NationalThesisList {
  total: number;
  limit: number;
  offset: number;
  items: NationalThesis[];
}

export interface NationalThesisQuery {
  busca?: string;
  area?: string;
  lado?: ThesisSide;
  limit?: number;
  offset?: number;
}

export async function listarTesesNacionais(
  params: NationalThesisQuery,
): Promise<NationalThesisList> {
  const { data } = await api.get<NationalThesisList>(
    "/banco-nacional-teses",
    { params },
  );
  return data;
}

export async function obterTeseNacional(
  thesisId: string,
): Promise<NationalThesis> {
  const { data } = await api.get<NationalThesis>(
    `/banco-nacional-teses/${thesisId}`,
  );
  return data;
}
