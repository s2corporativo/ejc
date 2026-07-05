// ── src/pages/ramos/ramosConfig.ts ───────────────────────────────────────────
export type CampoTipo =
  | "text"
  | "number"
  | "date"
  | "select"
  | "textarea"
  | "checkbox";

export interface CampoConfig {
  nome: string;
  label: string;
  tipo: CampoTipo;
  opcoes?: string[];
  obrigatorio?: boolean;
  placeholder?: string;
  col?: 1 | 2;
  ajuda?: string;
}

export interface FerramentaCampo {
  nome: string;
  label: string;
  tipo: "number" | "date" | "select" | "text";
  opcoes?: string[];
  default?: string | number;
}

export interface FerramentaConfig {
  id: string;
  titulo: string;
  descricao: string;
  baseLegal: string;
  endpoint: string;
  metodo?: "GET";
  campos: FerramentaCampo[];
  autoLoad?: boolean;
  grupo?: string; // agrupa ferramentas visualmente por sub-área
}

export interface RamoConfig {
  slug: string;
  endpoint: string;
  areaCaso: string;
  titulo: string;
  subtitulo: string;
  icone: string;
  cor: string;
  campoTitulo: string;
  campoStatus: string;
  campos: CampoConfig[];
  ferramentas: FerramentaConfig[];
  subareas?: string[];
  ferramentasExternas?: LinkExterno[];
  externo?: boolean; // ramo sem router backend dedicado — usa o sistema geral de casos
  analiseDocumento?: boolean; // habilita o leitor/analisador de documento por área
  comparadorBacen?: boolean; // comparador de juros com a média BACEN
  guiaBancario?: boolean; // guia operacional de direito bancário (referência)
  analiseExtratos?: boolean; // análise de extrato bancário (cobranças abusivas)
  bancarioForense?: boolean; // forense bancário: verificador de abusividade + calculadora de CET
  guiaTransito?: boolean; // guia operacional de multas de trânsito (referência)
  guiaTrabalhista?: boolean; // guia operacional de direito do trabalho
  liquidacaoTrabalhista?: boolean; // liquidação de sentença trabalhista: verbas + FGTS/correção ADC 58/59 + honorários
  guiaTributario?: boolean; // guia operacional de direito tributário
  tributarioFiscal?: boolean; // recuperação de créditos fiscais: upload de XML NF-e + diagnóstico por tese
  guiaPrevidenciario?: boolean; // guia operacional de direito previdenciário
  guiaAmbiental?: boolean; // guia operacional de direito ambiental
  autosAmbientais?: boolean; // autos de infração ambiental com prazo automático (/environmental)
  ambientalEstrategia?: boolean; // simulador de estratégia do auto de infração (comparador econômico + peça de conversão)
  guiaCivil?: boolean; // guia operacional de direito civil
  guiaPenal?: boolean; // guia operacional de direito penal
  guiaConsumidor?: boolean; // guia operacional de direito do consumidor
  guiaImobiliario?: boolean; // guia operacional de direito imobiliário
  guiaFamilia?: boolean; // guia operacional de direito de família
  guiaAdministrativo?: boolean; // guia operacional de direito administrativo
  guiaLicitacoes?: boolean; // guia operacional de licitações e contratos
  guiaEmpresarial?: boolean; // guia operacional de direito empresarial (3 pilares)
  sociedadesCliente?: boolean; // sociedades do cliente: cap table + eventos societários (/empresarial/sociedades)
  guiaLgpd?: boolean; // guia operacional de adequação à LGPD (referência)
  lgpdRegistros?: boolean; // ROPA por cliente + gerador de RIPD (/lgpd/registros)
}

export interface LinkExterno {
  nome: string;
  url: string;
  descricao: string;
}

// ══════════════════════════════════════════════════════════════════════════
// 1. EMPRESARIAL
// ══════════════════════════════════════════════════════════════════════════
const empresarial: RamoConfig = {
  analiseDocumento: true,
  guiaEmpresarial: true,
  sociedadesCliente: true,
  slug: "empresarial",
  endpoint: "/empresarial",
  areaCaso: "empresarial",
  titulo: "Direito Empresarial",
  subtitulo:
    "Societário · Recuperação Judicial · M&A · CADE · Tributário · INPI",
  icone: "Building2",
  cor: "amber",
  campoTitulo: "tipo",
  campoStatus: "status",
  campos: [
    {
      nome: "tipo",
      label: "Tipo de matéria",
      tipo: "select",
      obrigatorio: true,
      col: 2,
      opcoes: [
        "societario",
        "recuperacao_judicial",
        "recuperacao_extrajudicial",
        "falencia",
        "contrato_empresarial",
        "due_diligence",
        "cade",
        "propriedade_intelectual",
        "trabalhista_empresarial",
        "tributario_empresarial",
        "administrativo_empresarial",
        "consumidor_empresarial",
        "ambiental_empresarial",
        "governanca",
        "outro",
      ],
    },
    {
      nome: "cnpj_empresa",
      label: "CNPJ da empresa",
      tipo: "text",
      placeholder: "00.000.000/0001-00",
    },
    {
      nome: "tipo_societario",
      label: "Tipo societário",
      tipo: "select",
      opcoes: ["LTDA", "SA", "EIRELI", "SLU", "MEI", "outro"],
    },
    { nome: "capital_social", label: "Capital social (R$)", tipo: "number" },
    {
      nome: "regime_tributario",
      label: "Regime tributário",
      tipo: "select",
      opcoes: ["Simples Nacional", "Lucro Presumido", "Lucro Real"],
    },
    {
      nome: "data_distribuicao_rj",
      label: "Distribuição RJ (se houver)",
      tipo: "date",
      ajuda: "Dispara o cálculo dos prazos de recuperação judicial",
    },
    {
      nome: "valor_passivo_total",
      label: "Passivo total (R$)",
      tipo: "number",
    },
    { nome: "observacoes", label: "Observações", tipo: "textarea", col: 2 },
  ],
  ferramentas: [
    {
      id: "prazos-rj",
      titulo: "Prazos de Recuperação Judicial",
      descricao: "Marcos críticos do processo a partir da distribuição.",
      baseLegal: "Lei 11.101/2005",
      endpoint: "/empresarial/ferramentas/prazos-rj",
      campos: [
        {
          nome: "data_distribuicao",
          label: "Data da distribuição",
          tipo: "date",
        },
      ],
    },
    {
      id: "verificar-cade",
      titulo: "Verificar Notificação CADE",
      descricao: "Obrigatoriedade de notificar ato de concentração.",
      baseLegal: "Lei 12.529/2011 art. 88",
      endpoint: "/empresarial/ferramentas/verificar-cade",
      campos: [
        {
          nome: "valor_faturamento_br",
          label: "Faturamento grupo no Brasil (R$)",
          tipo: "number",
        },
        {
          nome: "valor_operacao",
          label: "Valor da operação (R$)",
          tipo: "number",
        },
      ],
    },
    {
      id: "juros-mora",
      titulo: "Juros de Mora + Multa",
      descricao: "Atualização de débito contratual: juros simples + multa.",
      baseLegal: "CC arts. 395, 406 · CDC art. 52 §1",
      grupo: "Cálculos",
      endpoint: "/empresarial/ferramentas/juros-mora",
      campos: [
        {
          nome: "valor_principal",
          label: "Valor principal (R$)",
          tipo: "number",
        },
        { nome: "meses_atraso", label: "Meses em atraso", tipo: "number" },
        {
          nome: "taxa_juros_mensal_pct",
          label: "Juros ao mês (%)",
          tipo: "number",
          default: 1,
        },
        { nome: "multa_pct", label: "Multa (%)", tipo: "number", default: 2 },
      ],
    },
  ],
};

// ══════════════════════════════════════════════════════════════════════════
// 2. CÍVEL — Consumidor · Família · Imobiliário · Responsabilidade Civil
// ══════════════════════════════════════════════════════════════════════════
const civel: RamoConfig = {
  guiaCivil: true,
  slug: "civel",
  endpoint: "/civel",
  areaCaso: "civil",
  titulo: "Direito Cível",
  subtitulo:
    "Família · Imobiliário · Consumidor · Responsabilidade Civil · JEC",
  icone: "Scale",
  cor: "blue",
  campoTitulo: "tipo",
  campoStatus: "status",
  campos: [
    {
      nome: "tipo",
      label: "Tipo de ação",
      tipo: "select",
      obrigatorio: true,
      col: 2,
      opcoes: [
        "responsabilidade_civil",
        "familia_divorcio",
        "familia_alimentos",
        "familia_guarda",
        "familia_inventario",
        "familia_uniao_estavel",
        "familia_adocao",
        "imobiliario_compra_venda",
        "imobiliario_locacao",
        "imobiliario_usucapiao",
        "imobiliario_vizinhanca",
        "imobiliario_condominio",
        "consumidor",
        "jec",
        "cobranca",
        "indenizacao_acidente",
        "outro_civel",
      ],
    },
    { nome: "valor_causa", label: "Valor da causa (R$)", tipo: "number" },
    {
      nome: "competencia",
      label: "Competência",
      tipo: "text",
      placeholder: "ex: 2ª Vara Cível de Betim",
    },
    {
      nome: "polo_ativo",
      label: "Polo do cliente",
      tipo: "select",
      opcoes: ["autor", "reu"],
    },
    {
      nome: "data_citacao",
      label: "Data da citação",
      tipo: "date",
      ajuda: "Calcula automaticamente o prazo de contestação",
    },
    {
      nome: "tutela_urgencia",
      label: "Há pedido de tutela de urgência?",
      tipo: "checkbox",
    },
    { nome: "observacoes", label: "Observações", tipo: "textarea", col: 2 },
  ],
  ferramentas: [
    // ── PRAZOS ──────────────────────────────────────────────────────────
    {
      id: "prazos-contestacao",
      titulo: "Prazo de Contestação",
      descricao: "Prazo por rito processual (CPC / JEC / Fazenda Pública).",
      baseLegal: "CPC art. 335 · Lei 9.099 art. 30",
      grupo: "Prazos",
      endpoint: "/civel/ferramentas/prazos-contestacao",
      campos: [
        { nome: "data_citacao", label: "Data da citação", tipo: "date" },
        {
          nome: "tipo",
          label: "Rito",
          tipo: "select",
          opcoes: ["cpc", "jec", "fazenda_publica"],
          default: "cpc",
        },
      ],
    },
    // ── CONSUMIDOR ───────────────────────────────────────────────────────
    {
      id: "prescricao-consumidor",
      titulo: "Prescrição / Decadência CDC",
      descricao:
        "Vícios (30/90 dias), fato do produto/serviço (5 anos), cobrança indevida (3 anos).",
      baseLegal: "CDC arts. 26-27",
      grupo: "Consumidor",
      endpoint: "/civel/ferramentas/prescricao-consumidor",
      campos: [
        {
          nome: "tipo_vicio",
          label: "Tipo de pretensão",
          tipo: "select",
          opcoes: [
            "fato_produto",
            "fato_servico",
            "servico_ou_produto",
            "cobranca_indevida",
          ],
          default: "fato_produto",
        },
        { nome: "data_fato", label: "Data do fato / entrega", tipo: "date" },
      ],
    },
    {
      id: "dano-moral",
      titulo: "Parâmetros de Dano Moral",
      descricao:
        "Faixas STJ por tipo de caso — negativação, extravio, produto defeituoso etc.",
      baseLegal: "CC art. 944 + STJ",
      grupo: "Consumidor",
      endpoint: "/civel/ferramentas/calculo-dano-moral",
      campos: [
        {
          nome: "tipo_caso",
          label: "Tipo de caso",
          tipo: "select",
          opcoes: [
            "negativacao_indevida",
            "extravio_bagagem",
            "produto_defeituoso",
            "acidente_consumo",
            "cobranca_abusiva",
            "outro",
          ],
          default: "negativacao_indevida",
        },
        {
          nome: "salarios_minimos_pedido",
          label: "Quantum pedido (SMs)",
          tipo: "number",
          default: 10,
        },
      ],
    },
    // ── FAMÍLIA ──────────────────────────────────────────────────────────
    {
      id: "alimentos",
      titulo: "Alimentos Proporcionais",
      descricao:
        "Estimativa de pensão alimentícia pelo binômio necessidade/possibilidade.",
      baseLegal: "CC art. 1.694 §1º",
      grupo: "Família",
      endpoint: "/civel/ferramentas/alimentos-calcular",
      campos: [
        {
          nome: "salario_devedor",
          label: "Salário do devedor (R$)",
          tipo: "number",
        },
        {
          nome: "percentual",
          label: "Percentual (%)",
          tipo: "number",
          default: 30,
        },
        { nome: "filhos", label: "Nº de filhos", tipo: "number", default: 1 },
      ],
    },
    {
      id: "partilha-divorcio",
      titulo: "Partilha no Divórcio",
      descricao:
        "O que se partilha em cada regime de bens — Súm. STJ 377 incluída.",
      baseLegal: "CC arts. 1.658-1.688",
      grupo: "Família",
      endpoint: "/civel/ferramentas/partilha-divorcio",
      campos: [
        {
          nome: "regime_bens",
          label: "Regime de bens",
          tipo: "select",
          opcoes: [
            "comunhao_parcial",
            "comunhao_universal",
            "separacao_obrigatoria",
            "separacao_voluntaria",
            "participacao_final_aquestos",
          ],
          default: "comunhao_parcial",
        },
        { nome: "data_casamento", label: "Data do casamento", tipo: "date" },
        {
          nome: "data_separacao_fatos",
          label: "Separação de fato (se houver)",
          tipo: "date",
        },
      ],
    },
    // ── IMOBILIÁRIO ──────────────────────────────────────────────────────
    {
      id: "usucapiao",
      titulo: "Usucapião — Verificar Requisitos",
      descricao: "Modalidade e prazo de posse mínimo.",
      baseLegal: "CC arts. 1.238-1.244 + CF art. 183",
      grupo: "Imobiliário",
      endpoint: "/civel/ferramentas/usucapiao-verificar",
      campos: [
        {
          nome: "tipo",
          label: "Modalidade",
          tipo: "select",
          opcoes: [
            "ordinaria",
            "extraordinaria",
            "especial_urbana",
            "especial_rural",
            "familiar",
          ],
        },
        { nome: "anos_posse", label: "Anos de posse", tipo: "number" },
      ],
    },
    {
      id: "rescisao-locacao",
      titulo: "Rescisão de Locação",
      descricao: "Multa, aviso prévio e direitos de locador/locatário.",
      baseLegal: "Lei 8.245/91 (Lei do Inquilinato)",
      grupo: "Imobiliário",
      endpoint: "/civel/ferramentas/rescisao-locacao",
      campos: [
        { nome: "data_inicio", label: "Início do contrato", tipo: "date" },
        {
          nome: "data_rescisao_pretendida",
          label: "Rescisão pretendida",
          tipo: "date",
        },
        {
          nome: "valor_aluguel",
          label: "Valor do aluguel (R$)",
          tipo: "number",
        },
        {
          nome: "tipo_locacao",
          label: "Tipo",
          tipo: "select",
          opcoes: ["residencial", "comercial", "temporada"],
          default: "residencial",
        },
        {
          nome: "quem_rescinde",
          label: "Quem rescinde",
          tipo: "select",
          opcoes: ["locatario", "locador"],
          default: "locatario",
        },
      ],
    },
  ],
};

