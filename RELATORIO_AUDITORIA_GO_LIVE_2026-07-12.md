# RELATÓRIO DE AUDITORIA E CONSOLIDAÇÃO PRÉ-GO-LIVE — EJC

**Data:** 2026-07-12 · **Branch:** `claude/system-audit-testing-9bilfd` · **Base:** `main` (merge do PR #218)
**Objetivo:** auditoria completa do sistema (links, funcionalidades, segurança, testes), correção de tudo que era necessário e consolidação para entrada em operação em 2026-07-13.

---

## 1. Metodologia

Quatro fases, executadas por agentes especialistas em paralelo:

1. **Auditoria** — 4 frentes simultâneas: teste funcional no navegador (Playwright, 41 rotas), suíte automatizada completa (pytest + Alembic + tsc + vitest + build, replicando o CI com Postgres/pgvector real), auditoria de segurança pré-produção e consistência estática frontend↔backend.
2. **Correção** — todos os defeitos delegados a agentes de backend/frontend, com suíte verde exigida por commit.
3. **Reverificação** — code review do diff completo, re-auditoria de segurança focada nas mudanças e verificação ponta a ponta no navegador dos fluxos corrigidos; novos achados corrigidos em lote final.
4. **Consolidação** — este relatório, push e PR.

Adicionalmente, a **Bíblia de Conhecimento EJC v2** foi tratada e ingerida na base de conhecimento RAG (seção 5).

## 2. Estado encontrado (auditoria)

- **Consistência estática:** nenhuma quebra — todas as rotas/links do frontend resolvem, todas as chamadas de API batem com endpoints reais, zero resíduo funcional de "licitação". Apenas itens cosméticos (páginas órfãs, docs de env).
- **Suíte:** 1.844 testes passando; 3 falhas eram contaminação de ambiente (`.env` local), não bugs. 1 bug real latente achado por lint: endpoint `POST /ai/detectar-prazos` chamava função inexistente (500 garantido).
- **Navegador:** 41 rotas varridas, CRUDs completos exercitados, zero 5xx. 7 defeitos (2 altos: `/assinaturas` quebrada; leads do CRM sumindo do funil).
- **Segurança:** postura sólida, **nenhum bloqueador de código**; bloqueadores apenas operacionais (checklist na seção 6) e melhorias priorizadas (todas aplicadas nesta consolidação).

## 3. Correções aplicadas (7 commits)

### Funcionais
- **`/assinaturas` reconstruída** — crash na listagem (2 causas: `signatarios` ausente na API + enum de status divergente) e formulário que nunca funcionava (contrato real: `document_id`+`client_id` com selects de cliente/documento); backend passou a retornar `signatarios` na listagem; toasts de erro em fluxos antes silenciosos (criação, assinatura, download de PDF de peças).
- **CRM/funil de leads** — `ClientCreate` agora aceita `status`/`etapa_funil`/`origem_lead`/`area_interesse` (migration `087`); lead criado aparece no funil, move de etapa e não polui a lista de clientes ativos.
- **Peças jurídicas preservam acentuação** — a normalização que convertia tudo a ASCII ("Petição"→"Peticao") foi corrigida: acentos e símbolos jurídicos (§ º ª) preservados no armazenamento e na exportação (WeasyPrint/python-docx suportam UTF-8); reparo de mojibake das formas latin-1 **e** cp1252 restaurando o caractere correto.
- **`POST /ai/detectar-prazos` implementado** — função inexistente substituída por implementação no padrão dos endpoints vizinhos (sanitização LGPD → gateway → AILog HITL, parse fail-safe que nunca inventa prazo), com validação de existência/acesso ao caso antes do custo de IA.
- **Google Drive indisponível → 503 limpo** (antes 500) em upload/download/delete; delete não deixa mais arquivo órfão no Drive.
- **UX:** feedback "senha alterada" no login após troca obrigatória; tour de onboarding pausa quando um modal abre; contraste do painel do dashboard; input de avatar acessível.

### Segurança
- **Refresh tokens:** detecção de reuso (reuso de token revogado → revoga todas as sessões + auditoria `REFRESH_REUSE`), com **janela de graça de 60s** para corrida benigna de multi-abas (migration `088`); fluxos manuais de auth checam `deleted_at`.
- **2FA/TOTP:** segredo cifrado com Fernet (migration `086`, fallback a legado + re-cifragem oportunista); resiliente a rotação da chave PII (401 controlado, nunca 500); `totp_desativar` com bloqueio anti-brute-force em chave própria; passo "TOTP obrigatório" não consome mais o orçamento de brute-force do login legítimo (contador separado, teto 20/15min).
- **Uploads:** validação de extensão + magic bytes + MIME derivado do servidor também no upload ao Drive (fecha XSS armazenado); `Content-Disposition` sanitizado (RFC 5987, anti header-injection).
- **NFS-e:** leitura (consulta/PDF/XML) restrita a `superadmin/admin/socio/financeiro` (expunha honorários e CPF/CNPJ a qualquer advogado).
- **Config:** `SECRET_KEY` exige ≥32 chars em produção; alias canônico `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON`; `.env.example` completado.
- **Dependências:** `fastapi 0.116.2` + `starlette 0.47.3` (CVE-2024-47874, CVE-2025-54121) + `python-multipart 0.0.20` (CVE-2024-53981) + `jinja2 3.1.6`; removidos `python-jose`/`passlib`/`ecdsa` (mortos, com CVEs).
- **Webhook Z-API:** lookup de cliente filtrado no SQL (antes carregava a tabela inteira de clientes por mensagem).
- **LGPD/privacidade:** fonte Inter auto-hospedada (elimina envio de IP ao Google em toda página).

### Higiene
- Ruff safe-fix (~100 correções F401/F541), páginas órfãs removidas (`Agenda.tsx`, `VictoryVault.tsx`), suíte blindada contra `.env` local, comentários de CVE corrigidos, documentação de rate-limit por processo (não escalar `--workers` sem Redis).

## 4. Reverificação final (veredito)

| Gate | Resultado |
|---|---|
| `alembic upgrade head` (Postgres+pgvector vazio) | ✅ limpo, head `088`, idempotente |
| pytest backend (suíte completa, RUN_DB_TESTS=1) | ✅ **1.861 passed, 0 failed** |
| tsc (typecheck) | ✅ 0 erros |
| vitest | ✅ 57 passed |
| `npm run build` | ✅ |
| Fluxos no navegador (login/2FA, troca de senha, CRM, casos, prazos, peças, documentos, financeiro, assinaturas, NFS-e RBAC, refresh reuse, smoke 10 rotas) | ✅ todos exercitados e aprovados |

Re-auditoria de segurança do diff: **apto para operação** — nenhuma correção abriu vulnerabilidade nova; achados residuais aplicados no lote final.

## 5. Base de conhecimento — Bíblia EJC v2

**350 documentos** ingeridos no pipeline oficial do RAG (`upsert_documento`, dedup por `chave_origem`, versionamento, chunking 1200/150): 84 situações jurídicas (SIT-01..84), 221 modelos de peça (Vol. I–V), 40 docs de governança e 5 instruções de uso.

Tratamento para IA: todo doc com `extra.ficticio=true`, aviso "[MATERIAL DIDÁTICO FICTÍCIO]" no primeiro chunk e "(fictício)" no título; categorias `referencia_interna`/`modelo_documento_juridico` **fora dos filtros de jurisprudência/precedente real**; confiança `media` (reclassificável na Curadoria). Corpus versionado em `backend/seeds/biblia_ejc/`, seed idempotente validado em Postgres real (350 docs, 1.304 chunks; 2ª execução: "350 inalterados").

**Em produção:** `python scripts/seed_biblia_ejc.py` dentro do container backend (vetoriza inline com `EMBEDDINGS_ENABLED=true`; alternativa `--sem-vetores` + `scripts/vetorizar_documentos.py`).

## 6. Checklist operacional para o go-live (fazer na VPS antes/durante o deploy)

1. **Conferir o `.env` real:** `SECRET_KEY` forte (≥32 chars — o boot agora bloqueia curtas), `POSTGRES_PASSWORD` forte, `ADMIN_PASSWORD` não-placeholder e senha do superadmin já trocada, `NFSE_ENABLED=false` até o contador confirmar alíquota/regime.
2. **Deploy pelo script gated** (com backup antes das migrations) — evitar `docker compose up` cru (`RUN_MIGRATIONS=1` aplicaria migrations sem backup). Migrations novas desta entrega: `086`, `087`, `088` (aditivas).
3. **Não subir uvicorn com `--workers N`** — anti-brute-force e slowapi são por processo (documentado em `entrypoint.sh`/`docker-compose.yml`).
4. **Rodar o seed da Bíblia** (item 5) e conferir `fontes_ingestao.biblia_ejc = sucesso/350`.
5. Smoke pós-deploy: `/api/health`, login, uma rota de cada família do menu.

## 7. Pendências conhecidas (não bloqueantes, pós-go-live)

- `cryptography` ≥44.0.1 quando conveniente (CVE-2024-12797, relevância baixíssima no uso atual) e revisão do `langchain 0.2.5` (defasado; CVEs exigem uso de features não utilizadas).
- Cadeia dev do frontend (`esbuild→vite≤6.4.2→vitest 2.1.9`) tem advisories — só afeta ambiente de desenvolvimento; fix exige vite 8 (breaking).
- Débito de formatação prettier (~61 arquivos) e baseline ruff (199 avisos estilísticos) — cosmético.
- Access token com TTL de 8h é stateless (sobrevive à revogação de refresh até expirar) — avaliar redução futura.
- Dashboard não conta casos em `triagem` como "ativos" enquanto o honorário do caso já aparece em "A receber" — comportamento a validar com o escritório.
- Uploads `.txt` não têm magic bytes verificável (mitigado por download sempre `attachment`).
- Retenção de `refresh_tokens`: se um job futuro expurgar linhas antes do `exp` (7 dias), a detecção de reuso puniria usuários legítimos — documentado para quem criar o job.
