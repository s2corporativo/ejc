// ── src/lib/ajuizamento.ts ───────────────────────────────────────────────────
// Tipos e helpers PUROS do núcleo de ajuizamento (testáveis sem React/axios).
// O backend é a fonte da verdade: aqui só há tradução para a UI.

export type EstadoAjuizamento =
  | "DRAFT"
  | "PREPARING"
  | "VALIDATING"
  | "INVALID"
  | "READY_FOR_REVIEW"
  | "APPROVED"
  | "SIGNING"
  | "READY_TO_SUBMIT"
  | "SUBMITTING"
  | "SUBMITTED"
  | "CONFIRMED"
  | "SYNCING"
  | "FAILED"
  | "REQUIRES_AUTHORIZATION"
  | "CANCELLED";

export type EstadoCapacidade =
  "SUPPORTED" | "UNSUPPORTED" | "CONDITIONAL" | "REQUIRES_AUTHORIZATION";

export interface AssuntoAjuizamento {
  codigo: string;
  nome?: string | null;
  principal?: boolean;
}

export interface DocumentoAjuizamento {
  document_id: string;
  document_type:
    | "procuracao"
    | "documento_pessoal"
    | "comprovante"
    | "probatorio"
    | "complementar";
  tpu_document_type?: string | null;
  ordem?: number;
}

export interface AdvogadoAjuizamento {
  user_id: string;
  tipo?: "advogado" | "advogado_auxiliar" | "estagiario";
  procuracao_id?: string | null;
}

export interface Preflight {
  ready: boolean;
  errors: string[];
  warnings: string[];
  missing_fields: string[];
  authorization_requirements: string[];
  matriz?: MatrizCapacidades | null;
  validado_em?: string;
}

export interface MatrizCapacidades {
  conector: string;
  sistema: string;
  tribunal?: string | null;
  ambiente: string;
  operacoes: Record<string, { estado: EstadoCapacidade; motivo: string }>;
  requisitos_autorizacao: string[];
  protocolo_real_liberado: boolean;
  perfil_id?: string | null;
  grau?: string | null;
}

export interface Filing {
  id: string;
  case_id: string;
  client_id: string;
  profile_id?: string | null;
  peticao_legal_doc_id?: string | null;
  estado: EstadoAjuizamento;
  tribunal_code?: string | null;
  system?: string | null;
  segment?: string | null;
  degree?: string | null;
  environment?: string | null;
  jurisdicao?: string | null;
  codigo_localidade?: string | null;
  competencia?: string | null;
  competencia_codigo?: string | null;
  classe_codigo?: string | null;
  classe_nome?: string | null;
  assuntos: AssuntoAjuizamento[];
  valor_causa?: string | null;
  nivel_sigilo: number;
  gratuidade: boolean;
  tutela: boolean;
  prioridade?: string | null;
  caracteristicas: Record<string, string | number | boolean | null>;
  documentos: DocumentoAjuizamento[];
  advogados: AdvogadoAjuizamento[];
  canonico?: Record<string, unknown> | null;
  canonico_hash?: string | null;
  preflight?: Preflight | null;
  assinatura?: Record<string, unknown> | null;
  numero_cnj?: string | null;
  protocolado_em?: string | null;
  ultimo_erro?: string | null;
}

export interface PerfilTribunal {
  id: string;
  tribunal_code: string;
  tribunal_nome?: string | null;
  segment: string;
  degree: string;
  system: string;
  environment: string;
  integration_type: string;
  base_url?: string | null;
  api_version?: string | null;
  auth_type: string;
  client_id_ref?: string | null;
  certificate_ref?: string | null;
  certificate_required: boolean;
  filing_supported: boolean;
  append_petition_supported: boolean;
  process_query_supported: boolean;
  movement_query_supported: boolean;
  document_download_supported: boolean;
  notice_query_supported: boolean;
  callback_supported: boolean;
  authorized: boolean;
  production_endpoint_verified: boolean;
  credentials_valid: boolean;
  homologation_checklist?: Record<string, unknown> | null;
  homologated_at?: string | null;
  status: EstadoCapacidade;
  documentation_url?: string | null;
  ativo: boolean;
}

/** Confirmação literal exigida pelo backend na revisão humana final. */
export const CONFIRMACAO_REVISAO = "REVISAR E PROTOCOLAR";

export const ROTULO_ESTADO: Record<EstadoAjuizamento, string> = {
  DRAFT: "Rascunho",
  PREPARING: "Preparando",
  VALIDATING: "Validando",
  INVALID: "Com pendências",
  READY_FOR_REVIEW: "Pronto para revisão",
  APPROVED: "Aprovado",
  SIGNING: "Assinando",
  READY_TO_SUBMIT: "Pronto para protocolar",
  SUBMITTING: "Enviando",
  SUBMITTED: "Protocolado",
  CONFIRMED: "Confirmado",
  SYNCING: "Sincronizando",
  FAILED: "Falhou",
  REQUIRES_AUTHORIZATION: "Aguardando autorização",
  CANCELLED: "Cancelado",
};

export const ROTULO_CAPACIDADE: Record<EstadoCapacidade, string> = {
  SUPPORTED: "Disponível",
  UNSUPPORTED: "Não oferecido",
  CONDITIONAL: "Condicional",
  REQUIRES_AUTHORIZATION: "Requer autorização",
};