// ══════════════════════════════════════════════════════════════════════════
// 3. PENAL
// ══════════════════════════════════════════════════════════════════════════
const penal: RamoConfig = {
  guiaPenal: true,
  slug: "penal",
  endpoint: "/penal",
  areaCaso: "criminal",
  titulo: "Direito Penal",
  subtitulo:
    "Defesa criminal · HC · ANPP · Execução penal · Lei Maria da Penha",
  icone: "Lock",
  cor: "red",
  campoTitulo: "tipo_crime",
  campoStatus: "fase",
  campos: [
    {
      nome: "tipo_crime",
      label: "Crime imputado",
      tipo: "select",
      obrigatorio: true,
      col: 2,
      opcoes: [
        "estelionato",
        "furto",
        "roubo",
        "lesao_corporal",
        "homicidio",
        "trafico_drogas",
        "crime_transito",
        "crime_ambiental",
        "violencia_domestica",
        "corrupcao",
        "sonegacao_fiscal",
        "crimes_informaticos",
        "injuria_difamacao",
        "ameaca",
        "outro_penal",
      ],
    },
    {
      nome: "fase",
      label: "Fase processual",
      tipo: "select",
      opcoes: [
        "investigacao",
        "denuncia_pendente",
        "resposta_acusacao",
        "instrucao",
        "alegacoes_finais",
        "julgamento",
        "recursal_rese",
        "recursal_apelacao",
        "execucao_penal",
        "habeas_corpus",
        "anpp",
        "encerrado",
      ],
    },
    { nome: "numero_ip", label: "Nº do inquérito/processo", tipo: "text" },
    { nome: "data_fato", label: "Data do fato", tipo: "date" },
    { nome: "preso", label: "Cliente está preso?", tipo: "checkbox" },
    {
      nome: "artigo_imputado",
      label: "Artigo imputado",
      tipo: "text",
      placeholder: "ex: CP art. 157 §2º I",
    },
    {
      nome: "data_denuncia",
      label: "Data da denúncia",
      tipo: "date",
      ajuda:
        "Calcula o prazo de resposta à acusação (CPP art. 396-A — 10 dias)",
    },
    { nome: "observacoes", label: "Observações", tipo: "textarea", col: 2 },
  ],
  ferramentas: [
    {
      id: "prazos",
      titulo: "Prazos Processuais Penais",
      descricao: "Resposta à acusação, ED, RESE e apelação.",
      baseLegal: "CPP arts. 396-A, 586, 593",
      endpoint: "/penal/ferramentas/prazos-processuais",
      campos: [
        { nome: "data_denuncia", label: "Data da denúncia", tipo: "date" },
      ],
    },
    {
      id: "anpp",
      titulo: "Verificar ANPP",
      descricao: "Acordo de Não Persecução Penal — elegibilidade e condições.",
      baseLegal: "CPP art. 28-A (Lei 13.964/2019)",
      endpoint: "/penal/ferramentas/verificar-anpp",
      campos: [
        {
          nome: "pena_min_anos",
          label: "Pena mínima do tipo (anos)",
          tipo: "number",
        },
        {
          nome: "confessou",
          label: "Confessou?",
          tipo: "select",
          opcoes: ["true", "false"],
        },
        {
          nome: "nao_violento",
          label: "Sem violência?",
          tipo: "select",
          opcoes: ["true", "false"],
        },
        {
          nome: "primario",
          label: "Primário?",
          tipo: "select",
          opcoes: ["true", "false"],
        },
      ],
    },
    {
      id: "prescricao",
      titulo: "Prescrição Punitiva",
      descricao: "Prescrição em abstrato pela pena máxima (CP art. 109).",
      baseLegal: "CP art. 109",
      endpoint: "/penal/ferramentas/prescricao-punitiva",
      campos: [
        {
          nome: "pena_maxima_anos",
          label: "Pena máxima do tipo (anos)",
          tipo: "number",
        },
        { nome: "data_fato", label: "Data do fato", tipo: "date" },
      ],
    },
    {
      id: "prescricao-penal",
      titulo: "Prescrição Penal (pena em abstrato)",
      descricao: "Prazo prescricional da pretensão punitiva pela pena máxima.",
      baseLegal: "CP art. 109",
      grupo: "Prazos",
      endpoint: "/penal/ferramentas/prescricao-penal",
      campos: [
        {
          nome: "pena_maxima_anos",
          label: "Pena máxima cominada (anos)",
          tipo: "number",
        },
      ],
    },
    {
      id: "dosimetria",
      titulo: "Dosimetria da Pena (trifásico)",
      descricao: "Cálculo das 3 fases: base, agravantes/atenuantes, causas.",
      baseLegal: "CP arts. 59, 68 · Súmula 231 STJ",
      grupo: "Cálculos",
      endpoint: "/penal/ferramentas/dosimetria",
      campos: [
        { nome: "pena_base_anos", label: "Pena-base (anos)", tipo: "number" },
        {
          nome: "fracao_agravantes_pct",
          label: "Agravantes líq. (%)",
          tipo: "number",
          default: 0,
        },
        {
          nome: "fracao_aumento_pct",
          label: "Causas de aumento (%)",
          tipo: "number",
          default: 0,
        },
        {
          nome: "fracao_diminuicao_pct",
          label: "Causas de diminuição (%)",
          tipo: "number",
          default: 0,
        },
      ],
    },
  ],
};

// ══════════════════════════════════════════════════════════════════════════
// 4. TRABALHISTA
// ══════════════════════════════════════════════════════════════════════════
const trabalhista: RamoConfig = {
  analiseDocumento: true,
  guiaTrabalhista: true,
  liquidacaoTrabalhista: true,
  slug: "trabalhista",
  endpoint: "/trabalhista-esp",
  areaCaso: "trabalhista",
  titulo: "Direito Trabalhista",
  subtitulo:
    "Verbas · Horas extras · Insalubridade · Acidente · Equiparação salarial",
  icone: "HardHat",
  cor: "green",
  campoTitulo: "tipo",
  campoStatus: "fase",
  campos: [
    {
      nome: "tipo",
      label: "Tipo de pedido",
      tipo: "select",
      obrigatorio: true,
      col: 2,
      opcoes: [
        "verbas_rescisorias",
        "reconhecimento_vinculo",
        "horas_extras",
        "insalubridade",
        "periculosidade",
        "dano_moral_trabalhista",
        "assedio_moral",
        "assedio_sexual",
        "acidente_trabalho",
        "estabilidade_gestante",
        "rescisao_indireta",
        "equiparacao_salarial",
        "adicional_noturno",
        "intervalo_intrajornada",
        "plr_participacao",
        "nulidade_demissao",
        "outro_trabalhista",
      ],
    },
    {
      nome: "polo",
      label: "Polo do cliente",
      tipo: "select",
      opcoes: ["reclamante", "reclamado"],
    },
    { nome: "salario_base", label: "Salário base (R$)", tipo: "number" },
    { nome: "data_admissao", label: "Data de admissão", tipo: "date" },
    { nome: "data_demissao", label: "Data de demissão", tipo: "date" },
    {
      nome: "tipo_rescisao",
      label: "Tipo de rescisão",
      tipo: "select",
      opcoes: [
        "sem_justa_causa",
        "pedido_demissao",
        "justa_causa",
        "acordo_484a",
        "rescisao_indireta",
      ],
    },
    { nome: "cargo", label: "Cargo", tipo: "text" },
    {
      nome: "valor_causa_estimado",
      label: "Valor estimado da causa (R$)",
      tipo: "number",
    },
    { nome: "observacoes", label: "Observações", tipo: "textarea", col: 2 },
  ],
  ferramentas: [
    {
      id: "verbas-rescisorias",
      titulo: "Verbas Rescisórias Completas",
      descricao:
        "Saldo, aviso prévio proporcional (Lei 12.506/11), 13°, férias+1/3, FGTS e multa.",
      baseLegal: "CLT arts. 477-500 + Lei 12.506/11 + Lei 8.036/90",
      endpoint: "/trabalhista-esp/ferramentas/verbas-rescisorias",
      campos: [
        { nome: "salario", label: "Salário bruto (R$)", tipo: "number" },
        { nome: "data_admissao", label: "Data de admissão", tipo: "date" },
        { nome: "data_demissao", label: "Data de demissão", tipo: "date" },
        {
          nome: "tipo_rescisao",
          label: "Tipo de rescisão",
          tipo: "select",
          opcoes: [
            "sem_justa_causa",
            "pedido_demissao",
            "justa_causa",
            "acordo_484a",
            "rescisao_indireta",
          ],
          default: "sem_justa_causa",
        },
        {
          nome: "saldo_fgts",
          label: "Saldo FGTS acumulado (R$)",
          tipo: "number",
          default: 0,
        },
        {
          nome: "aviso_previo",
          label: "Aviso prévio",
          tipo: "select",
          opcoes: ["indenizado", "trabalhado", "dispensado"],
          default: "indenizado",
        },
      ],
    },
    {
      id: "prazos",
      titulo: "Prazos Trabalhistas",
      descricao: "RO, depósito recursal e embargos a partir da sentença.",
      baseLegal: "CLT art. 895",
      endpoint: "/trabalhista-esp/ferramentas/prazos",
      campos: [
        { nome: "data_sentenca", label: "Data da sentença", tipo: "date" },
      ],
    },
    {
      id: "deposito",
      titulo: "Depósito Recursal 2026",
      descricao: "Valor do depósito para RO e RR (teto TST).",
      baseLegal: "CLT art. 899 + Ato TST GP",
      endpoint: "/trabalhista-esp/ferramentas/deposito-recursal",
      campos: [
        {
          nome: "valor_condenacao",
          label: "Valor da condenação (R$)",
          tipo: "number",
        },
      ],
    },
    {
      id: "prescricao",
      titulo: "Prescrição Trabalhista",
      descricao: "Bienal (término do contrato) e quinquenal (crédito).",
      baseLegal: "CLT art. 11 + CF art. 7º XXIX",
      endpoint: "/trabalhista-esp/ferramentas/prescricao-trabalhista",
      campos: [
        { nome: "data_demissao", label: "Data da demissão", tipo: "date" },
        { nome: "data_fato", label: "Data do fato gerador", tipo: "date" },
      ],
    },
    {
      id: "horas-extras",
      titulo: "Horas Extras + Reflexos",
      descricao: "Valor de HE (jornada 220h) com DSR, 13º, férias e FGTS.",
      baseLegal: "CF art. 7 XVI · CLT art. 59 · Súmula 264 TST",
      grupo: "Cálculos",
      endpoint: "/trabalhista/ferramentas/horas-extras",
      campos: [
        {
          nome: "salario_mensal",
          label: "Salário mensal (R$)",
          tipo: "number",
        },
        {
          nome: "horas_extras_mes",
          label: "Horas extras no mês",
          tipo: "number",
        },
        {
          nome: "adicional_percentual",
          label: "Adicional (%)",
          tipo: "number",
          default: 50,
        },
      ],
    },
  ],
};

