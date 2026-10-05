// api-helpers.ts — Helpers compartilhados para APIs (parse/validação/limites)
//
// Centraliza:
// - parseJsonBody<T>: parse seguro com discriminated union {ok:true,body}|{ok:false,error}
// - requireText: valida texto (min/max/fieldName) e retorna valor ou erro
// - truncateForDisplay: corta texto longo p/ exibição em logs/UI
// - normalizeOAB/normalizeUF/formatOAB: formatação de inscrição OAB
// - PLAN_LIMITS/VALID_PLANS/VALID_UFS: limites e conjuntos válidos
// - isPrismaUniqueViolation: detecta P2002 (constraint @@unique)
//
// IMPORTANTE: tudo determinístico, sem custo de IA.

import type { NextRequest } from "next/server";

// ── Constantes de limite ─────────────────────────────────────────────────

export const MAX_API_TEXT_LENGTH = 100_000; // 100k chars: teto de texto de entrada
export const MAX_PRAZO_DIAS = 3650; // 10 anos — teto para prazo calculado

export const PLAN_LIMITS: Record<string, number> = {
  free: 3,
  individual_1: 50,
  individual_2: 100,
  individual_3: 200,
  enterprise: 1000,
};

export const VALID_PLANS = new Set<string>(Object.keys(PLAN_LIMITS));

export const VALID_UFS = new Set<string>(
  "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split(" "),
);

// ── Erro de Prisma P2002 (constraint @@unique) ──────────────────────────

interface PrismaLikeError {
  code?: string;
  clientVersion?: string;
  message?: string;
}

export function isPrismaUniqueViolation(e: unknown): boolean {
  if (!e || typeof e !== "object") return false;
  const err = e as PrismaLikeError;
  if (err.code === "P2002") return true;
  // fallback: mensagem com "Unique constraint"
  if (typeof err.message === "string" && /unique constraint/i.test(err.message)) return true;
  return false;
}

// ── parseJsonBody<T> ─────────────────────────────────────────────────────

export type ParseOk<T> = { ok: true; body: T };
export type ParseErr = { ok: false; error: string };
export type ParseResult<T> = ParseOk<T> | ParseErr;

export async function parseJsonBody<T = Record<string, unknown>>(
  req: NextRequest,
): Promise<ParseResult<T>> {
  try {
    const text = await req.text();
    if (!text || text.trim().length === 0) {
      return { ok: false, error: "Corpo da requisição vazio" };
    }
    const body = JSON.parse(text) as T;
    return { ok: true, body };
  } catch {
    return { ok: false, error: "JSON inválido" };
  }
}

// ── requireText: valida texto de entrada ─────────────────────────────────

export interface RequireTextOptions {
  min?: number;
  max?: number;
  fieldName?: string;
}

export type TextOk = { ok: true; value: string };
export type TextErr = { ok: false; error: string };
export type TextResult = TextOk | TextErr;

export function requireText(raw: unknown, opts: RequireTextOptions = {}): TextResult {
  const min = opts.min ?? 1;
  const max = opts.max ?? MAX_API_TEXT_LENGTH;
  const fieldName = opts.fieldName ?? "texto";
  if (typeof raw !== "string") {
    return { ok: false, error: `${fieldName} deve ser string` };
  }
  const value = raw.trim();
  if (value.length < min) {
    return { ok: false, error: `${fieldName} muito curto (mínimo ${min} caracteres)` };
  }
  if (value.length > max) {
    return { ok: false, error: `${fieldName} muito longo (máximo ${max} caracteres)` };
  }
  return { ok: true, value };
}

// ── truncateForDisplay ───────────────────────────────────────────────────

export function truncateForDisplay(text: string, max = 500): string {
  if (typeof text !== "string") return "";
  if (text.length <= max) return text;
  return text.slice(0, max) + "…";
}

// ── OAB: normalização e formatação ───────────────────────────────────────

export function normalizeOAB(raw: string | null | undefined): string {
  if (!raw) return "";
  return (raw.match(/\d/g) || []).join("");
}

export function normalizeUF(raw: string | null | undefined): string {
  if (!raw) return "";
  // NFD: separa acentos e remove-os; uppercase; pega 2 primeiros chars
  const semAcento = (raw || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
    .trim();
  return semAcento.slice(0, 2);
}

export function formatOAB(numero: string | null | undefined, estado: string | null | undefined): string {
  const n = normalizeOAB(numero);
  const uf = normalizeUF(estado);
  if (!n || !uf) return "";
  return `OAB/${uf} ${n}`;
}

// ── Helper: montar resposta JSON com status ──────────────────────────────

export function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

// ── Helper: extrair IP do cliente ───────────────────────────────────────

export function clientIp(req: NextRequest): string | null {
  return (
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    req.headers.get("x-real-ip") ||
    null
  );
}
