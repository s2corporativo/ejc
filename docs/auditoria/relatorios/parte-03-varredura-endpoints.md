# Auditoria Técnica do EJC — Parte 3: Varredura completa + teste da IA ponta a ponta
**Escopo desta rodada:** todos os endpoints de leitura mapeados, um fluxo de escrita completo (Sala Jurídica → Cliente → Caso → Prazo → Tarefa), e um teste dirigido da IA com caso fictício completo, avaliando se o resultado é "solução completa pronta para protocolar" conforme solicitado.
**Usuário de teste:** soares@depaulateixeira.adv.br (perfil `advogado`).
**Dados criados:** todos identificados com o prefixo `[TESTE AUDITORIA - EXCLUIR]`, arquivados/inativados ao final (ver seção 6 — limitação de limpeza).

---

## 1. Achado mais importante da rodada: a conversão Sala Jurídica → Caso perde os dados da análise

Este é o achado de maior impacto prático de toda a auditoria (Partes 1–3), porque atinge diretamente o fluxo que o próprio EJC apresenta como seu diferencial: entrada conversacional com IA → caso formal.

**Sequência exata reproduzida:**
1. Criei uma sessão em Sala Jurídica e enviei, em uma única mensagem, um caso fictício completo de vício de produto (CDC): datas, valores, número de nota fiscal, protocolo de assistência técnica, protocolo de SAC, lista de provas em posse do escritório.
2. A IA respondeu com uma análise FIRAC completa e uma minuta de petição inicial citando corretamente cada fato, cada valor e cada prova que eu havia informado (transcrição completa na Seção 2).
3. Converti a sessão em Caso formal pelo endpoint oficial (`POST /sala-juridica/{id}/converter`) — o mesmo botão que a tela "Converter em Caso" aciona.
4. Ao abrir o Caso recém-criado (`GET /cases/{id}`), o campo `descricao_fatos` estava **null**. Nenhum documento foi transferido (`documentos_transferidos: []` na resposta da própria conversão).
5. Rodei a ferramenta de IA do próprio módulo Casos — `POST /cases/{id}/score-juridico/calcular` — e ela devolveu nota **23/100**, com a justificativa: *"Nenhum documento anexado (Docs: 0). Ausência total de nota fiscal, garantia, protocolos de reclamação, laudos ou fotos do vício"* e *"faltam elementos fáticos: data da compra, descrição do defeito, prazo decadencial, tentativas de solução junto ao fornecedor"*.

**O ponto 5 é factualmente falso em relação ao que já havia sido levantado no ponto 2** — a data da compra, a descrição do defeito, o protocolo de assistência técnica e o protocolo de SAC já estavam todos registrados, com riqueza de detalhe, na análise da Sala Jurídica que deu origem a este mesmo caso. A ferramenta de score jurídico do módulo Casos simplesmente não tem acesso a esse conteúdo, porque a conversão não o transportou.

**Consequência prática para o advogado:** ele faz o trabalho de descrever o caso uma vez (na Sala Jurídica, com a IA já estruturando fatos, direito e minuta), converte para caso formal — e ao abrir o Caso, tem que description tudo de novo, porque o sistema "esqueceu" o que acabou de ser analisado. Isso anula boa parte do ganho de tempo que a Sala Jurídica promete entregar. Complementarmente, a ferramenta de Índice de Risco (`POST /cases/{id}/indice-risco/recalcular`) classificou o caso como **"risco baixo"** justamente por não ter documentos — ou seja, o mesmo vazio de dados que deveria gerar um alerta ("faltam evidências, revisar antes de prosseguir") é lido pela ferramenta de risco como sinal de tranquilidade. Isso é potencialmente perigoso: um advogado que confia no badge de "risco baixo" sem abrir o caso pode subestimar um caso que, na verdade, só está com a triagem incompleta.

**Recomendação:** o endpoint de conversão (`/sala-juridica/{id}/converter`) deveria, no mínimo, copiar o resumo da análise da IA para `descricao_fatos` do caso e vincular formalmente as evidências citadas na conversa (mesmo que como referência/anexo pendente, não como documento físico ainda anexado). Sem isso, o Índice de Risco e o Score Jurídico do caso deveriam explicitamente diferenciar "sem evidência porque não existe" de "sem evidência porque a triagem anterior não foi transferida" — hoje os dois casos são tratados de forma idêntica.