// ══════════════════════════════════════════════════════════════════════════
// 5. ADMINISTRATIVO — Licitações · Multas · Prefeituras · MS · PAD
// ══════════════════════════════════════════════════════════════════════════
const administrativo: RamoConfig = {
  guiaAdministrativo: true,
  guiaLicitacoes: true,
  slug: "administrativo",
  endpoint: "/admin-esp",
  areaCaso: "tributario",
  titulo: "Direito Administrativo",
  subtitulo:
    "Licitações · Contratos Públicos · Recursos de Multas · MS · Prefeituras · Improbidade",
  icone: "Landmark",
  cor: "slate",
  campoTitulo: "tipo",
  campoStatus: "status",
  campos: [
    {
      nome: "tipo",
      label: "Tipo",
      tipo: "select",
      obrigatorio: true,
      col: 2,
      opcoes: [
        "recurso_multa_transito",
        "recurso_multa_ambiental",
        "recurso_multa_tributaria",
        "recurso_multa_sanitaria",
        "recurso_autuacao_mte",
        "improbidade_administrativa",
        "mandado_seguranca_admin",
        "servidor_publico",
        "licitacao_recurso",
        "desapropriacao",
        "indenizacao_estado",
        "licenca_negada_admin",
        "contrato_administrativo",
        "outro_admin",
      ],
    },
    {
      nome: "orgao_autuador",
      label: "Órgão / Entidade",
      tipo: "text",
      placeholder: "DETRAN/IBAMA/Prefeitura/TCU",
    },
    {
      nome: "numero_auto_infracao",
      label: "Nº do auto / processo",
      tipo: "text",
    },
    {
      nome: "data_notificacao",
      label: "Data da notificação",
      tipo: "date",
      ajuda: "Calcula o prazo recursal automaticamente conforme o tipo",
    },
    {
      nome: "valor_multa_original",
      label: "Valor da multa / contrato (R$)",
      tipo: "number",
    },
    {
      nome: "data_ato_coator",
      label: "Data do ato coator (MS)",
      tipo: "date",
      ajuda: "Para MS: calcula o prazo decadencial de 120 dias",
    },
    { nome: "observacoes", label: "Observações", tipo: "textarea", col: 2 },
  ],
  ferramentas: [
    // ── LICITAÇÕES ────────────────────────────────────────────────────────
    {
      id: "prazo-recurso-licitacao",
      titulo: "Prazo de Recurso em Licitação",
      descricao:
        "Pregão (3 dias), concorrência (3 dias), tomada de preços (5 dias).",
      baseLegal: "Lei 14.133/2021 art. 165 · Lei 10.520/02",
      grupo: "Licitações",
      endpoint: "/admin-esp/ferramentas/prazo-recurso-licitacao",
      campos: [
        {
          nome: "data_publicacao_resultado",
          label: "Data do resultado / julgamento",
          tipo: "date",
        },
        {
          nome: "modalidade",
          label: "Modalidade",
          tipo: "select",
          opcoes: [
            "pregao",
            "concorrencia",
            "tomada_precos",
            "convite",
            "credenciamento",
          ],
          default: "pregao",
        },
      ],
    },
    {
      id: "habilitacao-licitacao",
      titulo: "Checklist de Habilitação",
      descricao: "Documentação mínima para habilitar em licitação pública.",
      baseLegal: "Lei 14.133/2021 arts. 62-70 · LC 123/06",
      grupo: "Licitações",
      endpoint: "/admin-esp/ferramentas/habilitacao-licitacao",
      campos: [
        {
          nome: "tem_certidao_federal",
          label: "CND Federal (Receita+PGFN)?",
          tipo: "select",
          opcoes: ["true", "false"],
          default: "true",
        },
        {
          nome: "tem_certidao_estadual",
          label: "CND Estadual?",
          tipo: "select",
          opcoes: ["true", "false"],
          default: "true",
        },
        {
          nome: "tem_certidao_municipal",
          label: "CND Municipal?",
          tipo: "select",
          opcoes: ["true", "false"],
          default: "true",
        },
        {
          nome: "tem_fgts",
          label: "Certidão FGTS (CEF)?",
          tipo: "select",
          opcoes: ["true", "false"],
          default: "true",
        },
        {
          nome: "tem_trabalhista",
          label: "CNDT (TST)?",
          tipo: "select",
          opcoes: ["true", "false"],
          default: "true",
        },
        {
          nome: "tem_qualificacao_tecnica",
          label: "Qualif. técnica (atestados)?",
          tipo: "select",
          opcoes: ["true", "false"],
          default: "true",
        },
        {
          nome: "tem_qualificacao_economica",
          label: "Qualif. econômica (balanço)?",
          tipo: "select",
          opcoes: ["true", "false"],
          default: "true",
        },
      ],
    },
    {
      id: "reajuste-contrato-admin",
      titulo: "Reajuste de Contrato com Prefeitura",
      descricao:
        "Cálculo do reajuste após 12 meses por índice contratual (IPCA/INCC/IGP-M).",
      baseLegal: "Lei 14.133/2021 art. 92 §§2º-3º",
      grupo: "Licitações",
      endpoint: "/admin-esp/ferramentas/reajuste-contrato-administrativo",
      campos: [
        {
          nome: "valor_original",
          label: "Valor original do contrato (R$)",
          tipo: "number",
        },
        {
          nome: "indice_acumulado_pct",
          label: "IPCA/IGP-M/INCC acumulado (%)",
          tipo: "number",
        },
        { nome: "meses_contrato", label: "Meses de contrato", tipo: "number" },
      ],
    },
    // ── MULTAS / MS ───────────────────────────────────────────────────────
    {
      id: "multa-transito",
      titulo: "Recurso Multa de Trânsito",
      descricao: "Prazos JARI/CETRAN e 20% de desconto pagamento imediato.",
      baseLegal: "CTB arts. 281-284",
      grupo: "Recursos de Multas",
      endpoint: "/admin-esp/ferramentas/recurso-multa-transito",
      campos: [
        {
          nome: "data_notificacao",
          label: "Data da notificação",
          tipo: "date",
        },
        { nome: "valor_multa", label: "Valor da multa (R$)", tipo: "number" },
        {
          nome: "pontos_cnh",
          label: "Pontos na CNH",
          tipo: "number",
          default: 0,
        },
      ],
    },
    {
      id: "ms",
      titulo: "Mandado de Segurança",
      descricao:
        "Prazo decadencial de 120 dias e pressupostos constitucionais.",
      baseLegal: "Lei 12.016/2009 art. 23 · CF art. 5º LXIX",
      grupo: "Outros",
      endpoint: "/admin-esp/ferramentas/mandado-seguranca",
      campos: [
        { nome: "data_ato_coator", label: "Data do ato coator", tipo: "date" },
      ],
    },
  ],
};

// ══════════════════════════════════════════════════════════════════════════
// 6. BANCÁRIO
// ══════════════════════════════════════════════════════════════════════════
const bancario: RamoConfig = {
  comparadorBacen: true,
  analiseDocumento: true,
  guiaBancario: true,
  analiseExtratos: true,
  bancarioForense: true,
  slug: "bancario",
  endpoint: "/bancario",
  areaCaso: "civil",
  titulo: "Direito Bancário e Financeiro",
  subtitulo:
    "Revisão de juros · Negativação · Superendividamento · Busca e apreensão · Pix",
  icone: "Banknote",
  cor: "yellow",
  campoTitulo: "tipo",
  campoStatus: "status",
  campos: [
    {
      nome: "tipo",
      label: "Tipo",
      tipo: "select",
      obrigatorio: true,
      col: 2,
      opcoes: [
        "revisao_contrato_juros",
        "negativacao_indevida",
        "cobranca_abusiva",
        "superendividamento",
        "consignado_indevido",
        "fraude_bancaria",
        "busca_apreensao",
        "execucao_bancaria",
        "fraude_cartao_credito",
        "pix_golpe",
        "limite_conta_fatura",
        "leasing_alienacao_fiduciaria",
        "hipoteca_garantia_real",
        "outro_bancario",
      ],
    },
    {
      nome: "instituicao_financeira",
      label: "Instituição financeira",
      tipo: "text",
    },
    { nome: "numero_contrato", label: "Nº do contrato", tipo: "text" },
    {
      nome: "modalidade_credito",
      label: "Modalidade",
      tipo: "text",
      placeholder: "pessoal/consignado/CDC/leasing",
    },
    {
      nome: "valor_contratado",
      label: "Valor contratado (R$)",
      tipo: "number",
    },
    {
      nome: "taxa_mensal_contratada",
      label: "Taxa mensal contratada (%)",
      tipo: "number",
    },
    { nome: "negativado", label: "Cliente negativado?", tipo: "checkbox" },
    {
      nome: "data_notificacao_ba",
      label: "Notificação busca e apreensão",
      tipo: "date",
      ajuda: "Calcula o prazo de purga da mora (5 dias — Dec.-Lei 911/69)",
    },
    { nome: "observacoes", label: "Observações", tipo: "textarea", col: 2 },
  ],
  ferramentas: [
    {
      id: "taxas-bacen",
      titulo: "Taxas BACEN ao Vivo",
      descricao:
        "SELIC, CDI, TR e IPCA-15 diretamente do Banco Central do Brasil.",
      baseLegal: "BCB SGS — api.bcb.gov.br (dados oficiais)",
      endpoint: "/bancario/ferramentas/taxas-bacen",
      campos: [],
      autoLoad: true,
    },
    {
      id: "analise-juros",
      titulo: "Análise de Juros e Spread",
      descricao:
        "Spread contratado vs. referência BCB — indício de abusividade.",
      baseLegal: "Súm. STJ 530 · REsp 1.061.530",
      endpoint: "/bancario/ferramentas/analise-juros",
      campos: [
        {
          nome: "taxa_mensal_contratada",
          label: "Taxa mensal contratada (%)",
          tipo: "number",
        },
        {
          nome: "taxa_mensal_referencia",
          label: "Taxa referência BCB (% a.m.)",
          tipo: "number",
        },
        {
          nome: "valor_contratado",
          label: "Valor contratado (R$)",
          tipo: "number",
        },
      ],
    },
    {
      id: "superendividamento",
      titulo: "Superendividamento",
      descricao: "Comprometimento da renda e direitos da Lei 14.181/2021.",
      baseLegal: "Lei 14.181/2021 (CDC art. 54-A)",
      endpoint: "/bancario/ferramentas/superendividamento",
      campos: [
        { nome: "renda_mensal", label: "Renda mensal (R$)", tipo: "number" },
        {
          nome: "total_parcelas_mes",
          label: "Total de parcelas/mês (R$)",
          tipo: "number",
        },
      ],
    },
    {
      id: "busca-apreensao",
      titulo: "Busca e Apreensão",
      descricao:
        "Prazo de purga da mora e estratégias de defesa (adimplemento substancial).",
      baseLegal: "Dec.-Lei 911/69 art. 3º · STJ REsp 1.622.555",
      endpoint: "/bancario/ferramentas/busca-apreensao",
      campos: [
        {
          nome: "data_notificacao",
          label: "Data da notificação",
          tipo: "date",
        },
        { nome: "valor_divida", label: "Valor da dívida (R$)", tipo: "number" },
        { nome: "bem_descricao", label: "Bem em garantia", tipo: "text" },
      ],
    },
    {
      id: "juros-abusivos",
      titulo: "Juros Abusivos (revisional)",
      descricao: "Compara a taxa contratada com a média de mercado (BACEN).",
      baseLegal: "STJ REsp 1.061.530 · Súmula 530 STJ",
      grupo: "Revisional",
      endpoint: "/bancario/ferramentas/juros-abusivos",
      campos: [
        {
          nome: "taxa_contratada_mensal_pct",
          label: "Taxa contratada (% a.m.)",
          tipo: "number",
        },
        {
          nome: "taxa_media_bacen_mensal_pct",
          label: "Taxa média BACEN (% a.m.)",
          tipo: "number",
        },
      ],
    },
  ],
};

