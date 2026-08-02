/**
 * Fonte ÚNICA de verdade dos status de caso no frontend.
 *
 * Espelha `CaseStatus` de `backend/app/models/case.py`, que por sua vez é o ENUM
 * nativo `casestatus` do Postgres. Qualquer valor fora desta lista é rejeitado
 * pelo backend com HTTP 422 — e, antes da correção, virava 500.
 *
 * Existia antes: quatro listas concorrentes e divergentes (`STATUS_REGISTRY` e
 * `LEGACY_STATUS_TONE` em components/UI.tsx, `STATUS_LABEL`/`ENCERRADOS` em
 * components/Dashboards.tsx, `INACTIVE_CASE_STATUSES` em pages/DashboardModern.tsx),
 * nenhuma igual à outra, com chaves mortas (`em_andamento`, `cancelado`,
 * `inativo`) que nunca casam e ausências (`triagem`, `acordo`) que caem em
 * fallback. Isso produzia contagens diferentes para o mesmo rótulo em telas
 * diferentes.
 *
 * A paridade com o backend é travada por teste automatizado
 * (`backend/tests/test_status_caso_paridade_frontend.py`): se alguém adicionar
 * um status no enum do Python sem atualizar este arquivo, o CI quebra.
 */

/** Os seis valores aceitos pela coluna `cases.status`. Ordem = ciclo de vida.
 * Migration 126 (Bloco 3): quatro estados de trabalho + dois terminais. */
export const CASE_STATUS = [
  "aberto",
  "em_instrucao",
  "em_producao",
  "protocolado",
  "encerrado",
  "arquivado",
] as const;

export type CaseStatus = (typeof CASE_STATUS)[number];

/**
 * Caso em curso — o trabalho jurídico ainda acontece.
 * Espelha `STATUS_ABERTOS` de `backend/app/core/status_caso.py`.
 */
export const CASE_STATUS_ABERTOS: readonly CaseStatus[] = [
  "aberto",
  "em_instrucao",
  "em_producao",
  "protocolado",
];

/**
 * Caso fora da operação. `encerrado` é desfecho; `arquivado` é guarda.
 * Espelha `STATUS_FECHADOS` do backend.
 */
export const CASE_STATUS_FECHADOS: readonly CaseStatus[] = [
  "encerrado",
  "arquivado",
];

const ABERTOS = new Set<string>(CASE_STATUS_ABERTOS);

/**
 * "Ativo" como AGREGADO (o KPI), não como o status homônimo.
 *
 * Desde a migration 126 nenhum status se chama `ativo` — "ativos" é sempre o
 * AGREGADO dos abertos. A ambiguidade antiga foi a causa de o painel mostrar 9
 * ativos enquanto a listagem mostrava 8.
 *
 * A classificação usa allowlist e falha fechada: valor novo, ausente ou
 * inválido não vira ativo por exclusão. Assim o frontend não repete a antiga
 * regra `total - fechados`, que aceitava estados desconhecidos em silêncio.
 */
export function isCasoAtivo(status: unknown): boolean {
  return ABERTOS.has(String(status ?? "").toLowerCase());
}

/** Rótulos em pt-BR. Cobre os SEIS status — sem buracos, sem chave morta. */
export const CASE_STATUS_LABEL: Record<CaseStatus, string> = {
  aberto: "Aberto",
  em_instrucao: "Em instrução",
  em_producao: "Em produção",
  protocolado: "Protocolado",
  encerrado: "Encerrado",
  arquivado: "Arquivado",
};

/** Type guard para valores vindos da API (tipados como `string`). */
export function isCaseStatus(value: unknown): value is CaseStatus {
  return (CASE_STATUS as readonly string[]).includes(String(value));
}
