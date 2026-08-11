# Parte 20 — Configurações, Lixeira e módulos de apoio

**Data:** 2026-08-11
**Método:** leitura do código-fonte. Nenhum ambiente executado, nenhuma chamada a produção.
**Última parte** da auditoria de código iniciada na Parte 14. Fecha a cobertura.

Cobre: configuração de módulos, lixeira, checklists, produtividade e o conteúdo dos contratos do
escritório (a Parte 17 tinha visto apenas o RBAC).

---

## CFG-01 (P2) — O desligamento de módulo é aplicado no frontend; a API continua aberta

**Evidência.** `SystemModuleSetting` é gravado por `PUT /system-modules/settings/{key}`
(`routers/module_settings.py:79-137`), com `require_admin`, proteção de módulos estruturais
(409 em `PROTECTED_MODULE_KEYS`) e audit log.

Os únicos arquivos do backend que tocam o model são o próprio router, seu schema, o model e
`models/__init__.py`. Em `main.py`, as duas únicas menções são o `import` e o
`include_router(module_settings.router, ...)` (`main.py:172,497`) — isto é, o registro do router de
configuração, não uma consulta ao ajuste. **Nenhum middleware, dependency ou router consulta
`SystemModuleSetting` para bloquear coisa alguma.**

Do outro lado, o frontend **aplica de verdade**: `stores/moduleLifecycle.ts` carrega `GET
/system-modules/settings`, e `frontend/src/components/ModuleLifecycleGate.tsx:49-59` envolve a área
staff e **redireciona** (`Navigate`) quando `enabled=false` ou `status="disabled"` — então link
salvo e navegação direta também são barrados, não só o item de menu.

**Impacto.** O que resta aberto é a API: um cliente HTTP autenticado com o papel adequado alcança
os endpoints do módulo desligado. Segundo `docs/auditorias/module_lifecycle_20260710.md:45-51`,
esse é o desenho declarado — gate de rota no frontend, RBAC autoritativo no backend —, o que
rebaixa o achado de defeito para **lacuna de defesa em profundidade**.

Ainda assim vale registrar: a lista de módulos é onde se desliga o que não está pronto, e nesse
caso "não pronto" costuma significar que gravar é indesejável, não só navegar.

**Nota de retificação:** a primeira redação classificava isto como P1 e afirmava que link salvo
passava. Estava errado — o `ModuleLifecycleGate` cobre esse caso. Apontado na revisão do PR #1060.

**Correção sugerida.** Um dependency global que consulte os ajustes (com cache curto) e devolva
404/503 nos prefixos desligados, respeitando `PROTECTED_MODULE_KEYS`. O gate `menu_visible` pode
seguir só visual, mas `enabled=false` precisa fechar a porta.

---

## LIX-01 (P1) — A lixeira não purga, e o expurgo que existe não cobre as entidades dela

**Evidência.** `routers/trash.py` tem exatamente dois endpoints: `GET /trash/` (`:39`) e
`POST /trash/{entidade}/{id}/restaurar` (`:62`). Não há rota de exclusão definitiva em nenhum
lugar do arquivo — que tem 79 linhas no total.

**O que existe** (e a primeira redação deste achado ignorou):

- **`POST /clients/{client_id}/esquecimento`** (`backend/app/routers/clients.py:914`) com
  `services/client_anonimizacao.py` — anonimização irreversível do titular, com verificação prévia
  de bloqueios (`/esquecimento/bloqueios`, `clients.py:892`) e trilha. É o atendimento ao art. 18,
  VI da LGPD, e **funciona** para o cliente.
- **`_purgar_dados_lgpd`** (`backend/app/services/scheduler.py:1165`) — retenção por
  `RETENCAO_CLIENTE_ANOS` (default 5), mas aplica **soft delete** (`UPDATE clients SET deleted_at
  = NOW()`), não eliminação.
- **`entrada_expurgo_service.expurgar_rascunhos_entrada_unica`** — `db.delete()` real, porém
  restrito a rascunhos órfãos da Entrada Única.

**O que falta, e é o achado.** Nenhum desses caminhos toca as **outras oito entidades da lixeira**
(`trash.py:24-33`: `Case`, `Document`, `LegalDoc`, `Fee`, `Procuracao`, `EnvironmentalCase`,
`Task`). Um caso, um documento ou um honorário enviado à lixeira permanece indefinidamente, e a
retenção de cliente só troca um estado por outro dentro da mesma tabela. O art. 16 da LGPD (Lei
13.709/2018, vigente desde 18/09/2020) exige eliminação após o término do tratamento — e para
essas entidades não há política declarada nem mecanismo.

**Ressalva honesta:** guarda documental tem prazos próprios, e apagar dado de caso encerrado não é
decisão de software. O achado é a ausência de política e de caminho para as entidades restantes,
não a ausência de um botão.

**Nota de retificação:** a primeira redação afirmava que "não existe caminho no sistema para
eliminar de fato o dado" e que um pedido de titular "não pode ser atendido". Estava errado — o
fluxo de esquecimento existe e atende. O erro veio de concluir pela ausência olhando só
`trash.py`, contrariando a regra do próprio `CLAUDE.md` de confirmar antes de afirmar que algo não
existe. Apontado na revisão do PR #1060.

**Correção sugerida.** Purga definitiva restrita a `superadmin`, com motivo obrigatório, trilha e
confirmação — e uma política de retenção declarada que diga o que pode ser purgado e quando.

---

## LIX-02 (P1) — A restauração é de uma linha só, sem as relações

