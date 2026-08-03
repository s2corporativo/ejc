# Backlog de higienização do frontend (frontend/src)

Catálogo produzido na passada de padronização/higienização de 2026-07-26
(branch `chore/padronizacao-frontend`). Itens verificados mas **não**
resolvidos naquela passada — cada um com o motivo.

## Exceções intencionais (não mexer sem motivo forte)

- `src/components/ErrorBoundary.tsx` usa `fetch()` cru (não o client
  `lib/api.ts`) para reportar crashes a `/api/observabilidade/frontend-error`.
  Intencional e comentado no código: evita recursão caso a falha esteja no
  próprio client axios.
- `src/lib/api.ts` (`refreshAccessToken`, `logout`) usa `axios` cru de
  propósito — evita recursão com o interceptor de response que refaz refresh
  em 401. Comentado no código.

## Kit de UI paralelo `src/components/ui/` — REMOVIDO (2026-08-03)

389 linhas em 6 arquivos (`Badge`, `Button`, `Card`, `Input`, `Page` e o barrel
`index.ts`) sem um único importador em `src/`. Entrou no commit `8524014`, o
mesmo que trouxe por engano `audit/quality/`, `auditoria-grafo/` e o
`docker-compose.override.yml`.

Além de morto, era um risco ativo: exportava `Button`, `Badge`, `Card` e
`PageHeader` — os mesmos nomes de `src/components/UI.tsx`, que 121 arquivos
usam de fato. Bastava um autoimport do editor apontar para o lado errado para a
tela renderizar com outro design system, sem erro de tipo.

`src/lib/cn.ts` **ficou**: `components/base/Skeleton.tsx` e
`pages/Ferramentas.tsx` usam.

## Módulos sem consumidores — RESOLVIDO (2026-07-27)

Todos os itens desta seção foram removidos; ficam registrados com o destino:

- `src/lib/aiCore.ts` — **removido em 1befdf0**. Nunca teve um único call site
  em `src/`. Recriá-lo sem migrar as telas só recriaria o órfão: a decisão real
  está na pendência "Núcleo de IA sem consumidor no frontend" (abaixo).
- `src/config/domainContracts.ts` — **removido em 1befdf0**. Duplicava à mão os
  literais de `backend/app/core/domain_contracts.py` sem replicar a lógica
  associada (`canonical_case_status`) e sem nenhum import. Se o frontend
  precisar desses unions, gerar a partir do OpenAPI em vez de copiar — a
  geração automática que recriava o arquivo foi retirada de
  `scripts/apply_architecture_refactor_wave1.py`.
- `src/pages/Biblioteca.tsx`, `KnowledgeHub.tsx`, `MemoriaInstitucional.tsx`,
  `Wiki.tsx` e `src/components/AssistedWritingMode.tsx` — **removidos em
  69e2799** após a consolidação "Conhecimento". As rotas antigas seguem vivas
  como redirects para `/inteligencia?tab=conhecimento` (`LEGACY_REDIRECTS` em
  `moduleRegistry.tsx` e `canonicalRoutes.ts`), e `src/config/lazyModules.test.ts`
  trava lazy import apontando para arquivo inexistente.

## Pendências de arquitetura (dono a definir)

### Núcleo de IA sem consumidor no frontend

**Situação.** O Núcleo Único de IA existe, está governado e é servido em
`/api/ai/core/*` (orchestrator em `backend/app/services/ai/core/`, HITL
carimbado por `hitl_policy.aplicar()`, política de provider e barreira final de
PII no `ai_gateway`). Nenhuma tela do frontend o consome: as superfícies de IA
seguem nos endpoints legados — `/ai/analisar-caso`, `/ai/skills/execute`,
`/ai/gerar-minuta`, `/ai/analisar-contrato`, entre outros — que hoje funcionam
como wrappers.

**Consequência.** O contrato do núcleo não tem verificação de ponta a ponta
pelo cliente real, e a documentação de IA descrevia um client de frontend
(`lib/aiCore.ts`) que nunca teve consumidor e foi removido em 1befdf0 — as
referências foram corrigidas em 2026-07-27, mas o descompasso de fato
permanece.

**Encaminhamento sugerido (não decidido).** Tratar como item de arquitetura
próprio — "migrar as superfícies de IA do frontend para o núcleo único" — com
migração incremental tela a tela, o client tipado nascendo junto do primeiro
consumidor real e não antes. Alternativa legítima: assumir os wrappers legados
como contrato público estável e ajustar a documentação de IA para refletir
isso. **Não é uma decisão de faxina** e precisa de dono definido.

