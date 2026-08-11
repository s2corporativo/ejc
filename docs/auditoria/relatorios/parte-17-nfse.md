# Parte 17 — NFS-e (auditoria de código-fonte)

**Data:** 2026-08-11
**Método:** leitura do código-fonte. Nenhum ambiente executado, nenhuma chamada a produção,
nenhuma nota emitida.
**Continuação** das Partes 14 (Financeiro e Prazos), 15 (Portal e Assinaturas) e 16 (Notificações).

---

## A pergunta central: emite nota de verdade?

**Sim.** Não é fachada. Há integração real com a **Nuvem Fiscal**
(`backend/app/services/nfse/nuvem_fiscal.py`, 312 linhas), montando a DPS do padrão nacional
(`infDPS`) e falando com o provedor por HTTP.

O módulo é `NFSE_ENABLED=false` por default e nasce em homologação — o `get_provider()`
(`services/nfse/__init__.py:31-50`) recusa com 503 quando desligado e com 422 quando o provedor
é desconhecido, e o texto do erro é explícito: *"a emissão fiscal nasce DESLIGADA e em
homologação — a ativação é uma decisão do dono."* Segue o padrão do repositório para integração
externa (flag opt-in, degradação graciosa), aplicado à área mais sensível do sistema.

Existe ainda um caminho paralelo: `POST /nfse/manual` registra nota emitida **fora** do sistema,
no Emissor Nacional gov.br. É uma saída pragmática enquanto a emissão automática não é ligada.

**Antes de ligar em produção, três decisões fiscais estão embutidas no código e precisam do
contador.** É o núcleo desta parte.

---

## NFS-01 (P0) — Regime tributário fixado em código como Simples Nacional

**Evidência:** `backend/app/services/nfse/nuvem_fiscal.py:221-226`

```python
"prest": {
    "CNPJ": self._cnpj,
    # regTrib padrão (Simples Nacional optante) — CONFIRMAR com o
    # contador antes de produção; muda a base de cálculo da DPS.
    "regTrib": {"opSimpNac": 1, "regEspTrib": 0},
},
```

**Ressalva de verificação:** a leitura de que `opSimpNac: 1` significa optante do Simples Nacional
vem do comentário no próprio código; `docs/NFSE_VIABILIDADE.md:96` registra que os valores desses
enums ainda carecem de confirmação contra o schema oficial da DPS. O achado permanece porque o
valor está **fixo** independentemente do significado — mas a semântica exata precisa ser conferida
na fonte oficial antes da correção.

**Impacto.** O regime tributário do emitente está fixo no código, não em configuração. Se o
escritório não for optante do Simples Nacional, **toda nota emitida declara regime errado** — e o
próprio comentário registra a consequência: muda a base de cálculo da DPS. Documento fiscal com
regime incorreto é problema de obrigação acessória, não de software.

O comentário é honesto e o autor sabia do risco. Mas "confirmar com o contador" é uma instrução
para uma pessoa, dentro de um arquivo que ninguém relê antes de ligar uma flag de ambiente. O
gate `NFSE_ENABLED` protege contra emitir cedo demais; não protege contra emitir com o regime
errado depois de ligado.

**Correção sugerida.** `NFSE_REGIME_TRIBUTARIO` em configuração, **sem default**, com o boot
falhando se `NFSE_ENABLED=true` e o regime não estiver declarado — mesmo padrão que o projeto já
usa para `SECRET_KEY` e chaves de PII em produção.

---

## NFS-02 (P0) — Retenção de ISS fixada em "não retido"

**Evidência:** `backend/app/services/nfse/nuvem_fiscal.py:239-243`

```python
"tribMun": {
    "tribISSQN": 1,            # 1 = operação tributável
    "cLocIncid": cmun_prest,
    "pAliq": round(float(aliq), 4),
    "tpRetISSQN": 1,           # 1 = ISS não retido
}
```

**Base legal.** LC 116/2003, art. 6º: Municípios e o DF podem, por lei municipal, atribuir ao
**tomador** a responsabilidade pela retenção e recolhimento do ISS — e o tomador responde pelo
imposto ainda que não tenha retido. Para optante do Simples Nacional há regra própria (LC 123/2006,
art. 21, §4º): o tomador aplica a alíquota efetiva informada **no documento fiscal**; se a NFS-e
não a informar, aplica-se a maior alíquota do anexo. Ou seja, o campo depende também do município
do tomador — o que reforça que não pode ser constante.

