# EJC — Política HITL (Human-In-The-Loop)

Data: 2026-07-04 · Código: `backend/app/services/ai/core/hitl_policy.py`, `backend/app/models/ai_log.py`.

## 1. Regra central

**Toda resposta jurídica gerada por IA é RASCUNHO.** Nenhuma saída é apresentada como definitiva; o advogado responsável revisa antes de qualquer uso (vedação OAB de resposta jurídica "final"). `hitl_policy.aplicar` (hitl_policy.py:15-26) carimba o resultado padronizado do orchestrator:

- `is_rascunho = True` — **sempre**, sem exceção;
- `requer_revisao = AI_REQUIRE_HITL or revisao_obrigatoria`;
- `status_hitl = "gerado"`;
- `aviso_hitl = "Rascunho sujeito à revisão humana (HITL obrigatório — OAB)."` (hitl_policy.py:12).

O caminho legado `executar_tarefa_ia` devolve o mesmo carimbo (`is_rascunho: True, requer_revisao: True`, ai_gateway.py:443).

## 2. Ciclo de vida — `status_hitl` (models/ai_log.py:30-35)

```
gerado ──(revisão humana)──► revisado ──► aplicado
   │                                        (advogado aplicou ao caso/peça)
   └────────────────────────► descartado
```

| Status | Significado |
|---|---|
| `gerado` | IA respondeu; ninguém revisou (default de todo AILog, ai_log.py:66) |
| `revisado` | Humano revisou o conteúdo |
| `aplicado` | Advogado aplicou ao caso/peça |
| `descartado` | Rejeitado |

Cada transição grava `revisado_por` e `revisado_em` (ai_log.py:67-68).

## 3. Onde o usuário revisa

- **`PATCH /api/ai/logs/{log_id}/hitl`** (routers/ai.py:123-141): atualiza `log.status_hitl = AIStatusHITL(req.status)` + revisor/timestamp; listagem dos logs com status em `GET /api/ai/logs` (ai.py:114).
- **IA Defensiva**: `GET /api/ia-defensiva/historico` (por caso; não-sócios só veem os próprios logs, ia_defensiva.py:110-112) e `PATCH /api/ia-defensiva/historico/{log_id}/status` (ia_defensiva.py:138-156) — exige ser o autor ou role ≥ socio.
- **Dashboards**: `/api/ia-saude/dashboard` agrega `por_status_hitl` (ia_saude.py:51-62); `/api/ia-governanca` mede pendências (`status_hitl == "gerado"`, ia_governanca.py:385) e aproveitamento (`revisado/aplicado`, ia_governanca.py:247).

O contrato desses campos é carimbado no backend por `hitl_policy.aplicar()` (services/ai/core/hitl_policy.py:15-26), que injeta `is_rascunho`, `requer_revisao`, `status_hitl` e `aviso_hitl` em toda resposta do núcleo; o `log_id` acompanha a resposta e é o que o cliente usa para a revisão. **Não há client tipado no frontend**: `frontend/src/lib/aiCore.ts` foi removido em 1befdf0 (nunca teve consumidor) e as telas seguem consumindo os endpoints legados de IA — ver a pendência "Núcleo de IA sem consumidor no frontend" em docs/HIGIENIZACAO_BACKLOG_FRONTEND.md.

## 4. `AI_REQUIRE_HITL` (core/config.py:89)

Default `true`. Controla apenas a exigência de revisão FORMAL (`requer_revisao`); existe para ambientes de teste — em produção permanece `true`. Mesmo com `AI_REQUIRE_HITL=false`, `is_rascunho` continua `True` (hitl_policy.py:17-23) e o rótulo de rascunho é inegociável. A flag também é espelhada em `PolicyDecision.requer_hitl` (provider_policy.py:121) e exposta em `/ai/core/status` como `hitl_obrigatorio` (ai_core.py:195).

## 5. `revisao_obrigatoria` — gatilhos automáticos (response_validator.py:38-99)

Independente da flag global, a revisão torna-se obrigatória quando o validador de resposta detecta:

1. **Citações não confirmadas** na base oficial (citation_check por lookup exato) — alerta "verificação manual obrigatória (OAB)" (linhas 69-74); falha da própria verificação também obriga revisão (linhas 62-68);
2. **Possível promessa de resultado** (vedação OAB) — trechos detectados viram alerta, o texto nunca é reescrito (linhas 76-84);
3. **Sem base verificável** — tarefa que exige fonte sem nenhuma fonte RAG nem citação confirmada; resposta prefixada com "SEM BASE VERIFICÁVEL" (linhas 86-92).

`revisao_obrigatoria=True` força `requer_revisao=True` no carimbo final (hitl_policy.py:23), e os `alertas` acompanham a resposta para orientar o revisor.

## 6. Casos com HITL reforçado

- **LegalWritingAgent** (minutas/peças): `exige_fonte=True` + `validate_citations` no pipeline — peça sem citação confirmada nunca sai sem alerta (agent_registry.py:67-76).
- **JurimetryAgent**: prompt trata cenários como hipóteses estatísticas, nunca promessa (system_prompts/__init__.py:51); promessa detectada dispara revisão.
- **RepairAgent**: além do HITL da resposta, as skills de patch não têm handler — aplicação/rollback de código exige autorização humana explícita fora do núcleo (skill_registry.py:186-197).
- **ClientCommunicationAgent**: o texto é rascunho que o advogado revisa antes do envio ao cliente (system_prompts/__init__.py:54).

## 7. Auditoria do ciclo

Todo item revisável nasce de um AILog (ver `EJC_AI_COST_AND_AUDIT_POLICY.md`); a gravação é obrigatória no núcleo — erro de log propaga e a resposta não é entregue (orchestrator.py:152-169; ai_guard.py:53-57). Skill correspondente: `mark_as_draft` (skill_registry.py:144-146).
