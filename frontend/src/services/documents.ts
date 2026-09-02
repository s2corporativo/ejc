import type { AxiosError } from "axios";
import api from "../lib/api";

export type OperationalStatus = "ready" | "processing" | "attention";

export interface DocumentPolicy {
  extensions: string[];
  max_upload_mb: number;
  confidentiality: string[];
  malware_scan_enabled: boolean;
}

export interface DocumentItem {
  id: string;
  titulo: string;
  tipo?: string | null;
  filename: string;
  size_bytes?: number | null;
  confidencialidade: string;
  case_id?: string | null;
  client_id?: string | null;
  versao?: number | null;
  versao_grupo_id?: string | null;
  versao_anterior_id?: string | null;
  analysis_status?: string | null;
  analysis_updated_at?: string | null;
  integrity_status?: string | null;
  integrity_verified_at?: string | null;
  malware_scan_status?: string | null;
  malware_scanned_at?: string | null;
  rag_status?: string | null;
  rag_indexed_at?: string | null;
  legal_hold?: boolean;
  retention_until?: string | null;
  operational_status?: OperationalStatus;
  attention_reasons?: string[];
  publicado_portal?: boolean;
  sha256?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DocumentListResponse {
  data: DocumentItem[];
  total: number | null;
  page: number;
  page_size: number;
  next_cursor?: { created_at: string; id: string } | null;
}

export interface DocumentStats {
  total: number;
  confidenciais: number;
  este_mes: number;
  inbox: number;
  tipos_distintos: number;
  por_tipo: Array<{ tipo: string; total: number }>;
}

export interface DocumentVersionResponse {
  document_id: string;
  group_id: string;
  data: Array<DocumentItem & { is_current: boolean }>;
  total: number;
}

export interface DocumentHistoryResponse {
  document_id: string;
  data: Array<{ action: string; created_at: string }>;
  total: number;
}

export interface DocumentGovernance {
  document_id: string;
  retention_until?: string | null;
  legal_hold: boolean;
  legal_hold_reason?: string | null;
  legal_hold_set_by?: string | null;
  legal_hold_set_at?: string | null;
  deleted_at?: string | null;
}

export interface ListDocumentsParams {
  page?: number;
  pageSize?: number;
  search?: string;
  caseId?: string | number | null;
  clientId?: string | null;
  tipo?: string | null;
  confidencialidade?: string | null;
  dataInicio?: string | null;
  dataFim?: string | null;
  classificacaoPendente?: boolean;
}

export interface UploadDocumentInput {
  file: File;
  titulo: string;
  tipo?: string | null;
  confidencialidade: string;
  caseId?: string | null;
  clientId?: string | null;
  predecessorId?: string | null;
  allowDuplicate?: boolean;
}

export interface DuplicateDetail {
  code: "exact_duplicate";
  message: string;
  document_id: string;
}

export interface DocumentClassification {
  doc_id: string;
  aplicado: boolean;
  tipo_atual?: string | null;
  tipo_sugerido?: string | null;
  confianca?: "alta" | "media" | "baixa" | null;
  justificativa?: string;
  disponivel?: boolean;
  aviso?: string;
}

export const STATUS_LABEL: Record<OperationalStatus, string> = {
  ready: "Pronto",
  processing: "Processando",
  attention: "Atenção",
};

export const ATTENTION_LABEL: Record<string, string> = {
  sem_caso: "Sem caso vinculado",
  sem_tipo: "Tipo pendente",
  analise_falhou: "Análise precisa ser refeita",
  integridade_atencao: "Integridade precisa de verificação",
  seguranca_atencao: "Verificação de segurança pendente",
};

export function humanStatus(document: DocumentItem): OperationalStatus {
  if (document.operational_status) return document.operational_status;
  const reasons = document.attention_reasons || [];
  if (reasons.length > 0) return "attention";
  if (["failed", "stale"].includes(document.analysis_status || "")) return "attention";
  if (["divergent", "error", "unavailable"].includes(document.integrity_status || ""))
    return "attention";
  if (["infected", "error", "unavailable"].includes(document.malware_scan_status || ""))
    return "attention";
  if (["pending", "processing"].includes(document.analysis_status || ""))
    return "processing";
  if (["pending", "processing"].includes(document.malware_scan_status || ""))
    return "processing";
  return "ready";
}

export async function getDocumentPolicy(): Promise<DocumentPolicy> {
  const { data } = await api.get<DocumentPolicy>("/documents/policy");
  return data;
}

export async function listDocuments(
  params: ListDocumentsParams = {},
): Promise<DocumentListResponse> {
  const { data } = await api.get<DocumentListResponse>("/documents/", {
    params: {
      page: params.page ?? 1,
      page_size: params.pageSize ?? 25,
      search: params.search || undefined,
      case_id: params.caseId ?? undefined,
      client_id: params.clientId || undefined,
      tipo: params.tipo || undefined,
      confidencialidade: params.confidencialidade || undefined,
      data_inicio: params.dataInicio || undefined,
      data_fim: params.dataFim || undefined,
      classificacao_pendente: params.classificacaoPendente || undefined,
      include_total: true,
    },
  });
  return data;
}

export async function listInbox(
  params: Pick<ListDocumentsParams, "page" | "pageSize" | "caseId" | "clientId"> = {},
): Promise<DocumentListResponse> {
  const { data } = await api.get<DocumentListResponse>("/documents/workflow/inbox", {
    params: {
      page: params.page ?? 1,
      page_size: params.pageSize ?? 25,
      case_id: params.caseId ?? undefined,
      client_id: params.clientId || undefined,
    },
  });
  return data;
}

export async function getDocumentStats(): Promise<DocumentStats> {
  const { data } = await api.get<DocumentStats>("/documents/workflow/stats");
  return data;
}

export async function getDocument(id: string): Promise<DocumentItem> {
  const { data } = await api.get<DocumentItem>(`/documents/${id}`);
  return data;
}

export async function getDocumentVersions(id: string): Promise<DocumentVersionResponse> {
  const { data } = await api.get<DocumentVersionResponse>(`/documents/${id}/versions`);
  return data;
}

export async function getDocumentHistory(id: string): Promise<DocumentHistoryResponse> {
  const { data } = await api.get<DocumentHistoryResponse>(`/documents/${id}/history`);
  return data;
}

export async function getDocumentGovernance(id: string): Promise<DocumentGovernance> {
  const { data } = await api.get<DocumentGovernance>(`/documents/${id}/governanca`);
  return data;
}

export async function updateDocumentGovernance(
  id: string,
  payload: {
    retention_until?: string | null;
    legal_hold?: boolean;
    legal_hold_reason?: string | null;
    motivo_alteracao: string;
  },
): Promise<DocumentGovernance> {
  const { data } = await api.patch<DocumentGovernance>(
    `/documents/${id}/governanca`,
    payload,
  );
  return data;
}

export async function updateDocumentMetadata(
  id: string,
  payload: { titulo?: string; tipo?: string | null; confidencialidade?: string },
): Promise<DocumentItem> {
  const { data } = await api.patch<DocumentItem>(`/documents/${id}`, payload);
  return data;
}

export async function uploadDocument(input: UploadDocumentInput): Promise<DocumentItem> {
  const body = new FormData();
  body.append("file", input.file);
  body.append("titulo", input.titulo.trim());
  body.append("confidencialidade", input.confidencialidade);
  if (input.tipo) body.append("tipo", input.tipo);
  if (input.caseId) body.append("case_id", String(input.caseId));
  if (input.clientId) body.append("client_id", input.clientId);
  if (input.predecessorId) body.append("documento_anterior_id", input.predecessorId);
  if (input.allowDuplicate) body.append("permitir_duplicado", "true");
  const { data } = await api.post<DocumentItem>("/documents/workflow/upload", body);
  return data;
}

export function duplicateDetail(error: unknown): DuplicateDetail | null {
  const axiosError = error as AxiosError<{ detail?: DuplicateDetail }>;
  if (axiosError.response?.status !== 409) return null;
  const detail = axiosError.response?.data?.detail;
  return detail?.code === "exact_duplicate" ? detail : null;
}

export async function moveDocumentToTrash(id: string): Promise<void> {
  await api.delete(`/documents/${id}`);
}

export async function getDocumentBlob(id: string): Promise<Blob> {
  const { data } = await api.get(`/documents/${id}/download`, { responseType: "blob" });
  return data as Blob;
}

export async function reprocessDocument(id: string): Promise<void> {
  await api.post(`/documents/${id}/reprocessar-analise`);
}

export async function verifyDocumentIntegrity(id: string): Promise<void> {
  await api.post(`/documents/${id}/verificar-integridade`);
}

export async function setDocumentRag(id: string, enabled: boolean): Promise<void> {
  await api.post(`/documents/${id}/rag`, { ativo: enabled });
}

export async function publishDocumentToPortal(id: string, published: boolean): Promise<void> {
  await api.patch(`/documents/${id}/publicacao-portal`, { publicado: published });
}

export async function classifyDocument(
  id: string,
  apply = false,
): Promise<DocumentClassification> {
  const { data } = await api.post<DocumentClassification>(`/documents/${id}/classificar`, null, {
    params: { aplicar: apply },
  });
  return data;
}

export async function fetchAllCaseDocuments(
  caseId: string | number,
): Promise<DocumentItem[]> {
  const pageSize = 100;
  const all: DocumentItem[] = [];
  let page = 1;
  let total = Number.POSITIVE_INFINITY;

  while (all.length < total) {
    const result = await listDocuments({ caseId, page, pageSize });
    all.push(...(result.data || []));
    total = result.total ?? all.length;
    if (result.data.length < pageSize) break;
    page += 1;
    if (page > 100) break;
  }
  return all;
}
