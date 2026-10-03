# Auditoria do Núcleo de IA — 03/10/2026

**Base auditada:** `main` @ `049fd6c`. **Método:** leitura de código do núcleo
(gateway, política de sanitização, pseudonimização, HITL, validador de resposta,
delimitador anti-injeção, orquestrador/agente, RAG, embeddings, rotas de IA),
sondas empíricas executadas contra o código real e execução das suítes de teste.
**Sem acesso a produção** (regra 9 do `CLAUDE.md`): nada aqui foi medido na VPS.

IDs `NIA-*`. Severidade: **P1** = vazamento/defeito com efeito real hoje;
**P2** = enfraquecimento condicionado a configuração ou cobertura parcial;
**P3** = consistência/robustez.

---

## 1. Resultado dos testes

| Execução | Ambiente | Resultado |
|---|---|---|
| Testes do núcleo de IA (245 arquivos: gateway, PII, HITL, RAG, agente, citações, provedores, legal brain…) | Linux, venv Python 3.11, `requirements.txt` | **2343 passed**, 118 skipped (db-level), 0 falhas |
| Testes db-level do núcleo de IA (`RUN_DB_TESTS=1`) | PostgreSQL 16.14 + pgvector local, `alembic upgrade head` do zero (head `170_djen_remove_unicidade_global`) | **107 passed**, 0 falhas |
| Suíte completa do backend (baseline `049fd6c`) | idem | 8033 passed, 482 skipped, **1 falha fora do núcleo de IA** (ver §4) |
| Todos os testes db-level do repositório (após a correção NIA-01) | PostgreSQL 16 + pgvector | **366 passed**, 0 falhas |
| `ruff check app` | ruff 0.6.9 | sem achados |

Leitura: os invariantes já cobertos por teste (kill-switch, fail-closed da
cadeia, barreira LGPD por provedor, LOCAL_COMPLETO, reidratação local,
AILog pseudonimizado, cache não persistindo PII, HITL, gate de citações,
RBAC/ownership/IDOR do agente) **estão íntegros**. Os achados abaixo estão onde
a suíte não alcançava.

## 2. Pontos verificados e conformes

- **Ponto único de saída:** nenhum import de SDK/provedor fora de
  `services/providers/` e `ai_gateway.py` (varredura por `anthropic|groq|openai`
  e por chamadas HTTP aos endpoints dos provedores).
- **Elegibilidade única** (`provider_registry`): `AI_ENABLED` e
  `AI_EXTERNAL_PROVIDERS_ALLOWED` valem para toda a cadeia; cadeia vazia é
  fail-closed (`SafeAIError`), sem fallback sintético para externo.
- **Claude só por solicitação explícita** (política de 20/09):
  `ANTHROPIC_AUTO_ROUTING_ENABLED=false` remove `anthropic` da cadeia automática;
  `CONFIGURACOES` por tarefa não usa `anthropic`.
- **Sigilo reforçado** (crimes sexuais/menores + `cases.sigilo_reforcado`):
  externos removidos da cadeia; sem local → bloqueio seguro em `chat()`,
  `executar_tarefa_ia()`, `chat_agentico()` e no loop do agente.
- **Barreira LGPD:** PII residual pula o provedor externo (`_ProviderPulado`);
  mapa de reidratação só em memória; AILog grava versão pseudonimizada
  (`@validates` em `resposta`, `prompt_sanitizado`, `critica_adversarial`).
- **Cache de resposta:** chaves de tarefa reversível/local recebem prefixo
  `ai:nocache:` (obter/gravar NO-OP).
- **HITL:** `is_rascunho=True` é incondicional; retomada de write-tool do agente
  vinculada a usuário/caso/papel, one-shot e fail-closed sem Redis.
- **RAG:** gate de governança fail-closed (pendente/bloqueado/recusado nunca
  entram), norma revogada excluída incondicionalmente, isolamento por
  cliente/caso; API pública de ingestão força `rag_status=pendente`.
- **Anti-injeção:** delimitador com token aleatório por chamada (`delimitador.py`).

## 3. Achados

### NIA-01 — P1 — Barreira de PII deixava formatos reais em claro (CORRIGIDO — #2003)

