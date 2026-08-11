# Auditoria do módulo Clientes — agosto/2026

**Escopo**: CRM de clientes ponta a ponta — routers `clients.py`, `dossie_cliente.py`,
`relatorio_cliente.py`, `pending_items.py`, `sociedades_cliente.py`; services
`conflito_service.py`, `client_anonimizacao.py`, `pii_crypto` (uso); model/schema
`client.py`; gate `core/client_ownership.py`; frontend `Clientes.tsx`,
`DossieCliente.tsx`, `CRMLeads.tsx`, `moduleRegistry.tsx`; migrations 112 e 126;
testes correlatos em `backend/tests/`.

**Método**: leitura integral dos arquivos citados, cruzamento frontend↔backend↔schema
de banco (migrations) e verificação de cada achado no código — nenhum item abaixo é
inferência sem evidência. Auditoria **somente leitura**: nenhuma correção aplicada
neste PR; cada achado indica a correção recomendada.

---

## Resumo executivo

O núcleo do CRUD de clientes está bem construído: o cutover de PII (migration 112)
gravou CPF/CNPJ apenas cifrado (Fernet) + índice cego (HMAC), a segregação de
carteira (sigilo interno LGPD/EOAB) cobre listagem, detalhe, escrita e criação de
acesso ao portal, e há trilha de auditoria em toda escrita. Porém a auditoria
encontrou **1 achado crítico** (dois endpoints centrais quebrados por referência a
colunas dropadas — a ficha do cliente não abre), **2 achados altos** (rebaixamento
silencioso do alerta ético de conflito e vazamento de CPF/CNPJ em claro sem rate
limit num endpoint de conflito) e uma série de médios/baixos de consistência.

| # | Severidade | Achado | Onde |
|---|-----------|--------|------|
| 1 | **Crítica** | Dossiê e relatório financeiro consultam colunas `cpf`/`cnpj` dropadas → 500 em toda chamada | `dossie_cliente.py:98`, `relatorio_cliente.py:89` |
| 2 | **Alta** | Conflito ético: `_STATUS_ATIVOS` usa status de caso extintos → nível "crítico" nunca dispara | `clients.py:240,354` |
| 3 | **Alta** | `/clients/verificar-conflito` devolve CPF/CNPJ decifrado, sem máscara e sem rate limit | `clients.py:196-235` + `conflito_service.py:146,168` |
| 4 | Média | Dossiê restrito à gestão, mas rota `/clientes` liberada a advogado/secretaria → 403 estrutural | `dossie_cliente.py:94` × `moduleRegistry.tsx:55` |
| 5 | Média | Exclusão de cliente não desativa login do portal nem checa dependências | `clients.py:676-690` × `portal.py` |
| 6 | Média | `GET /clients/?status=<inválido>` → 500 (filtro sem validação contra o enum) | `clients.py:403,431-432` |
| 7 | Média | `ClientUpdate` descarta silenciosamente `data_nascimento`, `profissao`, `nome_fantasia`, `complemento`, `origem` | `schemas/client.py:97-115` |
| 8 | Média | Papel `financeiro` autorizado no relatório financeiro, mas sem visão → 404 para tudo; `secretaria` com visão total no CRM e 404 nos sub-recursos | `relatorio_cliente.py:17,27-43`, `pending_items.py:14-32` |
| 9 | Baixa | `pending-items` sem schema Pydantic (payload `dict` cru; `due_date`/`status`/`type` sem validação; `case_id` não conferido) | `pending_items.py:53-108` |
| 10 | Baixa | Gate de titularidade quadruplicado (ORM ×2 + SQL cru ×2) em vez do módulo canônico | `clients.py:56-117` × `core/client_ownership.py` |
| 11 | Baixa | Wildcard `%`/`_` não escapado no ILIKE de `case_partes` em `/checar-conflito` | `clients.py:342-343` |
| 12 | Baixa | `email` do cliente sem validação de formato no cadastro | `schemas/client.py:30` |

---

## Achados detalhados

### 1. [CRÍTICA] Dossiê e relatório financeiro do cliente respondem 500 — colunas dropadas

A migration `112_client_pii_drop_plaintext.py` executa
`ALTER TABLE clients DROP COLUMN IF EXISTS cpf / cnpj` (linhas 111-112). Dois
endpoints continuam consultando essas colunas em SQL bruto:

- `backend/app/routers/dossie_cliente.py:98` — `COALESCE(cpf, cnpj) AS cpf_cnpj`
  na query **do cliente**, a única seção do dossiê declarada "não degradável"
  (docstring, linhas 10-11). Resultado: `UndefinedColumnError` → **500 em toda
  chamada de `GET /clients/{id}/dossie`**.
- `backend/app/routers/relatorio_cliente.py:89` — mesma expressão na query
  inicial de `GET /clients/{id}/relatorio-financeiro`; a query roda antes da
  degradação por seção, então o endpoint inteiro responde 500.

