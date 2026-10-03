-- BUG-22 — Normalizar nome do modelo de IA nos logs existentes
-- Padroniza para 'groq/llama-3.3-70b-versatile'. Rodar após backup.
BEGIN;
SELECT modelo, count(*) AS antes FROM ai_logs GROUP BY modelo ORDER BY 2 DESC;

UPDATE ai_logs
   SET modelo = 'groq/llama-3.3-70b-versatile'
 WHERE modelo = 'llama-3.3-70b-versatile';

SELECT modelo, count(*) AS depois FROM ai_logs GROUP BY modelo ORDER BY 2 DESC;
COMMIT;
