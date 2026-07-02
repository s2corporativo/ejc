# PLANO ETAPA 4 — CORREÇÃO SEGURA E PRIORIZADA DO SISTEMA EJC

Data: 2026-07-02
Branch: `audit-ejc-graphify-etapa1`
Base: `RELATORIO_ETAPA_1_SEGURANCA_E_DIAGNOSTICO.md`, `RELATORIO_ETAPA_2_GRAPHIFY_MAPEAMENTO.md`, `RELATORIO_ETAPA_3_AUDITORIA_COMPLETA.md`, código real do sistema.
Nenhuma correção foi executada nesta etapa — apenas planejamento.

**Investigação adicional feita antes deste plano** (resolve a pendência "investigar antes de decidir" da Etapa 3, achado C1): confirmado via grep que `ia_extra.py` tem **8 pontos de chamada reais no frontend** (`ExplicarMov.tsx:31`, `AssistenteIA.tsx:72,74,76,82`, `CasoDetalhe.tsx:394`, `ramos/RamoBase.tsx:631`, `NoticiasCard.tsx:114`) — a página `AssistenteIA.tsx` inteira depende desse router e está 404 em produção agora. `assistente.py` não tem nenhuma chamada frontend — é código morto de verdade.

---

## 1. ORDEM CORRETA DE CORREÇÃO

1. Bloco 0 — erros que impedem build (nenhum encontrado na Etapa 3; confirmar no início do Bloco 1 mesmo assim)
2. Bloco 1 — rota crítica quebrada em produção (`ia_extra.py` não montado) — menor risco, maior impacto imediato
3. Bloco 2 — segurança crítica em backend (IDOR documentos)
4. Bloco 3 — banco de dados (modelo ORM `processes` + teste de schema em CI)
5. Bloco 4 — integração frontend/backend (erros silenciosos, alert/toast, Whatsapp.tsx)
6. Bloco 5 — IA/RAG (isolamento por cliente no RAG — o mais delicado, feito com teste controlado dedicado)
7. Bloco 6 — LGPD (criptografia PII, direito ao esquecimento) — feito depois do RAG porque tem menor risco de regressão técnica, mas antes dos médios porque é obrigação legal
8. Bloco 7 — médios restantes (duplicação de serviços, fragmentação de routers) — só depois de tudo crítico estável
9. Bloco 8 — leves / limpeza (componentes órfãos, dependências não usadas, testes E2E)

Cada bloco só começa depois que o anterior estiver testado e commitado.

---

## 2. BLOCOS DE CORREÇÃO

### BLOCO 1 — Montar `ia_extra.py` em `main.py` (Prioridade CRÍTICA / Área: Backend)

- **Problema encontrado:** router com 5 endpoints (`/ai/traduzir-andamento`, `/ai/resumir-texto`, `/ai/gerar-minuta`, `/ai/pesquisar`, `/ai/sugestao-honorarios`) nunca é incluído via `include_router()` em `main.py`.
- **Risco atual:** 8 chamadas reais do frontend em 5 arquivos retornam 404. Página `AssistenteIA.tsx` completamente inoperante.
- **Arquivos prováveis envolvidos:** `backend/app/main.py` (adicionar 2 linhas: import + `include_router`).
- **Impacto esperado:** `AssistenteIA.tsx`, `ExplicarMov.tsx`, `CasoDetalhe.tsx` (sugestão de honorários), `RamoBase.tsx` (gerar minuta), `NoticiasCard.tsx` (resumir texto) voltam a funcionar.
- **Risco de quebra:** praticamente nulo — é adicionar uma rota que não existe, não pode conflitar com nada ativo. Único cuidado: checar se o prefixo `/ai` já montado por `ai.py` não colide com os mesmos paths (confirmar antes: `ai.py` não tem essas 5 rotas).
- **Teste necessário depois:** `curl -X POST http://localhost:8000/api/ai/resumir-texto` (ou teste via frontend), mais `pytest --collect-only` para garantir que nada quebrou na coleção de testes.
- **Critério de aceite:** as 5 rotas respondem (não mais 404); `AssistenteIA.tsx` carrega e executa ação sem erro de rede.