Impacto: `DossieCliente.tsx:937` usa o dossiê como fonte principal da ficha —
**a ficha do cliente não abre**; a aba financeira (`DossieCliente.tsx:723`)
idem. É a reintrodução do exato achado da auditoria de julho ("a tela do dossiê
não abria"), que a "degradação por seção" (PR #765) tentou resolver — mas a
seção quebrada é justamente a não degradável. Nota: o commit `65dbbe7` que criou
a migration 112 é o mesmo que tocou esses dois arquivos sem atualizar o SQL.

Por que o CI não pegou: nenhum teste exercita o SQL desses dois routers contra o
schema real — `test_dossie_modulos.py` testa o service `dossie_modulos` (outro
módulo) e `test_degradacao_por_secao.py` não passa pela query do cliente.

**Correção recomendada**: substituir a expressão por seleção de `cpf_enc`/`cnpj_enc`
com decifra via `pii_crypto` (ou carregar o `Client` ORM e usar `documento_plain`),
e adicionar teste de regressão **db-level** que chame os dois endpoints contra o
Postgres do CI (o job `db-validation` já sobe o schema via `alembic upgrade head`).

### 2. [ALTA] Alerta ético de conflito rebaixado silenciosamente — status de caso extintos

`clients.py:240` define `_STATUS_ATIVOS = {"triagem", "ativo", "suspenso", "acordo"}`
para elevar a "crítico" o conflito com parte de caso **ativo** em `/checar-conflito`
(linha 354). Mas a migration 126 reduziu `CaseStatus` a
`aberto | em_instrucao | em_producao | protocolado | encerrado | arquivado`
(`models/case.py:42-55`) — **nenhum** valor de `_STATUS_ATIVOS` existe mais.

Consequência: `ativo` é sempre `False`; toda parte encontrada é classificada como
`parte_em_caso_encerrado` com nível "atenção" (`clients.py:369-381`), inclusive em
casos em plena representação. O alerta EOAB arts. 34-35 nunca atinge "crítico" por
esse caminho — falso negativo silencioso em checagem ética obrigatória. (O bloqueio
de anonimização, em contraste, já usa os status novos — `client_anonimizacao.py:29-31`.)

**Correção recomendada**: `_STATUS_ATIVOS = {s.value for s in CaseStatus} - {"encerrado", "arquivado"}`
(deriva do enum; não envelhece), com teste de regressão cobrindo parte em caso
`aberto`/`em_instrucao` → nível "critico". Regra jurídica exige fonte e teste
(regra 5 da governança).

### 3. [ALTA] `/clients/verificar-conflito` expõe CPF/CNPJ decifrado, sem máscara e sem rate limit

`detectar_conflito` inclui `"documento": c.documento_plain` (CPF/CNPJ **decifrado
completo**) nos achados (`conflito_service.py:146,168`), cruzando a base inteira
por dever ético — deliberadamente **sem** segregação de carteira. O endpoint
`POST /clients/verificar-conflito` (`clients.py:196-235`) devolve esses achados
**crus** a qualquer papel de `_CLIENTES` (inclui advogado e secretaria), sem
máscara e **sem rate limit**.

O endpoint irmão `/checar-conflito` recebeu exatamente essas duas mitigações no
PR #528 (máscara via `mascarar_documento` + `rate_limit("checar-conflito", 10)`,
`clients.py:243-245,296`) — e seu docstring afirma ser "o único que cruza a base
inteira" (`clients.py:266`), o que é falso: `verificar_conflito` também cruza.
Vetor prático: advogado enumera nome (ILIKE ≥4 chars) ou CPF/CNPJ e reconstrói a
carteira alheia **com documento em claro**, em massa, sem throttle — exatamente o
que a máscara do #528 quis impedir.

**Correção recomendada**: aplicar `mascarar_documento` aos achados e o mesmo
`rate_limit` do endpoint irmão; corrigir o comentário de `/checar-conflito`.
Avaliar unificar os dois endpoints (o frontend `Clientes.tsx:112` usa apenas
`/checar-conflito`; verificar chamadores restantes de `/verificar-conflito`).

### 4. [MÉDIA] Dossiê é gestão-only, mas a rota é liberada a advogado/secretaria

`GET /clients/{id}/dossie` exige `is_gestao` (socio+) — `dossie_cliente.py:94-95`.
Mas o `moduleRegistry.tsx:55` libera `/clientes` (e a navegação à ficha) para
`advogado` e `secretaria`. Resultado estrutural: esses papéis abrem a ficha e
recebem 403 na carga principal — mesmo para cliente da **própria carteira**, que
eles podem ver no detalhe (`GET /clients/{id}`). O comentário do endpoint justifica
a restrição pelo risco de agregação, porém o gate de titularidade já existente
(`_pode_ver_cliente`) resolveria o caso do advogado sem abrir a base inteira.