---

## 2. Teste dirigido: a IA entrega "solução completa pronta para protocolar"?

**Resposta direta: não — e isso é proposital, não uma limitação a corrigir.** Abaixo, a evidência e o raciocínio.

Enviei um caso fictício **completo** (fatos, datas, valores, números de protocolo, lista de provas, pedidos e valores desejados) solicitando explicitamente: *"gere a petição inicial completa (...) pronta para revisão final e protocolo."*

Duas tentativas foram necessárias:
- Na primeira, incluí nome completo, CPF e RG fictícios da parte autora no texto livre. O sistema **recusou processar**, com a mensagem: *"Este conteúdo tem dados pessoais que não podem ir a uma IA externa. Habilite uma IA local (OLLAMA_ENABLED=true) ou remova os dados pessoais do texto e tente novamente."* — um bloqueio de LGPD funcional e verificado: o sistema impede envio de CPF/RG/nome completo a provedores externos de IA (Anthropic/Maritaca/Groq, conforme o Painel de Provedores identificado na Parte 1), a menos que um modelo local (Ollama) esteja habilitado.
- Na segunda tentativa, removi apenas os campos de identificação pessoal (mantendo todos os fatos, valores, protocolos e provas) e o sistema processou normalmente em 94 segundos.

**O que a IA entregou** (petição de ação de rescisão contratual c/c restituição de valores e indenização por danos morais e materiais, fundamentada no CDC):

- Todos os fatos que informei (compra em 10/03/2026, defeito em 15/04/2026, protocolo de assistência AT-88231, protocolo de SAC SAC-556677, mais de 3 meses sem o produto, R$ 380,00 em gastos com gelo) foram incorporados corretamente, com as datas e números exatos.
- Fundamentação jurídica correta e específica: art. 18, caput e §1º (vício não sanado em 30 dias), art. 26, II e §2º, I (prazo decadencial de 90 dias e sua interrupção pela reclamação comprovada), art. 6º, VI e VIII (dano material, inversão do ônus da prova), art. 2º e 3º (caracterização da relação de consumo) — todos do CDC.
- Calculou corretamente o valor da causa (R$ 12.580,00 = R$ 4.200,00 + R$ 380,00 + R$ 8.000,00).
- **Identificou um risco jurídico real que eu não havia sinalizado**: alertou para a necessidade de confirmar a contagem exata do prazo decadencial na data do protocolo, e para a ausência de laudo técnico da assistência confirmando que o defeito é "de fabricação" — um ponto de prova genuinamente relevante para o mérito.
- **Recusou-se a inventar jurisprudência**: em vez de citar precedentes fictícios do STJ/TJMG para sustentar o valor do dano moral (comportamento comum e perigoso em IAs genéricas), escreveu explicitamente *"inserir apenas precedentes verificáveis"* e deixou o campo em aberto.
- **Corrigiu, com justificativa técnica, uma instrução minha**: eu pedi valor fixo de R$ 8.000,00 de dano moral; a IA manteve o valor mas recomendou pedir "não inferior a R$ 8.000,00, ou o que o juízo arbitrar" — prática processual mais adequada, com a ressalva de que a fixação do valor é prerrogativa do advogado.
- **Não incluiu uma tese cabível ao caso mas não pedida** (repetição em dobro, art. 42, parágrafo único, CDC) porque os fatos não a sustentam (não houve cobrança indevida paga) — evidência de raciocínio aplicado ao caso, não geração de texto genérico.
- Terminou com um bloco de aviso, dentro do próprio texto da peça (não só como metadado da tela): *"⚠️ RASCUNHO — REVISÃO HUMANA OBRIGATÓRIA. Não protocolar sem definição do juízo/rito, conferência da contagem decadencial na data do protocolo, obtenção do laudo técnico e revisão do advogado responsável (OAB)."*
- A resposta da API também trouxe os metadados `is_rascunho: true` e `aviso_hitl: "Rascunho sujeito à revisão humana (HITL obrigatório — OAB)."`.

