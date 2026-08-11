# Fechamento — auditoria de código de agosto/2026 (Partes 14 a 20)

**Período:** 10–11 de agosto de 2026.
**Método:** leitura do código-fonte no repositório. **Nenhum ambiente foi executado e nenhuma
chamada foi feita a produção.** Todo achado tem evidência `arquivo:linha`, conferida por leitura
direta do arquivo — não pelo graphify.

**Diferença em relação às Partes 1 a 13.** Aquelas foram feitas por fora: HTTPS contra o ambiente
de produção, sem acesso ao repositório. Podiam reproduzir sintomas, não localizar causas. Esta
auditoria lê o código e, em três casos, fecha achados que estavam abertos desde julho.

---

## O que esta auditoria resolveu de pendências antigas

**A "chance de êxito" não vaza para o cliente.** Era um dos cinco achados destacados no
`README.md`, aberto desde a Parte 9, com risco ético relevante (Código de Ética da OAB, art. 6º,
parágrafo único, e art. 34, XXIX). Há duas barreiras independentes: o portal devolve allowlist de
seis campos factuais em vez do objeto do caso, e a tela que exibe a métrica é `STAFF_ROUTES` com
`roles: ROLES.compliance`, enquanto o `AuthMiddleware` restringe `cliente_externo` a seis prefixos
de path que não incluem `/api/triagem/`. *(Parte 15)*

**O prefixo `/v1/` duplicado não existe mais.** Todos os routers financeiros declaram prefixo
simples e `grep -rn 'prefix="/v1' backend/app` não retorna nada. O achado das Partes 8, 9 e 11
está resolvido no repositório. *(Parte 14)*

**A contradição do `backup_offsite` tem causa localizada.** Duas fontes com o mesmo rótulo lendo
settings diferentes — `_probe_backup` lê `BACKUP_ENABLED`, o painel de integrações lê
`BACKUP_REMOTE` — e as duas caem na mesma resposta porque o filtro só descarta o grupo
"Inteligência". *(Parte 19)*

**Não foi encontrado vazamento entre clientes em nenhuma das quatro superfícies externas.** Portal,
assinaturas, notificações e `/api/users/me` — todas derivam o escopo do usuário autenticado, nunca
do request. *(Partes 15 e 16)*

---

## Achados por severidade

### P0 — decidir antes de operar

| ID | Parte | Achado |
|---|---|---|
| **PRZ-01** | 14 | O termo inicial do prazo gerado por intimação DJEN usa a data de **disponibilização** como se fosse a de **publicação**, ignorando o salto do art. 224 §2 do CPC. Todo prazo vindo do DJEN vence um dia útil antes do legal — e é sinalizado como vencido antes de vencer. |
| **PRZ-02** | 14 | O recesso do art. 220 (20/12–20/01) não é aplicado em nenhum dos três caminhos por onde um prazo realmente nasce (calculadora, criação manual, DJEN), embora o motor de peças e o agente de IA o apliquem. A mesma pergunta tem duas respostas no sistema. |
| **SOC-01** | 18 | Cadastrar sócio exige `admin` (nível 8); **alterar** exige apenas `socio` (nível 7), e o `PATCH` aceita qualquer campo, incluindo `participacao_percentual` e `pro_labore`. Um sócio pode alterar a própria participação e a dos demais — sem trilha alguma. |
| **NFS-01** | 17 | Regime tributário fixado em código como Simples Nacional optante. Se o escritório não for optante, toda nota declara regime errado — o próprio comentário registra que isso muda a base de cálculo da DPS. |
| **NFS-02** | 17 | Retenção de ISS fixada em "não retido" e operação fixada em "tributável". Retenção depende do **tomador**; nota para tomador obrigado a reter sai errada. |

**Sequência recomendada.** SOC-01 primeiro: é o único P0 cuja correção é pequena e não depende de
ninguém de fora (elevar o gate do `PATCH`, restringir campos por allowlist, registrar trilha).
PRZ-01 e PRZ-02 em seguida, com teste de regressão — são regra jurídica e a governança exige fonte,
vigência e teste. NFS-01 e NFS-02 são **decisão de contador**, não de programador: valem uma
conversa antes de qualquer código e antes de `NFSE_ENABLED=true` em produção.

### P1 — corrigir antes de escalar o uso

