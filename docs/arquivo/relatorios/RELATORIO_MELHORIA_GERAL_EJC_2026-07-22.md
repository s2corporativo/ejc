# Relatório Geral de Melhoria e Viabilidade — EJC v3

**Data:** 2026-07-22
**Natureza:** documento único de melhoria geral, unificando (a) a avaliação técnica ao vivo desta sessão — 6 dimensões testadas em paralelo com stack de pé, suíte executada e navegação no browser — e (b) o veredito técnico-jurídico de homologação (H01–H15, notas por dimensão, esteira de protocolo estrito).
**Ótica:** advogado detalhista que quer um sistema moderno, preciso, coerente, confiável e simples, com um núcleo de IA que entregue proposta confiável a ponto de exigir apenas revisão antes do protocolo.

> **Nota de método e reconciliação de números.** Este relatório funde três fontes: a medição ao vivo desta sessão, a evidência do CI do projeto e o roteiro formal de homologação (ainda pendente). Onde os números pareciam divergir, eles se reconciliam e se validam mutuamente: **3.213** testes backend (suíte rápida, sem banco) **+ 114** testes `*_dblevel.py` (só rodam com Postgres no CI) = **3.327** (CI completo); **98** tabelas ORM **+ ~33** tabelas raw-SQL sem model = **131** tabelas no banco real. Onde uma afirmação vem do inventário arquitetural do projeto (e não foi remedida ao vivo), isso está sinalizado.

---

## 1. Conclusão principal

**O EJC é viável e deve ser continuado, não reconstruído.** A base já ultrapassou o estágio de protótipo: arquitetura estruturada, banco relacional com migrations, ampla cobertura automatizada, controle de acesso, núcleo central de IA, RAG, trilha de auditoria, geração documental, proteção de dados e procedimentos de continuidade — tudo verificado como **real** nesta sessão (a stack sobe limpa e o fluxo central do advogado é percorrível ponta a ponta).

**Porém, o EJC ainda não está comprovadamente pronto para operação jurídica integral**, nem pode ser considerado uma IA que entregue, em qualquer matéria, peça pronta para protocolo com mera revisão superficial. A classificação correta hoje é:

> **Sistema apto para homologação e piloto controlado, mas ainda não homologado para produção jurídica integral.**

O gargalo atual **não é capacidade** — é **consolidação, mensuração e homologação**. O próprio sistema é honestamente construído para **impedir** o carimbo automático enquanto a fundamentação não estiver validada — postura ética correta (OAB/anti-alucinação) que confirma o diagnóstico.

**Recomendação objetiva:**

- **continuar** o projeto;
- **congelar** temporariamente novos módulos;
- **consolidar** os fluxos existentes (eliminar duplicidades);
- **comprovar** a qualidade jurídica da IA com benchmark real;
- **executar** a homologação H01–H15;
- **iniciar** um piloto limitado a matérias padronizadas, em paralelo aos controles atuais.

---

## 2. O que foi efetivamente testado e verificado

### 2.1 Medido ao vivo nesta sessão (evidência de primeira mão)

- **Suíte de testes:** backend **3.213 passed, 0 failed, 0 erros de coleta** (114 skips são a camada de banco, por design); `ruff` limpo. Frontend: **186 testes** + typecheck verde + `vite build` gerando bundle; `npm ci` sem vulnerabilidades. **17/17** testes de integridade de rota.
- **Boot ao vivo (browser real):** stack subida (FastAPI + `alembic upgrade head` com 112 migrations/131 tabelas em Postgres 16 + pgvector + Vite), **476 respostas HTTP 200, zero 5xx, zero tracebacks**. Os 7 fluxos centrais navegados: login → troca de senha forçada → dashboard → cliente (PII cifrada, round-trip) → **caso pelo wizard, que já gera procuração + contrato como rascunho `human_reviewed=false`** → prazo (bucketing "≤7d" correto) → financeiro (KPIs, Estimador OAB) → portal do cliente (**isolamento em 3 vias, zero vazamento staff**).
- **Banco (Postgres real):** cadeia de migrations íntegra (1 head, 1 base, 107 revisions, branch reconciliado por merge); `upgrade head` limpo; drop destrutivo de PII (migration 112) exemplar (backfill antes do drop, sem perda de dados).

