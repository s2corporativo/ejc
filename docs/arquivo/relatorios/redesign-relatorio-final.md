# Relatório Final de Entregáveis — Redesign EJC

**Data:** 2026-07-03
**Branch:** `ui/fase-3-tokens` (13 commits sobre o merge-base `c97392f` do `main`)
**Base:** `C:\Users\User\ejc-canonical` (espelho de produção + segurança). Não mergeado nem deployado — aguarda revisão humana.
**Verificação global:** `tsc --noEmit` limpo, `vite build` de produção OK (7s), `py_compile` OK em todos os arquivos tocados, cadeia Alembic com head único **058**, 555 endpoints (era 534).

Este documento cobre os 9 entregáveis obrigatórios da Seção 14 do prompt.

---

## 1. Relatório de mapeamento/auditoria inicial (Etapa 1)
Entregue em [docs/auditoria-ejc-pre-redesign.md](auditoria-ejc-pre-redesign.md). Produzido por 4 agentes em paralelo (frontend, backend, banco, gap analysis) + grafo Graphify, **antes de qualquer alteração de código**. Confirmou: Graphify existe e foi usado; 73 páginas, 534 endpoints/108 routers, 42+ modelos, head Alembic 056.

## 2. Telas analisadas e problemas encontrados
Inventário completo na auditoria inicial (seções 1–3). Problemas de frontend catalogados (F1–F6). Destaques corrigidos: **F1 (XSS)** em MemoriaInstitucional.tsx — eliminado; literais de cor legados — 0 remanescentes (Fase 3 visual). Responsividade: mobile-first confirmado em todas as páginas (hamburger + overlay no Layout; grids `grid-cols-1 sm:2 md:3`).

## 3. Alterações efetivamente aplicadas (por fase)

**Fase 2 — Design system**
- Correção de XSS (MemoriaInstitucional.tsx → `<Markdown>` seguro; 0 `dangerouslySetInnerHTML` no `src/`).
- Escala tipográfica (`display`, `caption`, `fontFamily.mono`); animação `slide-in-right`.
- Kit UI ampliado (retrocompatível): `Modal` (size/footer/Esc), `ConfirmModal` (com `typeToConfirm`), `Drawer`, `Alert`, `THead/TR/TH/TD`. Documentado em [docs/design-system.md](design-system.md).

**Correção crítica pré-fases** — routers órfãos `ia_extra.py` e `honorarios_oab.py` registrados no `main.py`: **6 endpoints que o frontend chamava estavam em 404 na produção** (`/ai/gerar-minuta`, `/ai/resumir-texto`, `/ai/traduzir-andamento`, `/ai/pesquisar`, `/ai/sugestao-honorarios`, `/honorarios-oab/estimar`).

**Fase 3 — Módulos funcionais**
- Migração **057**: tabelas `module_help`, `area_modulos_mapping`, `document_types_master`, `tabela_oab_honorarios` + modelos + seed (14 tipos de documento, matriz de 16 áreas × módulos reais, 3 ajudas exemplo).
- Ajuda contextual (R1): `/module-help` (CRUD + busca) + `HelpButton` com Drawer por rota no Layout.
- Arquivar/excluir caso (R2): `POST /cases/{id}/arquivar` e `/desarquivar`; `DELETE` com **motivo obrigatório** e **bloqueio 422** (prazo pendente / honorário aberto / peça protocolada → só arquivamento). UI: ConfirmModal com digitação de "EXCLUIR", aba Arquivados.
- Classificação de documentos (R3): `GET /documents/tipos`, `POST /documents/sugerir-tipo` (IA sugere do master, **confirmação humana obrigatória**), upload aceita **XML/NF-e** com bloqueio XXE, validação de tipo. UI: seletor por categoria + card de sugestão.
- Extração com origem/confiança (R4): `campos_v2` com `{valor, trecho_origem, confianca}` + verificação de origem no texto; UI de revisão editável antes de gravar.
- Matriz área→módulos (R6): `/area-modulos` configurável.

