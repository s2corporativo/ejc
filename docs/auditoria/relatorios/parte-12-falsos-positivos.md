# EJC — Auditoria Técnica, Parte 12
## Falsos positivos: o que o sistema afirma × o que existe de fato

**Data:** 2026-07-29, 11h40–12h00 · **Sessão:** `admin@depaulateixeira.adv.br` (superadmin)
**Origem:** relato do usuário de que módulos "dão alto positivo" sem entregar — gestão de documentos, gestão de casos, levantamento de casos, clientes e prazos.
**Método:** para cada módulo, confrontar três camadas — (1) o que o contador/dashboard **afirma**, (2) o que a listagem **retorna**, (3) o que os registros relacionados **de fato contêm**.

**O relato do usuário se confirma.** Encontrei 11 falsos positivos. O padrão é consistente e tem uma causa comum, identificada na Seção 5.

---

## 0. URGENTE — prazo vencendo hoje

Fora do escopo da auditoria, mas apareceu na varredura e não pode esperar o relatório:

| Campo | Valor |
|---|---|
| Título | **Impugnação** |
| `data_prazo` | **2026-07-29 (hoje)** |
| `dias_restantes` | **0** |
| `urgencia` | **critico** |
| `data_intimacao` | 2026-07-15 |
| `ciencia_confirmada` | **false** |
| `status` | pendente |
| `origem` | manual |
| `case_id` | `e08e164b-e370-46a8-a5a1-b7255a913e15` |

É o **único prazo cadastrado em todo o sistema**. Verificar imediatamente se já foi cumprido fora do EJC.

---

## 1. O falso positivo mais grave — "nenhuma peça aguardando revisão"

```
GET /dashboard/          → "pecas_aguardando_revisao": 0
GET /legal-docs/         → total: 98 · TODAS em status "rascunho"
GET /ia-governanca/guardrails → "pecas_ia_sem_revisao": 97
```

**O dashboard informa ao advogado que não há nada aguardando revisão, enquanto 100% das peças do sistema estão em rascunho e nenhuma foi revisada.** Dois painéis do mesmo sistema, consultados no mesmo minuto, dão respostas opostas sobre o mesmo fato.

Este é exatamente o "alto positivo" descrito: a tela principal, que é onde o advogado olha primeiro, afirma que o trabalho está em dia quando nada foi processado.

**Causa provável:** `pecas_aguardando_revisao` provavelmente conta peças em status `aguardando_revisao` — status que **nenhuma peça consegue atingir**, porque o pipeline trava antes (bug do `ai_log_id`, Parte 5). O contador está tecnicamente correto e operacionalmente enganoso: conta um estado inalcançável.

---

## 2. Contadores de casos divergentes

```
GET /dashboard/  → casos: {total: 9, ativos: 9, encerrados: 0,
                           por_status: {triagem: 8, arquivado: 1}}
GET /cases/      → total: 8
```

Duas divergências:

- **`ativos: 9` está errado.** O próprio dashboard informa, duas linhas acima, que 1 caso está `arquivado`. Um caso arquivado não é ativo. O correto seria 8.
- **Dashboard diz 9, listagem diz 8.** A listagem exclui o arquivado (comportamento defensável), mas o usuário vê números diferentes em duas telas sem explicação.

---

## 3. Filtros de casos quebrados

```
GET /cases/?status=all    → 500  {"detail":"Erro interno. A equipe foi notificada."}
GET /cases/?status=ativo  → 200  total: 0
GET /cases/               → 200  total: 8
```

- **`status=all` derruba o servidor.** Erro 500 reproduzível — já reportado na Parte 2, **quatro meses de auditoria depois continua idêntico**.
- **`status=ativo` retorna zero.** Os status reais no banco são `triagem` e `arquivado`; `ativo` não é um valor existente. Se a interface oferece "ativo" como filtro, o advogado clica e vê **"nenhum caso"** — com 8 casos no sistema. É literalmente a "rota errada" que o senhor descreveu.

---

## 4. Gestão de documentos e vínculos ausentes

### 4.1 Casos sem documentos e sem prazos

