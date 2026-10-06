# 🧠 JuridIA — Cérebro Jurídico com IA

Sistema de inteligência artificial jurídica que atua como **Advogado**, **Promotor** e **Juiz**. Construído sobre o núcleo cognitivo do [LexValida](https://github.com/) + EJC, com IA verificável (anti-alucinação), 3 personas e base de conhecimento jurídico curada.

## ⚖️ Arquitetura

### Cérebro Jurídico (zona única — sem ERP)

O sistema é **exclusivamente cognitivo**. Funções operacionais (clientes/casos/documentos/prazos/audiências/financeiro) foram removidas para focar no conhecimento. As APIs continuam disponíveis para a IA usar internamente.

**14 tabs** no AppShell:
- **Assistente** — classificador determinístico de 17 intenções
- **Biblioteca** — skills + fontes legais + jurisprudência + precedentes + normas
- **1. Cérebro** — 8 etapas cognitivas (classificação → extração → questões → legislação → jurisprudência → viabilidade → lacunas → estratégia)
- **2. Inteligência** — Case Mapper (graph + assertions + evidence)
- **3. Pipeline** — LexValida 8 fases com SSE streaming
- **5. Produção** — Gerador de minutas com templates + skills
- **Editor** — Molde mode + estilo + citation checker
- **Homologação** — 10 casos end-to-end
- **Análise Jurídica** — 9 tools (prazo, correção, juros, prescrição + salvaguardas + valor-causa + triagem + vedação-surpresa + checklist-julgador)
- **Visual Law** — timeline + quadro-resumo
- **DataJud** — consulta pública CNJ
- **Grafo** — agente de grafo do sistema (mapeia APIs/components/libs/models)
- **6. Governança** — settings

### 3 Personas

| Persona | Cor | Foco | Comportamento |
|---|---|---|---|
| **Advogado** 🟢 | emerald | Defesa do cliente | Balance persuasão com honestidade |
| **Promotor** 🔴 | rose | Acusação pública | Tipificação, autoria, materialidade |
| **Juiz** 🟣 | violet | Decisão imparcial | CPC arts. 9 e 10 — ouça as partes |

## 🛡️ Camadas

1. **Cognitiva** (alto nível): `legal_brain`, `lexvalida_pipeline`, `agent_loop`
2. **Governança** (anti-alucinação): `citation_gate` (`{{juris:ID}}`, `{{lei:ID}}`, `[[autos:DOC:PÁG|trecho]]`), `evidence`, `rag_lite`
3. **Jurídica especializada**: `judge_simulator`, `proof_matrix`, `thesis_checker`, `skill_router`
4. **Privacidade (LGPD)**: `anonymize` (tarja-1), `pseudonymizer`
5. **Portadas do LexValida**: `lexvalida_port`, `assistente`, `graph-agent`, `api-helpers`

## 🔌 z-ai-web-dev-sdk integration

6 APIs com LLM real:
- `/api/brain` — Cérebro cognitivo (~30s, 8 etapas)
- `/api/generate-minuta` — Geração de minutas
- `/api/case-analysis` — Análise estruturada
- `/api/molde` — Modo Molde
- `/api/suggest` — Sugestões contextuais
- `/api/intelligence/map` — Case Mapper

## 🔒 Segurança

- **Auth**: `requireAuth()` helper com header `X-API-Token` (bypass em dev, obrigatório em produção)
- **Rate limiting**: token bucket in-memory (5 req/min para /api/brain, 10 req/min para outros)
- **Idempotência**: POST /api/intimacoes com SHA-256 hash dedup

## 📦 Stack

- **Framework**: Next.js 16 com App Router
- **Linguagem**: TypeScript 5
- **Estilo**: Tailwind CSS 4 + shadcn/ui (New York)
- **Database**: Prisma ORM + SQLite
- **IA**: z-ai-web-dev-sdk (LLM)
- **UI**: framer-motion + lucide-react
- **State**: Zustand

## 🚀 Setup

\`\`\`bash
# Instalar dependências
bun install

# Configurar .env
echo "DATABASE_URL=file:./db/custom.db" > .env

# Push schema para o banco
bun run db:push

# Em desenvolvimento, popular base de conhecimento (OPCIONAL — só dev):
bun run scripts/seed.ts
bun run scripts/seed-extra-skills.ts
bun run scripts/seed-legal-sources.ts

# Em produção: usar fontes REAIS oficiais (Planalto, CNJ, STJ, STF) — scripts de seed BLOQUEADOS em produção

# Iniciar dev server
bun run dev
# Acesse http://localhost:3000
\`\`\`

## 📚 Conhecimento jurídico real (não fictício)

O banco contém apenas fontes reais:
- **17 skills** (CC responsabilidade civil, CDC cláusulas abusivas, CLT petição inicial, CNJ 615/2025, etc.)
- **11 templates** (petição inicial cível, apelação, contrato, defesa fiscal, despacho, etc.)
- **33 legal sources** (CC, CPC, CLT, CP, CDC, CTN, CF + artigos específicos)
- **48 skillVersions** (versionadas para auditoria)

## 🧹 Garantia anti-fictitious

- **Scripts de seed marcados DEPRECATED** com production guard
- **Banco limpo**: 0 clients/cases/documents/auditEvents fictícios
- **Scripts de auditoria**: `scripts/audit-fictitious.ts` + `scripts/clean-fictitious.ts`

## 📁 Estrutura

\`\`\`
src/
├── app/api/          49+ endpoints (auth + rate limited)
├── components/app/   20+ componentes (Assistente, Cérebro, Pipeline, etc.)
├── components/ui/    48+ shadcn primitives
├── lib/              25+ libs (legal_brain, lexvalida_pipeline, personas, security, etc.)
└── page.tsx          único route público

prisma/
└── schema.prisma     25+ models (User, Case, Document, EvidenceRef, etc.)

scripts/
├── seed*.ts          7 seed scripts (DEPRECATED em produção)
├── audit-fictitious.ts
├── clean-fictitious.ts
└── auto-backup.sh    git auto-commit
\`\`\`

## 📄 Licença

Projeto demonstrativo. Código aberto para estudo.