### 2.2 Confirmado no CI do projeto

- **3.327** testes backend + **77** subtestes; **186** frontend (31 arquivos); migrations em Postgres 16/pgvector; Ruff, Prettier, TypeScript, Vite, `pip-audit`, `npm audit` aprovados; Release Gate aprovado; inventário arquitetural aprovado; restauração cifrada em banco vazio no CI aprovada; smoke responsivo em Chromium aprovado.

### 2.3 Limitação indispensável (o que NÃO foi comprovado)

O boot ao vivo desta sessão foi um **smoke de caminho feliz** com dados fictícios, **sem** provedor de IA, **sem** cenários negativos de segurança e **sem** recuperação-após-falha. Ele **não** substitui a homologação formal. Portanto, continua correto afirmar:

- os **15 cenários jurídicos H01–H15** seguem **formalmente pendentes** na issue P0 de homologação;
- não há benchmark jurídico representativo comprovando a **qualidade das peças por área**;
- a **restauração real** (do Google Drive, ponta a ponta) e o **rollback real** (código antigo × banco migrado × arquivos) **não** foram demonstrados.

O que está provado é **cobertura automatizada forte + integridade estrutural + fluxo central percorrível**. O que falta é **homologação humana + mensuração jurídica + continuidade comprovada**.

---

## 3. Notas por dimensão (avaliação técnica, não certificação formal)

| Dimensão | Nota | Avaliação | Corroboração ao vivo (esta sessão) |
|---|---:|---|---|
| Base de engenharia | **8,7/10** | Robusta, versionada, bem testada | ✅ 3.213 testes verdes, build OK |
| Cobertura automatizada | **8,8/10** | Excelente — não substitui homologação | ✅ medida de forma independente |
| Arquitetura e coerência | **6,6/10** | Boa direção; legado e duplicidades | ✅ duplicidades e órfão confirmados |
| Simplicidade operacional | **7,2/10** | Menu melhorou; interna ainda excessiva | ✅ "poda por ocultação", ~77k linhas TSX |
| Segurança no código | **8,0/10** | RBAC, auditoria, PII cifrada | ✅ PII cifrada exemplar, JWT maduro |
| Segurança operacional | **6,0/10** | Backup/branch protection/2FA a decidir | ⚠️ kill-switch 2FA fail-open latente |
| Arquitetura da IA | **8,0/10** | Gateway, roteamento, governança | ✅ núcleo único, HITL, barreira LGPD reais |
| **Qualidade jurídica da IA** | **5,8/10** | Falta benchmark jurídico | ⚠️ base jurisprudencial vazia, citação só formato |
| Continuidade e recuperação | **5,8/10** | CI ok; recuperação real pendente | — não testável nesta sessão |
| Prontidão para piloto | **8,0/10** | Viável em escopo controlado | ✅ fluxo central percorrível ao vivo |
| Prontidão para produção integral | **6,2/10** | Bloqueada por riscos P0 | ⚠️ ver §10 |

---

## 4. Arquitetura — capacidade elevada, simplicidade incompleta

**Inventário arquitetural do projeto:** 5.493 itens; 85 páginas; 90 componentes React; 58 rotas; 163 routers; 810 endpoints; 233 serviços; 98 tabelas ORM; 2.098 funções Python; 1.221 funções TS/TSX; 492 classes Python. Classificados: 180 para consolidar, 208 para corrigir, 25 para renomear, 5 para redirecionar, 22 para excluir após migração; **4.858 ainda dependem de revisão humana conservadora** (marcar "manter" ≠ homologado).

**Diagnóstico:** o EJC não sofre por falta de funcionalidades. Seu risco é **muitas capacidades corretas em estruturas paralelas, sem uma experiência canônica única.**