## Formatadores locais NÃO consolidados (semântica própria)

Os formatadores idênticos foram consolidados em `src/utils/formato.ts`
(`fmtMoney`/`fmtDate`/`fmtDateTime`, re-exportados por `components/UI.tsx`).
Ficaram de fora, por terem comportamento próprio:

- `src/components/ClientServiceTimeline.tsx` — `formatDateTime` devolve
  `{dia, hora}` separados (dia por extenso) e `formatCompactDate` devolve
  `null` para JSX condicional.
- `src/pages/RadarCompliance.tsx` — `formatData` devolve o ISO cru quando a
  data é inválida (não um fallback fixo).
- `src/pages/DataJudBusca.tsx` (`formatCNJ`) e
  `src/components/EntradaUniversalDocumentos.tsx` (`formatBytes`) — únicos no
  repo, sem duplicata.
- `src/components/AnaliseExtratos.tsx` — `fmt(v: any)` genérico de célula;
  consolidar exigiria retipar a tabela dinâmica.

## Dívida de tipos e lint (pré-existente na main)

- `npm run lint:eslint`: **0 erros**, ~640 warnings — quase todos
  `@typescript-eslint/no-explicit-any`, majoritariamente `catch (e: any)` em
  handlers. É o padrão dominante do repo; tipar tudo é um passe dedicado
  (sugestão: helper `detalheErro(e: unknown)` central, como o adotado em
  `RedefinirSenha.tsx` nesta passada).

  **RESOLVIDO em 2026-08-03.** O helper central sugerido virou
  `src/utils/erro.ts` e o `catch (e: any)` deixou de existir no repo:

  | | antes | depois |
  |---|---|---|
  | warnings do eslint | 644 | 401 |
  | `no-explicit-any` | 619 | 376 |
  | `catch (e: any)` | 227 | **0** |
  | cópias locais do helper | 19 (em 4 nomes) | **0** |

  `src/utils/erro.ts` é o ponto único. `detalheErro` cobre a união dos formatos
  reais de `response.data.detail` — string, objeto com `mensagem` **ou**
  `message`, e lista do 422 do Pydantic. Para o resto: `statusErro`
  (`response.status`), `mensagemErro` (`.message` de erro nativo), `foiAbortado`
  (as 4 formas de cancelamento), `dadosErro` (`response.data` cru, para
  `must_change_password`/`precisa_configurar_2fa` no fluxo de sessão) e
  `detalheBruto` (`detail` sem formatar, para quem inspeciona a forma do
  payload). Coberto por `src/utils/erro.test.ts`.

  **Três mudanças de comportamento**, todas para melhor e todas com teste:
  as cópias `errDetail` devolviam `JSON.stringify(detail).slice(0, 200)` para
  objeto sem `mensagem`, colocando `{"campo":"cpf","codigo":422}` dentro de um
  toast — agora cai no fallback em português; `detail` só com espaço em branco
  vira fallback (comportamento que só o `erroDetalhe` tinha); e a chave
  `message` passa a ser lida em todo lugar, não só no login e no 2FA.

  Método, se for aplicar em outra frente: converter `any` → `unknown` e deixar o
  `tsc` apontar cada uso que não é seguro. Foi assim que os 43 pontos não
  mecânicos apareceram em tempo de build, em vez de em produção. Vale o aviso de
  um erro cometido no caminho: o primeiro script checava se ainda havia acesso
  cru **no arquivo inteiro** antes de trocar a anotação, então um único `catch`
  fora do padrão travava todos os outros do mesmo arquivo — 44 dos 56 `catch`
  que pareciam irredutíveis eram falso positivo disso. Escopo de verificação é
  o bloco, não o arquivo.
- `react-hooks/exhaustive-deps` em nível warn com ocorrências pontuais —
  revisar caso a caso (algumas dependências omitidas são intencionais).

## Observações

- Não há `console.log`/`console.debug` em `src/` (verificado por grep);
  os `console.error`/`console.warn` remanescentes são de handlers legítimos.
- Não há `TODO`/`FIXME` pendentes em `src/` (ocorrências de "TODOS" são a
  palavra portuguesa em comentários).
- Rótulos de UI conferidos contra `src/config/moduleRegistry.tsx` — sem
  divergência de nomenclatura ("Casos" etc.); a aba "Processos" em
  `CasoDetalhe.tsx` refere-se aos processos judiciais do caso, não ao módulo.
