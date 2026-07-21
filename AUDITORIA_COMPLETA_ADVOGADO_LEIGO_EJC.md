# AUDITORIA COMPLETA DO SISTEMA EJC
## Perspectiva: Advogado Leigo em Tecnologia (Operador do Sistema)

**Data da Auditoria:** 21 de Julho de 2026  
**Auditor:** Advogado(a) com 15+ anos de experiência jurídica, ZERO conhecimento técnico  
**Objetivo:** Avaliar se o sistema é usável, confiável e seguro para operação diária sem suporte técnico constante

---

## 📋 RESUMO EXECUTIVO (Veredito Franco)

### O que funciona BEM (e deve ser mantido)

| Ponto Forte | Por que importa para o advogado |
|---|---|
| **Central de Ajuda com 42 ferramentas explicadas** | Posso consultar como usar cada função sem pedir ajuda |
| **HITL (Revisão Humana Obrigatória) em toda IA** | A OAB exige revisão do advogado — o sistema me protege |
| **Verificador de citações anti-alucinação** | Não corro risco de citar jurisprudência falsa em petições |
| **Backup diário automático (30 dias)** | Meus dados estão protegidos contra perda |
| **Health check do sistema** | O sistema avisa se algo está quebrado antes de eu perder trabalho |
| **Degradação graciosa** | Se a IA cai, o sistema continua funcionando (busca textual) |
| **Trilha de auditoria imutável** | Sei quem fez o quê e quando — essencial para ética jurídica |
| **Empty states que ensinam** | Quando não há dados, o sistema explica como criar |

### O que QUEBRA minha operação (Crítico — P0)

| Problema | Impacto no meu trabalho | Status |
|---|---|---|
| **1. Crash ao gerar análise de IA sem provedor configurado** | Clico em "Gerar análise completa" → tela quebra com erro em inglês ("Objects are not valid as a React child") → PERCO O ACESSO À TELA | ⚠️ NÃO RESOLVIDO |
| **2. Erros de IA em "dialeto técnico"** | Vejo mensagens como ".env", "GROQ_API_KEY não configurada", "Ollama indisponível: [Errno -2]" — NÃO ENTENDO NADA | ⚠️ NÃO RESOLVIDO |
| **3. Porta de entrada bloqueada** | Sem autocadastro, sem indicação de quem me dá acesso, recuperação de senha depende de e-mail que nunca chega (SMTP desligado) | ⚠️ PARCIALMENTE RESOLVIDO |
| **4. Dois onboardings sobrepostos** | Card "Comece por aqui" + popover "Primeiros passos" abrem juntos, conteúdos diferentes, popover cobre botões de ação | ⚠️ NÃO RESOLVIDO |
| **5. Rascunho de peças "some"** | Salvo peça como rascunho → vou em "Peças" → mostra "0 peças" → NÃO ACHEI MEU TRABALHO | 🔴 BUG ATIVO |
| **6. Upload rejeita .doc e .txt sem explicar** | Tento subir Word antigo (.doc) ou texto (.txt) → "extensão não permitida" → não diz quais formatos servem | 🔴 BUG ATIVO |
| **7. Data-input em formato americano (mm/dd/yyyy)** | Digito 25/07/2026 → sistema não entende → preciso descobrir que é mês/dia/ano | 🔴 BUG ATIVO |

### O que me CONFUNDE (Alto — P1)

| Problema | Por que é confuso para mim |
|---|---|
| **Jargão técnico visível** | "RAG", "HITL", "Guardrails", "GED", "Data Room", "Kanban", "SLA", "prompt injection" — parecem outra língua |
| **Múltiplos nomes para a mesma coisa** | "Análise IA", "IA do caso", "Análise Completa", "Entrevista inteligente", "Raio-X" — são 5 nomes para "pedir análise à IA" |
| **Hub de ramo inalcançável** | Tela "Áreas de Atuação" só tem "Ver casos" e "Importar" — NÃO TEM BOTÃO para abrir o hub do ramo onde estão as calculadoras |
| **Tela do caso sobrecarregada** | 6 abas + 5 sub-abas + 13 botões de ação na mesma faixa — não sei qual usar primeiro |
| **"Novo prazo" sem vínculo ao caso** | Crio prazo na agenda → não vinculo ao processo → depois não acho qual caso esse prazo pertence |
| **Anexar documento "teleporta" para GED** | Clico em "Anexar documento ao caso" → sou levado para outra tela (/documentos) — perdi o contexto |
| **Placeholder errado no ramo Trabalhista** | A análise pede para colar "texto do contrato bancário" — estou no trabalhista, não no bancário! |
| **Saudação genérica** | "Bom trabalho, Dr." — não sabe meu nome e assume gênero |

