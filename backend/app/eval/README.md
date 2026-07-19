# Avaliação do RAG / IA jurídica (harness O-4)

Ciclo **eval-driven**: meça o baseline **antes** de mudar qualquer coisa
(reranker, embedding, prompt, threshold), depois itere medindo cada passo.
Sem régua, toda melhoria é aposta.

> Três gold sets, mesma filosofia:
> - **RAG** (`run_eval.py`, este documento): mede o *retrieval* e a resposta.
> - **Trajetória do agente** (`agent_trajectory.py`, seção 6): mede as *decisões*
>   do loop de tool-use (qual tool chamou, se fundamentou, se respeitou HITL/leitura
>   e o orçamento). É OFFLINE — o LLM é mockado, sem rede/banco/Redis.
> - **Peças** (`gold_set_pecas.jsonl`, seção 7): casos curados para avaliar o
>   pipeline de geração de peças (incl. o laço de auto-crítica das Duas IAs).

## 1. Monte o gold set

Copie `gold_set.example.jsonl` para `gold_set.jsonl` e cresça para **50–150 casos
reais** (pseudonimizados), cobrindo as áreas de atuação. Cada linha é um JSON:

```json
{"id": "trab-001", "area": "trabalhista",
 "query": "prazo prescricional para verbas rescisórias",
 "expected_titulos": ["CLT art. 11", "Súmula 308 TST"],
 "expected_categorias": ["legislacao", "sumula"],
 "expected_citacoes": ["Súmula 308 do TST"],
 "notes": "referência humana"}
```

O gold set é o ativo mais valioso do processo — só o escritório o produz.

## 2. Rode

Dentro do backend, com `DATABASE_URL` no banco a avaliar:

```bash
# Só retrieval (rápido, determinístico) — mede hit@k / precision / recall / MRR
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6

# Completo — roda a IA e mede alucinação de citação + groundedness (LLM-judge)
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6 --full --judge

# Baseline para diff entre execuções
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --out baseline.json
```

## 3. Métricas

| Métrica | O que mede | De onde vem |
|---|---|---|
| `hit@k`, `precision@k`, `recall@k`, `MRR` | o retrieval trouxe as fontes certas? | `buscar_contexto_rag` vs `expected_titulos` |
| taxa de citações não confirmadas | alucinação de jurisprudência | gate `citation_check` (`--full`) |
| groundedness | a resposta se apoia no contexto? | LLM-as-judge Haiku (`--judge`) |

Métricas de baseline **imediato** que já existem sem gold set: a taxa de citações
não confirmadas (AILog) e a **nota de robustez** das Duas IAs.

## 4. Iteração recomendada (roteiro da auditoria)

1. **Baseline** com o pipeline atual.
2. **Reranker** (O-1, já implementado) → ligue `RAG_RERANK_ENABLED` e compare.
3. **BM25/FTS** (A-3) → migration 095 + `RAG_FTS_ENABLED=true` → compare.
4. **Embedding** (O-2) → migration 096 + reindex + compare recall.
5. **HyDE** (O-6) → `RAG_HYDE_ENABLED=true` → compare recall.
6. **FIRAC / extended thinking** (O-3) → compare groundedness/alucinação.

Uma variável por vez, sempre medindo.

## 5. CI (regressão)

Adicione ao pipeline um job que roda o gold set e barra queda:

```bash
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6 --min-recall 0.7
```

> Ferramentas externas complementares: **RAGAS** / **DeepEval** (faithfulness,
> context precision/recall), **promptfoo** (comparar prompts/modelos), e os
> benchmarks PT-BR **OAB-Bench** / **Magis-Bench** / **LegalBench-BR** para
> calibrar o teto de qualidade.

## 6. Eval de TRAJETÓRIA do agente (loop de tool-use)

O módulo agêntico (`app/services/ai/agent/loop.py`) **decide → chama ferramenta →
lê o resultado → decide de novo**. O que importa não é só a resposta final, mas a
**trajetória**. Este harness roda o agente REAL com o **LLM mockado** (roteiro de
tool-use por cenário — sem rede, LLM, banco ou Redis) e mede 4 coisas:

| Métrica | O que mede | De onde vem |
|---|---|---|
| escolha de ferramenta | chamou a tool certa para a intenção? | `passos[].ferramentas` vs `ferramenta_esperada` |
| fundamentação/fonte | a resposta que afirma tese cita fonte? | detector local `_tem_fonte` (o gate real de citações roda no loop) |
| HITL / modo leitura | write-tool pausa (não executa sem aprovação); em `apenas_leitura` é bloqueada | `status`/`REGISTRY.executar`/evento `ferramenta_bloqueada` |
| orçamento | respeita `max_steps`/tokens/custo; encerra no teto com aviso | `passos` vs `max_steps` + alertas |

Como o LLM é mockado (espelha o `loop_env` de `tests/test_agente_ia.py`): cada
cenário do gold set traz `turnos`, o roteiro de respostas de tool-use que
substitui `ai_gateway.chat_agentico`; as demais bordas do loop (ownership,
entidades, AILog, gate de citações, store HITL, `REGISTRY.executar`) são fakes em
memória. O loop `rodar_agente` é exercitado ponta a ponta.

```bash
# Roda o gold set embarcado (offline — NÃO precisa de DATABASE_URL)
python -m app.eval.agent_trajectory

# Gate de regressão para CI (falha se cair a escolha de tool ou surgir violação HITL)
python -m app.eval.agent_trajectory --min-tool 1.0 --max-violacoes-hitl 0

# Baseline para diff
python -m app.eval.agent_trajectory --out traj.json
```

Gold set: `agent_scenarios.jsonl` (uma linha = um cenário FICTÍCIO, sem PII).
Campos: `intencao`, `mensagem`, `ferramenta_esperada`, `espera_fonte`,
`hitl` (`nenhum|pausa|escrita_aprovada|bloqueia_leitura`), `orcamento` (`ok|estoura`),
`apenas_leitura`, `aprovar_escrita`, `orcamento_override`, `tool_result`, `turnos`.
Cresça-o cobrindo as intenções reais do escritório. Teste offline determinístico:
`tests/test_eval_agent_trajectory.py`.

## 7. Gold set de PEÇAS (pipeline de geração + auto-crítica)

Scaffold pronto para o escritório preencher:

- **Template comentado**: `gold_set_pecas.template.json` — todos os campos de um
  caso (`id`, `area`, `ficticio`, `fatos`, `pedidos`, `tipo_peca_esperado`,
  `teses_esperadas`, `jurisprudencia_esperada`, `criterios`, `notes`).
- **Exemplos FICTÍCIOS**: `gold_set_pecas.example.jsonl` — 3 casos 100% sintéticos
  (`ficticio: true`), com jurisprudência **placeholder** (`SUMULA-FICTICIA-XXX`).
  Servem só para demonstrar o formato — **nunca** copie os placeholders (nem
  qualquer citação não conferida) para o gold set real.

### Curadoria (quem produz é o escritório)

1. Copie o formato dos exemplos para `gold_set_pecas.jsonl` (uma linha JSON por caso).
2. **Pseudonimize tudo** (LGPD): troque nomes por `[CLIENTE_1]`/`[EMPRESA_1]`,
   remova CPF/endereços/valores identificáveis ANTES de gravar.
3. Em `jurisprudencia_esperada`, liste **apenas referências reais conferidas na
   fonte oficial** (STF/STJ/TST/planalto). Jurisprudência inventada é proibida —
   inclusive nos exemplos, onde só o placeholder explícito `SUMULA-FICTICIA-XXX` é aceito.
4. Meta: **50–150 casos reais pseudonimizados** cobrindo as áreas de atuação;
   comece pelos tipos de peça mais gerados (petição inicial, contestação, RO).
5. Marque `ficticio: false` nos casos reais pseudonimizados.

### Como rodar

```bash
# Smoke (offline, sem banco/LLM): valida o FORMATO de TODOS os gold sets *.jsonl
python -m app.eval.run_eval --smoke

# Retrieval sobre o gold set de RAG (precisa de DATABASE_URL)
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6
```

O CI (`.github/workflows/ci.yml`, job `eval-smoke`) roda `--smoke` +
`agent_trajectory` em modo **não bloqueante** (`continue-on-error`) — vira gate
bloqueante quando o gold set real existir e o baseline estiver estabelecido.
