# Bloco 3 — desenho das telas

> Issue #641 · Bloco 3 de `docs/auditoria/plano-lancamento-v3.md`

**O que este documento é:** o desenho em nível de tela que o Bloco 3 pede antes
de codificar — telas, estados, contratos de API e contagem de cliques.

**O que ele não é:** implementação. Nenhuma linha foi escrita.

**Relação com o desenho anterior:** `docs/DESENHO_ENTRADA_UNICA_E_CASO_WORKSPACE.md`
é o desenho de conceito, já aprovado por você em 2026-08-02 (quatro estados,
migrar o enum, tela de confirmação aprovada, quatro abas no primeiro corte).
Este documento **não revoga** aquele — desce ao nível de tela e **corrige uma
afirmação dele que a leitura do código não sustenta** (ver adiante).

---

## 1. Onde o Bloco 3 está, verificado no código

A ordem de implementação aprovada tinha quatro entregas. O estado real:

| # | Entrega | Estado | Evidência |
|---|---|---|---|
| 1 | Conversão Sala Jurídica → Caso preserva os fatos | **NÃO resolvido** | abaixo |
| 2 | Quatro estados | **Pronto** | migration `126_case_status_quatro_estados`, `core/status_caso.py`, `models/case.py:42` |
| 3 | Caso como espaço de trabalho | **Não iniciado** | `CasoDetalhe.tsx` tem 27 abas; as de trabalho são listas somente-leitura |
| 4 | Entrada única | **Não iniciado** | não existe rota `/entrada` em `moduleRegistry.tsx` |

### A correção ao desenho anterior

O desenho aprovado afirma, na seção *"Verificação posterior ao desenho"*, que o
pré-requisito nº 1 **já estaria resolvido** porque `converter_em_caso` grava
`descricao_fatos`. A metade backend da frase é verdadeira. A conversão continua
perdendo os fatos assim mesmo:

```
backend/app/services/legal_chat_service.py:907
    descricao_fatos=payload.descricao,        ← o backend aceita

backend/app/schemas/legal_chat.py:107
    descricao: str | None = Field(default=None, …)   ← opcional

frontend/src/pages/SalaJuridica.tsx:564-577
    api.post(`/sala-juridica/${ativa.id}/converter`, {
      client_id, novo_cliente_nome, area, titulo_caso,
      advogado_responsavel_id, confirmo_conflito_verificado,
      confirmo_dados_revisados, conflict_confirmed, duplicate_confirmed,
    })                                        ← `descricao` nunca é enviada
```

O campo é opcional no schema, o wizard não tem campo para ele, e o caso nasce
com `descricao_fatos = NULL`. **O defeito que a auditoria viu em produção existe
no repositório** — só não está onde o desenho anterior procurou. É o primeiro
item a corrigir, e é pequeno: o passo de conferência do wizard ganha um campo
"Fatos" pré-preenchido com o resumo da sessão, e o `POST` passa a enviá-lo.

Os anexos, esses sim, já são transferidos (`transferir_anexos: true` é o default
do schema e `_transferir_anexos` roda dentro da mesma transação).

---

## 2. Tela A — `/entrada`

Rota nova. Sem seletor de área, sem tipo de caso, sem cliente. **Nada que o
sistema possa inferir é perguntado antes de tentar inferir.**

### A.1 Estado inicial

```
┌────────────────────────────────────────────────────────────────┐
│  Novo caso                                                     │
│  Cole o relato, arraste os documentos, ou os dois.             │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Cole aqui o que o cliente contou.                        │  │
│  │                                                          │  │
│  │                                                          │  │
│  │                                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  ⬒  Arraste documentos aqui  ·  ou clique para escolher  │  │
│  │     PDF, DOCX, imagens, ZIP · até 40 arquivos, 120 MB    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│                                      [ Analisar ]              │
└────────────────────────────────────────────────────────────────┘
```

`[ Analisar ]` habilita com **relato ≥ 40 caracteres OU ≥ 1 arquivo**. Os dois
juntos é o caminho bom, não o exigido. Os limites vêm de
`entrada_universal_service` (`MAX_ARQUIVOS`, `MAX_BYTES_LOTE`) e são exibidos,
não descobertos por erro.

### A.2 Estado "analisando"

Uma tela só, com progresso honesto por etapa — o OCR de um PDF grande leva
dezenas de segundos e barra indeterminada nesse tempo parece travamento:

```
│  Analisando…                                                   │
│                                                                │
│  ✓ Documentos recebidos e preservados          3 arquivos      │
│  ✓ Texto extraído                              14 páginas      │
│  ⋯ Classificando e cruzando com o relato                       │
│  ○ Procurando o cliente na base                                │
│                                                                │
│  Os originais já estão salvos. Se algo falhar daqui em         │
│  diante, nada se perde.                                        │
```

