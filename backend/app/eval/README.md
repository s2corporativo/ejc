# Avaliação do RAG / IA jurídica (harness O-4)

Ciclo **eval-driven**: meça o baseline **antes** de mudar qualquer coisa
(reranker, embedding, prompt, threshold), depois itere medindo cada passo.
Sem régua, toda melhoria é aposta.

> Quatro gold sets, mesma filosofia:
> - **Capacidades** (`run_gold_ia.py`, seção 8): mede as CINCO portas de IA
>   (`analisar`, `redigir`, `resumir`, `conversar`, `extrair`) — tem modo
>   `--mock` offline para CI. Casos ainda CANDIDATOS (sem atestação humana).
> - **RAG** (`run_eval.py`, este documento): mede o *retrieval* e a resposta.
> - **Trajetória do agente** (`agent_trajectory.py`, seção 6): mede as *decisões*
>   do loop de tool-use (qual tool chamou, se fundamentou, se respeitou HITL/leitura
>   e o orçamento). É OFFLINE — o LLM é mockado, sem rede/banco/Redis.
> - **Peças** (`gold_set_pecas.jsonl`, seção 7): casos curados para avaliar o
>   pipeline de geração de peças (incl. o laço de auto-crítica das Duas IAs).

### Benchmark provisório por proveniência

Enquanto o gold humano não está disponível, `benchmarks/rag_source_curated.jsonl`
contém 14 fichas da Biblioteca Jurídica que têm URL oficial, snapshot local,
data de verificação e `gerado_por_IA=false`. Ele serve para medir recuperação de
fontes versionadas e **não conta como gold jurídico**, porque não contém casos
reais atestados. Regenere-o somente a partir do acervo versionado:

```bash
python -m app.eval.build_source_benchmark
python -m app.eval.run_eval \
  --gold app/eval/benchmarks/rag_source_curated.jsonl --k 6 \
  --out /tmp/rag-source-baseline.json
```

Resultado `recall=0` acompanhado de falha de conexão, banco ou embedding é
falha operacional, não evidência de baixa qualidade jurídica.

### Homologação inicial sem casos próprios

`research_acceptance.synthetic.example.jsonl` contém 20 perguntas explicitamente
sintéticas, distribuídas entre consumidor, trabalhista, cível/processual, penal
e tributário. Elas testam se a pesquisa retorna autoridade, exige prova e
documentos, reconhece lacunas e mantém revisão humana. Não são casos do
escritório e não contam como gold set.

```bash
python -m app.eval.run_research_acceptance
```

Para verificar mudanças nas páginas oficiais em produção, execute o monitor
determinístico e persista o manifesto fora do repositório:

```bash
python -m app.eval.check_public_sources \
  --out /var/lib/ejc/fontes-publicas-manifesto.json
```

Código de saída `2` significa alteração ou erro de consulta e exige
revalidação humana; o monitor nunca promove automaticamente uma fonte nova a
fundamento apto para citação.

## 1. Monte o gold set

Consulte também [`GUIA_CURADORIA_GOLD_SET.md`](GUIA_CURADORIA_GOLD_SET.md),
[`GOLD_SET_GOVERNANCE.md`](GOLD_SET_GOVERNANCE.md) e
[`gold_set.template.json`](gold_set.template.json).

Use `gold_set.example.jsonl` apenas para entender o formato sintético. Para o
corpus real, parta de `gold_set.template.json` e crie `gold_set.jsonl`, crescendo
para **50–150 casos reais pseudonimizados**, cobrindo as áreas de atuação e os
cenários `normal`, `fronteira` e `excecao`. Cada linha é um JSON independente.
Exemplo resumido de um caso real (os valores de curadoria são ilustrativos):

```json
{"id":"trab-001","area":"trabalhista","cenario":"normal","ficticio":false,
 "query":"prazo prescricional para verbas rescisórias",
 "expected_titulos":["CLT art. 11","Súmula 308 TST"],
 "expected_categorias":["legislacao","sumula"],
 "expected_citacoes":["Súmula 308 do TST"],
 "curadoria":{"curador":"advogado-area","revisor":"revisor-independente",
 "revisado_em":"YYYY-MM-DD","vigencia_conferida_em":"YYYY-MM-DD",
 "fontes_oficiais":[{"titulo":"Fonte oficial","url":"https://dominio-oficial.gov.br/caminho",
 "consultada_em":"YYYY-MM-DD","identificador_versao":"norma/julgado + versão ou data do texto conferido"}]},
 "notes":"referência humana sem PII"}
```

