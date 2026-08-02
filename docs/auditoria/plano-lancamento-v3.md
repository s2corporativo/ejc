# EJC — Plano de Lançamento (v3)
## Do estado atual até "um advogado leva um caso do início ao fim sem preguiça"

> **O que este documento é:** o plano de execução para colocar o EJC em operação.
> **O que ele não é:** o backlog completo. Esse continua sendo o `plano-correcao-v2.md`, que segue válido como referência de todos os 40+ achados da auditoria.
>
> A v3 é **mais curta que a v2 de propósito.** Ela contém apenas o que precisa estar pronto **antes** do primeiro caso real, na ordem em que precisa ficar pronto. Tudo o mais foi deliberadamente empurrado para depois do lançamento (Seção "Depois").

---

## MISSÃO

**Fazer o EJC levar um caso do cliente ao protocolo com pouco atrito — e só então iniciar a operação.**

Critério de sucesso, único e não negociável:

> Um advogado do escritório abre um caso real, leva-o até o protocolo dentro do sistema, e ao final diz que foi **mais fácil** do que fazer fora do sistema.

Se esse teste não passar, nada mais no plano importa.

---

## CONTEXTO QUE O EXECUTOR PRECISA SABER

- **Ferramenta interna** de um escritório com 3 advogados. Não é produto de mercado. Não construa para escala, multi-tenancy ou generalidade.
- **O sistema nunca foi usado de ponta a ponta.** Nenhum caso passou da triagem, nenhuma peça foi protocolada, nenhum lançamento financeiro existe. Isso significa que **não há dado real para preservar e não há hábito consolidado para respeitar** — mudanças de modelo, de status e de navegação são baratas agora e caras depois do lançamento.
- **O problema central não é falta de funcionalidade. É excesso.** 34 módulos, 453 rotas, 211 delas nunca chamadas por nenhuma tela. Levar um caso ao fim exige hoje **15 ações atravessando 8 módulos**. O usuário descreveu o efeito com precisão: *"dá preguiça"*.
- **Regra que atravessa todo o plano:** quando estiver em dúvida entre adicionar e remover, **remova**.

**Leia `CLAUDE.md` na raiz do repositório antes de qualquer bloco.** Ele contém as regras invariantes e as armadilhas conhecidas deste código.

---

# BLOCO 1 — Fazer o sistema dizer a verdade

**Por que primeiro:** enquanto a tela mentir sobre um número, nada mais que você construir será confiável aos olhos de quem usa. Isso é pré-requisito psicológico, não técnico.

**O que está errado:**

```
GET /dashboard/ → "pecas_aguardando_revisao": 0      (com 100% das peças em rascunho)
GET /dashboard/ → casos: {total: 9, ativos: 9, por_status:{triagem:8, arquivado:1}}
GET /cases/     → total: 8                            (dashboard diz 9, listagem diz 8)
GET /cases/?status=ativo → total: 0                   (existem 8 casos)
GET /cases/?status=all   → 500
GET /analytics/roi-por-area → 500 "A equipe foi notificada"   (ninguém é notificado — não há Sentry)
```

**Prompt para colar:**

```
Leia CLAUDE.md e docs/auditoria/plano-correcao-v2.md (apenas a Fase 1).

Corrija os contadores e filtros que hoje mentem sobre o estado do sistema:

1. pecas_aguardando_revisao no dashboard retorna 0 com todas as peças em rascunho.
   Derive o contador do dado real (rascunho + não revisada), não de um status
   intermediário que o pipeline quebrado nunca alcança.
2. casos.ativos conta o caso arquivado. Deve ser 8, não 9.
3. Dashboard e listagem de casos divergem (9 vs 8) sem explicação ao usuário.
4. Filtro status=ativo retorna vazio porque os status reais são triagem/arquivado.
   Crie um enum único compartilhado entre frontend e backend, gerado de uma
   definição só. Se "ativo" e "all" existem na interface, precisam existir no backend.
5. status=all retorna 500. Corrija.
6. /analytics/roi-por-area retorna 500. Corrija o erro E remova a frase "A equipe
   foi notificada" enquanto não houver coletor de erros ativo.

NÃO zere uma métrica para que coincida com a outra. O certo é a métrica refletir
a realidade.

Ao final: tabela com os números do dashboard ANTES e DEPOIS, lado a lado.
```