**Avaliação técnica honesta:** a qualidade jurídica do texto produzido — estrutura, fundamentação, cálculo de valor da causa, identificação de risco de decadência, recusa a fabricar jurisprudência — é de nível bastante superior ao que normalmente se vê em geração de peças por IA genérica. Isso é um ponto forte real, verificado com um caso adversarial (dei uma instrução de valor que a IA preferiu não simplesmente obedecer sem ressalva). Ao mesmo tempo, a única coisa que faltou para ser "protocolável" foram exatamente os três elementos que **por desenho e por exigência ética/legal não podem ser preenchidos pela IA sem supervisão humana**: (a) qualificação das partes (nome, CPF, endereço — dados pessoais reais, que o próprio guardrail de LGPD impede de circular livremente pela IA), (b) escolha do juízo competente (decisão profissional do advogado, não da IA), e (c) confirmação factual de que o prazo decadencial ainda não se esgotou e de que existe laudo técnico (fatos que só o advogado, com o cliente, pode confirmar).

**Conclusão sobre a expectativa "pronto para protocolar":** se a expectativa é uma peça que o advogado só copia e assina sem revisão, o sistema **não atende e não deveria atender** — fazer isso seria incompatível com o Provimento 205/2021 da OAB (uso de IA na advocacia exige revisão humana) e com o dever de verificação pessoal dos fatos pelo advogado. O que o sistema entrega, de fato, é uma minuta juridicamente sólida, com lacunas expressamente sinalizadas apenas onde a lei ou a ética exigem intervenção humana — que é o resultado correto a se esperar de uma ferramenta de IA jurídica bem desenhada. Recomendo alinhar a expectativa interna do escritório para "a IA entrega o primeiro rascunho pronto para revisão e complementação factual/documental, não para protocolo direto" — e usar esse enquadramento em qualquer material de treinamento da equipe, para que ninguém trate um rascunho como peça final por engano.

---

## 3. Varredura sistemática — ~100 endpoints de leitura testados

Testei todos os endpoints GET sem parâmetro de caminho mapeados no frontend. Resultado agregado: **64 responderam 200, 30 responderam 403 (controle de acesso, todos coerentes com o perfil advogado), 5 pediram parâmetro obrigatório (422, comportamento correto), 2 endpoints deram erro 500, 2 tiveram timeout na primeira tentativa (endpoints de integração externa lentos).**

### 3.1 — Erros de servidor confirmados (além do já relatado na Parte 2)
- `GET /api/v1/rag/docs` → **500 Internal Server Error** (`"Erro interno. A equipe foi notificada."`). Este é o segundo endpoint de listagem simples (sem filtro nenhum) que quebra nesta auditoria — o primeiro foi `/deadlines/?page_size=100&status=all` na Parte 2. Padrão preocupante: dois módulos distintos (Prazos e Base de Conhecimento RAG) quebram em consultas de listagem básica.

### 3.2 — Módulos "vazios por falta de conteúdo cadastrado" (não é bug de código, é ausência de dado/configuração — mas afeta diretamente a experiência de primeiro uso)
- `GET /checklists/templates` → `[]` (nenhum modelo de checklist cadastrado)
- `GET /templates/` → `{"data":[],...}` (nenhum modelo de peça/documento cadastrado, apesar do motor de variáveis já existir e listar `cliente_nome, cliente_cpf_cnpj, numero_processo...`)
- `GET /workflow/templates` → `[]` (nenhum fluxo de trabalho cadastrado)
- `GET /prompts-juridicos` → lista vazia (nenhum prompt padronizado salvo)
- `GET /etiquetas` → `[]` (nenhuma etiqueta cadastrada)

Isso é relevante porque, na Parte 1, o texto de ajuda do próprio sistema descreve esses módulos como reduzindo trabalho repetitivo ("Padroniza o passo a passo de cada tipo de trabalho... com modelos prontos"). Hoje, para o advogado que loga pela primeira vez, esses módulos existem como funcionalidade mas estão **funcionalmente vazios** — a ajuda promete um benefício que depende de curadoria ainda não feita. Recomendo que a implantação do EJC inclua, como etapa obrigatória de onboarding do escritório, popular ao menos 3–5 modelos de checklist e de peça mais usados, para que o primeiro uso já demonstre valor.

