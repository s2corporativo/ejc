# Auditoria — Módulo Áreas de Atuação e suas Ferramentas (EJC)

**Data:** 2026-08-10
**Escopo:** `frontend/src/pages/ramos/` (hubs de ramo + calculadoras), `backend/app/routers/ramos.py`
e routers satélite (`trabalhista_liquidacao.py`, `tributario_fiscal.py`, `previdenciario_beneficio.py`,
`ambiental_estrategia.py`, LGPD, sociedades), componentes `Guia*`/ferramentas dedicadas em
`frontend/src/components/`, contrato frontend↔backend, RBAC de rota, matriz de homologação jurídica.
**Método:** leitura direta do código (arquivo:linha em cada achado), sem acesso a produção. Auditoria
de código — complementar à auditoria externa de julho/2026 (`docs/auditoria/`), que testou por API sem
ver o código-fonte.

---

## 1. Resumo executivo

O módulo está em estado **bem melhor do que a auditoria externa de julho registrou** — as "Ondas 1–3"
já em `docs/auditoria/onda-2-limpeza.md` e a matriz de homologação (`homologacao_ferramentas.py`)
mostram trabalho de correção ativo e testado. Achei **6 problemas concretos e verificáveis**, nenhum
deles do tipo "cálculo errado" (não fiz perícia jurídica linha a linha de todas as 56 calculadoras —
ver limitações, §6), e uma crítica de arquitetura sobre o tamanho/forma do `ramosConfig.ts`.

| # | Achado | Severidade | Status |
|---|---|---|---|
| 1 | `licitacoes` existe no enum `CaseArea` do backend mas está ausente do catálogo de áreas do frontend | Média | Confirmado |
| 2 | Rota `/areas-de-atuacao/:slug` (onde os dados realmente aparecem) não tem RBAC no frontend — só o hub-pai tem | Média | Confirmado |
| 3 | Banner "⚠ regra em revisão — não homologada" aparece em **toda** ferramenta, mesmo nas 56/57 já homologadas | Média (confiança do usuário) | Confirmado |
| 4 | Frontend ainda renderiza 2 cards para prescrição penal; backend já depreciou um deles como duplicata | Baixa | Confirmado |
| 5 | Cor "indigo" do hub Tributário não existe no mapa de cores do card — cai para cinza | Baixa (cosmético) | Confirmado |
| 6 | 11 das 25 áreas do enum não têm hub/calculadora dedicada — apenas o CRUD genérico de casos | Informativo | Confirmado |

---

## 2. Inventário

### 2.1 Hubs com módulo dedicado (`RAMOS` em `ramosConfig.ts:2519-2534`)

| Hub | `areaCaso` | Endpoint backend | `externo` | Ferramentas | Cor | Guia próprio |
|---|---|---|---|---|---|---|
| empresarial | empresarial | `/empresarial` | não | 3 | amber | sim |
| civel | civil | `/civel` | não | 7 | blue | sim |
| penal | criminal | `/penal` | não | 5 (2 duplicadas — §3.3) | red | sim |
| trabalhista | trabalhista | `/trabalhista-esp` | não | 5 | green | sim |
| administrativo | administrativo | `/admin-esp` | não | 3 | slate | sim |
| bancario | bancario | `/bancario` | não | 5 | yellow | sim |
| tributario | tributario | `/admin-esp` (reuso) | não | 7 | **indigo — sem cor no card (§3.4)** | sim |
| ambiental | ambiental | `/admin-esp` (reuso) | não | 5 | green | sim |
| consumidor | consumidor | `/cases/?area=consumidor` | **sim** | 3 | teal | sim |
| familia | familia | `/cases/?area=familia` | **sim** | 2 | rose | sim |
| imobiliario | imobiliario | `/cases/?area=civil` | **sim** | 3 | amber | sim |
| previdenciario | previdenciario | `/cases/?area=previdenciario` | **sim** | 3 | slate | sim |
| digital_lgpd | digital_lgpd | `/cases/?area=empresarial` | **sim** | 2 | indigo | sim |
| transito | transito | `/cases/?area=civil` | **sim** | 3 | bronze | sim |