**Evidência:** `routers/trash.py:71-78`

```python
r = (await db.execute(select(Model).where(
    Model.id == registro_id, Model.deleted_at.isnot(None)
))).scalar_one_or_none()
...
r.deleted_at = None
```

Um registro, um campo. Nada percorre o grafo do objeto.

**Impacto.** Restaurar um caso devolve o caso — não seus prazos, documentos ou honorários. E na
direção inversa, o problema já era conhecido: a auditoria externa registrou que **a exclusão de um
caso não cascateia para suas peças** (Retificações do `README.md`), o que gerou 75 peças órfãs.

Somando as duas pontas: a exclusão não desce pelas relações e a restauração também não. O
resultado é que caso e filhos podem ficar em estados inconsistentes nos dois sentidos — filhos
ativos com pai excluído, ou pai restaurado com filhos ainda na lixeira. Nada no sistema detecta
nem reporta essa inconsistência (o `/diagnostico/integridade` verifica vínculos, mas não vi
cobertura específica deste caso — não confirmei).

Também é possível restaurar um prazo cujo caso continua excluído: a query filtra apenas
`deleted_at` do próprio registro.

**Correção sugerida.** Restauração transacional por agregado (caso → prazos, documentos,
honorários e peças excluídos no mesmo ato), usando o `deleted_at` como marca de lote — o que exige
registrar o momento da exclusão em cascata.

---

## LIX-03 (P2) — A lixeira não diz quem excluiu

**Evidência:** a listagem devolve `{id, rotulo, excluido_em}` (`trash.py:55-58`). O `deleted_at` é
timestamp; não há `deleted_by` nos models.

O `criar_audit_log` registra a exclusão em outro lugar, mas a tela da lixeira não faz esse
cruzamento. Quem olha a lixeira vê o quê e o quando, nunca o quem — e "quem excluiu o cliente"
é exatamente a pergunta que se faz ao abrir uma lixeira.

---

## PRO-01 (P2) — Produtividade conta horas de casos excluídos

**Evidência:** `routers/produtividade.py:55-61`

```sql
FROM time_entries t JOIN cases c ON c.id = t.case_id
WHERE t.deleted_at IS NULL AND t.data >= :desde
GROUP BY c.area
```

O filtro cobre `t.deleted_at`, mas o `JOIN` com `cases` não filtra `c.deleted_at`. Horas lançadas
em casos excluídos continuam somando na distribuição por área.

**Impacto.** Baixo em valor absoluto, mas é a classe "o painel diverge da listagem" já
identificada: a área aparece com horas que não correspondem a nenhum caso visível. `produtividade.py`
também não registra trilha (`criar_audit_log` = 0 ocorrências), o que é aceitável para módulo de
leitura.

---

## CON-01 (P2) — Contratos do escritório repetem o padrão frágil de `despesas.py`

**Evidência:** `routers/office_contracts.py:59-88` — o `POST` recebe `body: dict` e valida apenas
a presença de três campos (`title`, `counterparty`, `start_date`). O restante entra por
`body.get()` direto no `INSERT`, incluindo `value` (monetário) sem tipo, sinal ou faixa. Não há
schema Pydantic. `criar_audit_log` não aparece nenhuma vez no arquivo.

É exatamente o mesmo desenho de `despesas.py` (FIN-07, Parte 14): os dois routers financeiros
escritos em SQL bruto compartilham a fragilidade, enquanto `fees.py` — o vizinho — usa schema
Pydantic e audita quatro operações.

**Observação favorável:** o arquivo tem um comentário reconhecendo uma lacuna própria no `PATCH`
(`office_contracts.py:112`): *"Falta a checagem de EXISTÊNCIA: sem ela, um UPDATE por id..."* —
autoconsciência registrada no código, que vale confirmar se virou correção.

---

## O que está bom nesta faixa

**Checklists é o módulo mais bem fechado dos cinco.** `verificar_acesso_caso` gate tanto a
instanciação (`checklists.py:212`) quanto a geração por IA (`:292`), e o comentário registra o
IDOR que isso corrigiu: *"caso podia gerar checklist para caso alheio"*. Três pontos de trilha, e
o checklist gerado por IA nasce como **rascunho** — HITL preservado.

**A lixeira tem o RBAC certo e não aceita entidade arbitrária.** `require_roles(["superadmin",
"admin", "socio"])` nos dois endpoints, e o `ENTIDADES` é uma whitelist explícita
(`trash.py:24-33`) — sem ela, o parâmetro `entidade` seria um caminho para alcançar qualquer
model. A restauração é auditada.

**A configuração de módulos é auditável, ainda que não seja aplicada.** `require_admin` na
escrita, `PROTECTED_MODULE_KEYS` impedindo desligar módulo estrutural (409), e audit log em
criação, alteração e remoção. O que falta é o backend consultar o que foi gravado.

---

## Cobertura final

| Frente | Parte |
|---|---|
| Financeiro (consolidado, despesas, honorários, calculadoras) | 14 |
| Prazos e intimações | 14 |
| Portal do Cliente | 15 |
| Assinaturas eletrônicas | 15 |
| Notificações | 16 |
| NFS-e | 17 |
| Gestão societária (escritório e clientes) | 18 |
| Estimador de honorários OAB | 19 |
| Central de Diagnóstico | 19 |
| Configurações de módulos, Lixeira, Checklists, Produtividade, Contratos | **20** |

A consolidação dos achados das sete partes está em
`docs/auditoria/FECHAMENTO-auditoria-codigo-2026-08.md`.