// ══════════════════════════════════════════════════════════════════════════
// 7. TRIBUTÁRIO
// ══════════════════════════════════════════════════════════════════════════
const tributario: RamoConfig = {
  analiseDocumento: true,
  guiaTributario: true,
  tributarioFiscal: true,
  slug: "tributario",
  endpoint: "/admin-esp", // reusa AdminCase com tipos tributários
  areaCaso: "tributario",
  titulo: "Direito Tributário",
  subtitulo:
    "Planejamento fiscal · Auto de infração · Prescrição · Simples Nacional · Parcelamento",
  icone: "Receipt",
  cor: "indigo",
  campoTitulo: "tipo",
  campoStatus: "status",
  campos: [
    {
      nome: "tipo",
      label: "Tipo de matéria",
      tipo: "select",
      obrigatorio: true,
      col: 2,
      opcoes: [
        "recurso_multa_tributaria",
        "recurso_multa_sanitaria",
        "recurso_autuacao_mte",
        "mandado_seguranca_admin",
        "outro_admin",
      ],
    },
    {
      nome: "orgao_autuador",
      label: "Autoridade fiscal / órgão",
      tipo: "text",
      placeholder: "RFB / SEFAZ / Prefeitura / PGFN",
    },
    {
      nome: "numero_auto_infracao",
      label: "Nº do auto / processo",
      tipo: "text",
    },
    {
      nome: "data_notificacao",
      label: "Data da ciência / notificação",
      tipo: "date",
      ajuda: "Dispara contagem do prazo de impugnação (30 dias)",
    },
    {
      nome: "valor_multa_original",
      label: "Valor total do débito (R$)",
      tipo: "number",
    },
    { nome: "observacoes", label: "Observações", tipo: "textarea", col: 2 },
  ],
  ferramentas: [
    {
      id: "auto-infracao-prazos",
      titulo: "Auto de Infração — Prazos e Estratégias",
      descricao:
        "Prazo de impugnação (30 dias), recursos, reduções de multa por pagamento/parcelamento.",
      baseLegal: "Decreto 70.235/72 (PAF) · CTN art. 151 III",
      grupo: "Contencioso",
      endpoint: "/tributario/ferramentas/auto-infracao-prazos",
      campos: [
        {
          nome: "data_ciencia",
          label: "Data da ciência / entrega",
          tipo: "date",
        },
        {
          nome: "valor_multa",
          label: "Valor total do débito (R$)",
          tipo: "number",
        },
        {
          nome: "esfera",
          label: "Esfera",
          tipo: "select",
          opcoes: ["federal", "estadual", "municipal"],
          default: "federal",
        },
      ],
    },
    {
      id: "prescricao-decadencia",
      titulo: "Prescrição e Decadência Tributária",
      descricao:
        "Decadência do direito de lançar (CTN 150/173) e prescrição do crédito constituído (CTN 174).",
      baseLegal: "CTN arts. 150 §4º, 173 I, 174",
      grupo: "Contencioso",
      endpoint: "/tributario/ferramentas/prescricao-decadencia",
      campos: [
        {
          nome: "tipo",
          label: "Tipo de extinção",
          tipo: "select",
          opcoes: ["lancamento", "homologacao", "credito_nao_constituido"],
          default: "homologacao",
        },
        {
          nome: "data_fato_gerador",
          label: "Data do fato gerador / pagamento",
          tipo: "date",
        },
      ],
    },
    {
      id: "parcelamento",
      titulo: "Simulação de Parcelamento",
      descricao:
        "Estimativa de parcela e descontos por modalidade (PERT, parcelamento comum, Simples).",
      baseLegal: "Lei 13.496/17 (PERT) · LC 123/06 · CTN art. 155-A",
      grupo: "Contencioso",
      endpoint: "/tributario/ferramentas/parcelamento",
      campos: [
        {
          nome: "valor_total_debito",
          label: "Total do débito (R$)",
          tipo: "number",
        },
        {
          nome: "parcelas",
          label: "Nº de parcelas",
          tipo: "number",
          default: 60,
        },
        {
          nome: "modalidade",
          label: "Modalidade",
          tipo: "select",
          opcoes: ["pert", "refis", "simples", "parcelamento_comum"],
          default: "pert",
        },
      ],
    },
    {
      id: "simples-nacional",
      titulo: "Alíquota Efetiva Simples Nacional",
      descricao: "Faixa, alíquota nominal e efetiva por RBT12 e anexo (I-V).",
      baseLegal: "LC 123/2006 · Res. CGSN 140/2018",
      grupo: "Planejamento Fiscal",
      endpoint: "/tributario/ferramentas/simples-nacional",
      campos: [
        {
          nome: "receita_bruta_12m",
          label: "Receita bruta 12 meses — RBT12 (R$)",
          tipo: "number",
        },
        {
          nome: "anexo",
          label: "Anexo",
          tipo: "select",
          opcoes: ["I", "II", "III", "IV", "V"],
          default: "III",
        },
      ],
    },
    {
      id: "regime-tributario",
      titulo: "Comparativo de Regimes Tributários",
      descricao:
        "Carga estimada Simples Nacional × Lucro Presumido × Lucro Real.",
      baseLegal: "LC 123/06 · RIR/2018 · Lei 9.430/96",
      grupo: "Planejamento Fiscal",
      endpoint: "/tributario/ferramentas/regime-tributario",
      campos: [
        {
          nome: "receita_bruta_anual",
          label: "Receita bruta anual (R$)",
          tipo: "number",
        },
        {
          nome: "lucro_estimado_pct",
          label: "Margem de lucro estimada (%)",
          tipo: "number",
          default: 20,
        },
        {
          nome: "atividade",
          label: "Atividade",
          tipo: "select",
          opcoes: ["comercio", "industria", "servicos"],
          default: "servicos",
        },
      ],
    },
    {
      id: "reforma-tributaria",
      titulo: "Reforma Tributária — Impacto por Regime",
      descricao:
        "EC 132/2023 + LC 214/2025: IBS, CBS, IS — cronograma 2026-2033 e impacto por regime e atividade.",
      baseLegal: "EC 132/2023 · LC 214/2025",
      grupo: "Planejamento Fiscal",
      endpoint: "/tributario/ferramentas/reforma-tributaria",
      campos: [
        {
          nome: "receita_bruta_anual",
          label: "Receita bruta anual (R$)",
          tipo: "number",
        },
        {
          nome: "regime_atual",
          label: "Regime atual",
          tipo: "select",
          opcoes: ["simples", "lucro_presumido", "lucro_real"],
          default: "simples",
        },
        {
          nome: "atividade",
          label: "Atividade",
          tipo: "select",
          opcoes: [
            "comercio",
            "industria",
            "servicos",
            "financeiro",
            "imobiliario",
          ],
          default: "servicos",
        },
        {
          nome: "ano_analise",
          label: "Ano de análise",
          tipo: "select",
          opcoes: ["2026", "2027", "2029", "2030", "2031", "2032", "2033"],
          default: "2026",
        },
      ],
    },
    {
      id: "multa-mora",
      titulo: "Multa de Mora (tributo federal)",
      descricao: "0,33%/dia limitada a 20% (+ Selic, não incluída).",
      baseLegal: "Lei 9.430/96 art. 61",
      grupo: "Cálculos",
      endpoint: "/tributario/ferramentas/multa-mora",
      campos: [
        {
          nome: "valor_tributo",
          label: "Valor do tributo (R$)",
          tipo: "number",
        },
        { nome: "dias_atraso", label: "Dias de atraso", tipo: "number" },
      ],
    },
  ],
};