### O que é REDUNDANTE (Médio — P2)

| Redundância | Quantas vezes aparece | Deveria ser |
|---|---|---|
| Jornada do caso | 4 caminhos diferentes | 1 caminho claro |
| "Raio-X do processo" vs "Analisar processo externo" vs "Novo caso por documento" | 3 nomes | 1 nome consistente |
| Wiki + Memória Institucional + Biblioteca Jurídica | 3 "acervos" | 1 acervo unificado ou diferenciação clara |
| Honorários | 4 routers (fees.py, honorarios_calc.py, honorarios_oab.py, exito_rateio.py) | 1 módulo consolidado |
| Dossiê estratégico | 3 superfícies concorrentes | 1 superfície |
| Análise estratégica | 4 endpoints concorrentes | 1 endpoint |
| Prompts de IA | ~20 lugares com regras OAB reescritas | 1 fonte central |

---

## 🔍 ANÁLISE PONTO A PONTO

### 1. PRIMEIRO ACESSO E AUTENTICAÇÃO

#### O que encontrei:
- **Tela de login limpa**, mas sem instrução de "como obtenho acesso?"
- Campo "Esqueci minha senha" → preencho → mensagem "Se o e-mail existir, enviaremos instruções"
- **Nunca recebo e-mail** (SMTP desligado por padrão)
- Sem fallback: "Procure o administrador do escritório"

#### Meu diagnóstico de leigo:
> "Parece que o sistema foi feito para quem JÁ TEM acesso. Se sou novo contratado ou estagiário, não sei a quem pedir. E se esqueci a senha, estou travado para sempre."

#### Sugestão:
- Adicionar na tela de login: "Primeiro acesso? Contate o administrador: [email/telefone do responsável]"
- Na recuperação de senha, se SMTP desligado: mostrar "Recuperação por e-mail indisponível. Procure o administrador para reset manual."

---

### 2. ONBOARDING E PRIMEIROS PASSOS

#### O que encontrei:
- **DOIS guias de primeiros passos**:
  1. Card no dashboard: "Comece por aqui (3 passos)"
  2. Popover flutuante: "Primeiros passos no EJC (4 tarefas)"
- O popover **cobre botões de ação** (comprovado: cobriu "Anexar documento ao caso")
- Conteúdos similares mas não idênticos — não sei qual seguir

#### Meu diagnóstico de leigo:
> "O guia que deveria me ajudar está **impedindo eu dar o primeiro passo**. É como se o manual de instruções cobrisse o botão de ligar."

#### Sugestão:
- Unificar em UM único onboarding
- Travar popover para não cobrir elementos clicáveis
- Manter sessão após troca de senha obrigatória (não me jogar de volta ao login)

---

### 3. INTELIGÊNCIA ARTIFICIAL — FUNCIONALIDADE CORE

#### O que funciona bem:
- ✅ HITL obrigatório (revisão humana antes de usar qualquer saída de IA)
- ✅ Selo "MINUTA — REVISÃO OBRIGATÓRIA" em tudo que é gerado por IA
- ✅ Verificador de citações confere súmulas e artigos contra base oficial
- ✅ Detecção de promessa de resultado (vedação OAB)
- ✅ AILog registra todas as interações para auditoria

#### O que QUEBRA:

**Bug Crítico #1: Análise de caso sem IA derruba a tela**
```
Cenário: Cliquei em "Gerar análise completa" no caso #123
Resultado: Tela fica branca, erro em inglês:
"Objects are not valid as a React child (found: object with keys {nome, endpoint})"
Impacto: Perdi acesso à tela do caso, precisei recarregar (F5)
```

**Bug Crítico #2: Erros técnicos incompreensíveis**
```
Mensagens que vi:
- "Falha na IA. A IA pode estar desabilitada (.env)"
- "Todos os provedores falharam para task=estrategia… Ollama indisponível: [Errno -2] Name or service not known"
- "GROQ_API_KEY não configurada para transcrição"
- "configure Ollama"

Minha tradução mental: "O sistema está quebrado e eu não sei consertar nem a quem pedir ajuda"
```