### BLOCO 1b — Decidir destino de `assistente.py` (Prioridade MÉDIA / Área: Backend)

- **Problema:** router com 2 endpoints (`/assistente/cases/{case_id}/chat`, `/assistente/detectar-prazos`) sem nenhuma chamada frontend.
- **Risco atual:** nenhum (não afeta usuário) — mas é código morto ocupando espaço mental de manutenção.
- **Arquivos:** `backend/app/routers/assistente.py`.
- **Impacto esperado:** nenhum, é decisão de escopo — **não removo sem confirmação explícita do usuário** (regra "não remova módulos sem justificativa técnica" e "perguntar antes de executar quando houver ambiguidade").
- **Ação recomendada:** perguntar ao usuário antes de decidir entre (a) montar também, se for funcionalidade planejada, ou (b) mover para `_QUARENTENA/` com justificativa documentada.
- **Critério de aceite:** decisão registrada por escrito antes de qualquer ação no Bloco 1b.

---

### BLOCO 2 — Corrigir IDOR na criação de documentos (Prioridade CRÍTICA / Área: Backend, Segurança)

- **Problema:** endpoint de upload em `documents.py` não valida ownership de `case_id`/`client_id` antes de associar o documento.
- **Risco atual:** usuário autenticado pode criar documento em caso de outro cliente adivinhando/enumerando UUID — violação de sigilo profissional (EOAB art. 25) e possível vazamento de dados entre clientes.
- **Arquivos prováveis envolvidos:** `backend/app/routers/documents.py` (endpoint de upload), reusar `verificar_acesso_caso()` de `backend/app/core/ownership.py` (mesmo padrão já usado no fix de `processes.py` nesta branch).
- **Impacto esperado:** upload de documento passa a exigir que o usuário tenha acesso ao `case_id` informado, igual ao padrão já aplicado em `processes.py` e outros routers.
- **Risco de quebra:** baixo — mesmo padrão testado recentemente em `processes.py` (commit `50e8ad4` desta branch). Pode quebrar fluxos que hoje dependem do comportamento permissivo (ex: upload em nome de outro usuário por engano) — checar se há caso de uso legítimo antes.
- **Teste necessário depois:** teste de ownership dedicado (seguir padrão de `backend/tests/test_ownership.py`), mais teste manual: usuário do caso A tenta subir documento com `case_id` do caso B → deve retornar 403/404.
- **Critério de aceite:** upload de documento só funciona se o usuário tem acesso ao caso; teste automatizado cobrindo o caso negativo passa.

---

### BLOCO 3 — Modelo ORM para `processes` + teste de schema (Prioridade CRÍTICA / Área: Banco de Dados)

- **Problema:** tabela `processes` (migration 048) não tem model SQLAlchemy — acesso só via SQL cru. Histórico recorrente de drift model↔banco (migrations 038, 053, 056 reconciliando retroativamente).
- **Risco atual:** disaster recovery falha silenciosamente (banco limpo + migrations não garante que o código funcione); qualquer typo em coluna SQL cru não é pego em tempo de desenvolvimento.
- **Arquivos prováveis envolvidos:** novo `backend/app/models/process.py`, `backend/app/models/__init__.py` (registrar import), **NÃO** requer nova migration (tabela já existe — só declarar o model em cima dela).
- **Impacto esperado:** `routers/processes.py` e `services/processo_service.py` podem futuramente migrar de SQL cru para ORM (fora do escopo deste bloco — só criar o model primeiro, sem reescrever os routers ainda, para não misturar riscos).
- **Risco de quebra:** baixo se o model só for **declarado** (mapear colunas existentes) sem alterar o código que já usa SQL cru. Risco médio se tentarmos migrar os routers para ORM no mesmo bloco — **não fazer isso agora**, é um segundo bloco separado se o usuário quiser.
- **Teste necessário depois:** `python -c "from app.models.process import Process"` sem erro; `alembic check` (se disponível) ou script que compara `Base.metadata.tables['processes']` com colunas reais via `information_schema`.
- **Critério de aceite:** model existe, mapeia todas as colunas reais (incluindo `is_principal` da migration 056), nenhuma mudança de comportamento visível.

