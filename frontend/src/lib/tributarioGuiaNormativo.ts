export const GUIA_TRIBUTARIO_DATA_BASE = "2026-09-06";

export type RegraGuiaTributario = {
  tema: string;
  regra: string;
  fonte: string;
  alerta?: string;
};

export const CHECKLIST_TRIBUTARIO = [
  "Identificar o tributo, o ente competente e o tipo de procedimento antes de calcular qualquer prazo.",
  "Preservar a prova da ciência/intimação: data, canal (DTE/e-CAC/SIARE/AR/publicação) e documento original.",
  "Calcular prazo somente pela regra vigente para o ente e para a data de ciência; nunca transportar prazo federal para Estado ou Município.",
  "Conferir o CTN compilado na data da análise — inclusive alterações da LC 236/2026, vigente desde 04/09/2026, quando houver lançamento, penalidade, exigibilidade, restituição, prescrição ou processo administrativo.",
  "Confirmar regime tributário, período de apuração, declarações entregues e pagamentos antes de apontar crédito ou passivo.",
  "Reunir auto/notificação, processo administrativo integral, procuração, contrato social e documentos fiscais/contábeis pertinentes.",
  "Verificar causas de suspensão da exigibilidade do CTN art. 151 na redação vigente e registrar a hipótese concreta — não presumir suspensão.",
  "Consultar situação fiscal federal e dívida ativa nos canais oficiais (Receita/e-CAC e REGULARIZE/PGFN), quando aplicável.",
  "Para MG, conferir o RPTA vigente, o e-PTA/SIARE e o Conselho de Contribuintes antes de definir rito ou prazo.",
  "Para Município, identificar Código Tributário, decreto/regulamento processual, órgão julgador e regra de ciência vigentes.",
  "Em recuperação de créditos, tratar o resultado do EJC como oportunidade potencial: validar escrituração, apuração, documentos, legitimidade, período, prescrição/decadência e via cabível.",
  "Antes de judicializar, definir ato coator/pretensão, competência, interesse processual, prazo próprio da ação e efeito pretendido.",
  "Registrar no caso a fonte oficial e a data-base usadas na conclusão jurídica.",
] as const;

export const REGRAS_PAF_FEDERAL: RegraGuiaTributario[] = [
  {
    tema: "Impugnação do lançamento",
    regra:
      "Regra vigente: 20 dias úteis. Para intimações realizadas até 31/03/2026, aplicar a transição do ADI RFB 2/2026: considerar 20 dias úteis ou 30 dias corridos, prevalecendo o vencimento posterior.",
    fonte:
      "Decreto 70.235/1972, art. 15, redação da LC 227/2026; ADI RFB 2/2026; Receita Federal — Prazo de impugnação (atualizado em 17/03/2026).",
  },
  {
    tema: "Recurso voluntário ao CARF",
    regra:
      "Regra geral vigente: 20 dias úteis da ciência da decisão de primeira instância. A transição até 31/03/2026 também deve ser observada.",
    fonte:
      "Decreto 70.235/1972, art. 33, redação da LC 227/2026; ADI RFB 2/2026; Receita Federal — Prazo do recurso voluntário (atualizado em 18/03/2026).",
  },
  {
    tema: "Suspensão de prazos processuais",
    regra:
      "Os prazos processuais do PAF federal ficam suspensos entre 20/12 e 20/01. Em 2026, a Receita orientou tratamento específico do período inicial de vigência da LC 227/2026, inclusive suspensão entre 14 e 20/01 quando pertinente.",
    fonte:
      "Decreto 70.235/1972, art. 5º-A; LC 227/2026; Receita Federal — Perguntas e Respostas Prazos Processuais (13/03/2026).",
  },
  {
    tema: "Prazos previstos em lei específica",
    regra:
      "A alteração para dias úteis não converte automaticamente todo prazo tributário federal. Quando lei específica fixa prazo próprio, deve-se aplicar essa regra específica.",
    fonte:
      "Receita Federal — Perguntas e Respostas Prazos Processuais LC 227/2026.",
    alerta:
      "Exemplo oficial: a manifestação de inconformidade do art. 74 da Lei 9.430/1996 mantém prazo específico de 30 dias corridos.",
  },
  {
    tema: "Recurso especial / CSRF",
    regra:
      "Não manter prazo estático no guia. Verificar admissibilidade, hipótese de divergência, prazo e rito no RICARF vigente na data do ato.",
    fonte:
      "RICARF — Portaria MF 1.634/2023 e alterações vigentes; página institucional do CARF.",
  },
];

