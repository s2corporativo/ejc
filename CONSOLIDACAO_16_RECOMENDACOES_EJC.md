# Consolidação das 16 Recomendações - EJC 2026

## Visão Geral

Este documento consolida as 16 recomendações adicionais para o EJC, mapeando cada uma ao estado atual do repositório e identificando gaps de implementação.

**Data da análise**: Julho/2026  
**Base**: Repositório EJC existente (backend FastAPI + frontend React/TSX)

---

## 1. Dashboard como Central de Ação

### Recomendação
O Dashboard deve organizar o trabalho diário com cards que abrem diretamente as pendências:
- Prazos aguardando confirmação
- Intimações não analisadas
- Tarefas vencidas
- Casos sem próxima ação
- Documentos pendentes do cliente
- Peças aguardando revisão
- Propostas e contratos aguardando aceite
- Cobranças e parcelas vencidas
- Erros de integração
- Análises da IA aguardando validação

### Estado Atual
**✅ Parcialmente Implementado**

Arquivos relacionados:
- `/workspace/frontend/src/pages/DashboardModern.tsx` (1332 linhas)
- `/workspace/backend/app/routers/dashboard.py`
- `/workspace/backend/app/services/dashboard_service.py`

**O que já existe:**
- Dashboard com seção "Meu dia" e "Próxima ação recomendada"
- Cards de prazos críticos (vencidos, 3 dias, 7 dias)
- Integração com financeiro (pendente, atrasado, recebido mês)
- Widget de peças aguardando revisão (`pecas_aguardando_revisao`)
- Widget ambiental crítico
- Clientes ativos

**Gaps identificados:**
1. ❌ Card específico para "intimações não analisadas"
2. ❌ Card "casos sem próxima ação" 
3. ❌ Card "documentos pendentes do cliente" (existe `solicitacoes` no CRM, mas não integrado como pendência documental)
4. ❌ Card "propostas e contratos aguardando aceite"
5. ❌ Card "erros de integração"
6. ❌ Cada card não abre **diretamente** na pendência específica (navegação genérica)

**Próximos passos:**
- Backend: Expandir endpoint `/dashboard/` para incluir contagens específicas de cada pendência
- Frontend: Criar cards individuais com links diretos para filtros específicos
- Implementar deep linking por tipo de pendência

---

## 2. "Próxima Ação" Obrigatória em Todo Caso

### Recomendação
Um caso ativo não pode ficar sem:
- Responsável
- Situação atual
- Próxima providência
- Data esperada
- Grau de urgência
- Eventual bloqueio
- Documento ou evento que originou a ação

Alertas necessários:
- Caso ativo sem próxima ação
- Caso sem atividade há determinado período
- Tarefa concluída sem evidência
- Prazo próximo sem peça iniciada
- Atendimento sem retorno ao cliente

### Estado Atual
**⚠️ Implementação Incompleta**

Arquivos relacionados:
- `/workspace/backend/app/models/case.py` (modelo Case)
- `/workspace/backend/app/models/task.py` (modelo Task)
- `/workspace/backend/app/models/case_movimento.py` (timeline via CaseMovimento)
- `/workspace/frontend/src/pages/CasoDetalhe.tsx` (147990 linhas)
- `/workspace/frontend/src/pages/Casos.tsx` (61003 linhas)

**O que já existe:**
- Modelos `Case` com campos: `advogado_responsavel_id`, `status`, `fase`, `prioridade`
- Modelo `Task` vinculado a casos
- Timeline de movimentos (`case_movimentos`) com tipos: peticao, decisao, audiencia, nota, intimacao, ia
- Frontend extenso de gestão de casos

**Gaps identificados:**
1. ❌ Campo canônico `proxima_acao` no modelo Case
2. ❌ Campo `data_esperada_proxima_acao`
3. ❌ Campo `bloqueio` (texto/json)
4. ❌ Campo `evento_origem_id` (FK para documento/movimento)
5. ❌ Validação de integridade: caso ativo SEM próxima ação
6. ❌ Alertas automáticos baseados em inatividade
7. ❌ Vínculo tarefa-conclusão com evidência obrigatória

**Próximos passos:**
- Migration: Adicionar campos de próxima ação ao modelo Case
- Service: Criar validator de integridade de casos ativos
- Scheduler: Job diário para detectar casos sem movimento
- Frontend: Tornar próxima ação obrigatória no formulário de caso

---