6 dos 14 hubs (`externo: true`) não têm router/CRUD dedicado — reaproveitam o sistema geral de casos e
só acrescentam calculadoras + guia. Isso é declarado no tipo (`ramosConfig.ts:66`) e é uma escolha
razoável para ramos sem campos estruturados próprios; não é um bug.

### 2.2 Áreas sem hub dedicado

`CaseArea` (`backend/app/models/case.py:9-39`) define **25 valores**. `RAMOS` cobre 14 (contando
`civel`→`civil` e `penal`→`criminal`, que trocam de nome por convenção histórica —
`taxonomiaAreas.test.ts:19-22` documenta e trava isso). As **11 áreas sem hub, calculadora ou guia**:
`sucessoes`, `constitucional`, `saude`, `medico`, `agrario`, `agronegocio`, `eleitoral`,
`internacional`, `contratual`, `societario`, `licitacoes`. Casos nessas áreas existem (a auditoria
externa de julho criou e confirmou os 25 — `docs/auditoria/relatorios/parte-05-areas-visuallaw-extracao.md:48-74`)
mas navegam apenas pelo CRUD genérico de `/casos`, sem nenhuma ferramenta jurídica de apoio.
**Isso não é um bug** — é o estado real de cobertura do produto, útil para priorizar onde investir a
próxima ferramenta.

### 2.3 Governança de homologação (o que mudou desde a auditoria externa)

`backend/app/services/homologacao_ferramentas.py:15-39` é a fonte única. Hoje:
- `FERRAMENTAS_BLOQUEADAS` (503, indisponível) está **vazio** — nada bloqueado.
- `FERRAMENTAS_NAO_HOMOLOGADAS` (responde, mas com selo de aviso) tem **1 entrada**:
  `/penal/ferramentas/dosimetria`.
- O comentário no próprio arquivo documenta 3 fases já fechadas ("Onda 2 — Fase A/B/C") que
  corrigiram e removeram da matriz **~15 ferramentas** que estavam sinalizadas como não homologadas
  quando a auditoria externa rodou.
- Isso é espelhado em `ramosConfig.ts`: de 57 ferramentas declaradas, só `dosimetria`
  (`ramosConfig.ts:819`) tem `homologada: false`.
- O gate em `/pecas/demonstrativo` (mencionado em `RamoBase.tsx:154-169`) valida `ferramenta` contra
  rota real + exige `fontes`/`vigencia_regra`/`versao_regra` — coberto por
  `backend/tests/test_areas_atuacao_onda1.py` itens (f) e (g).

**Conclusão sobre homologação:** o processo de governança funcionou — o backlog de calculadoras não
homologadas foi trabalhado e reduzido de forma auditável, com teste de regressão para cada fase. O
problema que resta é de **comunicação na UI**, não de governança de conteúdo (§3.3).

---

## 3. Achados confirmados

### 3.1 `licitacoes` ausente do catálogo de áreas do frontend

- **Backend:** `backend/app/models/case.py:39` — `licitacoes = "licitacoes"` no enum `CaseArea`.
- **Frontend:** `frontend/src/lib/areaCatalog.ts:5-28` — lista `AREAS_FALLBACK` com 24 áreas,
  terminando em `societario` (linha 28); `licitacoes` não aparece.
- **Impacto:** qualquer código que deriva do catálogo do frontend (formulários de área, o próprio
  teste `taxonomiaAreas.test.ts:26` que usa `AREAS_FALLBACK` como fonte de "áreas conhecidas") não
  reconhece `licitacoes` como área válida, mesmo ela sendo uma área de primeira classe no backend
  (confirmado por criação de caso real na auditoria externa,
  `docs/auditoria/relatorios/parte-05-areas-visuallaw-extracao.md:74`, que também recomenda
  reclassificar `licitacoes` como subárea de `administrativo` — mérito de taxonomia à parte, o ponto
  aqui é a divergência de catálogo, não a taxonomia).