Regras bloqueantes do corpus real:

- curador identificado; revisor opcional e pode coincidir com o curador;
- consulta da fonte e conferência de vigência não podem ser posteriores à revisão;
- toda fonte oficial precisa identificar a versão revisada por `identificador_versao` ou `hash_sha256`;
- o sanitizer de PII examina todo o payload e falha fechado se ficar indisponível;
- IDs são únicos em todo o acervo, mesmo quando repartido em vários arquivos;
- RAG exige `query` + `expected_titulos`; peças exigem `fatos`, `tipo_peca_esperado`, `teses_esperadas` e `criterios`;
- placeholders/fonte fictícia são proibidos em `expected_citacoes` e `jurisprudencia_esperada` de casos reais.

O gold set é o ativo mais valioso do processo — só o escritório o produz.

### Coleta verificável das fontes (`coleta_fontes.py`)

Preencher `fontes_oficiais` à mão é onde a curadoria erra: artigo transcrito de
memória, URL que mudou, versão que não se reconstrói. `coleta_fontes.py` faz só
a parte mecânica — baixa da fonte oficial, fixa o `sha256` dos bytes recebidos,
extrai o texto literal dos artigos pedidos e registra a data da consulta.

```bash
cd backend
python -m app.eval.coleta_fontes --listar          # o que está registrado
python -m app.eval.coleta_fontes                   # coleta tudo
python -m app.eval.coleta_fontes --apelido cdc     # só uma fonte
```

Registro em `fontes_registro.json`; resultado em `fontes_oficiais.json`. Só entra
no registro URL cujo **conteúdo** foi conferido — responder 200 não basta, e essa
regra é do código: cada fonte declara em `verificar_texto` os trechos que o
documento precisa conter (número e data da norma), e a coleta recusa a fonte se
faltar qualquer um. Uma URL que responde 200 servindo outra lei falha alto em vez
de entrar calada no acervo.

**A ferramenta não cura.** Não escolhe tese, não escreve gabarito, não preenche
`vigencia_conferida_em` e não assina `curador`. Esses campos saem `null` de
propósito: uma ferramenta que os preenchesse deixaria o gate verde sem que
ninguém tivesse conferido nada.

### Publicação original não prova vigência

O Planalto (texto compilado) está inacessível de parte dos ambientes de
execução. `camara.leg.br` e `senado.leg.br` são oficiais e alcançáveis, mas
grande parte do acervo da Câmara é **publicação original** — prova o texto como
publicado, não o texto em vigor. Cada fonte carrega `natureza` e
`prova_vigencia`, e a classificação falha fechada: sem sinal inequívoco na URL,
`prova_vigencia` é falso.

O acervo penal mostra por que isso não é formalidade. Na publicação original do
Código Penal de 1940:

| Artigo | Publicação original de 1940 | Código Penal hoje |
|---|---|---|
| art. 14 | crime impossível | consumação e tentativa |
| art. 33 | doença mental superveniente | regimes de cumprimento de pena |
| art. 59 | revogação do sursis | circunstâncias judiciais (dosimetria) |
| art. 155 | multa "de quinhentos mil réis a dez contos de réis" | multa em dias-multa |

A Lei 7.209/1984 renumerou a Parte Geral inteira. Um gold set penal montado
sobre essa fonte erraria **o número do artigo**, não só a redação — com fonte
oficial, autêntica e íntegra. Confira em texto compilado antes de preencher
`vigencia_conferida_em`.

## 2. Rode

Dentro do backend, com `DATABASE_URL` no banco a avaliar:

```bash
# Só retrieval (rápido, determinístico) — mede hit@k / precision / recall / MRR
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6

# Completo — roda a IA e mede alucinação de citação + groundedness (LLM-judge)
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6 --full --judge

# Baseline para diff entre execuções
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --out baseline.json

# Comparação controlada de providers sobre a MESMA query e o MESMO contexto RAG
python -m app.eval.compare_providers \
  --gold app/eval/gold_set.jsonl \
  --providers anthropic,maritaca \
  --k 6 --judge --out comparacao.json
```