#### Meu diagnóstico de leigo:
> "A IA é o grande diferencial do sistema, mas quando não está configurada, **o sistema não me avisa de forma clara**. Os botões de IA estão ativos e convidativos, mas ao clicar, recebo erros técnicos. É como ter um carro esportivo sem gasolina — o painel não avisa, só descobro quando tento acelerar."

#### Sugestões:
1. **Banner global** quando IA não estiver configurada: "⚠️ Inteligência Artificial não ativada nesta instalação. Fale com o administrador."
2. **Botões de IA desabilitados** com tooltip explicativo quando IA indisponível
3. **Traduzir TODOS os erros** para linguagem leiga:
   - ❌ "GROQ_API_KEY não configurada"
   - ✅ "Serviço de IA externa não configurado. Contate o administrador."
4. **Corrigir o crash** da análise de caso — renderizar estado degradado amigável

---

### 4. GESTÃO DE CASOS — O CORAÇÃO DO SISTEMA

#### O que funciona bem:
- ✅ Cadastro guiado com deduplicação por CPF/CNPJ
- ✅ Empty state que ensina: "Os casos são o centro do EJC…"
- ✅ Jornada do caso com "pendência que trava esta etapa → próxima ação"
- ✅ 404 exemplar (página não encontrada é clara e útil)

#### O que me confunde:

**Problema #1: Excesso de botões de ação**
```
Na tela do caso, vejo 13 botões na mesma faixa:
[Resumo] [Partes] [Documentos] [Andamentos] [Prazos] [Honorários]
[Ações: ▼] [Análise IA] [IA do caso] [Análise Completa] [Arquivar] [Excluir] [Honorários (OAB)]

Não sei:
- Qual é a ação principal?
- Por que "Excluir" está ao lado de ações rotineiras?
- Preciso mesmo de 3 tipos de "Análise"?
```

**Problema #2: Abas duplicadas**
```
Aba "Resumo" tem 5 sub-abas, incluindo "Resumo dentro de Resumo"
Parece que há conteúdo repetido em lugares diferentes
```

**Problema #3: Anexo de documento "teleporta"**
```
Estou na tela do caso → clico "Anexar documento" → 
Sou levado para /documentos?caso=123 (outra tela!)
Perdi o contexto, não sei se voltei pro caso certo
```

#### Meu diagnóstico de leigo:
> "A tela do caso parece o **painel de controle de uma usina nuclear** — tantos botões que tenho medo de clicar no errado. Para um advogado que quer apenas anexar um documento ou ver prazos, é exaustivo."

#### Sugestões:
1. **Hierarquizar botões**: ações frequentes visíveis, destrutivas em menu "⋯", avançadas em dropdown
2. **Consolidar análises de IA**: 1 único botão "Análise Jurídica (IA)" que abre modal com opções
3. **Anexo inline**: permitir anexar documento sem sair da tela do caso
4. **Reduzir abas**: fundir sub-abas duplicadas

---

### 5. PEÇAS JURÍDICAS — FEATURE CRÍTICA

#### O que funciona bem:
- ✅ Gate por Ficha de Triagem (obriga informações mínimas antes de gerar peça)
- ✅ Fluxo de aprovação HITL claro
- ✅ Minuta com aviso de revisão obrigatória

#### O que QUEBRA:

**Bug #1: Rascunho "invisível"**
```
Cenário: 
1. Preenchi ficha de triagem no ramo Trabalhista
2. Cliquei "Salvar rascunho"
3. Mensagem: "Salvo em Peças (rascunho)"
4. Fui em módulo "Peças" → mostra "0 peças"

Onde está meu rascunho? Sumiu?
```

**Bug #2: Upload rejeita formatos comuns**
```
Tentei subir:
- arquivo.doc (Word antigo, muito comum em escritórios)
- arquivo.txt (texto simples)

Resultado: "1 arquivo(s) ignorado(s): extensão não permitida"
Não diz:
- Qual arquivo foi rejeitado
- Quais formatos SÃO permitidos
```