export const REGRAS_CTN_2026: RegraGuiaTributario[] = [
  {
    tema: "LC 236/2026 — vigência imediata",
    regra:
      "A LC 236/2026 foi publicada em 04/09/2026 e entrou em vigor na própria data. Para atos e análises posteriores, não usar versão antiga do CTN sem conferir a incidência temporal da nova redação.",
    fonte: "Lei Complementar 236/2026, art. 3º; CTN compilado — Planalto.",
  },
  {
    tema: "Lançamento por homologação",
    regra:
      "O CTN art. 150 recebeu §§ 5º e 6º: dolo, fraude ou simulação remetem a contagem para o art. 173 I; no pagamento parcial de tributo sujeito a homologação, o prazo decadencial é contado da ocorrência do fato gerador. A aplicação concreta exige identificar modalidade, pagamento e período.",
    fonte: "CTN art. 150, §§ 4º a 6º, redação vigente após LC 236/2026.",
  },
  {
    tema: "Suspensão da exigibilidade",
    regra:
      "O art. 151 foi ampliado. Além das hipóteses tradicionais, a redação vigente prevê, nos termos da legislação específica, arbitragem especial, proposta de transação aceita, acordo de mediação e determinadas garantias aceitas pelo credor em execução fiscal. Não presumir efeito suspensivo sem conferir os requisitos legais/regulatórios da hipótese.",
    fonte: "CTN art. 151, incisos e §§ incluídos/alterados pela LC 236/2026.",
  },
  {
    tema: "Restituição e habilitação de indébito",
    regra:
      "A LC 236 acrescentou o art. 165-A e os §§ 2º e 3º do art. 168. A atualização do indébito segue os índices dos créditos do respectivo ente; o prazo do art. 168 também se aplica à habilitação, e a habilitação decorrente de decisão judicial transitada em julgado possui regra própria de termo inicial na certificação do trânsito.",
    fonte: "CTN arts. 165-A e 168, §§ 2º-3º, incluídos pela LC 236/2026.",
  },
  {
    tema: "Prescrição — novas causas do art. 174",
    regra:
      "A lista histórica de causas interruptivas não é mais suficiente. A redação vigente do art. 174 passou a contemplar, entre outras hipóteses, protesto extrajudicial da CDA, mediação, arbitragem especial, evento específico de extinção da execução, informação do crédito em falência/liquidação e ato inicial de execução fiscal extrajudicial. O § 3º também disciplina o reinício da prescrição interrompida.",
    fonte: "CTN art. 174, redação da LC 236/2026.",
    alerta:
      "Não usar calculadora que aceite apenas uma data e uma lista antiga de interrupções para conclusão de prescrição.",
  },
  {
    tema: "Processo administrativo dos entes",
    regra:
      "A LC 236 introduziu normas gerais de processo administrativo tributário e determinou que Estados, Distrito Federal e Municípios atualizem sua legislação em até dois anos para adotar parâmetros mínimos. Isso não autoriza aplicar automaticamente o rito federal nem inventar prazo local.",
    fonte: "CTN arts. 208-A a 208-J e 211-A/211-B, incluídos pela LC 236/2026.",
  },
];