No comparador, fallbacks são registrados separadamente e **não entram nas
métricas do provider solicitado**. O comando não habilita providers nem altera o
roteamento de produção.

## 3. Métricas

| Métrica | O que mede | De onde vem |
|---|---|---|
| `hit@k`, `precision@k`, `recall@k`, `MRR` | o retrieval trouxe as fontes certas? | `buscar_contexto_rag` vs `expected_titulos` |
| taxa de citações não confirmadas | alucinação de jurisprudência | gate `citation_check` (`--full`) |
| groundedness | a resposta se apoia no contexto? | LLM-as-judge Haiku (`--judge`) |
| custo e latência por provider | eficiência comparativa | `compare_providers.py` |

Métricas de baseline **imediato** que já existem sem gold set: a taxa de citações
não confirmadas (AILog) e a **nota de robustez** das Duas IAs.

## 4. Iteração recomendada (roteiro da auditoria)

1. **Baseline** com o pipeline atual.
2. **Reranker** (O-1, já implementado) → ligue `RAG_RERANK_ENABLED` e compare.
3. **BM25/FTS** (A-3) → mantenha `RAG_FTS_ENABLED=false` até existir baseline
   jurídico real; depois ative de forma controlada e compare.
4. **Embedding** (O-2) → migration 096 + reindex + compare recall.
5. **HyDE** (O-6) → `RAG_HYDE_ENABLED=true` → compare recall.
6. **FIRAC / extended thinking** (O-3) → compare groundedness/alucinação.

Uma variável por vez, sempre medindo.

## 5. CI (regressão)

Adicione ao pipeline um job que roda o gold set e barra queda:

```bash
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6 --min-recall 0.7
```

### 5.1 Gate POR ÁREA (auditoria máxima 2026-07-26, achado AI-087)

Média global esconde a área ruim: um recall alto puxado por cível não diz **nada**
sobre penal ou trabalhista. Por isso o runner segmenta as métricas pela chave
`area` do gold set (bloco `== POR ÁREA ==` e campo `por_area` no JSON) e oferece
dois gates independentes do global:

```bash
# Falha se QUALQUER área crítica ficar abaixo do piso — ou se estiver ausente
# do gold set (cobertura zero não é aprovação).
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6 \
  --areas-obrigatorias penal,trabalhista,consumidor,tributario,ambiental \
  --min-recall-area 0.7
```

O modo offline (`--smoke`, o que roda hoje no CI) imprime a **cobertura por área**
dos gold sets reais — exemplos `*.example.*` não contam — e aceita o mesmo gate:

```bash
python -m app.eval.run_eval --smoke \
  --areas-obrigatorias penal,trabalhista --min-casos-area 10
```

A governança do corpus também pode exigir amplitude de cenários antes de chamar o
gate de institucional:

```bash
python -m app.eval.gold_governance --require-real \
  --areas penal,trabalhista,consumidor,tributario,ambiental --min-casos-area 10 \
  --cenarios normal,fronteira,excecao --min-casos-cenario 5 --min-total 100
```

> **Estado atual (honesto):** o repositório só tem gold sets de **exemplo**, então
> a cobertura real por área é **zero** e o gate acima falha de propósito se ligado.
> O mecanismo está pronto; o que falta é conteúdo — e conteúdo jurídico gold só
> vale com curadoria humana (owner por área, fonte, vigência, revisor). Ver
> `GUIA_CURADORIA_GOLD_SET.md`. Ligue o gate no `ci.yml` **na mesma entrega** em
> que a primeira área crítica ganhar gold set curado; até lá, a linha de cobertura
> no log do CI mantém a lacuna visível em vez de disfarçada.

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

# Gate de regressão para CI
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

- **Template comentado**: `gold_set_pecas.template.json` — inclui payload avaliável,
  classificação de cenário e a mesma trilha `curadoria` obrigatória do gold RAG;
- **Exemplos FICTÍCIOS**: `gold_set_pecas.example.jsonl` — casos 100% sintéticos.
  Servem só para demonstrar o formato. Placeholders de jurisprudência são
  tolerados apenas nos arquivos `.example.*` e são bloqueados em corpus real.

