# EJC — Auditoria de Rotas, Fluxos e Design
## Parte 6 — Consolidação técnica e plano de correção priorizado

**Sistema:** Ecossistema Jurídico Clovis (EJC) — `https://ejc.depaulateixeira.adv.br`
**Sessão autenticada:** `soares@depaulateixeira.adv.br` (perfil advogado)
**Data/hora do teste:** 2026-07-29, 06h00–06h30
**Escopo:** auditoria transversal de (1) rotas — frontend e API; (2) fluxos — jornadas ponta a ponta do usuário; (3) design — consistência visual, acessibilidade e arquitetura de informação. Este documento consolida evidências das Partes 1–5 com testes adicionais realizados nesta rodada e apresenta um plano de correção único e priorizado.

---

## 1. Resumo executivo

| Dimensão | Nota geral | Achado mais grave |
|---|---|---|
| Rotas | Estrutura sólida, com falhas de consistência taxonômica e de mensagens de erro | Rotas administrativas de autodiagnóstico (`/system-modules/mapa`, `/diagnostico/central`, `/trash/`) existem mas são inacessíveis ao perfil advogado — inclusive para o próprio advogado consultar seu histórico de exclusão |
| Fluxos | Fluxos de criação funcionam bem; fluxos de finalização estão quebrados | Pipeline validação → aprovação → PDF/protocolo permanece bloqueado (achado da Parte 5, reconfirmado aqui como falha estrutural de fluxo, não apenas de endpoint isolado) |
| Design | Base de componentes consistente, mas dois sistemas de cor coexistindo e cobertura de acessibilidade parcial | 65% dos módulos de frontend (44 de 68 bundles) não possuem nenhum atributo `aria-*` |

Esta parte não repete integralmente os achados já documentados nas Partes 1–5 — remete a eles onde aplicável — e concentra-se em (a) organizar tudo o que já foi levantado sob a ótica de rotas/fluxos/design, (b) acrescentar evidências novas obtidas nesta rodada (testes de comportamento de rota inválida, teste do módulo `Lixeira`/`trash`, análise de paleta de cores e de cobertura de acessibilidade no CSS/JS de produção) e (c) entregar um plano de correção único, priorizado e com sugestão técnica de implementação para cada item.

---

## 2. Auditoria de Rotas

### 2.1 Inventário

- **Frontend:** 54 páginas/módulos carregados sob demanda (lazy-loading) pelo roteador React, mapeados na Parte 1 e reconfirmados nesta rodada via inspeção dos 68 arquivos de bundle publicados (`/tmp/ejc_assets`, correspondência 1:1 entre bundle e módulo funcional, com alguns módulos internos sem rota própria — ex. `CaseBreadcrumb`, `UI`).
- **Backend:** mais de 100 endpoints REST sob `/api/v1/`, varridos sistematicamente na Parte 3 (autenticação, casos, clientes, prazos, peças, honorários, IA/skills, checklists, prompts, etiquetas, visual-law, entrada-universal, trash, system-modules, diagnóstico, sociedade, etc.).

O próprio sistema já possui uma ferramenta interna de auditoria cruzada de rotas — o módulo **Mapa de Módulos** (`GET /system-modules/mapa`), que compara rotas do frontend com endpoints registrados no backend e sinaliza divergências com status `ativo/beta/legado/oculto`. **Esta rodada tentou consultá-lo diretamente e confirmou que ele está bloqueado para o perfil advogado:**

```
GET /api/v1/system-modules/mapa → 403
{"detail":"Acesso negado. Perfis permitidos: superadmin, admin, socio"}

GET /api/v1/diagnostico/central → 403
{"detail":"Acesso negado. Perfis permitidos: socio"}
```

**Recomendação de método:** um usuário com perfil `sócio` ou `admin` deve rodar esse módulo diretamente — ele é uma fonte de verdade mais confiável do que qualquer inferência externa feita por engenharia reversa de bundle, como a que sustenta este relatório. Sugiro que essa seja a primeira ação prática após a leitura deste documento.

### 2.2 Comportamento de rotas inválidas — testado nesta rodada