| ID | Parte | Achado |
|---|---|---|
| FIN-01 | 14 | O consolidado não lê `fee_payments`: pagamento parcial não entra no "recebido no mês", e o valor cheio cai de uma vez na competência da quitação. |
| FIN-02 | 14 | "Recorrente" é rótulo, não comportamento — nenhum job materializa a despesa do mês seguinte, então a virada do mês infla caixa e margem. |
| FIN-03 | 14 | `/despesas/resumo` aplica o filtro de competência a dois agregados e não aos outros dois, misturando mês e histórico no mesmo card. |
| FIN-04 | 14 | `competencia` é gravada sem validação de formato e casada por igualdade de string na leitura — fora do padrão, a despesa some do relatório. |
| PRZ-03 | 14 | Data de disponibilização inválida vira `date.today()` silenciosamente, deslocando o termo inicial na direção perigosa. |
| ASS-01 | 15 | O hash SHA-256 não é reconferido no ato de assinar: troca do arquivo entre a solicitação e a assinatura não é detectada — e é essa correspondência que dá valor probatório à trilha. |
| ASS-02 | 15 | Não há cancelamento, expiração nem lembrete de solicitação de assinatura. |
| POR-01 | 15 | Documento aparece ao cliente por `confidencialidade='normal'`, não por ato de publicação. *(Já tratado no PR #758.)* |
| NOT-01 | 16 | Notificações se acumulam para sempre — sem deduplicação, retenção ou arquivamento. Ângulo LGPD: `mensagem` é texto livre com contexto de caso. |
| NOT-02 | 16 | `notificar()` comita a sessão do chamador no meio da transação dele; 22 chamadas expostas. |
| NFS-03 | 17 | Valor e alíquota passam por `float` + `round()` (arredondamento bancário) na fronteira fiscal. |
| NFS-04 | 17 | Nota presa em `processando` bloqueia o faturamento do honorário para sempre — não há job de reconciliação. |
| SOC-02 | 18 | O módulo societário do escritório quase não tem trilha (2 registros) enquanto o dos clientes tem 10 audit logs. Alteração de participação não registra nada. |
| SOC-03 | 18 | A soma de 100% só é validada na distribuição, nunca na escrita — o quadro pode ser gravado somando 150%. |
| HON-01 | 19 | O estimador de IA não passa pelo citation gate; a proteção contra inventar item da tabela OAB é instrução de prompt. |
| DIA-01 | 19 | `/diagnostico/central` reporta `backup_offsite` ligado e desligado na mesma resposta, no campo que o próprio código chama de "único mitigante do ponto único de falha do banco". |
| CFG-01 | 20 | Desligar um módulo esconde o menu; a API continua aberta. |
| LIX-01 | 20 | Não existe purga definitiva — pedido de exclusão de titular não pode ser atendido pelo sistema (LGPD art. 16 e art. 18, VI). |
| LIX-02 | 20 | A restauração é de uma linha só, sem as relações; somada à exclusão que não cascateia, produz inconsistência nos dois sentidos. |

### P2

FIN-05, FIN-06, FIN-07 *(14)* · PRZ-04 *(14)* · POR-02, POR-03, ASS-03 *(15)* · NFS-05 *(17)* ·
SOC-04 *(18)* · HON-02 *(19)* · LIX-03, PRO-01, CON-01 *(20)*. Detalhe em cada parte.

---

## O que está bom e deve ser preservado

Auditoria que só lista defeito distorce a prioridade. Estes pontos são bons o bastante para virar
padrão do repositório:

**Matemática monetária.** `Numeric` nas colunas e `Decimal` com `ROUND_HALF_UP` ponta a ponta, com
a conversão para `float` deliberadamente adiada até a serialização — e comentada. A distribuição
de lucros vai além e **corrige o drift de centavos**: a soma das cotas arredondadas fecha
exatamente o total. *(14, 18)*

**RBAC least-privilege com o motivo escrito.** Vários gates usam conjunto explícito **em vez de**
`require_roles`, com o comentário registrando por quê: *"NÃO require_roles, que pelo fallback
hierárquico deixaria advogado passar"*. *(14)*

**Isolamento do portal.** Todo endpoint deriva o `client_id` do usuário autenticado, nunca do
request, e a resposta é allowlist de campos, não `model_dump`. *(15)*

**Idempotência garantida pelo banco.** A emissão de NFS-e reserva a referência com `UNIQUE` e
comita **antes** de tocar o provedor; o alerta de prazo usa faixas disjuntas com flag por faixa; a
conversão intimação→prazo devolve o prazo existente em vez de duplicar. *(14, 17)*

**Trilha antes da ação externa.** A NFS-e grava o audit log da **intenção** de emitir e comita
antes da chamada ao provedor, para que a tentativa não se perca se o externo falhar. *(17)*

**IA no lugar certo.** No estimador de honorários, o que vira registro do caso **não** passa por
IA: a sugestão é determinística e a gravação é versionada, auditada e revalidada contra a vigência
da tabela OAB. *(19)*

**Limites declarados no próprio código.** O motor de prazos diz que não cobre suspensões por
tribunal; o adapter de NFS-e diz que o regime tributário precisa do contador; o scheduler descreve
com precisão a limitação do commit interno de `notificar()`. Código que documenta a própria
fronteira é mais confiável do que código que a esconde.

---

## Limitações desta auditoria

**Leitura estática não é execução.** Nenhum achado foi reproduzido em ambiente de pé. São
consistentes no código; a confirmação em runtime não foi feita.

**Três perguntas dependem do estado de produção**, fora do alcance deste trabalho:
- a captura DJEN está capturando? (o código já tem contagem estruturada de resultado e resumo de
  heartbeat — a crítica da Parte 11 parece endereçada, mas isso precisa ser visto rodando);
- o índice RAG está populado? Se seguir vazio, o estimador de honorários opera permanentemente em
  modo degradado *(HON-02)*;
- o APScheduler está ligado? Sem ele não há alerta de prazo algum, e o módulo de Prazos não tem
  como sinalizar essa condição ao advogado.

**Não auditado:** todo o restante do sistema fora das dez frentes listadas — em especial o núcleo
de IA/RAG, o pipeline de peças, casos, clientes e documentos, que já têm cobertura própria nas
Partes 1 a 13 e nos PRs abertos.

**Nenhum defeito foi corrigido.** Este trabalho é diagnóstico. Cada P0 e P1 precisa de Issue
própria e teste de regressão, conforme a regra 6 da governança.