## 3. Estados Operacionais Padronizados

### Recomendação
Evitar status escritos livremente. Usar estados controlados com regras de transição.

**Exemplo Triagem:**
1. Recebida → 2. Aguardando validação → 3. Aguardando documentos → 4. Em análise → 5. Aguardando decisão comercial → 6. Aprovada / 7. Recusada → 8. Convertida em caso → 9. Arquivada

**Exemplo Caso:**
1. Onboarding → 2. Planejamento → 3. Em andamento → 4. Aguardando cliente → 5. Aguardando terceiro → 6. Providência urgente → 7. Negociação → 8. Encerramento → 9. Encerrado

**Regras:** Caso não deve ser encerrado com prazo aberto, documento aguardando assinatura ou lançamento financeiro pendente.

### Estado Atual
**✅ Enums Existentes, ❌ Sem Regras de Transição**

Arquivos relacionados:
- `/workspace/backend/app/models/case.py`:
  - `CaseStatus`: triagem, ativo, suspenso, acordo, encerrado, arquivado
  - `CaseFase`: pre_processual, conhecimento, recursal, execucao, administrativo
  - `CasePrioridade`: baixa, media, alta, critica

**O que já existe:**
- Enums SQLAlchemy bem definidos para status, fase e prioridade
- Status canônicos no banco

**Gaps identificados:**
1. ❌ Máquina de estados com transições válidas
2. ❌ Validação de pré-condições para encerramento
3. ❌ Bloqueio de encerramento com prazos abertos
4. ❌ Bloqueio de encerramento com documentos pendentes
5. ❌ Bloqueio de encerramento com fees pendentes
6. ❌ Workflow de triagem detalhado (9 estados recomendados vs 6 atuais)

**Próximos passos:**
- Criar serviço `workflow_validator.py` com regras de transição
- Adicionar validação no endpoint de update de caso
- Expandir enum `CaseStatus` se necessário
- Criar migration de dados para normalizar status legados

---

## 4. Linha do Tempo Verdadeiramente Única

### Recomendação
A linha do tempo deve reunir TODOS os eventos:
- Atendimento, ligação, mensagem
- Documento recebido
- Movimentação processual
- Prazo, tarefa, audiência, decisão
- Peça produzida, pagamento
- Mudança de responsável
- Análise da IA, aprovação/rejeição humana

Cada evento deve registrar: autor, data, origem, caso relacionado, informação anterior/posterior.

### Estado Atual
**⚠️ Modelo Base Existe, ❌ Não Unificado**

Arquivos relacionados:
- `/workspace/backend/app/models/case.py` (modelo CaseMovimento)
- `/workspace/backend/app/models/atendimento.py`
- `/workspace/backend/app/models/document.py`
- `/workspace/backend/app/models/deadline.py`
- `/workspace/backend/app/models/task.py`
- `/workspace/backend/app/routers/movimentos.py` (provável)

**O que já existe:**
- Modelo `CaseMovimento` com campos: tipo, descricao, data_evento, created_by, resumo_ia
- Tipos: peticao, decisao, audiencia, nota, intimacao, ia

**Gaps identificados:**
1. ❌ Eventos de atendimento não integrados à timeline do caso
2. ❌ Eventos de documento não espelham na timeline
3. ❌ Eventos de prazo (criação/conclusão) não geram movimento automático
4. ❌ Eventos de tarefa não geram movimento
5. ❌ Eventos financeiros (pagamento) não geram movimento
6. ❌ Mudança de responsável não gera movimento
7. ❌ Decisões de aprovação/rejeição da IA não registradas como evento
8. ❌ Falta campo `dados_antes` / `dados_depois` para auditoria completa

**Próximos passos:**
- Refatorar `CaseMovimento` para ser o registro central único
- Criar service `timeline_service.py` com método unificado `registrar_evento()`
- Implementar triggers/hooks nos principais modelos para gerar movimentos automaticamente
- Adicionar campos de auditoria (antes/depois) quando aplicável

---

## 5. Motor de Prazos com "Prova do Cálculo"

### Recomendação
Cada prazo crítico deve guardar:
- Evento que o originou
- Documento/intimação correspondente
- Data da ciência
- Regra legal aplicada
- Forma de contagem (úteis/corridos)
- Calendário utilizado
- Feriados e suspensões considerados
- Termo inicial e final
- Responsável pelo cálculo e conferência
- Alterações posteriores
- Justificativa de cancelamento

