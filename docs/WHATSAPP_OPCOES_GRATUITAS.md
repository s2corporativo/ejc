# WhatsApp Business no EJC — Opções "gratuitas" (pesquisa jul/2026)

> Pesquisa externa multi-fonte realizada em 18/07/2026 para decidir o canal WhatsApp da fila de notificações do EJC (prazos, avisos a clientes, alertas internos) sem mensalidade de provedor (Z-API ≈ R$89/mês). Escopo: escritório com 5 advogados, volume baixo (~centenas de msgs/mês).
> **Ressalva metodológica:** as páginas oficiais da Meta (`developers.facebook.com`, `whatsapp.com/legal`, `faq.whatsapp.com`) retornaram HTTP 403 ao fetch no ambiente de pesquisa; os valores de preço foram confirmados por convergência de múltiplas fontes secundárias 2025-2026 e devem ser validados no rate card oficial antes de ativar billing.

## Resumo executivo

**Não existe caminho 100% gratuito E seguro.** Mas existe um caminho *quase* gratuito e oficial: a **WhatsApp Cloud API da Meta, integrada diretamente (sem BSP)**. A Meta hospeda a API sem custo — paga-se só por mensagem — e, para notificações de utilidade (prazos, avisos de processo), o custo estimado para centenas de mensagens/mês é da ordem de **R$5-20/mês**, contra R$89/mês do Z-API. As soluções open-source não oficiais (Evolution API, WAHA, WPPConnect, Baileys) têm custo zero de licença, mas violam os Termos de Serviço da Meta e o risco de **banimento definitivo do número comercial** escalou fortemente desde o fim de 2025 — inaceitável para o número principal de um escritório de advocacia.

**Recomendação: Cloud API oficial direta, com templates "utility".** Detalhes e nuances na seção 4.

## Tabela comparativa

| Opção | Custo (baixo volume) | Oficial? | Risco de ban | Risco LGPD/OAB | Esforço de integração |
|---|---|---|---|---|---|
| **Meta Cloud API direta** | R$0 de mensalidade; ~R$5-20/mês em msgs utility (~US$0,008/msg)* | Sim | Nenhum (respeitando políticas) | Baixo (contrato com a Meta, criptografia gerenciada) | Médio: Meta Business + verificação CNPJ + número dedicado + token + templates aprovados |
| **BSP pago (Z-API etc.)** | ~R$89/mês + repasse Meta | Sim (via parceiro) | Nenhum | Baixo | Baixo — mas é justamente o custo que se quer evitar |
| **Evolution API (self-hosted)** | R$0 (Apache 2.0; só o VPS) | **Não** | **Alto e crescente (ondas de ban desde fim de 2025)** | Alto (sem DPA com a Meta; msgs em claro no servidor próprio; sigilo profissional exposto) | Baixo-médio (Docker + Postgres + Redis; API REST) |
| **WAHA Core** | R$0 (Apache 2.0; Core/Plus unificados desde jun/2026) | **Não** | **Alto** (mesmo motor não oficial) | Alto (idem) | Baixo (container único, REST/Swagger) |
| **WPPConnect / Baileys (lib)** | R$0 (LGPL v3 / MIT) | **Não** | **Alto** (autor original do Baileys recebeu C&D da Meta e teve conta banida) | Alto (idem) | Médio (biblioteca Node, mais montagem) |
| **Manter só e-mail** | R$0 | — | — | Baixo | Zero (já funciona) |

\* Valor de utility fora da janela; dentro da janela de 24h é grátis até 01/10/2026 (ver abaixo).

## 1. WhatsApp Cloud API oficial (Meta)

**Modelo de cobrança vigente (jul/2026)** — confirmado por múltiplas fontes independentes:

- Em **01/07/2025 a Meta migrou de cobrança por-conversa para por-mensagem** de template entregue (marketing, utility, authentication). A regra segue vigente em 2026. [YCloud](https://www.ycloud.com/blog/whatsapp-api-pricing-update) (2025); [CleverTap](https://clevertap.com/blog/whatsapp-business-pricing-changes-in-july-2025/) (2025); doc oficial: developers.facebook.com/documentation/business-messaging/whatsapp/pricing (não lida diretamente — 403).
- **Grátis hoje:** mensagens de serviço (texto livre) dentro da janela de atendimento de 24h aberta pelo cliente — ilimitadas desde 01/11/2024 (o antigo teto de 1.000 conversas grátis/mês foi extinto e substituído por gratuidade ilimitada); templates **utility** entregues dentro de janela aberta também são grátis desde 01/07/2025. [8x8](https://cpaas.8x8.com/en/blog/whatsapp-pricing-changes-2024/) (2024); [YCloud](https://www.ycloud.com/blog/whatsapp-service-messages-24-hour-window-pricing) (2026).
- **Atenção — mudança anunciada:** a partir de **01/10/2026** a Meta passará a cobrar mensagens de serviço e utility dentro da janela (rate cards até 01/09/2026). Orçamento deve considerar isso. [ChakraHQ](https://chakrahq.com/article/whatsapp-api-pricing-update-service-messages-october-2026/) (2026); [Charles](https://www.hello-charles.com/blog/whatsapp-service-message-pricing-what-changes-in-2026) (2026).
- **Preços Brasil (tier base, por mensagem)** — *não confirmados em fonte primária (403); fontes secundárias divergem levemente*: utility ≈ **US$0,008** (~R$0,04-0,06), authentication ≈ US$0,0315, marketing ≈ US$0,0625 (~R$0,31-0,40). Desde 01/07/2026, novas WABAs brasileiras podem faturar em **BRL**. [MessageCentral](https://www.messagecentral.com/blog/whatsapp-business-api-pricing-brazil) (2026); [SocialHub](https://www.socialhub.pro/blog/preco-whatsapp-api-2026-brasil/) (2026).
- **A API em si é gratuita:** a Meta hospeda a Cloud API sem taxa de acesso/assinatura; paga-se apenas por mensagem. A On-Premises API foi descontinuada em out/2025. [Chatarmin](https://chatarmin.com/en/blog/whatsapp-cloudapi) (2026); [Respond.io](https://respond.io/blog/whatsapp-cloud-api) (2025/2026).

**Custo estimado para o escritório** (300 msgs/mês, todas utility fora de janela): 300 × US$0,008 ≈ **US$2,40/mês (~R$13)**. Mesmo com margem de erro, ordem de grandeza muito abaixo dos R$89/mês do Z-API.

**Requisitos para uso direto (sem BSP):**

1. Conta Meta Business (Business Portfolio) + app no Meta for Developers com caso de uso WhatsApp — grátis. [Meta Get Started](https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started) (acessada via snippet, 18/07/2026).
2. **Número dedicado** — não pode ficar ativo simultaneamente no app WhatsApp normal/Business (migrar exige apagar a conta do app, perdendo histórico). Há número de teste grátis da Meta (até 5 destinatários) para desenvolver. [Wati](https://support.wati.io/en/articles/11463152) (2026).
3. **Verificação de negócio (CNPJ)** — não obrigatória para começar, mas sem ela o limite é 250 conversas iniciadas pela empresa/24h (suficiente para o volume do escritório, aliás); com verificação, 1.000/dia. Exige cartão CNPJ, endereço batendo, site no ar; prazo típico 2-10 dias úteis (fontes secundárias). [Meta Messaging Limits](https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits); [Anylinga](https://anylinga.com/blog/pt/meta-business-verification-rejected-7-fixes.html) (2026).
4. **Token permanente** via System User no Business Manager; **webhook HTTPS público** (Let's Encrypt serve) para receber mensagens/status. [Meta blog auth tokens](https://developers.facebook.com/blog/post/2022/12/05/auth-tokens/) (05/12/2022); [Hookdeck](https://hookdeck.com/webhooks/platforms/guide-to-whatsapp-webhooks-features-and-best-practices).
5. **Templates pré-aprovados** para mensagens fora da janela de 24h (aprovação típica: minutos a 24h). Notificação de prazo/andamento processual se enquadra em **utility**. [Twilio docs](https://www.twilio.com/docs/whatsapp/tutorial/message-template-approvals-statuses).
6. Não precisa do programa "Tech Provider" (isso é para operar em nome de terceiros); precisa cadastrar meio de pagamento no Business Manager (*não confirmado em fonte primária*).

## 2. Open-source não oficiais (estado jul/2026)

Todas usam engenharia reversa do protocolo WhatsApp Web — violação dos Termos da Meta (ver seção 3).

- **Evolution API** — viva e popular no Brasil; repo migrou para `evolution-foundation/evolution-api`; v2.3.7 (dez/2025), v2.4.0 em RC (mai/2026); Apache 2.0; Docker + Postgres + Redis; usa Baileys por baixo **e também suporta o canal Cloud API oficial**. Novidade: a **v2.4.0 exige ativação de licença "phone-home"** (gratuita, mas controversa — issue [#2534](https://github.com/evolution-foundation/evolution-api/issues/2534), mai/2026). Core continua gratuito; "Evolution Cloud" gerenciado com preço público **não confirmado**. [Repo](https://github.com/evolution-foundation/evolution-api) (18/07/2026).
- **WAHA** — ativamente mantido (release 2026.7.1 em 15/07/2026); Apache 2.0. **O tier pago acabou: desde a 2026.6.1 (22/06/2026) as features do WAHA Plus (multi-sessão, mídia, storage) entraram no Core gratuito.** Historicamente Plus custava ~US$19/mês em modelo de doação (*preços não confirmados na fonte primária — site 403*). Container único, o mais simples para notificações (engines NOWEB/GOWS sem Chromium). [Releases](https://github.com/devlikeapro/waha/releases) (2026); [Discussion #58](https://github.com/devlikeapro/waha/discussions/58).
- **WPPConnect** — mantido (v2.2.3 em 15/07/2026), LGPL v3, comunidade brasileira ativa; exige mais montagem que o WAHA. [Repo](https://github.com/wppconnect-team/wppconnect) (18/07/2026).
- **Baileys** (WhiskeySockets) — mantido (v7.0.0-rc13, mai/2026), MIT; README declara não-afiliação à Meta e desencoraja mensageria automatizada. O **repo original (adiwajshing) foi removido em abr/2023 após cease & desist do jurídico do WhatsApp, com ban da conta pessoal do autor** (*confirmado apenas em fontes secundárias — o statement original foi deletado*). [Repo](https://github.com/WhiskeySockets/Baileys) (18/07/2026); [histórico do takedown](https://www.nikkixploit.com/2023/04/alasan-adiwajshing-menghapus-repository-github-baileys.html) (abr/2023).

## 3. Riscos jurídicos e operacionais

- **ToS da Meta:** automação/envio em massa fora dos produtos oficiais é proibida; desde dez/2019 a Meta declara que pode tomar **ação judicial** (não só ban), inclusive com evidência off-platform. Precedente de litígio: *Meta v. HeyMods* (out/2022, clientes não oficiais de WhatsApp). Nenhum processo específico contra Evolution/WAHA/Baileys localizado até jul/2026 — o enforcement observado contra eles é técnico (ban) e contratual (C&D). [SecurityWeek](https://www.securityweek.com/whatsapp-will-take-legal-action-against-automated-or-bulk-messaging/) (dez/2019); [Engadget](https://www.engadget.com/meta-sues-app-developers-whatsapp-accounts-104210186.html) (out/2022).
- **Banimento:** relatos volumosos no ecossistema brasileiro de **onda de bans desde fim de 2025/jan de 2026** em instâncias Evolution/Baileys, mesmo com volume baixo (issue [#1870](https://github.com/EvolutionAPI/evolution-api/issues/1870), ago/2025: bans com 40-50 msgs/dia). Padrão: restrição temporária → ban definitivo do número, **sem recurso garantido** — o escritório perderia o número comercial e o histórico. *(Frequência não quantificável em fonte primária; evidência anedótica mas convergente. Vários blogs que relatam bans vendem a API oficial — viés registrado. Existe o contra-argumento comercial de vendedores de API não oficial de que "o ban é pelo comportamento, não pela conexão" — sem confirmação da Meta e contrariado pelo texto dos ToS.)*
- **LGPD:** para notificar prazos a cliente contratado, a base legal é execução de contrato (art. 7º, V) / exercício regular de direitos (art. 7º, VI); cartilhas da OAB recomendam registrar o canal preferido e obter opt-in ([Guia LGPD OAB Campinas](https://oabcampinas.org.br/wp-content/uploads/2021/12/Guia-LGPD_Advocacia.pdf), 2021). Na rota **não oficial**, as mensagens trafegam em claro pelo servidor intermediário próprio, sem DPA com a Meta — fragiliza arts. 39 e 46-49 da LGPD e expõe o **sigilo profissional** (art. 34, Lei 8.906/94) a incidente reportável. *(Análise derivada — não há pronunciamento da ANPD nem precedente disciplinar OAB específico sobre APIs não oficiais de WhatsApp até jul/2026.)*
- **Boas práticas OAB para o conteúdo:** notificação enxuta ("Há uma atualização no seu processo — acesse o portal") em vez de detalhes sensíveis no corpo da mensagem; número profissional separado; confirmar titularidade do número do cliente.

## 4. Recomendação

**Caminho recomendado: Meta Cloud API oficial, integração direta (sem BSP).** Justificativa:

- Atende o objetivo real ("sem mensalidade de provedor"): R$0 fixo; custo variável estimado de R$5-20/mês para centenas de mensagens utility — e **R$0 em mensagens dentro da janela de 24h até 01/10/2026** (cliente que responde/inicia conversa abre janela grátis).
- Único caminho compatível com o dever de diligência de um escritório de advocacia: sem risco de ban, com lastro contratual com a Meta, defensável perante OAB/ANPD.
- A stub de WhatsApp da fila do EJC integraria via HTTP simples (Graph API `POST /{phone_number_id}/messages` com template utility) — esforço de código baixo; o esforço real é burocrático (verificação do CNPJ, número dedicado, aprovação de templates).

**Nuances:**

- **Se for exigido custo rigorosamente zero em mensagens:** usar a Cloud API só reativamente (responder dentro da janela aberta pelo cliente) é grátis hoje, mas notificações proativas de prazo exigem template pago (centavos) — e a gratuidade da janela acaba em out/2026. O "zero absoluto" oficial não existe para notificações proativas.
- **Alertas internos aos 5 advogados:** cabem na própria Cloud API (5 utility/dia ≈ centavos) — não vale o risco de montar uma Evolution/WAHA paralela. Se ainda assim se quiser experimentar a rota não oficial, que seja **apenas** para alertas internos, com **chip descartável exclusivo** (nunca o número comercial do escritório) e **nunca com dados de clientes** — ciente de que viola os ToS da Meta e o número pode cair a qualquer momento.
- **Plano B sem custo e sem risco:** manter o e-mail como canal primário (já funciona no EJC) e adiar o WhatsApp até aceitar o custo por mensagem da via oficial.
- **Reavaliar orçamento em set/2026**, quando a Meta publicar os rate cards da cobrança de mensagens na janela (vigência 01/10/2026).

## O que ainda precisa de validação em fonte primária

1. Preços exatos utility/authentication/marketing para Brasil no rate card oficial (validar logado em developers.facebook.com antes de ativar billing).
2. Exigência formal de billing cadastrado antes do primeiro template pago.
3. Prazos oficiais de verificação de empresa e de aprovação de template (números vieram de BSPs/comunidade).
4. Texto oficial da atualização de ToS de out/2025 (vigência 15/01/2026) — relatada por fontes secundárias.
5. Detalhes do merge WAHA Core/Plus e preços históricos do Plus (site oficial 403; release notes do GitHub confirmam o merge).

## Checklist de ativação (ação do dono, quando decidir)

1. Criar/usar Business Portfolio da S2/De Paula Teixeira em business.facebook.com e app em developers.facebook.com (caso de uso WhatsApp).
2. Separar um número dedicado para o canal (novo chip ou número que possa sair do app WhatsApp).
3. Submeter verificação de negócio (cartão CNPJ, endereço idêntico, site no ar).
4. Criar System User, gerar token permanente e cadastrar billing.
5. Aprovar 2-3 templates utility (alerta de prazo, atualização de processo, lembrete de reunião).
6. Entregar ao EJC: `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` e nomes dos templates — a integração na fila de notificações vira tarefa de código a partir daí.