export const REGRAS_CARF: RegraGuiaTributario[] = [
  {
    tema: "Empate / voto de qualidade",
    regra:
      "O empate no CARF não é proclamado automaticamente em favor do contribuinte. A Lei 14.689/2023 restabeleceu a proclamação do resultado pelo voto de qualidade previsto no art. 25, § 9º, do Decreto 70.235/1972.",
    fonte: "Lei 14.689/2023, arts. 1º, 2º e 17; Decreto 70.235/1972, art. 25, § 9º.",
  },
  {
    tema: "Decisão favorável à Fazenda por voto de qualidade",
    regra:
      "Há consequências legais específicas para a parcela decidida favoravelmente à Fazenda pelo voto de qualidade, incluindo exclusão de multas e cancelamento da representação fiscal para fins penais nos termos legais; demais efeitos dependem da hipótese concreta.",
    fonte:
      "Decreto 70.235/1972, arts. 25, § 9º-A, e 25-A, conforme Lei 14.689/2023.",
    alerta:
      "Não transformar essas consequências em regra genérica de inexigibilidade do principal nem em vitória automática do contribuinte.",
  },
];

export const REGRAS_MG: RegraGuiaTributario[] = [
  {
    tema: "Processo tributário administrativo de MG",
    regra:
      "O RPTA de Minas Gerais é disciplinado pelo Decreto 44.747/2008. A impugnação é dirigida ao Conselho de Contribuintes e, na regra do art. 117 vigente consultada, é apresentada em 30 dias contados da intimação do lançamento ou do indeferimento de restituição.",
    fonte: "Decreto MG 44.747/2008 (RPTA), especialmente arts. 103, 117, 120 e 121 — SEF/MG.",
    alerta:
      "A LC 236/2026 impõe atualização mínima da legislação processual dos entes em prazo legal. Conferir alterações estaduais posteriores à data-base antes de reutilizar esta regra.",
  },
  {
    tema: "e-PTA / SIARE",
    regra:
      "Quando o processo tramita como e-PTA, os atos eletrônicos devem seguir o RPTA e os canais oficiais da SEF/MG/SIARE; o meio de protocolo deve ser confirmado no próprio processo.",
    fonte: "Decreto MG 44.747/2008 (RPTA) e orientações vigentes da SEF/MG.",
  },
  {
    tema: "Judicialização em Minas Gerais",
    regra:
      "Competência depende do ente e da causa. Demandas tributárias federais em Minas Gerais pertencem à Justiça Federal da 6ª Região; matérias estaduais/municipais, em regra, seguem a Justiça Estadual, observadas as regras de competência.",
    fonte:
      "TRF6 — página institucional (competência sobre todo o Estado de Minas Gerais); Lei 14.226/2021; regras constitucionais e processuais de competência.",
  },
];

export const REGRAS_MUNICIPAIS: RegraGuiaTributario[] = [
  {
    tema: "Betim, Contagem, Belo Horizonte e demais municípios",
    regra:
      "Não existe prazo municipal genérico de 30 dias no EJC. Antes de orientar defesa ou recurso, identificar Município, tributo, norma processual vigente, órgão julgador, forma de ciência e eventual regra especial do lançamento.",
    fonte:
      "Código Tributário e regulamentos do Município competente, na versão vigente na data do ato; CTN arts. 211-A/211-B após LC 236/2026; publicação oficial municipal.",
    alerta:
      "A obrigação de atualização criada pela LC 236/2026 não transforma automaticamente o processo municipal em cópia do PAF federal.",
  },
];

