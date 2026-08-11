# Parte 15 — Portal do Cliente e Assinaturas Eletrônicas (auditoria de código-fonte)

**Data:** 2026-08-11
**Método:** leitura do código-fonte no repositório. Nenhum ambiente foi executado e nenhuma
chamada foi feita a produção.
**Continuação da Parte 14**, que cobriu Financeiro e Prazos/Intimações.

**Cobertura:** Portal do Cliente (isolamento, dashboard, documentos, financeiro, mensagens) e
Assinaturas Eletrônicas (natureza da assinatura, trilha, fluxo).

---

## O achado principal: a chance de êxito NÃO vaza para o cliente

Este era um dos cinco "achados que não podem se perder" do `README.md` da auditoria, em aberto
desde a Parte 9. A métrica de "chance de êxito" **está presente no código analisado** (a Parte 9 a
observou em produção; esta auditoria não acessou produção), e precisava ser confirmado
que não é exposta ao cliente no portal**.

**Fundamento correto, e uma retificação.** A vedação a prometer resultado está no **Provimento OAB
nº 205/2021, art. 6º e parágrafo único** (publicidade da advocacia), em vigor: é vedada, em
qualquer publicidade, a menção à promessa de resultados. A primeira redação repetia a citação do
`README.md` da auditoria — "Código de Ética da OAB, art. 6º, parágrafo único, e art. 34, XXIX" —,
que aponta para a Lei 8.906/1994 (Estatuto), cujo art. 34, XXIX trata de matéria diversa.
Corrigido na revisão do PR #1060.

**Confirmado: não é exposta.** Há duas barreiras independentes.

**1. O portal devolve allowlist de campos, não o objeto do caso.**
`backend/app/routers/portal.py:106-112` — o detalhe do caso monta a resposta campo a campo:

```python
"caso": {
    "numero_interno": c.numero_interno, "titulo": c.titulo,
    "status": ..., "numero_processo": c.numero_processo,
    "comarca": c.comarca, "vara": c.vara,
},
```

Seis campos, todos factuais. Nada de prognóstico, valor da causa, honorários internos ou
anotações. Um `model_dump()` do `Case` teria vazado tudo; a escolha aqui foi a oposta.

**2. A tela que exibe a métrica é staff-only, e a API está fora do alcance do cliente.**
A métrica vive em `frontend/src/pages/EntrevistaInteligente.tsx:446-465` (percentual com barra
colorida por faixa: ≥70 verde, ≥40 amarelo). A rota é registrada em `STAFF_ROUTES`
(`frontend/src/config/moduleRegistry.tsx:438-452`) como `/casos/:id/entrevista`, com
`sensitive: true`, `status: "hidden"` e `roles: ROLES.compliance`.

No backend, o `AuthMiddleware` (`backend/app/core/auth_middleware.py:191-204`) restringe o perfil
`cliente_externo` a seis prefixos:

```python
permitidos = ("/api/portal/", "/api/auth/", "/api/health",
              "/api/notifications", "/api/signatures", "/api/users/me")
```

`/api/triagem/` não está na lista — chamada direta do cliente recebe 403 antes de chegar ao
router. O gate de interface e o gate de API são independentes, então falhar um não abre o outro.

**O que isso não resolve.** A métrica continua existindo na tela do advogado, com barra colorida e
percentual em destaque. O parecer arquitetural já questiona seu mérito; esta auditoria conclui
apenas que **ela não chega ao cliente pelo sistema**. O risco ético remanescente é de uso humano
— o advogado repetir o número ao cliente —, não de vazamento por software.

---

## Portal do Cliente

### O isolamento está correto

Todo endpoint deriva o `client_id` **do usuário autenticado**, nunca do request
(`backend/app/routers/portal.py:26-30`):

```python
def _exigir_cliente(cu) -> str:
    """Garante perfil cliente_externo com vínculo; retorna client_id."""
    if cu.role != UserRole.cliente_externo or not cu.client_id:
        raise HTTPException(...)
    return cu.client_id
```

Esse `client_id` entra em todas as consultas: `/meus-casos` (`portal.py:41`), `/casos/{id}`
(`portal.py:88`), `/documentos` (`portal.py:132`), `/financeiro` (`portal.py:152`) e mensagens
(`portal.py:200`). Rotas com `case_id` na URL passam por `_caso_do_cliente`
(`portal.py:173-180`), que confere o vínculo caso→cliente antes de responder.

**Não encontrei IDOR no portal.** O padrão que produz IDOR — aceitar `client_id` ou `case_id` do
request e confiar nele — não ocorre em nenhuma das rotas. Somado ao allowlist de prefixos do
middleware, o resultado é a área mais bem defendida que li nas Partes 14 e 15.

### POR-01 (P1) — Documento vira visível ao cliente por confidencialidade, não por publicação

