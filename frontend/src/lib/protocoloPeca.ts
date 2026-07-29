// ── FLX-070 — registro de protocolo antes do status "protocolada" ──────────
// O backend agora rejeita (422) o PATCH direto de status para "protocolada"
// sem numero_protocolo registrado (e 403 para quem não é advogado). O caminho
// de UI passa por PATCH /legal-docs/{id}/protocolo ANTES do PATCH de status.
// Helpers puros — testáveis sem axios/React.
import type { LegalDoc } from "../types";

/** Campos do modal "Registrar protocolo" (strings cruas dos inputs). */
export interface ProtocoloCampos {
  numero: string;
  tribunal: string;
  /** yyyy-mm-dd do <input type="date">; "" = backend assume o instante atual. */
  data: string;
}

/** Payload de PATCH /legal-docs/{id}/protocolo (LegalDocProtocolo). */
export interface ProtocoloPayload {
  numero_protocolo: string;
  protocolo_tribunal?: string;
  protocolado_em?: string;
}

/**
 * Monta o payload do registro de protocolo. Número é obrigatório (retorna
 * null se vazio — o chamador decide a mensagem); tribunal/data só entram
 * quando preenchidos (o backend assume "agora" sem data).
 */
export function montarPayloadProtocolo(
  campos: ProtocoloCampos,
): ProtocoloPayload | null {
  const numero = campos.numero.trim();
  if (!numero) return null;
  const payload: ProtocoloPayload = { numero_protocolo: numero };
  const tribunal = campos.tribunal.trim();
  if (tribunal) payload.protocolo_tribunal = tribunal;
  const data = campos.data.trim();
  // Data-only ISO: o backend interpreta como meia-noite UTC (nunca no futuro).
  if (data) payload.protocolado_em = data;
  return payload;
}

/**
 * "Hoje" no calendário LOCAL do usuário, em yyyy-mm-dd — para o `max` do
 * <input type="date">, que também representa dia local. `toISOString()` daria o
 * dia UTC: em fuso positivo bloquearia a data real de hoje e em negativo
 * liberaria amanhã — inaceitável num campo que é prova de tempestividade.
 */
export function dataLocalISO(ref: Date = new Date()): string {
  const mes = String(ref.getMonth() + 1).padStart(2, "0");
  const dia = String(ref.getDate()).padStart(2, "0");
  return `${ref.getFullYear()}-${mes}-${dia}`;
}

/** A peça já tem comprovante registrado? (o modal pode ser pulado) */
export function temProtocoloRegistrado(
  doc: Pick<LegalDoc, "numero_protocolo">,
): boolean {
  return !!(doc.numero_protocolo ?? "").trim();
}

/**
 * Mensagem amigável para falhas do fluxo de protocolo: 403 (requer_advogado)
 * vira texto fixo; 422 mostra o `detail` do backend (string ou {mensagem}).
 */
export function mensagemErroProtocolo(
  status: number | undefined,
  detail: unknown,
  fallback = "Falha ao registrar o protocolo",
): string {
  if (status === 403) return "Apenas advogados podem registrar protocolo";
  if (typeof detail === "string" && detail) return detail;
  if (detail && typeof detail === "object") {
    const d = detail as { mensagem?: string };
    return d.mensagem ?? JSON.stringify(detail).slice(0, 200);
  }
  return fallback;
}