### BLOCO 3b — Teste de schema contínuo (Prioridade ALTA / Área: Banco de Dados, Testes)

- **Problema:** não há teste que compare `Base.metadata` com o banco real — só a topologia da cadeia Alembic é testada.
- **Arquivos:** novo teste em `backend/tests/test_schema_sync.py`.
- **Impacto esperado:** falhas de drift como as de 038/053/056 seriam pegas antes do deploy, não depois.
- **Risco de quebra:** nulo — é só um teste novo, não altera runtime.
- **Teste necessário:** rodar o próprio teste contra o banco de dev (requer Postgres disponível — hoje não há Docker local; documentar isso como limitação e não bloquear).
- **Critério de aceite:** teste escrito e passando localmente quando houver Postgres acessível; documentado no README de testes como pré-requisito.

---

### BLOCO 4 — Frontend: erros silenciosos, alert/toast, Whatsapp.tsx (Prioridade CRÍTICA / Área: Frontend)

Dividido em 3 sub-blocos pequenos, cada um testado isoladamente:

**4a — Whatsapp.tsx**
- **Problema:** tela placeholder vazia visível no menu.
- **Ação recomendada:** não é uma "correção" técnica — é decisão de produto. Opções: (1) esconder do menu até a feature existir, (2) manter visível com aviso mais claro de "em breve". **Perguntar ao usuário antes de agir** (mudança de UX visível).
- **Risco de quebra:** nulo, mudança isolada em 1 arquivo + 1 item de menu em `Layout.tsx`.

**4b — Erros de API silenciosos**
- **Problema:** `.catch(() => {})` em `Casos.tsx`, `Dashboard.tsx` e outras.
- **Arquivos prováveis:** todas as páginas listadas no relatório de auditoria frontend (usar `graphify query` para achar todas as ocorrências de `.catch(() => {})` no projeto antes de começar).
- **Ação:** substituir por `.catch(e => toast.error(...))`, usando o componente `Toast.tsx` já existente e testado (usado 23x em `CasoDetalhe.tsx`).
- **Risco de quebra:** baixo — é aditivo (adiciona feedback, não muda lógica de dados). Fazer página por página, testando visualmente cada uma antes de ir para a próxima (regra "corrija um bloco por vez").
- **Teste necessário:** abrir cada página corrigida no navegador, forçar erro de rede (ex: desligar backend temporariamente) e confirmar que o toast aparece.

**4c — `alert()` → `toast.error()`**
- **Problema:** inconsistência em 39+ páginas.
- **Ação:** mesma lógica do 4b, mas trocando `alert()` por `toast.error()`.
- **Risco de quebra:** baixo, mudança mecânica e visível — testar cada página manualmente.
- **Critério de aceite (4b+4c):** nenhuma página usa mais `alert()` para erro de API; todo `.catch` silencioso tem feedback visual.

---

### BLOCO 5 — RAG: isolamento por cliente/caso (Prioridade CRÍTICA / Área: IA, RAG — o mais delicado)