export const REGRAS_JUDICIAIS: RegraGuiaTributario[] = [
  {
    tema: "Mandado de segurança",
    regra:
      "O prazo decadencial de 120 dias é contado da ciência do ato impugnado, observada a adequação do mandado de segurança e a identificação da autoridade coatora. O encerramento do processo administrativo não cria, por si só, um novo prazo universal de 120 dias.",
    fonte: "Lei 12.016/2009, art. 23, e jurisprudência aplicável ao ato impugnado.",
  },
  {
    tema: "Ação anulatória / declaratória",
    regra:
      "Não usar no guia um prazo automático de 5 anos contado do encerramento administrativo. A pretensão, o termo inicial, a natureza do crédito e a jurisprudência precisam ser identificados no caso concreto.",
    fonte: "CTN na redação vigente, legislação processual e jurisprudência aplicável à pretensão concreta.",
  },
  {
    tema: "Repetição de indébito / habilitação",
    regra:
      "O CTN prevê prazo de 5 anos nas hipóteses do art. 168, com termo inicial definido pela hipótese legal. Após a LC 236/2026, conferir também os §§ 2º e 3º: a regra alcança habilitação e há termo inicial específico para habilitação decorrente de decisão judicial transitada em julgado. Modulações, compensação e regras específicas do tributo continuam relevantes.",
    fonte: "CTN arts. 165 a 168, especialmente art. 168 §§ 2º-3º após LC 236/2026.",
  },
  {
    tema: "Embargos à execução fiscal",
    regra:
      "A LEF prevê prazo de 30 dias, mas o termo inicial depende da hipótese do art. 16: depósito, juntada da prova da fiança/seguro garantia ou intimação da penhora. Registrar o evento correto antes de calcular.",
    fonte: "Lei 6.830/1980, art. 16.",
  },
  {
    tema: "Prescrição intercorrente",
    regra:
      "Não reduzir a análise a uma soma cega de 1 ano + 5 anos. Identificar ciência da Fazenda sobre não localização do devedor/bens, suspensão, arquivamento, citação/constrição efetiva e eventos posteriores, aplicando LEF art. 40, Temas 566-571 do STJ e CTN art. 174 na redação vigente.",
    fonte: "LEF art. 40; STJ REsp 1.340.553/RS, Temas 566-571; CTN art. 174 após LC 236/2026.",
  },
];

export const REGRAS_CREDITOS: RegraGuiaTributario[] = [
  {
    tema: "Natureza da saída do motor fiscal",
    regra:
      "XML/NF-e pode sustentar triagem e memória de cálculo preliminar, mas não prova, sozinho, crédito líquido, certo e recuperável. O EJC deve registrar hipótese/oportunidade potencial, documentos faltantes, período documental, risco e confiança.",
    fonte:
      "CTN na redação vigente e legislação específica de cada tributo/tese; escrituração e declarações fiscais/contábeis do contribuinte; precedentes aplicáveis.",
  },
  {
    tema: "Janela temporal do XML não é prescrição",
    regra:
      "A data de emissão da NF-e não é termo inicial universal do prazo do art. 168. Um filtro de documentos por data pode servir à triagem, mas não deve chamar notas antigas de prescritas nem excluí-las juridicamente sem identificar pagamento/extinção, hipótese de restituição, decisão, habilitação e demais marcos aplicáveis.",
    fonte: "CTN art. 168 na redação vigente, inclusive §§ 2º-3º após LC 236/2026.",
  },
  {
    tema: "Validação mínima",
    regra:
      "Antes de compensar, pedir restituição ou ajuizar: validar legitimidade, regime, fatos geradores, pagamentos, apurações, retificações, prescrição/decadência, modulação, documentação e via procedimental cabível.",
    fonte: "Legislação tributária específica e documentação do contribuinte.",
  },
];

export const FONTES_OFICIAIS_GUIA = [
  "Planalto — Constituição, CTN compilado, Decreto 70.235/1972, Lei 14.689/2023, LC 227/2026, LC 236/2026 e Lei 6.830/1980",
  "Receita Federal — Julgamento Administrativo e Perguntas e Respostas Prazos Processuais LC 227/2026",
  "STJ — Temas repetitivos 566-571 (prescrição intercorrente na execução fiscal)",
  "CARF — Regimento Interno vigente e jurisprudência administrativa",
  "PGFN / REGULARIZE — dívida ativa e negociação tributária federal",
  "SEF/MG — RPTA, SIARE/e-PTA e legislação tributária estadual",
  "TRF6 — Justiça Federal da 6ª Região em Minas Gerais",
  "Portais oficiais de Fazenda de Betim, Contagem e Belo Horizonte para normas e processos municipais",
] as const;
