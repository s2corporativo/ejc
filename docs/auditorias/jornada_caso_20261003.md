# Auditoria da jornada de caso — 03/10/2026

A simplificação deve ligar a inteligência existente ao trabalho do caso. A
Entrada Única, o workspace, o orquestrador e o fluxo central de peças já existem.
A principal falha confirmada é o dossiê da Entrada não participar da derivação
que orienta o operador, embora o snapshot esteja salvo e aprovado.

Escopo: código atual da branch de redundâncias, frontend/backend, contratos de
entrada/conversão, IA, documentos/provas, estratégia, prazos, peças, aprovação,
assinatura/protocolo, acompanhamento, financeiro e encerramento/aprendizagem.
122 testes backend e 36 frontend passaram; três cenários adicionais foram
reproduzidos com fixtures fictícias usando o código real de derivação.
Não houve teste de peticionamento em tribunal real, dados reais ou medição de
cliques/tempo por advogado. As medições históricas do desenho de agosto não
representam a experiência atual.

## Jornada existente e controles preservados

| Momento | Implementação observada | Controle que deve permanecer |
|---|---|---|
| Receber relato/documentos | `/entrada`, modo manual conforme perfil, Sala e Raio-X preliminares | RBAC, contexto de cliente, deduplicação e preservação dos originais |
| Identificar e converter | confirmação da Entrada; serviços de conversão | conflito de interesses, qualificação, vínculo de documentos e idempotência |
| Instruir o caso | workspace, partes, provas, ficha, dossiê/snapshots | origem/versionamento, associação fato→prova, aprovação humana |
| Planejar | orquestrador, matriz de teses, Motor de Peça | fontes, vigência, checklist, termo inicial confirmado |
| Contratar | honorários, procuração, contrato/kit | aprovação e acesso jurídico restrito |
| Produzir e revisar | aba Peças reutiliza `Pecas` e gerador canônico | contexto de caso, HITL, validação da versão/hash corrente |
| Assinar e protocolar | fluxo de peças e ajuizamento por capacidade do tribunal | revisão humana, assinatura, número/data/tribunal e comprovante vinculado |
| Acompanhar | processos, intimações, atividades, prazos e financeiro | ownership, confirmação do prazo e distinção do ciclo vigente |
| Encerrar/guardar | diagnóstico e `/cases/{id}/encerrar`, arquivo e memória | prazos bloqueantes, alertas confirmados/justificativa, auditoria, retenção; aprendizagem acessória não invalida fechamento |

## Achados e recomendações

1. **P1 — snapshot da Entrada não reconhecido.**
   `entrada_juridica_service.py:545` grava `origem="entrada_unica"`, permitida
   no modelo; `legal_case_orchestrator.py:91` não inclui essa origem entre os
   snapshots de conteúdo. Reprodução: snapshot aprovado `intake` →
   `classificacao`; mesmo snapshot `entrada_unica` → `entrada`, ambas as flags
   de inteligência falsas. Reconhecer a origem no contrato compartilhado e
   verificar Entrada→aprovação→orquestrador. Isso não é perda do dado salvo nem
   demonstra bypass de aprovação.

2. **P2 — orientação pelo histórico em vez do ciclo atual.**
   `legal_case_orchestrator.py:254` prioriza qualquer peça protocolada. Peça
   antiga protocolada + minuta nova → `acompanhamento`, somente `analisar_peca`
   como ação sugerida. Também há `classificacao` com snapshot atual não
   aprovado quando um antigo foi aprovado. São regras deliberadas de
   agregação, mas prejudicam a orientação de novo trabalho. Selecionar
   peça/versão vigente para recomendar a ação, preservando todos os artefatos
   anteriores e os gates dos endpoints.

3. **P2 — o pós-criação continua na Entrada.**
   `EntradaUnica.tsx:283` muda para dossiê local; `DossieJuridico.tsx:115`
   dispara nova análise ao montar. Depois o operador pode abrir outra visão
   do mesmo caso. Levar a confirmação diretamente ao workspace, exibindo o
   snapshot persistido; nova análise somente por ação explícita/novas provas.
   Preservar o dossiê completo e sua aprovação, sem regeneração por navegação.

4. **P2 — cinco agrupadores, sete abas principais, dez estados internos e
   dezesseis marcos apresentados.**
   `caseNav.ts:33`, `CasoDetalhe.tsx:929`, `legal_case_orchestrator.py:71` e
   `OrquestradorPanel.tsx:469` mostram vocabulários distintos. Não são quatro
   domínios a apagar: representam navegação, progresso e evidências. Usar os
   cinco agrupadores existentes em todas as superfícies; mostrar próxima
   ação e bloqueios, com os dezesseis marcos no detalhamento. Manter as seis
   situações persistidas do caso e seus deep-links.