A última frase não é decoração: `_salvar_original` commita antes de qualquer
OCR/IA justamente para isso, e o usuário precisa saber.

### A.3 Estado degradado (IA indisponível)

Não é tela de erro. É a tela de confirmação com menos campos preenchidos e um
aviso no topo:

```
│  ⚠ A análise por IA está indisponível agora. Os documentos     │
│    foram preservados e classificados pelas regras            │
│    determinísticas. Preencha o que faltar — nada se perdeu.   │
```

O caminho **sempre** chega ao botão de criar. Isso vale também para o relato
sem documentos: `POST /triagem/entrevista` responde 503 quando `AI_ENABLED` é
falso, e esse 503 não pode virar beco sem saída.

---

## 3. Tela B — `/entrada/confirmar`

Uma tela, tudo editável, nada obrigatório de digitar. Cada bloco mostra **de
onde veio** a informação — o advogado precisa saber o que está conferindo.

```
┌────────────────────────────────────────────────────────────────┐
│  Confira e confirme                          rascunho · 2 min  │
│                                                                │
│  ⚠ CONFLITO DE INTERESSES — 1 achado                           │
│    Parte contrária "Banco X S/A" consta como cliente ativo.    │
│    [ ver achado ]        ☐ Revisei e não há impedimento        │
│                                                                │
│  Cliente     Maria S. da Costa                    [ é outro ]  │
│              ✓ já cadastrada · 2 casos anteriores              │
│              origem: CPF no comprovante de pagamento           │
│                                                                │
│  Área        Consumidor                    ▾      confiança ●●○│
│                                                                │
│  Título      Negativação indevida — Maria S. da Costa          │
│                                                                │
│  Fatos       Negativação indevida após quitação do contrato    │
│              em 12/03/2026. A cobrança persistiu por 4 meses…  │
│                                                        [ ↕ ]   │
│              origem: relato + fls. 3-4 do contrato             │
│                                                                │
│  Parte       Banco X S/A                                       │
│  contrária                                                     │
│                                                                │
│  Documentos  ✓ Comprovante de pagamento     comprovante   ⨯    │
│              ✓ Print da negativação         prova         ⨯    │
│              ⚠ Contrato — não reconhecido   [classificar] ⨯    │
│              todos serão vinculados ao caso                    │
│                                                                │
│  Prazo       ⚠ 15 dias úteis a partir de 12/07/2026            │
│              vence 02/08/2026 · origem: fls. 2 da notificação  │
│              ☑ criar este prazo        responsável: [ eu ▾ ]   │
│                                                                │
│  Próxima     Notificação extrajudicial                    ▾    │
│  ação                                                          │
│                                                                │
│  Responsável  Dr. Clovis José Soares                      ▾    │
│                                                                │
│  ☐ Confirmo que revisei os dados acima                         │
│                                                                │
│  [ descartar ]                            [ Criar caso ]       │
└────────────────────────────────────────────────────────────────┘
```

### O que mudou em relação ao desenho aprovado, e por quê

O desenho de conceito não previa três coisas que a leitura do código mostrou
serem obrigatórias:

**1. Gate de conflito de interesses.** O caminho Sala Jurídica → Caso já exige
`conflict_confirmed` e devolve 409 quando `detectar_conflito` acha algo
(`legal_chat_service.py:848-861`). Uma entrada única que crie caso sem esse gate
seria uma porta lateral em volta de um dever ético (EOAB arts. 34-35). O bloco
de conflito aparece **só quando há achado**, e o checkbox só existe nesse caso.

**2. Gate de cliente duplicado.** Mesma origem: `duplicate_confirmed`. Aparece
como aviso ao lado do cliente quando `preview_conversao` retorna candidatos.

**3. Responsável explícito.** `converter_em_caso` valida que o responsável é
advogado ativo (422 caso contrário). Deixar implícito produziria 422 opaco no
clique final. Default: o próprio usuário, quando for advogado.

**Os três aparecem por exceção.** No caminho limpo — sem conflito, sem
duplicado, o próprio advogado como responsável — a tela é exatamente a que você
aprovou: cliente, área, fatos, documentos, prazo, próxima ação, um botão.

### Regras que não se negociam na implementação

- **Nada bloqueia.** Campo não inferido vem em branco e editável, não vira erro.
  Exceção única e deliberada: os dois checkboxes de conflito/duplicado, que só
  existem quando há achado real — esses são dever legal, não atrito.
- **Documento anexado é documento vinculado.** O `Document` nasce com
  `case_id = NULL` no momento do upload (o caso ainda não existe) e recebe o
  `case_id` na confirmação, **na mesma transação** que cria o caso. Isso é
  literalmente a classe de defeito que o `CLAUDE.md` marca como recorrente —
  "gravação não transacional entre registros relacionados". Um teste de
  regressão cobre exatamente isso: falha no meio ⇒ nenhum documento fica
  vinculado a caso inexistente e nenhum caso nasce sem seus documentos.
