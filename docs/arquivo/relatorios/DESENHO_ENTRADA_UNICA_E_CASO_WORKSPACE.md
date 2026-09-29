# Bloco 3 — desenho antes do código

**O que este documento é:** a proposta que o Bloco 3 do
`docs/auditoria/plano-lancamento-v3.md` pede antes de qualquer implementação —
*"proponha antes de implementar — quero revisar o desenho. Me mostre o desenho
das telas antes de codificar."*

**O que ele não é:** implementação. Nada aqui foi construído. Este é o artefato
que precisa da sua revisão para que a implementação valha a pena.

**Por que separado:** os Blocos 1, 2, 4 e 5 eram correção e curadoria — dava
para verificar se estavam certos contra o código. O Bloco 3 é desenho de
produto: se eu implementasse antes de você olhar, o risco não seria bug, seria
construir a coisa errada com esmero.

---

## O alvo, e como ele será medido

> Abrir um caso completo em **uma tela**, em **menos de dois minutos**.

Hoje são **15 ações atravessando 8 módulos**. A medição não é subjetiva: conte
cliques e trocas de tela numa passagem real. Se ao final da implementação um
caso novo ainda exigir mais de três telas, o bloco não cumpriu o objetivo,
independentemente do que o código faça.

---

## 3.1 — Entrada única

### O que existe hoje, desconectado

| Peça | O que faz | Onde termina |
|---|---|---|
| `POST /entrada-universal/processar` | OCR, classificação de documento, dedup | devolve JSON; ninguém consome |
| `entrevista-inteligente` | triagem por relato livre | tela própria, não gera caso |
| `sala-juridica` | conversa estruturada com IA | tem `/converter`, que perde os fatos |
| triagem automática | classifica área e urgência | roda dentro do caso, depois de criado |

Quatro portas, nenhuma termina num caso pronto. **A intervenção de maior retorno
do sistema inteiro não é construir IA nova — é encadear o que já existe.**

### A tela proposta

Uma rota nova, `/entrada`, com **um** campo e **uma** zona de arrastar:

```
┌──────────────────────────────────────────────────────────┐
│  Novo caso                                               │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Cole aqui o que o cliente contou.                  │  │
│  │                                                    │  │
│  │                                                    │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ─────────────────  ou  ─────────────────                │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │        Arraste os documentos aqui                  │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│                                     [ Analisar ]         │
└──────────────────────────────────────────────────────────┘
```

Sem seletor de área. Sem tipo de caso. Sem cliente. **Nada que o sistema possa
inferir deve ser perguntado antes de tentar inferir.**

### A tela de confirmação

O resultado da análise vira uma tela única de conferência — tudo editável, nada
obrigatório de digitar:

```
┌──────────────────────────────────────────────────────────┐
│  Confira e confirme                                      │
│                                                          │
│  Cliente     Maria S. da Costa            [é outro]      │
│              ✓ já cadastrada · 2 casos anteriores        │
│                                                          │
│  Área        Consumidor                   [trocar]       │
│                                                          │
│  Fatos       Negativação indevida após quitação do       │
│              contrato em 12/03. Cobrança persistiu…      │
│                                              [editar]    │
│                                                          │
│  Documentos  ✓ Comprovante de pagamento    (vinculado)   │
│              ✓ Print da negativação        (vinculado)   │
│              ⚠ Contrato — não reconhecido  [classificar] │
│                                                          │
│  Prazo       nenhum detectado             [criar prazo]  │
│                                                          │
│  Próxima     Notificação extrajudicial     [trocar]      │
│  ação                                                    │
│                                                          │
│                        [ Criar caso ]                    │
└──────────────────────────────────────────────────────────┘
```

Um clique em **Criar caso** e o caso existe, com cliente vinculado, fatos
gravados, documentos anexados **e vinculados**, e próxima ação definida.

### Regras de desenho que não podem ser negociadas na implementação

**Nada bloqueia.** Se a IA não identificar o cliente, o campo vem em branco e
editável — não vira erro. Se a área não for inferida, o advogado escolhe. A tela
**sempre** chega ao botão de criar. O sistema atual falha justamente por
transformar cada incerteza em obstáculo.

**A IA indisponível não derruba a entrada.** É o padrão que a auditoria elogiou
na extração de documentos: preservar o determinístico, sinalizar a
indisponibilidade, marcar revisão obrigatória. Sem IA, a tela vira um formulário
curto — pior, mas funcional.

