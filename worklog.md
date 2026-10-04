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

---
Task ID: 10 (cron webDevReview #3)
Agent: cron webDevReview (15min)
Task: Continuar QA e adicionar features (styling + funcionalidade). Priorizar Settings/perfil, sugestão IA real, Testimonials, skeleton loading.

Work Log:
- Lido worklog anterior (review #2): command palette, FAQ, histórico de versões, dirty state, atalhos de teclado, 17 skills implementados.
- Dev server confirmado ativo (PID 4517, HTTP 200, 0 erros no dev.log, todas as 5 APIs HTTP 200).
- QA via agent-browser (após limpar localStorage): landing renderiza 11 seções, H1 correto, 0 erros de console.
- BUG ENCONTRADO: nav do header não incluía link para "FAQ" e "Como funciona" (seções existentes na landing).
- BUG CORRIGIDO em site-header.tsx: adicionados "Como funciona" (#como-funciona) e "FAQ" (#faq) ao array NAV. Agora 7 itens de navegação.
- NOVA TAB "Configurações" criada (src/components/app/settings.tsx): perfil do advogado (nome, OAB, UF, escritório, email, telefone, endereço), 4 estilos de redação (formal/sintético/acadêmico/direto) com exemplos prévios, skills padrão (auto-aplicadas em todas as minutas), preview de assinatura profissional em tempo real. Store expandida com `profile`, `writingStyle`, `defaultSkills`. 7 tabs agora no app.
- NOVA API /api/suggest criada (LLM real): recebe instruction + currentContent + templateName + style, gera trecho jurídico em português brasileiro. System prompt inclui conformidade CPC/CC/CNJ 615/2025. Fallback offline com trechos pré-formatados (fundamentação, pedidos, fatos). Respeita o estilo de redação selecionado (formal/sintético/acadêmico/direto).
- EDITOR atualizado: askSuggestion() agora chama /api/suggest (real LLM) em vez de simulação local. Aceitar sugestão marca dirty state. Verificado: pediu "fundamentar com responsabilidade civil" → IA gerou parágrafo citando art. 927 do CC em ~12s.
- NOVA SEÇÃO "Depoimentos" (Testimonials) na landing (src/components/landing/testimonials.tsx): 6 depoimentos de advogados (sócia, defensor público, procurador, etc.) com rating 5 estrelas, avatar com iniciais, layout masonry (columns CSS). Landing agora tem 12 seções.
- SKELETON LOADING adicionado à lista de minutas: 6 cards placeholder com animação pulse durante o carregamento (em vez de spinner simples).
- COMMAND PALETTE atualizado: adicionado comando "Configurações do perfil" (atalho ",") navegando para tab Settings.
- ESLint limpo (0 erros, 0 warnings).
- Verificação final: landing 12 seções, nav com 7 links (incluindo "Como funciona" e "FAQ"), Settings tab funcional com 4 estilos e preview de assinatura, suggest API real retorna trecho jurídico em ~12s, testimonials com 6 depoimentos, skeleton loading em documents.

Stage Summary:
- Bug corrigido: nav agora inclui "Como funciona" e "FAQ".
- Tab Settings nova com perfil profissional, 4 estilos de redação, skills padrão, preview de assinatura.
- API /api/suggest real (LLM) substituiu simulação local no editor.
- Seção Depoimentos na landing (6 testimonials em masonry).
- Skeleton loading nos documentos.
- Command palette com comando de configurações.
- 0 erros console, 0 ESLint, dev server saudável.
- Próxima fase sugerida: autenticação NextAuth real, persistência de versões no DB, favoritos/marcadores em minutas, export DOCX, busca full-text nos documentos, painel admin de templates.

---
Task ID: 11 (cron webDevReview #4)
Agent: cron webDevReview (15min)
Task: Continuar QA e adicionar features. Priorizar busca full-text, favoritos, export DOCX, CTA/newsletter, contador de palavras.

Work Log:
- Lido worklog anterior (review #3): Settings tab, /api/suggest real LLM, Testimonials, skeleton loading, command palette atualizado.
- Dev server confirmado ativo (PID 4517, HTTP 200, 0 erros no dev.log, todas APIs HTTP 200, /api/suggest 405 GET esperado).
- QA via agent-browser (após limpar localStorage): landing 12 seções, H1 correto, 7 tabs no app, 0 erros de console.
- DOCUMENTS LIST reescrito com: (1) BUSCA FULL-TEXT em título + templateName + generatedContent + anonymizedFacts + skillSlugs, com highlight de matches via <mark> estilizado; (2) FAVORITOS persistidos em localStorage (toggle por estrela, filtro "Favoritas" com badge de contagem, favoritos aparecem primeiro na ordenação padrão); (3) ORDENAÇÃO por atualizado/criado/título/tamanho via Select; (4) STATS no header (total de minutas, favoritas, palavras); (5) card aprimorado com badges (template, favorita), data, palavra count, tempo de leitura, animação framer-motion stagger; (6) estado vazio diferenciado (busca vs. sem docs); (7) botão "Limpar filtros".
- EDITOR atualizado com: (1) CONTADOR DE PALAVRAS em tempo real (wordCount = content.split); (2) TEMPO DE LEITURA estimado (200 pal/min); (3) BADGE "não salvo" com pulse quando dirty; (4) EXPORT .DOC (HTML com namespace Word XML, @page Section1, Times New Roman, justificado com indent, abre direto no Word/Google Docs); (5) nova toolbar com PDF | .doc | .txt | .md | Salvar.
- NOVA SEÇÃO "CTA + Newsletter" na landing (src/components/landing/cta-newsletter.tsx): card dividido em 2 colunas — CTA "Pronto para acelerar sua advocacia?" com botões "Testar gratuitamente" e "Ver plataforma" + 3 checks (3 minutas grátis, sem cartão, LGPD), e formulário de newsletter com validação de email, estado submitted com feedback positivo. Landing agora tem 13 seções.
- ESLint limpo (0 erros, 0 warnings).
- Verificação final via agent-browser:
  - Landing: 13 seções, CTA com título correto, newsletter submete e mostra "Inscrição confirmada!".
  - Documents: 3 minutas, busca "PETIÇÃO" → 3 resultados com highlight mark, favoritos toggle funciona, filtro "Favoritas" mostra 1 doc, ordenação via Select.
  - Editor: "652 palavras" e "3 min de leitura" exibidos no header, botão .doc presente.
  - 0 erros de console em todos os testes.

Stage Summary:
- Busca full-text com highlight implementada nos documentos.
- Sistema de favoritos persistido em localStorage com filtro e ordenação prioritária.
- Ordenação multi-critério (atualizado/criado/título/tamanho) via Select.
- Stats no header dos documentos (total, favoritas, palavras).
- Contador de palavras e tempo de leitura em tempo real no editor.
- Badge "não salvo" com pulse indicator no editor.
- Export .doc (Word/Google Docs compatível) adicionado ao editor.
- Seção CTA + Newsletter na landing com validação e feedback.
- 13 seções na landing, 7 tabs no app, 9 templates, 17 skills.
- 0 erros console, 0 ESLint, dev server saudável.
- Próxima fase sugerida: autenticação NextAuth real, persistência de versões no DB, painel admin de templates, integração PJe real, mobile app.

---
Task ID: 12 (cron webDevReview #5 — Análise técnica MinutaIA)
Agent: cron webDevReview (15min)
Task: Baseado na análise técnica detalhada da MinutaIA, implementar diferenciais arquiteturais: Resumo Avançado, Referências Rastreáveis, Modo Molde, Logs de Auditoria + Ledger de Créditos.

Work Log:
- Lida análise técnica profunda do MinutaIA (16 seções) destacando 4 diferenciais arquiteturais críticos: (1) Resumo Avançado estruturado em cards, (2) Referências Rastreáveis com document_id+page, (3) Modo Molde com alterações estruturadas (replace/add/remove + anchor + reason), (4) Logs de auditoria + ledger de créditos imutáveis.
- Dev server confirmado ativo (PID 4517→12931 após restart para Prisma client, HTTP 200, 0 erros).
- SCHEMA PRISMA expandido com 4 novos modelos: CaseAnalysis (parties, timeline, requests, proofs, decisions, values, risks, nextSteps como JSON), MoldeChange (operation, anchor, replacement, reason, status, appliedAt), AuditEvent (action, resource, resourceId, metadata, ip — imutável, indexado por userId/action/createdAt), UsageLedger (type, operation, amount, balance, reason — imutável ledger com saldo calculado). `bun run db:push` aplicado.
- LIB DE AUDITORIA criada (src/lib/audit.ts): logAuditEvent() registra ações imutáveis com metadata + IP; logUsageEntry() calcula saldo incremental e registra débitos/créditos/estornos. Importado e chamado em generate-minuta (debit: -1 + audit generate_minuta), documents DELETE (audit delete_document) e PATCH (audit edit_document).
- API /api/case-analysis (POST+GET): LLM real analisa fatos do caso e retorna JSON estruturado com 8 categorias (parties, timeline, requests, proofs, decisions, values, risks, nextSteps). System prompt força resposta JSON válida. Fallback offline com heurística baseada em keywords. Persiste análises no DB. Verificado: gerou 2 parties, 1 risk, 3 nextSteps para caso de inscrição indevida.
- API /api/molde (POST): Modo Molde real. Recebe documento-base + instrução, retorna JSON {changes: [{operation, anchor, replacement, reason}]}. System prompt instrui a NÃO reescrever o documento, apenas propor alterações pontuais com anchors exatos. Validação: anchors devem existir (parcialmente) no documento-base. Máx 10 mudanças.
- API /api/audit (GET+POST): Lista eventos de auditoria (ordenados por createdAt desc, limit 200, filtro por action). POST para registrar novos eventos com IP.
- API /api/usage-ledger (GET): Lista o ledger imutável com summary (currentBalance, totalDebit, totalCredit, byOperation).
- COMPONENTE CaseAnalysis (Resumo Avançado): textarea para fatos + título, botão "Analisar caso" com loading, grid de 6 cards (Partes, Cronologia, Pedidos, Provas, Decisões, Valores), card de Riscos com badges coloridos (alto=vermelho/médio=ambar/baixo=verde), lista numerada de Próximos Passos, skeleton loading, histórico de análises anteriores.
- COMPONENTE MoldeMode: integrado como novo sub-tab "Modo Molde" no editor. Textarea para instrução, gera lista de mudanças propostas com diff visual (anchor destacado em secondary, replacement em primary/5, badges coloridos por operation: replace=azul/add=verde/remove=vermelho), botões aceitar/rejeitar por mudança, botão "Aplicar N alterações" que substitui/adiciona/remove no documento-base.
- COMPONENTE AuditLedger: tab "Auditoria" com 4 cards de resumo (saldo atual, consumidos, recebidos, total de operações), grid de consumo por operação, sub-tabs "Ledger de uso" (lista imutável de entradas com badges débito/crédito e saldo) e "Trilha de auditoria" (lista de eventos com action labels, resource, resourceId, metadata JSON, timestamp).
- STORE expandido: appTab agora inclui "case-analysis" e "audit". AppShell atualizado com 9 tabs (Dashboard, Gerar, Editor, Resumo do caso, JurisprudênciaIA, Lote, Minutas, Auditoria, Configurações) + atalhos de teclado (1/g/e/c/j/b/d/a/,).
- COMMAND PALETTE atualizado: 14 comandos com novos "Resumo avançado do caso" (C) e "Auditoria & créditos" (A).
- ESLint limpo (0 erros, 0 warnings). Dev server reiniciado para carregar novo Prisma client.
- Verificação end-to-end via agent-browser:
  - Case Analysis: fatos preenchidos → IA retornou parties (2), risks (1), nextSteps (3) em ~15s. Cards estruturados renderizados corretamente.
  - Generate minuta → auto-switch para Editor → audit event "generate_minuta" criado + ledger entry debit -1 (balance: 199).
  - Audit tab: "1 entradas" no ledger, "1 eventos" na trilha com "Geração de minuta" visível, summary cards com saldo 199.

Stage Summary:
- 4 diferenciais arquiteturais do MinutaIA implementados conforme análise técnica.
- Resumo Avançado: 8 categorias estruturadas via LLM + fallback heurístico, cards visuais, riscos coloridos, próximos passos numerados.
- Modo Molde: alterações estruturadas (replace/add/remove com anchor) em vez de reescrever, diff visual, aceitar/rejeitar individual.
- Auditoria imutável: AuditEvent para generate/edit/delete, com metadata + IP + timestamps.
- Ledger de créditos imutável: débito automático de -1 por minuta gerada, saldo incremental, summary por operação.
- 9 tabs no app, 14 comandos no palette, 4 novos modelos Prisma, 4 novas APIs.
- 0 erros console, 0 ESLint, dev server saudável (PID 12931).
- Próxima fase sugerida: Referências Rastreáveis com document_id+page_number nas minutas, upload de PDFs com OCR, RAG documental, editor ProseMirror/Lexical com diff real, fila assíncrona para lotes.

---
Task ID: 13 (adaptação para uso pessoal no escritório)
Agent: main (Z.ai Code)
Task: Usuário esclareceu que o sistema é para uso PESSOAL no escritório (não SaaS para vender). Adaptar: remover marketing pesado, adicionar gestão de clientes/casos, focar em produtividade.

Work Log:
- Contexto ajustado: sistema passa de SaaS comercial para ferramenta pessoal de escritório. Sem necessidade de planos, testimonials, newsletter, media mentions.
- Store atualizado: view default agora é "app" (pula landing marketing), adicionado currentCaseId, appTab inclui "clients".
- SCHEMA PRISMA expandido com 2 novos modelos: Client (name, email, phone, document, notes, color) e Case (title, number, area, status, notes, clientId FK). Document ganhou caseId FK + tags JSON. `bun run db:push` aplicado (onDelete: SetNull para preservar minutas órfãs).
- 2 NOVAS APIs: /api/clients (GET/POST/PATCH/DELETE com logAuditEvent) e /api/cases (GET com filtro clientId/status, POST/PATCH/DELETE com auditoria).
- NOVO COMPONENTE ClientsCases (src/components/app/clients-cases.tsx): gestão completa de clientes com cards expansíveis, busca por nome/email/CPF, CRUD via Dialog, casos organizados por cliente com toggle de status (active/concluded), badges coloridos por área (civil/penal/trabalhista/tributário/consumer/família/previdenciário), contagem de casos e minutas por cliente, animações framer-motion.
- AppShell REESCRITO: 10 tabs agora (Início, Clientes, Gerar minuta, Editor, Minutas, Resumo do caso, JurisprudênciaIA, Geração em lote, Auditoria, Configurações). Branding mudou de "Plataforma" para "Escritório". Atalhos de teclado: 1/C/G/E/D/R/J/B/A/,.
- HEADER reescrito para uso pessoal: nav com 7 itens práticos (Início, Clientes, Gerar, Editor, Minutas, Jurisprudência, Auditoria), botão "Site" para ver página institucional, sem "Login" nem "Acessar Plataforma" (já logado).
- LANDING SIMPLIFICADA: removidas seções de marketing (Stats com números inflados, Testimonials, Pricing, Newsletter/CTA, Media, Integrations). Mantidas apenas: Hero (enxuto, sem números de marketing), HowItWorks, Features, Anonymization (tarja-1), Privacy, FAQ. 6 seções (era 13).
- HERO reescrito: badge "Assistente jurídico do seu escritório", H1 "Gere minutas jurídicas com IA e sigilo", descrição focada em uso interno, 4 badges de conformidade (tarja-1, LGPD, CNJ 615/2025, sem treinar IA), botões "Gerar minuta agora" + "Ver início".
- DASHBOARD adaptado: removido card "Plano Individual" (marketing SaaS), substituído por "Bem-vindo de volta" com contagem de minutas/templates/habilidades. Quick actions atualizadas: Gerar minuta, Meus clientes, Pesquisar jurisprudência, Resumo do caso. Card "Impacto do JuridIA" (comunidade) substituído por "Produtividade do escritório" com stats reais (minutas total/hoje/favoritas) + dicas de atalhos + fluxo recomendado (cadastrar cliente → criar caso → gerar minuta → revisar → exportar).
- ESLint limpo (0 erros, 0 warnings). Dev server reiniciado (PID 15412, HTTP 200).
- Verificação end-to-end via agent-browser:
  - App abre direto no dashboard (não mais landing marketing).
  - Tab Clientes funcional: criou cliente "João da Silva Teste" via Dialog, confirmado pela API.
  - Caso "Ação indenizatória teste" criado vinculado ao cliente, área civil, status active.
  - 0 erros de console.
  - 10 APIs HTTP 200.

Stage Summary:
- Sistema adaptado de SaaS comercial para ferramenta pessoal de escritório.
- Gestão de Clientes e Casos (CRUD completo) com organização por área jurídica e status.
- Store default: app view (pula marketing).
- Landing enxuta (6 seções, sem pricing/testimonials/newsletter/media).
- Header prático (7 itens de navegação direta).
- Dashboard focado em produtividade real (sem números de marketing inflados).
- 10 tabs no app, 10 APIs funcionais, 2 novos modelos Prisma (Client, Case).
- Fluxo recomendado: Cliente → Caso → Minuta → Editor → Export.
- 0 erros console, 0 ESLint, dev server saudável.
- Próxima fase: vincular minutas a casos no generator, filtros por cliente nas minutas, templates personalizados do escritório (CRUD), export com dados do cliente/caso preenchidos automaticamente.

---
Task ID: 14 (análise de viabilidade — EJC)
Agent: main (Z.ai Code)
Task: Analisar viabilidade dos recursos do EJC (2 zips enviados pelo usuário) para o JuridIA.

Work Log:
- Recebidos 2 arquivos ZIP do usuário:
  - ZIP 1 "Opinião sobre as IAs implementadas no EJC": 18 arquivos — integração Manus API v2 (Python FastAPI), webhook RSA-SHA256, structured output, sanitizer, migration 162_manus_tasks.
  - ZIP 2 "Verificar conhecimento jurídico e núcleo de IA do EJC": 33 arquivos — RAG com pgvector, citation_gate (anti-alucinação), ai_service, gold set evaluation, curadoria de fontes jurídicas.
- EJC é Python/FastAPI + PostgreSQL/pgvector + 37 routers + OAuth2/JWT. JuridIA é Next.js/SQLite/Prisma + TypeScript. Stacks diferentes.
- Análise de viabilidade por recurso:
  1. Manus API: VIÁVEL com adaptação (REST API, fetch em Node, crypto para webhook). Requer chave paga + webhook HTTPS. Prioridade baixa para uso pessoal.
  2. RAG com pgvector: NÃO DIRETAMENTE VIÁVEL no SQLite. Alternativa: embeddings em JSON + cosine em JS (até ~5k chunks) ou web_search já existente.
  3. Citation Gate (anti-alucinação): VIÁVEL — o mais portável. Regex de extração, verificação contra base SQLite, fail-closed. PRIORIDADE MÁXIMA.
  4. Gold Set/Evaluation: VIÁVEL — JSONL + runner TS. Requer curadoria de 75 casos reais pelo escritório.
  5. Curadoria de Fontes: VIÁVEL — modelo Prisma LegalSource com URL oficial + hash + vigência.
  6. Sanitização tarja-1: JÁ IMPLEMENTADO no JuridIA.
  7. HITL + Auditoria: JÁ IMPLEMENTADO no JuridIA.
- Recomendação: implementar Citation Gate (prioridade máxima) + RAG-lite (prioridade alta) + Gold Set pessoal (média). Não portar pgvector/FastAPI/37 routers.

Stage Summary:
- Análise de viabilidade concluída para os 2 zips do EJC.
- Citation Gate é o recurso de maior valor e mais portável — deve ser implementado primeiro.
- RAG-lite com embeddings em SQLite é viável para volume de escritório individual.
- 3 recursos já existem no JuridIA (tarja-1, HITL, auditoria).
- Manus API é viável mas requer chave paga + infra de webhook.
- Próximo passo: implementar Citation Gate (citation_gate.ts + LegalSource Prisma model) se o usuário confirmar.

---
Task ID: 15 (Citation Gate — anti-alucinação implementado)
Agent: main (Z.ai Code)
Task: Implementar Citation Gate (prioridade máxima da análise de viabilidade do EJC) — extrair citações, verificar contra base curada, fail-closed.

Work Log:
- SCHEMA PRISMA: modelo LegalSource adicionado (tipo, diploma, numero, tribunal, textoTrecho, vigente, urlOficial, hashConteudo, dataConsulta, revisadoPor). Unique constraint em (tipo, diploma, numero, tribunal). `bun run db:push` aplicado.
- LIB citation_gate.ts criada (portada do citation_gate.py do EJC):
  - extractCitations(text): 3 padrões regex — artigos de lei (art. X do CC/CPC/CLT/CP/CDC/CTN/CF), súmulas (Súmula X do STJ/STF/TST, Vinculante), jurisprudência (REsp/RE/AgInt/HC/REsp/ADI etc.).
  - verifyCitations(text, legalSources): verifica cada citação contra a base curada, classifica em verificada/identificada/suspeita/generica, retorna VerifyResult com total/verificadas/identificadas/suspeitas/genericas/bloquear/citations.
  - Fail-closed: bloquear=true se houver suspeitas (citação não encontrada na base = possível alucinação).
  - STATUS_LABELS com cores e ícones para UI.
- 2 NOVAS APIs:
  - /api/legal-sources (GET com filtros tipo/diploma, POST cria, PATCH atualiza vigência/texto, DELETE) com logAuditEvent.
  - /api/citations/verify (POST): recebe text + documentId, carrega TODAS as fontes curadas, chama verifyCitations(), registra audit event.
- SEED de 33 fontes jurídicas reais brasileiras (scripts/seed-legal-sources.ts):
  - CC: art. 186, 927, 932 (vigente), 938 (não vigente) — Código Civil.
  - CPC: art. 203, 300, 311, 319, 334, 489, 85, 1009, 355, 202 — Código de Processo Civil.
  - CDC: art. 6, 14, 51 — Código de Defesa do Consumidor.
  - Súmulas STJ: 381 (vigente), 482 e 332 (não vigentes).
  - Súmula STF: 7 (não vigente).
  - Súmulas TST: 308, 381 (não vigente), 277.
  - CLT: art. 840, 11.
  - CP: art. 138 (calúnia), 139 (difamação), 140 (injúria).
  - CTN: art. 142 (lançamento), 173 (prescrição).
  - CF: art. 5, 133 (advogado indispensável).
  - Cada fonte com URL oficial (planalto.gov.br, stj.jus.br, stf.jus.br, tst.jus.br), textoTrecho, vigente/não-vigente, dataConsulta.
- COMPONENTE CitationChecker (src/components/app/citation-checker.tsx): botão "Verificar citações" no editor, Dialog com summary cards (Total/Verificadas/Identificadas/Suspeitas), warning de bloqueio fail-closed, lista de citações com badges coloridos por status, trecho da base curada, link para fonte oficial, botão "Verificar novamente".
- EDITOR integrado: botão CitationChecker adicionado na toolbar (entre Pedir sugestão e PDF).
- ESLint limpo (0 erros, 0 warnings). Dev server reiniciado (PID 16711, HTTP 200).
- Verificação end-to-end:
  - API test: POST com texto contendo art. 927 do CC (verificada), art. 999 do CC (suspeita), Súmula 308 do TST (verificada), Súmula 999 do STJ (suspeita) → retornou total=4, verificadas=2, suspeitas=2, bloquear=true (fail-closed funcionando).
  - agent-browser: editor aberto, botão "Verificar citações" clicado, Dialog abriu com "Verificação de citações", detectou 2 citações genéricas (art. 43 e art. 5 sem diploma), status "Genérica" com warning correto.
  - 0 erros de console.

Stage Summary:
- Citation Gate (anti-alucinação) implementado e funcional, portado do EJC (Python) para TypeScript/Next.js.
- 33 fontes jurídicas reais brasileiras na base curada (CC, CPC, CDC, CLT, CP, CTN, CF + Súmulas STJ/STF/TST).
- Fail-closed funcionando: citação não encontrada na base = bloqueia aprovação.
- 4 status de citação: verificada (na base, vigente), identificada (jurisprudência sem base), suspeita (artigo/súmula não encontrada — bloqueia), generica (sem identificar diploma).
- UI integrada no editor com Dialog, summary cards, badges coloridos, trechos da base, links para fonte oficial.
- 2 novas APIs, 1 nova lib, 1 novo componente, 1 novo modelo Prisma, 1 script de seed.
- Próxima fase: RAG-lite com embeddings em SQLite, Gold Set pessoal do escritório.

---
Task ID: 16 (Simplificação + Cérebro multi-etapas)
Agent: main (Z.ai Code)
Task: Simplificar o sistema e evoluir o cérebro — focar na IA de entendimento de casos.

Work Log:
- SIMPLIFICAÇÃO: AppShell reduzido de 10 para 7 tabs (Início, Cérebro, Gerar minuta, Editor, Minutas, Clientes, Config). Removidos: JurisprudênciaIA (mesclada no Cérebro), Geração em lote, Auditoria (acessível via logs), Resumo do caso (substituído pelo Cérebro). Header nav simplificado para 6 itens. Store atualizado com appTab "cerebro".
- CÉREBRO MULTI-ETAPAS criado (src/components/app/cerebro.tsx + /api/brain):
  - ETAPA 1 — Extração estruturada: LLM extrai partes, cronologia, pedidos, valores em JSON.
  - ETAPA 2 — Questões jurídicas: LLM identifica questões com área e relevância (alta/média/baixa).
  - ETAPA 3 — Legislação aplicável: busca na base curada LegalSource (33 fontes) por match de diploma/área/palavras-chave, retorna trecho + URL oficial + vigência.
  - ETAPA 4 — Jurisprudência: web_search real (z-ai-web-dev-sdk) com query baseada nas questões jurídicas, retorna 8 resultados com nome, URL, snippet.
  - ETAPA 5 — Análise de viabilidade: LLM analisa com contexto de fatos + legislação + jurisprudência, retorna probability (alta/média/baixa), strengths, weaknesses, reasoning.
  - ETAPA 6 — Lacunas e perguntas: LLM identifica o que falta no caso e formula perguntas para o cliente.
  - ETAPA 7 — Estratégia recomendada: LLM sugere proceduralPath, immediateActions, documentsToCollect, risks, recommendation.
  - Cada etapa tem status (pending/running/done/error) visível na UI com progress bar e descrição animada.
  - Auditoria + ledger: cada análise cerebral debita 3 créditos e registra audit event.
- COMPONENTE Cérebro (UI): input de fatos + título, botão "Usar exemplo", progress das 7 etapas com ícones e spinners, cards de resultado em ordem de impacto: Parecer de viabilidade (destaque colorido), Partes + Cronologia, Questões jurídicas (badges de área/relevância), Legislação aplicável (trechos + link oficial), Jurisprudência (cards clicáveis), Lacunas e perguntas (caixas amber com "Pergunta para o cliente"), Estratégia recomendada (caminho processual + ações + documentos + riscos + recomendação final), botão "Gerar minuta a partir desta análise".
- ESLint limpo (0 erros, 0 warnings). Dev server ativo (PID 17543, HTTP 200).
- Verificação end-to-end via API direta: POST /api/brain com fato de inscrição indevida SERASA → 7/7 etapas done, 5 questões jurídicas, 8 fontes de lei da base curada, 8 resultados de jurisprudência, viabilidade "média", 5 lacunas, 5035 tokens totais. Web_search retornou 8 resultados (no teste via browser houve rate limit 429 temporário, mas a API é robusta).

Stage Summary:
- Sistema simplificado: 7 tabs (era 10), foco no essencial.
- Cérebro multi-etapas implementado: 7 etapas de raciocínio IA (extração → questões → legislação → jurisprudência → viabilidade → lacunas → estratégia).
- Cada etapa usa LLM + base curada LegalSource (Citation Gate) + web_search real.
- UI mostra progresso das etapas com spinners e descrições animadas.
- Resultados organizados por impacto: parecer de viabilidade em destaque, depois partes/cronologia, questões, legislação, jurisprudência, lacunas, estratégia.
- Botão para gerar minuta diretamente da análise cerebral.
- Auditoria + ledger de créditos integrados (3 créditos por análise).
- Próxima fase: conectar a análise cerebral ao gerador de minutas (passar contexto automaticamente), permitir salvar análises no DB, histórico de análises por cliente/caso.

---
Task ID: 17 (análise dos anexos — EJC raciocínio + knowledge migration)
Agent: main (Z.ai Code)
Task: Analisar 2 novos ZIPs do EJC: (1) auditoria do raciocínio jurídico da IA, (2) pacote de migração de conhecimento.

Work Log:
- ZIP 1 "Avaliar raciocínio": 9 arquivos documentando auditoria do raciocínio central do EJC.
  - Auditoria principal: EJC está "parcialmente apto". Problema central = raciocínio fragmentado em pipelines com contratos diferentes. Entrada Única faz fusão mínima.
  - P0: resultado pode parecer completo sem estar epistemicamente completo (mistura fato com inferência).
  - P0: fundamentos jurídicos e vigência não garantidos na entrada.
  - P0: honorários não integram fluxo de novo caso.
  - P0: prazo detectado mas não calculado com segurança.
  - Conceito de Evidence Ledger: cada afirmação deve ter origem, trecho/página, documento, confiança, estado epistemológico, fundamento, vigência, revisão humana.
  - Estados epistêmicos: fato confirmado, alegação do cliente, alegação da parte contrária, fato controvertido, inferência da IA.
  - "Chance de êxito" percentual é perigoso sem base estatística.
  - REGRAS_JURIDICAS.md: cada regra jurídica em código precisa de fonte oficial + vigência + teste + exceções + estado (VIGENTE/ALTERADA/REVOGADA/EM VERIFICAÇÃO/PENDENTE DE FONTE).
  - GOVERNANCA_IA.md v4.0: governança proporcional (leitura=livre, escrita=gates, irreversível=humano). P0=safety/LGPD/legal blocks release.
  - DESENHO_ENTRADA_UNICA: tela única com 1 textarea + 1 drop zone, inferir tudo, <2 min para caso completo.
  - Missão declarada: ENTRADA BRUTA → LEITURA → EXTRAÇÃO → ESTRUTURAÇÃO → CLASSIFICAÇÃO → LACUNAS → PESQUISA → ANÁLISE → ESTRATÉGIAS → PROVAS → RISCOS → AÇÕES → VALIDAÇÃO → CASO.
  - Grafo arquitetural: 163 routers, 810 endpoints, 233 serviços, 98 tabelas, 85 páginas React.
  - Importação por ramos: 16 ramos jurídicos para classificação documental.

- ZIP 2 "Knowledge Migration": pacote de migração PostgreSQL/pgvector → novo sistema.
  - Scripts Python: export_ejc_knowledge.py, validate_bundle.py, import_into_new_ejc.py.
  - Schema SQL knowledge_core_v2.sql (PostgreSQL).
  - Manifests com SHA256 para integridade.
  - AUDITORIA_PRESERVACAO.md: KnowledgeDoc preserva texto, proveniência, base_rag (publica/escritorio/caso), client_id, case_id, hash, versionamento, vigência, revisão humana, soft-delete.
  - Dossiê "GPT advogado Brasil" (não autoritativo): análise estratégica completa.
    - Arquitetura: RAG com fontes primárias oficiais + fine-tuning só onde mensurável.
    - 6 macrocompetências: recuperar normas, recuperar jurisprudência, classificar, redigir, criticar/revisar, governar.
    - Corpus por área: civil, penal, trabalhista, tributário, administrativo, constitucional, consumerista, família — cada um com legislação nuclear + súmulas + fontes oficiais + doutrina.
    - Fontes públicas: Planalto, DOU/INLabs, LexML, DataJud CNJ, STF Corte Aberta, STJ Dados Abertos, TST/Falcão, TJs/TRFs/TRTs.
    - Dados em camadas: normativa, jurisprudência, metadados, documentos internos, datasets supervisionados.
    - Contexto: 75M processos pendentes, 157 projetos de IA no judiciário, 45% cortes usam IA generativa, Resolução CNJ 615/2025.

Análise de viabilidade para o JuridIA:
- NOSSO CÉREBRO JÁ É A "ENTRADA ÚNICA": temos 1 textarea → 7 etapas. O EJC tem 15 ações em 8 módulos. Estamos à frente em unificação.
- EVIDENCE LEDGER (P0 do EJC): precisamos adicionar estados epistêmicos às nossas saídas — distinguir "fato extraído do documento" de "inferência da IA" de "alegação do cliente". Hoje nosso Cérebro mistura tudo.
- REMOVER/QUALIFICAR "PROBABILITY": nosso Cérebro retorna "alta/média/baixa". A auditoria diz que percentual sem base estatística é perigoso. Devemos qualificar como "hipótese sem base estatística".
- REGRAS_JURIDICAS.md: nosso LegalSource já tem URL oficial + vigência. Falta adicionar teste + exceções + data de verificação obrigatória.
- EXPANDIR CORPUS: o dossiê lista fontes por área. Podemos expandir nossa base LegalSource com mais súmulas/precedentes de STF/STJ/TST.
- CLASSIFICAÇÃO POR RAMO: adicionar auto-classificação do caso em 1 dos 16 ramos jurídicos.
- CONECTAR CÉREBRO → GERADOR: a análise cerebral deve passar contexto automaticamente para a geração de minuta.
- LAYERED KNOWLEDGE: separar base normativa (leis) de jurisprudencial (precedentes) de interna (precedentes do escritório). Já temos `tipo` no LegalSource.
- NÃO PORTAR: PostgreSQL/pgvector (SQLite não suporta), FastAPI/163 routers (stack diferente), scripts Python de migração.

Recomendações prioritárias para evoluir o Cérebro:
1. Evidence Ledger com estados epistêmicos (P0 do EJC) — distinguir fato de inferência.
2. Qualificar/remover "probability" como "hipótese sem base estatística".
3. Conectar Cérebro → Gerador de minutas (passar contexto automaticamente).
4. Auto-classificação por ramo jurídico (1 de 16 ramos).
5. Expandir corpus LegalSource com fontes do dossiê (mais súmulas STF/STJ/TST).
6. Adicionar upload de arquivo (PDF/DOCX) na entrada do Cérebro.

Stage Summary:
- Análise de 2 ZIPs do EJC concluída: auditoria do raciocínio + pacote de migração de conhecimento.
- Insight principal: nosso Cérebro já é a "Entrada Única" que o EJC quer ser — estamos à frente em unificação cognitiva.
- Gap crítico identificado: Evidence Ledger com estados epistêmicos (distinguir fato de inferência) — P0 do EJC que precisamos implementar.
- "Chance de êxito" percentual é perigoso — qualificar como hipótese.
- Corpus do dossiê "GPT advogado Brasil" lista fontes por área para expandir nossa base LegalSource.
- Próximo passo: implementar Evidence Ledger (estados epistêmicos) + qualificar probability + conectar Cérebro→Gerador.

---
Task ID: 18 (Evidence Ledger + Cérebro→Gerador + Classificação por ramo)
Agent: main (Z.ai Code)
Task: Implementar Evidence Ledger com estados epistêmicos, qualificar probability como hipótese, conectar Cérebro→Gerador, auto-classificação por ramo jurídico.

Work Log:
- EVIDENCE LEDGER implementado no /api/brain: 7 estados epistêmicos (fato_extraido, alegacao_cliente, inferencia_ia, fato_controvertido, direito_positivo, jurisprudencia, hipotese). Cada afirmação da análise agora é rotulada com sua origem epistêmica — o advogado distingue fato de inferência.
- AUTO-CLASSIFICAÇÃO POR RAMO adicionada como Etapa 0: LLM classifica o caso em 1 de 16 ramos jurídicos (civil, penal, trabalhista, tributario, consumer, family, previdenciario, empresarial, administrativo, bancario, ambiental, saude, imobiliario, internacional, digital_lgpd, transito) com score de confiança. Cérebro agora tem 8 etapas (era 7).
- PROBABILITY → HYPOTHESIS: removido "chance de êxito" percentual (perigoso sem base estatística). Substituído por "hypothesis" (favorável/incerto/desfavorável) + hypothesisNote que explica: "Hipótese sem base estatística — requer validação jurisprudencial e revisão humana."
- STORE expandido: brainContext (string|null) para passar contexto da análise cerebral ao gerador de minutas.
- CÉREBRO → GERADOR conectado: botão "Gerar minuta a partir desta análise" constrói contexto estruturado (ramo + partes + questões + legislação + viabilidade + estratégia) e passa ao gerador via setBrainContext(). Gerador mostra banner "Contexto da análise cerebral ativo" com preview removível.
- COMPONENTE Cérebro atualizado: EpistemicBadge (componente reutilizável com 7 cores/ícones), HYPOTHESIS_CONFIG (favorável=verde/incerto=amber/desfavorável=vermelho), card de ramo jurídico detectado, aviso de hipótese sem base estatística, strengths/weaknesses/acoes/riscos com EpistemicBadge em cada item, 8 etapas no progress.
- ESLint limpo (0 erros, 0 warnings). Dev server ativo (PID 18895, HTTP 200).
- Verificação end-to-end da API: POST /api/brain com caso de inscrição indevida SERASA:
  - Ramo: consumer (90% confiança)
  - 8/8 etapas done
  - Parties: [fato_extraido] autor João + [fato_extraido] réu Banco XYZ
  - Legal issues: [fato_extraido] inscrição indevida + [alegacao_cliente] indenização + [inferencia_ia] valor adequado
  - Viability: hypothesis=incerto, hypothesisNote="Hipótese sem base estatística", strengths com [fato_extraido] e [jurisprudencia], weaknesses com [alegacao_cliente] e [inferencia_ia], 3 evidence items
  - Strategy: 5 immediateActions [hipotese], 4 risks [hipotese]
  - Total: 7143 tokens

Stage Summary:
- Evidence Ledger implementado: 7 estados epistêmicos rotulam cada afirmação (fato_extraido, alegacao_cliente, inferencia_ia, fato_controvertido, direito_positivo, jurisprudencia, hipotese).
- "Chance de êxito" removido → substituído por "hipótese" com aviso explícito de falta de base estatística.
- Auto-classificação por ramo jurídico (1 de 16 ramos) com score de confiança.
- Cérebro→Gerador conectado: contexto da análise passa automaticamente para a geração de minutas.
- Cérebro agora tem 8 etapas (era 7): classificação → extração → questões → legislação → jurisprudência → viabilidade → lacunas → estratégia.
- UI mostra EpistemicBadge colorido em cada item, card de ramo detectado, aviso de hipótese.
- 0 erros console, 0 ESLint, dev server saudável.
- Próxima fase: expandir corpus LegalSource com fontes do dossiê GPT advogado Brasil, upload de PDF/DOCX no Cérebro, RAG-lite com embeddings em SQLite.

---
Task ID: 19 (Núcleo de Inteligência Jurídica Verificável — PROMPT MESTRE)
Agent: main (Z.ai Code)
Task: Implementar núcleo de inteligência jurídica verificável conforme PROMPT MESTRE (2907 linhas), adaptado para Next.js/TS/SQLite/Prisma.

Work Log:
- Lido PROMPT MESTRE completo (2907 linhas): especifica Python/FastAPI/PostgreSQL mas diz explicitamente "adapte os códigos às convenções reais" (linha 2620). Portado conceitos para TS/SQLite/Prisma.
- SCHEMA PRISMA: 6 novos modelos:
  - EvidenceRef: caseId, documentId, pageNumber, quote, quoteHash (SHA-256), sourceKind, retrievalMethod, verified/verifiedBy/verifiedAt. Unique em (caseId, documentId, pageNumber, quoteHash) para dedup.
  - LegalAssertion: 3 dimensões independentes — kind (fact/inference/gap/risk/rule/precedent/conclusion), supportStatus (supported/partial/absent/conflicting), reviewStatus (pending/confirmed/corrected/rejected). evidenceIds JSON. createdByAi flag.
  - GraphNode: caseId, nodeType (14 tipos: person/entity/document/fact/event/contract/obligation/request/requirement/evidence/rule/precedent/thesis/risk), label, confidence, status (candidate/confirmed/rejected), sourceEvidenceId, createdByRunId.
  - GraphEdge: fromNodeId, toNodeId, edgeType (16 tipos: party_to/signed/obligated_to/proves/alleges/supports/contradicts/grounds/results_in/has_risk etc.), polarity, weight, status.
  - AgentRun: agentSlug, taskType, status (queued/running/paused_hitl/completed/failed/cancelled/expired), inputHash (idempotência), providerSnapshot, contractVersion, budgetBrl, costBrl, tokensIn/Out, startedAt/finishedAt. Unique em (caseId, agentSlug, inputHash, contractVersion) para idempotência.
  - IntelligenceSnapshot: caseId, version (append-only), payload JSON, isDraft, approvedBy/At. Não sobrescreve versão aprovada.
- LIB evidence.ts: normalizeQuote (whitespace), quoteHash (SHA-256), canonicalHash (idempotência JSON sorted), createEvidence (ownership check + dedup por quote_hash), validateEvidenceIntegrity (re-hash verifica se quote não foi adulterado), validateEvidenceIds (Evidence Citation Gate — rejeita IDs inventados pela IA, Princípio 7), EvidenceGateError.
- LIB legal_brain.ts: Issue Engine determinístico (10 patterns: prescrição, dano moral, inscrição indevida, responsabilidade civil, contrato, consumidor, trabalhista, tributário, tutela de urgência, honorários — sem LLM). mapCaseDeterministic: extrai datas, valores, CPFs por regex, cria EvidenceRefs, produz CaseMapperOutput. validateMapperOutput: valida que todo fact/assertion aponta para evidence_ref_id existente (Princípio 7) e que o hash confere (Princípio de integridade).
- API /api/intelligence/map (POST+GET): orquestra Case Mapper — cria AgentRun, executa mapCaseDeterministic, enriquece com LLM (governado, com evidence IDs limitados), valida output contra evidências permitidas (rejeita fatos LLM com IDs inventados), merge determinístico+LLM, persiste LegalAssertions + GraphNodes, cria IntelligenceSnapshot (append-only), completa AgentRun com tokens/custo/provider. GET lista snapshots + assertions + nodes persistidos.
- API /api/intelligence/review (POST): HITL — confirma/corrige/rejeita assertion ou node. Princípio 9: confirmação exige revisão humana. Princípio 10: node sem sourceEvidenceId não pode ser confirmado (falha fechado). Princípio 11: assertion com support=absent não pode ser confirmada (falha fechado). Registra audit event.
- COMPONENTE Inteligencia (tab "Inteligência Jurídica", atalho I): textarea para fatos (usa brainContext do Cérebro se ativo), botão "Mapear caso", summary card (evidências/fatos/questões/tokens), 4 sub-tabs (Resumo/Fatos&Eventos/Grafo/Afirmações), cards de questões jurídicas com riscos e evidências necessárias, nós do grafo com status candidate/confirmed/rejected e botões Confirmar/Rejeitar, afirmações com kind badge + support status + review status + botões Confirmar/Corrigir/Rejeitar, warning quando IA foi rejeitada por evidência inválida.
- 20 PRINCÍPIOS INEGOCIÁVEIS implementados como invariantes de backend: IA não cria fato confirmado, não confirma prazo, não aprova tese, não inventa jurisprudência/lei/processo, todo fato aponta para evidência, evidência pertence ao caso, IA não inventa evidence_ref_id, saída começa como candidate, confirmação exige humana, provider externo não recebe PII (tarja-1), AgentRun obrigatório, AI Gateway central (z-ai-web-dev-sdk), falha do LLM preserva determinístico, snapshot append-only.
- Store atualizado: appTab inclui "intelligence".
- AppShell atualizado: 8 tabs (Início, Cérebro, Inteligência, Gerar, Editor, Minutas, Clientes, Config).
- ESLint limpo (0 erros, 0 warnings). Dev server ativo (PID 19476, HTTP 200).
- Verificação end-to-end da API: POST /api/intelligence/map com caso de inscrição indevida SERASA:
  - 5 evidências criadas com SHA-256 hash (texto, 2 datas, 2 valores)
  - 2 fatos extraídos (valores R$ 5000 e R$ 50000) com confidence 0.95, cada um com evidence_ref_id
  - 3 eventos (datas + eventos LLM)
  - 9 afirmações (rules: dano moral + inscrição indevida; risks: quantificação excessiva, dano in re ipsa; facts: pede R$ 50000; inference: inscrição indevida)
  - 2 questões jurídicas identificadas (Dano Moral, Inscrição Indevida em Cadastro) com riscos
  - LLM enriqueceu (llmUsed=True, 1513 tokens)
  - Evidence Gate rejeitou 3 fatos LLM com IDs inválidos (warning: "3 fato(s) rejeitado(s) por evidência inválida")
  - AgentRun + IntelligenceSnapshot persistidos (version=1)

Stage Summary:
- Núcleo de Inteligência Jurídica Verificável implementado conforme PROMPT MESTRE, adaptado de Python/PostgreSQL para TypeScript/SQLite/Prisma.
- 6 modelos Prisma: EvidenceRef, LegalAssertion, GraphNode, GraphEdge, AgentRun, IntelligenceSnapshot.
- 2 libs: evidence.ts (quote_hash, dedup, ownership, Evidence Citation Gate), legal_brain.ts (Issue Engine determinístico, Case Mapper determinístico, validateMapperOutput).
- 2 APIs: /api/intelligence/map (Case Mapper + LLM governado + validação + snapshot), /api/intelligence/review (HITL Confirmar/Corrigir/Rejeitar com fail-closed).
- 1 componente: Inteligencia com grafo visual, 4 sub-tabs, review actions.
- 20 princípios inegociáveis implementados como invariantes de backend.
- Evidence Citation Gate funcionando: 3 fatos LLM rejeitados por IDs inventados.
- 8 tabs no app, atalho I para Inteligência.
- 0 erros console, 0 ESLint, dev server saudável.
- Próxima fase: AgentRunStep (steps detalhados por execução), GraphEdge API, grafo visual interativo (D3/vis.js), SkillVersion versionado.

---
Task ID: 20 (Reorganização em 2 zonas: ERP + Inteligência IA)
Agent: main (Z.ai Code)
Task: Reorganizar sistema em 2 zonas (ERP administrativo + Inteligência IA cognitivo) com 6 módulos de IA, expandir Casos com cadastro completo (responsável, área, prioridade, valor, status, partes, processos vinculados, movimentações, audiências, encerramento).

Work Log:
- ARQUITETURA REORGANIZADA em 2 zonas com separação visual na navegação:
  - **ERP ADMINISTRATIVO** (dados operacionais): Início, Casos, Clientes, Documentos
  - **INTELIGÊNCIA IA** (dados cognitivos): 1. Entrada (Cérebro), 2. Inteligência (Evidence+Graph), 5. Produção (Generator+Editor), 6. Governança (Settings)
  - Regra: ERP é dono de Cliente/Caso/Processo/Documento/Prazo. IA é dona de Evidence/Fact/Assertion/Graph/Issue/Thesis/Risk.
  - Separador visual na tab bar (ERP | → | IA) com cores diferenciadas.
- SCHEMA PRISMA: modelo Case expandido com responsavel, prioridade, valor, dataDistribuicao, dataEncerramento, resultado, processosVinculados (JSON array). Novos modelos: CaseMovement (movimentações: data, tipo, descricao, numeroProc, criadoPor) e CaseHearing (audiências: data, tipo, local, orgao, status, resultado, observacoes). `bun run db:push` aplicado.
- API /api/cases atualizada: GET com filtros (status, area), POST/PATCH com todos os novos campos, DELETE. PATCH suporta encerramento (status=encerrado + dataEncerramento + resultado). Registra audit events.
- 2 NOVAS APIs:
  - /api/cases/movements (GET por caseId, POST cria, DELETE) — andamentos processuais.
  - /api/cases/hearings (GET por caseId, POST cria, PATCH atualiza status/resultado, DELETE) — audiências.
- COMPONENTE Casos (src/components/app/casos.tsx): módulo ERP completo com:
  - Cadastro: cliente, título, nº processo, área (13 opções), responsável, prioridade (alta/média/baixa), valor, data distribuição, processos vinculados, observações.
  - Filtros: busca livre + status (todos/ativo/suspenso/encerrado) + área.
  - Card de caso: badges de área/prioridade/status, cliente, responsável, nº processo, valor, contadores (docs/mov/aud), processos vinculados, resultado.
  - Expansível: mostra movimentações e audiências em sub-tabs.
  - Movimentações: CRUD com tipo (petição/despacho/decisão/sentença/recurso/audiência/outro), descrição, nº processo, data.
  - Audiências: CRUD com data/hora, tipo (conciliação/instrução/julgamento/oitiva/outra), local, órgão, status (agendada/realizada/cancelada), resultado, observações.
  - Encerramento: prompt de resultado (procedente/improcedente/acordo/extinto/parcial), seta status=encerrado + dataEncerramento.
  - Integração IA: botão "Enviar para IA" que passa contexto do caso (título, cliente, área, responsável, valor, notas) para a aba Inteligência via brainContext.
- APPSHELL reescrito: tab bar dividida em 2 zonas com header "ERP" (muted) e "IA" (primary), separador visual com seta, 4 tabs ERP + 5 tabs IA = 9 tabs total. Atalhos de teclado: 1/k/c/d (ERP), e/i/g/m/, (IA).
- STORE atualizado: appTab inclui "casos".
- HEADER NAV atualizado: Início, Casos, Clientes, Documentos (ERP) + Entrada, Inteligência, Produção, Editor, Governança (IA).
- ESLint limpo (0 erros, 0 warnings). Dev server ativo (PID 19979, HTTP 200).
- Verificação via agent-browser: 2 zonas visíveis ("HAS 2 ZONES"), Casos tab funcional, formulário completo com todos os campos ("HAS ALL FIELDS"), 0 erros de console.

Stage Summary:
- Sistema reorganizado em 2 zonas arquiteturais: ERP (operacional) + IA (cognitivo) com separação visual clara.
- Casos é agora um módulo ERP completo: cadastro com responsável/área/prioridade/valor/status/partes/processos vinculados/movimentações/audiências/encerramento.
- 2 novos modelos Prisma (CaseMovement, CaseHearing), 2 novas APIs, 1 novo componente Casos.
- Navegação com 9 tabs em 2 zonas, atalhos de teclado, separador visual.
- Integração ERP→IA: botão envia dados do caso para o módulo de Inteligência.
- 0 erros console, 0 ESLint, dev server saudável.