**Correção recomendada**: decidir o produto — (a) dossiê com gate de titularidade
(gestão vê tudo; advogado só a própria carteira; secretaria conforme matriz), ou
(b) esconder a entrada da ficha para não-gestão no frontend. A assimetria atual é
a pior das opções (tela acessível que sempre falha).

### 5. [MÉDIA] Exclusão de cliente não desativa o portal nem verifica dependências

`DELETE /clients/{id}` (`clients.py:676-690`) faz soft delete e nada mais:

- **não desativa** usuários `cliente_externo` vinculados (`users.client_id`) — a
  anonimização LGPD faz isso (`client_anonimizacao.py:108-112`), a exclusão não;
- os endpoints do portal (`portal.py`) filtram por `cu.client_id` e `deleted_at`
  **dos casos**, nunca verificam `clients.deleted_at` — o login do cliente
  "removido" continua ativo e acessando casos, documentos e financeiro;
- não há verificação de casos ativos antes da exclusão (a anonimização tem
  `verificar_bloqueios`; a exclusão, mais drástica na prática, não tem).

É instância da classe já mapeada pela auditoria externa: "gravação não
transacional entre registros relacionados".

**Correção recomendada**: na exclusão, desativar logins vinculados (mesmo bloco da
anonimização) e bloquear — ou exigir confirmação — quando houver caso em
representação ativa, espelhando `verificar_bloqueios`.

### 6. [MÉDIA] Filtro `status` da listagem devolve 500 para valor inválido

`GET /clients/?status=X` compara a string crua com a coluna `SAEnum(ClientStatus)`
(`clients.py:403,431-432`). Valor fora do enum estoura no bind → 500. O frontend
atual só envia `lead`/`ativo` (`CRMLeads.tsx:111`, `CentralRelacionamento.tsx:125-126`),
mas a API é pública para a equipe e a auditoria externa já registrou 500 por
vocabulário de status como armadilha recorrente. `ClientCreate`/`ClientUpdate`
validam status; a query string ficou de fora.

**Correção recomendada**: validar `status_f` contra `ClientStatus` no endpoint
(422 quando inválido), padrão já usado nos schemas do mesmo módulo.

### 7. [MÉDIA] `ClientUpdate` descarta campos do cadastro em silêncio

`ClientUpdate` (`schemas/client.py:97-115`) não expõe `data_nascimento`,
`profissao`, `nome_fantasia`, `complemento` e `origem` — todos presentes em
`ClientCreate` e no model. Um PATCH com esses campos é aceito (200) e os valores
são ignorados pelo Pydantic. O formulário atual da ficha só edita
nome/email/telefone/whatsapp (`DossieCliente.tsx:977-982`), então não há defeito
visível hoje — mas a API é assimétrica e o dado se torna ineditável após o
cadastro (só via recriação).

**Correção recomendada**: alinhar `ClientUpdate` a `ClientBase` (com os mesmos
validadores de `origem`/`tipo` quando aplicável) ou documentar a restrição.

### 8. [MÉDIA] Matriz de papéis inconsistente nos sub-recursos do cliente

- `relatorio_cliente.py:17` autoriza `financeiro`, mas o gate de visibilidade
  (`:27-43`) exige ser responsável pelo cliente ou advogado de caso — condição que
  o papel `financeiro` nunca satisfaz → 404 para tudo (autorização inócua).
- `secretaria` tem visão total no CRM (`clients.py:53`, `client_ownership.py:21`),
  mas em `pending-items`, `relatorio-financeiro` e `dossie` cai no gate comum e
  recebe 404/403 — a recepção opera o funil mas não vê pendências do cliente.

**Correção recomendada**: definir a matriz por sub-recurso (quem precisa ver o quê)
e reusar `visao_total_clientes()`/`ids_clientes_visiveis()` do módulo canônico em
todos eles, em vez de reimplementações divergentes.

### 9. [BAIXA] `pending-items` sem schema Pydantic

`pending_items.py:53-108` recebe `body: dict` cru: `title` é o único campo
verificado; `status`/`type` aceitam qualquer string (o board espera vocabulário
fixo); `due_date` inválida vira erro de banco (500); `case_id` não é conferido
contra o cliente da URL (item pode apontar caso de outro cliente). Escritas não
geram `criar_audit_log`, diferente do restante do módulo.

**Correção recomendada**: schema Pydantic com vocabulários fechados + validação de
`case_id` pertencer ao cliente + audit log nas escritas.

### 10. [BAIXA] Gate de titularidade implementado 4 vezes