**Fase 4 — Motor IA e configurabilidade**
- Intake (R5): `POST /intake/casos/{id}/analise-completa` — área + teses (**só do banco, com fonte**) + estratégia + honorários OAB (3 camadas, **nunca inventa valor**) + módulos sugeridos; tudo **rascunho com AILog** e ressalva OAB Prov. 205/2021.
- Endpoint fantasma `/teses/busca-avancada` implementado (a Biblioteca.tsx já o chamava).
- Checklist de conversão (R8/§10): `GET .../converter-judicial/checklist` (8 verificações) + `POST` **bloqueante** (422 com pendentes). UI: modal com as 8 verificações.
- Workflow por área (R9): `POST /workflow/casos/{id}/aplicar-padrao` + **job diário de SLA 07h30** em dias úteis forenses com alerta de véspera idempotente. Migração **058** (valor `atrasado` no enum).

**Fase 5 — Export e Diário Oficial**
- DOCX (R7): `docx_service.gerar_docx` (Times 12pt, margens ABNT, cabeçalho/rodapé institucional); `GET /legal-docs/{id}/exportar-docx` + `POST /export/docx`. View de impressão (`@media print` + botão nas Peças).
- Diário Oficial/DJEN (R10): vinculação automática publicação→caso por nº CNJ (marcada para conferência humana) + notificação ativa; `POST /intimacoes/{id}/sugerir-prazo` (heurística por tipo, **cita artigo só quando casou, nunca inventa**, não cria o prazo). Jobs de captura já existiam (DOU 06:00, DJEN 06:30).

**Fase 6 — Auditoria de segurança**: 5 IDORs CRÍTICOS corrigidos (ver §9).

## 4. Documentação do design system final
[docs/design-system.md](design-system.md) — paleta com hex e papéis, tipografia, catálogo de componentes com props e exemplos, regras de uso (IA sempre via AIResponse/Markdown; nunca `dangerouslySetInnerHTML`), esqueleto de tela nova.

## 5. Rotas testadas (frontend e backend)
- **Backend**: `py_compile` OK; 3 novos routers registrados no `main.py`; ordem de rotas conferida (`/tipos`, `/sugerir-tipo`, `/busca-avancada`, `/module-help` antes dos `/{param}`).
  - ✅ **RESOLVIDO (07-03) — suíte pytest rodada de verdade:** contra `pgvector/pgvector:pg16` (mesmo do CI `db-validation`), com `alembic upgrade head` aplicando toda a cadeia até o head único **064_drive_columns** e `RUN_DB_TESTS=1`: **126 passed** (inclui os testes ROW-LEVEL de RAG/anonimização/PII e os novos de arquivamento). A cadeia de migrations do redesign (062→063→064, encadeada após o head real 061) foi validada num Postgres real, não só por inspeção.
  - ✅ **RESOLVIDO (07-03) — cobertura de arquivar/excluir portada:** `tests/test_casos_dblevel.py` (5 testes) substitui o `test_casos.py` API-level removido na integração, agora no padrão DB-level da suíte (arquivar/desarquivar, 409 em já-arquivado, 422 sem motivo, 422 com prazo pendente, soft-delete sem pendências). `tests/test_documento_service.py` foi reescrito para travar o invariante LGPD real (extração de PII fixada no Ollama local + fail-closed), em vez do "mascarar antes" da frente rejeitada na merge.
- **Frontend**: `tsc --noEmit` limpo + `vite build` de produção OK (code-splitting preservado).

## 6. Módulos revisados
Casos, Prazos, Documentos, Peças, Teses/Biblioteca, Workflow, Intimações, Diário Oficial, IA/Intake, Ajuda, Conversão. Revisão de segurança independente por agente `code-reviewer` sobre o diff completo.

## 7. Cobertura de responsividade
Mobile-first confirmado (breakpoints `sm/md/lg` em todas as páginas; sidebar com hamburger+overlay). Componentes novos (Modal/Drawer/Table com `overflow-x-auto`) são responsivos por construção. **Pendente de teste visual** em 375/768/1280 com dev server (não há preview neste ambiente) — recomendado antes do deploy.

## 8. Pendências técnicas remanescentes
1. ✅ **RESOLVIDO (07-03) — PII sem sanitização (LGPD):**
   - `documento_service.extrair_e_analisar` agora roda **só no modelo local (Ollama)** via `provider_override="ollama"` — sem fallback para o Groq externo; falha fechado (mensagem clara) se o Ollama estiver indisponível. O texto bruto (com PII) nunca sai para a nuvem. **Requer Ollama habilitado em produção** para a extração funcionar.
   - `cases.py assistente-estrategico` agora aplica `sanitizar_pii` ao contexto (nomes de partes, nº do processo) e à demanda antes de enviar à IA.
