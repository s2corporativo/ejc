# EJC — Consolidação e publicação 2026-09-23/24

**Status:** EM TESTE — ainda não promover para `main` nem para produção.

## Estado confirmado

| Item | Estado |
|---|---|
| `main` confirmada | `16bdb03e` — PR #1822 W8.2 assíncrona, flag OFF |
| Release de consolidação | `release/ejc-publicacao-2026-09-23` |
| VPS em produção | `0bb8c62d` — saudável; ainda sem as mudanças de 23/09 |
| Readiness produção | banco, migrations, Redis e embeddings = OK |
| Migration nova neste release | nenhuma |
| W8.2 assíncrona | código presente, **não ativar**; store ainda é em memória |
| Deploy final | bloqueado até release → `main` + Woodpecker push/main verde |

## Correções da auditoria de consolidação

### #1818 — Assistente de casos: NÃO promover como nova superfície

A branch de release havia incorporado manualmente `backend/app/routers/assistente.py`,
mas o EJC já possui as capacidades canônicas:

- `POST /api/ai/casos/{case_id}/assistente`;
- `POST /api/ai/detectar-prazos`.

As rotas canônicas já aplicam equipe jurídica, ownership, sigilo reforçado,
sanitização, RAG/anti-injection quando aplicável e trilha `AILog/HITL`.
A #1818 criaria portas paralelas chamando `ai_gateway` diretamente, sem a mesma
governança, e não possui consumidor frontend confirmado.

**Decisão técnica:** remover o router duplicado do release e preservar as portas
canônicas existentes. A Issue #1821 deve ser encerrada como superada após a
consolidação da PR #1825.

### #1820 — Auditor preliminar de propostas de licitação

A implementação original foi mantida, mas precisa entrar somente com o hardening
da #1825:

- prefixo interno `/licitacao-auditoria` — o middleware global fornece
  compatibilidade externa `/api/v1`;
- acesso restrito à equipe jurídica;
- rate limit;
- PDF limitado a 15 MB;
- erro de parser sem conteúdo sensível em log;
- PDF sem texto extraível falha fechado como `requires_manual_review`, nunca
  como “nenhuma falha encontrada”;
- teste de regressão específico.

### #1819/#1827 — sql_safe

A #1819 colocou a biblioteca `sql_safe.py` na `main`, mas sozinha não protegia
nenhum consumidor. A #1827 é a integração real em routers/services e deve ser
tratada como frente separada até a suíte completa ficar verde. Não considerar a
frente de SQL dinâmico concluída apenas pela existência da biblioteca.

### #1817/#1826 — templates jurídicos

Os seeds de cláusulas/templates entraram na `main`, porém não são executados
automaticamente. A #1826 remove a associação inadequada do HITL ao Provimento
OAB 205/2021, mantendo a revisão humana obrigatória antes do protocolo.

**Não executar os seeds em produção antes da #1826 e do deploy final.**

### #1823 — DataJud Redis L2

A PR adiciona cache compartilhado opt-in para `consultar_movimentos`, com
`DATAJUD_CACHE_REDIS_ENABLED=false` por padrão.

Ela é **parcial** em relação ao OPS-04: a consolidação das três rotinas DataJud
continua pendente. Mesmo após merge, manter a flag OFF em produção até teste
controlado e avaliação de retenção/LGPD dos metadados processuais no Redis.

## Gates para promoção

1. PRs integrantes do release com Woodpecker verde no HEAD exato.
2. Release reconciliado com a `main` vigente.
3. Um único PR release → `main`, sem bypass.
4. Woodpecker `push/main` verde no SHA final.
5. Deploy manual pelo runbook a partir de **checkout Git limpo** do SHA final.
6. Backup pré-deploy + classificação Alembic.
7. `/api/health` e `/api/health/ready` verdes.
8. Smoke autenticado do fluxo mínimo cliente → caso → documento → peça → revisão
   → prazo → financeiro → encerramento.

## Observação operacional da VPS

O runtime `/opt/ejc` não é atualmente um checkout Git. O alias histórico
`/opt/ejc-deploy-src` aponta para esse runtime, portanto o comando antigo
`cd /opt/ejc-deploy-src && git ...` não é válido no estado atual.

O `scripts/deploy_manual.sh` exige:

- execução a partir de um checkout Git cujo HEAD seja o SHA alvo;
- SHA alvo igual ao `origin/main` atual;
- prova Woodpecker `push/main` verde;
- `APP_DIR=/opt/ejc` como runtime;
- backup, migration gate, health e rollback.

Antes do deploy final, preparar/reutilizar um checkout limpo dedicado ao deploy,
sem transformar `/opt/ejc` novamente em árvore Git e sem criar cópias paralelas
permanentes desnecessárias.

## Itens deliberadamente NÃO ativados neste ciclo

- `IA_ANALISE_ASYNC_ENABLED`: manter `false` até Redis/Celery + UI de progresso
  + teste multi-worker.
- `DATAJUD_CACHE_REDIS_ENABLED`: manter `false` até homologação controlada.
- migrations destrutivas/remoção de PII legado: fora deste release.
- pesquisa jurídica pública/RAG hardening fechados para backlog: não ressuscitar
  no release sem nova homologação.

## Rollback

A produção atual `0bb8c62d` permanece o baseline estável até a promoção final.
O deploy final deve continuar usando a transação existente de backup,
health-check e rollback automático. Nenhuma PR deste bloco introduz migration
nova.