### Curadoria

1. Use `gold_set_pecas.template.json` como fonte do schema do caso real; os exemplos não são base para copiar metadados de proveniência.
2. Pseudonimize nomes, documentos, endereços e valores identificáveis.
3. Classifique `cenario` como `normal`, `fronteira` ou `excecao`.
4. Preencha `curadoria` com curador (revisor opcional), datas e fonte oficial; a fonte deve ter `identificador_versao` ou `hash_sha256`.
5. Liste apenas jurisprudência real conferida na fonte oficial.
6. Confirme que `fatos`, `tipo_peca_esperado`, `teses_esperadas` e `criterios` estão preenchidos.
7. Cresça para 50–150 casos pseudonimizados e marque `ficticio: false` somente nos casos reais revisados.

### Como rodar

```bash
python -m app.eval.gold_governance
python -m app.eval.run_eval --smoke
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6
```

O CI (`.github/workflows/ci.yml`, job `eval-smoke`) roda `--smoke` +
`agent_trajectory` em modo não bloqueante; torna-se gate bloqueante quando o gold
set real existir e o baseline estiver estabelecido.

## 8. Régua das CINCO CAPACIDADES (`run_gold_ia.py`) — item I7

Desde a unificação das portas de IA (item I1: `/ia/analisar`, `/ia/redigir`,
`/ia/resumir`, `/ia/conversar`, `/ia/extrair`), a pergunta "a IA melhorou?"
precisa de resposta **por capacidade**, não por endpoint. É o que esta régua faz.

- **Gold set**: `gold_set_ia_candidatos.jsonl` — 10 casos **100% fictícios**
  (`E2E-FICTICIO-*`), distribuídos em consumidor (4), cível (3), trabalhista (2)
  e família (1). Cada linha traz `entrada` (fatos + pergunta/pedido),
  `capacidade`, `area`, `criterios` (os pontos que a resposta tinha de
  enfrentar), `citacoes_esperadas_tipo` e `nao_deve_conter`.
- **Citação por TIPO, nunca por número**: o gold set exige *"artigo do CDC sobre
  vício do produto"*, não *"art. N"*. Número de súmula ou de artigo entra
  **depois**, pela mão do curador humano, conferido em fonte oficial — inventar
  numeração para "completar o gabarito" contamina a régua inteira.
- **Candidato ≠ atestado**: todos os casos são `status: "candidato"`,
  `atestado_por: null`. `gold_governance.py` os conta à parte
  (`candidatos_não_atestados`) e **não** os soma à cobertura por área; o
  relatório da régua repete o aviso. Enquanto ninguém atestar, o número compara
  execuções entre si e não certifica a qualidade jurídica da IA.

```bash
cd backend

# Modo MOCK — provedor falso determinístico. Roda em CI: sem rede, sem banco,
# sem chave de provedor. Mede o HARNESS, não a IA.
python -m app.eval.run_gold_ia --mock

# Gate de regressão (piso de score e tolerância zero a conteúdo proibido)
python -m app.eval.run_gold_ia --mock --min-score 0.5 --max-proibidos 0

# Modo REAL — gateway + LLM-juiz sobre os critérios + citation_check
python -m app.eval.run_gold_ia --juiz --out app/eval/relatorio_gold_ia.json
```

**Pontuação por caso** (0..1): `0.6 × cobertura dos critérios + 0.4 × cobertura
das citações por tipo` (sem citação esperada, o peso vai todo para os
critérios). Citação só conta quando a resposta traz **o assunto e o marcador da
fonte** (CDC, CLT, Código Civil, súmula, dispositivo constitucional…) — repetir a
tese não é fundamentar. **Conteúdo proibido zera o caso**: promessa de
resultado, valor certo de indenização ou dispensa da revisão humana não são
desconto de pontinho, são reprovação.

Saída em `relatorio_gold_ia.json`: score por caso (com os critérios *não*
enfrentados, que é o que o curador lê), agregado global, por área e por
capacidade, mais o bloco `governanca`. Teste offline do modo `--mock`:
`tests/test_gold_ia_regua.py`.