- **Problema:** `scope_client_id` existe na assinatura de `buscar_contexto_rag()` mas nunca é passado nas 20+ chamadas reais.
- **Risco atual:** hoje "seguro por acidente" (nunca recupera nada restrito), mas funcionalmente quebrado (precedentes internos nunca aparecem) e uma bomba-relógio de segurança se alguém mexer sem entender.
- **Arquivos prováveis envolvidos:** todas as 20+ chamadas listadas na Etapa 3 (`ai_service.py:332,341`, `rag.py:301`, `ai.py:310`, `teses.py:335,427,430`, `ai_tools.py`, `ai_skills.py`, `peca_service.py`, `documento_service.py`, `validador_juridico_service.py`, `dossie_service.py`).
- **Impacto esperado:** cada chamada passa a extrair `client_id` do usuário atual ou do `case_id` em contexto (`case.client_id`) e passar como `scope_client_id`.
- **Risco de quebra:** **ALTO se feito errado** — é exatamente o tipo de mudança que pode introduzir vazamento real entre clientes se a lógica de extração do `client_id` correto estiver errada em algum dos 20+ pontos.
- **Regra obrigatória aplicada:** "Não altere IA/RAG sem teste controlado." Este bloco **não deve ser feito em uma tacada só**. Proposta de execução:
  1. Escrever teste automatizado ANTES da correção: cenário com 2 clientes fictícios (dados fake, não reais), 2 precedentes internos (um de cada), confirmar que hoje nenhum aparece (comportamento atual) e depois que só o do cliente correto aparece após a correção.
  2. Corrigir 1 chamada por vez (começar por `ai_service.py:341`, a mais crítica — busca de precedentes internos), rodar o teste, confirmar isolamento, só então seguir para a próxima chamada.
  3. Repetir para as 19 restantes, em lotes pequenos (3-5 por vez), com o teste automatizado rodando a cada lote.
- **Teste necessário depois de cada lote:** o teste de isolamento multi-cliente descrito acima, mais os testes existentes de `test_rag_isolation.py`.
- **Critério de aceite:** todas as 20+ chamadas passam `scope_client_id`; teste de isolamento multi-cliente passa; nenhum precedente de cliente A aparece em consulta de cliente B.

### BLOCO 5b — Corrigir status de embeddings desabilitados (Prioridade MÉDIA / Área: IA, RAG)

- **Problema:** `status_indexacao` fica "pendente" para sempre quando `EMBEDDINGS_ENABLED=False`, em vez de refletir a realidade.
- **Arquivos:** `backend/app/services/ingestion_service.py:182-185`.
- **Ação:** trocar valor para `"sem_embeddings"` quando embeddings estão desligados por configuração.
- **Risco de quebra:** baixo — é só um valor de status, checar se algum código depende do valor literal `"pendente"` antes de trocar.
- **Critério de aceite:** status reflete corretamente a causa (config desligada vs. processamento pendente).

---

### BLOCO 6 — LGPD: criptografia de PII + direito ao esquecimento (Prioridade CRÍTICA / Área: Segurança, Documentação)

**6a — Criptografia de CPF/CNPJ em repouso**
- **Problema:** campos em texto puro no banco.
- **Arquivos prováveis:** `backend/app/models/client.py`, nova migration para converter tipo de coluna, gerenciamento de chave de criptografia via `.env`.
- **Risco de quebra:** **ALTO** — mexe em dado de produção real, índice UNIQUE em cpf/cnpj precisa continuar funcionando (criptografia determinística ou índice separado por hash), buscas por CPF/CNPJ no sistema inteiro (grep antes de mexer) precisam continuar funcionando.
- **Ação recomendada:** este é o único item do plano que exige uma decisão de arquitetura **antes** de codar — não corrigir "no impulso". Sugestão: sessão de design dedicada (fora do escopo mecânico deste plano) para decidir entre criptografia em nível de coluna (pgcrypto) vs. aplicação (Fernet) vs. tokenização.
- **Teste necessário:** migração testada em cópia do banco antes de produção; validar que login/busca por CPF continuam funcionando.
- **Critério de aceite:** CPF/CNPJ não legíveis em texto puro numa consulta SQL direta; funcionalidade de busca/dedup preservada.

