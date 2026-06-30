# Changelog — EJC (Ecossistema Jurídico Clovis)

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/).
Datas em AAAA-MM-DD.

## [Não lançado] — 2026-06-14

### Segurança
- **GZip**: `GZipMiddleware` adicionado (ordem CORS → GZip → Auth); respostas JSON comprimidas (~70-85% menores).
- **2FA obrigatório** para perfis `admin`/`superadmin` (flag `REQUIRE_2FA_FOR_ADMIN`, default `true`); login sinaliza `must_enable_2fa` e a UI força o cadastro.
- **CSP** adicionada ao Nginx do host (`script-src 'self'` — script do service worker externalizado para `public/sw-register.js`); `Permissions-Policy` incluída. HSTS, X-Frame-Options, X-Content-Type-Options e TLS 1.2/1.3 já existiam.
- **gzip no Nginx** (host e container) para assets estáticos.
- Headers básicos (`X-Content-Type-Options`, `X-Frame-Options`) no Nginx do container frontend.

### Performance / Confiabilidade
- **WeasyPrint assíncrono**: geração de PDF movida para thread do executor (não bloqueia mais o event loop). Callers atualizados: `legal_docs`, `clients` (LGPD), `dashboard` (relatório mensal).
- **Retry com backoff** (`tenacity`, 3 tentativas) nas integrações **DataJud** e **DJEN** para erros transitórios.
- **Lazy loading** das páginas no frontend (React.lazy + Suspense): bundle inicial reduzido de ~363 KB → ~255 KB (gzip 105 → 84 KB); cada página vira chunk sob demanda.
- **Índice GIN trigram** (`pg_trgm`) em `knowledge_chunks.conteudo` — acelera o fallback ILIKE da busca RAG (migração `009`).

### Funcionalidades
- **Busca global** com atalho `Ctrl/⌘ K` (command palette): clientes, casos e peças, respeitando o escopo do perfil (`/api/search`).
- **Exportação CSV**: clientes, casos e honorários (`/api/export/*.csv`, separador `;`, BOM p/ Excel pt-BR).
- **Portabilidade LGPD em JSON** (art. 18, V): `/api/clients/{id}/dados-lgpd.json` (complementa o relatório PDF do art. 18, II).
- **Alerta de prescrição**: job semanal notifica o responsável sobre casos com prescrição em ≤ 90 dias.
- **Suspensões de prazo por tribunal** (sessão anterior): módulo isolado + simulador de prazo ciente de suspensões; paginação adicionada à listagem.

### Manutenção
- Logo removido do código-fonte: `app/services/_logo_b64.py` agora carrega de `app/assets/logo.png` (antes ~102 KB de base64 embutido).
- Migração para Pydantic V2: `class Config` → `SettingsConfigDict` em `core/config.py`.
- `tenacity` adicionado ao `requirements.txt`.
- Suíte de testes (`pytest`) mantida verde (17 testes).

### Notas de implantação
- Copiar `frontend/public/logo.png` real para o servidor antes do deploy (já presente no repositório).
- Migrações pendentes: `alembic upgrade head` aplica `008` (suspensões) e `009` (índice GIN RAG; cria extensão `pg_trgm`).
- Revisar a CSP caso novos domínios externos (CDNs, APIs) sejam adicionados ao frontend.

### Diferido (requer decisão arquitetural — não incluído)
- Multi-tenant (SaaS) — exige `tenant_id` em todas as tabelas + isolamento por middleware.
- Integração real de assinatura digital (DocuSign/ClickSign/ICP-Brasil) — depende de conta/credenciais externas.
- Notificações em tempo real (WebSocket/SSE) — polling de 60 s atende ao MVP.
- Reconstrução completa do Portal do Cliente (mensageria, aprovação de acordo, pagamento).
- IA híbrida (Anthropic para peças de alto risco + Groq para tarefas leves) — decisão de custo/risco OAB.

## [Camada 3 — Precedentes Internos] 2026-06-15
### Adicionado
- `case_context.py`: agregador de dossiê consolidado (interliga cliente, ramo
  especializado, prazos, honorários, peças e histórico) — sanitização LGPD.
