# Ferramentas jurídicas já implementadas e sem interface

**O que este documento é:** o inventário pedido pelo Bloco 4 do
`docs/auditoria/plano-lancamento-v3.md` — *"antes de construir a interface, teste
as 15 e me diga o que cada uma exige e retorna"*.

**Primeira correção ao plano:** não são 15. `backend/app/routers/ramos.py`
declara **55** rotas `/<área>/ferramentas/*`, em **14** áreas, das quais 4 são
aliases depreciados que apenas delegam à rota canônica. A auditoria enxergou
apenas as três áreas que testou (cível, empresarial e penal) e generalizou a
contagem a partir delas.

O inventário abaixo foi extraído automaticamente do código e cobre **52** das
55 — três decoradores de múltiplas linhas escaparam do extrator. Confira o
arquivo-fonte antes de tratar esta lista como exaustiva.

**Por que isso importa:** o plano classifica a exposição destas rotas como "o
maior ganho de valor por esforço" da auditoria — valor já construído e pago, a
um trabalho de frontend de distância. O tamanho real do acervo dobra esse
ganho, e também dobra o trabalho de interface. Construir 55 telas não é
"um trabalho de frontend"; é um módulo.

**Recomendação:** não construir 55 telas. Construir **uma** tela de
ferramentas com busca, e nela expor primeiro as das áreas que o escritório
pratica — consumidor e cível, pelos casos existentes. As demais aparecem na
mesma busca conforme a prática exigir, sem custo de tela nova.

---

## Como ler

Todas respondem a `GET` com parâmetros de query e devolvem JSON. Todas exigem
autenticação e perfil de equipe. Nenhuma grava nada — são funções de cálculo
puras sobre a entrada, o que as torna seguras de expor e baratas de testar.

As marcadas **(depreciada)** existem só para não quebrar chamadas antigas e
**não devem ganhar tela**: delegam à rota canônica indicada na descrição.

---

### admin-esp

**`GET /api/admin-esp/ferramentas/mandado-seguranca`**

Prazo DECADENCIAL do Mandado de Segurança: 120 dias CORRIDOS contados da ciência, pelo interessado, do ato impugnado (Lei 12.016/2009 art. 23) — prazo

Parâmetros: `data_ato_coator`

**`GET /api/admin-esp/ferramentas/reajuste-contrato-administrativo`**