IA sugere, mas ativação depende de confirmação humana. Prazos críticos exigem dupla validação.

### Estado Atual
**✅ Parcialmente Implementado**

Arquivos relacionados:
- `/workspace/backend/app/models/deadline.py`
- `/workspace/backend/app/routers/deadlines.py`
- `/workspace/backend/app/services/deadline_calculator.py`

**O que já existe:**
- Campos: `data_prazo`, `data_intimacao`, `base_legal`, `tipo` (processual/administrativo/interno/audiencia/prescricao)
- `ciencia_confirmada`, `ciencia_confirmada_em`, `ciencia_confirmada_por`
- `origem` (manual/datajud), `referencia_datajud`
- `confirmado` (para prazos extraídos por IA)
- `origem_documento_id` (FK para documents)
- Calculadora de dias úteis/corridos com feriados
- Auditoria de alteração de data (`PRAZO_ALTERADO`)
- Confirmação de ciência com audit

**Gaps identificados:**
1. ❌ Campo `regra_legal_aplicada` (ex: "CPC art. 219 + 183")
2. ❌ Campo `forma_contagem` (uteis/corridos) - parcialmente em `tipo`
3. ❌ Campo `calendario_utilizado` (tribunal já cobre parcialmente)
4. ❌ Campo `feriados_suspensos` (lista JSON)
5. ❌ Campo `responsavel_calculo_id` (diferente de responsavel_id)
6. ❌ Campo `responsavel_conferencia_id` (dupla validação)
7. ❌ Histórico de alterações com justificativa
8. ❌ Campo `justificativa_cancelamento`
9. ❌ Política de dupla validação para prazos críticos implementada

**Próximos passos:**
- Migration: Adicionar campos de rastreabilidade completa
- Frontend: Formulário de criação com "prova do cálculo" visível
- Implementar política de dupla validação para prazos críticos (tipo=processual + prioridade=critica)
- Criar endpoint de histórico de alterações do prazo

---

## 6. Pesquisa Global do Sistema

### Recomendação
Busca única capaz de localizar (respeitando permissões):
- Cliente (nome, CPF, CNPJ)
- Número de processo, caso, parte contrária
- Documento (e trecho contido)
- Tese, prazo, atendimento, lançamento financeiro

Comandos naturais:
- "casos do cliente X"
- "prazos desta semana"
- "processos sem movimentação interna"
- "documentos aguardando assinatura"

### Estado Atual
**❌ Não Implementada**

Arquivos relacionados:
- Buscas existentes分散 em vários routers (cases.py, clients.py, etc.)

**O que já existe:**
- Rotas individuais de listagem com filtros por módulo

**Gaps identificados:**
1. ❌ Endpoint unificado `/search` ou `/global-search`
2. ❌ Indexação de conteúdo textual de documentos (OCR + vetorial)
3. ❌ Busca full-text cruzando múltiplas entidades
4. ❌ Sintaxe de comandos naturais
5. ❌ Respeito a permissões por caso na busca
6. ❌ Ranking de resultados por relevância

**Próximos passos:**
- Criar router `/search` com endpoints para busca global
- Implementar search service com queries multi-tabela
- Integrar com RAG existente para busca semântica em documentos
- Adicionar filtro de permissão baseado no usuário
- Opcional: Implementar parser de comandos naturais

---

## 7. Três Bases Separadas no RAG

### Recomendação
Separar claramente:
| Base | Conteúdo | Regra principal |
|------|----------|-----------------|
| Jurídica oficial | Legislação, atos, jurisprudência | Vigência, autoridade, atualização |
| Conhecimento do escritório | Modelos, teses, orientações internas | Curadoria, versionamento |
| Documentos do caso | Autos, contratos, provas, comunicações | Sigilo, permissão por caso |

Recuperação deve filtrar permissão **antes** da pesquisa vetorial.

### Estado Atual
**✅ Arquitetura Existente, ⚠️ Segregação a Validar**

Arquivos relacionados:
- `/workspace/backend/app/models/rag.py`
- `/workspace/backend/app/models/legal_doc.py`
- `/workspace/backend/app/models/jurisprudencia_interna.py`
- `/workspace/backend/app/models/matriz_teses.py`
- `/workspace/docs/ai/EJC_SINGLE_AI_CORE_ARCHITECTURE.md`
- `/workspace/docs/google-drive-rag.md`