// ══════════════════════════════════════════════════════════════════════════
// 8. AMBIENTAL
// ══════════════════════════════════════════════════════════════════════════
const ambiental: RamoConfig = {
  analiseDocumento: true,
  guiaAmbiental: true,
  autosAmbientais: true,
  ambientalEstrategia: true,
  slug: "ambiental",
  endpoint: "/admin-esp",
  areaCaso: "ambiental",
  titulo: "Direito Ambiental",
  subtitulo:
    "Licenciamento · Auto de infração · Reserva Legal · TAC · Crimes ambientais",
  icone: "Leaf",
  cor: "green",
  campoTitulo: "tipo",
  campoStatus: "status",
  campos: [
    {
      nome: "tipo",
      label: "Tipo de matéria",
      tipo: "select",
      obrigatorio: true,
      col: 2,
      opcoes: [
        "recurso_multa_ambiental",
        "mandado_seguranca_admin",
        "outro_admin",
      ],
    },
    {
      nome: "orgao_autuador",
      label: "Órgão ambiental",
      tipo: "text",
      placeholder: "IBAMA / SEMAD / COPAM / IEF / Municipal",
    },
    {
      nome: "numero_auto_infracao",
      label: "Nº do auto / processo",
      tipo: "text",
    },
    {
      nome: "data_notificacao",
      label: "Data da ciência / notificação",
      tipo: "date",
      ajuda: "Prazo de defesa: 20 dias corridos (Decreto 6.514/08 art. 113)",
    },
    {
      nome: "valor_multa_original",
      label: "Valor da multa (R$)",
      tipo: "number",
    },
    {
      nome: "observacoes",
      label: "Observações / descrição do dano",
      tipo: "textarea",
      col: 2,
    },
  ],
  ferramentas: [
    {
      id: "auto-infracao-ambiental",
      titulo: "Auto de Infração Ambiental",
      descricao:
        "Prazo de defesa (20 dias), recursos, conversão de multa e teses de defesa.",
      baseLegal: "Lei 9.605/98 · Decreto 6.514/2008",
      grupo: "Contencioso",
      endpoint: "/ambiental/ferramentas/auto-infracao-ambiental",
      campos: [
        {
          nome: "data_ciencia",
          label: "Data da ciência / entrega",
          tipo: "date",
        },
        { nome: "valor_multa", label: "Valor da multa (R$)", tipo: "number" },
        {
          nome: "tipo_infracao",
          label: "Tipo de infração",
          tipo: "select",
          opcoes: [
            "degradacao",
            "desmatamento",
            "poluicao",
            "fauna",
            "flora",
            "residuos",
            "outro",
          ],
          default: "degradacao",
        },
      ],
    },
    {
      id: "crimes-ambientais",
      titulo: "Crimes Ambientais — Penas e Institutos",
      descricao:
        "Penas por tipo, suspensão condicional, transação penal e responsabilidade civil objetiva.",
      baseLegal: "Lei 9.605/1998 (Lei de Crimes Ambientais)",
      grupo: "Contencioso",
      endpoint: "/ambiental/ferramentas/crimes-ambientais",
      campos: [
        {
          nome: "tipo_crime",
          label: "Tipo de crime",
          tipo: "select",
          opcoes: [
            "desmatamento",
            "poluicao",
            "fauna",
            "flora",
            "mineracao",
            "residuos",
            "upa",
          ],
          default: "poluicao",
        },
        {
          nome: "pessoa",
          label: "Réu",
          tipo: "select",
          opcoes: ["fisica", "juridica"],
          default: "fisica",
        },
      ],
    },
    {
      id: "tac-ambiental",
      titulo: "TAC Ambiental — Requisitos e Cláusulas",
      descricao:
        "Termo de Ajustamento de Conduta: efeitos, cláusulas essenciais e vantagens.",
      baseLegal: "Lei 7.347/85 art. 5º §6º · Lei 9.605/98 art. 79-A",
      grupo: "Contencioso",
      endpoint: "/ambiental/ferramentas/tac-ambiental",
      campos: [
        {
          nome: "orgao_proponente",
          label: "Órgão proponente",
          tipo: "select",
          opcoes: ["mp", "ibama", "estado", "municipio"],
          default: "mp",
        },
        {
          nome: "tipo_dano",
          label: "Tipo de dano",
          tipo: "select",
          opcoes: ["desmatamento", "poluicao", "mineracao", "fauna", "outro"],
          default: "desmatamento",
        },
        { nome: "area_afetada_ha", label: "Área afetada (ha)", tipo: "number" },
        {
          nome: "valor_estimado_dano",
          label: "Valor estimado do dano (R$)",
          tipo: "number",
        },
      ],
    },
    {
      id: "licenciamento",
      titulo: "Licenciamento Ambiental — Fases e Prazos",
      descricao:
        "LP / LI / LO: documentos mínimos, prazos de análise, validade e órgãos competentes.",
      baseLegal: "LC 140/2011 · CONAMA 237/97",
      grupo: "Licenciamento",
      endpoint: "/ambiental/ferramentas/licenciamento",
      campos: [
        {
          nome: "fase",
          label: "Fase da licença",
          tipo: "select",
          opcoes: ["lp", "li", "lo"],
          default: "lp",
        },
        {
          nome: "porte",
          label: "Porte do empreendimento",
          tipo: "select",
          opcoes: ["pequeno", "medio", "grande"],
          default: "medio",
        },
        {
          nome: "data_protocolo",
          label: "Data do protocolo (se houver)",
          tipo: "date",
        },
      ],
    },
    {
      id: "reserva-legal",
      titulo: "Reserva Legal — Cálculo por Bioma",
      descricao:
        "Percentual obrigatório, área exigida, formas de regularização e APP adicional.",
      baseLegal: "Lei 12.651/2012 (Código Florestal) arts. 12-17",
      grupo: "Propriedade Rural",
      endpoint: "/ambiental/ferramentas/reserva-legal",
      campos: [
        {
          nome: "area_imovel_ha",
          label: "Área total do imóvel (hectares)",
          tipo: "number",
        },
        {
          nome: "bioma",
          label: "Bioma",
          tipo: "select",
          opcoes: [
            "amazonia",
            "cerrado",
            "pantanal",
            "caatinga",
            "mata_atlantica",
            "pampa",
          ],
          default: "cerrado",
        },
        {
          nome: "inscrito_car",
          label: "Inscrito no CAR?",
          tipo: "select",
          opcoes: ["true", "false"],
          default: "false",
        },
      ],
    },
  ],
};

// ══════════════════════════════════════════════════════════════════════════
// RAMOS COMPLEMENTARES (usam o sistema geral de casos — externo:true)
// ══════════════════════════════════════════════════════════════════════════
const _campoBasico: CampoConfig[] = [
  { nome: "titulo", label: "Assunto", tipo: "text", obrigatorio: true, col: 2 },
  { nome: "observacoes", label: "Observações", tipo: "textarea", col: 2 },
];

const consumidor: RamoConfig = {
  analiseDocumento: true,
  guiaConsumidor: true,
  slug: "consumidor",
  endpoint: "/cases/?area=consumidor",
  areaCaso: "consumidor",
  titulo: "Direito do Consumidor",
  subtitulo: "CDC · Planos de Saúde · E-commerce · Aviação · PROCON",
  icone: "Users",
  cor: "teal",
  campoTitulo: "titulo",
  campoStatus: "status",
  campos: _campoBasico,
  ferramentas: [
    {
      id: "devolucao-dobro",
      titulo: "Devolução em Dobro (art. 42)",
      descricao: "Repetição do indébito em dobro por cobrança indevida.",
      baseLegal: "CDC art. 42 §ú · STJ EAREsp 676.608",
      grupo: "Cálculos",
      endpoint: "/consumidor/ferramentas/devolucao-dobro",
      campos: [
        {
          nome: "valor_cobrado",
          label: "Valor cobrado indevidamente (R$)",
          tipo: "number",
        },
        {
          nome: "houve_ma_fe",
          label: "Cobrança sem engano justificável?",
          tipo: "select",
          opcoes: ["sim", "nao"],
          default: "sim",
        },
      ],
    },
    {
      id: "prazos-cdc",
      titulo: "Prazos CDC (decadência/prescrição)",
      descricao:
        "Vício (30/90d), fato (5a), cobrança indevida (3a), arrependimento (7d).",
      baseLegal: "CDC arts. 26, 27, 49",
      grupo: "Prazos",
      endpoint: "/consumidor/ferramentas/prazos-cdc",
      campos: [
        { nome: "data_fato", label: "Data do fato / entrega", tipo: "date" },
        {
          nome: "tipo",
          label: "Tipo de pretensão",
          tipo: "select",
          opcoes: [
            "vicio_duravel",
            "vicio_nao_duravel",
            "arrependimento",
            "fato",
            "cobranca_indevida",
          ],
          default: "vicio_duravel",
        },
      ],
    },
    {
      id: "negativacao-indevida",
      titulo: "Negativação Indevida (dano moral)",
      descricao: "Triagem do dano moral por inscrição irregular (Súmula 385).",
      baseLegal: "Súmula 385 STJ · CDC art. 6 VI",
      grupo: "Responsabilidade",
      endpoint: "/consumidor/ferramentas/negativacao-indevida",
      campos: [
        {
          nome: "existe_inscricao_anterior_legitima",
          label: "Há inscrição anterior legítima?",
          tipo: "select",
          opcoes: ["nao", "sim"],
          default: "nao",
        },
      ],
    },
  ],
  externo: true,
};
const familia: RamoConfig = {
  guiaFamilia: true,
  slug: "familia",
  endpoint: "/cases/?area=familia",
  areaCaso: "familia",
  titulo: "Direito de Família",
  subtitulo: "Divórcio · Guarda · Alimentos · Inventário · Sucessões",
  icone: "Scale",
  cor: "rose",
  campoTitulo: "titulo",
  campoStatus: "status",
  campos: _campoBasico,
  ferramentas: [
    {
      id: "debito-alimentos",
      titulo: "Débito de Pensão Alimentícia",
      descricao: "Débito acumulado e rito (prisão civil x penhora).",
      baseLegal: "CPC art. 528 §3/§8 · Súmula 309 STJ",
      grupo: "Execução",
      endpoint: "/familia/ferramentas/debito-alimentos",
      campos: [
        {
          nome: "valor_mensal",
          label: "Valor mensal da pensão (R$)",
          tipo: "number",
        },
        { nome: "meses_atraso", label: "Meses em atraso", tipo: "number" },
      ],
    },
    {
      id: "itcmd-inventario",
      titulo: "ITCMD no Inventário",
      descricao:
        "Imposto sobre o monte partilhável (MG 5%; conferir lei estadual).",
      baseLegal: "CTN art. 35 · MG Lei 14.941/03",
      grupo: "Sucessões",
      endpoint: "/familia/ferramentas/itcmd-inventario",
      campos: [
        { nome: "valor_monte", label: "Valor do monte (R$)", tipo: "number" },
        {
          nome: "aliquota_percentual",
          label: "Alíquota ITCMD (%)",
          tipo: "number",
          default: 5,
        },
      ],
    },
  ],
  externo: true,
};
const imobiliario: RamoConfig = {
  guiaImobiliario: true,
  slug: "imobiliario",
  endpoint: "/cases/?area=civil",
  areaCaso: "civil",
  titulo: "Direito Imobiliário",
  subtitulo: "Compra e Venda · Locação · Usucapião · Incorporação · Distrato",
  icone: "Building2",
  cor: "amber",
  campoTitulo: "titulo",
  campoStatus: "status",
  campos: _campoBasico,
  ferramentas: [
    {
      id: "reajuste-aluguel",
      titulo: "Reajuste de Aluguel",
      descricao: "Reajuste anual pelo índice contratual (IGP-M / IPCA).",
      baseLegal: "Lei 8.245/91 art. 18",
      grupo: "Locação",
      endpoint: "/imobiliario/ferramentas/reajuste-aluguel",
      campos: [
        { nome: "valor_atual", label: "Aluguel atual (R$)", tipo: "number" },
        {
          nome: "indice_percentual",
          label: "Índice de reajuste (%)",
          tipo: "number",
        },
      ],
    },
    {
      id: "prazos-despejo",
      titulo: "Ação de Despejo — Prazos",
      descricao: "Contestação e purga da mora por fundamento.",
      baseLegal: "Lei 8.245/91 arts. 9, 59-63",
      grupo: "Locação",
      endpoint: "/imobiliario/ferramentas/prazos-despejo",
      campos: [
        { nome: "data_citacao", label: "Data da citação", tipo: "date" },
        {
          nome: "fundamento",
          label: "Fundamento",
          tipo: "select",
          opcoes: ["falta_pagamento", "denuncia_vazia", "infracao"],
          default: "falta_pagamento",
        },
      ],
    },
    {
      id: "distrato",
      titulo: "Distrato Imobiliário (retenção)",
      descricao: "Retenção máxima no distrato de imóvel na planta.",
      baseLegal: "Lei 13.786/18 (art. 67-A Lei 4.591/64)",
      grupo: "Compra e Venda",
      endpoint: "/imobiliario/ferramentas/distrato",
      campos: [
        { nome: "valor_pago", label: "Valor já pago (R$)", tipo: "number" },
        {
          nome: "tem_patrimonio_afetacao",
          label: "Há patrimônio de afetação?",
          tipo: "select",
          opcoes: ["nao", "sim"],
          default: "nao",
        },
      ],
    },
  ],
  externo: true,
};
const previdenciario: RamoConfig = {
  guiaPrevidenciario: true,
  slug: "previdenciario",
  endpoint: "/cases/?area=previdenciario",
  areaCaso: "previdenciario",
  titulo: "Direito Previdenciário",
  subtitulo: "INSS · Aposentadorias · Benefícios · BPC/LOAS · Revisões",
  icone: "Scale",
  cor: "slate",
  campoTitulo: "titulo",
  campoStatus: "status",
  campos: _campoBasico,
  ferramentas: [
    {
      id: "prazos-previdenciario",
      titulo: "Prazos Previdenciários",
      descricao:
        "Recurso ao CRPS (30d), decadência de revisão (10a) e prescrição (5a).",
      baseLegal: "Lei 8.213/91 art. 103 · Dec. 3.048/99",
      grupo: "Prazos",
      endpoint: "/previdenciario/ferramentas/prazos",
      campos: [
        {
          nome: "data_indeferimento",
          label: "Data do indeferimento / concessão",
          tipo: "date",
        },
        {
          nome: "tipo",
          label: "Tipo de prazo",
          tipo: "select",
          opcoes: [
            "recurso_administrativo",
            "decadencia_revisao",
            "prescricao_parcelas",
          ],
          default: "recurso_administrativo",
        },
      ],
    },
    {
      id: "tempo-contribuicao",
      titulo: "Tempo de Contribuição (regra de pontos)",
      descricao:
        "Pontos = idade + tempo; compara com a regra de transição do ano.",
      baseLegal: "EC 103/2019 art. 15",
      grupo: "Cálculos",
      endpoint: "/previdenciario/ferramentas/tempo-contribuicao",
      campos: [
        { nome: "idade", label: "Idade (anos)", tipo: "number" },
        {
          nome: "tempo_contribuicao_anos",
          label: "Tempo de contribuição (anos)",
          tipo: "number",
        },
        {
          nome: "sexo",
          label: "Sexo",
          tipo: "select",
          opcoes: ["M", "F"],
          default: "M",
        },
        {
          nome: "ano",
          label: "Ano de referência",
          tipo: "number",
          default: 2026,
        },
      ],
    },
    {
      id: "carencia",
      titulo: "Carência do Benefício",
      descricao: "Meses de contribuição vs. carência exigida por benefício.",
      baseLegal: "Lei 8.213/91 arts. 25-26",
      grupo: "Cálculos",
      endpoint: "/previdenciario/ferramentas/carencia",
      campos: [
        {
          nome: "meses_contribuicao",
          label: "Meses de contribuição",
          tipo: "number",
        },
        {
          nome: "beneficio",
          label: "Benefício",
          tipo: "select",
          opcoes: [
            "aposentadoria",
            "auxilio_doenca",
            "aposentadoria_invalidez",
            "salario_maternidade",
            "auxilio_acidente",
            "pensao_morte",
          ],
          default: "aposentadoria",
        },
      ],
    },
  ],
  externo: true,
};
const digital_lgpd: RamoConfig = {
  analiseDocumento: true,
  guiaLgpd: true,
  lgpdRegistros: true,
  slug: "digital_lgpd",
  endpoint: "/cases/?area=empresarial",
  areaCaso: "empresarial",
  titulo: "Direito Digital e LGPD",
  subtitulo:
    "Adequação LGPD · DPO · Contratos SaaS · Startups · Incidentes de Dados",
  icone: "Lock",
  cor: "indigo",
  campoTitulo: "titulo",
  campoStatus: "status",
  campos: _campoBasico,
  ferramentas: [
    {
      id: "multa-lgpd",
      titulo: "Multa LGPD (art. 52)",
      descricao:
        "Teto de multa simples: 2% do faturamento, até R$ 50 mi por infração.",
      baseLegal: "LGPD Lei 13.709/18 art. 52 II",
      grupo: "Sanções",
      endpoint: "/digital_lgpd/ferramentas/multa-lgpd",
      campos: [
        {
          nome: "faturamento_anual",
          label: "Faturamento anual (R$)",
          tipo: "number",
        },
      ],
    },
    {
      id: "prazos-lgpd",
      titulo: "Prazos LGPD",
      descricao:
        "Resposta ao titular (15d) e comunicação de incidente à ANPD (3 dias úteis).",
      baseLegal: "LGPD art. 19 · Res. ANPD CD/15 2024",
      grupo: "Prazos",
      endpoint: "/digital_lgpd/ferramentas/prazos-lgpd",
      campos: [
        {
          nome: "data_evento",
          label: "Data do pedido / incidente",
          tipo: "date",
        },
        {
          nome: "tipo",
          label: "Tipo",
          tipo: "select",
          opcoes: ["resposta_titular", "incidente_anpd"],
          default: "resposta_titular",
        },
      ],
    },
  ],
  externo: true,
};

