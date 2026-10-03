# Auditoria — Legal Brain / raciocínio jurídico

- Data: 2026-10-02 · Branch `claude/blissful-darwin-nr2i2v`
- Método: leitura estática. **Nada foi executado, nenhum teste rodado, produção não acessada** (CLAUDE.md, regra 9). Achados "a reproduzir" exigem teste antes de correção.
- Escopo lido: `backend/app/services/legal_brain/*` (brain, contracts, issue_engine, research_loop, rag_research, evidence, precedent_validity, case_state_bridge, skill_contracts, skill_factory, shadow), `docs/ia/LEGAL_BRAIN_ARCHITECTURE.md`, `services/legal_case_orchestrator.py`, `routers/orquestrador.py`, `services/manus_{client,deep_reasoning}.py`, `routers/manus.py`, `scripts/legal_brain_audit.py`, cabeçalho de `app/eval/legal_bench.py`, trechos de dois testes. **Não lidos:** frontend, demais testes, corpo de `legal_bench`, `legal_graph` além do formato das relações.

## 1. Veredicto sobre a premissa

O pipeline "problema → classificação → plano → evidências → avaliação → teses → contraditório → validação → rascunho" **não existe como execução**. O código implementa uma **fundação determinística e dormente** (contratos, regras lexicais, planos estáticos, adaptador do RAG, máquina de estados de evidência), em linha com o documento de arquitetura (fundação sem migration/endpoint; shadow antes de runtime). Não há tese, contraditório nem rascunho no pacote; `brain.build_legal_brain_plan` devolve `deterministic` e `runtime_injected: False`. Não é defeito: é preciso **não apresentar** o módulo como capacidade em operação.

## 2. Conformidades (verificadas no código)

- Estados de evidência com tabela de transições; CONFIRMADO/VALIDADO_ADVOGADO exigem revisor e data (`evidence.py`).
- `case_state_bridge`: "comprovado/confirmado" só vira CONFIRMADO se `origin=="manual"` com revisor/data; senão INFERENCIA_IA.
- `skill_factory` nunca cria skill ATIVA; exige fonte oficial, `verified_at` e norma vigente.
- Vigência de precedente só é "verificada" com autoridade oficial normativa, status vigente, origem e data de verificação e sem inferência.
- Manus: kill-switch (`MANUS_ENABLED`), roteamento automático proibido, pseudonimização + verificação de resíduo de PII antes do envio, piso de sigilo reforçado, handle de tarefa assinado e vinculado ao usuário, ownership do caso, resultado marcado como exigindo revisão humana.
- Orquestrador de caso: ações de aprovação humana separadas das executáveis; ownership no router.

## 3. Achados

| # | Sev. | Conf. | Achado | Local |
|---|---|---|---|---|
| LB1 | A | Alta | **Manus fica fora de `ai_gateway`/`provider_policy`.** `ManusClient` usa `httpx` direto. Mitigado por flag, pseudonimização e sigilo, mas os controles são reimplementados à parte (a regra 3 do CLAUDE.md exige passar pelo gateway). Não verifiquei se há AILog do Manus (**a verificar**). Corrige também a afirmação "gateway único" do relatório de Inteligência (já ajustada). | `manus_client.py`, `manus_deep_reasoning.py` l.152-222 |
| LB2 | A | Média (a reproduzir) | **`precedent_validity` ignora `direcao` das relações do grafo.** Mapeia `tipo`→status e escolhe por prioridade (SUPERADA 100 … CONFIRMADA 40) sem distinguir `saida`/`entrada`. "A supera B" e "A é superado por B" podem produzir o mesmo status para o precedente consultado → precedente vigente marcado como superado, ou o inverso. | `precedent_validity.py` |
| LB3 | A | Alta (**reproduzido e corrigido** — ver §6) | **Divergência de `purpose` no plano de esclarecimento.** `rag_research` define `clarification_only` por `purpose == "clarificar_fatos"`, mas `build_clarification_plan` gera `purpose="saneamento_fatico"`. O teste do adaptador usa o primeiro valor; o teste da fundação afirma o segundo. O ramo "só esclarecer" nunca dispara para o plano real e a busca de RAG roda onde deveria pedir fatos. | `rag_research.py`; `research_loop.py`; `tests/test_legal_brain_{rag_adapter,foundation}.py` |
| LB4 | M | Alta | **Evidência nunca chega a "aderência fática".** `_record_from_rag` fixa `stance=None` e `factual_fit_reviewed=False`; nada no pacote os altera. A cobertura só prova "há fonte vigente", não que sustenta a tese. | `rag_research.py` |
| LB5 | M | Alta | **Cobertura de pesquisa é agregada, não por questão.** `evaluate_research_coverage` combina booleanos globais; uma questão sem fonte pode ser coberta pela fonte de outra. `max_cycles` é só campo do plano — não há laço que o aplique. | `research_loop.py` |
| LB6 | M | Alta | **Validação do advogado não é verificada.** `CaseAssertion` aceita qualquer string em `validated_by_user_id`/`validated_at`; não confere usuário existente, papel, vínculo ao caso nem autoria diferente do gerador. | `evidence.py` |
| LB7 | M | Alta | **Skills nativas nascem `ATIVA` sem fonte.** `_contract_from_native` usa `SkillStatus.ATIVA` com `source_refs=()`, o oposto da regra que o `skill_factory` impõe a skills novas. | `skill_contracts.py` |
| LB8 | M | Alta | **Classificação de questões é lexical** (6 regras de palavras/radicais, fallback `saneamento_inicial`): sem negação, sem área mista, sem confiança; falso positivo/negativo silencioso. | `issue_engine.py` |
| LB9 | M | Alta | **"Shadow" não é inerte e não mede nada.** `run_shadow_ai_task` chama `orchestrator.run` (custo, AILog, provedor reais) e anexa `legal_brain_shadow`; sem telemetria de divergência e sem chamadores. O critério de promoção do rollout fica sem dado. | `shadow.py` |
| LB10 | M | Média | **Orquestrador de caso deriva estado da existência de artefatos**, não da qualidade; rate limit por ação em memória (premissa de worker único). | `legal_case_orchestrator.py` |
| LB11 | B | Média | **Gold set/`legal_bench` sem curadoria declarada** nos trechos lidos; sem ele, nenhuma promoção shadow→runtime é defensável. | `app/eval/legal_bench.py` |

