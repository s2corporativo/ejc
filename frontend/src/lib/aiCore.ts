// ── Client central do Núcleo Único de IA (/ai/core/*) ───────────────────────
// Todo consumo novo de IA DEVE passar por aqui — nenhuma tela chama
// provider/modelo diretamente; o backend monta contexto real com
// RBAC/ownership; toda resposta jurídica é rascunho HITL.
import api from "./api";

// Fonte citada pelo RAG/agente (shape flexível conforme domínio)
export interface AIFonte {
  titulo?: string;
  trecho?: string;
  score?: number;
  [k: string]: unknown;
}

// Resposta padrão de todos os endpoints /ai/core/*
export interface AICoreResponse {
  conteudo: string;
  agente: string;
  task_type: string;
  modelo: string;
  provider: string;
  fontes: AIFonte[];
  citacoes?: unknown[];
  is_rascunho: boolean;
  requer_revisao: boolean;
  status_hitl: string;
  aviso_hitl: string;
  sem_base_verificavel?: boolean;
  custo_estimado_brl?: number;
  tokens_input?: number;
  tokens_output?: number;
  log_id?: string;
}

export interface AIChatRequest {
  mensagem: string;
  case_id?: string;
  nivel_inteligencia?: string;
}

export interface AITaskRequest {
  task_type: string;
  domain?: string;
  mensagem: string;
  case_id?: string;
  document_id?: string;
  process_id?: string;
  params?: Record<string, unknown>;
  usar_rag?: boolean;
}

export interface AIAnalyzeRequest {
  domain: string;
  mensagem: string;
  case_id?: string;
}

export interface AIGenerateRequest {
  tipo: string;
  mensagem: string;
  case_id?: string;
  params?: Record<string, unknown>;
}

export interface AIReportRequest {
  domain: string;
  mensagem?: string;
  case_id?: string;
}

export async function aiChat(req: AIChatRequest): Promise<AICoreResponse> {
  const { data } = await api.post("/ai/core/chat", req);
  return data;
}

export async function aiTask(req: AITaskRequest): Promise<AICoreResponse> {
  const { data } = await api.post("/ai/core/task", req);
  return data;
}

export async function aiAnalyze(req: AIAnalyzeRequest): Promise<AICoreResponse> {
  const { data } = await api.post("/ai/core/analyze", req);
  return data;
}

export async function aiGenerate(req: AIGenerateRequest): Promise<AICoreResponse> {
  const { data } = await api.post("/ai/core/generate", req);
  return data;
}

export async function aiReport(req: AIReportRequest): Promise<AICoreResponse> {
  const { data } = await api.post("/ai/core/report", req);
  return data;
}

export async function aiStatus(): Promise<Record<string, unknown>> {
  const { data } = await api.get("/ai/core/status");
  return data;
}

export async function aiAgents(): Promise<Record<string, unknown>> {
  const { data } = await api.get("/ai/core/agents");
  return data;
}

export async function aiSkills(): Promise<Record<string, unknown>> {
  const { data } = await api.get("/ai/core/skills");
  return data;
}
