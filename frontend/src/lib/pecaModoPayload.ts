import type {
  ConfiguracaoMoldePeca,
  ModoProducao,
  PrepararModoPecaRequest,
  ReferenciaDocumentoPeca,
} from "../types/pecaWorkflow";

interface MontarPreparacaoModoInput {
  modo: ModoProducao;
  caseId?: string | null;
  tipoPeca: string;
  areaDireito: string;
  instrucaoLivre?: string;
  respostasGuiadas?: Record<string, unknown>;
  documentosConsiderados?: ReferenciaDocumentoPeca[];
  molde?: ConfiguracaoMoldePeca | null;
  aprovadoParaRedacao?: boolean;
}

function textoOuNulo(valor?: string): string | null {
  const limpo = valor?.trim();
  return limpo || null;
}

export function montarPreparacaoModo({
  modo,
  caseId,
  tipoPeca,
  areaDireito,
  instrucaoLivre,
  respostasGuiadas = {},
  documentosConsiderados = [],
  molde = null,
  aprovadoParaRedacao = false,
}: MontarPreparacaoModoInput): PrepararModoPecaRequest {
  const base: PrepararModoPecaRequest = {
    modo,
    case_id: textoOuNulo(caseId ?? undefined),
    tipo_peca: tipoPeca,
    area_direito: areaDireito,
  };

  if (modo === "livre") {
    return {
      ...base,
      instrucao_livre: textoOuNulo(instrucaoLivre),
    };
  }

  if (modo === "guiado") {
    return {
      ...base,
      respostas_guiadas: respostasGuiadas,
    };
  }

  if (modo === "molde") {
    return {
      ...base,
      molde,
    };
  }

  return {
    ...base,
    documentos_considerados: documentosConsiderados,
    aprovado_para_redacao: aprovadoParaRedacao,
  };
}