| Cenário | Resultado | Avaliação |
|---|---|---|
| Rota de API inexistente (`GET /api/v1/rota-que-nao-existe`) | `404 {"detail":"Not Found"}` | Correto, padrão FastAPI |
| Caso com UUID válido mas inexistente | `404 {"detail":"Caso não encontrado"}` | Correto, mensagem localizada |
| Caso com ID malformado (não-UUID) | `404 {"detail":"Caso não encontrado"}` | **Impreciso**: tecnicamente deveria ser `422 Unprocessable Entity` (formato inválido), não `404` (recurso inexistente) — são falhas semanticamente distintas. Não é um risco de segurança (não vaza informação), mas dificulta diagnóstico automatizado por quem integra com a API |
| Requisição sem token a rota protegida | `401 {"detail":"Token de autenticação não fornecido"}` | Correto e claro |
| Rota de frontend inexistente (SPA) | `200 OK`, HTML da aplicação | Comportamento padrão de SPA (fallback para `index.html`); **confirmado nesta rodada que existe um componente `NotFound` dedicado no bundle** (`NotFound-DhKqcmwb.js`), o que indica que o roteador React trata rotas desconhecidas com uma tela apropriada — porém a resposta HTTP em si permanece `200` para qualquer URL, o que já havia sido sinalizado na Parte 1 a propósito do `robots.txt` (que também recebe o fallback SPA em vez de um arquivo real) |

### 2.3 Inconsistências taxonômicas já documentadas (Partes 1 e 5)

- **Duplicação da lista de áreas de atuação em 5 módulos** (`CadastroManual`, `FinanceiroWorkspace`, `RaioXProcesso`, `RamoBase`, `RamosHub`) em vez de importar do catálogo central `areaCatalog` — risco de desalinhamento silencioso quando uma área for adicionada/renomeada no catálogo central e os módulos duplicados não forem atualizados junto.
- **"licitacoes" classificada como área de atuação de primeiro nível** no backend, ao lado de "administrativo" — confirmado na Parte 5 como inconsistência taxonômica (licitação é procedimento da Administração Pública regido pela Lei nº 14.133/2021, tipicamente subárea do Direito Administrativo, não ramo autônomo).

### 2.4 Rotas com controle de acesso bem aplicado, porém pouco descobríveis

O módulo **Lixeira** (`GET /trash/?entidade=...`, `POST /trash/{entidade}/{id}/restaurar`) — testado nesta rodada — confirma a existência de um mecanismo formal de soft-delete/restauração no sistema, mas também está restrito a `superadmin/admin/socio`:

```
GET /api/v1/trash/?entidade=casos → 403
{"detail":"Acesso negado. Perfis permitidos: superadmin, admin, socio"}
```

Isso **resolve uma ambiguidade** deixada em aberto nas Partes 3–5 ("por que o advogado não consegue excluir casos/clientes definitivamente?"): a resposta é que existe, sim, um fluxo de exclusão lógica → lixeira → exclusão definitiva, mas ele é uma responsabilidade de governança reservada a sócio/admin por desenho, e não uma lacuna de funcionalidade. Isso é uma decisão de segregação de função **defensável do ponto de vista de compliance** (evita exclusão acidental ou não auditada de prova documental por qualquer advogado), mas tem um custo de UX: o advogado que cria dados de teste ou registros incorretos não tem, hoje, nenhuma indicação na interface de que precisa acionar um sócio para a exclusão definitiva — ele só descobre isso ao tentar e receber um 403. Recomenda-se **tornar esse fluxo explícito na tela** (ex.: botão "Solicitar exclusão definitiva" que already visível ao advogado, mas que dispara uma notificação/aprovação ao sócio, em vez de simplesmente não expor a ação).

### 2.5 Correções sugeridas — Rotas

| # | Achado | Ação corretiva sugerida | Prioridade |
|---|---|---|---|
| R1 | Módulos de autodiagnóstico (Mapa de Módulos, Central de Diagnóstico) só acessíveis a sócio/admin | Sem alteração de permissão (correto por desenho) — mas **agendar execução periódica** desses módulos por um sócio/admin como rotina de manutenção (ex.: mensal), documentando resultado | Alta (ação administrativa, não técnica) |
| R2 | ID malformado retorna 404 em vez de 422 | Adicionar validação de formato de UUID no nível de path parameter (Pydantic/FastAPI `UUID` type na assinatura da rota), retornando 422 nativamente antes de consultar o banco | Baixa |
| R3 | `robots.txt` e qualquer URL inválida retornam 200 com o SPA | Servir `robots.txt` estático via Nginx com `Disallow: /` antes do fallback do SPA | Baixa (já registrada na Parte 1) |
| R4 | Catálogo de áreas duplicado em 5 módulos | Refatorar os 5 módulos para importar `areaCatalog` único; remover as listas locais | Média |
| R5 | "licitacoes" como área de primeiro nível | Reclassificar como subárea/tag de "administrativo" no enum do backend | Média |
| R6 | Fluxo de exclusão definitiva (Lixeira) não é descoberto pelo advogado até o 403 | Adicionar affordance na interface indicando que a exclusão definitiva requer aprovação de sócio, com botão de "solicitar" em vez de ausência de opção | Média |

