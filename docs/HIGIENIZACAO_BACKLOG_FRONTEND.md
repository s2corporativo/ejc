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

## Módulos sem consumidores (catalogados, não removidos)

- `src/lib/aiCore.ts` — nenhum import em `src/` hoje, mas é o contrato de
  frontend do Núcleo Único de IA documentado em `docs/ai/` (ex.:
  `EJC_SINGLE_AI_CORE_ARCHITECTURE.md`). Mantido; decidir entre religar
  consumidores ou remover junto com uma revisão das docs de IA.
- `src/config/domainContracts.ts` — constantes de status de ciclo de vida
  (caso/tarefa/documento) espelhando o backend; nenhum import em `src/`.
  Candidato a remoção ou a virar a fonte dos unions de status em
  `src/types` — decisão de arquitetura, não de faxina.
- `src/pages/Biblioteca.tsx`, `KnowledgeHub.tsx`, `MemoriaInstitucional.tsx`,
  `Wiki.tsx` e `src/components/AssistedWritingMode.tsx` — órfãos após a
  consolidação "Conhecimento" (comentário em `moduleRegistry.tsx`); remoção
  já em andamento por outra frente, fora do escopo desta passada.

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
