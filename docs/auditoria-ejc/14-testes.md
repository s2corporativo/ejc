# 14 — Testes (Fase 14)

## 1. Execução real — números brutos

### Backend

```
cd backend && python -m pytest -q --timeout=300
4463 passed, 166 skipped, 15 warnings, 77 subtests passed in 79.14s
```

| Métrica | Valor real |
|---|---|
| Arquivos de teste | 342 |
| Funções `test_*` (AST, pré-parametrização) | 3 472 |
| **Testes executados** | **4 629** |
| **Passaram** | **4 463** |
| **Falharam** | **0** |
| Erros de coleta | **0** |
| Pulados | **166** |

`ruff check app --output-format=concise` → **All checks passed!**

**Os 166 skips, com motivo:** 161 por `RUN_DB_TESTS=1`/Postgres ausente · 2 por `tesseract`
ausente (`test_ocr_service.py:93,98`) · 2 por `SCHEMA_CHECK_DATABASE_URL` · 1 por
`REQUIRE_2FA_ROLES` sobrescrito por env. **São skips declarados, com motivo acionável — não é
skip-para-passar.** No CI os DB-level rodam (`ci.yml:54`, serviço `pgvector/pgvector:pg16`) e o
tesseract está instalado.

**Registro obrigatório — `pip install -r requirements.txt` falha no interpretador do sistema:**

```
ERROR: Failed building wheel for http-ece
AttributeError: install_layout. Did you mean: 'install_platlib'?
```

Causa: setuptools Debian-patched. Contornado com venv limpo (setuptools 83.0.0), aí instala tudo.
Isto **reproduz o risco que `backend/requirements.txt:63-76` documenta** — mas o comentário culpa
`aiohttp`/`pywebpush`, quando o quebra-cabeça real é o **`http-ece` com setuptools velho**.

### Frontend

```
npm test           → 54 arquivos, 343 testes, 343 passed, 0 failed (63,6s)
npm run lint       → tsc --noEmit, exit 0
npm run format:check → All matched files use Prettier code style!
```

> **A suíte, como está, é verde de verdade — não há falha escondida a reportar.**

## 2. Qualidade dos testes

### 2.1 Estatística estrutural (342 arquivos)

| Padrão | Arquivos | % |
|---|---|---|
| Classe fake local (`_FakeDB`, `_Res`) | 101 | 29,5 % |
| Gate `RUN_DB_TESTS` (Postgres real) | 43 | 12,6 % |
| Sufixo `*_dblevel.py` | 35 | 10,2 % |
| `monkeypatch` / `unittest.mock` | 150 | 43,9 % |
| `TestClient` (rota real montada) | 29 | 8,5 % |
| `app.dependency_overrides` | 23 | 6,7 % |
| **`assert_called` / `.call_count` (valida só o mock)** | **0** | **0 %** |

> **O zero da última linha é o achado mais importante desta fase, e é positivo:** a suíte **não
> tem** a patologia clássica de "assegurar que um mock foi chamado". Os fakes são fixtures de dados
> (fila de `execute()` que devolve objetos), **não espiões** — o que está sob asserção é sempre o
> retorno da função de produção.

### 2.2 Amostra classificada — 15 arquivos dos domínios centrais

