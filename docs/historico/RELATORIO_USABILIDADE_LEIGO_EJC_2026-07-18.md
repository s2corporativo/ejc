# Relatório de Usabilidade — EJC sob a ótica de um advogado leigo em tecnologia

_Data: 2026-07-18. Persona: advogado(a) experiente, sem conhecimento técnico, usando o EJC pela primeira vez, sem manual e sem treinamento. Método: (1) mapeamento factual da superfície do sistema (rotas, menus, módulos, mensagens, papéis, docs — com referência `arquivo:linha`); (2) execução real da stack (Postgres 16 + pgvector, 096 migrations, seed, backend uvicorn, frontend Vite) e navegação completa no navegador (Chromium/Playwright), incluindo viewport mobile 390px, cenário sem chave de IA e sem SMTP — exatamente o "instalei e abri"._

---

## 1. Veredito executivo

O EJC tem **fundações de usabilidade acima da média** para sistema interno: Central de Ajuda com as 42 ferramentas explicadas em linguagem leiga (`frontend/src/content/guiaSistema.ts`, consumido por `/ajuda`), botão "?" de ajuda contextual por módulo, onboarding de 4 tarefas, empty states que ensinam ("Os casos são o centro do EJC…"), Jornada do caso com "pendência que trava esta etapa → próxima ação", cadastro guiado com dedup por CPF/CNPJ, disclaimers éticos de IA em toda parte e 404/login bem resolvidos.

Porém, **para um leigo usar sozinho, hoje, ele quebra em três pontos duros**:

1. **A porta de entrada**: não há autocadastro, a tela de login não diz a quem pedir acesso, e a recuperação de senha depende de SMTP que a instalação padrão tem desligado — o e-mail nunca chega e o usuário não tem como saber.
2. **BUG crítico**: "Gerar análise completa" na tela do caso, sem provedor de IA configurado, **derruba a tela com erro React cru em inglês** ("Objects are not valid as a React child…").
3. **Erros de IA em dialeto de infraestrutura**: ".env", "GROQ_API_KEY não configurada", "Ollama indisponível: [Errno -2] Name or service not known", "configure Ollama" — incompreensíveis para advogado.

Além disso, a **riqueza do sistema cobra um imposto cognitivo alto**: ~60 rotas, ~45 módulos no registry, 14 ramos com 56 ferramentas, 152 routers / ~751 endpoints, e jargões (RAG, HITL, guardrails, prompt injection, GED, Kanban, SLA) visíveis em telas centrais. O "Modo Essencial" da sidebar (7 itens) mitiga, mas não resolve.

**Conclusão**: o EJC está apto para advogado leigo **acompanhado de um administrador técnico e após meia hora de orientação**; não está apto para uso 100% autônomo do primeiro acesso. A lista priorizada da §10 fecha essa lacuna.

---

## 2. Jornada do primeiro acesso (a porta de entrada)

| # | Fricção | Onde | Por que é problema |
|---|---|---|---|
| 2.1 | Sem autocadastro e sem indicação de a quem pedir acesso | `/login` (`LoginModern`) | "Use suas credenciais internas" não diz quem as fornece. O admin inicial só nasce via seed/`.env` (`ADMIN_PASSWORD`) ou SQL manual (`README.md:86-91`) — impossível para leigo. |
| 2.2 | "Esqueci minha senha" depende de SMTP desligado por padrão | `/recuperar-senha`; diagnóstico mostra SMTP "Desligado" | A resposta neutra "Se o e-mail existir, enviaremos as instruções" (`auth.py:487`) vira beco sem saída: o e-mail nunca chega e não há fallback ("procure o administrador"). |
| 2.3 | Troca de senha obrigatória derruba de volta ao login | `/trocar-senha` → `/login?motivo=senha-alterada` | Redigitar credenciais logo após criá-las é atrito no primeiro minuto. Manter a sessão após a troca. |
| 2.4 | Dois onboardings sobrepostos | Dashboard `/` | Card "Comece por aqui (3 passos)" + popover "Primeiros passos no EJC (4 tarefas)" (`OnboardingTour.tsx`) abrem juntos, com conteúdos parecidos mas diferentes; o popover cobre o card. O leigo não sabe qual seguir. |
| 2.5 | O popover de onboarding **cobre botões de ação** | Tela do caso | Documentado em screenshot: cobriu "Anexar documento ao caso", tornando-o inclicável. O guia de primeiros passos impede o primeiro passo. |
| 2.6 | Saudação "Bom trabalho, Dr." sem nome e assumindo gênero | Dashboard | Cosmético, mas é a primeira frase que o sistema diz ao usuário. |

## 3. Fricções críticas de funcionalidade (P0)