Sonda empírica sobre `sanitizar_pii`, `validar_sem_pii` e `pseudonimizar`
(caminho padrão do gateway para provedor externo). Todos os itens abaixo
chegavam **em claro** ao provedor externo e a 2ª barreira respondia
"sem PII residual" (ela reusa as mesmas entradas de `_PATTERNS`):

| Formato | Exemplo | Observação |
|---|---|---|
| **CNPJ alfanumérico** | `12.ABC.345/01DE-35` | IN RFB nº 2.229/2024; atribuição a partir de jul/2026 — já em circulação |
| CEP pontuado | `30.130-010` | forma usual dos Correios |
| CPF com espaços | `123 456 789 09` | cópia de formulário/OCR |
| Celular sem DDD | `99999-9999` | |
| RG com UF / rótulo "identidade" | `MG-12.345.678` | |
| Título de eleitor, PIS/PASEP/NIT | `título de eleitor 1234 5678 9012` | |
| Agência/conta bancária | `conta corrente 12345-6` | |

**Correção:** `_MatcherCNPJ` (numérico legado + alfanumérico; sem máscara oficial,
exige DV válido — algoritmo conferido contra o exemplo oficial da RFB e contra
CNPJ numérico válido); CPF com três espaços; CEP pontuado; RG com UF/rótulo; e
três padrões APPEND-ONLY (celular sem DDD, `[DOC_ID]`, `[DADOS_BANCARIOS]`)
incluídos na 2ª barreira e no mapa do pseudonimizador. Os índices 0–10
referenciados permanecem. Regressão: `tests/test_sanitizer_lacunas_auditoria_ia_20261003.py`
(41 casos, inclusive falsos positivos jurídicos comuns: intervalo de anos,
diploma legal, montante, súmula). Uma primeira versão do padrão de CPF mordia
cartão AmEx agrupado — pega pela suíte existente e corrigida antes do push.

### NIA-02 — P2 — Nomes parciais e não capitalizados escapam da pseudonimização (PARCIALMENTE CORRIGIDO — #2003; restante em #2001)

Sonda com `entidades={"cliente": ["Ana Paula Souza"], "parte_contraria": ["Banco Exemplo S.A."]}`:
- prenome isolado posterior (`Ana disse…`) segue em claro;
- forma abreviada da parte (`o Banco Exemplo cobrou`) segue em claro;
- nome em minúsculas (`o cliente joão da silva`) não é detectado pelo NER local;
- nomes com menos de 4 caracteres são ignorados por piso anti-falso-positivo.

Risco: reidentificação por combinação com os fatos do caso.

**Corrigido neste PR (formas seguras):** razão social sem sufixo societário
(`Banco Exemplo`) e prenome + último sobrenome (`Ana Souza`) recebem o MESMO
marcador da entidade, numa 2ª passada que roda depois de todos os nomes
completos (uma variante nunca morde o nome completo de outra entidade).
**Pendente de decisão do titular:** prenome ou sobrenome isolado e nomes em
minúsculas — "Vitória", "Rosa", "Glória" são palavras comuns do texto
jurídico; mascará-las degrada o prompt (teste de não regressão incluído).

### NIA-03 — P2 — `AI_REQUIRE_HITL=false` não é barrado no boot de produção (CORRIGIDO — #2006)

`hitl_policy.py` declara que a flag "existe apenas para ambientes de teste — em
produção permanece True", mas `_validar_seguranca_producao` não a verifica. Com
a flag desligada, `requer_revisao` cai para `False` (o rótulo `is_rascunho`
continua). É mudança de configuração (regra 8 → `security-auditor`). Proposta:
falhar o boot de produção com `AI_REQUIRE_HITL=false`.

### NIA-04 — P3 — `EMBEDDINGS_API_URL` não é restrito a host interno (CORRIGIDO — #2006)

Com `EMBEDDINGS_PROVIDER=http`, o texto integral (documentos de cliente) vai sem
sanitização e fora do kill-switch `AI_EXTERNAL_PROVIDERS_ALLOWED` para a URL
configurada. O default é interno (`http://embeddings:8010/embed`), mas nada
impede apontar para serviço externo. Proposta: validar host privado/compose no
boot ou submeter o provider `http` externo ao kill-switch.