### 3.3 — Integrações externas anunciadas mas desligadas
- `GET /infosimples/status` → `{"enabled":false,"configured":false}` (consulta de CPF/CNPJ/processos TJMG via Infosimples)
- `GET /nfse/status` → `{"enabled":false,"configured":false,"ambiente":"homologacao"}` (emissão de nota fiscal de serviço)
- `GET /intelligence-v3/radar/legislativo` → timeout na primeira tentativa (endpoint lento; segunda tentativa não testada por já ter evidência suficiente do padrão)

Três das integrações mais "operacionais" do sistema (consulta de documentos, emissão fiscal, radar legislativo) estão sem configuração ativa neste ambiente de produção. Não interpreto isso como bug — é razoável que integrações pagas de terceiros só sejam ligadas quando contratadas — mas é uma lacuna real entre "o que o sistema pode fazer" e "o que está fazendo hoje", que deveria estar visível para quem decide investir tempo configurando essas integrações.

### 3.4 — Dado desatualizado em ferramenta financeira
`GET /indices/taxa-juros` devolveu `"mes_referencia":"Set-2025"` — a base de taxas de juros (usada presumivelmente para calculadoras de correção monetária/análise bancária) está com referência de **setembro de 2025**, quase um ano defasada na data desta auditoria (julho de 2026). Qualquer cálculo de correção monetária ou análise de abusividade de taxa bancária feito com essa base estará usando dado desatualizado, o que é um risco de precisão técnica direto — recomendo verificar a rotina de atualização automática dessa fonte (provavelmente BACEN/SGS) o quanto antes.

### 3.5 — Volume de alertas regulatórios pode gerar fadiga de alerta
`GET /diario-oficial/alertas` → **262 alertas não lidos**. `GET /v1/regulatorio/digest-semanal` → 44 alertas só nos últimos 7 dias, quase todos da fonte "câmara", com "código penal" como palavra-chave mais frequente (15 ocorrências) — para um escritório cuja base de casos observada é majoritariamente de Direito do Consumidor, isso sugere que as palavras-chave monitoradas estão amplas demais (monitorando temas penais/legislativos genéricos de baixa relevância direta), gerando volume que tende a ser ignorado pelo usuário com o tempo. Recomendo revisar a lista de keywords cadastradas (`GET /diario-oficial/keywords`) e ajustar para os termos efetivamente ligados às áreas de atuação e aos nomes/OAB dos sócios — regra geral de sistemas de alerta: um alerta que ninguém lê deixa de ser um alerta.

### 3.6 — Autenticação de dois fatores disponível mas não habilitada
`GET /users/me/security` → `{"totp_enabled":false,"two_factor_available":true,...}` para o usuário de teste (perfil advogado, acesso a dados de clientes e casos). O recurso existe e está pronto (`/users/me/totp-qr`, `/auth/totp/setup`, `/auth/totp/verificar`, `/auth/totp/desativar` todos mapeados no frontend) mas não está ativo para este usuário. Considerando que o sistema lida com dados de clientes (LGPD) e que o Provimento 205/2021 da OAB reforça a responsabilidade do advogado sobre segurança de dados no uso de IA, recomendo exigir 2FA obrigatório para todos os perfis com acesso a casos/clientes, não deixar como opcional.

### 3.7 — Inconsistência de formato de erro (achado recorrente, agora com mais exemplos)
Catalogados nesta rodada, além dos já relatados na Parte 2, mais dois formatos distintos de erro de permissão para situações equivalentes:
- `GET /jurimetria/overview` → `"Apenas sócios têm acesso ao painel de jurimetria"`
- `GET /jurimetria/desfechos` → `"Apenas sócios têm acesso a métricas de êxito"`
- `GET /sociedade/socios` → `"Acesso restrito a sócios"`
- `GET /sociedade/distribuicao` → `"Forbidden"` (em inglês, sem explicação — destoa de todas as outras mensagens do sistema, que são em português e explicativas)
- `GET /v1/despesas`, `/v1/office-contracts` → `"Acesso restrito a gestão/financeiro"`