- **Rascunho sobrevive ao F5.** O lote já é persistido (`DocumentIntakeBatch`);
  a proposta editada também precisa ser, senão dois minutos de conferência se
  perdem num recarregamento.
- **Tudo é rascunho até o clique.** Área, prazo e fatos vindos de IA carregam
  `requer_confirmacao_humana` e viram `AILog` com HITL, como já fazem os dois
  endpoints de origem.

---

## 4. Contrato de API

Um router novo, `backend/app/routers/entrada.py`, que **orquestra** — nenhuma
chamada de IA nova, nenhum modelo novo.

### `POST /api/entrada/analisar` — multipart

```
in   texto?: str, files?: UploadFile[]
out  { rascunho_id, cliente: {…, origem, confianca},
       area: {valor, confianca}, titulo, fatos, parte_contraria,
       documentos: [{document_id, nome, classificacao, confianca}],
       prazo?: {descricao, data, origem, requer_confirmacao_humana},
       proxima_acao, conflito: {alertas[]}, duplicados: {clientes[]},
       degradado: bool, avisos[] }
```

Encadeia, em ordem, o que já existe:

```
files ─→ entrada_universal_service (persistir → hash → OCR → classificar)
texto ─→ triagem_entrevista (área, urgência, fatos estruturados)
   └──→ fusão → identificação de cliente (CPF/CNPJ via índice HMAC cego)
        → detectar_conflito + preview de duplicados
        → rascunho persistido
```

**Permissão:** `advogado+`. É o piso mais alto entre as peças encadeadas
(`entrada-universal` pede `estagiario`, `triagem/entrevista` pede `advogado`) e
criar caso é ato privativo de advogado no resto do sistema.

### `POST /api/entrada/{rascunho_id}/criar-caso`

```
in   { cliente: {client_id? | novo_nome}, area, titulo, fatos,
       parte_contraria?, documentos_ids[], prazo?, proxima_acao,
       advogado_responsavel_id, confirmo_dados_revisados,
       conflict_confirmed?, duplicate_confirmed? }
out  { case_id, numero_interno, documentos_vinculados, deadline_id? }
```

**Uma transação:** `Client` (se novo) → `Case` (status `aberto`) →
`UPDATE documents SET case_id` → `Deadline` (se marcado) → `CaseMovimento` de
abertura → `AuditLog`. Idempotente por `rascunho_id` com o mesmo lock pessimista
de `converter_em_caso` — dois cliques no botão não criam dois casos.

Reaproveita `proximo_numero_interno`, `detectar_conflito`, `preview_conversao`,
`obter_cliente_autorizado` e a guarda G1 de `proxima_acao`.

### Contagem de cliques

| Passo | Ações |
|---|---|
| Abrir `/entrada` | 1 |
| Colar relato + arrastar documentos | 2 |
| Analisar | 1 |
| Conferir (caminho limpo: só o checkbox) | 1 |
| Criar caso | 1 |
| **Total** | **6 ações, 2 telas** |

Contra 15 ações em 8 módulos hoje. O critério de aceite do desenho aprovado —
"se um caso novo ainda exigir mais de três telas, o bloco não cumpriu" — é
medido numa passagem real, não neste documento.

---

## 5. Tela C — o caso como espaço de trabalho

### O diagnóstico, com o código na mão

O problema não é falta de abas. São 27, em 5 seções (`config/caseNav.ts`). O
problema é que **as abas de trabalho não trabalham**:

```
CasoDetalhe.tsx:1004  aba Documentos → <Link to="/documentos?caso=…">
CasoDetalhe.tsx:1078  aba Prazos     → <Link to="/atividades?caso=…">
```

São listas somente-leitura cujo botão de ação **leva para fora do caso**. É a
navegação por funcionalidade sobrevivendo dentro da tela que deveria substituí-la.
E **não existe aba de Peças** — o único caminho para redigir é o módulo `/pecas`.

### A mudança

Quatro superfícies passam a agir **em lugar**, sem navegação:

| Aba | Hoje | Proposto | Endpoint (já existe) |
|---|---|---|---|
| Documentos | link para `/documentos?caso=` | zona de arrastar embutida | `POST /documents/upload` com `case_id` |
| Prazos | link para `/atividades?caso=` | formulário inline de 3 campos | `POST /deadlines/` |
| **Peças** | **não existe** | lista + redigir + conferir-e-assinar + PDF | `POST /legal-docs/`, `/conferir-e-assinar`, `/pdf-minuta` |
| Andamentos | timeline somente-leitura | composer inline no topo | `POST /cases/{id}/movimentos` |

