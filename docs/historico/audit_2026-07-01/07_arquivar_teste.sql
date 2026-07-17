-- BUG-13 — Arquivar (soft-delete) casos de teste. Confirmado pelo usuário.
-- Reversível (deleted_at). NÃO faz DELETE físico. Rodar após backup.
-- Preview:
SELECT numero_interno, titulo, status
  FROM cases
 WHERE deleted_at IS NULL
   AND ( titulo ~* '^(teste|scssdcsdc)' OR titulo ILIKE 'TESTE %' OR titulo ILIKE '%ENCERRAR-FLUXO%' )
 ORDER BY numero_interno;

-- Aplicar:
UPDATE cases
   SET deleted_at = now(), updated_at = now()
 WHERE deleted_at IS NULL
   AND ( titulo ~* '^(teste|scssdcsdc)' OR titulo ILIKE 'TESTE %' OR titulo ILIKE '%ENCERRAR-FLUXO%' );

-- Resultado:
SELECT count(*) FILTER (WHERE deleted_at IS NULL) AS casos_vivos,
       count(*) FILTER (WHERE deleted_at IS NOT NULL) AS casos_arquivados
  FROM cases;