**Evidência:** `backend/app/routers/portal.py:123-136`

```python
"""Apenas docs do cliente com confidencialidade NORMAL (liberados)."""
select(Document).where(
    Document.client_id == client_id,
    Document.deleted_at.is_(None),
    Document.confidencialidade == DocConfidencialidade.normal,
)
```

**Impacto.** Não existe ato de publicação: qualquer documento vinculado ao cliente cujo campo
`confidencialidade` seja `normal` aparece no portal automaticamente. Se `normal` for o default de
upload, minuta de trabalho, rascunho e documento recebido de terceiro passam a ser visíveis sem
que ninguém tenha decidido mostrá-los. O controle existe, mas é por omissão — o inverso do que se
espera de compartilhamento com cliente.

**Estado no repositório:** o PR **#758** ("publicação explícita de documento no Portal do Cliente")
está aberto e trata exatamente disso. Este achado registra o comportamento do código na `main`
hoje; a correção já tem dono e não deve virar Issue nova.

### POR-02 (P2) — O cliente vê apenas prazos pendentes

**Evidência:** `backend/app/routers/portal.py:100-104` — a lista de "próximas datas" filtra
`Deadline.status == "pendente"`.

Prazo cumprido ou vencido não aparece. Para o cliente é uma agenda do que vem, não um histórico
— defensável como desenho. Registro porque tem efeito colateral: se o escritório perder um prazo,
o cliente não vê pelo portal. Se a intenção é transparência, o filtro precisa ser revisto; se a
intenção é agenda, está correto como está. É decisão do titular, não defeito.

### POR-03 (P2) — `float` no financeiro do portal

**Evidência:** `backend/app/routers/portal.py:157` — `"valor": float(f.valor) if f.valor else None`.

Fronteira de serialização, então o risco prático é baixo, mas destoa da disciplina do resto do
financeiro, que preserva `Decimal` até o `jsonable_encoder` deliberadamente e comenta a escolha
(ver Parte 14). Vale uniformizar para não servir de precedente.

### O que o cliente vê do financeiro

`portal.py:144-171` devolve descrição, valor, vencimento, data de pagamento e status dos
honorários **do próprio cliente**. Não expõe custo interno, margem, nem o consolidado do
escritório — que, aliás, é bloqueado por conjunto explícito de papéis
(`financeiro_consolidado.py:41-43`, ver Parte 14). Correto.

### Sanitização de andamento

`portal.py:114-117` corta um marcador interno antes de mostrar o andamento ao cliente:
`m.descricao.split(" [dj:")[0]`. Detalhe pequeno e revelador de cuidado — o dado interno não
vaza junto com o texto público.

---

## Assinaturas Eletrônicas

### Natureza: assinatura eletrônica simples com trilha de evidências — e é isso que é

**Evidência:** `backend/app/routers/signatures.py:191-233`.

O que é gravado no ato da assinatura: identidade pelo login autenticado (`sr.assinado_por_user`),
hash SHA-256 do arquivo (`sr.hash_sha256`), IP real do signatário, user agent e timestamp UTC.
O IP é extraído com `obter_ip_real(request)` — último salto do `X-Forwarded-For`, não o loopback
do Nginx —, com o motivo dito no comentário: "este IP é evidência probatória da assinatura
(MP 2.200-2)".

**Enquadramento.** Não é assinatura qualificada ICP-Brasil, e o código não afirma que seja. É
assinatura eletrônica com trilha de evidências. O art. 10, §2º, da MP 2.200-2/2001 admite meios
diversos da ICP-Brasil **desde que admitidos como válidos pelas partes ou aceitos pela pessoa a
quem o documento for oposto** — a validade é condicionada, não automática — modelo normal e defensável para documento entre escritório e cliente.
Para o que exige forma qualificada (peticionamento no PJe, por exemplo), **não serve**, e o
módulo não se propõe a isso.

**Recomendação de produto, não defeito:** a interface deveria dizer ao signatário qual é a
natureza do que ele está assinando. Não auditei a tela do portal para verificar se diz.

### ASS-00 (P0) — O signatário não consegue ler o documento que assina

**Evidência:** `frontend/src/pages/portal/PortalAssinaturas.tsx` exibe título e hash abreviado e
consome apenas `GET /signatures/` e `POST /signatures/{id}/assinar`. Não há link de download nem
visualização — não existe `href`, `download` ou `pdf` na tela. O backend, na listagem
(`signatures.py:121-189`), devolve metadados, não o conteúdo do arquivo.

Ao mesmo tempo, a confirmação apresentada ao cliente registra que *"serão registrados:
identificação, data/hora, IP e hash do arquivo"* e o fluxo pede o aceite.