**Duplicidades objetivas (convergência das duas auditorias):**
- `Dashboard.tsx` × `DashboardModern.tsx` (na verdade re-export intencional — verificar se pode colapsar);
- `data_room.py` × `data_room_v4.py` (v4 é stub incompleto);
- `peca_geracao.py` × `peca_geracao_router.py`;
- `sala_de_guerra.py` × `sala_de_guerra_v3.py`;
- `teses.py` × `teses_v4.py`;
- `google_drive.py` × `google_drive_service.py`.

**Achados adicionais confirmados ao vivo:**
- **Órfão real:** `frontend/src/pages/NotasFiscais.tsx` é código morto e o redirect `/nfse → /financeiro?tab=nfse` aponta para **aba inexistente** (NFS-e some em silêncio); o teste de rota não pega porque ignora o `?tab=`.
- **Cluster "Conhecimento" com 7 superfícies sobrepostas** (`knowledge-hub`, `biblioteca`, `memoria`, `wiki` + 3 abas).
- **`CasoDetalhe.tsx` com 4.293 linhas** — risco de manutenção concentrado.
- Campos processuais **legados em `Case`** coexistindo com a entidade canônica `Process` (dupla fonte de verdade); montagem central concentrada em `main.py`; navegação/RBAC/aliases concentrados em `moduleRegistry.tsx`.

**Julgamento:** arquitetura **recuperável e consolidável** — não há justificativa para recomeçar. Mas **não criar novas camadas** sobre essas estruturas antes de concluir as ondas de consolidação.

---

## 5. Design e simplicidade operacional

A organização por intenção (trabalhar um caso → pesquisar/IA → gerir o escritório → administrar) é correta, assim como o "Modo Essencial" com poucos destinos. Existem os dois caminhos de abertura de caso: guiado (`/casos/novo`) e manual sem IA (`/cadastro-manual`). A consolidação de prazos/tarefas/intimações na Central de Atividades é acertada.

**Problema restante:** a poda foi feita **ocultando** (30 rotas ocultas, aliases, "Mais Ferramentas"), **não removendo**. Resultado: **visualmente mais simples, estruturalmente ainda complexo** (~77 mil linhas de TSX mantidas).

**Modelo operacional recomendado** (o advogado deveria enxergar só isto):

- **Início:** prazos críticos · intimações pendentes · casos sem próxima ação · documentos aguardando revisão · peças aguardando aprovação · tarefas bloqueadas · compromissos do dia.
- **Casos** (workspace único por caso, com abas): 1) resumo e próxima ação; 2) cliente, partes e processos; 3) timeline; 4) documentos e provas; 5) fatos, riscos, estratégia e teses; 6) peças, revisão e protocolo; 7) prazos, tarefas e audiências; 8) honorários e pagamentos; 9) auditoria.
- **Agenda e Prazos:** central única para intimação · prazo · tarefa · audiência · compromisso · suspensão · providência · retorno ao cliente.
- **Pesquisa e IA:** pesquisa jurídica · análise avulsa · Raio-X · assistente · jurisprudência · legislação · biblioteca interna.

Data Room, Sala de Guerra, checklists, teses e ferramentas especiais devem aparecer **dentro do caso**, não como ilhas operacionais.

---

## 6. Os quinze fluxos obrigatórios (H01–H15)

Status formal do roteiro de homologação, **enriquecido** com a evidência ao vivo desta sessão (caminho feliz), que sobe alguns cenários de "não testado" para "feliz verificado, homologação formal pendente":