**O que já existe:**
- Modelo `RAG` com embeddings
- Modelo `LegalDoc` para legislação
- Modelo `JurisprudenciaInterna` para jurisprudência do escritório
- Modelo `MatrizTeses` para teses institucionais
- Documentação de arquitetura Single AI Core
- Integração Google Drive para RAG

**Gaps identificados:**
1. ❌ Validação explícita de segregação nas queries de retrieval
2. ❌ Filtro de permissão por caso ANTES da busca vetorial
3. ❌ Metadados claros de "base de origem" em cada embedding
4. ❌ Política de vigência para documentos jurídicos oficiais
5. ❌ Workflow de curadoria para conhecimento do escritório

**Próximos passos:**
- Revisar `rag.py` e serviços de IA para garantir filtragem por permissão
- Adicionar campo `base_origem` (oficial/escritorio/caso) aos embeddings
- Implementar middleware de verificação de acesso antes do retrieval
- Criar política de curadoria documentada

---

## 8. Ciclo de Publicação do Conhecimento

### Recomendação
Fluxo para entrada na base jurídica:
1. Recebido → 2. Verificado → 3. Classificado → 4. Conferida origem → 5. Verificada vigência → 6. Indexado → 7. Aprovado por curador → 8. Publicado → 9. Atualizado/substituído/retirado

### Estado Atual
**❌ Não Implementado**

Arquivos relacionados:
- `/workspace/backend/app/models/legal_doc.py`
- `/workspace/backend/app/models/jurisprudencia_interna.py`

**O que já existe:**
- Modelos para documentos jurídicos

**Gaps identificados:**
1. ❌ Campos de status de curadoria (recebido, verificado, publicado, etc.)
2. ❌ Campo `curador_id` (responsável pela aprovação)
3. ❌ Campo `vigencia_inicio` / `vigencia_fim`
4. ❌ Campo `fonte_oficial` (URL/DOU)
5. ❌ Campo `documento_substituido_id` (versionamento)
6. ❌ Workflow de aprovação para entrada na base
7. ❌ Flag `permitido_rag` (só após aprovação)

**Próximos passos:**
- Migration: Adicionar campos de workflow de curadoria
- Criar router de curadoria de conhecimento
- Frontend: Interface para curadores aprovarem conteúdos
- Implementar flag de liberação para RAG

---

## 9. Central de IA como Governança

### Recomendação
Central de IA deve controlar:
- Provedores e modelos habilitados
- Finalidade permitida para cada modelo
- Versões de prompts
- Consumo e custo
- Falhas e tempo de resposta
- Fontes recuperadas pelo RAG
- Nível de confiança da extração
- Aprovação/rejeição do usuário
- Fallback entre provedores
- Políticas de envio de dados confidenciais
- Avaliações comparativas

### Estado Atual
**✅ Parcialmente Implementado**

Arquivos relacionados:
- `/workspace/backend/app/models/ai_log.py`
- `/workspace/backend/app/routers/ai.py`, `ai_core.py`, `ai_skills.py`
- `/workspace/docs/ai/EJC_AI_PROVIDER_POLICY.md`
- `/workspace/docs/ai/EJC_AI_COST_AND_AUDIT_POLICY.md`
- `/workspace/docs/ai/EJC_SINGLE_AI_CORE_ARCHITECTURE.md`

**O que já existe:**
- Modelo `AILog` para rastreamento
- Múltiplos providers (Anthropic, etc.)
- Políticas documentadas de provider e custo
- Arquitetura Single AI Core

**Gaps identificados:**
1. ❌ Dashboard de governança de IA (consumo, custo, desempenho por modelo)
2. ❌ Versionamento explícito de prompts
3. ❌ Métricas de tempo de resposta por modelo/tarefa
4. ❌ Registro de fontes RAG usadas em cada resposta
5. ❌ Campo `nivel_confianca` nas extrações
6. ❌ Registro explícito de aprovação/rejeição do usuário
7. ❌ Mecanismo de fallback automático entre providers
8. ❌ Política técnica de risco por tipo de tarefa (não apenas documental)

**Próximos passos:**
- Criar router `/ai/governance` com métricas consolidadas
- Adicionar versionamento aos prompts salvos
- Implementar logging de fontes RAG por requisição
- Criar mecanismo de rating de confiança pós-resposta
- Documentar matriz de risco por tipo de tarefa

---

## 10. Benchmark Jurídico Próprio do EJC