A aba **Peças** é a que fecha o caminho até o protocolo: o Bloco 2 já consolidou
validar→aprovar→PDF em `POST /legal-docs/{id}/conferir-e-assinar`, e hoje esse
ato só é alcançável fora do caso.

**Financeiro fica de fora** deste corte, conforme sua decisão de 2026-08-02.

### Risco a vigiar

`CasoDetalhe.tsx` tem 27 abas em um arquivo. O desenho aprovado já avisava:
**começar pela extração das abas em componentes próprios**, seguindo o padrão de
`pages/CasoDetalhe/Tab*.tsx` que já existe, e só então acrescentar conteúdo. Na
ordem inversa, o arquivo fica impossível de manter.

### Os módulos transversais

`/prazos`, `/documentos`, `/pecas` **continuam existindo e não mudam de rota** —
mudam de papel. Ganham um cabeçalho que diz o que são ("Todos os prazos da
semana — para trabalhar um caso, abra o caso") e perdem a posição de destino
primário no menu. Isso é rótulo e ordenação no `moduleRegistry`, não deleção.

---

## 6. Quatro estados — o que sobrou

O enum foi migrado (migration 126) e `core/status_caso.py` é a fonte única. Duas
pontas soltas:

1. **`/casos/:id/jornada` ainda mostra nove etapas.** `jornada_caso.py` continua
   calculando `_etapa_cliente … _etapa_gestao`. O código é bom — funções puras,
   determinísticas, testáveis — e a proposta **não é apagá-lo**: é rebaixá-lo de
   *marco a vencer* para *tarefas opcionais do estado atual*. Nove barras
   vermelhas foi o que o desenho aprovado identificou como origem da culpa.
2. **Transição de estado precisa de gatilho.** Hoje nada move um caso de
   `aberto` para `em_instrucao`. Proposta: derivar por evento — primeiro
   documento vinculado ⇒ `em_instrucao`; primeira peça criada ⇒ `em_producao`;
   `conferir-e-assinar` + protocolo ⇒ `protocolado`. Sempre **sugerido e
   reversível**, nunca automático e travado.

---

## 7. Ordem de implementação proposta

| # | Entrega | Tamanho | Por quê nesta ordem |
|---|---|---|---|
| 1 | `descricao` no wizard da Sala Jurídica | pequeno | defeito ativo; independente |
| 2 | Abas do caso agindo em lugar + aba Peças | grande | fecha o caminho até o protocolo |
| 3 | `POST /entrada/analisar` + `/criar-caso` | grande | orquestração; sem UI ainda |
| 4 | Telas `/entrada` e `/entrada/confirmar` | médio | consome o contrato de 3 |
| 5 | Jornada como tarefas opcionais + transições | médio | cosmético perto do resto |

A entrada única continua vindo depois do workspace, pela razão do desenho
aprovado: ela **cria** casos, e criar caso num workspace que ainda vai mudar é
retrabalho.

---

## 8. O que eu preciso de você antes de codificar

1. **Os três blocos por exceção da tela de confirmação** (conflito, duplicado,
   responsável) — concorda que entram, ou prefere que a entrada única fique sem
   o gate de conflito e ele só apareça depois, na tela do caso?
2. **A aba Peças dentro do caso** duplica o módulo `/pecas` no primeiro corte.
   Aceita a duplicação temporária, ou prefere que `/pecas` já nasça como visão
   transversal no mesmo PR?
3. **Transições de estado sugeridas por evento** (item 6.2) — sugerir com um
   toque de confirmação, ou mover sozinho e deixar o advogado corrigir?
4. **Ordem**: começar por 2 (workspace) ou por 3+4 (entrada única)? A ordem
   acima é a do desenho aprovado, mas a entrada única é a que você sente
   primeiro.

---

## Decisões do titular — 2026-08-02 (segunda rodada)

As quatro perguntas da seção 8 foram respondidas. O desenho passa a
especificação aprovada, com estes termos:

1. **Gates por exceção**: o titular deixou em aberto ("não sei"); na dúvida,
   prevalece a recomendação do desenho — **os gates entram** na tela de
   confirmação. Conflito de interesses é dever do EOAB, não atrito; os blocos
   só aparecem quando há achado real.
2. **Aba Peças**: **duplica** o módulo `/pecas` temporariamente. A conversão
   de `/pecas` em visão transversal fica para depois do primeiro corte.
3. **Transições de estado**: **movem sozinhas** — sempre para frente, nunca
   regridem, e o advogado pode corrigir manualmente. Primeiro documento
   vinculado ⇒ `em_instrucao`; primeira peça ⇒ `em_producao`; protocolo ⇒
   `protocolado`.
4. **Ordem**: a proposta da seção 7, confirmada — correção da Sala Jurídica →
   workspace do caso → entrada única (backend, depois telas) → transições.

---

*Desenho aprovado em duas rodadas. Implementação autorizada nesta branch.*
