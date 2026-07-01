-- BUG-04 — Reconciliação de status RAG (NÃO re-embeda; os vetores já existem)
-- Marca como 'indexado' todo doc 'pendente' que já possui ao menos um chunk embeddado.
-- Idempotente. Rodar em produção após backup.
BEGIN;
SELECT status_indexacao, count(*) AS antes
  FROM knowledge_docs GROUP BY status_indexacao ORDER BY 2 DESC;

UPDATE knowledge_docs d
   SET status_indexacao = 'indexado',
       atualizado_em = now()
 WHERE d.status_indexacao = 'pendente'
   AND EXISTS (
     SELECT 1 FROM knowledge_chunks c
      WHERE c.doc_id = d.id AND c.embedding IS NOT NULL
   );

SELECT status_indexacao, count(*) AS depois
  FROM knowledge_docs GROUP BY status_indexacao ORDER BY 2 DESC;
-- Docs realmente sem chunk (deveria ser 0):
SELECT count(*) AS docs_sem_chunk
  FROM knowledge_docs d
 WHERE NOT EXISTS (SELECT 1 FROM knowledge_chunks c WHERE c.doc_id = d.id);
COMMIT;