---

## 3. Auditoria de Fluxos

Fluxos testados ponta a ponta nas Partes 3–5, reorganizados aqui por jornada completa com status consolidado.

### 3.1 Fluxo de autenticação e sessão

`POST /auth/login` → JWT válido por 8h → navegação autenticada. 2FA disponível (`Configurar2FA`) mas **não habilitado por padrão** para o usuário de teste (achado da Parte 3). Gestão de sessões ativas (`GET /auth/sessions` ou equivalente) apresenta inconsistência na flag "sessão atual" (Parte 2). **Status: funcional, com dívida de segurança (2FA opcional) e um bug cosmético (flag de sessão atual).**

### 3.2 Fluxo de criação de caso

Dois caminhos observados, com comportamento **divergente**:

- **Caminho direto** (`POST /cases/`): funciona corretamente, incluindo persistência de `descricao_fatos` — reconfirmado nas 25 criações da Parte 5. Bug pontual: título com colchetes quebra o parser de IA (Parte 5, R-título).
- **Caminho via Sala Jurídica → conversão** (`POST /sala-juridica/{id}/converter`): **perda de dados confirmada na Parte 3** — fatos e evidências levantados na conversa não são transferidos ao caso resultante, forçando o advogado a redigitar o que a IA já havia estruturado. Este é o fluxo mais "vendido" como diferencial de produto (conversa natural → caso estruturado) e é justamente o que está quebrado.

**Diagrama do problema:**
```
Sala Jurídica (conversa + fatos + evidências levantados)
        │
        ▼  POST /converter
   Caso criado  →  descricao_fatos = vazio/incompleto  ❌
```

**Status: fluxo crítico do produto parcialmente quebrado.**

### 3.3 Fluxo de geração e finalização de peça (o mais grave do sistema)

```
Gerar peça (IA)  →  Validar juridicamente  →  Marcar log como revisado/aplicado  →  Aprovar  →  Exportar PDF/Protocolar
     ✅                    ✅ (score 94/100)         ✅ (status "aplicado")            ❌              ❌ (bloqueado em cascata)
```

Causa raiz (detalhada na Parte 5, Seção 3.3): o campo `validacao_juridica.ai_log_id` no registro do documento nunca é preenchido, mesmo após validação e aplicação bem-sucedidas do log de IA. O endpoint de aprovação lê esse campo — não o log isoladamente — e por isso trava com `"Status atual: sem_validacao"` mesmo havendo um log de validação aplicado com score acima do mínimo exigido (75/100).

**Impacto no fluxo, não apenas no endpoint:** isso não é uma falha isolada de uma chamada de API — é a quebra do **elo entre duas etapas consecutivas de um único fluxo de negócio** (controle de qualidade → liberação para uso). Toda a jornada de 9 etapas do módulo `JornadaCaso` (Cliente → Triagem → Documentos → Inteligência → Estratégia → Produção → Revisão → Protocolo → Gestão, mapeada na Parte 1) fica interrompida na etapa "Protocolo", que depende deste pipeline. **Nenhum caso pode hoje avançar organicamente até o fim da jornada desenhada pelo próprio sistema.**

**Status: fluxo crítico bloqueado — prioridade máxima de correção (já sinalizada na Parte 5, reafirmada aqui como bloqueio de fluxo, não só de feature).**

### 3.4 Fluxo de extração e ingestão de documentos

```
Upload de arquivo → OCR/extração estruturada → Classificação por regra → Interpretação por IA → Pacote de peças
        ✅                    ✅                          ✅                      ❌ (indisponível)        ⚠️ parcial (memória de cálculo bloqueada)
```

Degradação segura confirmada (Parte 5): o sistema não inventa dados quando a IA está fora — preserva a extração determinística e sinaliza `requer_confirmacao_humana`. **Status: funcional em modo degradado, com uma etapa (interpretação por IA) indisponível de forma persistente.**