### Recomendação
Criar conjunto fixo de testes sem dados pessoais:
- Casos completos por área
- Documentos incompletos
- Leis revogadas vs vigentes
- Precedentes favoráveis e contrários
- Prazos com feriados/suspensões
- Conflitos de competência
- Pedidos incompatíveis
- Citações inexistentes
- Provas contraditórias
- Situações de "insuficiência de dados"

Métricas: fonte existente, aderência, lacunas, alucinações, precisão, conformidade com rito, custo/tempo.

### Estado Atual
**❌ Não Implementado**

Arquivos relacionados:
- `/workspace/backend/app/eval/` (diretório vazio ou mínimo)
- `/workspace/qa/` (diretório de QA)

**O que já existe:**
- Estrutura básica de eval/QA

**Gaps identificados:**
1. ❌ Dataset de benchmark jurídico próprio
2. ❌ Scripts de avaliação automatizada
3. ❌ Métricas de alucinação/precisão
4. ❌ Comparativo entre modelos (Claude, Maritaca, etc.)
5. ❌ Testes de extração de prazo com feriados
6. ❌ Casos de "resposta correta = declarar insuficiência"

**Próximos passos:**
- Criar diretório `/workspace/benchmark/` com datasets anonimizados
- Implementar scripts de avaliação em `/backend/app/eval/`
- Definir métricas padrão (precisão, recall, alucinação, etc.)
- Rodar baseline com modelos atuais
- Integrar avaliação ao pipeline de deploy de novos prompts

---

## 11. Separação por Nível de Risco da IA

### Recomendação
| Nível | Exemplos | Controle |
|-------|----------|----------|
| Baixo | Classificação, resumo, organização | Revisão simplificada |
| Médio | Extração de obrigações, pesquisa, rascunho | Confirmação obrigatória |
| Alto | Prazo, estratégia, parecer, peça final, valor | Revisão jurídica formal |
| Crítico | Protocolo, mensagem externa, acordo, movimentação financeira | Aprovação expressa; automatismo vedado |

### Estado Atual
**⚠️ Parcialmente Documentado, ❌ Não Implementado Tecnicamente**

Arquivos relacionados:
- `/workspace/docs/ai/EJC_AI_HITL_POLICY.md` (Human-in-the-Loop)
- `/workspace/backend/app/models/ai_log.py`

**O que já existe:**
- Política HITL documentada
- Logs de IA

**Gaps identificados:**
1. ❌ Classificação técnica de tarefas por nível de risco no código
2. ❌ Validação de nível de risco antes de executar ação
3. ❌ Bloqueio de automatismo para tarefas críticas
4. ❌ Fluxo de aprovação formal para tarefas de risco alto
5. ❌ Registro do nível de risco no log de IA

**Próximos passos:**
- Criar enum `AIRiskLevel` no backend
- Adicionar classificação de risco a cada skill/ferramenta de IA
- Implementar validação de risco antes de execução
- Criar fluxo de aprovação para tarefas críticas
- Registrar nível de risco nos logs

---

## 12. Integridade Documental

### Recomendação
Para cada arquivo, preservar:
- Original imutável
- Hash de integridade
- Origem, usuário responsável, data de recebimento
- Versão
- Resultado do OCR
- Páginas utilizadas pela IA
- Extrações realizadas
- Documentos derivados
- Histórico de acesso
- Política de retenção

OCR gera camada derivada, nunca substitui original.

### Estado Atual
**✅ Parcialmente Implementado**

Arquivos relacionados:
- `/workspace/backend/app/models/document.py`
- `/workspace/backend/app/services/document_service.py` (provável)

**O que já existe:**
- Modelo `Document` básico

**Gaps identificados:**
1. ❌ Campo `hash_integridade` (SHA256 do original)
2. ❌ Armazenamento imutável do original (WORM)
3. ❌ Controle de versão de documentos
4. ❌ Campo `ocr_result_id` (separado do original)
5. ❌ Rastreamento de páginas usadas por IA
6. ❌ Registro de documentos derivados (ex: PDF → texto → resumo)
7. ❌ Log de acesso por documento
8. ❌ Política de retenção por tipo documental

**Próximos passos:**
- Migration: Adicionar campos de hash, versão, OCR
- Implementar armazenamento WORM para originais
- Criar serviço de checksum automático no upload
- Implementar log de acesso a documentos sensíveis
- Definir políticas de retenção por categoria

---

## 13. Índice de Saúde do Caso

