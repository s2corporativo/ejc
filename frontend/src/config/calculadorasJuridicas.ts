// ── config/calculadorasJuridicas.ts ─────────────────────────────────────────
// V2-5.1 (plano-mestre): ~50 endpoints GET /{area}/ferramentas/{nome} já
// implementados e funcionais no backend (padrão `_EQUIPE`, query params
// tipados, resposta com `fontes`/`aviso`/`vigencia_regra`) sem NENHUMA tela
// que os exponha — a auditoria chamou de "maior ganho rápido do backlog".
//
// Esta config declara a PRIMEIRA LEVA (6 ferramentas — 4 cível + 2 penal,
// as que tiveram o código-fonte lido e confirmado). O padrão é
// deliberadamente genérico (campos tipados + endpoint) para que as ~44
// restantes entrem só como novas entradas neste array, sem mudança de tipo
// nem de componente — ver CalculadorasJuridicas.tsx.
export type TipoCampo = "date" | "number" | "text" | "select" | "boolean" | "sim_nao";

export interface OpcaoCampo {
  value: string;
  label: string;
}

export interface CampoConfig {
  /** Nome exato do query param no backend (ex.: "salario_devedor"). */
  nome: string;
  label: string;
  tipo: TipoCampo;
  obrigatorio?: boolean;
  /** Para tipo "select" — espelha os Literal[...] do backend. */
  opcoes?: OpcaoCampo[];
  min?: number;
  max?: number;
  valorPadrao?: string | number | boolean;
  /** Texto de apoio abaixo do campo (regra de negócio, unidade, etc.). */
  ajuda?: string;
  /**
   * Visibilidade condicional — recebe os valores atuais do formulário.
   * Omitido = sempre visível.
   */
  exibirSe?: (valores: Record<string, unknown>) => boolean;
}

export interface FerramentaConfig {
  /** Slug único e estável. */
  chave: string;
  titulo: string;
  descricao: string;
  /** Rótulo de agrupamento — "Cível" | "Penal" hoje, extensível. */
  area: string;
  /** Path exato do endpoint GET, sem prefixo (bate com src/lib/api.ts). */
  endpoint: string;
  campos: CampoConfig[];
}

