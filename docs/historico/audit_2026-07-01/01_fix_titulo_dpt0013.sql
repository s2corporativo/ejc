-- BUG-03 — Correção pontual do título com JSON bruto da IA (caso DPT-2026-0013)
-- Só afeta 1 linha. Título neutro e honesto (não inventar assunto).
-- Rodar em produção somente após backup.
BEGIN;
UPDATE cases
   SET titulo = '[Revisar] Caso importado por IA — DPT-2026-0013',
       updated_at = now()
 WHERE numero_interno = 'DPT-2026-0013'
   AND titulo LIKE '%json%';
-- Confirmação:
SELECT numero_interno, titulo FROM cases WHERE numero_interno = 'DPT-2026-0013';
COMMIT;
