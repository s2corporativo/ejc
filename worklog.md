# Worklog — Projeto JuridIA (Clone do MinutaIA)

## Análise do Site Original (minutaia.com.br)

O MinutaIA é uma LegalTech SaaS brasileira que usa IA generativa para produzir minutas/documentos jurídicos (petições, sentenças, despachos, contratos). Foi adquirida pelo Jusbrasil em agosto de 2026. Principais funcionalidades mapeadas:

- **Geração de minutas com IA**: petições, sentenças, despachos, contratos etc.
- **Múltiplos perfis de IA combinados** em cada etapa da geração.
- **Processamento do inteiro teor** do processo em uma única operação (até 6 mil páginas).
- **Jurisprudência inteligente** com pesquisa assistida por IA nos principais tribunais (TJ, STF, STJ etc.).
- **Aprendizado de estilo**: aprende o estilo individual de redação do usuário.
- **Anonimização local (tarja-1)**: detecta CPFs, nomes, endereços, valores e substitui por marcadores `[NOME_0001]` ANTES de enviar à IA; desanonimiza no retorno localmente.
- **Conformidade LGPD e Resolução CNJ 615/2025**.
- **Privacidade**: criptografia TLS + AES-256, sem treinar IA com dados dos usuários.
- **Habilidades (skills)**: 2.000 pacotes de conhecimento jurídico orientando a geração.
- **Editor**: páginas reais com timbrado, cabeçalho, rodapé, notas de rodapé, comentários, histórico de versões, tabelas, sumário, IA que sugere em vez de reescrever.
- **Geração em Lote** com geração em etapas.
- **Prints do Processo**: insere imagens do processo como figura.
- **JurisprudênciaIA**: site público de pesquisa de jurisprudência conversando com IA.
- **Conecta**: extensão Chrome que se integra a PJe, SEEU, Eproc, STF, Projudi, STJ, e-SAJ, SEI, JPe. OCR incluso.
- **Estatísticas**: +90 mil usuários, +35 milhões de minutas geradas, +150 instituições públicas, 26+DF estados, +5 mil escritórios.
- **Planos**: Individual I (R$140/mês, 100 minutas), Individual II (R$280, 200), Individual III (R$560, 400). Mensal/semestral (-10%)/anual (-25%).

## Decisão de Arquitetura

Como a rota única visível é `/`, vou construir uma SPA-style com **duas views controladas por estado**:
1. **Landing**: hero + stats + features + tarja-1 + privacidade + novidades + integrações + planos + mídia + footer sticky.
2. **Plataforma (App)**: dashboard com gerador de minutas (template, fatos, skills, preview anonimizado, editor + IA sugestões), busca de jurisprudência, geração em lote, lista de documentos salvos.

**Stack**: Next.js 16 App Router, TS, Tailwind 4, shadcn/ui, Prisma+SQLite, z-ai-web-dev-sdk (LLM + web_search no backend), framer-motion.

## Status Atual
- Schema Prisma sendo desenhado.
- Próximos passos: seed de dados, APIs, frontend landing + app.

---
Task ID: 1-7 (build completo)
Agent: main (Z.ai Code)
Task: Construir clone do MinutaIA chamado "JuridIA" — LegalTech de IA para geração de minutas jurídicas brasileiras com anonimização local (tarja-1), busca de jurisprudência, geração em lote, editor e planos.