5. **P1 — falha de consulta pode parecer ausência de dados.**
   `CasoDetalhe.tsx:348` engole erro em `TabLista`, mantendo lista/valores
   inicialmente vazios; `:715` redireciona qualquer falha de carregar caso
   para a lista. Análise estática: não há distinção ali entre indisponibilidade,
   falta de permissão e ausência. Exibir erro/repetição e preservar o último
   dado com indicação de desatualização. O painel do orquestrador já distingue
   erro de carga inicial; esse padrão deve ser reaproveitado.

6. **P2 — protocolo distribuído em duas requisições.**
   `Pecas.tsx:370` registra comprovante, depois muda status. O primeiro handler
   (`legal_docs.py:1135`) faz commit antes da segunda requisição. Uma falha da
   segunda permite resultado parcial e mensagem de erro após registro salvo.
   Propor uma operação canônica transacional/idempotente, reutilizando os
   gates atuais de revisão, validação, ownership e prova do protocolo. A
   auditoria não executou falha de rede nesse fluxo nem alterou os handlers.

7. **P2 — dois lugares podem orientar a próxima ação.**
   O orquestrador usa artefatos; `TabResumo.tsx:956` exibe
   `Case.proxima_acao`, cadastrada separadamente. Unificar a apresentação numa
   fila determinística: prazo urgente → bloqueio real → tarefa do ciclo atual.
   Preservar ações manuais e identificar sua autoria/prioridade.

8. **P2 — contrato canônico de produto incompleto/desatualizado.**
   `FLUXO_CANONICO_EJC.md:24` mantém operações/transições em branco e `:44`
   descreve status anteriores à migration 126. Documentar o fluxo realmente
   implementado para revisão do titular, incluindo exceções de caso já
   judicializado, entrada manual, trabalho extrajudicial e reabertura. Não
   converter o texto histórico em migration ou decisão nova por inferência.

9. **Oportunidade de desempenho a medir.**
   `legal_case_orchestrator.coletar_artefatos` carrega listas de snapshots,
   peças, teses, propostas e prazos completos para derivar flags. Avaliar
   seleção de metadados/versões pertinentes e consultas existenciais; paginar
   o detalhamento. Não foi medida latência dessa consulta; nenhum histórico
   deve ser eliminado para reduzir a leitura.

## Simplificação proposta

Entrada → confirmação → `/casos/:id`. Dentro do caso, manter **Visão,
Atividades, Documentos, Estratégia e Financeiro**, já definidos em `caseNav`.
A produção/revisão/protocolo permanece acessível por uma ação principal e
pelos componentes canônicos da aba Peças. Módulos globais continuam como
visões da carteira, sem exigir saída do caso para tarefas contextuais.

A Visão apresenta: situação do caso, prazo urgente, próxima ação concreta,
bloqueios com destino de resolução e última evidência/versão aprovada. A
jornada técnica fica expansível, com trilha de auditoria integral. Fatos,
provas, teses, fontes, riscos, honorários e aprendizagem continuam acessíveis.
Aprovações, assinatura, confirmação de prazo e protocolo permanecem explícitos.
Atividades não aplicáveis dependem de política do domínio; não marcar como
concluídas ou remover um gate apenas para encurtar a tela.

Ordem sugerida: (1) reconhecer inteligência da Entrada; (2) orientar pelo
ciclo atual e distinguir erros; (3) conectar pós-criação ao workspace;
(4) alinhar navegação/detalhamento; (5) consolidar protocolo e medir desempenho.
As fases são de apresentação; não há proposta de trocar novamente o enum.

Critérios de aceitação: snapshot aprovado continua orientando o mesmo caso;
novo ciclo destaca sua minuta; nenhuma confirmação humana desaparece;
sem reupload/redigitação/reanálise apenas ao navegar; erro nunca significa
"sem documentos"/"zero pendências"; protocolo parcial é tratado; todas as
capacidades anteriores e links históricos continuam acessíveis. Medir telas,
cliques, repetições de análise e tempo numa jornada fictícia antes/depois, sem
prometer percentuais ainda não medidos.

## Limites e estado da entrega

Esta auditoria é diagnóstico/proposta; não mudou comportamento do produto.
Três achados estão registrados em `docs/ia/PROBLEMAS_CONHECIDOS.md`. Os 122/36
checks cobrem contratos, não são um único teste E2E contra todas as integrações.
A migration 171 e a retirada futura dos espelhos continuam sujeitas a decisão
humana; a higienização remove caches, preserva evidências e não purga dados.