| Fluxo | Estado | Ponto crítico | Evidência ao vivo desta sessão |
|---|---|---|---|
| **H01 — Login, 2FA e sessão** | 🟡 | Desativação de 2FA em PR aberto exige nova homologação | ✅ login + troca de senha forçada OK; 2FA obrigatório confirmado no código |
| **H02 — Cliente, conflito e carteira** | 🟡 | Falta matriz completa de acessos negativos | ✅ criar/listar cliente com PII cifrada OK; negativos pendentes |
| **H03 — Documento → caso assistido** | 🟡 | Provar retomada após falha e não-duplicidade | ⚠️ extração por IA precisa de provedor (não testado) |
| **H04 — Cadastro manual** | 🟡🟢 | Usabilidade a homologar | ✅ wizard 2 passos + rota manual existem |
| **H05 — Processo principal e acessórios** | 🟡 | Campos legados em `Case` × `Process` canônico | ⚠️ drift confirmado |
| **H06 — Intimação, prazo, tarefa, agenda** | 🟡🔴 | "Próxima ação" e saúde operacional não integradas | ✅ criar prazo + bucketing OK; próxima-ação é o gap |
| **H07 — Prova, estratégia, tese, peça** | 🔴 p/ protocolo | Qualidade jurídica e citações não homologadas | ⚠️ **confirmado: jurisprudência não sai pronta** (ver §7) |
| **H08 — Audiência e atendimento** | 🟡 | Continuidade ata → providências → timeline | — não testado |
| **H09 — Honorários e pagamentos** | 🟡 | Parcelas, conciliação, cancelamento | ✅ tela/KPIs abrem; transações não testadas |
| **H10 — Raio-X e conversão** | 🟡 | Converter sem duplicar entidades | ⚠️ precisa de IA |
| **H11 — DataJud e impacto cognitivo** | 🟡 | Indisponibilidade, dedup, impacto controlado | — opt-in, off por default |
| **H12 — Portal do cliente** | 🔴→🟡 | IDOR/segregação por comprovar | ✅ **isolamento em 3 vias verificado ao vivo**; matriz IDOR completa pendente |
| **H13 — Backup e restauração** | 🔴 | Restore de CI passou; do Drive real pendente | — não testável nesta sessão |
| **H14 — Deploy e rollback** | 🔴 | Rollback com banco/migrations reais não comprovado | — não testado |
| **H15 — Usabilidade e desempenho** | 🔴 | Só login responsivo; falta nos fluxos jurídicos | ✅ UX polida ao vivo (screenshots); perf formal pendente |

O roteiro define corretamente critérios de aprovação e suspensão. **Enquanto H01–H15 não fecharem, o EJC não deve substituir integralmente os controles atuais.**

---

## 7. Núcleo de IA jurídica

### 7.1 Pontos fortes (maduros — preservar)

Gateway único de IA (nenhum módulo chama modelo direto); roteamento por tipo/complexidade da tarefa; modelos fortes para tarefa jurídica séria (produção usa Claude Opus 4.8); fallback controlado com registro de modelo/provedor/custo/tokens/duração/motivo; modo local completo; pseudonimização reversível para provedor externo + reidratação local; logs sem PII real; estrutura FIRAC; distinção fato/inferência/lacuna/decisão humana; crítica adversarial ("Duas IAs"); verificador de citações; **barreira LGPD centralizada** (fonte única, não contornável pelo caminho normal); roteador corrigido para não rebaixar silenciosamente tarefa séria a modelo rápido. Governança HITL genuína: toda saída nasce `is_rascunho=True, requer_revisao=True`; **não há caminho de auto-aprovação por IA**.

### 7.2 O problema fundamental: a arquitetura é mais madura que a comprovação jurídica

O EJC tem harness de avaliação (`app/eval/`) capaz de medir `hit@k`, precisão, recall, MRR, citações não confirmadas e groundedness. **Mas o CI roda principalmente o modo `--smoke`** (valida formato dos gold sets, sem banco e sem modelo real). É necessário, mas **não demonstra que a resposta jurídica está correta**.

### 7.3 Onde a IA para (achados confirmados no código)

