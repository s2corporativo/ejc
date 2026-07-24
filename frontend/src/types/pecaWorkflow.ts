export type ModoProducao = "livre" | "guiado" | "molde" | "agente";

export interface PecaModoMeta {
  value: ModoProducao;
  label: string;
  descricao: string;
  exige_caso: boolean;
  exige_aprovacao: boolean;
}

export interface PecaTipoModoMeta {
  value: string;
  label: string;
  grupo: string;
  campos_guiados: string[];
}

export interface PecaAreaModoMeta {
  value: string;
  label: string;
}

export interface PecaModosMetaResponse {
  modos: PecaModoMeta[];
  tipos: PecaTipoModoMeta[];
  areas: PecaAreaModoMeta[];
  limites: {
    documentos_considerados: number;
  };
  hitl_obrigatorio: boolean;
  endpoint_redacao: string;
}

export interface ReferenciaDocumentoPeca {
  documento_id: string;
  versao?: number | null;
  hash_conteudo?: string | null;
  nome?: string | null;
}

export interface ConfiguracaoMoldePeca {
  referencia: ReferenciaDocumentoPeca;
  preservar: string[];
  substituir: string[];
}

export interface PrepararModoPecaRequest {
  modo: ModoProducao;
  case_id?: string | null;
  tipo_peca: string;
  area_direito: string;
  instrucao_livre?: string | null;
  respostas_guiadas?: Record<string, unknown>;
  documentos_considerados?: ReferenciaDocumentoPeca[];
  molde?: ConfiguracaoMoldePeca | null;
  aprovado_para_redacao?: boolean;
}

export interface EtapaPlanoAgentePeca {
  ordem: number;
  codigo: string;
  titulo: string;
  objetivo: string;
  exige_aprovacao: boolean;
}

export interface PrepararModoPecaResponse {
  modo: ModoProducao;
  case_id: string | null;
  tipo_peca: string;
  area_direito: string;
  pronto_para_redacao: boolean;
  exige_aprovacao: boolean;
  bloqueios: string[];
  alertas: string[];
  documentos_considerados: ReferenciaDocumentoPeca[];
  molde: ConfiguracaoMoldePeca | null;
  campos_estruturados: Record<string, unknown>;
  etapas: EtapaPlanoAgentePeca[];
  instrucoes_pipeline: string;
  checklist_revisao: string[];
}