**Problema #3: Pré-preenchimento por IA falha silenciosamente**
```
Ficha de triagem tem botão "Pré-preencher com IA"
Sem IA configurada: botão funciona? falha? não sei — não há feedback
```

#### Meu diagnóstico de leigo:
> "Peças jurídicas são o produto final do meu trabalho. Se o sistema **perde rascunhos** ou **rejeita arquivos comuns** sem explicar, perco confiança nele. É como um cartório que extravia processos."

#### Sugestões:
1. **Investigar bug do rascunho**: ou aparece em Peças, ou explicar ONDE está
2. **Aceitar .doc e .txt** (com validação de conteúdo) OU listar formatos aceitos claramente
3. **Feedback claro** quando IA indisponível para pré-preenchimento

---

### 6. AGENDA E PRAZOS — GERENCIAMENTO DE TEMPO

#### O que funciona bem:
- ✅ Visualização clara de prazos por prioridade
- ✅ Lembretes automáticos de audiência (3/1/0 dias)
- ✅ Kanban de atividades (para quem gosta de visual)

#### O que me confunde:

**Problema #1: Novo prazo sem vínculo**
```
Criei "Novo prazo" na agenda:
- Título: "Contestar ação 12345-67"
- Data: 25/07/2026
- Prioridade: Alta

Mas NÃO PERGUNTOU qual caso/processo é este prazo.
Depois, não consigo achar qual caso este prazo pertence.
```

**Problema #2: Formato de data americano**
```
Campo de data mostra placeholder: mm/dd/yyyy
Digito 25/07/2026 → sistema não aceita ou interpreta errado
Preciso digitar 07/25/2026 (mês primeiro) — contraintuitivo!
```

**Problema #3: Validação longe do campo**
```
Erro "Informe o título do caso" aparece como toast no canto inferior
Não destaca o campo em vermelho
Preciso caçar qual campo está faltando
```

#### Meu diagnóstico de leigo:
> "Prazo processual SEM VÍNCULO ao processo é como endereço sem CEP — posso até ter a informação, mas não acho quando preciso. E o formato de data americano me faz errar justo no que mais importa: o vencimento!"

#### Sugestões:
1. **Obrigar vínculo caso/processo** ao criar prazo (ou pelo menos sugerir fortemente)
2. **Forçar formato dd/mm/aaaa** em todos os campos de data
3. **Validação inline**: erro aparece abaixo do campo, em vermelho

---

### 7. DOCUMENTOS E GED — GESTÃO DOCUMENTAL

#### O que funciona bem:
- ✅ Upload com validação de magic bytes (não aceita .pdf falso)
- ✅ Deduplicação por hash SHA256
- ✅ Soft delete (não apaga definitivamente sem querer)

#### O que me confunde:

**Problema #1: Upload multi-arquivo cria duplicatas e órfãos**
```
Cenário relatado no código:
1. Importei 3 PDFs para criar novo caso
2. Sistema processou via Entrada Universal
3. Resultado:
   - 1º arquivo: gravado 2x (uma cópia órfã + uma anexada)
   - 2º e 3º arquivos: ficaram órfãos, sem vínculo com caso
   
Ninguém me avisou disso!
```

**Problema #2: Extensões rejeitadas sem explicação**
(já mencionado em Peças, mas afeta GED geral)

#### Meu diagnóstico de leigo:
> "Se o sistema **duplica documentos** ou **perde vínculos** silenciosamente, não posso confiar nele para guarda de provas e peças originais."

#### Sugestões:
1. **Corrigir fluxo multi-arquivo**: usar vínculo de lote em vez de re-upload
2. **Lista clara de formatos aceitos** no modal de upload
3. **Relatório pós-upload**: "3 arquivos processados: 3 vinculados, 0 órfãos"

---

### 8. NAVEGAÇÃO E ARQUITETURA DE INFORMAÇÃO

#### O que funciona bem:
- ✅ Sidebar com partição "Essencial" (7 itens) vs "Mais / Avançado"
- ✅ Grupos por intenção ("Trabalhar um caso", "Pesquisar & IA", etc.)
- ✅ 25 redirects de rotas legadas (não quebra links antigos)
- ✅ Busca global (Ctrl+K) quando funciona

#### O que me confunde:

**Problema #1: Hub de ramo inalcançável**
```
Fui em "Áreas de Atuação" (/ramos)
Vi cards de todos os ramos (Bancário, Trabalhista, etc.)
Cliquei em "Ver casos" → lista de casos
Cliquei em "Importar" → importação

ONDE ESTÁ O HUB DO RAMO???
(/ramos/trabalhista, onde estão as 56 calculadoras e ferramentas)

Descobri digitando a URL manualmente. Um leigo nunca acharia.
```

**Problema #2: Excesso de portas de entrada para IA**
```
Contei pelo menos 5 nomes para "pedir análise à IA":
1. "Análise IA" (menu lateral)
2. "IA do caso" (tela do caso)
3. "Análise Completa (IA)" (botão na tela do caso)
4. "Entrevista inteligente" (módulo próprio)
5. "Raio-X do processo" (módulo próprio)

São 5 portas para o mesmo cômodo!
```

**Problema #3: Toggle "MAIS / AVANÇADO" engana**
```
Sidebar tem seção "MAIS / AVANÇADO" que colapsa
Item que eu queria estava lá, colapsei sem querer → item "sumiu"
Não percebi que era um toggle
```

**Problema #4: Ctrl+K fecha modais**
```
Estava preenchendo formulário → apertei Ctrl+K sem querer
Busca global abriu POR CIMA do modal
Apertei Esc → fechou OS DOIS
Perdi o que estava digitando
```

#### Meu diagnóstico de leigo:
> "A navegação parece um **labirinto com múltiplas entradas para o mesmo lugar**. Como usuário, quero UM caminho claro para cada função, não cinco atalhos diferentes."

#### Sugestões:
1. **Botão explícito "Abrir Hub do Ramo"** em "Áreas de Atuação" e na tela do caso
2. **Consolidar portas de IA**: 1 botão por contexto, com opções internas
3. **Toggle com indicador visual** (seta, ícone) mostrando estado expandido/recolhido
4. **Ctrl+K não abrir sobre modais** ou ter confirmação

---

### 9. LINGUAGEM E JARGÃO TÉCNICO

#### Jargões que encontrei (e NÃO entendi sem pesquisar):

| Termo | Onde aparece | Tradução necessária |
|---|---|---|
| **RAG** | "Busca unificada em RAG", "Curadoria RAG" | "Base de conhecimento jurídico" |
| **HITL** | Badge "Validar HITL X/100", aba "Por status (HITL)" | "Revisão do advogado" |
| **Guardrails** | Descrição de Governança da IA | "Barreiras de segurança" |
| **Prompts sistêmicos** | Módulo de IA | "Instruções da IA" |
| **Scanner Anti-Sabotagem** | Segurança de IA | "Detector de manipulação" |
| **GED** | Menu/telas | "Gestão de Documentos" (ou só "Documentos") |
| **Data Room** | Módulo próprio | "Sala de Due Diligence" |
| **Kanban** | Central de Atividades | "Quadro de Tarefas" |
| **SLA** | Relatórios | "Prazo de Atendimento" |
| **DataJud** | Integrações | "Base de Processos do CNJ" |
| **Embeddings** | Configurações | "Indexação para busca" |
| **Provider** | Configurações de IA | "Serviço de IA" |
| **Token** | Configurações | "Unidade de processamento" |
| **Chunk** | RAG | "Trecho de documento" |
| **Fallback** | Logs/mensagens | "Plano B" |
| **Rollback** | Runbooks | "Reverter alteração" |
| **Soak test** | Documentação | "Teste prolongado" |
| **Feature-flag** | Configurações | "Interruptor de funcionalidade" |
| **IDOR** | Auditorias (vazou para docs?) | "Falha de acesso indireto" |

#### Meu diagnóstico de leigo:
> "Parece que os desenvolvedores **esqueceram que advogados não falam 'tiopês'**. Cada termo técnico é uma barreira. Alguns até entendi depois de pesquisar, mas **não deveria precisar de glossário para usar o sistema**."

#### Sugestões:
1. **Varredura completa de jargão** em toda UI
2. **Glossário integrado** no Guia do Sistema (já existe conteúdo, falta organizar)
3. **Tooltips explicativos** em termos inevitáveis (ex.: passar mouse em "HITL" mostra "Revisão humana obrigatória")

---

### 10. CONFIGURAÇÕES E AMBIENTE

#### O que me assusta:

**Problema #1: Arquivo .env.example com 577 linhas**
```
Abri o arquivo de exemplo de configuração:
- 577 linhas
- 164 variáveis de ambiente
- Muitas com nomes técnicos: PII_ENCRYPTION_KEY, AI_EXTERNAL_PROVIDERS_ALLOWED, RRF_MIN_SIM...

Como um leigo instala isso sozinho? IMPOSSÍVEL.
```

**Problema #2: Instalação requer Docker + VPS + SSH**
```
Para rodar o sistema localmente, precisei:
1. Instalar Docker
2. Configurar Docker Compose
3. Acessar VPS por SSH
4. Editar arquivos .env
5. Rodar migrations Alembic

Isso é trabalho de TI, não de advogado!
```

**Problema #3: SMTP desligado por padrão**
```
Recuperação de senha DEPENDE de e-mail
SMTP vem desligado na instalação padrão
Resultado: recuperação de senha NÃO FUNCIONA sem intervenção técnica
```

**Problema #4: IA desligada por falta de configuração**
```
Botões de IA estão ativos e visíveis
Mas sem GROQ_API_KEY ou Anthropic configurada, a IA não funciona
Não há aviso prévio — só descubro ao clicar e receber erro
```

#### Meu diagnóstico de leigo:
> "O sistema foi feito **por técnicos para técnicos**, não para advogados. A instalação é complexa demais para o público-alvo declarado. O produto deveria ser entregue **já hospedado e configurado**, com painel administrativo simplificado para o advogado-administrador."

#### Sugestões:
1. **Wizard de primeira configuração** no próprio app (não via .env):
   - Passo 1: Dados do escritório
   - Passo 2: Configurar e-mail (teste de envio na hora)
   - Passo 3: Configurar IA (escolher provider, colar chave, testar)
   - Passo 4: Criar primeiro usuário admin
2. **Produto entregue hospedado** (como já é o caso: ejc.depaulateixeira.adv.br)
3. **Painel do admin leigo**: ativar/desativar funcionalidades com toggles, sem tocar em código
4. **Detectar configurações ausentes** e avisar nos módulos afetados

---

### 11. SEGURANÇA E LGPD — VISÃO DO LEIGO

#### O que me tranquiliza:
- ✅ 2FA disponível (embora não obrigatório por padrão)
- ✅ Senhas com força validada
- ✅ Trilha de auditoria de quem acessou o quê
- ✅ PII (CPF/CNPJ) criptografada no banco
- ✅ Backup diário automático
- ✅ Rate limit previne abuso

#### O que me preocupa (quando entendi):

**Problema #1: Segregação de clientes contornável**
```
Li na auditoria: "Um advogado sem relação com o cliente X pode criar acesso de portal 
com e-mail e senha que ele controla, loga como cliente_externo e lê casos de outra carteira"

Isso significa que sigilo entre carteiras pode ser violado?
```

**Problema #2: Procurações vazam PII**
```
"POST /procuracoes/{id}/minuta monta qualificação completa (nome, CPF, endereço) 
sem checar se o advogado tem vínculo com o cliente"

Qualquer interno pode reconstruir dados de todos os clientes?
```

**Problema #3: Agenda pessoal sem dono**
```
"Evento sem case_id não tem checagem de dono: qualquer interno edita/reagenda 
evento alheio"

Meus compromissos pessoais podem ser modificados por outros?
```

#### Meu diagnóstico de leigo:
> "Segurança é como cofre: só percebo que está aberto quando algo some. As brechas que li nas auditorias são **técnicas demais para eu detectar**, mas me preocupam porque envolvem sigilo de cliente — dever ético fundamental."

#### Sugestões:
1. **Blindar segregação de clientes** em TODOS os endpoints (não só nos principais)
2. **Auditar regularmente** acessos cruzados entre carteiras
3. **Relatório de acessos** por cliente: "Quem viu este caso nos últimos 30 dias?"
4. **Notificação de acesso suspeito**: "Cliente X foi acessado por advogado Y (sem vínculo)"

---

### 12. RELATÓRIOS E PDFs — PRODUTO FINAL

#### O que funciona bem:
- ✅ Design system consistente (tema dourado/Visual Law)
- ✅ Todos os PDFs usam mesmo tema unificado
- ✅ QR Code para verificação de autenticidade
- ✅ Modo claro forçado (impressão econômica)