**Documento anexado é documento vinculado.** Hoje 7 dos 19 documentos não têm
`case_id`; vincular é passo manual e separado. Nesta tela, o upload já nasce
preso ao caso que está sendo criado.

**A conversão da Sala Jurídica precisa ser corrigida no caminho.** Hoje
`POST /sala-juridica/{id}/converter` perde `descricao_fatos` e as evidências
levantadas na conversa. Enquanto isso não for corrigido, a entrada única
herda o mesmo defeito.

### O que a implementação encadeia

```
relato ─┬─→ entrevista-inteligente ──┐
        │                            ├─→ triagem (área, urgência) ─┐
docs ───┴─→ entrada-universal ───────┘                             │
                    │                                              │
                    └─→ classificação + extração de partes/datas ──┤
                                                                   ▼
                                                        tela de confirmação
                                                                   │
                                                    POST /cases + vínculos
```

Nenhuma chamada de IA nova. Nenhum modelo novo. Orquestração.

---

## 3.2 — O caso como espaço de trabalho

### O diagnóstico

Hoje a navegação é **por funcionalidade**: módulo de Casos, de Prazos, de
Documentos, de Peças, Financeiro. Para trabalhar um caso, o advogado atravessa
oito deles carregando o contexto na cabeça. É o padrão de ERP dos anos 2010 e é
a origem direta da fadiga.

### A mudança

A tela do caso deixa de ser uma **ficha** e passa a ser o **lugar onde o
trabalho acontece**. Dentro dela, sem sair:

| Ação | Hoje | Proposto |
|---|---|---|
| anexar e vincular documento | GED, dois passos | aba Documentos do caso, um passo |
| criar prazo | módulo Prazos | aba Prazos do caso, a partir da intimação |
| redigir/conferir/exportar peça | módulo Peças | aba Peças do caso |
| lançar hora e despesa | Financeiro | aba Financeiro do caso |
| registrar andamento | Casos | aba Andamentos |

Os módulos **continuam existindo**, mas mudam de função: viram **visões
transversais** — "todos os prazos da semana", "todas as peças aguardando
conferência". São relatórios, não estações de trabalho.

**Isso é rearranjo de interface, não de arquitetura de dados.** Os endpoints já
existem e já aceitam `case_id`. O trabalho é de frontend.

### Risco a vigiar

`CasoDetalhe.tsx` já é grande. Empilhar cinco abas nele sem quebrar em
componentes produz um arquivo impossível de manter. A implementação deve
começar pela extração das abas em componentes próprios, com carregamento sob
demanda — não pelo conteúdo novo.

---

## 3.3 — Quatro estados no lugar de nove etapas

### O que existe

> **Desatualizado (conferido em 24/08/2026):** `backend/app/routers/jornada_caso.py`
> não existe mais no repositório. O trecho abaixo descreve o desenho original e
> permanece como registro; confirme no código antes de usá-lo como referência.

`backend/app/routers/jornada_caso.py` calcula **nove etapas** de forma
determinística: Cliente → Triagem → Documentos → Inteligência → Estratégia →
Produção → Revisão → Protocolo → Gestão. É código bom — funções puras, sem IA,
auditável.

O problema não é a implementação. É o que nove marcos **comunicam**: que o
advogado está sempre atrasado em alguma coisa. Na prática a maioria dos casos
pula metade das etapas, e as puladas ficam eternamente vermelhas.

### A proposta

Quatro estados que descrevem o que de fato muda no caso:

| Estado | Significa | Vem de |
|---|---|---|
| **Aberto** | existe, tem cliente, tem fatos | `triagem` |
| **Em instrução** | juntando documentos e provas | `ativo` (com docs) |
| **Em produção** | peça sendo redigida e conferida | `ativo` (com peça) |
| **Protocolado** | entregue ao juízo | novo |
| *Encerrado* | fora da operação | `encerrado`, `arquivado`, `acordo` |

O que hoje é **etapa** — triagem, inteligência, estratégia — vira **tarefa
opcional dentro do estado**, não marco a vencer. A diferença é psicológica e é
grande: tarefa opcional não gera culpa; marco não cumprido gera.

### O ponto que exige a sua decisão