2. ✅ **RESOLVIDO (07-03) — Colunas Drive:** migração **059** cria `documents.drive_file_id/drive_link` (+ index) e `cases.drive_folder_id`; o SQL do router foi alinhado às colunas reais (`titulo/filename/filepath/size_bytes/uploaded_by`), corrigindo também a violação de NOT NULL que impedia o INSERT do Drive. Os endpoints Google Drive agora funcionam.
3. ✅ **RESOLVIDO (07-03) — Tabela OAB/MG estruturada:** a partir do PDF institucional fornecido, `app/seeds/oab_honorarios_seed.py` popula `tabela_oab_honorarios` com **311 itens em 21 áreas**. Extração **segura**: só entraram itens em que código e valor estão na mesma linha física do PDF (associação inequívoca) — os ~90 itens em layout intercalado de 2 colunas ficaram **de fora, para entrada manual** (nunca se adivinhou valor). Valores/percentuais verbatim; `observacoes` guarda o trecho de origem para auditoria; `fonte` cita o documento; `vigencia_inicio` ficou nullable (a edição não consta no PDF — não se inventou data). O intake passa a exibir o honorário de referência OAB por área. Rodar `python -m app.seeds.oab_honorarios_seed` após o `alembic upgrade head`.
   - **Entrada manual pendente:** ~90 itens de layout intercalado (ex.: seção Recursos 9.2/9.4/9.5, e partes de Família/Previdenciário/Imobiliário) não foram importados por segurança; conferir no PDF e cadastrar pela tela de administração.
4. **Fila assíncrona não persistente (B4):** upload usa `BackgroundTasks` (perde tarefa em restart). Migrar para Celery/Redis se o volume exigir.
5. **Deploy:** rodar `alembic upgrade head` (aplica 057→058→059) **antes** de subir o backend (o enum `atrasado` precisa existir antes do 1º ciclo do job de SLA; as colunas Drive antes de qualquer chamada `/documents/drive/*`). Popular via `python -m app.seeds.redesign_seed` (ajuda/matriz/tipos de documento) e `python -m app.seeds.oab_honorarios_seed` (311 itens da tabela OAB/MG). Nota: a migração 057 foi ajustada (`vigencia_inicio` nullable) — como a tabela ainda não foi criada em produção, o `upgrade head` a cria já correta.

## 9. Recomendações finais priorizadas por criticidade

**Crítico (feito nesta branch):** ✅ 5 IDORs de ownership corrigidos — `workflow.py` (GET/iniciar/avancar/concluir) e `teses.py` (casos/{id}, vincular-caso) agora chamam `verificar_acesso_caso`; `intimacoes.py` escopado por `advogado_id`. Sem esses gates, um advogado via/manipulava dados de casos de outros clientes (sigilo EOAB art. 25 / LGPD).

**Alto:** resolver a pendência 1 (PII → roteamento local) antes de expor o intake/extração a documentos reais de clientes; rodar a suíte pytest no container.

**Médio:** pendência 2 (Drive); popular tabela OAB (pendência 3); auditar `Depends(get_current_user)` nos ~100 routers restantes fora do escopo do redesign.

**Baixo:** consolidar navegação das 4 superfícies de IA (`/ia`, `/assistente-ia`, `/inteligencia`, `/ferramentas-ia`); remover artefatos `.bak`/experimentais; adicionar Storybook.

---

### Compliance com as regras absolutas (CLAUDE.md + prompt)
- ✅ Nenhum dado/lei/jurisprudência/valor OAB **inventado** (tabela OAB ficou sem seed por não haver fonte; teses só do banco; artigos de prazo só quando a heurística casou).
- ✅ Nenhum arquivo deletado sem confirmação; nada de `.env`/produção/banco tocado; nada commitado no `main`.
- ✅ Toda saída de IA marcada como **rascunho sujeito a revisão** (OAB Prov. 205/2021); AILog em todas as chamadas.
- ✅ Sigilo entre clientes reforçado (IDORs fechados).
- ✅ Não regressão: só adições e correções; componentes/props existentes preservados; endpoints legados mantidos.