### Recomendação
Em vez de "chance de êxito", usar **índice operacional de saúde** calculado por regras transparentes:
- Existe próxima ação?
- Existem prazos sem confirmação?
- Faltam documentos?
- Há tarefa vencida?
- A estratégia foi aprovada?
- A procuração está válida?
- Existem parcelas vencidas?
- Há movimentação não analisada?
- Cliente aguardando retorno?
- Responsável definido?

### Estado Atual
**⚠️ Módulo Existente, ❌ Abordagem Diferente**

Arquivos relacionados:
- `/workspace/backend/app/modules/indice_risco/`
- `/workspace/backend/app/modules/score_juridico/`

**O que já existe:**
- Módulos de índice de risco e score jurídico

**Gaps identificados:**
1. ❌ Foco em "risco/êxito" ao invés de "saúde operacional"
2. ❌ Regras de cálculo não transparentes/explicáveis
3. ❌ Não baseado nos critérios operacionais listados
4. ❌ Sem breakdown dos fatores que compõem o índice

**Próximos passos:**
- Revisar módulos existentes de indice_risco/score_juridico
- Refatorar para cálculo baseado em critérios operacionais
- Criar endpoint que retorne breakdown dos fatores
- Frontend: Mostrar saúde como "checklist de saúde" ao invés de % genérica

---

## 14. Aprendizado com Correções dos Advogados

### Recomendação
Quando advogado corrigir a IA, registrar:
- Texto sugerido, correção realizada, motivo
- Tipo do erro, área jurídica
- Fonte utilizada, modelo e versão do prompt

Correções NÃO alimentam automaticamente treinamento/RAG. Precisam de curadoria, anonimização e validação.

### Estado Atual
**❌ Não Implementado**

Arquivos relacionados:
- `/workspace/backend/app/models/ai_log.py`

**O que já existe:**
- Logging básico de IA

**Gaps identificados:**
1. ❌ Mecanismo de capturar correções do usuário
2. ❌ Campos para texto_original, texto_corrigido, motivo
3. ❌ Classificação de tipo_de_erro (alucinacao, omisso, impreciso, etc.)
4. ❌ Workflow de curadoria para correções
5. ❌ Anonimização de dados antes de uso em melhoria
6. ❌ Flag `usado_treinamento` com controle explícito

**Próximos passos:**
- Criar modelo `AICorrection` ou expandir `AILog`
- Frontend: Botão "Reportar erro" / "Sugerir melhoria" nas respostas de IA
- Implementar workflow de curadoria de correções
- Criar política explícita de uso de correções para treinamento

---

## 15. Implantação Sem Grande Refatoração Imediata

### Recomendação
Caminho seguro:
1. Inventariar o que existe ✅
2. Identificar dados duplicados
3. Definir entidades canônicas
4. Criar visualizações integradas
5. Manter compatibilidade com rotas antigas
6. Migrar gradualmente
7. Medir erros e uso
8. Desativar estruturas antigas somente após validação

### Estado Atual
**✅ Alinhado com Abordagem Atual**

Arquivos relacionados:
- Múltiplos relatórios de auditoria na raiz
- `/workspace/PLANO_FASE4_CONSOLIDACAO.md`
- `/workspace/PLANO_ETAPA_4_CORRECAO_SEGURA_EJC.md`

**O que já existe:**
- Cultura de auditoria e documentação
- Plano de consolidação em fases

**Próximos passos:**
- Consolidar este documento ao plano de fase 4 existente
- Priorizar implementações por impacto/risco
- Manter compatibilidade retroativa em todas as migrations

---

## 16. Recuperação de Desastre Testada

### Recomendação
Testar periodicamente restauração, documentando:
- Data do teste, versão restaurada
- Banco recuperado, arquivos recuperados
- Tempo necessário, falhas encontradas
- Responsável pela validação

Google Drive pode ser uma cópia, não a única estratégia.

### Estado Atual
**✅ Parcialmente Implementado**

Arquivos relacionados:
- `/workspace/RUNBOOK_BACKUP.md`
- `/workspace/RUNBOOK_ROTINA_BACKUP_DIARIA_GDRIVE.md`
- `/workspace/scripts/backup/` (provável)

**O que já existe:**
- Runbooks de backup
- Rotina de backup no Google Drive