const transito: RamoConfig = {
  guiaTransito: true,
  slug: "transito",
  endpoint: "/cases/?area=civil",
  areaCaso: "civil",
  titulo: "Direito de Trânsito",
  subtitulo:
    "Multas \u00b7 Recursos JARI/CETRAN \u00b7 Suspens\u00e3o de CNH \u00b7 Crimes de tr\u00e2nsito",
  icone: "Car",
  cor: "bronze",
  campoTitulo: "titulo",
  campoStatus: "status",
  campos: _campoBasico,
  ferramentas: [
    {
      id: "prazos-recurso-transito",
      titulo: "Prazos e Desconto de Multa",
      descricao:
        "Defesa prévia, recurso JARI e CETRAN, com descontos (40% SNE / 20%).",
      baseLegal: "CTB arts. 281, 284, 285, 288 · Lei 14.071/20",
      grupo: "Multas",
      endpoint: "/transito/ferramentas/prazos-recurso",
      campos: [
        {
          nome: "data_notificacao",
          label: "Data da notificação",
          tipo: "date",
        },
        { nome: "valor_multa", label: "Valor da multa (R$)", tipo: "number" },
        {
          nome: "fase",
          label: "Fase",
          tipo: "select",
          opcoes: ["autuacao", "penalidade"],
          default: "autuacao",
        },
      ],
    },
    {
      id: "pontuacao-cnh",
      titulo: "Pontuação e Suspensão da CNH",
      descricao:
        "Teto de pontos conforme infrações gravíssimas nos últimos 12 meses.",
      baseLegal: "CTB art. 261 · Lei 14.071/20",
      grupo: "CNH",
      endpoint: "/transito/ferramentas/pontuacao-cnh",
      campos: [
        {
          nome: "pontos_total",
          label: "Pontos acumulados (12m)",
          tipo: "number",
        },
        {
          nome: "infracoes_gravissimas_12m",
          label: "Infrações gravíssimas (12m)",
          tipo: "number",
          default: 0,
        },
        {
          nome: "categoria_profissional",
          label: "Condutor profissional (EAR)?",
          tipo: "select",
          opcoes: ["nao", "sim"],
          default: "nao",
        },
      ],
    },
    {
      id: "valor-multa",
      titulo: "Valor da Multa (por gravidade)",
      descricao: "Valor-base do CTB por gravidade, com multiplicador.",
      baseLegal: "CTB art. 258 · Lei 13.281/16",
      grupo: "Cálculos",
      endpoint: "/transito/ferramentas/valor-multa",
      campos: [
        {
          nome: "gravidade",
          label: "Gravidade",
          tipo: "select",
          opcoes: ["leve", "media", "grave", "gravissima"],
          default: "media",
        },
        {
          nome: "multiplicador",
          label: "Multiplicador (gravíssimas)",
          tipo: "number",
          default: 1,
        },
      ],
    },
  ],
  externo: true,
  subareas: [
    "Defesa pr\u00e9via e recursos (JARI/CETRAN)",
    "Suspens\u00e3o e cassa\u00e7\u00e3o de CNH",
    "Sistema de pontos (Lei 14.071/20)",
    "Gest\u00e3o de multas de frota (PJ)",
    "Mandado de seguran\u00e7a",
    "Crimes de tr\u00e2nsito",
    "Repeti\u00e7\u00e3o de ind\u00e9bito de multa",
    "Prescri\u00e7\u00e3o (CTB 322)",
  ],
  ferramentasExternas: [
    {
      nome: "DETRAN-MG",
      url: "https://www.detran.mg.gov.br",
      descricao: "Multas, pontos, recursos, situa\u00e7\u00e3o do ve\u00edculo",
    },
    {
      nome: "INMETRO \u2014 afericao",
      url: "https://www.gov.br/inmetro",
      descricao:
        "Aprova\u00e7\u00e3o de modelo e afericao de radares/etil\u00f4metros",
    },
    {
      nome: "CONTRAN",
      url: "https://www.gov.br/transportes/pt-br/assuntos/transito/contran",
      descricao: "Resolu\u00e7\u00f5es vigentes",
    },
    {
      nome: "SENATRAN",
      url: "https://www.gov.br/transportes/pt-br/assuntos/transito/senatran",
      descricao: "Portarias e valores de multas",
    },
  ],
};

export const RAMOS: Record<string, RamoConfig> = {
  empresarial,
  civel,
  penal,
  trabalhista,
  administrativo,
  bancario,
  tributario,
  ambiental,
  consumidor,
  familia,
  imobiliario,
  previdenciario,
  digital_lgpd,
  transito,
};

export const RAMOS_LISTA = Object.values(RAMOS);