### NIA-05 — P3 — `chat_agentico` não aplica o piso `reforcar_sigilo` da tarefa (CORRIGIDO — #2005)

`chat()` e `executar_tarefa_ia()` fazem `reforcar_sigilo(modo_para_task(task), modo)`;
`chat_agentico` só usa `modo_para_task` quando `modo_sanitizacao is None`. Hoje
sem efeito (o único chamador passa o modo do caso e usa `task_type="estrategia"`),
mas um chamador futuro que passe modo explícito com `task_type` sigiloso
perderia o piso. Proposta: alinhar ao contrato dos outros dois caminhos.

### NIA-06 — P3 — Cache ignora o modo efetivo informado pelo chamador (CORRIGIDO — #2005)

`ai_cache._tarefa_cacheavel` decide pela tarefa normalizada, não pelo modo
efetivo (`modo_sanitizacao` do caso). Só se materializa se
`AI_SANITIZATION_MODE_MAP` mapear a tarefa para `mascaramento` **e** o caso for
`LOCAL_COMPLETO`: a resposta local, em claro, seria gravada no Redis. Proposta:
incluir o modo efetivo na decisão de cacheabilidade.

### NIA-07 — P3 — Falha do grounding ao vivo não marca `revisao_obrigatoria` (CORRIGIDO — #2005)

Em `response_validator.validar`, a exceção da verificação de citações (passo 1)
marca `revisao_obrigatoria=True`; a do grounding (passo 1.5) só acrescenta alerta.
Proposta: tratar as duas indisponibilidades da mesma forma.

### NIA-08 — P3 — Formatos de PII ainda não cobertos (CORRIGIDO — #2003, exceto telefone fixo)

Corrigidos: placa Mercosul (`ABC1D23`) e antiga com rótulo (`placa ABC-1234`;
sem rótulo colidiria com `ISO-9001`), passaporte com rótulo e numeração
processual anterior ao padrão CNJ (`0024.12.345678-9`). Mantido fora:
telefone fixo sem DDD — a forma `\d{4}-\d{4}` colide com intervalo de anos.

## 3.1 Situação das correções (03/10/2026)

| Achado | Situação | PR |
|---|---|---|
| NIA-01 | Corrigido | #2003 |
| NIA-02 | Parcial: variantes seguras de nome; prenome isolado e minúsculas aguardam decisão do titular | #2003 / #2001 |
| NIA-03 | Corrigido (boot de produção recusa HITL desligado) | #2006 |
| NIA-04 | Corrigido (boot recusa embeddings HTTP externo; aprovado pelo `security-auditor` com ressalvas não bloqueantes) | #2006 |
| NIA-05 | Corrigido | #2005 |
| NIA-06 | Corrigido (cache de resposta fica na prática inativo nos modos default) | #2005 |
| NIA-07 | Corrigido | #2005 |
| NIA-08 | Corrigido, exceto telefone fixo sem DDD | #2003 |
| Teste do financeiro dependente da data | Corrigido | #2004 |

**Antes do deploy** (travas de boot do #2006): conferir o `.env` de produção
conforme `RUNBOOK_DEPLOY_MANUAL.md`, seção "Conferência pré-deploy das travas
de boot da IA".

## 4. Fora do escopo do núcleo de IA

- `tests/test_clientes_contrato_financeiro.py::test_socio_cria_entrada_parcelas_e_exito`
  falha na `main` @ `049fd6c` (comparação de `data_vencimento` das parcelas),
  reproduzido sem as alterações deste PR. Registrado na Issue #2002 e corrigido
  no #2004 (o teste fixava a data do dia em que foi escrito).

## 5. Limitações

- Sem acesso à VPS: configuração efetiva de produção (flags, chaves, provedor de
  embeddings) não foi verificada.
- Nenhuma chamada real a provedor externo foi feita; o comportamento dos
  provedores é coberto pelos testes com dublês já existentes.
- O Actions da organização segue indisponível; a evidência é a execução local acima.