1. **A base jurisprudencial nasce vazia.** Ingestores STJ/TJMG/DJEN/LexML vêm **todos desligados** (`base_juridica_seed.py:53-59`). Consequência dupla: a etapa "baseado exclusivamente no RAG" não tem precedentes reais, **e** o gate `_bloquear_jurisprudencia_nao_validada` (`legal_docs.py`) **bloqueia qualquer peça que cite julgado não validado** → a peça **não sai com jurisprudência pronta**.
2. **A verificação confere existência, não pertinência.** `_existe_sumula`/`_existe_artigo` confirmam que o número existe — **não** que sustenta a tese. Citação real porém impertinente **passa** no gate.
3. **A base de conhecimento (`bíblia_ejc`) é 100% FICTÍCIA por design** (~398 registros; README: "Todo o material é FICTÍCIO"; `ficticio=true`). Usada só como **esqueleto estrutural**, excluída da fundamentação — ótima para estilo, nula como autoridade.
4. **`score_juridico` e `indice_risco` estão vazios** (só `__init__.py`); o score que libera o protocolo é **heurística por regex**, não jurimetria de desfechos.
5. **Legislação real (lei seca) É recuperada** (~20 códigos federais chunkados por artigo), **mas o seed é OFF no boot** (garantido só no deploy) — em ambiente novo a fundamentação nasce fina.
6. **Dependência de provedor externo pago:** default `anthropic,maritaca,groq,ollama` com `OLLAMA_ENABLED=false`; **sem `ANTHROPIC_API_KEY`, o núcleo fica indisponível** (degrada, não produz). PII sai do VPS **pseudonimizada**, não "nunca sai".

### 7.4 Riscos jurídicos do uso atual

- **Falsa sensação de fundamentação** (lei seca presente, jurisprudência ausente → peça parece completa e é rasa);
- **citação existente porém impertinente** passa no gate (pertinência é 100% humana);
- **modo estrito de citações desligado** (`CITACOES_MODO_ESTRITO=False`) porque, com base incompleta, ligá-lo bloquearia citações reais ainda não ingeridas — o gate opera na configuração mais permissiva.

---

## 8. É possível o advogado apenas revisar e protocolar?

**Sim, com escopo controlado** — casos repetitivos, documentos padronizados, teses consolidadas, notificações/requerimentos administrativos, peças de consumo bem documentadas, contratos com checklist fechado, impugnações recorrentes, casos com fatos e provas estruturados.

**Não de forma universal** — em criminal, tributário, ambiental, societário, recuperação judicial, fatos controvertidos, prova incompleta, risco elevado ou entendimento local mutável, a revisão continuará substancial. Nenhum sistema juridicamente responsável deve prometer peça pronta para protocolo só porque um modelo forte gerou texto.

> Meta correta: **reduzir a revisão humana sem reduzir a responsabilidade, a profundidade ou a rastreabilidade jurídica.**

---

## 9. Esteira obrigatória de "Protocolo Estrito"

Toda peça destinada a protocolo deveria passar por esta sequência (e a IA precisa poder concluir *"não há elementos suficientes para uma peça segura"* — recusa tratada como comportamento **correto**):

1. extração documental;
2. fatos confirmados, alegados e contraditórios;
3. informações faltantes (expressas);
4. árvore de questões jurídicas;
5. mapa de pedidos, ônus e provas;
6. recuperação de fontes autorizadas;
7. confirmação de vigência e aderência;
8. tese principal;
9. teses subsidiárias;
10. contra-argumentos previsíveis;
11. primeira minuta;
12. crítica adversarial (segundo agente/modelo);
13. verificação de artigos, súmulas e precedentes;
14. checklist determinístico (competência, rito, prazo, partes, pedidos, valor, anexos);
15. nível de confiança por seção;
16. aprovação humana registrada;
17. exportação para protocolo.

**Estado no código:** as etapas 1, 2, 5, 8–11, 12 (crítica adversarial) e 16 já existem no pipeline (`peca_service.py`, `legal_docs.py`); as etapas 6–7 e 13 existem mas **operam sobre base vazia/verificação só-formato** (o elo fraco); as etapas 3, 4, 14 e 15 são **parciais** (o "score" heurístico faz as vezes do checklist 14/15). Fechar 6–7, 13, 14 e 15 é o que converte "rascunho assistido" em "protocolo estrito".

