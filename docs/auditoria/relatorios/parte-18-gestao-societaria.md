# Parte 18 — Gestão Societária (auditoria de código-fonte)

**Data:** 2026-08-11
**Método:** leitura do código-fonte. Nenhum ambiente executado, nenhuma chamada a produção.
**Continuação** das Partes 14 a 17. Completa a verificação iniciada na Parte 17, que tinha coberto
apenas o RBAC destes módulos.

---

## São dois módulos societários, não um

A distinção importa para ler os achados:

| Módulo | Router | O que gere |
|---|---|---|
| Sociedade do **escritório** | `routers/gestao_societaria.py` (253 linhas) | Sócios do De Paula Teixeira, participação, pró-labore, distribuição de lucros |
| Sociedades de **clientes** | `routers/sociedades_cliente.py` (472 linhas) | Cap table de empresas clientes (vertical Empresarial), due diligence, eventos societários |

O primeiro é o "sociedade" que o titular vê no Financeiro. É onde estão os achados graves — e, por
uma inversão difícil de justificar, é o **menos** protegido dos dois.

---

## SOC-01 (P0) — Um sócio pode alterar a própria participação e a dos demais, sem deixar rastro

**Evidência:** `backend/app/routers/gestao_societaria.py:90-127`.

Cadastrar um sócio exige **admin** (nível 8):

```python
if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["admin"]:
    raise HTTPException(403, "Apenas administradores podem cadastrar sócios")
```

Alterar um sócio exige apenas **socio** (nível 7) — `gestao_societaria.py:117-118`:

```python
if not _is_socio(cu):
    raise HTTPException(403)
```

com `_is_socio` definido em `gestao_societaria.py:53` como `ROLE_LEVEL >= ROLE_LEVEL["socio"]`. Na
hierarquia do projeto (`core/security.py:30-40`), `admin` = 8 e `socio` = 7.

E o `PATCH` aplica qualquer campo enviado, sem restrição por campo
(`gestao_societaria.py:123-125`):

```python
for campo, valor in req.model_dump(exclude_none=True).items():
    setattr(s, campo, valor)
```

`SocioPatch` (`gestao_societaria.py:37`) aceita `participacao_percentual` e `pro_labore`.

**Impacto.** Qualquer sócio pode alterar a participação societária e o pró-labore de **si mesmo e
de qualquer outro sócio** — e criar um sócio, que é ato menos grave, exige privilégio *maior* do
que alterar quanto cada um detém da sociedade. A permissão está invertida em relação ao risco.

**E não há rastro.** `atualizar_socio` não chama `criar_audit_log` nem `registrar_acao` — ver
SOC-02. A alteração não deixa registro de quem mudou, o que mudou nem quando.

O único mecanismo que perceberia algo é a validação de 100% na distribuição de lucros
(`gestao_societaria.py:151-160`), que recusaria um quadro somando ≠ 100%. Mas ela acusa o
**total**, não a autoria: quem alterou pode compensar reduzindo outro sócio e a soma continua
fechando.

**Correção sugerida.** Exigir `admin` para `PATCH /socios/{id}` (paridade com o cadastro),
restringir `participacao_percentual` e `pro_labore` a `superadmin`/`admin` por allowlist de campo,
e registrar trilha com valores antes e depois.

---

## SOC-02 (P1) — A sociedade do escritório quase não tem trilha; a dos clientes tem

**Evidência.** `routers/gestao_societaria.py` não chama `criar_audit_log` nenhuma vez
(`grep -c` = 0). Usa `registrar_acao` (`modules/auditoria/middleware.py:23`) em apenas dois pontos:
`cadastrar_socio` (`:106`) e `aprovar_distribuicao` (`:251`).

Ficam **sem qualquer registro**:
- `PATCH /socios/{id}` — alteração de participação e pró-labore (o ato mais sensível do módulo);
- `POST /distribuicao` — o cálculo da distribuição de lucros.

Para comparação, `routers/sociedades_cliente.py` — que cuida das empresas **dos clientes** —
chama `criar_audit_log` em **dez** pontos, cobrindo criação, alteração e remoção de sociedade, de
sócio e de evento societário (`:186,262,328,348,378,417,443,469`).

**Impacto.** O escritório audita melhor o quadro societário dos clientes do que o próprio. Numa
divergência entre sócios sobre quando e por quem uma participação foi alterada, não há o que
consultar. Também não há como reconstruir o histórico de pró-labore.

**Detalhe adicional:** nos dois pontos em que há trilha, `registrar_acao` é chamado **depois** do
`await db.commit()` (`gestao_societaria.py:105-106` e `:250-251`). Se o registro falhar, a
alteração já está persistida e o rastro se perde — mesma classe do NOT-02 (Parte 16).

---

## SOC-03 (P1) — A soma de 100% só é validada na distribuição, nunca na escrita

**Evidência.** `cadastrar_socio` e `atualizar_socio` (`gestao_societaria.py:90-127`) validam
apenas o intervalo de cada valor isoladamente — `Field(gt=0, le=1)`
(`gestao_societaria.py:27,37`). Nenhum dos dois consulta os demais sócios para conferir o
agregado.

