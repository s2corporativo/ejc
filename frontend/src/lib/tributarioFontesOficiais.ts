export type TipoFonteTributaria =
  | "portal"
  | "servico_autenticado"
  | "legislacao"
  | "nfse"
  | "dados_abertos"
  | "tribunal";

export type StatusFonteTributaria =
  | "verificada"
  | "integracao_ejc"
  | "parcial";

export type FonteTributariaOficial = {
  id: string;
  nome: string;
  esfera: "Federal" | "Minas Gerais" | "Municipal" | "Nacional" | "Judicial";
  tipo: TipoFonteTributaria;
  status: StatusFonteTributaria;
  url?: string;
  municipio?: string;
  observacao: string;
  apiPublica: boolean;
};

/**
 * Catálogo de fontes tributárias oficiais exibidas no workspace.
 *
 * Regra arquitetural: portal/site autenticado NÃO é chamado de API. `apiPublica`
 * só pode ser true quando houver contrato público verificável. Integrações reais
 * do backend continuam governadas pelo gateway `/api/integracoes/*` e feature flags.
 *
 * Data-base de verificação manual: 06/09/2026.
 */
export const FONTES_TRIBUTARIAS_OFICIAIS: readonly FonteTributariaOficial[] = [
  {
    id: "receita-servicos",
    nome: "Receita Federal — Serviços",
    esfera: "Federal",
    tipo: "portal",
    status: "verificada",
    url: "https://www.gov.br/receitafederal/pt-br/servicos",
    observacao: "Portal oficial de serviços tributários federais; acesso a serviços pode exigir gov.br/e-CAC.",
    apiPublica: false,
  },
  {
    id: "pgfn-regularize",
    nome: "PGFN — REGULARIZE",
    esfera: "Federal",
    tipo: "servico_autenticado",
    status: "verificada",
    url: "https://www.regularize.pgfn.gov.br/",
    observacao: "Portal oficial para dívida ativa e negociações. Não confundir com a integração separada de PGFN Dados Abertos já existente no EJC.",
    apiPublica: false,
  },
  {
    id: "pgfn-dados-abertos",
    nome: "PGFN — Dados Abertos",
    esfera: "Federal",
    tipo: "dados_abertos",
    status: "integracao_ejc",
    observacao: "Integração real já implementada no gateway do EJC para descoberta de recursos bulk; não faz consulta individual autenticada de CPF/CNPJ.",
    apiPublica: true,
  },
  {
    id: "carf",
    nome: "CARF",
    esfera: "Federal",
    tipo: "portal",
    status: "verificada",
    url: "https://www.gov.br/carf/pt-br",
    observacao: "Fonte institucional para regimento, jurisprudência e informações do contencioso administrativo federal.",
    apiPublica: false,
  },
  {
    id: "sef-mg",
    nome: "SEF/MG",
    esfera: "Minas Gerais",
    tipo: "portal",
    status: "verificada",
    url: "https://www.fazenda.mg.gov.br/",
    observacao: "Portal oficial da Secretaria de Estado de Fazenda de Minas Gerais.",
    apiPublica: false,
  },
  {
    id: "siare-mg",
    nome: "SIARE/MG",
    esfera: "Minas Gerais",
    tipo: "servico_autenticado",
    status: "verificada",
    url: "https://www2.fazenda.mg.gov.br/sol/",
    observacao: "Ambiente oficial de serviços tributários estaduais; operações dependem de autenticação e regras próprias.",
    apiPublica: false,
  },
  {
    id: "trf6",
    nome: "TRF6",
    esfera: "Judicial",
    tipo: "tribunal",
    status: "verificada",
    url: "https://portal.trf6.jus.br/",
    observacao: "Justiça Federal da 6ª Região, competente sobre Minas Gerais.",
    apiPublica: false,
  },
  {
    id: "nfse-nacional",
    nome: "NFS-e Nacional",
    esfera: "Nacional",
    tipo: "nfse",
    status: "verificada",
    url: "https://www.nfse.gov.br/EmissorNacional/",
    observacao: "Emissor Nacional; adesão, obrigatoriedade e cronograma devem ser conferidos por ente/regime.",
    apiPublica: false,
  },

  // ── Betim ────────────────────────────────────────────────────────────────
  {
    id: "betim-servicos",
    nome: "Betim — Serviços Online",
    esfera: "Municipal",
    municipio: "Betim",
    tipo: "portal",
    status: "verificada",
    url: "https://www.betim.mg.gov.br/portal/servicos_online/",
    observacao: "Central oficial com Dívida Ativa, taxas, IPTU, ITBI, NFS-e, protocolo e serviços fazendários.",
    apiPublica: false,
  },
  {
    id: "betim-dte",
    nome: "Betim — DTE",
    esfera: "Municipal",
    municipio: "Betim",
    tipo: "servico_autenticado",
    status: "verificada",
    url: "https://servicos.betim.mg.gov.br/appsgi/servlet/wlogin",
    observacao: "Canal oficial de comunicações tributárias municipais; a Prefeitura informa possibilidade de impugnação de lançamentos pelo sistema.",
    apiPublica: false,
  },
  {
    id: "betim-nfse",
    nome: "Betim — NFS-e 2026",
    esfera: "Municipal",
    municipio: "Betim",
    tipo: "nfse",
    status: "verificada",
    url: "https://www.betim.mg.gov.br/nota-fiscal-eletronica-2026",
    observacao: "Orientação municipal vigente para cadastro e emissão via padrão/emissor nacional.",
    apiPublica: false,
  },

  // ── Contagem ─────────────────────────────────────────────────────────────
  {
    id: "contagem-receita",
    nome: "Contagem — Receita Municipal",
    esfera: "Municipal",
    municipio: "Contagem",
    tipo: "portal",
    status: "verificada",
    url: "https://receita.contagem.mg.gov.br/",
    observacao: "Portal oficial com ISS, ITBI, IPTU, certidões, protocolos, NFS-e, legislação e serviços tributários.",
    apiPublica: false,
  },
  {
    id: "contagem-contac",
    nome: "Contagem — CONTAC",
    esfera: "Municipal",
    municipio: "Contagem",
    tipo: "legislacao",
    status: "verificada",
    url: "https://receita.contagem.mg.gov.br/contac/",
    observacao: "Conselho Tributário Administrativo de Contagem, segunda instância administrativa municipal.",
    apiPublica: false,
  },
  {
    id: "contagem-nfse",
    nome: "Contagem — NFS-e / ISS Digital",
    esfera: "Municipal",
    municipio: "Contagem",
    tipo: "nfse",
    status: "verificada",
    url: "https://receita.contagem.mg.gov.br/nfe/",
    observacao: "Portal oficial de NFS-e/declaração de serviços; informa ambiente de testes para webservices alinhados ao padrão nacional.",
    apiPublica: false,
  },

  // ── Belo Horizonte ───────────────────────────────────────────────────────
  {
    id: "bh-sisdram",
    nome: "Belo Horizonte — SISDRAM",
    esfera: "Municipal",
    municipio: "Belo Horizonte",
    tipo: "portal",
    status: "verificada",
    url: "https://prefeitura.pbh.gov.br/fazenda/sisdram",
    observacao: "Sistema unificado para guias, débitos e parcelamentos municipais, com funções identificadas e não identificadas.",
    apiPublica: false,
  },
  {
    id: "bh-bhiss",
    nome: "Belo Horizonte — BHISS Digital",
    esfera: "Municipal",
    municipio: "Belo Horizonte",
    tipo: "nfse",
    status: "verificada",
    url: "https://bhissdigital.pbh.gov.br/",
    observacao: "Ambiente oficial da Fazenda municipal para NFS-e e obrigações relacionadas ao ISS.",
    apiPublica: false,
  },

  // ── Igarapé ──────────────────────────────────────────────────────────────
  {
    id: "igarape-dte",
    nome: "Igarapé — Portal do Contribuinte / DTE",
    esfera: "Municipal",
    municipio: "Igarapé",
    tipo: "servico_autenticado",
    status: "verificada",
    url: "https://dte.igarape.mg.gov.br/",
    observacao: "Portal oficial municipal que referencia CND, IPTU, protocolo, ITBI, NFS-e, Código Tributário e DTE.",
    apiPublica: false,
  },
  {
    id: "igarape-nfse",
    nome: "Igarapé — NFS-e",
    esfera: "Municipal",
    municipio: "Igarapé",
    tipo: "nfse",
    status: "verificada",
    url: "https://igarape.quasar.srv.br/",
    observacao: "Sistema de NFS-e apontado pelo portal oficial do Município; serviço de terceiro referenciado oficialmente, não API pública do EJC.",
    apiPublica: false,
  },

  // ── São Joaquim de Bicas ────────────────────────────────────────────────
  {
    id: "sao-joaquim-bicas-contribuinte",
    nome: "São Joaquim de Bicas — Área do Contribuinte",
    esfera: "Municipal",
    municipio: "São Joaquim de Bicas",
    tipo: "portal",
    status: "parcial",
    observacao: "A Prefeitura registra oficialmente que CND municipal pode ser obtida na aba do contribuinte, mas o endpoint operacional atual não foi localizado com segurança na verificação de 06/09/2026. Não habilitar automação até nova validação.",
    apiPublica: false,
  },
] as const;

export function fontesMunicipais(municipio?: string): FonteTributariaOficial[] {
  return FONTES_TRIBUTARIAS_OFICIAIS.filter(
    (fonte) =>
      fonte.esfera === "Municipal" &&
      (!municipio || fonte.municipio === municipio),
  );
}

export function fontesComAcessoExterno(): FonteTributariaOficial[] {
  return FONTES_TRIBUTARIAS_OFICIAIS.filter(
    (fonte) => fonte.status !== "parcial" && Boolean(fonte.url),
  );
}