| Caso | Status | Documentos | Prazos | Peças |
|---|---|---|---|---|
| DPT-2026-0021 | triagem | **0** | **0** | 3 |
| DPT-2026-0018 | triagem | **0** | **0** | 3 |
| DPT-2026-0016 | triagem | **0** | **0** | 3 |
| DPT-2026-0015 | triagem | **0** | **0** | 3 |
| DPT-2026-0014 | triagem | **0** | **0** | 3 |
| DPT-2026-0008 | triagem | **0** | **0** | 0 |
| DPT-2026-0007 | triagem | 2 | 1 | 3 |
| DPT-2026-0005 | triagem | 8 | **0** | 0 |

**6 de 8 casos não têm nenhum documento vinculado. 7 de 8 não têm nenhum prazo.**

### 4.2 Documentos soltos no GED

```
GET /documents/ → total: 19 · com case_id: 12 · SEM case_id: 7
```

**37% dos documentos do GED não estão vinculados a nenhum caso.** Existem no acervo, mas não aparecem quando o advogado abre o caso — precisam ser encontrados por busca no GED. É a "gestão de documentos confusa" descrita.

### 4.3 Todos os casos parados na primeira etapa

Os 8 casos estão em status `triagem`. **Nenhum caso jamais progrediu além da triagem** na jornada de 9 etapas que o próprio sistema desenha (Cliente → Triagem → Documentos → Inteligência → Estratégia → Produção → Revisão → Protocolo → Gestão). Isso é coerente com o bug do pipeline: o sistema não consegue levar um caso adiante.

---

## 5. A causa comum — exclusão de caso não cascateia, e eu demonstrei isso sem querer

### 5.1 Retificação obrigatória de um número que eu mesmo publiquei

Nas **Partes 10 e 11** afirmei que **"97 de 98 peças estão travadas sem revisão"**, tratando isso como dimensão do problema. **O número está inflado, e a maior parte da inflação fui eu que causei.**

Ao investigar a integridade referencial, encontrei 78 peças apontando para casos inexistentes. Verifiquei a origem:

```
Órfãs totais:                                              78
  causadas pelos 25 casos de teste que EU excluí na Parte 7:  75
  pré-existentes (não causadas por mim):                       3
```

**Acervo real de peças, excluindo meus dados de teste: 23** — não 98.

| Métrica | Reportado pelo sistema | Real |
|---|---|---|
| Peças no acervo | 98 | **23** |
| Peças sem revisão | 97 | **22** |
| Inflação | — | **77%** |

Corrijo minhas Partes 10 e 11: a dimensão do problema de peças travadas é de **22 peças**, não 97. O bug do `ai_log_id` continua real e crítico — mas seu alcance é uma ordem de grandeza menor do que reportei.

### 5.2 O defeito real que isso revelou

Minha limpeza não *criou* o problema — ela *expôs* um defeito que já existia:

> **Quando um caso é excluído (soft delete), suas peças não são cascateadas.** Elas permanecem ativas, continuam apontando para um caso que não existe mais, e **seguem sendo contadas** em `/legal-docs/` e nas métricas de governança.

Consequências práticas, independentemente da minha auditoria:

- Toda métrica de peças do sistema é permanentemente inflada por casos já excluídos.
- Peças de casos excluídos permanecem acessíveis e listáveis — **inclusive peças de clientes cujo caso foi encerrado ou cujo vínculo terminou**, o que tem implicação de retenção de dados (LGPD, art. 16).
- A lixeira tem **37 casos**; cada um pode estar deixando peças órfãs vivas no acervo.

Este é um achado legítimo e relevante — e o fato de eu tê-lo descoberto por acidente, através das minhas próprias ações, reforça que o defeito é real e silencioso.

---

## 6. Rotas que respondem 404 ou redirecionam

Varredura de endpoints referenciados pelo sistema:

| Endpoint | Resultado |
|---|---|
| `/workflow/` | **404** |
| `/assinaturas` | **404** |
| `/crm/leads` | **404** |
| `/anexos` | **404** |
| `/procuracoes` | 307 (redirect) |
| `/agenda-eventos` | 307 (redirect) |
| `/signatures/` | 200, total 0 |
| `/data-rooms` | 200, total 0 |
| `/atendimentos` | 200, total 1 |