**Isto mexe no enum `casestatus` do Postgres**, que é a fonte única de verdade de
`app/core/status_caso.py` e tem paridade travada por teste com
`frontend/src/types/caseStatus.ts`. Duas rotas possíveis:

**(a) Estados novos como camada de apresentação.** O enum fica como está;
os quatro estados são derivados dos seis valores atuais. Barato, reversível,
sem migration. **Custo:** o vocabulário do banco continua diferente do que o
advogado vê — exatamente o defeito que o Bloco 1 corrigiu em outra frente.

**(b) Migrar o enum.** Os quatro estados viram os valores reais. Honesto e
definitivo. **Custo:** migration com conversão de dado, e a janela para isso
fecha no dia em que o primeiro caso real entrar.

**Recomendo (b), e recomendo agora.** O plano é explícito sobre a janela: *"não
há dado real para preservar e não há hábito consolidado para respeitar — mudanças
de modelo, de status e de navegação são baratas agora e caras depois do
lançamento."* Oito casos em `triagem` e um `arquivado` é o custo total da
migração hoje. Depois do lançamento, é outra ordem de grandeza.

Mas **é decisão sua**, não minha: (b) toca o schema, e o plano deixa claro que
mudança de modelo com dado real é irreversível na prática.

---

## Ordem de implementação sugerida

| # | Entrega | Depende de | Tamanho |
|---|---|---|---|
| 1 | Corrigir a conversão Sala Jurídica → Caso | — | pequeno |
| 2 | Quatro estados — via (a) ou (b), conforme sua decisão | decisão do titular | médio |
| 3 | Tela do caso como espaço de trabalho | 2 | grande |
| 4 | Entrada única + tela de confirmação | 1 | grande |

A entrada única vem por último de propósito: ela **cria** casos, e criar caso
num modelo de estados que ainda vai mudar é retrabalho garantido.

---

## O que eu preciso de você antes de codificar

1. **Os quatro estados estão certos?** Em particular: "Em instrução" e "Em
   produção" são a divisão que o escritório reconhece, ou vocês pensam o
   trabalho de outro jeito?
2. **(a) ou (b)** para o enum de status.
3. **A tela de confirmação mostra o que importa?** Falta algo que o advogado
   confere sempre e que eu não listei?
4. **Alguma das cinco abas do caso é dispensável** no primeiro corte? Menos aba
   é mais rápido de entregar e mais fácil de acertar.

---

*Desenho para revisão. Nenhuma linha de implementação foi escrita.*

---

## Decisões do titular — 2026-08-02

As quatro perguntas foram respondidas. O desenho acima passa de proposta a
especificação aprovada, com estes termos:

1. **Estados**: os quatro, como propostos — Aberto → Em instrução → Em produção
   → Protocolado, e Encerrado.
2. **Enum**: **migrar de verdade** (opção b). Migration com conversão dos casos
   existentes, agora, enquanto a janela está aberta.
3. **Tela de confirmação**: aprovada como desenhada.
4. **Primeiro corte do caso-workspace**: **quatro abas** — Documentos, Prazos,
   Peças e Andamentos. **Financeiro (hora/despesa) fica para depois**, por ser a
   aba menos ligada ao fluxo caso→protocolo.

### Verificação posterior ao desenho

O pré-requisito nº 1 da ordem de implementação — corrigir a conversão Sala
Jurídica → Caso — **já está resolvido no código**: `converter_em_caso`
(`legal_chat_service.py`) grava `descricao_fatos` no caso criado, com gates de
conflito de interesses, deduplicação e idempotência por lock pessimista. O
defeito que a auditoria viu em produção não existe mais no repositório.

### Refinamento na migração do enum

O mapeamento da tabela 3.3 agrupava `arquivado` sob *Encerrado* como
apresentação. Na migração real, `arquivado` **permanece valor próprio** do enum:
`core/status_caso.py` distingue deliberadamente desfecho (`encerrado`) de guarda
(`arquivado`), e os endpoints de arquivar/desarquivar e a lixeira dependem dessa
distinção. O enum final fica com seis valores:

    aberto · em_instrucao · em_producao · protocolado · encerrado · arquivado

`triagem` → `aberto`; `ativo` → `em_instrucao`; `suspenso` → `aberto` (não há
caso suspenso em produção); `acordo` → `encerrado` (acordo é desfecho; não há
caso em acordo em produção). Nenhuma linha real é perdida — os 9 casos são
`triagem` (8) e `arquivado` (1).