**Impacto.** O cliente declara aceite de um documento que o sistema não lhe mostra. Isso é anterior
ao ASS-01: não se trata de provar que o arquivo não mudou, e sim de que **não há prova de que o
signatário teve acesso ao conteúdo** — que é o pressuposto da manifestação de vontade. Para um
aceite eletrônico cuja validade depende da admissão pelas partes (MP 2.200-2/2001, art. 10, §2º),
é o ponto mais frágil da trilha.

**Correção sugerida.** Servir o documento ao signatário no próprio fluxo (download ou visualizador
inline, autorizado pelo mesmo gate de `client_id`), e registrar na trilha o momento do acesso ao
conteúdo, não só o do aceite.

**Achado incorporado da revisão do PR #1060** — não constava da primeira redação.

### ASS-01 (P1) — O hash não é reconferido no momento da assinatura

**Evidência:** `signatures.py:214-220` — o fluxo usa `sr.hash_sha256`, gravado quando a
solicitação foi **criada** (`signatures.py:95`), e não recalcula o hash do arquivo no ato de
assinar. O comprovante devolve esse mesmo hash armazenado.

**Impacto.** Se o arquivo for substituído entre a criação da solicitação e a assinatura, o sistema
não percebe: o cliente assina uma tela que se refere a um hash que pode não corresponder mais ao
arquivo servido. O hash gravado prova o que foi registrado na criação, não o que foi exibido na
assinatura — e é justamente essa correspondência que dá valor probatório à trilha.

**Correção sugerida.** Recalcular o SHA-256 do arquivo no `assinar` e comparar com
`sr.hash_sha256`; divergência recusa a assinatura (409) em vez de gravá-la. Teste de regressão
com arquivo trocado no intervalo.

### ASS-02 (P1) — Não há cancelamento, expiração nem lembrete

**Evidência:** o router tem três endpoints — `POST /` (`signatures.py:48`), `GET /`
(`signatures.py:121`) e `POST /{sig_id}/assinar` (`signatures.py:191`). Não há rota de
cancelamento nem campo de validade no fluxo.

**Impacto.** Solicitação criada por engano, ou para o documento errado, fica pendente para sempre
e não pode ser retirada do portal do cliente. Não há prazo de validade nem cobrança automática.
Numa disputa, "pendente há oito meses" é um estado que o sistema não sabe distinguir de
"aguardando o cliente".

**Correção sugerida.** `POST /{sig_id}/cancelar` restrito a quem criou (advogado+), com motivo e
trilha; opcionalmente `expira_em` com varredura que marca `expirado`.

### ASS-03 (P2) — Um signatário por solicitação, e só cliente com conta

**Evidência:** `SignatureRequest` tem `client_id` único (`signatures.py:95`) e `assinar` exige
`cu.role == UserRole.cliente_externo` com `client_id` casado (`signatures.py:201-208`).

**Impacto.** Não existe fluxo multi-signatário, ordem de assinatura, nem signatário externo sem
conta no sistema (parte contrária, testemunha, sócio de cliente PJ). Contrato que precise de duas
assinaturas não é atendido pelo módulo. É limitação de escopo, não bug — mas contraria a
expectativa de "fluxo de assinatura com signatários e trilha", e precisa ser dita antes que
alguém tente usar o módulo para contrato bilateral.

### O que está bom em Assinaturas

O controle de acesso na criação é em camadas e o código explica por quê
(`signatures.py:61-83`): confere que o documento pertence ao cliente informado — direto por
`doc.client_id` ou pelo caso —, e ainda assim chama `verificar_acesso_caso` e
`obter_cliente_autorizado`, com o comentário registrando a ameaça que isso fecha ("um advogado que
conheça o par (document_id, client_id) alheio"). É defesa em profundidade escrita por quem pensou
no atacante.

A assinatura é transacional (um único `commit`), tem guarda de idempotência (409 em solicitação
já processada, `signatures.py:211-212`) e grava audit log com hash e IP.

---

## Estado da cobertura da auditoria

| Frente | Situação |
|---|---|
| Financeiro (consolidado, despesas, honorários, calculadoras) | Parte 14 |
| Prazos e intimações | Parte 14 |
| Portal do Cliente | **Parte 15** |
| Assinaturas eletrônicas | **Parte 15** |
| NFS-e | pendente |
| Contratos do escritório e gestão societária | pendente |
| Estimador de honorários OAB | pendente |
| Notificações | pendente — e é superfície alcançável pelo cliente externo (ver abaixo) |
| Configurações, Lixeira, Diagnóstico, Checklists, Produtividade | pendente |

**Pista para a próxima parte:** a allowlist do `AuthMiddleware`
(`backend/app/core/auth_middleware.py:192-198`) mostra que `cliente_externo` alcança
`/api/notifications` e `/api/users/me` além do portal e das assinaturas. São superfícies expostas
ao público externo do sistema e por isso devem ser auditadas antes dos módulos internos —
notificações, em particular, precisa ser verificada quanto a isolamento por cliente.
