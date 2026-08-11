# Parte 19 — Estimador de Honorários OAB e Central de Diagnóstico

**Data:** 2026-08-11
**Método:** leitura do código-fonte. Nenhum ambiente executado, nenhuma chamada a produção.
**Continuação** das Partes 14 a 18.

---

## Parte A — Estimador de honorários OAB

### A arquitetura acerta a separação entre explorar e registrar

O módulo tem **dois caminhos distintos**, e a diferença entre eles é a coisa mais importante a
registrar:

| Caminho | Natureza | Persiste? |
|---|---|---|
| `POST /honorarios-oab/estimar` | IA sobre contexto RAG da tabela OAB/MG | Não |
| `POST /honorarios-oab/casos/{id}/proposta/sugerir` | **Determinístico**, sem IA | Não |
| `POST /honorarios-oab/casos/{id}/proposta` | Rascunho versionado | **Sim**, auditado |

O que vira **registro do caso** não passa por IA. `sugerir_proposta` é determinística e, segundo a
própria docstring (`routers/honorarios_oab.py:363-366`), *"nunca inventa valor — sem item OAB
vigente, o mínimo fica None com aviso explícito"*. E `criar_proposta_honorarios`
(`routers/honorarios_oab.py:373-400`) grava rascunho com `versao = max+1`, protegido por índice
único `(case_id, versao)` contra corrida, com audit log obrigatório
(`services/fee_proposal_service.py:209-245`).

Mais: ao gravar, o `item_codigo` é **revalidado** contra os itens vigentes da área; sem
correspondência, grava `validada=False` com aviso, em vez de bloquear — *"transparência sem
bloquear (o advogado define o valor final)"*.