| # | Fricção | Onde | Detalhe |
|---|---|---|---|
| 3.1 | **Crash da Análise IA do caso** | `/casos/:id` → "Gerar análise completa" | Sem IA, backend responde 200 com payload degradado e o frontend quebra: "Erro ao carregar este módulo. Objects are not valid as a React child (found: object with keys {nome, endpoint})". Erro é logado em `/api/observabilidade/frontend-error` (boa engenharia), mas o advogado perde a tela e não entende nada. |
| 3.2 | Erros de IA técnicos ao usuário | `/ia` "Sugerir teses"; `AssistenteIA.tsx:92`; `ai_gateway.py:466-511` | "Falha na IA. A IA pode estar desabilitada (.env)", "Todos os provedores falharam para task=estrategia… Ollama indisponível", "GROQ_API_KEY não configurada para transcrição", "configure Ollama". Nenhuma tela avisa antecipadamente que a IA está desligada — os botões de IA seguem ativos e convidativos no sistema todo. |
| 3.3 | "Salvo em Peças (rascunho)" que não aparece em Peças | `/ramos/trabalhista` (demonstrativo de verbas) → `/pecas` | A página Peças mostra "0 peças". Ou o rascunho se perde, ou fica onde o usuário não encontra — nos dois casos o leigo conclui que "sumiu". Investigar (possível filtro/status invisível). |
| 3.4 | Peças gateada por Ficha de triagem obrigatória (~12 campos) cujo "Pré-preencher com IA" falha | `/pecas` | O gate é explicado (bom), mas mata o passo 3 do próprio onboarding ("Gerar uma peça") no primeiro uso sem IA. |
| 3.5 | Upload rejeita `.txt` e `.doc` (Word antigo, comum em escritórios) com mensagem seca | Modal de envio em `/documentos` | "1 arquivo(s) ignorado(s): extensão não permitida" — não diz qual arquivo nem quais formatos servem (aceitos: pdf, docx, jpg, png, xlsx, xml). |
| 3.6 | "Novo prazo" da agenda não vincula a caso/processo | `/atividades` → +Novo prazo | Só título/prioridade/data/responsável/descrição. Prazo órfão de processo contraria o modelo mental do advogado (a Jornada do caso pede prazo com vínculo). |
| 3.7 | Date-inputs em `mm/dd/yyyy` | "Novo prazo" e demais formulários de data | Formato americano na instalação padrão; advogado digita 25/07 e se confunde. Forçar `pt-BR`/máscara dd/mm/aaaa. |
| 3.8 | Validação longe do campo | Modal "Novo caso" | Toast "Informe o título do caso." no canto inferior, sem destacar o campo em vermelho. |
| 3.9 | "Anexar documento ao caso" teleporta para o GED | Aba Documentos do caso → `/documentos?caso=…` | Mudança de contexto silenciosa: o usuário esperava anexar ali e é levado a outro módulo com filtro aplicado ("onde estou?"). Anexar inline no caso. |

## 4. Linguagem e jargão

Rótulos e textos visíveis que um advogado leigo não decodifica sem tradução:

- **"RAG"** — "Busca unificada em RAG, teses, jurisprudência e memória" (`moduleRegistry.tsx:552`) e "Curadoria RAG".
- **"HITL"** — badge "Validar HITL X/100" (`Pecas.tsx:151`), aba "Por status (HITL)" e "aproveitamento (HITL)" (`DashboardIA.tsx:36,44`), aba "Histórico / HITL". O conceito é ótimo; a sigla, não. Trocar por "Revisão do advogado".
- **"Guardrails" e "prompts sistêmicos"** — descrição de Governança da IA (`moduleRegistry.tsx:736`).
- **"Scanner Anti-Sabotagem (prompt injection)"**, **"GED"**, **"Data Room"**, **"Kanban"**, **"SLAs"**, **"DataJud"** (sem explicar que é o CNJ).
- Metáforas sem legenda: **"Raio-X do Processo"**, **"Sala de Guerra"**, **"Núcleo Jurídico"** — aceitáveis como marca, desde que o subtítulo diga o que fazem (hoje nem sempre diz).
- **Texto reciclado de outro ramo**: no hub Trabalhalhista, o placeholder pede "…cole aqui o texto do **contrato bancário**" (copiado do módulo bancário) — mina a confiança na análise.
- Painel de ajuda contextual com slug técnico no título: "Ajuda — inteligencia" em vez de "Ajuda — Inteligência Jurídica".

## 5. Navegação, rotas e o que SOBRA