**Impacto.** A retenção do ISS não é uma propriedade do emitente: depende do tomador e do
município. Há tomadores pessoa jurídica legalmente obrigados a reter o ISS na fonte. Com
`tpRetISSQN` fixo em "não retido", **a nota emitida para esse tomador sai errada** — e a
divergência aparece na escrituração do tomador, não na do escritório, o que atrasa a descoberta.

Pela mesma razão, `tribISSQN: 1` ("operação tributável") fixo não comporta operação imune,
isenta ou com exigibilidade suspensa.

**Correção sugerida.** Ambos os campos vêm do pedido, com default de configuração e possibilidade
de sobrescrever por nota (o `NFSePedidoEmissao` já tem o padrão para isso em
`aliquota_iss`/`item_lista_servico`).

---

## NFS-03 (P1) — Valor e alíquota da nota passam por `float` e arredondamento bancário

**Evidência:** `backend/app/services/nfse/nuvem_fiscal.py:237,242`

```python
"vServPrest": {"vServ": round(float(pedido.valor), 2)},
...
"pAliq": round(float(aliq), 4),
```

**Impacto.** Dois problemas somados, exatamente na fronteira em que o número deixa de ser interno
e vira declaração fiscal:

1. **`float()` desfaz a disciplina `Decimal`** que o resto do financeiro mantém deliberadamente.
   O router faz a coisa certa até o último passo — `valor=Decimal(str(valor))`
   (`routers/nfse.py:679`) — e o adapter converte para binário logo em seguida.
2. **`round()` do Python é arredondamento bancário** (metade para o par), não `ROUND_HALF_UP`.
   `round(2.675, 2)` devolve `2.67`. O consolidado financeiro usa `ROUND_HALF_UP` explicitamente
   (`financeiro_consolidado.py:23-29`, ver Parte 14).

Resultado: o valor declarado na nota pode divergir em um centavo do honorário registrado no
sistema, com regra de arredondamento diferente da usada em todo o resto do módulo financeiro.

**Correção sugerida.** `quantize(Decimal("0.01"), ROUND_HALF_UP)` e serializar como string ou via
`float()` só na última linha, sem `round()`.

---

## NFS-04 (P1) — Nota presa em `processando` bloqueia o faturamento do honorário para sempre

**Evidência.** A reconciliação com o provedor acontece **apenas na leitura** de uma nota
(`routers/nfse.py:716-730`): `GET /nfse/{id}` consulta o provedor se o status for `processando`.
Não há job de reconciliação — nenhuma referência a NFS-e em `services/scheduler.py` nem em
tarefas Celery.

Ao mesmo tempo, `_STATUS_ATIVOS = (processando, autorizada)` (`routers/nfse.py:101`) é o que
bloqueia nova emissão para o mesmo honorário (`routers/nfse.py:580-581`).

**Impacto.** Se a chamada ao provedor retornar `processando` e ninguém abrir aquela nota, ela
permanece `processando` indefinidamente — e o honorário fica **impossível de faturar**, com 409
("Já existe NFS-e em emissão para este honorário") a cada tentativa. O desbloqueio depende de
alguém saber que precisa abrir a nota específica para forçar a consulta.

É a classe já identificada no EJC de "monitoramento afere execução, não resultado", numa variante
nova: aqui não há nem monitoramento — o estado só avança se um humano olhar.

**Correção sugerida.** Job periódico que reconcilia notas em `processando` há mais de N minutos, e
alerta quando uma passa de um limite de tempo.

---

## NFS-05 (P2) — Endereço do tomador é coletado e descartado

**Evidência:** `NFSeTomador` (`services/nfse/base.py:19-31`) aceita `logradouro`, `numero` e
`bairro`, mas `_montar_dps` monta o endereço só com `cMun`, `UF` e `CEP`
(`nuvem_fiscal.py:204-208`). Os três campos nunca entram no payload.

