# Revisão de segurança do PR #975 — 2026-08-09

> **Escopo e limitação:** esta revisão segue manualmente o checklist canônico de
> `.claude/agents/security-auditor.md` sobre o diff do PR #975. O ambiente desta
> execução (conector GitHub) não expõe o comando `graphify` nem a invocação de
> subagentes Claude. Portanto **este documento não substitui a execução literal
> do `security-auditor` exigida por `AGENTS.md` antes do merge**. O PR deve
> permanecer bloqueado por esse gate até a execução canônica ser registrada.

## Escopo revisado

Mudanças do PR #975 relacionadas a segurança/governança:

- `backend/app/routers/trash.py` — restauração com validação de dependências,
  paginação e auditoria;
- `backend/app/routers/produtividade.py` — evento de exportação gerencial
  auditado e rate-limited;
- `frontend/src/pages/Lixeira.tsx` — paginação e tratamento do conflito 409;
- `frontend/src/pages/Produtividade.tsx` e `frontend/src/utils/exportPdf.ts` —
  exportação vinculada ao snapshot carregado e preservação do gesto do usuário;
- `frontend/src/pages/Checklists.tsx` — erro de carga explícito e bloqueio de
  criação enquanto o estado remoto é desconhecido;
- testes associados.

Não há migration, upload, segredo, integração externa nova ou alteração de JWT.

## Mapeamento de fluxo

### 1. Lixeira — restauração

`Lixeira.tsx` → `POST /trash/{entidade}/{registro_id}/restaurar` →
`require_roles([superadmin, admin, socio])` → allowlist `ENTIDADES` → busca do
registro soft-deleted → `_validar_dependencias_restauração` → validação de caso
/ cliente pai → alteração `deleted_at = NULL` → `criar_audit_log` → commit.

### 2. Produtividade — exportação

`Produtividade.tsx` carrega `GET /analytics/produtividade` → usuário clica em
CSV/PDF → snapshot local precisa corresponder ao período selecionado →
`POST /analytics/produtividade/export-event` → `rate_limit` autenticado →
`_req_gestao` (piso `socio`) → Pydantic `Literal` + limite de linhas →
`criar_audit_log` com metadados mínimos → commit → geração local do arquivo no
browser.

No PDF a janela é aberta dentro do gesto do usuário **antes** da chamada de
rede. Popup bloqueado não gera evento de exportação; falha da auditoria fecha a
janela reservada e não gera PDF.

## Verificações do security-auditor

### Autenticação

- Nenhum endpoint novo é público.
- `rate_limit()` depende de `get_current_user`; requisição sem token válido
  recebe 401 antes de consumir cota.
- Nenhuma mudança em JWT, refresh token, 2FA ou bcrypt.

**Achados novos:** nenhum.

### Autorização / RBAC

- Lixeira continua restrita a `superadmin`, `admin` e `socio`.
- `require_roles()` possui fallback hierárquico genérico conhecido, porém neste
  uso o menor nível permitido é `socio`; `advogado`, `financeiro`, `estagiario`,
  `secretaria` e `cliente_externo` permanecem abaixo do piso e recebem 403.
- Produtividade e o novo evento de exportação usam `_req_gestao`, que exige
  `ROLE_LEVEL >= socio`.
- Não houve afrouxamento de ownership; a Lixeira é uma superfície deliberadamente
  gerencial/global e não uma carteira individual.

**Achados novos após as correções:** nenhum.

### Entrada do usuário / injeção

- `entidade` na Lixeira é resolvida exclusivamente pela allowlist estática
  `ENTIDADES`; não é interpolada em SQL textual.
- `page >= 1` e `1 <= page_size <= 100` são validados pelo FastAPI.
- Evento de exportação restringe `periodo` e `formato` por `Literal` e rejeita
  `linhas < 0` ou `linhas > 100000`.
- Nenhum conteúdo de relatório é aceito ou persistido no endpoint de auditoria.

**Achados novos:** nenhum.

### Rate limiting / abuso

- Foi adicionado `rate_limit("produtividade_export_event", 30)` ao endpoint que
  grava AuditLog, reduzindo risco de flood por conta comprometida ou bug de UI.
- A operação de restauração não ganhou rate limit nesta frente; ela já é
  restrita a gestão e cada chamada representa uma mutação deliberada auditada.
  Não foi identificado vetor externo ou custo de integração que justificasse
  ampliar o escopo neste PR.

**Achados novos:** nenhum bloqueante.

### LGPD / minimização

- AuditLog de restauração registra somente entidade, id e `deleted_at`
  antes/depois; não registra conteúdo do objeto restaurado.
- AuditLog de exportação registra apenas período, formato e quantidade de linhas;
  não registra nome de advogado, e-mail, CPF, conteúdo do relatório ou filtros
  pessoais.
- O tratamento do 409 da Lixeira exibe a mensagem de domínio já produzida pelo
  backend e não inclui dado sensível adicional.
- O PDF continua sendo gerado localmente no browser; nenhum novo envio externo
  de dados foi introduzido.

**Achados novos:** nenhum.

### Segredos / configuração / rede

- Nenhum `.env`, token, chave, credencial, CORS, nginx ou integração externa foi
  alterado.
- Nenhuma resposta de provedor externo é exposta.

**Achados novos:** nenhum.

## Achados corrigidos nesta rodada

1. **P2 — popup PDF após `await`**: corrigido abrindo a janela no gesto do
   usuário e reutilizando-a depois da auditoria.
2. **P2 — auditoria vinculada ao período errado**: corrigido usando
   `data.periodo`, bloqueando export durante loading e descartando respostas
   obsoletas do período anterior.
3. **P2 — Lixeira não mostrava 409 de dependência**: corrigido com feedback do
   backend e estado de restauração.
4. **P2 — Lixeira descartava metadados de paginação**: corrigido com navegação
   por `total/page/page_size`.
5. **Baixo — flood de AuditLog do export-event**: mitigado com rate limit
   institucional autenticado de 30/min.
6. **UX — Checklists permitia clicar em ação sem efeito durante erro**:
   corrigido; criação fica bloqueada até carga válida.

## Resultado estático

- Crítico: **0**
- Alto: **0**
- Médio/P2 pendente: **0**
- Baixo pendente introduzido pelo PR: **0**

## Gate que permanece aberto

`[ ] security-auditor` **literalmente executado no ambiente canônico do
repositório**, com `graphify`/ferramentas definidas no agente, e resultado
registrado no PR.

Até esse item e os gates de CI voltarem a executar normalmente, o PR #975 não
deve ser mesclado.