- **Correção sugerida:** adicionar `{ slug: "licitacoes", nome: "Licitações" }` a `AREAS_FALLBACK`, ou
  — se a decisão for reclassificar como subárea de administrativo (recomendação da auditoria externa,
  ainda não implementada) — remover do enum do backend e migrar os casos existentes. Qualquer um dos
  dois fecha a divergência; deixar como está não fecha nada.

### 3.2 RBAC não aplicado na rota onde os dados aparecem

- **Rota-pai (protegida):** `frontend/src/config/moduleRegistry.tsx:397-410` — `/areas-de-atuacao` tem
  `roles: ROLES.juridico` e o comentário explícito (linha 402-403): *"Ferramentas dos ramos exigem a
  equipe jurídica (`_EQUIPE` no backend); financeiro/secretaria recebem 403 ao acionar qualquer
  ferramenta."*
- **Rota-filha (sem RBAC):** `frontend/src/config/moduleRegistry.tsx:413-422` — `/areas-de-atuacao/:slug`
  (`ramo-detalhe`, onde `RamoBase` de fato renderiza casos, formulários e calculadoras) **não declara
  `roles`**.
- **Efeito em `App.tsx:141-155`:** a rota só recebe o wrapper `<RoleOnly>` quando `module.roles` existe
  (`element={module.roles ? <RoleOnly roles={module.roles}>{content}</RoleOnly> : content}`). Como
  `ramo-detalhe` não tem `roles`, o componente renderiza **sem checagem de papel** — qualquer usuário
  autenticado que monte a URL (`/areas-de-atuacao/civel`, por exemplo) chega à tela.
- **Confirmação de que o comentário do hub-pai está impreciso:** o backend concorda parcialmente —
  `backend/app/routers/ramos.py` protege os `POST` com `require_roles(_EQUIPE)`
  (ex.: linha 432 `emp_criar`, 656 `civ_criar`, 919 `pen_criar`), mas os `GET` de listagem usam **só**
  `get_current_user`, sem checagem de papel (linhas 419-428 `emp_listar`, 649-652 `civ_listar`,
  912-919 `pen_listar`, 1126-1133 `trab_listar`). O comentário do hub-pai diz que
  financeiro/secretaria recebem 403 "ao acionar qualquer ferramenta" — na prática, **listar casos do
  ramo funciona (200) para qualquer papel autenticado**; só criar (`POST`) é de fato barrado.