**Impacto.** Baixo enquanto o provedor aceitar o endereço reduzido; se alguma prefeitura exigir
endereço completo, a rejeição vai apontar para um dado que o sistema **tinha** e não enviou.
Campo de entrada que não chega ao destino é armadilha para quem for depurar a rejeição.

---

## O que está bom em NFS-e (e é bastante)

**O fluxo de emissão é um dos mais bem construídos do repositório.**

*Idempotência real, não aparente.* `referencia = fee-<id>` com `UNIQUE(provider, referencia)` no
banco, e a linha é criada em `processando` e **comitada antes de tocar o provedor**
(`routers/nfse.py:669-676`): a corrida é fechada pelo banco, não por verificação em memória. Duas
requisições simultâneas para o mesmo honorário resultam em `IntegrityError` → 409, sem segunda
emissão real. Estados terminais (`rejeitada`, `cancelada`) permitem reaproveitar a linha para
reemitir (`routers/nfse.py:632-634`).

*Trilha antes e depois.* O audit log da **intenção** de emitir é gravado e comitado antes da
chamada externa (`routers/nfse.py:661-667`), com o motivo declarado: se o provedor falhar, a
tentativa não se perde. Na falha, grava `NFSE_EMISSAO_FALHOU` e marca a nota como `rejeitada`
para não deixar a referência presa (`routers/nfse.py:684-696`).

*Ordem das validações pensada.* O tomador é resolvido **depois** do short-circuit de idempotência
e **antes** do commit da reserva, com o comentário explicando: se faltar tomador (422), a
transação é descartada sem deixar a referência presa em `processando`.

*RBAC estratificado.* Emissão e cancelamento exigem `socio+`; leitura exige perfil financeiro,
porque a nota expõe honorários e CPF/CNPJ. Erros carregam código e mensagem do provedor mas
**nunca credencial ou token** — promessa declarada em `services/nfse/base.py:1-8`.

---

## Contratos do escritório e retiradas de sócio — verificação parcial

Não é a auditoria completa desses módulos, que segue pendente. Verifiquei apenas o controle de
acesso, por ser o risco imediato em dado societário.

`office_contracts.py:10-20` restringe a `{superadmin, admin, socio, financeiro}` por dependency no
router inteiro. `partner_withdrawals.py:12` restringe a `{superadmin, socio}` — mais estrito, o
que é correto para pró-labore e retiradas —, e `partner_withdrawals.py:65` impede que um sócio
lance retirada em nome de outro (só `superadmin` pode).

**Uma observação de robustez, verificada e descartada como defeito.** `partner_withdrawals.py`
compara o enum direto com strings (`current_user.role not in PRIVILEGED`), sem o `.value` que o
resto do repositório usa. Confirmei que **funciona**: `UserRole` é `(str, enum.Enum)`
(`models/user.py:9-18`) e todo membro tem nome igual ao valor, então a busca no `set` casa. Não é
bug hoje. É frágil: depende de uma coincidência entre nome e valor do enum. Se a comparação um dia
quebrasse, `not in` passaria a ser sempre verdadeiro e o módulo **falharia fechado** (403 para
todos) — a direção segura.

Ficam pendentes as perguntas de fundo: a soma das participações do cap table valida 100%, o
cálculo de pró-labore, e a trilha de auditoria de alteração de quotas.

---

## Estado da cobertura da auditoria

| Frente | Situação |
|---|---|
| Financeiro (consolidado, despesas, honorários, calculadoras) | Parte 14 |
| Prazos e intimações | Parte 14 |
| Portal do Cliente | Parte 15 |
| Assinaturas eletrônicas | Parte 15 |
| Notificações | Parte 16 |
| NFS-e | **Parte 17** |
| Contratos do escritório e gestão societária | **parcial** (só RBAC, nesta parte) |
| Estimador de honorários OAB | pendente |
| Configurações, Lixeira, Diagnóstico, Checklists, Produtividade | pendente |

**Recomendação de sequência para o titular:** NFS-01 e NFS-02 são decisões de contador, não de
programador. Valem uma conversa antes de qualquer linha de código — e antes de `NFSE_ENABLED=true`
em produção. O fluxo está implementado para **homologação**; não está pronto para produção enquanto NFS-01 e
NFS-02 seguirem abertos. O que falta não é código — é confirmar **o que** ele vai declarar.