Isso é o oposto do antipadrão que o `CLAUDE.md` alerta ("chance de êxito que fica no log e não no
caso"): aqui a IA é rascunho descartável e o que persiste é determinístico, versionado e auditado.

### HON-01 (P1) — O estimador de IA não passa pelo citation gate

**Evidência:** `routers/honorarios_oab.py` não menciona `citation_gate` nem `validate_citations`
em nenhuma linha. A proteção contra inventar item da tabela OAB é **instrução de prompt**
(`routers/honorarios_oab.py:99-101`):

```python
sys = ("A tabela oficial OAB/MG NÃO está na base. Dê referência genérica por percentuais "
       "usuais de mercado. PROIBIDO citar número de item da tabela. " + REGRAS)
```

Dez outros módulos do backend usam o gate — `routers/legal_docs.py`, `routers/ai.py`,
`routers/ia_citacoes.py`, `routers/ia_defensiva.py`, `services/ai/core/response_validator.py`,
entre outros. Este não.

**Impacto.** O `CLAUDE.md` (regra crítica 4) trata o gate de citações como obrigatório e diz para
não contorná-lo. Uma instrução de prompt não é um gate: se o modelo devolver "item 4.3 da Tabela
OAB/MG" apesar da proibição, nada no caminho de resposta detecta. O advogado lê um número de item
com aparência de fonte oficial.

**Atenuante real, que reduz a severidade:** o caminho que **persiste** valida o `item_codigo`
programaticamente contra a vigência (`routers/honorarios_oab.py:389-400`). O risco fica confinado
ao texto exploratório — que, ainda assim, é o que o advogado lê e pode transcrever para a proposta.

**Correção sugerida.** Passar `resp.texto` pelo `citation_gate` antes de devolver, ou validar
programaticamente qualquer padrão de item citado contra `_itens_oab_vigentes` — reaproveitando a
função que o caminho de gravação já usa.

### HON-02 (P2) — Com o RAG vazio, o estimador opera permanentemente em modo degradado

**Evidência:** `_contexto_oab` (`routers/honorarios_oab.py:68-77`) busca no RAG com
`categorias=["tabela_honorarios_oab"]` e descarta placeholder:

```python
reais = [c for c in ctx
         if len((c.get("conteudo") or "").strip()) > 40
         and "lorem ipsum" not in (c.get("conteudo") or "").lower()]
return txt, len(reais) > 0
```

**Impacto.** A Parte 8 da auditoria externa registrou **0 de 47.359 chunks indexados**. Se isso
ainda vale, `tabela_ok` é sempre `False` e o estimador roda para sempre no ramo degradado —
"percentuais usuais de mercado", sem âncora na tabela oficial. A degradação é bem construída (o
prompt muda, proíbe citar item, e a resposta carrega `tabela_oficial_disponivel: false`), mas o
recurso anunciado — estimativa ancorada na tabela OAB/MG — nunca se realiza.

**Não confirmei em produção.** Depende do estado do índice RAG, fora do alcance desta auditoria.
Vale checar antes de tratar o estimador como funcional.

### O que está bom no estimador

Passa pelo `ai_gateway.chat` (`routers/honorarios_oab.py:124`), como a regra 4 exige — sem chamada
direta a provider. Tem rate limit próprio, `temperature=0.2`, e devolve `_aviso` explícito de que
a estimativa não vincula e o advogado define o valor final. O filtro de *lorem ipsum* mostra que
alguém já viu placeholder vazando para resposta de usuário e fechou o caminho.

A gestão da tabela estruturada é versionada por vigência com `fonte` obrigatória — *"nova
vigência = NOVOS registros (fechar vigencia_fim dos antigos), nunca sobrescrever"*
(`routers/honorarios_oab.py:135-139`) —, restrita a sócio+ e auditada. É o tratamento correto para
regra com vigência, exatamente o que a regra 5 da governança exige.

---

## Parte B — Central de Diagnóstico

### DIA-01 (P1) — Causa-raiz da contradição do `backup_offsite`, localizada no código

A auditoria externa (Parte 7) reproduziu, de fora, `/diagnostico/central` reportando
`backup_offsite` **ligado e desligado na mesma resposta**. A causa está confirmada:

**São duas fontes independentes, com o mesmo rótulo, lendo settings diferentes.**

**Fonte 1** — `services/diagnostico_service.py:565-600`, subsistema de topo:

```python
async def _probe_backup(settings: Settings) -> dict[str, Any]:
    ...
    habilitado = bool(settings.BACKUP_ENABLED)
```

registrado como `_rodar("Backup offsite", _probe_backup(settings))`
(`services/diagnostico_service.py:760`).

**Fonte 2** — `services/integration_status.py:336-344`:

```python
_status(
    key="backup_offsite",
    label="Backup offsite",
    group="Infraestrutura",
    enabled=bool(settings.BACKUP_REMOTE),
    configured=bool(settings.BACKUP_REMOTE),
    ...
)
```

**E as duas caem na mesma resposta.** `diagnostico_completo` roda os dois em paralelo
(`services/diagnostico_service.py:753-762`): `_probe_backup` como subsistema próprio, e
`_probe_integracoes` — que chama `build_integration_status(settings)` e repassa os itens do painel
(`services/diagnostico_service.py:252-264`). O filtro ali descarta **apenas** o grupo
`"Inteligência"`:

```python
if it.get("group") == "Inteligência":
    continue
```

`backup_offsite` está no grupo `"Infraestrutura"`, então passa. Resultado: `subsistemas` contém
duas entradas rotuladas "Backup offsite", derivadas de `BACKUP_ENABLED` e de `BACKUP_REMOTE`.

**Impacto — e por que este campo é o pior lugar possível para isso acontecer.** As duas settings
não são sinônimos: `BACKUP_REMOTE` declara um **destino**; `BACKUP_ENABLED` liga o **backup**.
Declarar destino sem ligar o backup é justamente o estado perigoso — e é exatamente nele que o
painel pinta uma das entradas de verde. Quem ler a linha da lista de integrações conclui que está
protegido; o backup cifrado offsite é, nas palavras do próprio código, *"o único mitigante do
ponto único de falha do banco"*.

**Correção sugerida.** Uma única fonte de verdade para o estado do backup. Ou `_probe_integracoes`
descarta a chave `backup_offsite` (já tem o mecanismo de filtro), ou os dois passam a compor um
estado só, distinguindo no rótulo "destino declarado" de "backup habilitado" — que é a informação
que o operador precisa.

### O que está bom no diagnóstico

O RBAC é sólido: `/central` e `/integridade` exigem **socio+** via `require_roles`, com rate limit
(10/min e 5/min) e feature flag própria (`_exigir_diagnostico_habilitado`).

E há uma decisão de privacidade explícita e bem executada em `/integridade`: a docstring promete
que *"o relatório contém somente UUIDs técnicos, contagens, severidade e ação recomendada. Não
retorna nomes, CPF/CNPJ, número de processo ou conteúdo de documentos"* — endpoint de diagnóstico
que assume que diagnóstico não precisa de PII.

`_probe_backup` também acerta o tom: alerta especificamente para produção rodando sem backup, com
ação sugerida concreta (`BACKUP_ENABLED=true` e `BACKUP_ENCRYPTION_KEY`), e o comentário deixa
claro que **só lê configuração, não liga nada**.

---

## Estado da cobertura da auditoria

| Frente | Situação |
|---|---|
| Financeiro (consolidado, despesas, honorários, calculadoras) | Parte 14 |
| Prazos e intimações | Parte 14 |
| Portal do Cliente / Assinaturas | Parte 15 |
| Notificações | Parte 16 |
| NFS-e | Parte 17 |
| Gestão societária | Parte 18 |
| Estimador de honorários OAB | **Parte 19** |
| Central de Diagnóstico | **Parte 19** |
| Configurações, Lixeira, Checklists, Produtividade | pendente |
| Conteúdo dos contratos do escritório | pendente (RBAC visto na Parte 17) |