- **Atenuante real (não é um vazamento total):** `_crud_listar`
  (`backend/app/routers/ramos.py:316-327`) já filtra por escopo de propriedade —
  `if not is_gestao(cu): q = q.where(Model.case_id.in_(_casos_visiveis_subq(cu)))`. Um usuário
  financeiro/secretaria não vê casos de qualquer advogado, só os que já teria visibilidade via a
  subconsulta de casos visíveis. O achado não é "qualquer papel vê qualquer caso"; é que a camada de
  UI/rota está inconsistente com a intenção documentada, e o dado sensível específico do ramo (tipo de
  matéria, valores contratados, CNPJ, instituição financeira etc. — campos que **não** aparecem na
  listagem genérica de `/casos`) fica acessível a papéis que a governança do produto já decidiu, em
  outro lugar (Issue #694, `backend/tests/test_rbac_equipe_juridica_694.py`), que não devem tocar ato
  jurídico.
- **Correção sugerida:** adicionar `roles: ROLES.juridico` à entrada `ramo-detalhe`
  (`moduleRegistry.tsx:413-422`), espelhando o hub-pai; e decidir conscientemente se os `GET` de
  listagem em `ramos.py` devem exigir `_EQUIPE` (fechando a lacuna nos dois lados) ou se o
  comportamento atual (leitura por qualquer papel autenticado, escopada por ownership) é o desejado —
  caso seja, corrigir o comentário em `moduleRegistry.tsx:402-403`, que hoje descreve um
  comportamento que o código não tem.

### 3.3 Banner de "não homologada" aparece em toda ferramenta, mesmo nas homologadas

- **UI:** `frontend/src/pages/ramos/RamoBase.tsx:269-276` — dentro do card de **toda** ferramenta,
  incondicionalmente:
  ```tsx
  {/* AI-107/AI-113: nenhuma calculadora está homologada — o estado é
      comunicado como selo operacional, não só aviso genérico. */}
  <span ...>⚠ regra em revisão — não homologada</span>
  ```
  Esse texto não depende de `f.homologada` — aparece igual em `taxas-bacen` (dado bruto do BCB, sem
  regra jurídica nenhuma para homologar) e em `dosimetria` (a única de fato não homologada).
- **Config:** `FerramentaConfig.homologada` (`ramosConfig.ts:38-41`) documenta *"Ausente = true
  (homologada)"* — ou seja, o **tipo** e a matriz do backend (§2.3) tratam quase todas as ferramentas
  como homologadas; só a UI trata todas como não homologadas.
- **Por que isso importa:** o comentário `AI-107/AI-113` no código é de uma época em que era
  literalmente verdade que nada estava homologado. As Ondas 2A/2B/2C (§2.3) já corrigiram e
  homologaram 56 das 57 ferramentas, com teste de regressão por fase — mas a UI nunca foi atualizada
  para refletir isso. O efeito prático é o oposto do que a homologação deveria comunicar: um advogado
  que confia no processo vê o mesmo aviso genérico em uma calculadora corrigida e testada e em uma
  que ainda está sob revisão, e não tem como diferenciar as duas pelo texto — só pelo selo
  condicional que já existe corretamente ao lado (`RamoBase.tsx:255-262`,
  `{naoHomologada && <span>⚠️ Não homologada</span>}`).
- **Correção sugerida:** remover o `<span>` incondicional de `RamoBase.tsx:271-276` (ou trocá-lo por
  um texto neutro tipo "minuta — revisão humana obrigatória", que já aparece em outro lugar do card,
  linha 353-355) e deixar o selo "⚠️ Não homologada" condicional (`naoHomologada`, já implementado)
  como o único indicador de status de homologação.

### 3.4 Prescrição penal: card duplicado que o backend já não tem

- **Frontend:** `ramosConfig.ts` declara dois cards na mesma página (`penal`):
  - `id: "prescricao"`, endpoint `/penal/ferramentas/prescricao-punitiva` (linhas 741-777);
  - `id: "prescricao-penal"`, endpoint `/penal/ferramentas/prescricao-penal` (linhas 779-816);
  — com os mesmos 6 campos, mesma base legal (CP arts. 109-117), mesmo grupo.
- **Backend:** `backend/app/routers/ramos.py:1076-1090` — a rota `prescricao-punitiva` já está
  `@router.get(..., deprecated=True)` e delega para a **mesma função**
  `_prescricao_penal_consolidada` (linha 1666) que `prescricao-penal` usa (linha 2435-2449). O próprio
  comentário do backend (linha 1675-1676) chama isso de *"duplicata mantida até a Onda 3"*.
- **Efeito:** o usuário vê dois cards com título quase idêntico ("Prescrição Punitiva" e "Prescrição
  Penal") que calculam exatamente a mesma coisa — confuso, e a marcação `deprecated=True` do OpenAPI
  não aparece em lugar nenhum da UI.
- **Correção sugerida:** já que o backend resolveu a duplicação (Onda 3, conforme o comentário),
  remover o card `id: "prescricao"` de `ramosConfig.ts:740-777` do frontend — é trabalho de limpeza
  que já tem luz verde do próprio código, só não foi propagado ao outro lado do contrato.

### 3.5 Cor "indigo" do hub Tributário não existe no mapa de cores do card

- **Config:** `ramosConfig.ts:1438` — `tributario.cor = "indigo"`.
- **UI:** `RamoBase.tsx:96-103` — `COR_BORDA` só mapeia `amber`, `blue`, `red`, `green`, `slate`,
  `yellow`. O uso é `COR_BORDA[cfg.cor] || "border-slate-500"` (linha ~1224) — então o hub Tributário
  (que **não** é `externo` e efetivamente lista casos) cai sempre no cinza padrão em vez da cor de
  marca pretendida.
- Os outros hubs com cor não mapeada (`teal`, `rose`, `bronze`, e o segundo uso de `indigo` em
  `digital_lgpd`) são todos `externo: true` — `load()` (`RamoBase.tsx:1035-1045`) retorna lista vazia
  para eles sempre, então o card de listagem nunca chega a renderizar e o bug não tem efeito visual
  ali. Tributário é o único caso real.
- **Correção sugerida:** adicionar `indigo: "border-indigo-500"` a `COR_BORDA` (uma linha), ou trocar
  a cor do hub Tributário para uma já mapeada.

### 3.6 Cobertura de teste — o que já existe e o que falta

**O que já existe e é sólido** (ao contrário do que eu esperava antes de ler):
- `backend/tests/test_paridade_ferramentas_frontend.py` — compara campo a campo o parser textual de
  `ramosConfig.ts` contra a introspecção real dos handlers de `ramos.py` via `typing.get_type_hints()`
  (evita a armadilha de `from __future__ import annotations` mascarar `Literal`). Isso cobre
  exatamente o risco de "campo que o frontend manda e o backend rejeita com 422" — já é regressão
  automática, não uma lacuna.
- `backend/tests/test_rbac_equipe_juridica_694.py` — trava que papéis fora de `EQUIPE_JURIDICA`
  (financeiro, secretaria, cliente_externo) recebem 403 em atos jurídicos, e varre o repositório
  atrás de gates novos escritos com o padrão hierárquico defeituoso que causou a Issue #694. **Não
  cobre**, porém, os `GET` de listagem do §3.2 — esses nunca tiveram gate de papel, então não são
  "gate escrito errado" (o padrão que o varredor procura), são ausência de gate.
- `frontend/src/pages/ramos/taxonomiaAreas.test.ts` e `ramosDaArea.test.ts` — travam exatamente os
  bugs de achatamento de área que a auditoria externa de julho apontou (bancário/imobiliário/
  trânsito/LGPD/administrativo caindo em área genérica). Já resolvido e testado.
- `backend/tests/test_areas_atuacao_onda1.py` — cobre a matriz de homologação, bloqueio 503, gate do
  demonstrativo e mass assignment nos `PATCH`.

**O que falta:**
- Nenhum teste de componente para `RamoBase.tsx` (não existe `RamoBase.test.tsx`) — o achado §3.3
  (banner incondicional) não teria sido pego por nenhuma suíte automática porque não há teste de
  render do card de ferramenta.
- Nenhum teste (frontend ou backend) trava a paridade entre `AREAS_FALLBACK` (frontend) e `CaseArea`
  (backend) — é exatamente por isso que a divergência do §3.1 (`licitacoes`) sobreviveu sem ser
  pega; `taxonomiaAreas.test.ts` usa `AREAS_FALLBACK` como a própria fonte da verdade, então um item
  faltando ali é invisível para o teste.
- Nenhum teste trava que toda rota do frontend com dado sensível (`sensitive: true` em
  `moduleRegistry.tsx`) tem `roles` definido — é o tipo de invariante que `test_rbac_equipe_
  juridica_694.py` já demonstra saber escrever para o backend (varredura estática), só que para
  rotas do frontend não existe o equivalente.

---

## 4. Avaliação de arquitetura — `ramosConfig.ts`

O arquivo tem **3.275 linhas** e concentra: definição de 5 tipos, 14 configs de ramo completos (campos
de formulário + calculadoras + textos de ajuda + base legal), o mapa `SUBAREAS` (listas de texto para
exibição) e os `LinkExterno`. `RamoConfig` (linhas 44-96) tem **25 flags booleanas** individuais
(`guiaBancario`, `guiaTransito`, `guiaTrabalhista`, `liquidacaoTrabalhista`, `guiaTributario`,
`tributarioFiscal`, `guiaPrevidenciario`, `previdenciarioSimulacao`, `guiaAmbiental`, `autosAmbientais`,
`ambientalEstrategia`, `guiaCivil`, `guiaPenal`, `guiaConsumidor`, `guiaImobiliario`, `guiaFamilia`,
`guiaAdministrativo`, `guiaEmpresarial`, `sociedadesCliente`, `guiaLgpd`, `lgpdRegistros`,
`comparadorBacen`, `analiseDocumento`, `analiseExtratos`, `bancarioForense`), cada uma correspondendo
a uma linha de renderização condicional dedicada em `RamoBase.tsx:1132-1154`
(`{cfg.guiaBancario && <GuiaBancario />}` etc.) e um `import` próprio no topo do arquivo
(`RamoBase.tsx:54-77`).

**Isso funciona hoje porque 14 ramos é um número administrável à vista**, mas o padrão não escala
linearmente: cada ramo novo com um componente próprio (guia + eventual ferramenta especial) exige
tocar **3 arquivos** — o tipo `RamoConfig` (nova flag), o objeto do ramo (`flag: true`), e
`RamoBase.tsx` (import + condicional). Nenhum desses pontos falha ruidosamente se esquecido — uma
flag esquecida simplesmente não renderiza nada, sem erro de tipo nem teste que pegue.

**Sugestão de melhoria (não urgente, é dívida técnica administrável):** substituir as 25 flags
booleanas por um único campo `widgets?: Array<"guiaBancario" | "comparadorBacen" | ...>` (ou, mais
simples, um mapa `componentesExtras?: string[]` resolvido contra um registry central
`{ guiaBancario: GuiaBancario, ... }` em `RamoBase.tsx`). Isso reduz a superfície de 25 propriedades
+ 25 condicionais para 1 propriedade + 1 loop, e um teste único (`todo componentesExtras[i] existe no
registry`) substitui a necessidade de lembrar de tocar 3 arquivos por ramo novo. Não é um problema
hoje — é o tipo de coisa que vale a pena antes do ramo #20, não antes do #15.

Os 14 componentes `Guia*` (`GuiaBancario.tsx` … `GuiaTributario.tsx`, 226 a 865 linhas cada, ~5.700
linhas somadas) seguem o mesmo padrão estrutural (componente `Sec` colapsável + conteúdo estático em
JSX) — não há duplicação de *lógica* preocupante (é conteúdo, não código), mas a repetição do
componente `Sec` em cada arquivo (visto em `GuiaCivil.tsx:10-38` e replicado, por inspeção do padrão,
nos demais) é candidata óbvia a virar um componente compartilhado único em vez de copiado 14 vezes —
não teve tempo de confirmar se já existe um `Sec` compartilhado em `components/UI.tsx` que os Guias
deveriam estar usando em vez de redefinir; vale checagem rápida em revisão futura.

---

## 5. Sugestões priorizadas

1. **Corrigir §3.2 (RBAC da rota-filha)** — é o único achado com superfície de segurança real, mesmo
   atenuado pelo escopo de ownership. Adicionar `roles: ROLES.juridico` a
   `moduleRegistry.tsx:413-422` é uma linha; decidir e alinhar o comportamento dos `GET` de listagem
   em `ramos.py` é a parte que precisa de decisão consciente (ver §6).
2. **Corrigir §3.3 (banner de homologação obsoleto)** — baixo custo, alto valor de confiança: o
   trabalho de homologação já foi feito (§2.3) e a UI está sabotando a comunicação desse trabalho.
3. **Adicionar `licitacoes` a `AREAS_FALLBACK` (§3.1)** e considerar um teste de paridade
   `CaseArea` (backend) ↔ `AREAS_FALLBACK` (frontend) para essa classe de divergência não voltar.
4. **Remover o card duplicado de prescrição penal (§3.4)** — o backend já fez a parte difícil.
5. **Adicionar `indigo` a `COR_BORDA` (§3.5)** — cosmético, uma linha.
6. Informativo: **11 áreas sem ferramenta dedicada (§2.2)** — não é bug, é dado para priorização de
   produto; decisão do titular sobre quais (se algumas) merecem hub próprio.

---

## 6. Riscos residuais, limitações e pontos que exigem decisão humana

- **Não fiz perícia jurídica de mérito em cada uma das 56 calculadoras homologadas** (fórmulas de
  verbas rescisórias, prescrição, juros, custas etc.) — validei que o *processo* de homologação
  (matriz + testes de regressão por fase) existe e está sendo seguido, não que cada fórmula está
  juridicamente correta hoje. Isso exigiria revisão por área do direito, idealmente pelo próprio
  advogado responsável por cada ramo — está fora do escopo de uma auditoria de código.
- **Não validei renderização visual no navegador** — só análise de código/config, como a auditoria
  externa já registrou como limitação própria dela (`parte-05...md:106`). Recomendo `app-runner`
  como próximo passo se o titular quiser confirmar visualmente os achados de UI (§3.3, §3.5).
  Não subi a stack; convite explícito para o titular ou próxima sessão, não uma execução minha.
- **§3.2 tem uma decisão de produto embutida, não só técnica:** deve financeiro/secretaria conseguir
  *ler* dados específicos de ramo (tipo de matéria, valor de contrato, CNPJ) para casos aos quais já
  têm acesso pelo sistema geral? Se sim, o comentário do código está errado e deve ser corrigido para
  não prometer um 403 que não acontece. Se não, é o backend que precisa do gate, não só o frontend.
  Não decidi por conta própria — reportando para decisão do titular.
- Três subagentes de exploração paralela (frontend, backend, contrato) caíram por limite de sessão
  antes de entregar achados; este relatório foi refeito manualmente, arquivo por arquivo, via `grep`/
  leitura direta — mais lento, mas cada achado acima foi verificado eu mesmo no código, não herdado
  de resumo de agente.

## 7. Arquivos lidos (evidência do método)

`frontend/src/pages/ramos/ramosConfig.ts` (completo, 3275 linhas), `RamoBase.tsx` (completo),
`camposCondicionais.ts`/`demonstrativo.ts` (referenciados), `taxonomiaAreas.test.ts`,
`ramosDaArea.test.ts`, `frontend/src/lib/areaCatalog.ts`, `frontend/src/config/moduleRegistry.tsx`
(trechos relevantes), `frontend/src/App.tsx` (bloco de rotas staff), `backend/app/routers/ramos.py`
(trechos relevantes, arquivo de 4542 linhas), `backend/app/services/homologacao_ferramentas.py`
(completo), `backend/app/models/case.py` (enum `CaseArea`), `backend/tests/test_paridade_ferramentas_
frontend.py`, `test_rbac_equipe_juridica_694.py`, `test_areas_atuacao_onda1.py` (cabeçalhos/docstrings),
`docs/auditoria/onda-2-limpeza.md`, `docs/auditoria/relatorios/parte-05-areas-visuallaw-extracao.md`.

**Comandos executados:** apenas leitura (`grep -n`, `sed -n`, `wc -l`) — nenhuma alteração de código
neste PR, é um relatório.