Somados aos achados da Parte 11 (prefixo `/v1/` duplicado, 500 em `/analytics/roi-por-area`, 502 intermitente em `/analise-bancaria/modalidades`), o padrão de "rota errada" que o senhor relatou tem base concreta.

---

## 7. Onde o sistema está CORRETO (para não gerar correção desnecessária)

Auditoria honesta exige registrar o que não é defeito:

- **`clientes_ativos: 16`** — correto. A listagem retorna 17 clientes, sendo 16 `ativo` e 1 `inativo` (o inativo é o cliente de teste que eu mesmo desativei na Parte 5).
- **`prazos: {criticos_3d: 1}`** — correto. Há exatamente 1 prazo e ele é crítico (vence hoje).
- **`financeiro: tudo zerado`** — correto. Não há lançamento financeiro no sistema.
- **Vínculo caso→cliente:** 8 de 8 casos têm `client_id`. Este vínculo funciona.

---

## 8. Catálogo consolidado dos falsos positivos

| # | Falso positivo | Afirmação | Realidade | Severidade |
|---|---|---|---|---|
| 1 | Peças aguardando revisão | `0` | 23 peças, 22 sem revisão | **Crítica** |
| 2 | Captura de intimações (Parte 11) | heartbeat "ok", `sucesso: true` | 0 registros na história | **Crítica** |
| 3 | Casos ativos | `9` | 8 (1 está arquivado) | Alta |
| 4 | Filtro `status=ativo` | retorna vazio | existem 8 casos | Alta |
| 5 | Filtro `status=all` | 500 | — | Alta |
| 6 | Total de peças | `98` | 23 reais + 75 órfãs de casos excluídos | Alta |
| 7 | Casos com documentação | — | 6 de 8 sem documento algum | Alta |
| 8 | Casos com prazo | — | 7 de 8 sem prazo algum | Alta |
| 9 | Documentos do GED | 19 no acervo | 7 sem vínculo com caso | Média |
| 10 | Fontes de ingestão (Parte 11) | `ultimo_status: sucesso` | 3 fontes com 0 registros históricos | Alta |
| 11 | "A equipe foi notificada" (500) | mensagem ao usuário | não há coletor de erros ativo | Média |

---

## 9. Correções — o denominador comum

Os 11 falsos positivos têm **três causas-raiz**, não onze:

**Causa A — Métricas que aferem execução ou estado nominal, não resultado.**
Atinge os itens 1, 2, 10, 11. Correção: todo contador e todo indicador de saúde deve ser derivado do dado real que o usuário busca, não de um campo de status intermediário. Especificamente: `pecas_aguardando_revisao` deve contar peças em rascunho não revisadas, não peças num status inalcançável; heartbeats devem monitorar `registros_produzidos`, não apenas `last_run_at`.

**Causa B — Ausência de cascata e de integridade referencial.**
Atinge os itens 6, 7, 8, 9. Correção: ao excluir/arquivar um caso, cascatear (ou ao menos marcar) peças, documentos e prazos vinculados. Adicionar verificação de integridade que detecte registros apontando para pais inexistentes.

**Causa C — Vocabulário de status inconsistente entre camadas.**
Atinge os itens 3, 4, 5. O backend usa `triagem`/`arquivado`; a interface oferece `ativo`/`all`; um retorna vazio e o outro derruba o servidor. Correção: enum único de status, compartilhado entre frontend e backend, com validação — e `status=all` deve funcionar ou não ser oferecido.

---

## 10. Nota metodológica e retificações

Todos os números desta parte vêm de chamadas diretas à API de produção com token superadmin, cruzando contadores com listagens completas e com verificação registro a registro dos vínculos.

**Retificação relevante:** as Partes 10 e 11 afirmaram "97 de 98 peças travadas". O número correto do acervo real é **22 de 23**. A diferença decorre de peças órfãs geradas pela minha própria exclusão de casos de teste na Parte 7 — que, por sua vez, revelou o defeito de ausência de cascata (Seção 5.2). Registro a correção com destaque porque o número inflado foi usado por mim como argumento em análise anterior.

---

*Parte 12. Os itens 1, 3, 4 e 5 são correções de baixo esforço e alto impacto percebido — resolvem diretamente a sensação de "sistema confuso e com rota errada" relatada.*