#### O que me confunde:

**Problema #1: Múltiplos geradores para o mesmo tipo**
```
Encontrei:
- Dossiê Estratégico (3 superfícies diferentes)
- Análise Bancária (múltiplos routers)
- Honorários (4 módulos)

Qual uso? São iguais? Um é melhor?
```

**Problema #2: Retenção de PDFs de terceiros**
```
Li: "PDFs gerados com dados de terceiros têm TTL de 1h (varredura remove)"

Meus relatórios somem depois de 1 hora?
Preciso baixar tudo imediatamente?
```

#### Meu diagnóstico de leigo:
> "Os PDFs são bonitos e profissionais, mas **não sei qual gerador usar** para cada situação. E a retenção de 1h me pega de surpresa — poderia perder trabalho se não baixar na hora."

#### Sugestões:
1. **Consolidar geradores**: 1 tipo de relatório = 1 gerador
2. **Aviso claro de retenção**: "Este PDF será apagado em 1h. Baixe agora?"
3. **Opção de salvar permanentemente** para relatórios importantes

---

### 13. TESTES E CONFIABILIDADE

#### O que descobri nas auditorias:

**Backend: 2.751 testes passando (0 falhas atuais)**
- Bom! Mas li que houve 8 falhas recentes corrigidas

**Frontend: 128 testes passando**
- Também bom

**CI (Integração Contínua):**
- Runner self-hosted ficou offline durante merges críticos
- Bugs passaram sem detecção

#### Meu diagnóstico de leigo:
> "Não entendo de testes automatizados, mas **confio mais num sistema que testa a si mesmo**. Me preocupa saber que bugs críticos passaram porque o 'robô de teste' estava offline."

#### Sugestões:
1. **CI redundante**: se runner principal falha, usa fallback
2. **Relatório de saúde dos testes** visível no dashboard admin
3. **Bloquear deploy** se suite de testes não rodar

---

## 📊 MATRIZ DE PRIORIDADES (Visão do Leigo)

### P0 — Bloqueiam meu uso autônomo (FAZER AGORA)

| # | Problema | Esforço estimado | Impacto |
|---|---|---|---|
| 1 | Crash da análise IA sem provedor | Baixo | Alto — perde acesso à tela |
| 2 | Erros de IA em dialeto técnico | Baixo | Alto — não entendo o erro |
| 3 | Banner/estado "IA não ativada" | Baixo | Alto — expectativa vs realidade |
| 4 | Login/recuperação sem fallback | Médio | Alto — porta de entrada bloqueada |
| 5 | Onboarding duplo cobre botões | Baixo | Médio — impede primeiros passos |
| 6 | Rascunho de peças invisível | Médio | Alto — perde trabalho |
| 7 | Upload rejeita .doc/.txt sem explicar | Baixo | Médio — formato comum bloqueado |

### P1 — Reduzem drasticamente minha produtividade (FAZER DEPOIS)

| # | Problema | Esforço | Impacto |
|---|---|---|---|
| 8 | Varredura de jargão + glossário | Médio | Alto — barreira de linguagem |
| 9 | Link para hub do ramo visível | Baixo | Alto — feature premium inalcançável |
| 10 | Reorganizar tela do caso (hierarquia) | Médio | Médio — sobrecarga cognitiva |
| 11 | Datas dd/mm/aaaa forçadas | Baixo | Médio — erro em dato crítico |
| 12 | Vínculo caso↔prazo obrigatório | Baixo | Médio — prazo órfão |
| 13 | Anexo inline no caso | Médio | Médio — teleporte confuso |
| 14 | Placeholder "contrato bancário" no trabalhista | Baixo | Baixo — quebra confiança |

### P2 — Polimento e escala (FAZER DEPOIS)

| # | Problema | Esforço | Impacto |
|---|---|---|---|
| 15 | Modo demonstração com dados fictícios | Médio | Médio — aprendizado no vazio |
| 16 | Manual em PDF exportável | Baixo | Baixo — prefere papel |
| 17 | Consolidar generators de relatório | Alto | Médio — confusão de opções |
| 18 | Feature-flag por perfil/plano | Alto | Baixo — sobrecarga de módulos |
| 19 | Wizard de configuração inicial | Alto | Alto — autonomia do admin |

---