// ══════════════════════════════════════════════════════════════════════════
// SUBÁREAS DE ATUAÇÃO + FERRAMENTAS PÚBLICAS EXTERNAS (por ramo)
// ══════════════════════════════════════════════════════════════════════════
const SUBAREAS: Record<string, string[]> = {
  empresarial: [
    "Auditoria Jurídica Preventiva",
    "Compliance Empresarial",
    "Gestão de Passivo Bancário e Reestruturação de Dívidas",
    "Contratos, Notificações e Documentos Empresariais",
    "Contencioso Cível e Trabalhista Empresarial",
    "Defesa em Execuções, Bloqueios e Cobranças Judiciais",
    "Cobrança de Créditos (Administrativa e Judicial)",
    "Assessoria Estratégica em Negócios e Impasses Comerciais",
    "Relação com o Poder Público e Órgãos Reguladores",
    "Conflito entre Sócios",
    "Saída ou Retirada de Sócio",
    "Revisão ou Criação de Acordo de Sócios",
    "Reestruturação Societária",
    "Constituição de Holding Empresarial",
    "Estrutura Societária para Empresas Digitais",
    "Elaboração e Revisão de Contratos Empresariais",
    "Planejamento Societário com Foco Tributário",
    "Defesa Patronal (Consultoria e Contencioso)",
    "Compliance Trabalhista",
    "Negociação Coletiva",
    "Terceirização e Contratos de Trabalho",
    "Defesa do Consumidor para Empresas (PROCON)",
    "Licitações e Contratos Públicos",
  ],
  consumidor: [
    "Planos de Saúde — Negativa de Cobertura",
    "Medicamentos de Alto Custo (rol ANS)",
    "Reajustes Abusivos de Mensalidade",
    "E-commerce e Compras Online",
    "Marketplaces — Golpes e Fraudes",
    "Direito de Arrependimento (7 dias)",
    "Extravio ou Atraso na Entrega",
    "Atraso na Entrega de Imóveis",
    "Cortes de Energia e Água",
    "Aviação — Voo Cancelado/Atrasado",
    "Extravio/Danificação de Bagagem",
    "Overbooking",
    "Produtos com Vício/Defeito (Garantia)",
    "Obsolescência Programada",
    "Telefonia e Internet",
    "PROCON e Consumidor.gov",
  ],
  bancario: [
    "Ação Revisional de Veículos",
    "Crédito Consignado (margem)",
    "Cartão de Crédito e Cheque Especial (juros rotativos)",
    "Combate a Juros Abusivos e Revisão de Contratos",
    "Golpe do PIX e Boletos Falsos (Súmula 479 STJ)",
    "Empréstimo Não Solicitado (devolução em dobro)",
    "Clonagem e Compras Indevidas",
    "Superendividamento (Lei 14.181/21)",
    "Plano de Repactuação de Dívidas",
    "Garantia do Mínimo Existencial",
    "Negativação Indevida (SPC/Serasa)",
    "Manutenção Indevida em Cadastros",
    "Limpeza do SCR/Registrato (BACEN)",
    "Defesa em Busca e Apreensão (purgação da mora)",
  ],
  trabalhista: [
    "Verbas Rescisórias",
    "Horas Extras e Intervalos",
    "Reconhecimento de Vínculo Empregatício",
    "Acidentes e Doenças Ocupacionais",
    "Assédio Moral/Sexual e Danos Morais",
    "Estabilidades (gestante, cipeiro, acidentado)",
    "Bancários (7ª e 8ª horas)",
    "Trabalhadores Domésticos (LC 150)",
    "Profissionais da Saúde (insalubridade/plantões)",
    "Construção Civil (periculosidade/terceirização)",
    "Defesa Patronal (Contestação)",
    "Compliance Trabalhista (auditoria interna)",
    "Negociação Coletiva (sindicatos)",
    "Terceirização e Trabalho Intermitente/Teletrabalho",
  ],
  administrativo: [
    "Licitações e Contratos Administrativos",
    "Análise de Editais (cláusulas restritivas)",
    "Impugnações e Recursos",
    "Equilíbrio Econômico-Financeiro (reajuste)",
    "Defesa em Sanções (multas/inidoneidade)",
    "Defesa de Servidores Públicos",
    "Processo Administrativo Disciplinar (PAD)",
    "Concursos Públicos (eliminação injusta)",
    "Direitos e Vantagens (progressões/aposentadoria)",
    "Agências Reguladoras (ANATEL/ANVISA/ANEEL)",
    "Parcerias Público-Privadas (PPP)",
    "Lei de Improbidade Administrativa",
    "Tribunais de Contas (TCU/TCE)",
    "Desapropriações e Indenizações",
    "Uso de Bens Públicos (concessões/permissões)",
  ],
  tributario: [
    "Consultoria Tributária e Planejamento Fiscal",
    "Escolha de Regime (Simples/Presumido/Real)",
    "Reestruturação Societária (eficiência fiscal)",
    "Mapeamento de Benefícios Fiscais",
    "Impugnação de Autos de Infração",
    "Recursos ao CARF e TARF",
    "Consulta Formal ao Fisco",
    "Ações de Repetição de Indébito (5 anos)",
    "Mandado de Segurança (CPEN)",
    "Defesa em Execução Fiscal",
    "Exceção de Pré-Executividade",
    "Federais (IRPJ, CSLL, PIS, COFINS, IPI, INSS)",
    "Estaduais (ICMS, ITCMD, IPVA)",
    "Municipais (ISS, IPTU, ITBI)",
  ],
  ambiental: [
    "Consultoria Preventiva e Compliance Ambiental",
    "Licenciamento Ambiental (LP/LI/LO)",
    "Renovação Prévia de Licenças (120 dias)",
    "Auditoria e Compliance ESG",
    "Estudos de Impacto (EIA/RIMA)",
    "Regularização Rural (CAR/APP/Reserva Legal)",
    "Defesa contra Autos de Infração (IBAMA/ICMBio)",
    "Termo de Ajustamento de Conduta (TAC)",
    "Ação Civil Pública",
    "Due Diligence Ambiental (passivos ocultos)",
    "Crimes Ambientais (Lei 9.605/98)",
    "Responsabilidade Penal da Pessoa Jurídica",
    "Logística Reversa (PNRS)",
    "Conversão de Multas em Serviços",
    "Mercado de Carbono",
    "Créditos de Reciclagem",
  ],
  penal: [
    "Homicídio e Infanticídio (Tribunal do Júri)",
    "Lesão Corporal",
    "Crimes Contra a Honra (Calúnia/Difamação/Injúria)",
    "Ameaça e Cárcere Privado",
    "Roubo e Furto (qualificadoras)",
    "Estelionato e Fraudes",
    "Receptação",
    "Extorsão e Dano",
    "Lavagem de Dinheiro",
    "Crimes Contra a Ordem Tributária",
    "Crimes Contra o Sistema Financeiro",
    "Corrupção (Ativa e Passiva)",
    "Invasão de Dispositivo Informático",
    "Fraudes Eletrônicas",
    "Vazamento de Dados e Fotos (LGPD)",
    "Estupro e Importunação Sexual",
    "Violência Doméstica (Lei Maria da Penha)",
    "Tráfico de Drogas (desclassificação)",
    "Crimes Ambientais",
    "Estatuto do Desarmamento",
  ],
  civel: [
    "Responsabilidade Civil e Indenizações",
    "Contratos Cíveis",
    "Cobranças e Execuções",
    "Obrigações",
    "Danos Morais e Materiais",
  ],
  familia: [
    "Divórcio Consensual e Litigioso",
    "Guarda (unilateral/compartilhada)",
    "Pensão Alimentícia — Fixação e Revisão",
    "Investigação de Paternidade",
    "União Estável — Reconhecimento e Dissolução",
    "Inventário e Partilha",
    "Testamento e Planejamento Sucessório",
    "Alienação Parental",
    "Tutela e Curatela",
  ],
  imobiliario: [
    "Compra e Venda de Imóveis",
    "Contratos de Locação",
    "Despejo e Ações Locatícias",
    "Usucapião",
    "Regularização Fundiária",
    "Incorporação Imobiliária",
    "Distrato e Atraso na Entrega",
    "Condomínio",
    "Financiamento e Alienação Fiduciária",
  ],
  previdenciario: [
    "Aposentadoria por Idade/Tempo de Contribuição",
    "Aposentadoria Especial",
    "Auxílio-Doença e Auxílio-Acidente",
    "BPC/LOAS",
    "Pensão por Morte",
    "Salário-Maternidade",
    "Revisão de Benefícios",
    "Planejamento Previdenciário",
    "Aposentadoria por Invalidez",
  ],
  digital_lgpd: [
    "Direito do Influenciador / Creators",
    "Contratos de Publicidade (publi)",
    "Direito de Imagem e Voz",
    "Remoção de Conteúdo e Difamação Online",
    "Direito ao Esquecimento",
    "Perfis Falsos / Fake News",
    "Monetização e Plataformas (YouTube, TikTok, Instagram)",
    "Publicidade Enganosa (CONAR)",
    "Golpes e Crimes Digitais",
    "Propriedade Intelectual de Conteúdo",
    "Adequação à LGPD",
    "DPO as a Service",
    "Políticas de Privacidade e Termos de Uso",
    "Contratos de Tecnologia (SaaS)",
    "Startup Law / Mútuo Conversível",
    "E-commerce",
    "Segurança da Informação",
    "Resposta a Incidentes de Dados",
    "Direito de Imagem e Reputação Digital",
    "Marco Civil da Internet",
  ],
};