**Gaps identificados:**
1. ❌ Procedimento documentado de teste de restauração
2. ❌ Histórico de testes de restauração
3. ❌ Métricas de RTO/RPO (Recovery Time/Point Objective)
4. ❌ Backup alternativo além do Google Drive
5. ❌ Automação de teste periódico de restauração

**Próximos passos:**
- Criar runbook de teste de restauração
- Agendar testes trimestrais de restauração
- Documentar resultados de cada teste
- Implementar backup secundário (ex: S3, outro cloud)
- Definir e medir RTO/RPO alvo

---

## Prioridade Recomendada (Consolidada)

Baseado nas 16 recomendações e no estado atual:

### Prioridade 1 (Crítico - Segurança/Integridade)
1. **Próxima ação obrigatória e central de pendências** (#1, #2)
2. **Motor auditável de prazos** (#5)
3. **Permissões e segregação por caso no RAG** (#7)
4. **Separação por nível de risco da IA** (#11)

### Prioridade 2 (Alto - Operação Diária)
5. **Linha do tempo unificada** (#4)
6. **Estados operacionais padronizados com regras** (#3)
7. **Índice operacional de saúde** (#13)
8. **Pesquisa global** (#6)

### Prioridade 3 (Médio - Governança)
9. **Central de IA como governança** (#9)
10. **Separação das três bases do RAG** (#7)
11. **Integridade e versionamento documental** (#12)
12. **Ciclo de publicação do conhecimento** (#8)

### Prioridade 4 (Baixo - Melhoria Contínua)
13. **Benchmark jurídico próprio** (#10)
14. **Aprendizado curado com correções** (#14)
15. **Teste periódico de restauração** (#16)

### Prioridade 5 (Estratégico - Longo Prazo)
16. **Consolidação gradual sem refatoração brusca** (#15)

---

## Próximos Passos Imediatos

1. **Validar com stakeholders** esta consolidação
2. **Criar issues no tracker** para cada gap identificado
3. **Estimar esforço** por item (T-shirt sizing)
4. **Definir sprint 0** para itens de Prioridade 1
5. **Atualizar documentação** de arquitetura com decisões

---

## Anexos

### A. Matriz de Rastreabilidade

| Recomendação | Status | Arquivos Chave | Esforço Est. | Prioridade |
|--------------|--------|----------------|--------------|------------|
| #1 Dashboard | ⚠️ Parcial | `DashboardModern.tsx`, `dashboard.py` | M | P1 |
| #2 Próxima Ação | ❌ Não Implementado | `case.py`, `CasoDetalhe.tsx` | L | P1 |
| #3 Estados | ⚠️ Enums só | `case.py` | M | P2 |
| #4 Timeline | ⚠️ Base existe | `case.py`, `CaseMovimento` | L | P2 |
| #5 Prazos | ⚠️ Parcial | `deadline.py`, `deadlines.py` | M | P1 |
| #6 Pesquisa | ❌ Não Implementado | - | XL | P2 |
| #7 RAG Bases | ⚠️ Arquitetura ok | `rag.py`, `legal_doc.py` | M | P1 |
| #8 Curadoria | ❌ Não Implementado | `legal_doc.py` | M | P3 |
| #9 Governança IA | ⚠️ Parcial | `ai_log.py`, docs/ai/ | L | P3 |
| #10 Benchmark | ❌ Não Implementado | `eval/`, `qa/` | XL | P4 |
| #11 Risco IA | ⚠️ Documentado | `EJC_AI_HITL_POLICY.md` | M | P1 |
| #12 Documentos | ⚠️ Parcial | `document.py` | L | P3 |
| #13 Saúde Caso | ⚠️ Módulo existe | `modules/indice_risco/` | M | P2 |
| #14 Correções | ❌ Não Implementado | `ai_log.py` | M | P4 |
| #15 Implantação | ✅ Alinhado | Planos existentes | - | P5 |
| #16 Backup | ⚠️ Parcial | `RUNBOOK_BACKUP.md` | S | P4 |

Legenda: S=Pequeno (<1 dia), M=Médio (1-3 dias), L=Longo (3-10 dias), XL=Muito Longo (>10 dias)

### B. Glossário

- **EJC**: Escritório Jurídico Contemporâneo (sistema)
- **RAG**: Retrieval-Augmented Generation
- **HITL**: Human-In-The-Loop
- **RTO**: Recovery Time Objective
- **RPO**: Recovery Point Objective
- **WORM**: Write Once, Read Many

---

*Documento gerado em Julho/2026 para consolidação das recomendações do EJC.*