A validação existe, mas só em `POST /distribuicao` (`gestao_societaria.py:150-160`), e é boa nas
duas direções:

```python
if round(total_participacao, 4) > 1.0001:
    raise HTTPException(422, f"Participação total {total_participacao * 100:.2f}% excede 100%")
# Antes, uma soma < 100% distribuía silenciosamente o restante a ninguém
...
if round(total_participacao, 4) < 0.9999:
```

**Impacto.** O quadro societário pode ser gravado em estado inválido — três sócios com 50% cada,
somando 150% — e persistir assim indefinidamente. O erro só aparece quando alguém tenta distribuir
lucros, possivelmente meses depois, e aí o bloqueio é total: não se distribui nada até alguém
descobrir qual dos lançamentos está errado. `GET /socios` devolve `total_participacao`
(`gestao_societaria.py:83-85`), então a interface **pode** mostrar a divergência — mas nada impede
a gravação.

**Correção sugerida.** Validar o agregado na escrita: recusar (ou exigir confirmação explícita)
alteração que faça a soma dos sócios ativos ultrapassar 100%.

---

## SOC-04 (P2) — Sem segregação de funções na aprovação da distribuição

**Evidência:** `aprovar_distribuicao` (`gestao_societaria.py:234-253`) exige `admin` e grava
`aprovado_por`/`aprovado_em`, com guarda de estado (`status != "calculado"` → 422). Não há
verificação de que o aprovador seja diferente de quem calculou (`created_by`).

**Impacto.** O mesmo administrador calcula e aprova a própria distribuição. Num escritório pequeno
isso pode ser aceitável e até inevitável; registro porque é o tipo de controle que se espera
existir explicitamente — como decisão consciente, não como omissão.

---

## O que está bom (e vale preservar)

**A matemática do dinheiro está correta, e melhor do que o comum.** A distribuição de lucros
(`gestao_societaria.py:163-183`) calcula em `Decimal` com `ROUND_HALF_UP` e — o ponto raro —
**corrige o drift de centavos**: depois de arredondar cada cota, a diferença entre a soma e o
total é somada à maior cota, de modo que as partes fechem exatamente o valor distribuído. O
comentário declara a regra: *"dinheiro nunca em float"*.

**Os tipos de coluna estão certos.** `models/socio.py:25,28` usa `Numeric(5, 4)` para participação
e `Numeric(12, 2)` para pró-labore. Os `float` que aparecem nos schemas Pydantic e nas respostas
são fronteira de serialização; a aritmética reconverte para `Decimal`
(`gestao_societaria.py:170`).

**A validação de 100% na distribuição corrige um bug real e documenta qual.** O comentário
registra que antes *"uma soma < 100% distribuía silenciosamente o restante a ninguém"* — dinheiro
que sumia da distribuição sem erro. Hoje as duas direções são recusadas.

**O cap table de clientes tem o desenho conceitual certo.** `montar_cap_table`
(`services/sociedades_service.py:56-82`) **não** força 100%: calcula os percentuais sobre as
quotas efetivamente declaradas e emite `alerta_percentual` quando a soma diverge do capital
social, explicando as duas causas possíveis (quadro incompleto ou digitação errada). Forçar 100%
esconderia dado faltante; alertar é mais honesto. A docstring explica a convenção brasileira
(LTDA/SLU/SS, 1 quota = R$ 1,00) e o que significa `None`.

**Ressalva sobre esse alerta:** ele é calculado na leitura do detalhe e devolvido na resposta.
Não é persistido nem bloqueia operação, e não verifiquei se a interface o exibe — se não exibir,
recai na classe "fica no retorno e não chega a ninguém". Fica como ponto a confirmar no frontend.

**Nota de consistência:** `calcular_percentual` (`services/sociedades_service.py:48-53`) usa
`round(float(q / t * 100), 2)` — mesmo padrão `float` + arredondamento bancário apontado em NFS-03
(Parte 17). Aqui o efeito é de exibição, não de valor gravado, então é P2; mas é o terceiro módulo
em que o padrão aparece, o que sugere tratá-lo como convenção a corrigir de uma vez.

---

## Estado da cobertura da auditoria

| Frente | Situação |
|---|---|
| Financeiro (consolidado, despesas, honorários, calculadoras) | Parte 14 |
| Prazos e intimações | Parte 14 |
| Portal do Cliente | Parte 15 |
| Assinaturas eletrônicas | Parte 15 |
| Notificações | Parte 16 |
| NFS-e | Parte 17 |
| Gestão societária (escritório e clientes) | **Parte 18** |
| Contratos do escritório | RBAC verificado (Parte 17); conteúdo pendente |
| Estimador de honorários OAB | pendente |
| Configurações, Lixeira, Diagnóstico, Checklists, Produtividade | pendente |

**Prioridade para o titular:** SOC-01 é o achado mais grave desta auditoria depois dos dois P0 de
prazos (Parte 14). Não exige decisão de terceiro — diferente de NFS-01 e NFS-02, que dependem do
contador — e a correção é pequena: elevar o gate do `PATCH` e adicionar trilha.