---

# BLOCO 2 — Desobstruir o caminho

**Por que agora:** não adianta encurtar um caminho que termina em parede. Hoje o fluxo trava na aprovação da peça e nunca chega ao PDF.

**Prompt para colar:**

```
Leia CLAUDE.md e docs/auditoria/plano-correcao-v2.md, itens 2.1 e 2.4.

O bug central: POST /legal-docs/{id}/validar retorna sucesso com score 94, mas
validacao_juridica.ai_log_id nunca é gravado no registro do documento. O endpoint
/aprovar lê esse campo e por isso responde "Status atual: sem_validacao", travando
aprovação e exportação de PDF em cascata. Confirmado que não é permissão — falha
igual como superadmin.

1. Diagnostique a causa real no código antes de escolher entre gravar o vínculo
   após a validação, ou fazer /aprovar consultar o AILog diretamente.
2. Depois de corrigido, consolide o fluxo de 4 chamadas (validar → marcar log →
   aprovar → pdf) em UM único ato de conferência e assinatura.
3. Libere a exportação de PDF desde o estado de minuta — o advogado precisa ler
   antes de assinar.
4. Troque o rótulo "rascunho" por "minuta final — conferir e assinar".

PRESERVE o registro de quem conferiu, quando e sobre qual versão. Consolidar
etapas é o objetivo; apagar o rastro não é (Lei 8.906/94, art. 32).

O backfill dos registros existentes roda em dry-run primeiro, com relatório de
quantos seriam afetados, antes de aplicar.

Critério de aceite: criar peça → conferir → assinar → PDF, ponta a ponta.
```

---

# BLOCO 3 — Encurtar o caminho

**Este é o bloco que resolve a preguiça.** É também o de maior valor e o único que envolve desenho de produto, não só correção.

## 3.1 Entrada única

Hoje existem quatro portas de entrada — `entrada-universal/processar`, `entrevista-inteligente`, `sala-juridica`, triagem automática — e **nenhuma termina num caso pronto**. Todas as peças existem; falta encadeá-las.

## 3.2 O caso como espaço de trabalho

Hoje a navegação é **por funcionalidade** (módulo de Casos, de Prazos, de Documentos, de Peças) e o advogado atravessa oito módulos carregando contexto na cabeça. Deve passar a ser **por entidade**: tudo acontece dentro da tela do caso. Os módulos viram visões transversais ("todos os prazos da semana"), não estações de trabalho.

## 3.3 Quatro estados no lugar de nove etapas

A jornada de nove etapas foi desenhada pensando em completude, não em trabalho real. Faz o advogado sentir que está sempre atrasado.

**Prompt para colar:**

```
Leia CLAUDE.md. Este bloco é redesenho de produto, não correção de bug.
Proponha antes de implementar — quero revisar o desenho.

OBJETIVO: hoje levar um caso do início ao protocolo exige 15 ações atravessando
8 módulos. Alvo: abrir um caso completo em UMA tela, em menos de 2 minutos.

1. ENTRADA ÚNICA
   Construa uma tela única de entrada onde o advogado faz uma de duas coisas:
   cola o relato do cliente, ou arrasta os documentos.
   O sistema devolve, numa tela de confirmação: cliente identificado (ou cadastro
   novo pré-preenchido), área sugerida, fatos estruturados, documentos já
   classificados E vinculados ao caso, prazo detectado se houver, próxima ação.
   O advogado confere e confirma. Um clique.

   Não construa IA nova. Encadeie o que já existe: entrada-universal/processar,
   entrevista-inteligente, sala-juridica e a triagem automática.
   Corrija de passagem a conversão sala-juridica → caso, que hoje perde
   descricao_fatos e as evidências levantadas na conversa.

2. O CASO COMO ESPAÇO DE TRABALHO
   Reorganize a navegação de "por funcionalidade" para "por entidade".
   Dentro da tela do caso deve ser possível, sem sair dela: anexar e vincular
   documento, criar prazo, redigir/conferir/exportar peça, lançar hora e despesa,
   registrar andamento.
   Os módulos de Prazos, Documentos e Peças permanecem, mas como visões
   transversais (relatórios), não como lugar onde se trabalha.

3. QUATRO ESTADOS
   Substitua a jornada de 9 etapas por 4 estados: Aberto → Em instrução →
   Em produção → Protocolado (e Encerrado).
   O que hoje é "etapa" (triagem, inteligência, estratégia) vira tarefa OPCIONAL
   dentro do estado, não marco a vencer.
   Migre os status existentes. Não há dado real em produção, então a migração é barata.

Me mostre o desenho das telas antes de codificar.
```