Cinco variações de texto para o mesmo tipo de bloqueio (perfil insuficiente). Nenhuma delas é insegura, mas a falta de padronização (incluindo uma mensagem em inglês solta no meio de um sistema totalmente em português) é o tipo de detalhe que, somado, passa uma impressão de sistema costurado por módulos independentes em vez de um produto único e coeso.

### 3.8 — Achado positivo a destacar: `/teses/motor` é mais cauteloso que a Sala Jurídica
Ao testar o motor de teses jurídicas isoladamente (`POST /teses/motor`) com os mesmos fatos do caso fictício, a IA foi mais conservadora do que na Sala Jurídica: sinalizou explicitamente que o dispositivo legal específico "não consta do contexto recuperado" e pediu confirmação antes de cravar a base legal. Isso mostra que diferentes pontos de entrada de IA no sistema têm níveis de acesso à base de conhecimento (RAG) e de contexto diferentes entre si — o que é aceitável, mas vale documentar para a equipe: o resultado da IA pode variar em precisão dependendo de qual tela/endpoint é usado para a mesma pergunta, e isso não é intuitivo para quem não conhece a arquitetura por trás.

---

## 4. Confirmações do fluxo de escrita (Cliente → Caso → Prazo → Tarefa)

Criando os registros de teste do zero (não apenas lendo), confirmei que o pipeline de escrita funciona corretamente quando seguido pela via oficial:
- Cliente e Caso criados via conversão da Sala Jurídica apareceram **imediatamente e corretamente** em `/clients/`, `/cases/` e no Dashboard (que subiu de 3→4 casos e 6→7 clientes de forma consistente) — **isso restringe e refina o achado da Parte 2**: o problema de listas vazias não é um defeito genérico do endpoint de listagem (que funciona bem para dado novo), e sim algo específico aos registros pré-existentes que o Dashboard contava mas que continuam inacessíveis via `/cases/`, `/clients/` e `/deadlines/` — reforça a recomendação de que a equipe técnica investigue diretamente no banco esses registros "órfãos" específicos, e não o código do endpoint de listagem em si.
- Criação de Prazo (`POST /deadlines/`) exige o campo `data_prazo` (ou `data_intimacao` + `dias_prazo`) — minha primeira tentativa com `data_vencimento` falhou com erro 422 claro e explicativo, o que é o comportamento correto de validação (só registro aqui para quem for integrar via API/automação saber o nome exato do campo).
- Criação de Tarefa (`POST /tasks/`) funcionou de primeira, com payload simples.
- Ferramenta de cálculo de prazo (`POST /deadlines/calcular`) funcionou corretamente e citou a base legal certa (art. 219 do CPC, contagem em dias úteis).
- Tentativa de criar um honorário (`POST /fees/`) foi corretamente **bloqueada** com 403 ("Sem permissão para alterar dados financeiros") — o perfil advogado pode consultar `/fees/` mas não criar lançamento financeiro, o que é uma separação de função (segregation of duties) adequada e não um bug.

---

## 5. Limitação da limpeza dos dados de teste (leia antes de considerar a auditoria "sem rastro")

A API não expõe, para o perfil advogado, exclusão definitiva (`DELETE`) de Casos, Clientes ou Prazos — apenas de Tarefas. Isso é, na minha avaliação, um desenho correto para um sistema de gestão jurídica (histórico de caso não deveria ser apagável por qualquer usuário, por motivos de auditoria e cadeia de custódia), mas significa que **não consegui remover definitivamente os registros de teste**. O que fiz, com o que a API permitiu:

| Registro | Ação tomada | Estado final |
|---|---|---|
| Tarefa "[TESTE AUDITORIA - EXCLUIR] Obter laudo técnico" | `DELETE` | **Removida definitivamente.** |
| Prazo "[TESTE AUDITORIA - EXCLUIR] Prazo para protocolar inicial" | `PATCH status=cancelado` | Permanece no banco, com status Cancelado, não deve aparecer em contagens de pendentes. |
| Caso "[TESTE AUDITORIA - EXCLUIR] Vício de produto - refrigerador" (id `a5de7e72-ff70-4468-a1f5-877bae01ef6f`) | `PATCH status=arquivado` + observação explicativa | Arquivado, fora da listagem ativa padrão. |
| Cliente "[TESTE AUDITORIA - EXCLUIR] Maria Ficticia da Silva Teste" (id `78edb08f-f0db-4af8-94e0-566756d51d3c`) | `PATCH status=inativo` + observação explicativa | Inativo, fora da listagem ativa padrão. |
| Sessão Sala Jurídica (id `cf478c34-dc6e-400d-8988-3b712b8337d6`) | Tentativa de arquivar recusada pelo sistema | **Bloqueada pelo próprio sistema** com a mensagem "Análise convertida em caso está congelada para auditoria" — comportamento correto de preservação de trilha de auditoria, não é falha. |

**Recomendo que um administrador (perfil sócio/admin/superadmin) exclua definitivamente esses registros pelo módulo Lixeira ou diretamente no banco**, já que meu perfil de teste não tinha essa permissão. Todos estão claramente identificados pelo prefixo `[TESTE AUDITORIA - EXCLUIR]` e pelos IDs acima para facilitar a localização.

---

## 6. Síntese de críticas e sugestões, por prioridade

**Crítico:**
1. Investigar e corrigir a origem dos 3 casos / 6 clientes / 2 prazos contados pelo Dashboard mas inacessíveis via `/cases/`, `/clients/`, `/deadlines/` (Parte 2, refinado na Seção 3 desta parte — não é bug do endpoint de listagem, é dado específico a localizar).
2. Corrigir a perda de dados na conversão Sala Jurídica → Caso (Seção 1 desta parte): a análise e as evidências levantadas pela IA precisam ser transferidas para o caso formal, não descartadas.
3. Investigar os dois erros 500 reproduzíveis (`/deadlines/` com `status=all`, `/rag/docs`).

**Alto:**
4. Ajustar o Índice de Risco para não classificar como "baixo risco" um caso apenas porque está sem documentos anexados — falta de evidência deveria ao menos gerar um alerta de "triagem incompleta", não uma leitura tranquilizadora.
5. Atualizar a base de taxas de juros (`/indices/taxa-juros`), defasada em quase um ano.
6. Exigir 2FA para perfis com acesso a casos/clientes.

**Médio:**
7. Popular checklists, templates de peça e prompts jurídicos padrão antes de considerar o sistema "pronto para uso" por um novo escritório — hoje esses módulos existem mas estão vazios.
8. Revisar as palavras-chave do Diário Oficial/Radar Regulatório para reduzir volume de alertas de baixa relevância (262 não lidos é sinal de alerta mal calibrado, não de vigilância eficaz).
9. Padronizar o texto das mensagens de erro de permissão (hoje há ao menos 5 variações, incluindo uma em inglês).
10. Ativar/configurar (ou documentar como pendente de contratação) as integrações Infosimples e NFS-e.

**Observação positiva a preservar:** o guardrail de LGPD que bloqueia envio de CPF/RG/nome completo a provedores de IA externos, e a recusa consistente da IA em citar jurisprudência não verificada, são controles reais e funcionando — não são apenas texto de marketing na tela de ajuda. Isso deveria ser destacado, não escondido, em qualquer material que o escritório use para explicar o sistema a clientes ou a órgãos de fiscalização.

---

## 7. O que ainda não foi testado

Por escopo e tempo desta rodada, não cobri: upload real de documento (multipart), assinatura eletrônica de documento, módulo Portal do Cliente (exige perfil "cliente", não "advogado" — todos os endpoints retornaram 403 "Acesso exclusivo do Portal do Cliente" ao testar com o perfil advogado, o que é o comportamento esperado), emissão de NFS-e (integração desligada), e os módulos administrativos restritos a sócio/admin/superadmin (Auditoria, Governança da IA, Cofre de Credenciais, Mapa de Módulos) — todos bloqueados corretamente para o perfil advogado, como já era esperado e confirmado nas Partes 2 e 3. Se quiser essa cobertura completa, preciso de um usuário de teste com perfil sócio ou admin.