Work Log:
- Analisado o site original minutaia.com.br via web-reader + web-search: mapeadas funcionalidades (anonimização tarja-1, múltiplos perfis de IA, jurisprudência inteligente, habilidades/skills, editor com sugestões, geração em lote, Conecta para PJe/Eproc/etc, conformidade LGPD + CNJ 615/2025, planos individuais R$140/R$280/R$560).
- Definida arquitetura: SPA de rota única `/` com duas views (landing + app) via store Zustand persistida. Stack: Next.js 16 App Router + TS + Tailwind 4 + shadcn/ui + Prisma/SQLite + z-ai-web-dev-sdk (LLM + web_search no backend) + framer-motion.
- Schema Prisma criado: User, Template, Skill, Document, JurisprudenceSearch, NewsItem. Aplicado com `bun run db:push`.
- Seed: 6 templates (Petição Inicial Cível, Sentença, Apelação, Contrato de Prestação de Serviços, Parecer Jurídico, Despacho), 11 skills (CPC estrutura/competência, dano moral, LGPD, CP, CLT, CTN, CDC, CC responsabilidade civil, família alimentos, CNJ 615/2025), 5 novidades (Geração em Lote, Novo Editor, Prints do Processo, Habilidades, JurisprudênciaIA), 1 usuário demo.
- Utilitário `src/lib/anonymize.ts`: detecção local de CPF, CNPJ, RG, telefone, e-mail, CEP, PIS, placa, conta bancária, valores R$, e nomes próprios (heurística com stop-words jurídicas). Funções `anonymize`, `deanonymize`, `detect`. Marcadores `[TIPO_0001]`.
- Tipos compartilhados em `src/lib/types.ts` (TemplateDTO, SkillDTO, NewsDTO, DocumentDTO, GenerateMinutaRequest/Response, JurisprudenceResult/Response).
- 7 API routes: `/api/templates`, `/api/skills`, `/api/news`, `/api/stats`, `/api/anonymize`, `/api/generate-minuta` (LLM com anonimização pré + desanonimização pós), `/api/jurisprudence` (web_search com cache 1h + persistência), `/api/documents` (GET/PATCH/DELETE).
- Store Zustand persistido (`src/lib/store.ts`): view, appTab, currentDocId, selectedTemplateSlug, selectedSkillSlugs, authOpen, user.
- Theme provider (next-themes) + useMounted hook (useSyncExternalStore) + ThemeToggle.
- Header sticky com glass effect, navegação, login e "Acessar Plataforma". Sheet mobile.
- Footer sticky (`mt-auto` + `min-h-screen flex flex-col`) com 4 colunas e social.
- AuthDialog com login Google/email (simulado, ativa conta demo).
- Landing (9 seções): Hero (com gradientes e badge de stats), Stats (4 cards buscando /api/stats), Features (6 cards), Anonymization (demo interativa tarja-1 com textarea + output + 3 pilares), Privacy (4 pilares), Integrations (9 sistemas + 5 features + extensão), News (6 cards de /api/news), Pricing (3 planos com toggle mensal/semestral/anual e tabs individual/corporativo/enterprise), Media (3 cards).
- App (5 tabs): Generator (seletor de templates, formulário dinâmico por template, skills sugeridas + catálogo em Sheet, geração com animação de etapas anon→skills→llm→restoring, auto-navega para editor), Editor (textarea estilo "página" + preview renderizado + tab marcadores + tab metadados + pedir sugestão IA + localizar/substituir + download .txt/.md + salvar via PATCH), JurisprudenceIA (modo IA/palavra-chave + queries sugeridas + resultados reais do web_search), Batch (CRUD de casos + geração em lote com primeiro modelo aprovado), DocumentsList (grid de minutas salvas com filtro + abrir/excluir).
- Paleta CSS customizada (verde-escuro legal + amber, sem indigo/azul) em claro/escuro. Utilities: container-juridia, bg-dot, gradient-text, glass, doc-page (página com serifa), marker-chip, scrollbar-juridia, animações marquee/pulse-soft.
- ESLint limpo (0 erros, 0 warnings).
- Dev server iniciado com `setsid -f next dev -p 3000 -H 0.0.0.0` (binding 0.0.0.0 é essencial para o gateway Caddy na porta 81 alcançar o localhost:3000).
- Self-verification com agent-browser (via http://21.0.7.103:81/):
  - Landing renderiza 100% (title "JuridIA — Inteligência Artificial para o Direito Brasileiro", h1 "O futuro do Direito brasileiro começa aqui", body 98540 chars, todas as seções presentes).
  - Click "Acessar Plataforma" → app view com 5 tabs.
  - Templates carregam (6 cards), seleção "Petição Inicial (Cível)" funciona.
  - Formulário preenchido (autor "João Carlos da Silva", réu "Banco XYZ S.A.", valor "R$ 50.000,00").
  - "Gerar minuta com IA" → LLM gera petição real em português jurídico (35s), marcadores [CPF_0001]/[RG_0001]/[ENDERECO_0001] preservados, nome restaurado localmente, auto-switch para Editor.
  - Editor mostra título "Petição Inicial (Cível) — 03/10/2026" com tabs Editar/Visualizar/Marcadores/Metadados.
  - Anonimização (tarja-1): click "Anonimizar localmente" → output com [NOME_0001], [CPF_0001], [RG_0001] + 12 marker chips + mapa detalhado.
  - JurisprudênciaIA: query "cliente inscrito indevidamente..." → 7 resultados reais (ex: TJ-SC Apelação) com links "Abrir fonte".
  - Footer: body min-h-screen flex-col + mt-auto funciona (footerAtBottom=true).
- APIs: stats/templates/skills/news/documents/anonymize/generate-minuta/jurisprudence todas HTTP 200.

Stage Summary:
- Projeto JuridIA totalmente funcional end-to-end. Clone do MinutaIA com todas as features principais: landing completa, plataforma de geração de minutas com IA + anonimização local (tarja-1), busca de jurisprudência real, geração em lote, editor com sugestões, 6 templates, 11 skills, planos, e footer sticky.
- Dev server sobrevive entre comandos bash usando `setsid -f` (fork completo) + bind 0.0.0.0. Acesso externo via gateway Caddy porta 81.
- Próxima fase: cron webDevReview a cada 15 min para revisão/QA contínuos e adição incremental de features.

---
Task ID: 8 (cron webDevReview #1)
Agent: cron webDevReview (15min)
Task: Review JuridIA project — QA via agent-browser, fix bugs, add features (styling + functionality), update worklog.

Work Log:
- Lido worklog anterior: projeto JuridIA funcional end-to-end (landing + app com 6 tabs, 6 templates, 11 skills, geração de minutas com IA + anonimização tarja-1, jurisprudência, lote, editor).
- Dev server confirmado ativo (PID 4517, HTTP 200 em localhost:3000 e gateway:81).
- QA com agent-browser (após limpar localStorage para resetar estado persistido):
  - Landing: 9 seções, 7 h2, H1 "O futuro do Direito brasileiro começa aqui", 0 erros de console.
  - Anonimização tarja-1: 12 marcadores detectados ([NOME_0001], [CPF_0001], [RG_0001], [TELEFONE_0001], [EMAIL_0001], [CEP_0001]...).
  - App: 5 tabs visíveis, templates carregam, seleção funciona.
  - Geração de minuta: LLM gera petição real em ~35s, auto-switch para Editor.
  - JurisprudênciaIA: 2 resultados reais retornados.
  - Geração em lote: tab funcional.
  - Minutas salvas: 2 documentos da sessão anterior.
  - Footer sticky: funcionando (top=558, vh=577, footer corretamente posicionado).
- BUG ENCONTRADO: LLM inventava marcadores não presentes no input original (ex: [LOCAL_0001], [PROFISSAO_0001]) que não estavam nos dados anonimizados.
- BUG CORRIGIDO em /api/generate-minuta/route.ts: adicionada lista EXAUSTIVA de marcadores disponíveis no prompt + instrução explícita "NUNCA crie marcadores novos. Se um campo não tiver marcador, escreva ____ no lugar." + função describeMarker() para dar contexto semântico ao LLM. Verificado: geração agora usa ____ para dados faltantes, sem inventar marcadores.
- 3 NOVOS TEMPLATES adicionados ao seed: Petição Inicial Trabalhista (CLT), Queixa-Crime (ação penal privada), Defesa Administrativa Fiscal (tributário). Total: 9 templates.
- NOVO TAB Dashboard criado (src/components/app/dashboard.tsx): card de uso do plano com progress bar, grid de 4 stats (minutas salvas, buscas, templates, skills), 4 quick actions, atividade recente (6 minutas), card de impacto da comunidade. Store atualizada com appTab "dashboard" como default.
- NOVA SEÇÃO "Como funciona" na landing (src/components/landing/how-it-works.tsx): 4 passos com timeline circular (Descreva o caso → Anonimização local → IA gera a minuta → Receba e revise), conectores visuais, ícones numerados.
- EXPORT PDF adicionado ao editor: função printPdf() abre nova janela com HTML formatado (timbrado, rodapé com branding JuridIA, @page margins 2.5cm, botão "Imprimir / Salvar PDF"), conversão markdown→HTML com escape. Botão "PDF" adicionado à toolbar do editor.
- AppShell melhorado: tab bar agora é sticky (top-16) com glass effect para permanecer visível durante scroll.
- ESLint limpo (0 erros, 0 warnings). Dev server saudável.

Stage Summary:
- BUG crítico corrigido: LLM não inventa mais marcadores — usa ____ para dados faltantes.
- 3 novos templates (9 total): trabalhista, penal, tributário.
- Dashboard tab novo com stats de uso, quick actions e atividade recente.
- Seção "Como funciona" na landing com timeline visual de 4 passos.
- Export PDF no editor com formatação profissional.
- Tab bar sticky no app.
- Próxima fase: adicionar autenticação real (NextAuth), histórico de versões no editor, mais skills, perfil de estilo do advogado.

---
Task ID: 9 (cron webDevReview #2)
Agent: cron webDevReview (15min)
Task: Continuar QA e adicionar features (styling + funcionalidade). Priorizar command palette, histórico de versões, mais skills, FAQ.

Work Log:
- Lido worklog anterior (review #1): bug LLM inventando marcadores corrigido, 9 templates, Dashboard tab, seção "Como funciona", export PDF, tab bar sticky.
- Dev server confirmado ativo (PID 4517, HTTP 200, 0 erros no dev.log).
- QA via agent-browser (após limpar localStorage): landing renderiza 11 seções (era 10, +1 FAQ), H1 correto, 0 erros de console, 0 page errors.
- COMMAND PALETTE (Cmd+K / Ctrl+K) criado em src/components/command-palette.tsx: 12 comandos agrupados (Navegação, Plataforma, Conta, Aparência, Ações, Ajuda), atalhos visuais (kbd), navegação completa (landing + 6 tabs app), toggle de tema, login, print. Listener global para Cmd+K. Botão "⌘K Comandos" adicionado ao header.
- SEÇÃO FAQ adicionada à landing (src/components/landing/faq.tsx): 8 perguntas frequentes com Accordion (anonimização local, LGPD, CNJ 615/2025, segredo de justiça, habilidades, sistemas suportados, planos, uso da minuta gerada). Estilo com Badge e cards arredondados.
- HISTÓRICO DE VERSÕES no editor: novo tab "Versões" com badge de contagem, auto-save a cada 2 min quando há mudanças, criação manual, restauração de versões, exclusão individual, persistência em memória por sessão. Interface com timestamps e char counts.
- DIRTY STATE no editor: botão Salvar muda para "Salvar*" quando há mudanças não salvas, volta para "Salvo" após persistir, disabled quando não há mudanças. Indicador visual claro do estado.
- ATALHOS DE TECLADO no editor: Ctrl/Cmd+S para salvar, Ctrl/Cmd+Enter para pedir sugestão IA. Prevenção de comportamento padrão.
- 6 NOVAS SKILLS adicionadas ao seed (total 17): INSS Tempo de Contribuição (previdenciário), CPC Tutela de Urgência/Evidência, CPC Audiência de Conciliação, Juros e Correção Monetária, OAB Estatuto da Advocacia, CDC Cláusulas Abusivas. Cobertura ampliada para previdenciário, financeiro, ética profissional.
- ESLint limpo (0 erros, 0 warnings após remover directive unused).
- Verificação final: landing 11 seções, FAQ com título "Perguntas frequentes", command palette abre com "Digite um comando ou busque...", 17 skills via API, editor versions tab com "Histórico de versões" + "Criar versão agora" + contagem "1 versões", navegação via palette funciona (click em jurisprudência → tab JurisprudênciaIA).

Stage Summary:
- Command palette (Cmd+K) com 12 comandos e navegação completa implementado.
- Seção FAQ com 8 perguntas/fundamentações sobre privacidade, conformidade e uso.
- Histórico de versões no editor (auto-save 2 min + manual + restauração).
- Dirty state no botão Salvar com indicador visual.
- Atalhos de teclado (Ctrl+S salvar, Ctrl+Enter sugerir).
- 6 novas skills (17 total) cobrindo previdenciário, financeiro, ética OAB.
- 0 erros de console, 0 erros ESLint, dev server saudável.
- Próxima fase sugerida: autenticação real (NextAuth), persistência de versões no DB, perfil de estilo do advogado, mais templates empresariais, integração com e-SAJ/PJe real.