---

# BLOCO 4 — Enxugar

**Por que antes do lançamento:** o menu que a equipe vir no primeiro dia é o menu que ela vai considerar normal. Comece com o menu certo.

**Prompt para colar:**

```
Leia CLAUDE.md e docs/auditoria/plano-correcao-v2.md, item 6.5.

Reduza a navegação de 34 módulos para o conjunto que o escritório realmente usa.

REMOVA DA NAVEGAÇÃO (não apague o código agora — apagar dá trabalho e risco;
basta sumir da vista):
- Jurimetria e predição de êxito (vazios; jurimetria com 8 casos é anedota)
- Victory Vault (vazio)
- Radar regulatório e Notícias (RSS de ConJur/JOTA; não é ERP)
- Sociedade / retiradas de sócio (nenhum sócio cadastrado)
- Áreas de atuação não praticadas — os casos reais são consumidor e civil

REMOVA DE VERDADE, incluindo o código:
- O módulo diplomacia-v3, especificamente os endpoints /diplomacia-v3/analisar-magistrado
  e /diplomacia-v3/dossie-pressao. Decisão do escritório: risco reputacional e
  disciplinar inaceitável, independentemente do que o código faça.

EXPONHA o que já existe e ninguém vê — 15 calculadoras jurídicas funcionais no
backend sem nenhuma tela (dosimetria, prescrição penal, verificar-anpp, dano moral,
partilha-divorcio, alimentos, usucapiao, prescricao-consumidor, prazos-contestacao,
juros-mora e outras — ver item 5.1 da v2).
Antes de construir a interface, teste as 15 e me diga o que cada uma exige e retorna.

AS 163 SKILLS DE IA: mantenha no catálogo apenas as que têm uso registrado nos logs.
Arquive o resto. Ninguém navega 163 opções.
```

---

# BLOCO 5 — Não perder prazo

**Prompt para colar:**

```
Leia CLAUDE.md e docs/auditoria/plano-correcao-v2.md, itens 0.2, 3.1 e 3.2.

A captura de intimações do DJEN nunca registrou um único documento em toda a sua
história, e três painéis reportam "ok" o tempo todo, porque o monitoramento pergunta
"o job rodou?" em vez de "o job entregou?".

1. Faça o monitoramento aferir RESULTADO, não execução. Toda fonte de ingestão deve
   declarar o que significa sucesso em termos de saída, e alertar quando: uma fonte
   historicamente produtiva zerar; uma fonte nunca tiver produzido nada; ou N
   execuções consecutivas retornarem 0.
2. Investigue os três importadores juris_import_* — dormentes há ~7 dias e com zero
   registros em toda a história, marcados como ativos.
3. A fonte anpd falha com ultimo_erro null. Corrija a captura da exceção e diagnostique.
4. Instrumente o parser "fail-safe" do TJMG: registre a contagem de itens brutos
   recebidos ANTES do parsing, para distinguir "nada veio" de "veio e não parseou".

Este bloco depende de uma ação humana que não é sua: cadastrar as OABs dos três
advogados no monitoramento DJEN. Confirme comigo que foi feito antes de testar.
```

---

# BLOCO 6 — Preparar os dados da operação

Não é desenvolvimento. É cadastro e configuração — mas se não for feito antes, contamina a operação desde o primeiro dia.