| Arquivo | Domínio | Classificação |
|---|---|---|
| `test_casos_dblevel.py` | casos | **REAL (persistência)** — 4 INSERT + `select()` de releitura pós-handler |
| `test_idor_criacao_caso_dblevel.py` | casos/IDOR | **REAL (segurança)** — demonstra o vetor com `pode_ver_cliente` real. O melhor teste da suíte |
| `test_clients_sigilo_titularidade_dblevel.py` | clientes | **REAL** — prova 404 (não 403) para advogado não-dono e CPF **mascarado** no conflito |
| `test_client_pii_cutover_dblevel.py` | clientes/LGPD | **REAL** — grava cifrado, relê pelo índice HMAC cego |
| `test_prazos_vencidos_dblevel.py` | prazos | **REAL** — job roda 2× e assere que a 2ª não re-notifica |
| `test_deadline_calculator.py:16-52` | prazos | **REAL (função pura)** — Páscoa Gauss 2024/25/26, Corpus Christi, dias úteis |
| `test_documento_service.py` | documentos | **REAL (contrato de segurança)** — captura o prompt entregue ao gateway e assere CPF/CNJ **mascarados** |
| `test_data_room_ownership_pente_fino.py` | documentos | **REAL (lógica)** — `_gate_room`, `_validar_vinculos_room` de verdade |
| `test_motor_peca.py` (558 l.) | peças | **REAL** — rotas montadas; assere que `/analisar` nunca cria `Deadline` |
| `test_peca_versionamento.py` | peças | **MISTO** — a atomicidade real só é provada com Postgres (`:216`) |
| `test_honorarios_oab_parse.py` (41 l.) | honorários | **REAL, mas trivial** — testa só `_parse_json` |
| `test_fee_proposal.py` (690 l.) | financeiro | **REAL (lógica)** — imutabilidade, versionamento max+1, HITL com `AuditLog` |
| `test_bloco6_auth.py` | auth | **REAL (integração)** — `/auth/login` real, incl. o wrapper slowapi |
| `test_security_p0_rbac_pii.py:34-75` | RBAC | **REAL (matriz)** — parametrizado por papel, esperando 403 |
| `test_rag_isolation*.py` | IA/RAG | **MISTO → REAL no CI** |

**Nenhum arquivo da amostra é TESTE DE MOCK e nenhum é TESTE VAZIO.** A qualidade média é acima do
que o volume de fakes sugeria.

### 2.3 Testes que passariam se a implementação fosse removida

**(a) 32 asserções sobre o texto do código-fonte (`inspect.getsource`)** — não executam o alvo:

```python
# tests/test_signatures_ownership.py:13-23
src = inspect.getsource(sig.listar)
assert "SignatureRequest.client_id == cu.client_id" in src
```

Passa se a string estiver num comentário; passa se o filtro estiver logicamente invertido noutro
ponto; e **quebra num refactor inofensivo**. Concentração: `test_signatures_ownership.py` (3),
`test_idor_criacao_carteira.py` (3), + 20 arquivos com 1-2.

*Atenuante:* `test_idor_criacao_carteira.py:97` declara que o teste comportamental correspondente
está em `test_idor_criacao_caso_dblevel.py`. **Só `test_signatures_ownership.py` (o módulo inteiro,
3/3) não tem par comportamental.**

**(b) 14 funções sem asserção alguma** (padrão "não deve levantar"):
`test_users_role_hardening.py:25,31,42`; `test_pente_fino_bloco1.py:66`;
`test_hardening_ownership_2026_07.py:235`; `test_security_p0_rbac_pii.py:88,97`;
`test_seguranca_senha_2fa.py:135`; `test_seed_bootstrap.py:16,24`; `test_health.py:71`;
`test_langfuse_client.py:194`; `test_auto_reembed_scheduler.py:50`;
`test_extracao_estruturada.py:114`.

*Atenuante forte:* todas têm um par negativo no mesmo arquivo que **falha** nesse cenário. Não são
ruído — são baixa densidade.

### 2.4 As perguntas diretas do escopo

| Pergunta | Resposta | Evidência |
|---|---|---|
| **Persistência real (grava e relê)?** | **SIM — 35 arquivos**, atrás de `RUN_DB_TESTS=1`, ligado no CI | `test_prazos_vencidos_dblevel.py` (2 INSERT/7 SELECT), `test_integridade_contadores_dblevel.py` (15 testes) |
| **Permissão / IDOR?** | **SIM, denso — a área mais bem testada do repo** | `test_idor_criacao_caso_dblevel.py`, `test_idor_subrecursos_403_dblevel.py`, `test_portal_idor_matrix.py` (305 l., 2 camadas) + versão `_dblevel` (9 INSERT, row-level) |
| **Isolamento do RAG?** | **SIM, em dois níveis** | `test_rag_isolation.py:60-70` prova o SQL emitido com `client_id = :scope_cli` e o fail-closed (`scope_cli == ""` nunca casa UUID); `test_rag_isolation_dblevel.py:67,121` prova com 2 docs de clientes distintos no Postgres |
| **Citation gate?** | **SIM** | `test_citation_gate.py` (281 l.) — 3 políticas, 3 critérios, 409 no HITL sem override, override auditado |
| **HITL?** | **SIM, transversal — 34 arquivos** | `test_eval_agent_trajectory.py` roda **no CI como gate** (`--max-violacoes-hitl 0`) |

