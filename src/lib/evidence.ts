// evidence.ts — Núcleo de proveniência do sistema (adaptado do PROMPT MESTRE)
// Princípios inegociáveis:
// 1. IA nunca cria fato automaticamente confirmado.
// 5. Todo fato relevante deve apontar para evidência.
// 6. Evidência deve pertencer ao mesmo caso.
// 7. Um modelo não pode inventar evidence_ref_id.
// 8. Saída de IA começa sempre como candidate.

import { createHash } from "crypto";
import { db } from "@/lib/db";

// ── Normalização e hash ─────────────────────────────────────────────────────

/** Normaliza um trecho: remove whitespace excessivo, trim. */
export function normalizeQuote(text: string): string {
  return (text || "").replace(/\s+/g, " ").trim();
}

/** Calcula SHA-256 do trecho normalizado. Usado para dedup + integridade. */
export function quoteHash(text: string): string {
  const normalized = normalizeQuote(text);
  if (!normalized) {
    throw new Error("Evidence quote cannot be empty");
  }
  return createHash("sha256").update(normalized, "utf8").digest("hex");
}

/** Hash canônico para idempotência (sorted keys JSON → SHA-256). */
export function canonicalHash(payload: unknown): string {
  const raw = JSON.stringify(payload, Object.keys(payload as object).sort());
  return createHash("sha256").update(raw, "utf8").digest("hex");
}

// ── EvidenceRef service ─────────────────────────────────────────────────────

export interface CreateEvidenceInput {
  caseId: string;
  documentId?: string | null;
  quote: string;
  pageNumber?: number | null;
  sectionLabel?: string | null;
  charStart?: number | null;
  charEnd?: number | null;
  sourceKind: string; // text | ocr | manual | llm_extracted
  retrievalMethod: string; // deterministic | llm | manual
  documentHash?: string | null;
  metadata?: Record<string, unknown>;
}

export interface EvidenceRefRecord {
  id: string;
  caseId: string;
  documentId: string | null;
  pageNumber: number | null;
  quote: string;
  quoteHash: string;
  sourceKind: string;
  retrievalMethod: string;
  verified: boolean;
  createdAt: string;
}

/**
 * Cria uma evidência com verificação de ownership e dedup.
 * Princípio 6: Evidência deve pertencer ao mesmo caso.
 * Princípio 7: Um modelo não pode inventar evidence_ref_id.
 */
export async function createEvidence(input: CreateEvidenceInput): Promise<EvidenceRefRecord> {
  const { caseId, quote, documentId, pageNumber, sourceKind, retrievalMethod } = input;

  if (!caseId) throw new Error("caseId obrigatório");
  if (!quote || !quote.trim()) throw new Error("Trecho vazio");

  const normalized = normalizeQuote(quote);
  if (!normalized) throw new Error("Trecho normalizado vazio");

  const qhash = quoteHash(normalized);

  // Dedup: se já existe evidência com mesmo (caseId, documentId, pageNumber, quoteHash), retorna a existente
  const existing = await db.evidenceRef.findFirst({
    where: {
      caseId,
      documentId: documentId || null,
      pageNumber: pageNumber || null,
      quoteHash: qhash,
    },
  });

  if (existing) {
    return toRecord(existing);
  }

  const evidence = await db.evidenceRef.create({
    data: {
      caseId,
      documentId: documentId || null,
      pageNumber: pageNumber || null,
      sectionLabel: input.sectionLabel || null,
      charStart: input.charStart || null,
      charEnd: input.charEnd || null,
      quote: normalized,
      quoteHash: qhash,
      documentHash: input.documentHash || null,
      sourceKind,
      retrievalMethod,
      metadata: JSON.stringify(input.metadata || {}),
    },
  });

  return toRecord(evidence);
}

/** Lista evidências de um caso. */
export async function listEvidence(caseId: string): Promise<EvidenceRefRecord[]> {
  const refs = await db.evidenceRef.findMany({
    where: { caseId },
    orderBy: { createdAt: "asc" },
  });
  return refs.map(toRecord);
}

/** Valida integridade: o hash do quote atual bate com o hash armazenado? */
export async function validateEvidenceIntegrity(
  caseId: string,
  evidenceId: string
): Promise<EvidenceRefRecord> {
  const evidence = await db.evidenceRef.findUnique({
    where: { id: evidenceId },
  });

  if (!evidence) {
    throw new EvidenceGateError("Evidência inexistente");
  }

  if (evidence.caseId !== caseId) {
    throw new EvidenceGateError("Evidência pertence a outro caso");
  }

  const currentHash = quoteHash(evidence.quote);
  if (currentHash !== evidence.quoteHash) {
    throw new EvidenceGateError("Integridade da evidência inválida — hash não confere");
  }

  return toRecord(evidence);
}

// ── Evidence Citation Gate ──────────────────────────────────────────────────
// Princípio: a IA está usando apenas evidências que realmente foram fornecidas?

export class EvidenceGateError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EvidenceGateError";
  }
}

/**
 * Valida que todos os evidence_ref_ids requisitados pela IA existem e pertencem ao caso.
 * Princípio 7: Um modelo não pode inventar evidence_ref_id.
 */
export async function validateEvidenceIds(
  requestedIds: string[],
  allowedIds: Set<string>
): Promise<void> {
  if (!requestedIds || requestedIds.length === 0) {
    throw new EvidenceGateError("Item sem evidência — todo fato deve apontar para evidence_ref_id");
  }

  const invalid = requestedIds.filter((id) => !allowedIds.has(id));
  if (invalid.length > 0) {
    throw new EvidenceGateError(
      `Evidências não autorizadas (IA inventou IDs?): ${invalid.join(", ")}`
    );
  }
}

// ── Helper ──────────────────────────────────────────────────────────────────

function toRecord(e: {
  id: string;
  caseId: string;
  documentId: string | null;
  pageNumber: number | null;
  quote: string;
  quoteHash: string;
  sourceKind: string;
  retrievalMethod: string;
  verified: boolean;
  createdAt: Date;
}): EvidenceRefRecord {
  return {
    id: e.id,
    caseId: e.caseId,
    documentId: e.documentId,
    pageNumber: e.pageNumber,
    quote: e.quote,
    quoteHash: e.quoteHash,
    sourceKind: e.sourceKind,
    retrievalMethod: e.retrievalMethod,
    verified: e.verified,
    createdAt: e.createdAt.toISOString(),
  };
}