- **O hub de ramo é quase inalcançável** (fricção grave): a página "Áreas de Atuação" (`/ramos`) só oferece "Ver casos" e "Importar" por card — **não há botão para abrir o hub do ramo** (`/ramos/trabalhista` etc.), onde estão as melhores ferramentas do produto (56 calculadoras com base legal, guias, súmulas). Só se chega adivinhando a URL.
- **Tela do caso sobrecarregada**: 6 abas + 5 sub-abas ("Resumo dentro de Resumo") + **13 botões de ação na mesma faixa**, sem hierarquia — "Excluir" ao lado de "Arquivar" e "Honorários (OAB)". Separar: ações frequentes visíveis, destrutivas em menu "⋯", e consolidar.
- **Excesso de portas de entrada para IA**: "Análise IA", "IA do caso", "Análise Completa (IA)", "Entrevista inteligente", "Raio-X", "Gerar com IA", "Assistente Jurídico", "Analisar e Produzir" — ao menos 5 nomes para "pedir análise à IA". Consolidar num único ponto por contexto.
- **Redundâncias**: Jornada do caso acessível por 4 caminhos; "Raio-X do processo" vs "Analisar processo externo" vs "Novo caso por documento" (três nomes para importar/analisar documento); Wiki + Memória Institucional + Biblioteca Jurídica (três "acervos" distintos).
- **Módulos provavelmente sem uso num escritório pequeno**: Funil de Leads, Jurimetria, Victory Vault, Prompts Operacionais, Mapa de Módulos, e boa parte dos 18 itens de "Mais Ferramentas". Candidatos a feature-flag por perfil/plano — o superadmin liga sob demanda.
- **Detalhes de navegação**: o rótulo "MAIS / AVANÇADO" da sidebar é um toggle que colapsa sem o usuário perceber (o item desejado "some"); Ctrl+K abre a busca por cima de modais abertos e o Esc fecha os dois, perdendo o que foi digitado; sino de notificações com área de clique instável.
- **O que está bom e deve ficar como está**: partição Essencial (7 itens) vs "Mais / Avançado"; grupos por intenção ("Trabalhar um caso", "Pesquisar & IA", "Gerir o escritório", "Administrar"); 25 redirects de rotas legadas; 404 exemplar.

## 6. O que FALTA

1. **Fluxo de convite de usuário**: admin convida por e-mail → link de definição de senha (hoje: admin cria com senha provisória + troca obrigatória; e sem SMTP nada funciona). Mensagem de fallback em toda troca/recuperação: "Sem e-mail? Procure o administrador do escritório."
2. **Aviso global de "IA não configurada"**: banner/estado nos módulos de IA quando nenhum provedor responde, com texto leigo ("A inteligência artificial ainda não foi ativada nesta instalação — fale com o administrador") e botões de IA desabilitados com tooltip, em vez de erro após o clique.
3. **Modo de demonstração/sandbox** com dados fictícios (1 cliente, 1 caso, 1 prazo, 1 peça) para o primeiro contato — hoje o usuário aprende no vazio ou em dados reais.
4. **Caminho visível para o hub de cada ramo** a partir de "Áreas de Atuação" e da tela do caso (pelo ramo do caso).
5. **Vincular prazo a caso/processo** no fluxo "+Novo prazo" da agenda.
6. **Anexo inline na tela do caso** (sem teleporte ao GED).
7. **Suporte a `.txt`/`.doc`** no upload (com validação de conteúdo/magic bytes) ou, no mínimo, mensagem que liste os formatos aceitos e o arquivo rejeitado.
8. **Glossário no Guia do Sistema** (RAG, HITL, GED, DataJud, Data Room, Kanban…) e varredura de jargões da UI.
9. **Manual imprimível/PDF** derivado do `guiaSistema.ts` para o perfil que prefere papel (o conteúdo já existe — falta o export).
10. **Instalação**: para o público-alvo o produto deve permanecer entregue hospedado (`ejc.depaulateixeira.adv.br`); autoinstalação por leigo é inviável (`.env.example` com 540 linhas/164 variáveis, Docker Compose, VPS por SSH) e não deve ser prometida. Um "wizard" de primeira configuração no próprio app (SMTP, chave de IA, dados do escritório) para o admin reduziria a dependência de `.env`.

## 7. Design e responsividade

- **Bom**: design system consistente (tema dourado/Visual Law nos PDFs), empty/error states padronizados (`UI.tsx:981-1043` — "Nada encontrado", "Não foi possível carregar… Tentar novamente"), responsividade real a 390px (sem scroll horizontal, hamburger, cards empilhados), selo LGPD no rodapé.
- **Ajustar**: densidade da tela do caso (ver §5); toasts de validação longe do campo; "Resultado positivo no período — R$ 0,00" no Financeiro (chamar zero de "positivo" soa estranho — usar empty state "sem lançamentos + como lançar"); "Taxas BACEN ao Vivo: indisponível" em vermelho sem explicar causa nem ação; toast órfão "Formato inválido — use JPG, PNG ou WebP" disparável fora de contexto (input de arquivo oculto).

