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
  "Confirmar regime tributário, período de apuração, declarações entregues e pagamentos antes de apontar crédito ou passivo.",
  "Reunir auto/notificação, processo administrativo integral, procuração, contrato social e documentos fiscais/contábeis pertinentes.",
  "Verificar causas de suspensão da exigibilidade do CTN art. 151 e registrar a hipótese concreta — não presumir suspensão.",
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
      "RICARF — Portaria MF 1.634/2023, página institucional do CARF atualizada até a Portaria MF 1.398/2026.",
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
      "Código Tributário e regulamentos do Município competente, na versão vigente na data do ato; publicação oficial municipal.",
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
    fonte: "CTN, legislação processual e jurisprudência aplicável à pretensão concreta.",
  },
  {
    tema: "Repetição de indébito",
    regra:
      "O CTN prevê prazo de 5 anos nas hipóteses do art. 168, com termo inicial definido pela hipótese legal; modulações, compensação e regras específicas do tributo devem ser verificadas.",
    fonte: "CTN, arts. 165 a 168, legislação específica e precedentes aplicáveis.",
  },
  {
    tema: "Embargos à execução fiscal",
    regra:
      "A LEF prevê prazo de 30 dias, mas o termo inicial depende da hipótese do art. 16. Registrar o evento de garantia/intimação correto antes de calcular.",
    fonte: "Lei 6.830/1980, art. 16.",
  },
];

export const REGRAS_CREDITOS: RegraGuiaTributario[] = [
  {
    tema: "Natureza da saída do motor fiscal",
    regra:
      "XML/NF-e pode sustentar triagem e memória de cálculo preliminar, mas não prova, sozinho, crédito líquido, certo e recuperável. O EJC deve registrar hipótese/oportunidade potencial, documentos faltantes, período, risco e confiança.",
    fonte:
      "CTN e legislação específica de cada tributo/tese; escrituração e declarações fiscais/contábeis do contribuinte; precedentes aplicáveis.",
  },
  {
    tema: "Validação mínima",
    regra:
      "Antes de compensar, pedir restituição ou ajuizar: validar legitimidade, regime, fatos geradores, pagamentos, apurações, retificações, prescrição/decadência, modulação, documentação e via procedimental cabível.",
    fonte: "Legislação tributária específica e documentação do contribuinte.",
  },
];

export const FONTES_OFICIAIS_GUIA = [
  "Planalto — Constituição, CTN, Decreto 70.235/1972, Lei 14.689/2023, LC 227/2026 e Lei 6.830/1980",
  "Receita Federal — Julgamento Administrativo e Perguntas e Respostas Prazos Processuais LC 227/2026",
  "CARF — Regimento Interno vigente e jurisprudência administrativa",
  "PGFN / REGULARIZE — dívida ativa e negociação tributária federal",
  "SEF/MG — RPTA, SIARE/e-PTA e legislação tributária estadual",
  "TRF6 — Justiça Federal da 6ª Região em Minas Gerais",
  "Portais oficiais de Fazenda de Betim, Contagem e Belo Horizonte para normas e processos municipais",
] as const;
