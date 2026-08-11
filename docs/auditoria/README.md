# Auditoria e plano de correção do EJC

Documentação produzida em auditoria técnica externa de 12 rodadas sobre o ambiente de produção
(`https://ejc.depaulateixeira.adv.br`), realizada em julho de 2026.

**Método da auditoria:** chamadas HTTPS diretas à API de produção com credenciais de advogado e de
superadmin, mais análise estática dos bundles JavaScript publicados. **Sem acesso ao código-fonte,
ao servidor por SSH, ou a navegador.** Isso delimita o alcance de tudo o que está aqui: os achados
são reproduzíveis pela API, mas as causas no código precisam ser confirmadas por quem tem o repositório.

**Atualização de agosto/2026:** as Partes 14 a 20 foram feitas **com** acesso ao código-fonte e
localizam causas, não só sintomas. A consolidação está em
`FECHAMENTO-auditoria-codigo-2026-08.md`. Um dos cinco achados destacados abaixo já foi resolvido por ela (a métrica de "chance de
êxito"); a correção do prefixo `/v1/` consta em "Retificações", não naquela lista.

---

## Por onde começar

**Se você vai executar o trabalho:** leia o `CLAUDE.md` na raiz do repositório, depois
`plano-lancamento-v3.md`. Nada mais é necessário para começar.

**Se você quer entender por que o sistema está assim:** leia `parecer-arquitetural.md`.

**Se quer a evidência de um achado específico:** procure em `relatorios/`.

---

## Os documentos

### `FECHAMENTO-auditoria-codigo-2026-08.md` — auditoria de CÓDIGO (agosto/2026)

Consolidação das Partes 14 a 20, a primeira leitura feita **com** o repositório em mãos. Lista
única de achados por severidade, o que foi resolvido de pendências antigas, o que está bom e deve
ser preservado, e as limitações do trabalho.

Diferente de tudo o que veio antes: as Partes 1 a 13 reproduziam sintomas de fora; estas localizam
causas no código, com evidência `arquivo:linha`.

### `plano-lancamento-v3.md` — PLANO ATIVO

O plano de execução até o início da operação. Sete blocos, cada um com o prompt pronto para colar
numa sessão do Claude Code. Uma sessão por bloco.

Organizado em torno de um único critério de sucesso: **um advogado leva um caso real do início ao
protocolo e considera que foi mais fácil do que fazer fora do sistema.**

É deliberadamente mais curto que o v2 — contém apenas o que precisa estar pronto **antes** do
primeiro caso real.

### `plano-correcao-v2.md` — backlog de referência

Todos os 40+ achados da auditoria, com evidência e passos de reprodução, organizados em fases.
Continua válido. O v3 aponta para ele quando um bloco precisa do detalhe técnico completo.

Contém, ao final, uma **Nota de Retificação** registrando um número que a v1 deste plano informava
errado (peças travadas: o correto é 22 de 23, não 97 de 98) e a origem do erro.

### `parecer-arquitetural.md` — crítica de produto

Opinião técnica sobre o que cortar, o que consertar, o que construir e o que já está bom.
Contém as recomendações mais duras: reduzir de 34 para ~10 módulos, remover o módulo
`diplomacia-v3`, abandonar jurimetria enquanto não houver histórico.

Também registra o que é genuinamente bom no sistema e deve ser amplificado — a crítica adversarial,
o validador de citações, a degradação segura da extração.

### `reduzir-atrito.md` — a análise da fricção

Contém a contagem real dos **15 passos atravessando 8 módulos** hoje necessários para levar um caso
ao protocolo, e as três mudanças que atacam isso: entrada única, o caso como espaço de trabalho, e
quatro estados no lugar de nove etapas.

Inclui o checklist de pré-operação e o método do "primeiro caso real".

### `relatorios/` — as 12 rodadas

| Arquivo | Conteúdo principal |
|---|---|
| `parte-01-analise-nao-autenticada.md` | Mapa de 54 módulos, postura de segurança, duplicação do catálogo de áreas |
| `parte-02-sessao-autenticada.md` | Divergência dashboard × listagens, 500 em `status=all`, OAB ausente |
| `parte-03-varredura-endpoints.md` | Varredura de ~100 endpoints, perda de dados na conversão Sala Jurídica → Caso |
| `parte-04-homologacao-ia.md` | Catálogo de 163 skills; **erro jurídico sobre decadência (CPC art. 487, II)** |
| `parte-05-areas-visuallaw-extracao.md` | 25 áreas testadas; **bug do pipeline de validação → PDF**; extração |
| `parte-06-rotas-fluxos-design.md` | Rotas, fluxos, paleta duplicada, acessibilidade |
| `parte-07-acesso-superadmin.md` | Mapa de Módulos e Central de Diagnóstico oficiais; **conta fictícia superadmin** |
| `parte-08-inteligencia-rag.md` | **0 de 47.359 chunks indexados**; cobertura crítica em 29 de 36 áreas |
| `parte-09-portal-financeiro-datajud.md` | **Métrica de "chance de êxito"**; financeiro vazio; portal não testado |
| `parte-10-hitl-e-item8.md` | **Provimento 205/2021 é norma de publicidade, não de IA** — citação incorreta na interface |
| `parte-11-apis-sincronizacao.md` | **DJEN nunca capturou nada**; prefixo `/v1/` duplicado; 15 calculadoras órfãs |
| `parte-12-falsos-positivos.md` | **11 falsos positivos** com 3 causas-raiz; retificação do número de peças |
| `parte-13-homologacao-dinamica.md` | Primeira homologação com stack real (Docker) e código-fonte; confirma os P0 do PR #652 em runtime; achado novo: `/legal-docs/{id}/validar` quebra com 500 sem provedor de IA e é isso que trava `/aprovar` |
| `parte-14-financeiro-prazos-intimacoes.md` | **Auditoria de código.** Termo inicial do prazo DJEN (art. 224 §2); recesso do art. 220 não aplicado; consolidado ignora pagamentos parciais; recorrentes sem motor |
| `parte-15-portal-assinaturas.md` | **Auditoria de código.** Chance de êxito NÃO vaza ao cliente; sem IDOR no portal; hash não reconferido ao assinar |
| `parte-16-notificacoes.md` | **Auditoria de código.** Sino é acumulador sem retenção (LGPD); `notificar()` comita a sessão do chamador; alertas de prazo são idempotentes |
| `parte-17-nfse.md` | **Auditoria de código.** Emite de verdade (Nuvem Fiscal); regime tributário e retenção de ISS fixos em código |
| `parte-18-gestao-societaria.md` | **Auditoria de código.** Sócio nível 7 altera participação de qualquer sócio sem trilha; 100% só validado na distribuição |
| `parte-19-estimador-oab-diagnostico.md` | **Auditoria de código.** Causa-raiz da contradição do `backup_offsite`; estimador sem citation gate |
| `parte-20-configuracoes-lixeira-apoio.md` | **Auditoria de código.** Desligar módulo só esconde o menu; lixeira sem purga definitiva (LGPD) |

---

## Os achados que não podem se perder

Se este material for lido por alguém com pressa, são estes cinco:

**A captura de intimações nunca capturou nada.** Zero registros em toda a história, com três painéis
reportando "ok". Só uma OAB monitorada, numa conta administrativa; os três advogados reais têm o
campo vazio. Risco de perda de prazo. *(Parte 11)*

**O pipeline de peças trava antes do protocolo.** O resultado da validação jurídica nunca é gravado
no documento, então aprovação e exportação de PDF ficam bloqueadas. Nenhuma peça foi protocolada em
toda a história do sistema. *(Partes 5 e 10)*

**A base de conhecimento da IA está vazia na prática.** 0 de 47.359 trechos indexados; 29 de 36 áreas
sem súmula, jurisprudência ou doutrina. *(Parte 8)*

**O sistema mente sobre os próprios números.** Dashboard informa "0 peças aguardando revisão" com
100% em rascunho; filtro `status=ativo` retorna vazio com 8 casos cadastrados. *(Parte 12)*

**~~Há uma métrica de "chance de êxito" ativa em produção.~~ RESOLVIDO — não vaza ao cliente.**
A métrica existe na tela do advogado, mas a auditoria de código confirmou duas barreiras
independentes: o portal devolve allowlist de seis campos factuais em vez do objeto do caso, e a
tela é `STAFF_ROUTES` com `roles: ROLES.compliance`, enquanto o `AuthMiddleware` restringe
`cliente_externo` a seis prefixos que não incluem `/api/triagem/`. O risco remanescente é de uso
humano, não de software. *(Parte 9 → resolvido na Parte 15)*

---

## Retificações

Auditoria honesta registra os próprios erros. Três foram corrigidos no curso do trabalho:

**Peças travadas.** Reportado como "97 de 98" nas Partes 10 e 11. O correto é **22 de 23** — 75
daquelas peças eram órfãs geradas pela própria exclusão dos casos de teste da auditoria. O bug
permanece real, com alcance uma ordem de grandeza menor. Esse erro, porém, revelou um defeito
legítimo: **a exclusão de um caso não cascateia para suas peças.** *(Parte 12)*

**Rotas "inexistentes".** As rotas `despesas`, `office-contracts` e `partner-withdrawals` foram
reportadas nas Partes 8 e 9 como não existentes. Na verdade estavam montadas com **prefixo `/v1/`
duplicado** (`/api/v1/v1/despesas`). *(Parte 11)* — **Já corrigido no repositório:** todos os
routers financeiros declaram prefixo simples e `grep -rn 'prefix="/v1' backend/app` não retorna
nada. *(confirmado na Parte 14)*

**Citação normativa.** As Partes 3 a 9 repetiram a citação do "Provimento OAB 205/2021" como
fundamento da revisão humana de IA, seguindo o que o próprio sistema afirma. **Verificado na fonte
oficial: aquele provimento dispõe sobre publicidade e informação da advocacia**, não sobre IA.
*(Parte 10)*

**Fundamento da vedação a promessa de resultado.** As Partes 4, 8 e 9, o `plano-correcao-v2.md` e o
`plano-lancamento-v3.md` citam "Código de Ética da OAB, art. 6º, parágrafo único, e art. 34, XXIX"
como base para vedar a promessa de resultado ao cliente. **Verificado na fonte oficial: o art. 34 é
do Estatuto da Advocacia (Lei 8.906/1994), não do Código de Ética, e seu inciso XXIX trata de
infração disciplinar por erro reiterado que evidencie inépcia profissional — matéria distinta.** O
fundamento correto para a vedação é o **Provimento OAB nº 205/2021, art. 6º e parágrafo único**
(publicidade da advocacia), aprovado pelo Conselho Pleno do Conselho Federal da OAB e em vigor
desde a publicação, sem revogação posterior conhecida em 11/08/2026 — que veda expressamente "a
menção à promessa de resultados" em qualquer publicidade. Os documentos citados não foram
reescritos — permanecem como registro histórico da auditoria original; a citação correta vale para
qualquer uso futuro do achado.
*(achado originado nas Partes 4/8/9; citação corrigida na revisão do PR #1060, Parte 15)*

---

## Nota sobre credenciais

Nenhum documento deste diretório contém senha, token ou chave. As credenciais usadas na auditoria
foram fornecidas em conversa e não estão registradas aqui. **Se alguma delas ainda estiver em uso,
recomenda-se rotação** — em particular, a auditoria registrou que a senha de root do VPS e a senha
de aplicação eram idênticas no momento do trabalho.
