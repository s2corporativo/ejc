-- BUG-09 — Merge de usuário duplicado (reatribuição + soft-deactivate)
-- PRINCIPAL = af6e457a (Dr. Clovis, admin@)  |  DUPLICADO = f23aeeb8 (clovis@)
-- Reatribui todas as referências existentes e DESATIVA (soft) a conta duplicada.
-- NÃO faz DELETE físico. Idempotente. Rodar após backup.
DO $$
DECLARE
  prin constant text := 'af6e457a-9e72-45bd-b578-c4d345925e51';
  dup  constant text := 'f23aeeb8-9479-4d93-bcaa-cb25e4c6d182';
  pairs text[][] := ARRAY[
    ['ai_logs','user_id'],['ai_logs','revisado_por'],['audit_logs','user_id'],
    ['atendimentos','advogado_responsavel_id'],['atendimentos','created_by'],
    ['cases','advogado_responsavel_id'],['cases','advogado_auxiliar_id'],
    ['case_movimentos','created_by'],['case_partes','created_by'],
    ['bank_analyses','created_by'],['centro_custos','created_by'],
    ['checklist_templates','created_by'],['case_checklists','created_by'],['case_checklist_items','concluido_por'],
    ['clients','responsavel_id'],
    ['contratos_societarios','created_by'],['contrato_historico','alterado_por'],
    ['socios','user_id'],['socios','aprovado_por'],['socios','created_by'],
    ['data_rooms','created_by'],['data_room_arquivos','adicionado_por'],['data_room_links','criado_por'],
    ['deadlines','responsavel_id'],['deadlines','ciencia_confirmada_por'],['diario_oficial_keywords','created_by'],
    ['djen_comunicacoes','advogado_id'],['djen_comunicacoes','processada_por'],
    ['dossies_estrategicos','gerado_por'],['dossies_estrategicos','aprovado_por'],
    ['legal_docs','created_by'],['legal_docs','revisor_id'],['jurisprudencias_internas','created_by'],
    ['prompts_juridicos','created_by'],['teses','created_by'],['tese_caso_links','created_by'],
    ['notifications','user_id'],['push_subscriptions','user_id'],['password_reset_tokens','user_id'],
    ['user_known_ips','user_id'],['refresh_tokens','user_id'],
    ['signature_requests','criado_por'],['suspensoes_tribunal','created_by'],
    ['tasks','responsavel_id'],['tasks','criado_por'],['doc_templates','created_by'],['time_entries','user_id'],
    ['wiki_paginas','atualizado_por'],['workflow_templates','created_by'],['workflow_etapas','created_by'],
    ['case_workflows','responsavel_id'],['workflow_historico','created_by']
  ];
  r text[];
  n integer;
BEGIN
  FOREACH r SLICE 1 IN ARRAY pairs LOOP
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name=r[1] AND column_name=r[2]) THEN
      EXECUTE format('UPDATE %I SET %I = %L WHERE %I = %L', r[1], r[2], prin, r[2], dup);
      GET DIAGNOSTICS n = ROW_COUNT;
      IF n > 0 THEN RAISE NOTICE 'reatribuído %.% -> % linhas', r[1], r[2], n; END IF;
    END IF;
  END LOOP;

  -- Soft-deactivate da conta duplicada (reversível; sem DELETE)
  UPDATE users
     SET is_active = false, deleted_at = now(), updated_at = now()
   WHERE id = dup;
  RAISE NOTICE 'conta duplicada % desativada (soft)', dup;
END $$;

-- Verificação
SELECT id, full_name, email, is_active, deleted_at IS NOT NULL AS soft_deleted
  FROM users WHERE id IN ('af6e457a-9e72-45bd-b578-c4d345925e51','f23aeeb8-9479-4d93-bcaa-cb25e4c6d182');