Reajuste em sentido estrito pelo índice PREVISTO no contrato, respeitada a ANUALIDADE (Lei 14.133/2021 arts. 25 §7º e 92 §3º c/c Lei 10.192/2001 art. 

Parâmetros: `valor_original`, `indice_acumulado_pct`, `meses_contrato`, `indice_nome`, `data_base`

**`GET /api/admin-esp/ferramentas/recurso-multa-transito`** **(depreciada)**

Alias mantido por compatibilidade — delega à implementação ÚNICA de /transito/ferramentas/prazos-recurso (rota canônica; retirada na Onda 3).

Parâmetros: `response`, `fase`, `data_notificacao_autuacao`, `data_notificacao_penalidade`, `data_ciencia_decisao_jari`, `valor_multa`


### ambiental

**`GET /api/ambiental/ferramentas/auto-infracao-ambiental`**

Prazos, descontos e teses de defesa contra auto de infração ambiental federal (Lei 9.605/98 · Decreto 6.514/2008).

Parâmetros: `data_ciencia`, `valor_multa`, `tipo_infracao`

**`GET /api/ambiental/ferramentas/crimes-ambientais`**

Penas e institutos despenalizadores por tipo de crime ambiental (Lei 9.605/98).

Parâmetros: `tipo_crime`, `pessoa`

**`GET /api/ambiental/ferramentas/licenciamento`**

Fases, documentos mínimos e prazos do licenciamento ambiental — classes, modalidades e prazos CONCRETOS dependem da UF e da norma do órgão licenciador

Parâmetros: `uf`, `fase`, `porte`, `orgao`, `data_protocolo`, `com_eia_rima`

**`GET /api/ambiental/ferramentas/reserva-legal`**

Percentual e área de Reserva Legal por bioma/localização — percentuais do art. 12 da Lei 12.651/2012 como REGRA FEDERAL GERAL; o enquadramento concret

Parâmetros: `area_imovel_ha`, `uf`, `bioma`, `inscrito_car`, `municipio`

**`GET /api/ambiental/ferramentas/tac-ambiental`**

Requisitos, cláusulas essenciais e efeitos do Termo de Ajustamento de Conduta.

Parâmetros: `orgao_proponente`, `tipo_dano`, `area_afetada_ha`, `valor_estimado_dano`


### bancario

**`GET /api/bancario/ferramentas/analise-juros`**

Análise de spreads e abusividade de juros. Súm. STJ 530: pactuação é livre para IF após a STJ 381 (revisada em 2015). STJ REsp 1.061.530 (leading case

Parâmetros: `taxa_mensal_contratada`, `taxa_mensal_referencia`, `valor_contratado`

**`GET /api/bancario/ferramentas/busca-apreensao`**

Prazos e estratégias em busca e apreensão de bem alienado fiduciariamente. Base: Dec.-Lei 911/69 (red. Lei 13.043/2014 e 10.931/2004).

Parâmetros: `data_notificacao`, `valor_divida`, `bem_descricao`

**`GET /api/bancario/ferramentas/juros-abusivos`**

Compara a taxa contratada com a média de mercado (BACEN) p/ tese revisional — classificação INDICATIVA, sem veredito de abusividade (aferição é casuís

Parâmetros: `taxa_contratada_mensal_pct`, `taxa_media_bacen_mensal_pct`

**`GET /api/bancario/ferramentas/superendividamento`**

Triagem de superendividamento (CDC art. 54-A, incl. Lei 14.181/2021). MÍNIMO EXISTENCIAL: o Decreto 11.150/2022 (red. Dec. 11.567/2023) fixa a renda m

Parâmetros: `renda_mensal`, `total_parcelas_mes`


### civel

**`GET /api/civel/ferramentas/alimentos-calcular`**

Estimativa aritmética de alimentos a partir do percentual INFORMADO. NÃO existe percentual legal ou jurisprudencial fixo (o "30%" é praxe forense, não

Parâmetros: `salario_devedor`, `percentual`, `filhos`

**`GET /api/civel/ferramentas/calculo-dano-moral`**

Estruturação metodológica do dano moral — SEM valor sugerido automático: não há tabelamento legal (tarifação vedada) e o quantum é arbitrado caso a ca

Parâmetros: `tipo_caso`, `salarios_minimos_pedido`

**`GET /api/civel/ferramentas/partilha-divorcio`**

O que se partilha no divórcio, por regime de bens (CC arts. 1.658-1.688).

Parâmetros: `regime_bens`, `data_casamento`, `data_separacao_fatos`

**`GET /api/civel/ferramentas/prazos-contestacao`**

Prazo de contestação por rito. • Rito comum: 15 dias ÚTEIS (CPC arts. 335 e 219), contados do marco do art. 335 (audiência de conciliação ou juntada d

Parâmetros: `rito`, `marco`, `data_marco`

**`GET /api/civel/ferramentas/prescricao-consumidor`**

Prescrição (5 anos, fato do produto/serviço) e decadência (30/90 dias, vício).

Parâmetros: `data_fato`, `tipo_vicio`

**`GET /api/civel/ferramentas/rescisao-locacao`**

Multa PROPORCIONAL na devolução antecipada (Lei 8.245/91 art. 4º).

Parâmetros: `data_inicio`, `data_rescisao_pretendida`, `valor_aluguel`, `tipo_locacao`, `quem_rescinde`, `prazo_contrato_meses`, `multa_contratual_alugueis`

**`GET /api/civel/ferramentas/usucapiao-verificar`**

Requisitos de usucapião por modalidade (CC arts. 1.238-1.244 · CF arts. 183 e 191). Prazos REDUZIDOS têm requisitos próprios e são informados à parte 

Parâmetros: `tipo`, `anos_posse`, `posse_mansa`


### consumidor

**`GET /api/consumidor/ferramentas/devolucao-dobro`**

Repetição em dobro do indébito — CDC art. 42 §ún. c/c STJ EAREsp 676.608/RS: o dobro NÃO exige má-fé; basta a cobrança indevida contrária à boa-fé OBJ

Parâmetros: `valor_cobrado_indevidamente`, `houve_pagamento`, `cobranca_contraria_boa_fe_objetiva`, `engano_justificavel`

**`GET /api/consumidor/ferramentas/negativacao-indevida`**

Checklist de análise da negativação indevida — a Súmula 385 STJ só afasta o dano moral se a inscrição ANTERIOR for LEGÍTIMA, CONTEMPORÂNEA e ATIVA; a 

Parâmetros: `existe_inscricao_anterior`, `inscricao_anterior_legitima_e_ativa`, `origem_verificada`

**`GET /api/consumidor/ferramentas/prazos-cdc`**

Decadência/prescrição do consumidor — a PRETENSÃO define instituto, prazo e termo inicial: vício aparente 30/90 dias da entrega (CDC art. 26 I-II e §1

Parâmetros: `pretensao`, `data_marco`, `bem_duravel`


### empresarial

**`GET /api/empresarial/ferramentas/juros-mora`**

Juros de mora sobre débito contratual — CC art. 406, red. Lei 14.905/2024. Desde 30/08/2024 NÃO existe mais o default de 1% a.m.: sem taxa convenciona

Parâmetros: `regime`, `valor_principal`, `data_inicio_mora`, `data_fim`, `selic_acumulada_percent`, `ipca_acumulado_percent`, `aplicar_regra_anterior`, `taxa_mensal_percent`, `multa_pct`

**`GET /api/empresarial/ferramentas/prazos-rj`**

Marcos temporais da recuperação judicial — Lei 11.101/2005 (red. Lei 14.112/2020). NENHUM marco conta da distribuição; cada um tem termo inicial própr

Parâmetros: `data_publicacao_deferimento`, `data_deferimento`, `data_concessao`


### familia

**`GET /api/familia/ferramentas/debito-alimentos`**

Rito da execução de alimentos (CPC art. 528 §7º; Súm. 309 STJ): autorizam a PRISÃO civil as 3 prestações ANTERIORES ao ajuizamento e as que VENCEREM n

Parâmetros: `datas_vencimento_em_aberto`, `data_ajuizamento_execucao`, `valor_parcela`

**`GET /api/familia/ferramentas/itcmd-inventario`**

ITCMD sobre o monte partilhável — SEM alíquota default: a alíquota é a da LEI ESTADUAL da UF vigente na data do fato gerador (Súm. 112 STF: alíquota d

Parâmetros: `valor_monte`, `uf`, `aliquota_percent`, `data_fato_gerador`


### imobiliario

**`GET /api/imobiliario/ferramentas/distrato`**

Distrato de imóvel na planta (Lei 13.786/2018): pena convencional de ATÉ 25% da quantia paga — ou ATÉ 50% quando a incorporação estiver submetida a pa

Parâmetros: `valor_pago`, `regime_patrimonio_afetacao`, `percentual_retencao`, `comissao_corretagem`, `meses_fruicao`, `valor_fruicao_mensal`

**`GET /api/imobiliario/ferramentas/prazos-despejo`**

Prazos da ação de despejo e purga da mora (Lei 8.245/91 art. 62 II: 15 dias contados da CITAÇÃO para purga).

Parâmetros: `data_citacao`, `forma_comunicacao`, `fundamento`

**`GET /api/imobiliario/ferramentas/reajuste-aluguel`**

Reajuste de aluguel pelo índice PACTUADO no contrato (Lei 8.245/91 art. 18), respeitada a periodicidade ANUAL mínima (Lei 10.192/2001 art. 2º §1º). O 

Parâmetros: `valor_atual`, `indice_percentual`, `indice_nome`, `data_base`


### penal

**`GET /api/penal/ferramentas/dosimetria`**

Simulador ASSISTIDO do cálculo trifásico da pena (CP art. 68), em MESES. 1ª fase (art. 59): pena-base = mínimo + 1/8 do intervalo (máx−mín) por circun

Parâmetros: `pena_minima_meses`, `pena_maxima_meses`, `circunstancias_judiciais_desfavoraveis`, `n_agravantes`, `n_atenuantes`, `causas_aumento`, `causas_diminuicao`

**`GET /api/penal/ferramentas/prazos-processuais`**

Prazos do processo penal — contagem em dias CORRIDOS (CPP art. 798: exclui-se o dia do começo e inclui-se o do vencimento; §3º: vencimento em domingo/

Parâmetros: `data_citacao`

**`GET /api/penal/ferramentas/prescricao-penal`**

Prescrição penal (CP arts. 109, 110, 115 e 117) — rota canônica. A rota /penal/ferramentas/prescricao-punitiva usa a MESMA implementação e será removi

Parâmetros: `data_fato`, `pena_maxima_anos`, `pena_concreta_anos`, `marcos_interruptivos`, `menor_21_na_data_fato`, `maior_70_na_sentenca`

**`GET /api/penal/ferramentas/prescricao-punitiva`** **(depreciada)**

Prescrição penal — implementação ÚNICA compartilhada com /penal/ferramentas/prescricao-penal (rota canônica). Ver _prescricao_penal_consolidada.

Parâmetros: `response`, `data_fato`, `pena_maxima_anos`, `pena_concreta_anos`, `marcos_interruptivos`, `menor_21_na_data_fato`, `maior_70_na_sentenca`

**`GET /api/penal/ferramentas/verificar-anpp`**

Verifica requisitos do Acordo de Não Persecução Penal — CPP art. 28-A (incluído pela Lei 13.964/2019). TODOS os requisitos e impeditivos legais são in

Parâmetros: `pena_minima_anos`, `sem_violencia_grave_ameaca`, `confissao_formal_circunstanciada`, `reincidente`, `conduta_criminal_habitual_reiterada_profissional`, `beneficiado_anpp_transacao_sursis_5anos`, `violencia_domestica_familiar_ou_razao_genero`


### previdenciario

**`GET /api/previdenciario/ferramentas/carencia`**

Carência por benefício e categoria (Lei 8.213/91 arts. 24-27): aposentadorias 180 contribuições (art. 25 II); auxílio por incapacidade 12 (art. 25 I),

Parâmetros: `beneficio`, `categoria`, `meses_contribuicao`, `decorre_acidente_ou_doenca_isenta`

**`GET /api/previdenciario/ferramentas/prazos`**

Motor de marcos previdenciários — cada natureza tem marco PRÓPRIO: • revisão do ato de concessão: DECADÊNCIA de 10 anos do dia 1º do mês seguinte ao P

Parâmetros: `natureza`, `data_primeiro_pagamento`, `data_ciencia_decisao`, `data_ajuizamento`

**`GET /api/previdenciario/ferramentas/tempo-contribuicao`**

Regra de transição por pontos (EC 103/2019 art. 15). Pontos = idade + tempo.

Parâmetros: `idade`, `tempo_contribuicao_anos`, `sexo`, `ano`


### trabalhista

**`GET /api/trabalhista/ferramentas/horas-extras`** **(depreciada)**

Alias DEPRECIADO de /trabalhista-esp/ferramentas/horas-extras. Handler próprio (e não decorator empilhado) porque o alias precisa do ``Response`` para

Parâmetros: `response`, `salario_mensal`, `horas_extras_mes`, `divisor`, `percentual_he`, `incluir_dsr`, `incluir_reflexo_fgts`


### trabalhista-esp

**`GET /api/trabalhista-esp/ferramentas/deposito-recursal`**

Calcula depósito recursal para Recurso Ordinário e Recurso de Revista. Metodologia (CLT art. 899 §1º): o depósito recursal corresponde ao VALOR DA CON

Parâmetros: `valor_condenacao`, `data_referencia`

**`GET /api/trabalhista-esp/ferramentas/prazos`**

Prazos recursais trabalhistas a partir da CIÊNCIA da decisão — TODOS em dias ÚTEIS (CLT art. 775, red. Lei 13.467/2017). O depósito recursal e as cust

Parâmetros: `data_ciencia`, `tipo_prazo`

**`GET /api/trabalhista-esp/ferramentas/prescricao-trabalhista`**

Prescrição trabalhista — CF art. 7º XXIX c/c CLT art. 11 e Súm. 308 TST. • BIENAL: a ação deve ser ajuizada até 2 anos após a extinção do contrato. • 

Parâmetros: `data_extincao_contrato`, `data_ajuizamento`

**`GET /api/trabalhista-esp/ferramentas/verbas-rescisorias`**

Verbas rescisórias completas. Delegado à MESMA calculadora auditável de /calculadoras/trabalhista/rescisao (app/services/calc/trabalhista.py), remodel

Parâmetros: `salario`, `data_admissao`, `data_demissao`, `tipo_rescisao`, `saldo_fgts`, `aviso_previo`


### transito

**`GET /api/transito/ferramentas/pontuacao-cnh`**

Sistema 20/30/40 de pontos da CNH — CTB art. 261 (red. Lei 14.071/2020): 40 pontos sem infração gravíssima; 30 com UMA gravíssima; 20 com DUAS ou mais

Parâmetros: `pontos_total`, `qtd_gravissimas`, `exerce_atividade_remunerada`

**`GET /api/transito/ferramentas/prazos-recurso`**

Prazos de defesa/recurso de multa de trânsito (CTB red. Lei 14.071/2020). • Defesa prévia: MÍNIMO 30 dias da notificação da AUTUAÇÃO (art. 281-A); • J

Parâmetros: `fase`, `data_notificacao_autuacao`, `data_notificacao_penalidade`, `data_ciencia_decisao_jari`, `valor_multa`

**`GET /api/transito/ferramentas/valor-multa`**

Valor da multa por gravidade (CTB art. 258) com fator multiplicador.

Parâmetros: `gravidade`, `multiplicador`


### tributario

**`GET /api/tributario/ferramentas/auto-infracao-prazos`**

Prazo de impugnação de auto de infração tributário (federal: 30 dias — Decreto 70.235/72 art. 15) e reduções de multa de ofício (Lei 8.218/91 art. 6º)

Parâmetros: `data_ciencia`, `valor_multa`, `esfera`

**`GET /api/tributario/ferramentas/multa-mora`**

Multa de mora de tributos: FEDERAL = 0,33%/dia limitada a 20% (Lei 9.430/96 art. 61). Estadual/municipal: a multa é a da LEI DO ENTE — sem cálculo com

Parâmetros: `ente`, `valor_tributo`, `dias_atraso`

**`GET /api/tributario/ferramentas/parcelamento`**

Simulação SIMPLIFICADA de parcelamento tributário por modalidade.

Parâmetros: `valor_total_debito`, `parcelas`, `modalidade`

**`GET /api/tributario/ferramentas/prescricao-decadencia`**

Decadência do direito de lançar (CTN 150 §4º/173 I) e prescrição da cobrança do crédito constituído (CTN 174) — sempre 5 anos, marcos distintos.

Parâmetros: `data_fato_gerador`, `tipo`

**`GET /api/tributario/ferramentas/reforma-tributaria`**

Informativo estruturado da transição CBS/IBS (EC 132/2023 · LC 214/2025).

Parâmetros: `receita_bruta_anual`, `regime_atual`, `atividade`, `ano_analise`

**`GET /api/tributario/ferramentas/regime-tributario`**

Comparativo ESTIMADO Simples × Lucro Presumido × Lucro Real (federais). Estimativa simplificada e documentada — NÃO substitui estudo tributário.

Parâmetros: `receita_bruta_anual`, `lucro_estimado_pct`, `atividade`

**`GET /api/tributario/ferramentas/simples-nacional`**

Faixa, alíquota nominal e alíquota EFETIVA do Simples Nacional por RBT12. Fórmula legal: (RBT12 × alíquota nominal − parcela a deduzir) ÷ RBT12 (LC 12

Parâmetros: `receita_bruta_12m`, `anexo`