A mesma regra (gestão/secretaria veem tudo; advogado só carteira própria) existe
em: `core/client_ownership.py` (canônico), `clients.py:56-117` (cópia ORM),
`relatorio_cliente.py:27-43` e `pending_items.py:14-32` (cópias em SQL cru — sem
a exceção da secretaria, aliás, origem do achado 8). Toda mudança de matriz
precisa ser feita em 4 lugares; o achado 8 mostra que já divergiram.

**Correção recomendada**: fazer os routers consumirem `client_ownership.pode_ver_cliente`
/`obter_cliente_autorizado` e aposentar as cópias.

### 11. [BAIXA] Wildcard não escapado no ILIKE de `case_partes`

`clients.py:342-343` monta `CaseParte.nome.ilike(f"%{req.nome.strip()}%")` sem
escapar `%`/`_`. O `conflito_service._padrao_like` (`:26-34`) existe exatamente
para isso e documenta o risco ("`____` casa qualquer registro com 4+ caracteres");
o trecho de `case_partes` não o usa. Mitigado pelo rate limit e pela máscara de
documento, mas amplia a enumeração de nomes de partes.

**Correção recomendada**: reusar `_padrao_like` (exportá-lo do service).

### 12. [BAIXA] `email` do cliente sem validação de formato

`ClientBase.email: Optional[str]` (`schemas/client.py:30`) aceita qualquer string.
`criar-acesso` usa `EmailStr`; o cadastro do CRM, não — e-mail inválido entra no
CRM e quebra fluxos de notificação downstream silenciosamente.

**Correção recomendada**: `EmailStr | None` com normalização (lower/trim), tolerando
string vazia → `None` como já se faz com `data_nascimento`.

---

## O que está bem (e deve ser preservado)

- **Cutover PII (C6/LGPD)** íntegro no CRUD principal: escrita somente
  `cpf_enc`/`cnpj_enc` (Fernet) + `cpf_hash`/`cnpj_hash` (HMAC); dedup por índice
  cego único parcial (exclui soft-deleted); busca por documento apenas por hash de
  documento completo; decifra resiliente por linha (`_decifrar_para_exibicao`)
  que degrada uma linha corrompida sem derrubar a listagem.
- **Segregação de carteira** aplicada na listagem (antes da busca — impede
  descoberta por documento), no detalhe, no PATCH (write-IDOR fechado), no
  find-or-create `/resolver` (não vaza existência: 404 uniforme) e no
  `criar-acesso`; portal isolado por `cu.client_id` em todos os endpoints.
- **Auditoria**: `criar_audit_log` em criação, atualização, exclusão, checagens de
  conflito, emissão LGPD e criação de credencial externa (ação destacada
  `PORTAL_ACESSO_CRIADO`).
- **LGPD arts. 17/18**: esquecimento com bloqueios verificáveis, `forcar`
  registrado, desativação do portal e limpeza de cifrados+hash; relatório do
  titular (PDF) e portabilidade (JSON) com trilha.
- **Validações de cadastro**: dígito verificador de CPF/CNPJ na criação e no
  update; senha forte + troca obrigatória no primeiro acesso do portal; erros de
  banco sem disclosure de schema (DataError → mensagem genérica).
- **Testes db-level existentes** para sigilo de titularidade, cutover PII,
  anonimização e funil de leads (`backend/tests/test_clients_*`,
  `test_client_*`) — o padrão certo; faltou estendê-lo a dossiê/relatório (achado 1).

## Lacunas de teste (consolidado)

1. Nenhum teste chama `GET /clients/{id}/dossie` nem
   `GET /clients/{id}/relatorio-financeiro` contra o schema real (achado 1).
2. Nenhum teste cobre a elevação a "crítico" de `/checar-conflito` com parte em
   caso ativo (teria pego o achado 2 na migration 126).
3. Nenhum teste de máscara/PII sobre `/verificar-conflito` (o de `/checar-conflito`
   existe via #528).
4. `pending-items` sem qualquer teste.

## Riscos residuais e limitações desta auditoria

- Análise **estática**: os 500 do achado 1 são certos pela combinação código ×
  migration, mas não foram reproduzidos contra um banco de pé nesta sessão.
- `sociedades_cliente.py` foi revisado em estrutura (gates, máscara de documento
  de sócio, soft delete, audit) sem linha a linha dos 10 endpoints; nada de
  anômalo encontrado no que foi lido.
- Integrações que **consomem** clientes (casos, financeiro, WhatsApp, DataJud)
  ficaram fora do escopo — só as junções diretas foram verificadas.

## Decisões que cabem ao titular

1. **Achado 4**: dossiê por titularidade (advogado vê a própria carteira) ou
   gestão-only com frontend ajustado?
2. **Achado 5**: exclusão de cliente deve bloquear com caso ativo (como a
   anonimização) ou apenas desativar o portal?
3. **Achado 8**: o papel `financeiro` deve ter visão total dos relatórios
   financeiros de clientes (hoje a autorização existe mas nunca passa do gate)?