### 3.5 Fluxo de exclusão/limpeza de dados

```
Criar registro → Arquivar/inativar (advogado pode) → Lixeira (só sócio/admin) → Exclusão definitiva (só sócio/admin)
       ✅                    ✅                              🔒                          🔒
```

Confirmado nesta rodada (Seção 2.4). **Status: funcional e coerente com segregação de função, mas pouco descobrível na interface do advogado.**

### 3.6 Fluxo financeiro

`POST /fees/` corretamente bloqueado para advogado (`403`, mensagem clara e localizada: "Sem permissão para alterar dados financeiros"). **Status: segregação de função corretamente implementada, sem achados.**

### 3.7 Fluxo de publicação de prompts/checklists

```
Advogado cria prompt → publicado automaticamente para todo o escritório → advogado NÃO pode excluir a própria publicação (só sócio)
```

Assimetria já documentada na Parte 4: o advogado pode tornar algo visível a todos, mas não pode desfazer sozinho. **Status: funcional, porém com desenho de permissão assimétrico e mensagem de erro não localizada em pelo menos 2 pontos do fluxo (ver Seção 4.3).**

### 3.8 Correções sugeridas — Fluxos

| # | Achado | Ação corretiva sugerida | Prioridade |
|---|---|---|---|
| F1 | Pipeline validação→aprovação→PDF quebrado | Corrigir a gravação de `validacao_juridica.ai_log_id` no registro do documento imediatamente após `/validar` (ou fazer `/aprovar` consultar o log de IA diretamente por `case_id`/`documento_id` em vez de depender de um campo denormalizado que não é populado) | **Crítica** |
| F2 | Conversão Sala Jurídica → Caso perde fatos/evidências | Corrigir o mapeamento de campos no endpoint `/converter` para transferir integralmente `descricao_fatos` e evidências already extraídas da conversa | **Alta** |
| F3 | Interpretação por IA indisponível em `/entrada-universal/processar` | Verificar status do provedor de IA associado a essa rota no Painel de Provedores IA; considerar fallback automático para outro provedor configurado (já existe arquitetura multi-provedor no sistema) | Alta |
| F4 | Advogado não pode excluir prompt próprio nem template de checklist próprio | Permitir que o autor exclua o próprio conteúdo; restringir aprovação de sócio apenas à exclusão de conteúdo de terceiros | Média |
| F5 | 2FA disponível mas não habilitado por padrão | Avaliar exigir 2FA obrigatório para perfis com acesso a dados de clientes (política, não bug) | Média (decisão do escritório) |
| F6 | Fluxo de exclusão definitiva invisível ao advogado até o 403 | Ver R6 (Seção 2.5) | Média |

---

## 4. Auditoria de Design

**Limitação metodológica, reafirmada:** o ambiente desta auditoria bloqueia o acesso de rede do Chromium/Playwright a domínios externos, portanto **não foi possível capturar telas renderizadas** nem avaliar diretamente legibilidade, contraste percebido, responsividade ou hierarquia visual como um usuário veria. As conclusões desta seção baseiam-se em evidência objetiva extraída do CSS/JS de produção (paleta de cores declarada, atributos de acessibilidade presentes no DOM gerado, estrutura de componentes) — é uma auditoria de "design como código", não de design como experiência visual. Recomenda-se complementar esta seção com uma revisão visual direta em navegador pelo usuário ou por um agente com acesso de rede irrestrito.

### 4.1 Paleta de cores — dois sistemas coexistindo

Análise do bundle CSS de produção (`index-BoJ9k3Gp.css`, 171 KB) revela duas paletas distintas com uso significativo simultâneo:

- **Paleta "dourado/jurídico"** (aparente identidade de marca): `#d4af37` (dourado, 44 ocorrências), `#fff5e6` (creme, 52), `#8f7117`, `#e5ce7f`, `#3b2f0b`, `#6f5711`, `#181008`.
- **Paleta "azul/slate"** (padrão Tailwind CSS não customizado): `#2563eb` / `#3b82f6` (azul, uso combinado 33 ocorrências), `#0f172a` / `#101828` (slate-900), `#f8fafc` (slate-50), `#e5e7eb` (slate-200).