## 4. Plano

**Fase 0 (sem código de produção):** decidir destino do Manus (migrar para o gateway, ou manter isolado com política documentada); decidir se o Legal Brain segue como fundação ou ganha runtime.
**Fase 1 (correções pequenas, com teste de regressão):** LB3 (unificar `purpose` + teste que cubra o plano real); LB2 (usar `direcao` + testes das quatro combinações); LB7 (skills nativas sem fonte → status que não seja ATIVA, ou preencher `source_refs`).
**Fase 2:** LB6 (validar revisor: existência, papel, vínculo ao caso, ≠ gerador); LB5 (cobertura por questão; laço respeitando `max_cycles`); LB4 (campo de revisão de aderência com fluxo de advogado).
**Fase 3:** LB1 (Manus pelo gateway/política + AILog); LB9 (shadow com telemetria, execução sem custo ou amostrada).
**Fase 4:** LB8 (classificador com negação/confiança/multi-área, validado contra gold set); LB11 (gold set curado por advogado); LB10.
**Portões:** Fase 1 — `ruff check app` + `pytest tests/test_legal_brain_*`; demais — suíte completa uma vez antes do push; mudança em auth/permissões (LB6) exige `security-auditor`; qualquer coluna nova exige migration com reserva de número.

## 5. Limitações

Leitura estática; sem execução; AILog do Manus, frontend e `legal_bench` não verificados; achados LB2 e LB3 dependem de reprodução; a regra jurídica de cada status (superação/confirmação) não foi validada por fonte oficial — exige revisão de advogado.

## 6. Execução da Fase 1 (parcial)

- **LB3 — corrigido.** Teste de regressão com o plano real (`build_clarification_plan`) falhava antes da correção e passa depois (`rag_research.py`: `_CLARIFICATION_PURPOSES` aceita `saneamento_fatico` e o legado `clarificar_fatos`). Evidência: `pytest tests/test_legal_brain_*.py` → 50 passed; `ruff check app/services/legal_brain` limpo. Suíte completa **não** executada (alteração restrita ao pacote, sem banco/modelos/routers).
- **LB2 — decisão: manter o comportamento (conservador) e documentar.** Ignorar `direcao` nunca esconde alerta de superação (no máximo sinaliza a mais); condicioná-la sem convenção definida e revisada por advogado poderia gerar alerta a menos. Registrado na docstring de `evaluate_proposition_validity`. Reabrir apenas se o titular definir a convenção.
- **LB7 — decisão: manter `ATIVA` e documentar** no código que o status não implica fonte curada (`source_refs` vazio até curadoria oficial).
- **LB6 — endurecimento mínimo aplicado:** revisor ou data só com espaços em branco deixavam de ser rejeitados em `CaseAssertion`; agora são. Teste de regressão incluso. A verificação de usuário/papel/vínculo ao caso **não** foi feita: o pacote é dormente e puro (sem sessão de banco nem chamadores); implementá-la agora seria especulativa e tocaria permissões (exigiria `security-auditor`). Fica para o momento em que houver runtime.
- **LB4/LB5/LB1/LB8–LB11:** mantidos como backlog; nenhum tem consumidor em produção hoje, então não há risco ativo — priorizar quando o runtime for decidido.
- Evidência final: `pytest tests/test_legal_brain_*.py` → 51 passed; suíte completa (antes do último ajuste) 7947 passed; `ruff check app` limpo.