## 8. IA — funcionalidade, confiança e comunicação

- **Manter (é o diferencial ético do produto)**: HITL obrigatório em toda saída de IA, selos "Consta nos documentos / Inferência da IA / Não confirmado", verificador de citações anti-alucinação (dígito CNJ, tetos de súmula), barreira de PII antes de provedor externo (`ai_gateway.py:466-468`), AILog/auditoria, jurimetria que se recusa a opinar com n<5, resultados sempre rotulados "MINUTA — REVISÃO OBRIGATÓRIA".
- **Corrigir**: crash 3.1; mensagens 3.2; a sigla "HITL" na UI (trocar por "Revisão do advogado"); consolidar as ~5 portas de entrada de IA (§5).
- **Pendências já apontadas pela auditoria de IA de 17/07/2026** (`RELATORIO_AUDITORIA_IA_EJC_2026-07-17.md`) que afetam o usuário final: severidade ALTA "IA criminal bloqueada em produção por conflito entre política de sanitização e configuração de deploy"; retrieval sem reranking/embedding antigo; ausência de harness de avaliação (gold set/regressão).

## 9. Confiabilidade e operação

- **Existente e adequado**: `/api/health` + `/api/health/ready` (DB/migrations/redis/embeddings; 503 se DB fora — `main.py:423-473`); backup diário com retenção de 30 dias + rotina Google Drive (runbooks); Sentry/Langfuse gated; trilha de auditoria imutável; degradação graciosa (RAG sem embeddings cai para busca textual; classificador devolve "Serviço de IA indisponível" em vez de 500; BCB com fallback de Selic; handler global "Erro interno. A equipe foi notificada." sem stack trace); go-live de 12/07 com 1.861 testes passando.
- **Pendências abertas conhecidas** (go-live 12/07, não bloqueantes): `cryptography` e `langchain` defasados, advisories na cadeia dev do frontend, access token TTL 8h stateless, Dashboard não conta casos em `triagem` como ativos, uploads `.txt` sem magic bytes, retenção de refresh_tokens, `EMBEDDINGS_ENABLED=false` em produção (busca semântica degradada para textual até ligar).
- **Risco operacional para leigo**: a Central de Diagnóstico é excelente para gestor/suporte, mas é o único lugar que revela que SMTP/integrações estão desligados — o usuário comum nunca a verá. Estados dependentes de configuração deveriam avisar no próprio módulo afetado.

## 10. Recomendações priorizadas

**P0 — bloqueiam o uso autônomo por leigo (fazer antes de qualquer divulgação):**
1. Corrigir o crash da Análise IA sem provedor (3.1) — renderizar estado degradado amigável.
2. Camada única de tradução de erros de IA: nenhum texto com `.env`/provider/chave chega à UI; mensagem padrão leiga + orientação (3.2).
3. Banner/estado global "IA não ativada" + botões de IA desabilitados com explicação (6.2).
4. Login/recuperação: fallback "procure o administrador"; detectar SMTP desligado e ajustar a mensagem (2.1, 2.2).
5. Unificar os dois onboardings num só e impedir que o popover cubra botões (2.4, 2.5); manter sessão após troca de senha (2.3).
6. Investigar/corrigir o rascunho "Salvo em Peças" que não aparece em Peças (3.3).

**P1 — reduzem drasticamente o custo cognitivo:**
7. Varredura de jargão (RAG→"base de conhecimento", HITL→"revisão do advogado", etc.) + glossário no Guia (§4, 6.8).
8. Link para o hub do ramo em "Áreas de Atuação" e na tela do caso (6.4).
9. Reorganizar a faixa de ações da tela do caso (frequente × destrutivo × avançado) e as abas duplicadas (§5).
10. Datas dd/mm/aaaa forçadas; validação junto ao campo; vínculo caso↔prazo no "+Novo prazo"; anexo inline no caso; upload aceitar `.doc`/`.txt` ou explicar formatos (3.5-3.9).
11. Corrigir placeholder "contrato bancário" no ramo trabalhista e o título "Ajuda — inteligencia" (§4).

**P2 — polimento e escala:**
12. Modo demonstração com dados fictícios (6.3); manual em PDF exportado do Guia (6.9); wizard de configuração inicial para o admin (6.10); feature-flags por perfil para módulos avançados (§5); Ctrl+K respeitar modais abertos; saudação com nome e sem gênero assumido; empty state do Financeiro; ligar `EMBEDDINGS_ENABLED` em produção; endereçar as 3 lacunas da auditoria de IA de 17/07.

---

_Relatório gerado a partir de navegação real da aplicação em execução (screenshots arquivados na sessão de auditoria) e varredura do código com referências de arquivo. Nenhum achado é hipotético._