A coexistência de ambas em volume comparável sugere uma de duas situações: (a) uma customização de marca (dourado) foi aplicada a parte dos componentes/módulos, mas outra parte ainda usa as cores padrão do framework Tailwind não substituídas; ou (b) as duas paletas têm papéis distintos intencionais (ex.: dourado para identidade/branding, azul/slate para estados funcionais como links e texto neutro) — o que seria uma prática legítima, mas não há evidência no CSS de uma convenção documentada (design tokens nomeados) que confirme a intenção. **Recomenda-se auditoria visual direta para confirmar se a mistura é intencional; se não for, consolidar em um único design system com tokens nomeados (ex. `--color-primary`, `--color-accent`) em vez de valores hexadecimais soltos.**

### 4.2 Cobertura de acessibilidade

| Métrica | Resultado |
|---|---|
| Total de bundles de módulo/página analisados | 68 |
| Bundles com ao menos 1 atributo `aria-*` | 24 (35%) |
| Bundles sem nenhum atributo `aria-*` | 44 (65%) |

Módulos sem qualquer marcação de acessibilidade identificada incluem áreas de alto uso operacional: **Clientes, Checklists, Intimacoes, Auditoria, CadastroManual, DataJudBusca, GovernancaIA, Infosimples, JornadaCaso, Lixeira, Noticias**, entre outros. Módulos com cobertura identificada: `index` (shell/layout global), `Central`, `Dashboard`, `Configuracoes`, `GestaoDocumental`, `FinanceiroWorkspace`, `CasoDetalhe`.

Isso não prova, por si só, que os módulos sem `aria-*` sejam inacessíveis (podem herdar semântica de componentes de UI compartilhados que já possuem os atributos corretos, como o bundle `UI-DOfcrAzZ.js`, que registrou uso de `aria-hidden`) — mas é um indicador objetivo de risco de conformidade que deveria ser verificado com uma ferramenta de auditoria de acessibilidade em navegador real (axe-core, Lighthouse) antes de qualquer alegação de conformidade com WCAG 2.1, especialmente relevante para um sistema jurídico que pode vir a ser usado por profissionais com deficiência visual ou motora.

### 4.3 Consistência de mensagens de erro (achado de UX transversal, reconfirmado nesta rodada)

Testado nesta rodada especificamente para medir consistência:

| Endpoint | Mensagem de erro (403) |
|---|---|
| `POST /fees/` | `"Sem permissão para alterar dados financeiros"` — localizada, clara |
| `DELETE /prompts-juridicos/{id}` | `"Apenas sócios podem remover prompts"` — localizada, clara |
| `GET /system-modules/mapa` | `"Acesso negado. Perfis permitidos: superadmin, admin, socio"` — localizada, clara |
| `DELETE /checklists/templates/{id}` | `"Forbidden"` — **em inglês, sem explicação** |
| `GET /sociedade/distribuicao` | `"Forbidden"` — **em inglês, sem explicação, reconfirmado ativo nesta rodada** |

A maioria do sistema segue um padrão consistente de mensagens de erro em português, específicas e acionáveis — o que é uma boa prática de design de API e de UX (o frontend pode exibir a mensagem diretamente ao usuário). Os dois casos com `"Forbidden"` genérico quebram esse padrão e, na interface, provavelmente aparecem como um erro técnico não traduzido para o usuário final — inconsistência de baixo esforço de correção e alto valor de UX.

### 4.4 Arquitetura de informação e descobribilidade (Parte 1, reafirmada)

- Módulos de compliance/auditoria de IA (Auditoria, Governança da IA, Produtividade) são alcançáveis apenas por atalhos no Dashboard, fora do menu lateral principal — o próprio texto de ajuda do sistema admite isso. Esses são justamente os módulos que deveriam ter mais visibilidade para sócios/responsáveis por compliance.
- Existe um enum de status de módulo (`ativo/beta/legado/oculto`) já modelado no sistema (usado por `MapaModulos`), mas não aplicado visualmente nos itens de menu — um recurso pronto e subutilizado.

### 4.5 Correções sugeridas — Design