## 3. Cobertura por domínio

| Domínio | Tem teste? | É real? | Ressalva |
|---|---|---|---|
| Casos | Sim | **Sim (persistência + IDOR)** | persistência só com `RUN_DB_TESTS=1` |
| Clientes | Sim | **Sim (persistência + sigilo + PII)** | idem |
| Prazos | Sim | **Sim (função pura + job real)** | |
| Documentos | Sim | **Sim (LGPD + ownership)** | OCR real pulado aqui, presente no CI |
| Produção de peças | Sim | **Sim (lógica, sem banco)** | atomicidade da numeração só com Postgres |
| **Honorários / financeiro** | Sim | **Parcial** | **`despesas.py`, `financeiro_consolidado.py`, `honorarios_calc.py` sem cobertura de cálculo. Nenhum teste de persistência financeira** |
| Portal do cliente | Sim | **Sim (2 camadas + row-level)** | **melhor cobertura de segurança do repo** |
| IA / RAG | Sim | **Sim (fail-closed + gate + HITL)** | isolamento com dados reais só no CI |
| Auth / RBAC | Sim | **Sim (integração real)** | rate limit em memória não testado sob concorrência |

**26 dos 162 routers não têm sequer menção nos testes:** `ai_skills`, `ai_tools`, `api_keys`,
`backup_admin`, `cerebro`, `consumidor_monitor`, `contratos_societarios`, `curadoria_renomada`,
`dossie_cliente`, `entrada_universal`, `entrada_universal_vinculo`, `exito_rateio`,
`gestao_societaria`, `ia_agente`, `ia_especializada`, `jurisprudencia_interna`, `module_help`,
**`peca_geracao_router`**, `pending_items`, **`pix`**, `produtividade`, `regulatorio`, `sumulas`,
`system_modules`, `veredito_ia_router`, `victory_vault_router`.

> Três merecem destaque: **`pix`** (movimenta dinheiro), **`api_keys`** (credencial) e
> **`peca_geracao_router`** — este último é o coração do critério de lançamento declarado no
> `CLAUDE.md` ("levar um caso ao protocolo").

## 4. CI — o que executa e o que deixa passar

`.github/workflows/ci.yml`, **três jobs** em `pull_request` + `push:main` + `workflow_dispatch`:

**`db-validation`** (Postgres `pgvector/pg16`, `RUN_DB_TESTS: "1"`): `bash -n` nos scripts de
deploy/backup → deps nativas (libmagic, poppler, **tesseract**, pango, cairo) → gate de
compatibilidade dos modelos RAG (sem baixar pesos) → extensões `vector`/`pg_trgm`/`pgcrypto` →
**`ruff check app` (bloqueante)** → **`pip-audit` (bloqueante)** → `alembic upgrade head` →
`pytest tests -q --tb=short --maxfail=25`.

**`eval-smoke`** (offline, bloqueante): `run_eval --smoke` + `agent_trajectory --min-tool 1.0
--max-violacoes-hitl 0`.

**`frontend-build`**: `npm ci` → **prettier bloqueante** → `vitest` → `npm audit --audit-level=critical`
→ `tsc --noEmit && vite build`.

> ### Correção ao `CLAUDE.md`
>
> A seção CI/CD afirma que ruff e pip-audit são **"informativos"**. **Está errado**: verificado por
> mim — não há `continue-on-error` em nenhum passo do `ci.yml`, e o passo do pip-audit se chama
> literalmente *"Auditoria **bloqueante** de dependências Python"* (`:114`). Além disso o
> `CLAUDE.md` **omite o terceiro job, `eval-smoke`** (`:157`).

### O que o CI deixaria passar

1. **Regressão de cobertura.** `pytest-cov` está instalado, mas **não há `--cov` nem limiar em
   lugar nenhum** (confirmado: `grep -c '\-\-cov' ci.yml` → **0**). **Um PR que apague 500 testes
   passa verde.**
