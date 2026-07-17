-- BUG-13 — Arquivar dados de teste em produção
-- ⚠️ REQUER CONFIRMAÇÃO EXPLÍCITA: afeta ~11 dos 14 casos.
-- Usa soft-delete (deleted_at) — REVERSÍVEL — em vez de DELETE físico ou status inexistente.
-- Rodar SOMENTE após backup e confirmação do responsável.
BEGIN;
-- Pré-visualização do que será arquivado:
SELECT numero_interno, titulo, status
  FROM cases
 WHERE deleted_at IS NULL
   AND ( titulo ~* '^(teste|scssdcsdc)' OR titulo ILIKE 'TESTE %' OR titulo ILIKE '%ENCERRAR-FLUXO%' );

-- Aplicar (descomente para executar):
-- UPDATE cases
--    SET deleted_at = now(), updated_at = now()
--  WHERE deleted_at IS NULL
--    AND ( titulo ~* '^(teste|scssdcsdc)' OR titulo ILIKE 'TESTE %' OR titulo ILIKE '%ENCERRAR-FLUXO%' );

SELECT count(*) FILTER (WHERE deleted_at IS NULL) AS casos_vivos_apos
  FROM cases;
COMMIT;