| O que | Estado hoje | Por quê |
|---|---|---|
| OAB dos 3 advogados no DJEN | vazio (só uma inscrição, em conta administrativa) | Sem isso não há captura de intimação |
| `oab_number` no perfil de cada advogado | `null` nos três | Aparece em peça e procuração |
| Excluir dados de teste | 37 casos na lixeira, peças órfãs, 2 contas fictícias | Começar sem saber o que é real é fatal |
| Conta `homolog.qa` (superadmin) | ativa em produção | Risco de segurança |
| Tabela de honorários OAB/MG | `{"disponivel": false}` | Sem base para teto/piso ético |
| Sócios e percentuais | vazio | Sem isso não há distribuição |
| Categorias de despesa | — | Definir antes do primeiro lançamento |
| RAG das áreas praticadas | 29 de 36 áreas em cobertura crítica | Cubra **só consumidor e civil**, e bem |
| Modelos de peça do escritório | 8 peças no acervo | A IA redige muito melhor com exemplos da casa |
| Ambiente de homologação | não existe | Há rotina de teste rodando contra produção |

---

# BLOCO 7 — O teste do primeiro caso real

**Este bloco não é do Claude Code. É seu.**

Escolha um caso real de complexidade média e leve-o do início ao fim dentro do sistema, com um advogado usando de verdade e alguém anotando.

Três regras para o teste valer:

**Não conserte nada durante a passagem.** Anote e siga. Se parar para depurar, vira sessão de depuração e você perde a observação do fluxo.

**Anote a hesitação, não só o erro.** "Não sei onde clicar" é achado tão válido quanto uma mensagem de falha — e mais difícil de descobrir depois.

**A ordem em que os problemas aparecerem já é a ordem de prioridade.** Ela reflete o caminho real, que nenhum plano feito de fora consegue prever.

Expectativa realista: entre 15 e 25 itens, dos quais uns seis explicam a maior parte da preguiça.

**Só depois que esse teste passar é que a operação começa.**

---

# DEPOIS DO LANÇAMENTO

Deliberadamente adiado. Não gaste tempo nisso antes de operar:

**Ciclo financeiro completo** (apontamento de horas → despesa → fatura → conciliação). É o que transforma o EJC em ERP de verdade, mas pode entrar com a operação já rodando.

**Integração de peticionamento** (PJe/eproc/Projudi). Alto valor, alto esforço. Enquanto não existir, exportar o PDF e subir à mão é aceitável.

**Portal do Cliente.** Nenhum cliente usando ainda. **Uma exceção não negociável e imediata:** confirmar que a métrica de "chance de êxito" não é serializada em nenhum endpoint `/portal/*`. É rápido e é risco ético (Código de Ética da OAB, art. 6º, parágrafo único, e art. 34, XXIX).

**Acessibilidade** (44 de 68 bundles sem `aria-*`). Real e importante; não bloqueia três advogados.

**Paleta e design tokens.** Estética sobre número errado não convence ninguém. Depois do Bloco 1.

**Remoção física das 211 rotas órfãs.** Sumir da navegação (Bloco 4) já resolve a confusão. A faxina do código fica para uma janela tranquila.

**Purga definitiva / LGPD, Sentry, correção do prefixo `/v1/` duplicado, unificação da taxonomia de áreas, e o erro jurídico sobre decadência nas skills.** Todos importantes, todos no `plano-correcao-v2.md`, nenhum bloqueia o lançamento — **com uma ressalva: o erro de decadência (art. 487, II do CPC) deve ser corrigido antes que a IA seja usada para peça que vá a protocolo.**

---

## ORDEM RECOMENDADA

| Ordem | Bloco | Natureza | Bloqueia o lançamento? |
|---|---|---|---|
| 1 | Verdade | Correção | Sim |
| 2 | Desobstruir | Correção | Sim |
| 3 | Encurtar | Redesenho | Sim — é o que resolve a preguiça |
| 4 | Enxugar | Curadoria | Sim — o menu do primeiro dia vira o normal |
| 5 | Prazo | Correção + humano | Sim |
| 6 | Dados | Cadastro | Sim |
| 7 | Primeiro caso real | Teste humano | **É o critério de lançamento** |

Uma sessão do Claude Code por bloco. Sessão nova a cada bloco.

---

*v3 — plano de lançamento. O backlog completo permanece em `plano-correcao-v2.md`.*