export const SISTEMAS: { valor: string; rotulo: string; nota: string }[] = [
  {
    valor: "pje_mni",
    rotulo: "PJe (MNI)",
    nota: "Peticionamento pelo serviço MNI Client; exige perfil do tribunal homologado.",
  },
  {
    valor: "pdpj",
    rotulo: "PDPJ-Br / Jus.br",
    nota: "Portal de Serviços do CNJ; depende de habilitação institucional.",
  },
  {
    valor: "eproc",
    rotulo: "eproc",
    nota: "Integração individual por tribunal (convênio); sem API pública uniforme.",
  },
  {
    valor: "manual",
    rotulo: "Protocolo manual no portal",
    nota: "O EJC prepara, valida, revisa e registra o protocolo feito no portal.",
  },
];

export const ETAPAS = [
  "Caso de origem",
  "Tribunal e sistema",
  "Classe e assuntos",
  "Partes",
  "Advogados",
  "Características",
  "Petição e anexos",
  "Validação",
  "Revisão",
  "Assinatura e protocolo",
  "Resultado",
] as const;

export type Etapa = (typeof ETAPAS)[number];

/** Etapa em que o wizard deve abrir para um dado estado do ajuizamento. */
export function etapaDoEstado(estado: EstadoAjuizamento): number {
  switch (estado) {
    case "DRAFT":
    case "PREPARING":
      return 1;
    case "INVALID":
    case "VALIDATING":
      return 7;
    case "READY_FOR_REVIEW":
      return 8;
    case "APPROVED":
    case "SIGNING":
    case "READY_TO_SUBMIT":
    case "REQUIRES_AUTHORIZATION":
    case "FAILED":
      return 9;
    case "SUBMITTING":
    case "SUBMITTED":
    case "CONFIRMED":
    case "SYNCING":
    case "CANCELLED":
      return 10;
    default:
      return 0;
  }
}

/** Um ajuizamento em estado protocolado não volta a ser editável. */
export function podeEditar(estado: EstadoAjuizamento): boolean {
  return [
    "DRAFT",
    "INVALID",
    "READY_FOR_REVIEW",
    "REQUIRES_AUTHORIZATION",
    "FAILED",
  ].includes(estado);
}

export function podeAprovar(f: Pick<Filing, "estado" | "preflight">): boolean {
  return f.estado === "READY_FOR_REVIEW" && !!f.preflight?.ready;
}

export function podeAssinar(estado: EstadoAjuizamento): boolean {
  return estado === "APPROVED" || estado === "SIGNING";
}

export function podeProtocolar(
  f: Pick<Filing, "estado" | "assinatura">,
): boolean {
  return (
    !!f.assinatura &&
    ["READY_TO_SUBMIT", "FAILED", "REQUIRES_AUTHORIZATION"].includes(f.estado)
  );
}

/** Corpo do POST /ajuizamento/filings (só campos preenchidos). */
export function montarPayloadFiling(
  form: Partial<Filing> & { case_id?: string },
): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  const copiar = <K extends keyof Filing>(campo: K) => {
    const valor = form[campo];
    if (valor !== undefined && valor !== null && valor !== "")
      payload[campo] = valor;
  };
  if (form.case_id) payload.case_id = form.case_id;
  (
    [
      "peticao_legal_doc_id",
      "tribunal_code",
      "system",
      "segment",
      "degree",
      "environment",
      "jurisdicao",
      "codigo_localidade",
      "competencia",
      "competencia_codigo",
      "classe_codigo",
      "classe_nome",
      "valor_causa",
      "prioridade",
    ] as (keyof Filing)[]
  ).forEach(copiar);
  if (form.assuntos) {
    payload.assuntos = form.assuntos
      .filter((a) => a.codigo?.trim())
      .map((a) => ({
        codigo: a.codigo.trim(),
        nome: a.nome || undefined,
        principal: !!a.principal,
      }));
  }
  if (form.documentos) payload.documentos = form.documentos;
  if (form.advogados) payload.advogados = form.advogados;
  if (form.caracteristicas) payload.caracteristicas = form.caracteristicas;
  if (typeof form.nivel_sigilo === "number")
    payload.nivel_sigilo = form.nivel_sigilo;
  if (typeof form.gratuidade === "boolean")
    payload.gratuidade = form.gratuidade;
  if (typeof form.tutela === "boolean") payload.tutela = form.tutela;
  return payload;
}

/** Resumo textual do que o conector do destino permite de fato. */
export function resumoCapacidade(matriz?: MatrizCapacidades | null): string {
  if (!matriz) return "Nenhum conector resolvido para o destino.";
  const envio = matriz.operacoes?.file_new_case;
  if (!envio) return "Este conector não oferece protocolo de petição inicial.";
  if (envio.estado === "SUPPORTED") {
    return `Protocolo eletrônico liberado por ${matriz.conector} (${matriz.ambiente}).`;
  }
  return `${ROTULO_CAPACIDADE[envio.estado]}: ${envio.motivo || "pendência de habilitação"}.`;
}

/** Só há protocolo eletrônico real com autorização + homologação + credencial. */
export function protocoloEletronicoLiberado(
  matriz?: MatrizCapacidades | null,
): boolean {
  return !!matriz?.protocolo_real_liberado;
}

export function checklistHomologacao(p: PerfilTribunal) {
  return [
    {
      chave: "authorized",
      rotulo: "Habilitação institucional registrada",
      ok: p.authorized,
    },
    {
      chave: "homologated_at",
      rotulo: "Homologação concluída com o tribunal",
      ok: !!p.homologated_at,
    },
    {
      chave: "production_endpoint_verified",
      rotulo: "Endpoint de produção verificado",
      ok: p.production_endpoint_verified,
    },
    {
      chave: "credentials_valid",
      rotulo: "Credencial validada",
      ok: p.credentials_valid,
    },
  ];
}