## 🎯 CONCLUSÃO FRANCA

### O EJC está pronto para um advogado leigo usar?

**Resposta curta: NÃO, não totalmente.**

**Resposta qualificada:**

O EJC está apto para uso por advogado leigo **DESDE QUE**:

1. ✅ **Haja um administrador técnico** (ou suporte) para:
   - Configurar SMTP e IA na instalação
   - Criar usuários iniciais
   - Resolver problemas de infraestrutura

2. ✅ **Haja 30 minutos de orientação inicial** para:
   - Mostrar o caminho até o hub do ramo
   - Explicar a hierarquia de botões na tela do caso
   - Demonstrar o fluxo correto de peças
   - Apresentar o glossário de jargões

3. ✅ **Sejam corrigidos os bugs críticos P0** listados acima

### Comparação com expectativas

| Expectativa do Leigo | Realidade do EJC | Gap |
|---|---|---|
| "Instalei, abri, usei" | "Instalei, travei na senha, SMTP não funciona" | 🔴 Alto |
| "Erros em português claro" | "Errors em inglês com jargão técnico" | 🔴 Alto |
| "Uma função = um nome" | "Uma função = cinco nomes" | 🟠 Médio |
| "Meu trabalho não se perde" | "Rascunho some, documento duplica" | 🔴 Alto |
| "Dados seguros" | "Brechas de segredo entre carteiras" | 🟠 Médio |
| "IA funciona ou avisa" | "IA falha com erro técnico" | 🔴 Alto |

### Veredito Final

> **O EJC é um Ferrari com manual em alemão e sem posto de gasolina na porta.**
>
> A engenharia é excelente (núcleo de IA maduro, segurança sólida, backups funcionais). Mas a **última milha** — tornar o sistema usável por um advogado sem suporte técnico — está incompleta.
>
> **Recomendação:** Antes de divulgar/vender para outros escritórios:
> 1. Corrigir todos os itens P0 (1-2 semanas de esforço)
> 2. Criar material de onboarding (vídeo de 15min + checklist impresso)
> 3. Oferecer **apenas como serviço hospedado** (não auto-instalável)
> 4. Ter canal de suporte rápido para primeiros 30 dias de cada cliente

---

## 📝 CHECKLIST DE SOBREVIVÊNCIA (Para o Advogado Leigo)

### Antes de começar a usar:

- [ ] Confirmar com administrador: SMTP configurado e testado?
- [ ] Confirmar: IA configurada (Groq ou Anthropic)?
- [ ] Receber credenciais de acesso + senha temporária
- [ ] Anotar contato do administrador (suporte)

### Primeiros 30 minutos:

- [ ] Fazer login (funcionou? se não, acionar admin)
- [ ] Trocar senha (obrigatório)
- [ ] Completar onboarding (ignorar popover se cobrir botões)
- [ ] Explorar Central de Ajuda (42 ferramentas explicadas)
- [ ] Criar caso de teste (cliente fictício)
- [ ] Testar upload de documento (PDF, DOCX)
- [ ] Testar geração de peça (ramo conhecido)
- [ ] Testar análise de IA (se configurada)

### Primeiro caso real:

- [ ] Cadastrar cliente (dedup por CPF/CNPJ ativa)
- [ ] Criar caso com título descritivo
- [ ] Anexar documentos iniciais (inline, se possível)
- [ ] Vincular partes (autor/réu)
- [ ] Gerar minuta de peça (IA ou manual)
- [ ] Revisar minuta (HITL obrigatório!)
- [ ] Protocolar (externo ao sistema)
- [ ] Registrar protocolo no caso
- [ ] Criar prazos vinculados ao caso

### Rotina diária:

- [ ] Checar Dashboard (prazos do dia)
- [ ] Verificar notificações (sino no topo)
- [ ] Processar fila de peças para revisão (HITL)
- [ ] Atualizar andamentos de casos ativos
- [ ] Registrar novas atividades

### Segurança:

- [ ] Ativar 2FA (recomendado)
- [ ] Nunca compartilhar credenciais
- [ ] Logout sempre ao terminar (especialmente em computador compartilhado)
- [ ] Reportar acessos suspeitos ao administrador

---

**Documento elaborado para fins de auditoria interna.**  
**Versão:** 1.0  
**Próxima revisão:** Após correção dos itens P0
