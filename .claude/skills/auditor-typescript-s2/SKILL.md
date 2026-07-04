---
name: auditor-typescript-s2
description: >
  Audit TypeScript full-stack codebase for security vulnerabilities, architectural coherence,
  modularization quality, and deployment readiness. Use this skill whenever the user asks to
  review code for security gaps (SQL injection, XSS, auth bypass, LGPD compliance), validate
  modularization structure (db.ts split into domain modules, router decomposition), check type
  safety strictness, identify unused code or circular dependencies, generate security/compliance
  reports, or prepare code for production deployment. Especially important for sistema-s2, a
  391-file TypeScript full-stack application handling public procurement data under Lei 14.133/21.
  Always ask which deployment context (SICAF, CAGEF, private API) if unclear. Generate actionable
  remediation checklists with criticality levels (critical/high/medium/low) and executive summaries.
  Trigger on: "audita código", "review sistema-s2", "vulnerabilidades TypeScript", "prep deploy",
  "gera ZIP refatorado", "SQL injection", "segurança do sistema".
---

# Auditor TypeScript — Sistema S2

## Contexto Operacional

O **sistema-s2** é aplicação full-stack TypeScript com:
- 391 arquivos (refatoração em andamento)
- PostgreSQL com dados de licitações públicas
- Integração com portais governamentais (SICAF, CAGEF/MG, ComprasGov, SAP Ariba)
- Conformidade obrigatória: Lei 14.133/21, LGPD, normas TCU

**Refactoring anterior (maio 2026):**
- `db.ts` → 22 módulos de domínio
- `routers.ts` → 15 arquivos especializados
- ZIP final ainda pendente de geração

---

## Fluxo de Auditoria

### Entrada

Formatos aceitos:
- Pasta local: `/home/claude/sistema-s2`
- ZIP enviado: `/mnt/user-data/uploads/sistema-s2.zip`
- URL GitHub
- Código em paste (revisão pontual)

Pergunta obrigatória se não especificado:
> "Audita sistema-s2 completo ou módulo específico (db, routers, auth)?"

---

### 4 Camadas de Análise

#### CAMADA 1 — SEGURANÇA (crítica)
- SQL Injection: padrões `query()`, `raw()`, raw string templates
- XSS: rendering de inputs, encoding, sanitização
- Auth bypass: verificação de token, expiração, permissões por role
- LGPD: mascaramento de dados pessoais em logs e responses
- Variáveis undefined / null checks faltando em fluxos críticos
- Secrets expostos em código (API keys, senhas, tokens hardcoded)

#### CAMADA 2 — MODULARIZAÇÃO (arquitetura)
- Coerência da decomposição (db.ts → 22 módulos): 1 responsabilidade por módulo?
- Routers especializados (15 arquivos): injeção de dependências correta?
- Imports circulares presentes?
- Duplicação de código entre módulos?
- Exports claros vs. acoplamento implícito?

#### CAMADA 3 — TIPAGEM TYPESCRIPT (confiabilidade)
- `tsconfig.json` com `strict: true`?
- `strictNullChecks`, `noImplicitAny` ativos?
- Tipos genéricos em modelos de domínio?
- Erros ignorados com `any` ou `// @ts-ignore`?

#### CAMADA 4 — PRODUÇÃO (readiness)
- Build sem warnings?
- Cobertura de testes >70%?
- CI/CD configurado?
- Healthcheck endpoints?
- Logging estruturado (não console.log)?
- Rate limiting implementado?

---

### Relatório Padrão de Saída

```
# AUDITORIA SISTEMA-S2 — [Data]

## SUMÁRIO EXECUTIVO
- Vulnerabilidades críticas: [N]
- Problemas de arquitetura: [N]
- Alertas de tipagem: [N]
- Status: ✅ SEGURO / 🟡 CONDICIONAL / 🔴 RISCO

## 1. VULNERABILIDADES CRÍTICAS

### [CRÍTICO] SQL Injection em função X
- Arquivo: src/db/queries.ts:142
- Código: `SELECT * FROM proposals WHERE id = ${proposalId}`
- Impacto: exposição de todas as licitações públicas
- Fix: parametrizar query com placeholder
- Tempo estimado: 15 min

## 2. ARQUITETURA
- Modularização DB: [status por módulo]
- Routers: [status por router]
- Circular deps: [lista]

## 3. TIPAGEM
- strictNullChecks: ✅/❌
- Variáveis não utilizadas: [N]

## 4. CHECKLIST REMEDIAÇÃO (priorizado)

Priority 1 — ANTES do deploy:
- [ ] Fix SQL injection em [arquivos]
- [ ] Resolver circular dep em auth
- [ ] Sanitizar inputs públicos

Priority 2 — Esta semana:
- [ ] Split router licitações
- [ ] Ativar noUnusedLocals
- [ ] Cobertura de testes >70%

## 5. PRÓXIMA AÇÃO
Gerar ZIP refatorado com correções críticas? Sim/Não?
```

---

### Outputs Entregáveis

Sempre gera:
1. Relatório `.md` com estrutura acima
2. `remediation-checklist.json` com todos os problemas + status
3. Scripts de fix automático (quando aplicável)
4. Novo ZIP com correções críticas (sob confirmação)

Arquivos de saída:
- `/mnt/user-data/outputs/auditoria-sistema-s2-[data].md`
- `/mnt/user-data/outputs/checklist-remediacao.json`
- `/mnt/user-data/outputs/sistema-s2-fixed.zip`

---

## Premissas Críticas

- Contexto sempre CRÍTICO: código toca dados de licitações públicas, auditável pelo TCU
- Nunca ignorar undefined variables em ambiente de produção com dados sensíveis
- Circular dependencies: identificar e quebrar, não tolerar
- LGPD: qualquer CPF/CNPJ/dado pessoal exige auditoria específica
- Lei 14.133/21: validações de regras de negócio devem ser testadas contra jurisprudência TCU

---

## Acionamento

Frases que ativam automaticamente:
- "audita sistema-s2", "audita o código"
- "review para segurança", "vulnerabilidades"
- "gera ZIP refatorado", "prep para deploy"
- "SQL injection", "LGPD no sistema"
- Quando você envia código + pergunta sobre segurança ou estrutura