---

## 10. Pontos críticos priorizados

### P0 — bloqueadores (antes de produção integral)

1. **Homologação H01–H15** — executar os 15 cenários com massa fictícia, acessos negativos, retomada após falha e IDOR. Enquanto pendente, o EJC não substitui integralmente os controles atuais.
2. **Backup real e restauração ponta a ponta** — credencial dedicada na VPS, upload cifrado no Drive, download, descriptografia, `pg_restore`, recuperação de uploads, boot da app restaurada; definir **RPO/RTO**. (CI só provou restore em banco vazio.)
3. **Proteção administrativa da `main`** — PR obrigatório, checks obrigatórios, bloqueio de push/force-push direto, resolução de conversas, branch atualizada antes do merge.
4. **Qualidade jurídica da IA** — gold sets jurídicos representativos por área + execução real do benchmark (não só `--smoke`) antes de chamar qualquer peça de "pronta".
5. **Portal do cliente** — não liberar amplamente antes da **matriz completa de IDOR/segregação** (o isolamento básico foi verificado ao vivo; a matriz exaustiva, não).
6. **Rollback real** — demonstrar compatibilidade entre código antigo, banco migrado e arquivos persistidos (não basta voltar a imagem Docker).
7. **Não ativar o kill-switch de 2FA** como está — ele nasce **fail-open** e **contorna até o TOTP de quem já cadastrou** (senha vazada = acesso pleno). *O 2FA hoje segue obrigatório para superadmin/admin/socio; a desativação está só preparada em workflow, não mesclada.*
8. **Armadilha de go-live `ADMIN_EMAIL`** — domínio reservado (ex.: `.local`) trava o login em 422 e **deixa o admin inacessível**; endurecer a validação no seed/config.

### P1 — riscos altos

- **Duplicidades estruturais** e **dupla fonte `Case` × `Process`**; **timeline não consolidada**; **"próxima ação" não integrada**; migrations concorrentes; `CasoDetalhe` excessivamente acoplado.
- **Endurecer o gate de caso órfão** (`ownership.py:64`) — hoje libera sub-recursos de caso sem responsável a **qualquer usuário interno**.
- **Exigir 2FA de `advogado`/`advogado_auxiliar`** (hoje só superadmin/admin/socio).
- **Banco:** tornar downgrades 032/033 **idempotentes** (`DROP ... IF EXISTS`); **ligar no CI a checagem de drift ORM↔banco** (Camada 2 de `test_schema_sync.py` com `pgvector/pgvector:pg16`) — hoje um `autogenerate` cego dropariam 13 colunas **vivas** e removeria a unicidade de `ix_users_email`; a guarda `include_name` protege tabelas, **não colunas**.
- **Embedding versionado:** o log de testes registra que o `multilingual-e5-large` **mudou o pooling de CLS para média** — isso altera embeddings e a ordenação do RAG entre versões. **Fixar a versão** ou versionar o comportamento explicitamente; limpar a coluna/índice `embedding_legacy_768` após validar a reindexação 1024.
- **Chave Fernet efêmera:** com `VAULT_MASTER_KEYS` ausente, gera-se chave **efêmera** (aviso observado ao vivo). Em ambiente persistente a chave precisa ser **estável**, sob pena de credenciais cifradas ficarem irrecuperáveis após reinício.
- **Dependência de fontes externas**; ausência de métricas operacionais aprovadas.
- **Corrigir `/nfse`** (aba inexistente + órfão `NotasFiscais.tsx`); **empacotamento** (`pip install` não completa em Debian limpo por `http-ece`/`pywebpush`).

### P2 — qualidade / simplicidade / dívida