**6b — Endpoint de direito ao esquecimento**
- **Problema:** ausente.
- **Arquivos prováveis:** novo endpoint em `backend/app/routers/clients.py`, novo fluxo de anonimização (não deleção física — soft delete + anonimização de campos, seguindo o padrão de soft-delete já usado no projeto).
- **Risco de quebra:** médio — precisa decidir o que acontece com casos/documentos vinculados ao cliente (não pode simplesmente apagar registros que têm valor jurídico/fiscal, como honorários já pagos).
- **Ação recomendada:** desenhar o fluxo (marcação → aprovação → anonimização) antes de implementar; não é uma correção mecânica.
- **Critério de aceite:** endpoint existe, gera log de auditoria imutável, anonimiza dados pessoais preservando o necessário para obrigações legais/fiscais do escritório.

---

### BLOCO 7 — Médios restantes (Prioridade MÉDIA — só depois de todo o crítico estável)

Lista resumida (detalhamento completo é repetir a Etapa 3 — não duplicado aqui):
- Consolidar duplicação de serviços de IA (M1, M2) e honorários (M4) — requer decisão de arquitetura, não é mecânico.
- Adicionar FK ausente em `clients.responsavel_id` (M9) — pequeno, baixo risco.
- Registrar schemas Pydantic faltantes (M5) — mecânico, baixo risco.
- Blacklist de refresh token (M6) — médio risco, requer Redis ou tabela nova.
- Telas dedicadas para Processos, Portal do Cliente, Relatórios (M20) — é trabalho de produto/frontend novo, não correção.

### BLOCO 8 — Leves / limpeza (Prioridade BAIXA)

- Remover componentes órfãos do frontend (M18) — após confirmar com o usuário que não há plano de uso futuro.
- Avaliar remoção de `langfuse`, `boto3`/`botocore` não usados (M21) — baixo risco, mecânico.
- Testes E2E (Playwright) para o frontend — trabalho novo, não correção de bug.

---

## 3. SEQUÊNCIA SEGURA (RESUMO)

```
Bloco 1  (montar ia_extra.py)              → testar → commit
Bloco 1b (decidir assistente.py)           → perguntar usuário → agir → testar → commit
Bloco 2  (IDOR documents.py)               → testar → commit
Bloco 3  (model ORM processes)             → testar → commit
Bloco 3b (teste de schema)                 → testar → commit
Bloco 4a (Whatsapp.tsx)                    → perguntar usuário → agir → testar → commit
Bloco 4b (erros silenciosos)               → testar por página → commit
Bloco 4c (alert→toast)                     → testar por página → commit
Bloco 5  (RAG isolamento, lotes pequenos)  → teste multi-cliente a cada lote → commit por lote
Bloco 5b (status embeddings)               → testar → commit
Bloco 6a (criptografia PII)                → design dedicado → testar em cópia → commit
Bloco 6b (direito ao esquecimento)         → design dedicado → testar → commit
Bloco 7  (médios restantes)                → um de cada vez → commit
Bloco 8  (leves/limpeza)                   → um de cada vez → commit
```

---

## 4. REGRAS DE EXECUÇÃO (reforçadas deste plano)

- Nenhuma correção deste plano será aplicada sem confirmação explícita do usuário para iniciar a Etapa 5.
- Blocos marcados como "perguntar usuário antes de agir" (1b, 4a) não avançam sozinhos.
- Blocos 5 e 6 (RAG e LGPD) são os de maior risco — sempre com teste dedicado antes de codar, nunca em lote único.
- Nenhuma migration de banco será aplicada em produção sem backup validado (regra já registrada na Etapa 1).
- Todo bloco gera commit próprio, com testes rodados antes de avançar para o próximo.

**Critério de aceite desta etapa: ATENDIDO** — plano claro, execução dividida em blocos pequenos, riscos mapeados, critérios de aceite definidos por bloco, nenhuma correção ainda aplicada.
