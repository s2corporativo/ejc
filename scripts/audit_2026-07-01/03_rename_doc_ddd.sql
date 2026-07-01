-- BUG-18 — Documento com título inválido "ddd"
-- Renomeia para rótulo de revisão (não apaga). Rodar após backup.
BEGIN;
UPDATE documents
   SET titulo = '[Revisar] Documento sem título — 743ea7cb'
 WHERE id = '743ea7cb-f1b1-46a2-98a8-f30d0617a5d6'
   AND titulo = 'ddd';
SELECT id, titulo FROM documents WHERE id = '743ea7cb-f1b1-46a2-98a8-f30d0617a5d6';
COMMIT;
