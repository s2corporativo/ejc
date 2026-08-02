// Tipos e normalização defensiva da Entrada Única (/entrada).
//
// O contrato de POST /entrada/analisar está em docs/DESENHO_BLOCO3_TELAS.md
// (seção 4). O backend é implementado em paralelo e pode divergir em detalhe:
// NENHUM campo ausente/nulo pode quebrar a tela — tudo aqui degrada para
// string vazia / null / lista vazia e a confirmação segue editável.

export interface DocumentoProposto {
  documentId: string;
  nome: string;
  classificacao: string | null;
  confianca: number | null; // 0-100
  /** false = removido pelo advogado (sai de documentos_ids; nada é deletado). */
  selecionado: boolean;
}

export interface PrazoProposto {
  descricao: string;
  /** yyyy-mm-dd quando o backend mandar ISO; texto livre caso contrário. */
  data: string;
  origem: string | null;
  requerConfirmacao: boolean;
  criar: boolean;
  responsavelId: string;
}

export interface DuplicadoCliente {
  clientId: string | null;
  rotulo: string;
}

export interface Proposta {
  rascunhoId: string;
  clienteId: string | null;
  clienteNome: string;
  clienteOrigem: string | null;
  clienteJaCadastrada: boolean;
  clienteCasosAnteriores: number | null;
  clienteConfianca: number | null;
  area: string;
  areaConfianca: number | null;
  titulo: string;
  fatos: string;
  parteContraria: string;
  documentos: DocumentoProposto[];
  prazo: PrazoProposto | null;
  proximaAcao: string;
  advogadoResponsavelId: string;
  conflitoAlertas: string[];
  duplicados: DuplicadoCliente[];
  degradado: boolean;
  avisos: string[];
  conflictConfirmed: boolean;
  duplicateConfirmed: boolean;
  confirmoRevisao: boolean;
}

export interface EntradaMeta {
  formatos: string[];
  maxArquivos: number;
  maxLoteMb: number;
}

/** Fallback estático quando GET /entrada-universal/meta não responde. */
export const META_PADRAO: EntradaMeta = {
  formatos: [".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg", ".zip"],
  maxArquivos: 40,
  maxLoteMb: 120,
};

function str(v: unknown): string {
  return typeof v === "string" ? v : "";
}

function strOuNull(v: unknown): string | null {
  return typeof v === "string" && v ? v : null;
}

function obj(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : {};
}

