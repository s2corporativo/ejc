# Parte 16 — Notificações (auditoria de código-fonte)

**Data:** 2026-08-11
**Método:** leitura do código-fonte. Nenhum ambiente executado, nenhuma chamada a produção.
**Continuação** das Partes 14 (Financeiro e Prazos) e 15 (Portal e Assinaturas).

**Por que este módulo veio antes de NFS-e e da gestão societária:** a Parte 15 mostrou que o
`AuthMiddleware` (`backend/app/core/auth_middleware.py:192-198`) libera `/api/notifications` ao
perfil `cliente_externo`. É uma das quatro superfícies que o público externo do sistema alcança —
junto com o portal, as assinaturas e `/api/users/me`. Superfície externa vem antes de módulo
interno.

---

## Isolamento: correto, sem vazamento entre usuários

Toda consulta filtra por `Notification.user_id == cu.id`, derivado do usuário autenticado e nunca
do request: listagem (`notifications.py:45,54`), marcar lida (`notifications.py:130`), marcar
todas (`notifications.py:146`), dispositivos de push (`notifications.py:186,208`).

Há inclusive guarda contra sequestro de dispositivo em `notifications.py:242-243`:

```python
if existente and existente.user_id != cu.id:
    raise HTTPException(409, "Este dispositivo já está associado a outra conta")
```

sem a qual um endpoint de push registrado com o mesmo `endpoint` reatribuiria o dispositivo a
outra conta.

**Conclusão:** o cliente externo que alcança `/api/notifications` vê apenas as próprias
notificações. Não encontrei vazamento entre usuários nem entre clientes.

---

## NOT-01 (P1) — Notificações se acumulam para sempre: sem deduplicação, sem retenção, sem arquivamento

**Evidência.** `criar_notificacao_interna` (`backend/app/services/notification_service.py:27-38`)
sempre insere linha nova — não há consulta por notificação equivalente já pendente:

```python
n = Notification(
    id=str(uuid4()), user_id=user_id,
    titulo=titulo, mensagem=mensagem, tipo=tipo, link=link,
)
db.add(n)
await db.commit()
```

E o model (`backend/app/models/notification.py:12-34`) não tem `expires_at`, `arquivada`, nem
qualquer chave de deduplicação. Os campos são `lida` e `lida_em` — e nada, em nenhum lugar do
backend, apaga ou arquiva notificação lida ou antiga.

**Impacto.** O sino é um acumulador monotônico. As 141 não lidas **relatadas pelo titular** (observação de tela, não verificada por esta auditoria)
não são defeito de um gerador específico: são o resultado esperado de um sistema que só cria e nunca compacta. Existe
`POST /notifications/ler-todas` (`notifications.py:139`), então dá para zerar o contador — mas isso
é o usuário limpando à mão o que o sistema deveria administrar.

**Ângulo LGPD, que é o mais sério aqui.** `Notification.mensagem` é `Text` livre e os geradores
escrevem contexto de caso nele (o alerta de prazo grava o título do prazo, que costuma
identificar a parte). Sem política de retenção, essas linhas ficam indefinidamente numa tabela que
ninguém revisa — a minimização é exigência do art. 6º, III, da LGPD (Lei 13.709/2018, vigente desde 18/09/2020) e a
eliminação após o término do tratamento é exigência do art. 16 — nenhuma das duas tem mecanismo
aqui. (O art. 6º, V trata de qualidade dos dados; a primeira redação o citava por engano.)

**Correção sugerida.** Retenção com purga de lidas após N dias e arquivamento de não lidas
antigas; e, para os alertas repetitivos, chave de deduplicação (`user_id`, `tipo`, entidade de
origem) que atualize a notificação existente em vez de criar outra.

---

## NOT-02 (P1) — `notificar()` comita a sessão do chamador no meio da transação dele

**Evidência.** `criar_notificacao_interna` faz `await db.commit()` dentro do helper
(`notification_service.py:37`), usando a **mesma** `AsyncSession` que o chamador passou. Quem
chama `notificar(db, ...)` no meio de uma operação de negócio tem suas alterações pendentes
comitadas junto, antes de a operação terminar.

São 22 chamadas a `notificar(` no backend, entre serviços e routers —
`services/cobranca_cliente_service.py`, `services/scheduler.py`, `services/datajud_sync_service.py`,
`routers/portal_documentos.py`, `routers/solicitacoes_documentos.py`, `routers/atendimentos.py`,
entre outros.

**Impacto.** É a classe de defeito recorrente do EJC — gravação não transacional entre registros
relacionados — instalada no ponto único de notificação. Se o fluxo falhar **depois** da
notificação, o rollback não desfaz o que o commit interno já persistiu: fica o registro de negócio
pela metade e a notificação avisando sobre ele.

**O projeto já sabe, e documentou.** A docstring de `_marcar_prazos_vencidos`
(`backend/app/services/scheduler.py:167-172`) descreve a consequência exata com precisão:

> "Limite conhecido: `notificar()` COMMITA internamente ao gravar o sino
> (criar_notificacao_interna), persistindo junto o UPDATE pendente→vencido; se a falha ocorrer
> DEPOIS desse commit interno (ex.: canal externo), o rollback não desfaz a transição e o alerta
> NÃO é retentado amanhã."

Registro isso como achado ainda assim por dois motivos. Primeiro, o limite está documentado num
único chamador, e vale para os 22. Segundo, no scheduler o efeito é um alerta perdido; num router
que grava documento, solicitação ou atendimento antes de notificar, o efeito é registro de negócio
comitado pela metade.

**Correção sugerida.** `criar_notificacao_interna` faz `flush`, não `commit`, e a transação fecha
no chamador; para os pontos que precisam de commit próprio (scheduler, tarefas de fundo), sessão
separada em vez da sessão do fluxo.

---

## Os alertas de prazo são idempotentes — e isso é uma correção de rumo

A Parte 14 encerrou sem verificar se algum job avisa prazo vencendo. Verificado agora: avisa, e
com cuidado.

`_alertar_prazos` (`backend/app/services/scheduler.py`) roda 07:15 em três faixas **disjuntas**
com flag persistida por faixa:

```python
for dias, piso, flag in [(7, 4, "alerta_7d_enviado"),
                         (3, 2, "alerta_3d_enviado"),
                         (1, 0, "alerta_1d_enviado")]:
```

O comentário registra o bug que essa forma corrigiu: antes, faixas sem piso faziam um prazo criado
perto do vencimento satisfazer as três de uma vez e disparar "e-mail/WhatsApp/push em triplicata".
Com piso mais flag, cada prazo recebe no máximo três avisos de *aproximação*, um por marco — mais,
eventualmente, um quarto aviso de *vencimento*, disparado por `_marcar_prazos_vencidos`, que usa
guarda própria (a transição `pendente→vencido`) e não reaproveita as flags de faixa.

`_marcar_prazos_vencidos` roda 07:10, antes, e transiciona `pendente→vencido` com guarda de
idempotência no próprio `UPDATE` (`WHERE id=:id AND status='pendente'`), disparando um único
alerta. A docstring explica que isso existe porque nada escrevia `status='vencido'` — a aba
"Vencidos" ficava sempre vazia e prazo já vencido nunca era alertado.

**Consequência para o NOT-01:** os alertas de prazo **não** explicam as 141 não lidas. Eles são
limitados por construção. O acúmulo vem da ausência de retenção, não de um gerador desgovernado.

**Ressalva que permanece:** tudo isso depende do APScheduler estar ligado. O `CLAUDE.md` registra a
premissa de worker único e `ENABLE_SCHEDULER`; com o scheduler desligado, não há alerta de prazo
nenhum, e o módulo de Prazos não tem como sinalizar essa condição ao advogado. Não verifiquei a
configuração de produção — está fora do alcance desta auditoria.

---

## O que está bom em Notificações

`notificar()` (`notification_service.py:170-258`) é um ponto único de entrega bem desenhado, e a
docstring define a semântica sem ambiguidade: sino interno para tipos mandatórios mesmo com
categoria desativada; quiet hours suprimem canais externos mas nunca o sino; `forcar_sino` garante
o registro interno sem abrir canal externo; falha de um canal não derruba os outros nem o fluxo.

A distinção entre "mandatório" e "preferência do usuário" é a decisão certa para o domínio: alerta
jurídico crítico não pode ser silenciado por configuração pessoal, e o código implementa isso em
vez de apenas afirmá-lo.

Os canais externos seguem o padrão do repositório — `EMAIL_ENABLED`, `PUSH_ENABLED` +
`VAPID_PRIVATE_KEY`, WhatsApp — todos opt-in por env com no-op seguro quando desligados.

---

## Estado da cobertura da auditoria

| Frente | Situação |
|---|---|
| Financeiro (consolidado, despesas, honorários, calculadoras) | Parte 14 |
| Prazos e intimações | Parte 14 |
| Portal do Cliente | Parte 15 |
| Assinaturas eletrônicas | Parte 15 |
| Notificações | **Parte 16** |
| NFS-e | pendente |
| Contratos do escritório e gestão societária | pendente |
| Estimador de honorários OAB | pendente |
| Configurações, Lixeira, Diagnóstico, Checklists, Produtividade | pendente |

As quatro superfícies alcançáveis pelo `cliente_externo` estão agora auditadas: portal (Parte 15),
assinaturas (Parte 15), notificações (esta parte) e `/api/users/me`, cujo escopo é o próprio
usuário. **Nenhuma delas apresentou vazamento entre clientes.** O que resta na fila é módulo
interno, e a prioridade passa a ser o risco fiscal e contratual: NFS-e, contratos e sociedade.