const FERRAMENTAS_EXTERNAS: Record<string, LinkExterno[]> = {
  empresarial: [
    {
      nome: "Juntas Comerciais — REDESIM (todos os estados)",
      url: "https://www.gov.br/empresas-e-negocios/pt-br/redesim",
      descricao:
        "Registro e consulta de empresas em qualquer UF (Rede Nacional).",
    },
    {
      nome: "Junta Comercial — JUCEMG",
      url: "https://www.jucemg.mg.gov.br/",
      descricao: "Registro e certidões de empresas (MG).",
    },
    {
      nome: "Central de Protestos (CENPROT)",
      url: "https://site.cenprot.org.br/",
      descricao: "Consulta nacional de títulos protestados.",
    },
    {
      nome: "SINTEGRA",
      url: "http://www.sintegra.gov.br/",
      descricao: "Consulta de inscrição estadual / cadastro ICMS.",
    },
    {
      nome: "Simples Nacional — consulta",
      url: "https://www8.receita.fazenda.gov.br/SimplesNacional/",
      descricao: "Situação do contribuinte no Simples Nacional.",
    },
    {
      nome: "Serasa — consulta/limpa nome",
      url: "https://www.serasa.com.br/",
      descricao: "Consulta de pendências e negativações (Serasa).",
    },
    {
      nome: "CND Federal (CNPJ) — Receita/PGFN",
      url: "https://servicos.receita.fazenda.gov.br/Servicos/certidao/CndConjuntaInter/InformaNICertidao.asp?Tipo=2",
      descricao: "Certidão negativa de débitos federais da empresa.",
    },
    {
      nome: "CNDT — Certidão Trabalhista (TST)",
      url: "https://www.tst.jus.br/certidao",
      descricao: "Certidão negativa de débitos trabalhistas.",
    },
    {
      nome: "CRF FGTS — Caixa",
      url: "https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf",
      descricao: "Regularidade do FGTS da empresa.",
    },
    {
      nome: "PNCP — Contratações Públicas",
      url: "https://www.gov.br/pncp/",
      descricao: "Editais de licitação e contratos públicos do Brasil.",
    },
    {
      nome: "Consulta CNPJ — Receita Federal",
      url: "https://solucoes.receita.fazenda.gov.br/servicos/cnpjreva/cnpjreva_solicitacao.asp",
      descricao: "Situação cadastral de empresas.",
    },
    {
      nome: "INPI — Marcas e Patentes",
      url: "https://busca.inpi.gov.br/pePI/",
      descricao: "Busca de marcas e propriedade industrial.",
    },
  ],
  trabalhista: [
    {
      nome: "INFOJUD (via e-CAC)",
      url: "https://cav.receita.fazenda.gov.br/",
      descricao:
        "Dados fiscais — acesso restrito ao Judiciário (requerer via petição).",
    },
    {
      nome: "SerasaJud",
      url: "https://www.serasaexperian.com.br/",
      descricao:
        "Negativação por ordem judicial — acesso restrito ao Judiciário.",
    },
    {
      nome: "CNDT — Certidão Trabalhista (TST)",
      url: "https://www.tst.jus.br/certidao",
      descricao: "Certidão negativa de débitos trabalhistas.",
    },
    {
      nome: "PJe-Calc Cidadão",
      url: "https://pje-calc.csjt.jus.br/",
      descricao: "Cálculo oficial de verbas rescisórias, horas extras e FGTS.",
    },
    {
      nome: "SISBAJUD — Bloqueio de valores (CNJ)",
      url: "https://www.sisbajud.cnj.jus.br/",
      descricao:
        "Bloqueio/penhora de ativos financeiros. Acesso restrito ao Judiciário — advogado requer via petição.",
    },
    {
      nome: "RENAJUD — Restrição de veículos",
      url: "https://renajud.denatran.serpro.gov.br/",
      descricao:
        "Restrição/penhora de veículos. Acesso restrito — solicitar via petição.",
    },
    {
      nome: "CNIB — Indisponibilidade de Bens",
      url: "https://www.indisponibilidade.org.br/",
      descricao: "Central Nacional de Indisponibilidade de Bens (imóveis).",
    },
    {
      nome: "Consumidor.gov.br",
      url: "https://www.consumidor.gov.br/",
      descricao: "Tentativa de acordo extrajudicial registrada.",
    },
  ],
  bancario: [
    {
      nome: "DETRAN — busca por estado (gov.br)",
      url: "https://www.gov.br/pt-br/servicos-estaduais",
      descricao: "Localize o DETRAN do estado do cliente (serviços estaduais).",
    },
    {
      nome: "Serasa — consulta/limpa nome",
      url: "https://www.serasa.com.br/",
      descricao: "Consulta de pendências e negativações (Serasa).",
    },
    {
      nome: "SPC Brasil",
      url: "https://www.spcbrasil.org.br/",
      descricao: "Consulta de restrições de crédito (SPC).",
    },
    {
      nome: "Central de Protestos (CENPROT)",
      url: "https://site.cenprot.org.br/",
      descricao: "Consulta nacional de títulos protestados.",
    },
    {
      nome: "DETRAN-MG",
      url: "https://www.detran.mg.gov.br/",
      descricao: "Consulta de veículos, CNH, multas e débitos.",
    },
    {
      nome: "Registrato — Banco Central",
      url: "https://www.bcb.gov.br/cidadaniafinanceira/registrato",
      descricao: "SCR e relacionamento com instituições financeiras.",
    },
    {
      nome: "Calculadora do Cidadão — BACEN",
      url: "https://www3.bcb.gov.br/CALCIDADAO/",
      descricao: "Correção de valores e simulação de juros.",
    },
  ],
  civel: [
    {
      nome: "DETRAN — busca por estado (gov.br)",
      url: "https://www.gov.br/pt-br/servicos-estaduais",
      descricao: "Localize o DETRAN do estado do cliente (serviços estaduais).",
    },
    {
      nome: "Central de Protestos (CENPROT)",
      url: "https://site.cenprot.org.br/",
      descricao: "Consulta nacional de títulos protestados.",
    },
    {
      nome: "Serasa — consulta/limpa nome",
      url: "https://www.serasa.com.br/",
      descricao: "Consulta de pendências e negativações (Serasa).",
    },
    {
      nome: "SPC Brasil",
      url: "https://www.spcbrasil.org.br/",
      descricao: "Consulta de restrições de crédito (SPC).",
    },
    {
      nome: "DETRAN-MG",
      url: "https://www.detran.mg.gov.br/",
      descricao: "Consulta de veículos, CNH, multas e débitos.",
    },
    {
      nome: "Junta Comercial — JUCEMG",
      url: "https://www.jucemg.mg.gov.br/",
      descricao: "Registro e certidões de empresas (MG).",
    },
    {
      nome: "INFOJUD (via e-CAC)",
      url: "https://cav.receita.fazenda.gov.br/",
      descricao:
        "Dados fiscais — acesso restrito ao Judiciário (requerer via petição).",
    },
    {
      nome: "SerasaJud",
      url: "https://www.serasaexperian.com.br/",
      descricao:
        "Negativação por ordem judicial — acesso restrito ao Judiciário.",
    },
    {
      nome: "CND Federal (CPF/CNPJ)",
      url: "https://servicos.receita.fazenda.gov.br/Servicos/certidao/CndConjuntaInter/InformaNICertidao.asp?Tipo=1",
      descricao: "Certidão de débitos federais (útil em execução/cobrança).",
    },
    {
      nome: "SISBAJUD — Bloqueio de valores (CNJ)",
      url: "https://www.sisbajud.cnj.jus.br/",
      descricao:
        "Bloqueio/penhora de ativos financeiros. Acesso restrito ao Judiciário — advogado requer via petição.",
    },
    {
      nome: "RENAJUD — Restrição de veículos",
      url: "https://renajud.denatran.serpro.gov.br/",
      descricao:
        "Restrição/penhora de veículos. Acesso restrito — solicitar via petição.",
    },
    {
      nome: "CNIB — Indisponibilidade de Bens",
      url: "https://www.indisponibilidade.org.br/",
      descricao: "Central Nacional de Indisponibilidade de Bens (imóveis).",
    },
    {
      nome: "Consumidor.gov.br",
      url: "https://www.consumidor.gov.br/",
      descricao: "Resolução de conflitos de consumo online.",
    },
    {
      nome: "ViaCEP",
      url: "https://viacep.com.br/",
      descricao: "Consulta de endereços por CEP.",
    },
    {
      nome: "Calculadora do Cidadão — BACEN",
      url: "https://www3.bcb.gov.br/CALCIDADAO/",
      descricao: "Correção monetária de valores.",
    },
  ],
  ambiental: [
    {
      nome: "MapBiomas",
      url: "https://plataforma.brasil.mapbiomas.org/",
      descricao: "Uso e cobertura da terra ano a ano (satélite).",
    },
    {
      nome: "Google Earth Pro",
      url: "https://www.google.com/earth/about/versions/",
      descricao: "Histórico de imagens de satélite por data.",
    },
    {
      nome: "Consulta Pública do CAR",
      url: "https://consultapublica.car.gov.br/publico/imoveis/index",
      descricao: "Regularidade ambiental de imóveis rurais.",
    },
  ],
  penal: [
    {
      nome: "Atestado de Antecedentes — Polícia Federal",
      url: "https://servicos.pf.gov.br/epol-sinic-publico/",
      descricao: "Emissão online do atestado de antecedentes criminais (PF).",
    },
    {
      nome: "Certidão Criminal — TJMG",
      url: "https://www4.tjmg.jus.br/juridico/certidaoJudicial/",
      descricao: "Certidão de ações criminais do Tribunal de Justiça de MG.",
    },
    {
      nome: "Certidões da Justiça Federal (TRF)",
      url: "https://www.cjf.jus.br/cjf/certidao-negativa",
      descricao: "Certidão de distribuição criminal na Justiça Federal.",
    },
    {
      nome: "BNMP — CNJ",
      url: "https://portalbnmp.cnj.jus.br/",
      descricao: "Banco Nacional de Mandados de Prisão.",
    },
    {
      nome: "Wayback Machine",
      url: "https://web.archive.org/",
      descricao: "Arquivo histórico de páginas da internet.",
    },
  ],
  administrativo: [
    {
      nome: "SICAF",
      url: "https://www3.comprasnet.gov.br/sicaf-web/",
      descricao: "Cadastro de fornecedores do governo federal.",
    },
    {
      nome: "Portal da Transparência",
      url: "https://portaldatransparencia.gov.br/",
      descricao: "Gastos, contratos e sanções da administração pública.",
    },
    {
      nome: "PNCP — Contratações Públicas",
      url: "https://www.gov.br/pncp/",
      descricao: "Editais e contratos da administração pública.",
    },
    {
      nome: "Compras.gov.br",
      url: "https://www.gov.br/compras/",
      descricao: "Portal de compras do Governo Federal.",
    },
  ],
  consumidor: [
    {
      nome: "DETRAN — busca por estado (gov.br)",
      url: "https://www.gov.br/pt-br/servicos-estaduais",
      descricao: "Localize o DETRAN do estado do cliente (serviços estaduais).",
    },
    {
      nome: "Serasa — consulta/limpa nome",
      url: "https://www.serasa.com.br/",
      descricao: "Consulta de pendências e negativações (Serasa).",
    },
    {
      nome: "SPC Brasil",
      url: "https://www.spcbrasil.org.br/",
      descricao: "Consulta de restrições de crédito (SPC).",
    },
    {
      nome: "Reclame Aqui",
      url: "https://www.reclameaqui.com.br/",
      descricao: "Histórico de reclamações contra a empresa.",
    },
    {
      nome: "DETRAN-MG",
      url: "https://www.detran.mg.gov.br/",
      descricao: "Consulta de veículos, CNH, multas e débitos.",
    },
    {
      nome: "Consumidor.gov.br",
      url: "https://www.consumidor.gov.br/",
      descricao: "Resolução de conflitos de consumo online.",
    },
    {
      nome: "PROCON",
      url: "https://www.procon.sp.gov.br/",
      descricao: "Órgão de defesa do consumidor.",
    },
    {
      nome: "ANS — Planos de Saúde",
      url: "https://www.gov.br/ans/pt-br",
      descricao: "Agência Nacional de Saúde Suplementar.",
    },
  ],
  familia: [
    {
      nome: "CRC Nacional — Registro Civil",
      url: "https://www.registrocivil.org.br/",
      descricao: "Certidões de nascimento, casamento e óbito; busca nacional.",
    },
    {
      nome: "e-Notariado — Divórcio/Inventário",
      url: "https://www.e-notariado.org.br/",
      descricao: "Divórcio e inventário extrajudicial em cartório online.",
    },
    {
      nome: "Calculadora do Cidadão — BACEN",
      url: "https://www3.bcb.gov.br/CALCIDADAO/",
      descricao: "Correção de alimentos/valores em atraso.",
    },
    {
      nome: "Calculadora do Cidadão — BACEN",
      url: "https://www3.bcb.gov.br/CALCIDADAO/",
      descricao: "Correção de valores de pensão/partilha.",
    },
    {
      nome: "CNJ — Consulta Processual",
      url: "https://www.cnj.jus.br/",
      descricao: "Acompanhamento processual unificado.",
    },
  ],
  imobiliario: [
    {
      nome: "Registradores — Consulta de Matrícula",
      url: "https://www.registradores.org.br/",
      descricao: "Certidões e matrículas de imóveis (ONR/CRI).",
    },
    {
      nome: "e-Notariado / Cartório 24h",
      url: "https://www.e-notariado.org.br/",
      descricao: "Atos notariais online (escritura, divórcio, inventário).",
    },
    {
      nome: "ViaCEP",
      url: "https://viacep.com.br/",
      descricao: "Consulta de endereços por CEP.",
    },
    {
      nome: "ONR — Registro de Imóveis",
      url: "https://www.registradores.org.br/",
      descricao: "Consulta e certidões de registro de imóveis.",
    },
    {
      nome: "ViaCEP",
      url: "https://viacep.com.br/",
      descricao: "Consulta de endereços por CEP.",
    },
  ],
  previdenciario: [
    {
      nome: "CNIS — Extrato de Contribuições",
      url: "https://meu.inss.gov.br/",
      descricao: "Histórico de vínculos e contribuições (CNIS).",
    },
    {
      nome: "Tábua de Mortalidade — IBGE",
      url: "https://www.ibge.gov.br/estatisticas/sociais/populacao/9126-tabuas-completas-de-mortalidade.html",
      descricao: "Expectativa de sobrevida (fator previdenciário/pensão).",
    },
    {
      nome: "Meu INSS",
      url: "https://meu.inss.gov.br/",
      descricao: "Benefícios, CNIS e simulação de aposentadoria.",
    },
    {
      nome: "Simulador de Aposentadoria",
      url: "https://www.gov.br/inss/pt-br",
      descricao: "Simulação oficial de tempo de contribuição.",
    },
  ],
  digital_lgpd: [
    {
      nome: "Lei Geral de Proteção de Dados (texto)",
      url: "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm",
      descricao: "Texto oficial da LGPD (Lei 13.709/2018).",
    },
    {
      nome: "Marco Civil da Internet (texto)",
      url: "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2014/lei/l12965.htm",
      descricao: "Texto oficial do Marco Civil (Lei 12.965/2014).",
    },
    {
      nome: "SaferNet — Denúncia de crimes digitais",
      url: "https://new.safernet.org.br/",
      descricao: "Canal de denúncia de conteúdo ilegal online.",
    },
    {
      nome: "CONAR — Publicidade",
      url: "http://www.conar.org.br/",
      descricao:
        "Autorregulamentação publicitária; denúncia de publi enganosa.",
    },
    {
      nome: "Registro.br — Domínios",
      url: "https://registro.br/",
      descricao: "Consulta e registro de domínios .br (whois).",
    },
    {
      nome: "Google — Remoção de conteúdo",
      url: "https://support.google.com/legal/answer/3110420",
      descricao:
        "Pedidos legais de remoção de conteúdo / direito ao esquecimento.",
    },
    {
      nome: "ANPD",
      url: "https://www.gov.br/anpd/pt-br",
      descricao: "Autoridade Nacional de Proteção de Dados.",
    },
    {
      nome: "gov.br",
      url: "https://www.gov.br/",
      descricao: "Autenticação e serviços digitais do governo.",
    },
  ],
  tributario: [
    {
      nome: "SINTEGRA",
      url: "http://www.sintegra.gov.br/",
      descricao: "Consulta de inscrição estadual / cadastro ICMS.",
    },
    {
      nome: "Simples Nacional — consulta",
      url: "https://www8.receita.fazenda.gov.br/SimplesNacional/",
      descricao: "Situação do contribuinte no Simples Nacional.",
    },
    {
      nome: "PGFN Regularize",
      url: "https://www.regularize.pgfn.gov.br/",
      descricao: "Negociação e regularização da dívida ativa da União.",
    },
    {
      nome: "INFOJUD (via e-CAC)",
      url: "https://cav.receita.fazenda.gov.br/",
      descricao:
        "Dados fiscais — acesso restrito ao Judiciário (requerer via petição).",
    },
    {
      nome: "CND Federal (CPF e CNPJ) — Receita/PGFN",
      url: "https://servicos.receita.fazenda.gov.br/Servicos/certidao/CndConjuntaInter/InformaNICertidao.asp?Tipo=1",
      descricao: "Certidão de débitos federais e dívida ativa da União.",
    },
    {
      nome: "CNDT — Certidão Trabalhista (TST)",
      url: "https://www.tst.jus.br/certidao",
      descricao: "Certidão negativa de débitos trabalhistas (CPF/CNPJ).",
    },
    {
      nome: "CRF FGTS — Caixa",
      url: "https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf",
      descricao: "Certidão de regularidade do FGTS.",
    },
    {
      nome: "e-CAC — Receita Federal",
      url: "https://cav.receita.fazenda.gov.br/",
      descricao: "Centro Virtual de Atendimento do contribuinte.",
    },
    {
      nome: "Simulador IRPF — Receita",
      url: "https://www.gov.br/receitafederal/",
      descricao: "Simulação de Imposto de Renda.",
    },
    {
      nome: "CARF",
      url: "https://carf.economia.gov.br/",
      descricao: "Conselho Administrativo de Recursos Fiscais.",
    },
  ],
};

for (const slug of Object.keys(RAMOS)) {
  if (SUBAREAS[slug]) RAMOS[slug].subareas = SUBAREAS[slug];
  if (FERRAMENTAS_EXTERNAS[slug])
    RAMOS[slug].ferramentasExternas = FERRAMENTAS_EXTERNAS[slug];
}

export const RAMOS_LISTA_FINAL = Object.values(RAMOS);