export const CALCULADORAS_JURIDICAS: FerramentaConfig[] = [
  {
    chave: "civel-prazos-contestacao",
    titulo: "Prazo de contestação",
    descricao:
      "Calcula o prazo de contestação por rito (comum, JEC, Fazenda Pública).",
    area: "Cível",
    endpoint: "/civel/ferramentas/prazos-contestacao",
    campos: [
      {
        nome: "rito",
        label: "Rito",
        tipo: "select",
        obrigatorio: true,
        opcoes: [
          { value: "comum", label: "Comum" },
          { value: "jec", label: "Juizado Especial Cível" },
          { value: "fazenda_publica", label: "Fazenda Pública" },
        ],
      },
      {
        nome: "marco",
        label: "Marco inicial",
        tipo: "select",
        opcoes: [
          { value: "audiencia_conciliacao", label: "Audiência de conciliação" },
          { value: "juntada_citacao", label: "Juntada do comprovante de citação" },
        ],
        ajuda: "Obrigatório para rito comum e Fazenda Pública (CPC art. 335).",
        exibirSe: (v) => v.rito !== "jec",
      },
      {
        nome: "data_marco",
        label: "Data do marco",
        tipo: "date",
        exibirSe: (v) => v.rito !== "jec",
      },
    ],
  },
  {
    chave: "civel-alimentos-calcular",
    titulo: "Cálculo de alimentos",
    descricao:
      "Estimativa aritmética a partir de percentual informado (não é regra legal fixa).",
    area: "Cível",
    endpoint: "/civel/ferramentas/alimentos-calcular",
    campos: [
      {
        nome: "salario_devedor",
        label: "Salário do devedor (R$)",
        tipo: "number",
        obrigatorio: true,
        min: 0,
      },
      {
        nome: "percentual",
        label: "Percentual (%)",
        tipo: "number",
        obrigatorio: true,
        min: 0,
        max: 100,
      },
      {
        nome: "filhos",
        label: "Número de filhos",
        tipo: "number",
        min: 1,
        valorPadrao: 1,
      },
    ],
  },
  {
    chave: "civel-usucapiao-verificar",
    titulo: "Verificação de usucapião",
    descricao:
      "Requisitos por modalidade (CC arts. 1.238-1.244, CF arts. 183 e 191).",
    area: "Cível",
    endpoint: "/civel/ferramentas/usucapiao-verificar",
    campos: [
      {
        nome: "tipo",
        label: "Modalidade",
        tipo: "select",
        obrigatorio: true,
        opcoes: [
          { value: "ordinaria", label: "Ordinária" },
          { value: "extraordinaria", label: "Extraordinária" },
          { value: "especial_urbana", label: "Especial urbana" },
          { value: "especial_rural", label: "Especial rural" },
          { value: "familiar", label: "Familiar" },
        ],
      },
      {
        nome: "anos_posse",
        label: "Anos de posse",
        tipo: "number",
        obrigatorio: true,
        min: 0,
      },
      {
        nome: "posse_mansa",
        label: "Posse mansa e pacífica",
        tipo: "boolean",
        valorPadrao: true,
      },
    ],
  },
  {
    chave: "civel-calculo-dano-moral",
    titulo: "Estruturação de dano moral",
    descricao:
      "Metodologia bifásica (STJ) — sem valor sugerido automático (tarifação vedada).",
    area: "Cível",
    endpoint: "/civel/ferramentas/calculo-dano-moral",
    campos: [
      {
        nome: "tipo_caso",
        label: "Tipo de caso",
        tipo: "select",
        valorPadrao: "negativacao_indevida",
        opcoes: [
          { value: "negativacao_indevida", label: "Negativação indevida" },
          { value: "extravio_bagagem", label: "Extravio de bagagem" },
          { value: "produto_defeituoso", label: "Produto defeituoso" },
          { value: "acidente_consumo", label: "Acidente de consumo" },
          { value: "cobranca_abusiva", label: "Cobrança abusiva" },
          { value: "outro", label: "Outro" },
        ],
      },
      {
        nome: "salarios_minimos_pedido",
        label: "Pedido pretendido (em salários mínimos)",
        tipo: "number",
        min: 0,
        valorPadrao: 0,
        ajuda: "Opcional — apenas contextualiza o pedido, não é sugestão da ferramenta.",
      },
    ],
  },
  {
    chave: "penal-prazos-processuais",
    titulo: "Prazos do processo penal",
    descricao: "Contagem em dias corridos a partir da citação (CPP art. 798).",
    area: "Penal",
    endpoint: "/penal/ferramentas/prazos-processuais",
    campos: [
      { nome: "data_citacao", label: "Data da citação", tipo: "date", obrigatorio: true },
    ],
  },
  {
    chave: "penal-verificar-anpp",
    titulo: "Elegibilidade ao ANPP",
    descricao: "Acordo de Não Persecução Penal — CPP art. 28-A.",
    area: "Penal",
    endpoint: "/penal/ferramentas/verificar-anpp",
    campos: [
      {
        nome: "pena_minima_anos",
        label: "Pena mínima cominada (anos)",
        tipo: "number",
        obrigatorio: true,
        min: 0,
      },
      {
        nome: "sem_violencia_grave_ameaca",
        label: "Infração sem violência ou grave ameaça",
        tipo: "sim_nao",
        obrigatorio: true,
      },
      {
        nome: "confissao_formal_circunstanciada",
        label: "Confissão formal e circunstanciada",
        tipo: "sim_nao",
        obrigatorio: true,
      },
      {
        nome: "reincidente",
        label: "É reincidente",
        tipo: "sim_nao",
        obrigatorio: true,
      },
      {
        nome: "conduta_criminal_habitual_reiterada_profissional",
        label: "Conduta criminal habitual/reiterada/profissional",
        tipo: "sim_nao",
        obrigatorio: true,
      },
      {
        nome: "beneficiado_anpp_transacao_sursis_5anos",
        label: "Já beneficiado com ANPP/transação/sursis nos últimos 5 anos",
        tipo: "sim_nao",
        obrigatorio: true,
      },
      {
        nome: "violencia_domestica_familiar_ou_razao_genero",
        label: "Violência doméstica/familiar ou razão de gênero",
        tipo: "sim_nao",
        obrigatorio: true,
      },
    ],
  },
];