- `GET /api/ai/dossie/{case_id}`: expõe o contexto que a IA enxerga (transparência HITL).
- IA carrega o dossiê automaticamente quando `case_id` é informado.
- Pós-mortem de encerramento agora gera PRECEDENTE INTERNO no RAG, incluindo o
  dossiê completo do ramo (não só a estratégia textual), com ingestão idempotente.
- Busca dedicada de precedentes internos na análise de caso (categoria
  `precedente_interno`, modo OR para relevância parcial).
### Técnico
- `buscar_contexto_rag` ganhou parâmetro `modo_or` (casamento tolerante de termos).

## [Frontend dos Ramos + Embeddings + Polimento] 2026-06-15
### Adicionado
- Frontend dos 6 ramos especializados: `ramosConfig.ts` (config declarativa) +
  `RamoBase.tsx` (página genérica). Rota `/ramos/:slug` e 6 itens de menu.
  Cada ramo tem listagem, criação e calculadoras com resultado ao vivo (HITL).
- Botão "Ver dossiê" na IA: seletor de caso vinculado + visualização do contexto
  consolidado que a IA recebe (transparência LGPD/HITL).
- Busca SEMÂNTICA via pgvector (embeddings): `buscar_contexto_rag` usa operador
  `<=>` (cosine) quando EMBEDDINGS_ENABLED=true; fallback textual caso contrário.
### Melhorado
- Comentários de categoria RAG atualizados (precedente_interno; peca_escritorio
  marcada como legada).
### Técnico
- RamoBase code-split: 20.7KB (gzip 6.75KB) — ícones importados individualmente.
- Tailwind: cores de borda em mapa estático (evita purga de classes dinâmicas).

## [Dedup CRUD + Deploy Embeddings] 2026-06-15
### Refatorado (sem mudança de comportamento)
- ramos.py: lógica CRUD repetida dos 6 ramos extraída para helpers compartilhados
  (_crud_listar / _crud_atualizar / _crud_remover). Cada rota permanece EXPLÍCITA
  e auditável, delegando em 1 linha. Superfície de rotas byte-idêntica (41 rotas,
  validada por diff). Arquivo: 1101 → 967 linhas. Whitelist e soft-delete preservados.
### Adicionado (deploy)
- RUNBOOK_EMBEDDINGS.md: ativação passo a passo da busca semântica em produção,
  com rollback e verificação.
- seeds/smoke_rag_producao.py: teste de fumaça do RAG em Postgres real (pgvector,
  ILIKE+ANY, operador <=>, precedentes internos). Somente leitura — seguro em produção.

## [Auditoria + Correções + Cobertura de Testes] 2026-06-15
### Bugs corrigidos
- sanitizer.py: regex `\b` substituída por lookahead/lookbehind — nomes com
  pontuação interna (S.A., Ltda., ME.) agora são corretamente mascarados.
  Bug afetava parte contrária do tipo PJ em todo o pipeline LGPD.
- case_context.py: `parte_contraria` adicionada ao texto do dossiê (ausência
  impedia o sanitizador de agir sobre ela). Agora aparece em claro no modo
  sanitizar=False e mascarada no modo padrão sanitizar=True.
- case_context.py: guard `hasattr(Deadline, 'deleted_at')` removido —
  campo confirmado presente no modelo; guard era código morto.
### Adicionado
- backend/entrypoint.sh: aguarda PostgreSQL → alembic upgrade head →
  seed_all.py → uvicorn. Migrations e seed agora rodam automaticamente
  no `docker compose up` (sem passo manual).
- backend/Dockerfile: ENTRYPOINT aponta para entrypoint.sh.
- tests/test_case_context_precedentes.py: 13 novos testes cobrindo
  montar_dossie (estrutura, sanitização LGPD, ramo especializado, prazos,
  honorários, histórico) e ciclo completo de precedentes internos
  (novo → inalterado → atualizado → meta gravada).
### Resultado
- Suite: 30 testes passando (era 17). Frontend: tsc 0 erros, build OK.