| # | Achado | Ação corretiva sugerida | Prioridade |
|---|---|---|---|
| D1 | Duas paletas de cor coexistindo sem tokens nomeados | Consolidar em um design system único com variáveis CSS nomeadas; confirmar visualmente antes de decidir qual paleta é a oficial | Média |
| D2 | 65% dos módulos sem atributo `aria-*` detectável | Rodar auditoria automatizada (axe-core/Lighthouse) em cada módulo listado na Seção 4.2 e aplicar correções mínimas de acessibilidade (labels em campos de formulário, roles em componentes interativos) | Média-Alta (depende de exposição a usuários com necessidades de acessibilidade) |
| D3 | Mensagens `"Forbidden"` não localizadas em 2 endpoints confirmados | Padronizar essas duas rotas para o mesmo formato `{"detail": "<mensagem em português, específica>"}` usado no restante da API | Baixa (esforço) / Média (valor de UX) |
| D4 | Módulos de compliance/auditoria de IA escondidos fora do menu principal | Adicionar entrada visível no menu lateral para Auditoria e Governança da IA, dado seu papel de compliance | Média |
| D5 | Enum de status de módulo (`ativo/beta/legado/oculto`) não é exibido na navegação | Renderizar badge de status nos itens de menu usando o enum já existente | Baixa |

---

## 5. Plano de correção consolidado — todas as dimensões, por prioridade

| Prioridade | Item | Dimensão | Esforço estimado* |
|---|---|---|---|
| **Crítica** | F1 — corrigir vínculo `ai_log_id` ↔ documento no pipeline de aprovação/PDF | Fluxo | Baixo–Médio (correção pontual de integração, alto impacto) |
| **Alta** | F2 — corrigir perda de dados na conversão Sala Jurídica → Caso | Fluxo | Médio |
| **Alta** | F3 — restaurar/monitorar interpretação por IA em extração de documentos | Fluxo | Baixo (se for configuração/credencial) a Médio (se for infraestrutura) |
| **Alta** | R1 — executar Mapa de Módulos/Central de Diagnóstico periodicamente (ação administrativa) | Rota | Baixo |
| **Média** | R4 — unificar catálogo de áreas em 5 módulos duplicados | Rota | Médio |
| **Média** | R5 — reclassificar "licitacoes" como subárea | Rota | Baixo |
| **Média** | R6 / F6 — expor fluxo de exclusão definitiva ao advogado | Rota/Fluxo | Baixo |
| **Média** | F4 — permitir autor excluir prompt/checklist próprio | Fluxo | Baixo |
| **Média** | D1 — consolidar paleta de cores em design tokens | Design | Médio (depende de confirmação visual) |
| **Média-Alta** | D2 — auditoria e correção de acessibilidade nos 44 módulos sem `aria-*` | Design | Alto |
| **Média** | D4 — expor Auditoria/Governança da IA no menu principal | Design | Baixo |
| **Baixa** | R2 — retornar 422 (não 404) para ID malformado | Rota | Baixo |
| **Baixa** | R3 — servir `robots.txt` real | Rota | Baixo |
| **Baixa** | D3 — localizar mensagens `"Forbidden"` residuais | Design | Baixo |
| **Baixa** | D5 — badge de status de módulo no menu | Design | Baixo |
| Decisão do escritório | F5 — tornar 2FA obrigatório | Fluxo | N/A (política) |

\* Estimativas de esforço são qualitativas, baseadas na natureza do problema observado externamente (ex.: um campo não populado tende a ser correção pontual; uma auditoria de acessibilidade em 44 módulos é necessariamente extensa). Não substituem uma estimativa de engenharia feita por quem tem acesso ao código-fonte.

---

## 6. Nota metodológica final

Todos os achados desta parte foram obtidos por chamadas diretas à API REST de produção com token JWT de sessão autenticada como advogado, e por análise estática dos bundles JavaScript/CSS servidos publicamente (não ofuscados). Nenhuma ferramenta de auditoria visual em navegador pôde ser executada devido a restrição de rede do ambiente desta sessão. Os achados de design (Seção 4) devem ser tratados como indicadores de risco a confirmar visualmente, não como veredito definitivo sobre a experiência final do usuário. Os achados de rotas e fluxos (Seções 2 e 3) são reproduções diretas de comportamento de API e, portanto, têm grau de confiança mais alto.

Recomenda-se, como próximo passo natural, que um usuário com perfil sócio/admin execute o módulo interno **Mapa de Módulos** (`Administração → Mapa de Módulos`) e a **Central de Diagnóstico**, que são as ferramentas de autoauditoria já construídas dentro do próprio EJC e mais confiáveis do que qualquer inferência externa — inclusive as apresentadas neste relatório.

---

*Documento produzido como parte da auditoria técnica solicitada. Deve ser lido em conjunto com as Partes 1 a 5 já entregues, das quais consolida e prioriza os achados sob a ótica de rotas, fluxos e design.*