- Consolidar cluster "Conhecimento" (7 → 1); quebrar `CasoDetalhe.tsx`; converter rotas ocultas em **remoção real**, não ocultação.
- Interceptor global de 403 em `api.ts` (UX coerente de permissão).
- Antivírus em uploads; teto de lockout por IP compartilhado; **remover o workflow que desliga 2FA** após a decisão.
- Substituir o "score" heurístico por **rubrica auditável por seção**; deixar claro na UI que é controle de qualidade **formal**, não predição de êxito.

---

## 11. Melhor rota de evolução

**Etapa 1 — congelar novos módulos.** Nada de novas páginas/routers/tabelas antes da consolidação. Funcionalidade nova entra como **ação/aba/etapa/ferramenta contextual** dentro de um domínio existente.

**Etapa 2 — concluir as ondas arquiteturais.** Consolidar Data Room e Teses; Sala de Guerra canônica; **timeline única**; saúde operacional do caso; painel contextual; saúde da carteira no Dashboard; convergir as fachadas de IA/geração de peças para **contratos únicos**.

**Etapa 3 — não criar outra ilha de chat.** A "Análise de Caso IA" deve ser integrada (aba **Estratégia e IA** no caso; **Pesquisa e IA** para avulsa; **Raio-X** antes da abertura), mudando de estado **avulsa → Raio-X → caso** sem copiar/duplicar.

**Etapa 4 — três modos claros.**
- **Operacional** (sem IA): cadastro, documentos, prazos, agenda, tarefas, financeiro.
- **Assistido** (IA sugere): classificação, resumo, cronologia, pendências, riscos, rascunhos.
- **Protocolo estrito** (§9): esteira completa de verificação, crítica adversarial, fontes, checklist e aprovação.

**Etapa 5 — próxima ação obrigatória.** Todo caso ativo tem: próxima ação · responsável · data-alvo · urgência · bloqueio · origem · critério de conclusão. O Dashboard responde: (1) o que vence; (2) o que está bloqueado; (3) quem precisa agir; (4) qual caso exige atenção agora.

**Etapa 6 — abastecer o cérebro jurídico (o caminho para o "só revisar", em ciclo *eval-driven*, uma variável por vez):** ingerir e curar **jurisprudência real validada** → **verificação semântica de pertinência** de citação → ampliar súmulas + doutrina/temas repetitivos + garantir seed de legislação no boot → definir **postura de provedor** explícita (Anthropic com DPA/LGPD documentado **ou** stack local com modelos maiores, sinalizando ao advogado a origem) → substituir o score heurístico por rubrica auditável.

---

## 12. Decisão de viabilidade e veredito final

- **Continuar ou abandonar?** **Continuar.** Recomeçar desperdiçaria milhares de testes, a arquitetura de segurança, banco e migrations, os módulos jurídicos, o gateway de IA, o RAG, as integrações e a auditoria.
- **Liberar para piloto?** **Sim, após fechar os P0 de governança e continuidade** — controlado, primeiro com dados fictícios, depois casos selecionados, limitado a matérias padronizadas, em paralelo aos controles existentes, com protocolo sempre aprovado pelo advogado.
- **Liberar para produção integral?** **Ainda não.**
- **IA pronta para "só revisar"?** **Ainda não de forma geral** — alcançável após gold sets jurídicos representativos, benchmark real, homologação por área, protocolo estrito, validação de fallbacks e acompanhamento dos primeiros casos.

> **O EJC é um produto juridicamente promissor, tecnicamente robusto e economicamente viável. Seu gargalo atual não é capacidade; é consolidação, mensuração e homologação.** A prioridade não deve ser torná-lo **maior**, e sim torná-lo **mais canônico, menos redundante, mensurável, previsível, recuperável, juridicamente verificável e simples para o advogado.**

---

*Relatório de melhoria geral consolidando a avaliação técnica ao vivo (suíte executada, stack navegada no browser, Postgres+pgvector real) e o veredito técnico-jurídico de homologação (H01–H15, notas, protocolo estrito). Avaliação somente-leitura sobre o código; nenhum comportamento de produção foi alterado.*