function lista(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

/** Normaliza confiança para 0-100 (aceita fração 0-1 ou percentual). */
export function confiancaPct(v: unknown): number | null {
  if (typeof v !== "number" || !Number.isFinite(v)) return null;
  const pct = v > 0 && v <= 1 ? v * 100 : v;
  return Math.round(Math.max(0, Math.min(100, pct)));
}

/**
 * Extrai um texto humano de um achado (conflito/duplicado/aviso) que pode vir
 * como string ou objeto de forma desconhecida. Nunca devolve "[object Object]".
 */
export function textoDeAchado(v: unknown): string {
  if (typeof v === "string") return v;
  if (v && typeof v === "object" && !Array.isArray(v)) {
    const o = v as Record<string, unknown>;
    for (const k of [
      "mensagem",
      "descricao",
      "detalhe",
      "texto",
      "motivo",
      "alerta",
      "nome",
    ]) {
      const val = o[k];
      if (typeof val === "string" && val) return val;
    }
    try {
      return JSON.stringify(v);
    } catch {
      return "";
    }
  }
  return v == null ? "" : String(v);
}

function normalizarDuplicado(v: unknown): DuplicadoCliente {
  const o = obj(v);
  return {
    clientId: strOuNull(o.client_id) ?? strOuNull(o.id),
    rotulo: textoDeAchado(v) || "Cliente semelhante encontrado",
  };
}

export function normalizarMeta(raw: unknown): EntradaMeta {
  const o = obj(raw);
  const formatos = lista(o.formatos).filter(
    (f): f is string => typeof f === "string" && f.length > 0,
  );
  const maxArquivos =
    typeof o.max_arquivos === "number" && o.max_arquivos > 0
      ? o.max_arquivos
      : META_PADRAO.maxArquivos;
  const maxLoteMb =
    typeof o.max_lote_mb === "number" && o.max_lote_mb > 0
      ? o.max_lote_mb
      : META_PADRAO.maxLoteMb;
  return {
    formatos: formatos.length ? formatos : META_PADRAO.formatos,
    maxArquivos,
    maxLoteMb,
  };
}

/**
 * Converte a resposta de POST /entrada/analisar na proposta editável da tela
 * de confirmação. Devolve null apenas quando não há `rascunho_id` — sem ele o
 * POST de criação não tem destino.
 */
export function normalizarAnalise(
  raw: unknown,
  meuId: string,
): Proposta | null {
  const r = obj(raw);
  const rascunhoId = strOuNull(r.rascunho_id);
  if (!rascunhoId) return null;

  const cliente = obj(r.cliente);
  const area = obj(r.area);
  const conflito = obj(r.conflito);
  const duplicados = obj(r.duplicados);

  const documentos: DocumentoProposto[] = lista(r.documentos).map((d) => {
    const o = obj(d);
    const documentId = str(o.document_id);
    return {
      documentId,
      nome: str(o.nome) || "Documento sem nome",
      classificacao: strOuNull(o.classificacao),
      confianca: confiancaPct(o.confianca),
      // Sem document_id não há como vincular — nasce desmarcado.
      selecionado: Boolean(documentId),
    };
  });

  let prazo: PrazoProposto | null = null;
  const prazoRaw = obj(r.prazo);
  if (r.prazo && (prazoRaw.descricao || prazoRaw.data)) {
    prazo = {
      descricao: str(prazoRaw.descricao),
      data: str(prazoRaw.data),
      origem: strOuNull(prazoRaw.origem),
      requerConfirmacao: prazoRaw.requer_confirmacao_humana !== false,
      criar: true,
      responsavelId: meuId,
    };
  }

  return {
    rascunhoId,
    clienteId: strOuNull(cliente.client_id),
    clienteNome: str(cliente.nome),
    clienteOrigem: strOuNull(cliente.origem),
    clienteJaCadastrada: cliente.ja_cadastrada === true,
    clienteCasosAnteriores:
      typeof cliente.casos_anteriores === "number"
        ? cliente.casos_anteriores
        : null,
    clienteConfianca: confiancaPct(cliente.confianca),
    area: str(area.valor),
    areaConfianca: confiancaPct(area.confianca),
    titulo: str(r.titulo),
    fatos: str(r.fatos),
    parteContraria: str(r.parte_contraria),
    documentos,
    prazo,
    proximaAcao: str(r.proxima_acao),
    advogadoResponsavelId: meuId,
    conflitoAlertas: lista(conflito.alertas).map(textoDeAchado).filter(Boolean),
    duplicados: lista(duplicados.clientes).map(normalizarDuplicado),
    degradado: r.degradado === true,
    avisos: lista(r.avisos).map(textoDeAchado).filter(Boolean),
    conflictConfirmed: false,
    duplicateConfirmed: false,
    confirmoRevisao: false,
  };
}

/** Corpo de POST /entrada/{rascunho_id}/criar-caso a partir da proposta. */
export function montarPayloadCriacao(p: Proposta): Record<string, unknown> {
  const documentosIds = p.documentos
    .filter((d) => d.selecionado && d.documentId)
    .map((d) => d.documentId);
  const payload: Record<string, unknown> = {
    cliente: p.clienteId
      ? { client_id: p.clienteId }
      : { novo_nome: p.clienteNome.trim() || undefined },
    area: p.area || undefined,
    titulo: p.titulo.trim() || undefined,
    fatos: p.fatos.trim() || undefined,
    parte_contraria: p.parteContraria.trim() || undefined,
    documentos_ids: documentosIds,
    proxima_acao: p.proximaAcao.trim() || undefined,
    advogado_responsavel_id: p.advogadoResponsavelId || undefined,
    confirmo_dados_revisados: true,
  };
  // O backend exige `data` no PrazoEntrada — prazo detectado sem data
  // interpretável não vira Deadline (o advogado cria depois, na aba Prazos
  // do caso). Título tem piso de 3 caracteres no schema.
  if (p.prazo?.criar && p.prazo.data) {
    const tituloPrazo = (p.prazo.descricao || "").trim();
    payload.prazo = {
      titulo:
        tituloPrazo.length >= 3 ? tituloPrazo : "Prazo detectado na entrada",
      data: p.prazo.data,
      responsavel_id: p.prazo.responsavelId || p.advogadoResponsavelId,
    };
  }
  if (p.conflitoAlertas.length > 0) {
    payload.conflict_confirmed = p.conflictConfirmed;
  }
  // NUNCA auto-confirmar duplicidade só porque um cliente existente foi
  // escolhido: o gate de "cliente com caso ativo" é do servidor — sem o
  // reconhecimento explícito, o 409 volta com os achados e a tela os
  // exibe com o checkbox (mesma semântica da conversão da Sala Jurídica).
  if (p.duplicados.length > 0 || p.duplicateConfirmed) {
    payload.duplicate_confirmed = p.duplicateConfirmed;
  }
  return payload;
}