2. **Router novo sem teste algum** — daí os 26 routers órfãos.
3. **Teste que assere sobre string de código-fonte** conta como teste válido (32 casos).
4. `npm audit --audit-level=critical` ignora `high` no frontend, enquanto o `pip-audit` do backend
   bloqueia em qualquer severidade. **Assimetria.**
5. `--maxfail=25` trunca o log quando o estrago é grande.
6. **`app/eval/`, `scripts/`, `seeds/`, `alembic/` não passam pelo ruff** — `ci.yml:103` roda
   `ruff check app` apenas.
7. **`qa/e2e/run_fictitious_smoke.py` não está em nenhum workflow.** O E2E ponta a ponta **não é
   executado por CI algum** — e, quando roda, é contra produção.

> ### O gap estrutural
>
> **A suíte inteira passa — 4 463 testes — com três defeitos P0 vivos** (ver `08-backend.md`), dois
> deles verificáveis com **uma única requisição HTTP**. Não há teste que faça request real contra
> `/api/rag/docs` nem contra os paths `/v1`.
>
> **Não é lacuna de cobertura de unidade — é lacuna de teste de superfície.** Nada exercita *"a URL
> que o navegador realmente envia bate numa rota que realmente responde"*.

## 5. Lacunas priorizadas

### P0 — bloqueia o critério de lançamento

| # | Lacuna |
|---|---|
| T-P0-1 | **`peca_geracao_router.py` sem nenhum teste** — é a rota do fluxo "caso → peça → protocolo". `test_motor_peca.py` cobre o *orquestrador*, não este router |
| T-P0-2 | **Nenhum teste da classe "gravação não transacional entre registros relacionados"** — nenhum teste força rollback parcial e verifica que nada meio-gravado sobrou (varredura de `rollback\|atomic\|transa*` nos 342 arquivos) |
| T-P0-3 | **`pix.py` e `api_keys.py` sem teste** — movimentação financeira e emissão de credencial sem rede de segurança |
| T-P0-4 | **Zero gate de cobertura no CI** — deleção de testes passa verde |
| T-P0-5 | **Nenhum teste de superfície URL-final → rota** (a lacuna que deixou passar os 3 P0) |

### P1

| # | Lacuna |
|---|---|
| T-P1-1 | `test_signatures_ownership.py` é **100 % asserção sobre string** (3/3), **sem par comportamental**. Assinatura eletrônica precisa de teste que **execute** `sig.listar`/`sig.assinar` com dois clientes |
| T-P1-2 | **Honorários/financeiro sem teste de cálculo nem de persistência** |
| T-P1-3 | `qa/e2e/run_fictitious_smoke.py` fora de todo workflow — e roda contra produção quando roda |
| T-P1-4 | **161 dos 4 629 testes (3,5 %) são inexecutáveis sem Postgres** — e são justamente os de persistência e isolamento row-level. Desenvolvedor sem Docker recebe **verde falso local** |

### P2 / P3

`T-P2-1` converter os 32 `inspect.getsource` de área sensível em comportamentais ·
`T-P2-2` asserção explícita nas 14 funções sem assert · `T-P2-3` ruff cobrir `scripts/`, `seeds/`,
`alembic/`, `app/eval/` · `T-P2-4` alinhar `npm audit` em `high` · `T-P2-5` elevar `--maxfail` ·
`T-P3-1` corrigir o `CLAUDE.md` (§4) · `T-P3-2` documentar venv limpo / pinar `setuptools`
(`http-ece`) · `T-P3-3` 23 routers menores sem teste.

## 6. Limitações declaradas

1. **Os 161 testes DB-level não foram executados** (sem Postgres/Docker). Passam ou falham no CI —
   não posso afirmar.
2. **Não houve teste de mutação real** (não era permitido alterar código). As afirmações de §2.3
   são **inferência por leitura, não observação**.
3. Amostra de **15 arquivos sobre 342** — a classificação por domínio é representativa, não exaustiva.
4. **Cobertura de linha não medida** (sem `--cov` e sem baseline). As lacunas de §3 e §5 vêm de
   mapeamento router × teste, não de coverage.
