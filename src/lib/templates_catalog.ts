// templates_catalog.ts — Lista curada de templates de peças jurídicas.
//
// Cada template define o tipo, a área, e o systemPrompt específico para
// gerar a peça via /api/generate-minuta. Usado pela UI do Gerador para
// popular o dropdown.

import type { AreaSlug } from "@/lib/personas";

export interface TemplateDef {
  slug: string;
  nome: string;
  descricao: string;
  area: AreaSlug;
  tipoPeca: "peticao_inicial" | "contestacao" | "recurso" | "denuncia" | "habeas_corpus" | "tutela" | "embargo" | "parecer";
  campos: string[]; // campos que o formulário deve pedir
  tags: string[];
}

export const TEMPLATES: TemplateDef[] = [
  // CIVEL
  { slug: "pet-inicial-civel", nome: "Petição Inicial Cível", descricao: "Ação de cobrança, indenização ou obrigação de fazer (CPC art. 319)", area: "civil", tipoPeca: "peticao_inicial", campos: ["autor", "reu", "fatos", "pedidos", "valorCausa"], tags: ["core"] },
  { slug: "contestacao-civil", nome: "Contestação Cível", descricao: "Defesa do réu com preliminares + mérito (CPC art. 341-343)", area: "civil", tipoPeca: "contestacao", campos: ["reu", "autor", "fatosAutor", "pedidosAutor"], tags: ["core"] },
  { slug: "recurso-apelacao", nome: "Recurso de Apelação", descricao: "Apelação contra sentença (CPC art. 1.009-1.044)", area: "processo_civil", tipoPeca: "recurso", campos: ["apelante", "apelado", "sentencaRecorrida", "fundamentos"], tags: ["recurso"] },
  { slug: "tutela-urgencia", nome: "Tutela de Urgência", descricao: "Liminar inaudita altera parte (CPC art. 300-310)", area: "processo_civil", tipoPeca: "tutela", campos: ["autor", "reu", "fatos", "probabilidadeDireito", "perigoDano"], tags: ["tutela"] },
  { slug: "embargo-declaracao", nome: "Embargos de Declaração", descricao: "Esclarecimento de obscuridade/contradição (CPC art. 1.022-1.025)", area: "processo_civil", tipoPeca: "embargo", campos: ["embargante", "acordaoRecorrido", "vicioApontado"], tags: ["recurso"] },

  // CONSUMIDOR
  { slug: "pet-inicial-consumidor", nome: "Petição Inicial — Consumidor", descricao: "CDC art. 6 — direitos básicos + inversão do ônus (art. 6, VIII)", area: "consumidor", tipoPeca: "peticao_inicial", campos: ["autor", "fornecedor", "fatos", "pedidos", "valorCausa"], tags: ["consumidor"] },
  { slug: "negativacao-indevida", nome: "Ação de Negativação Indevida", descricao: "CDC art. 42, parágrafo único — repetição de indébito em dobro + dano moral", area: "consumidor", tipoPeca: "peticao_inicial", campos: ["autor", "fornecedor", "dataNegativacao", "valorDivida", "valorIndebitoPago"], tags: ["consumidor"] },
  { slug: "contestacao-consumidor", nome: "Contestação — Consumidor", descricao: "Vício do produto/serviço (CDC art. 14)", area: "consumidor", tipoPeca: "contestacao", campos: ["fornecedor", "autor", "fatosAutor"], tags: ["consumidor"] },

  // TRABALHISTA
  { slug: "pet-inicial-trabalhista", nome: "Reclamação Trabalhista", descricao: "Verbas rescisórias, horas extras, adicional (CLT art. 840)", area: "trabalhista", tipoPeca: "peticao_inicial", campos: ["reclamante", "reclamada", "periodoContrato", "funcao", "pedidos"], tags: ["trabalhista"] },
  { slug: "contestacao-trabalhista", nome: "Contestação Trabalhista", descricao: "Defesa do empregador (CLT art. 847-849)", area: "trabalhista", tipoPeca: "contestacao", campos: ["reclamada", "reclamante", "fatosAutor"], tags: ["trabalhista"] },
  { slug: "recurso-ordinario-trabalhista", nome: "Recurso Ordinário Trabalhista", descricao: "Contra sentença do Juiz do Trabalho (CLT art. 895)", area: "trabalhista", tipoPeca: "recurso", campos: ["recorrente", "recorrido", "sentencaRecorrida"], tags: ["trabalhista", "recurso"] },

  // PREVIDENCIÁRIO
  { slug: "pet-aposentadoria-invalidez", nome: "Aposentadoria por Invalidez", descricao: "Lei 8.213/91 art. 42 — incapacidade definitiva", area: "previdenciario", tipoPeca: "peticao_inicial", campos: ["autor", "inss", "dataInicioIncapacidade", "cid"], tags: ["previdenciario"] },
  { slug: "pet-bpc-loas", nome: "BPC/LOAS — Idoso ou Deficiente", descricao: "Lei 8.742/93 art. 20 — miserabilidade + deficiência/idade", area: "previdenciario", tipoPeca: "peticao_inicial", campos: ["autor", "inss", "idade", "rendaFamiliar"], tags: ["previdenciario"] },

  // PENAL
  { slug: "resposta-acusacao", nome: "Resposta à Acusação", descricao: "CPP art. 396-397 — defesa preliminar antes da instrução", area: "processo_penal", tipoPeca: "contestacao", campos: ["acusado", "denuncia", "tipificacao"], tags: ["penal"] },
  { slug: "habeas-corpus", nome: "Habeas Corpus", descricao: "CPP art. 647 — remédio constitucional contra prisão ilegal", area: "processo_penal", tipoPeca: "habeas_corpus", campos: ["paciente", "autoridadeCoatora", "fundamento"], tags: ["penal"] },
  { slug: "tribunal-juri-plenario", nome: "Sustentação Oral — Tribunal do Júri", descricao: "CPP art. 482 — alegações finais no Plenário", area: "processo_penal", tipoPeca: "parecer", campos: ["acusado", "delito", "teseDefensiva"], tags: ["penal", "juri"] },

  // TRIBUTÁRIO
  { slug: "execucao-fiscal", nome: "Embargos à Execução Fiscal", descricao: "Lei 6.830/80 art. 16 — defesa do executado", area: "tributario", tipoPeca: "contestacao", campos: ["executado", "executante", "cda", "materia"], tags: ["tributario"] },
  { slug: "mandado-seguranca", nome: "Mandado de Segurança", descricao: "Lei 12.016/09 — direito líquido certo não amparado por HC/HD", area: "tributario", tipoPeca: "peticao_inicial", campos: ["impetrante", "autoridadeCoatora", "direitoViolado"], tags: ["tributario"] },

  // ADMINISTRATIVO
  { slug: "recurso-administrativo", nome: "Recurso Administrativo", descricao: "Lei 9.784/99 art. 56-65 — reconsideração, recurso hierárquico", area: "administrativo", tipoPeca: "recurso", campos: ["recorrente", "administracao", "atoRecorrido"], tags: ["administrativo"] },

  // AMBIENTAL
  { slug: "defesa-auto-infracao", nome: "Defesa em Auto de Infração Ambiental", descricao: "Lei 9.605/98 art. 70 + Decreto 6.514/08 art. 96-112", area: "ambiental", tipoPeca: "contestacao", campos: ["autuado", "orgaoAmbiental", "autoInfracao", "dataInfracao"], tags: ["ambiental"] },
  { slug: "acao-civil-publica-ambiental", nome: "Ação Civil Pública Ambiental", descricao: "Lei 7.347/85 art. 1 — proteção do patrimônio público ambiental", area: "ambiental", tipoPeca: "peticao_inicial", campos: ["autor", "reu", "danoAmbiental"], tags: ["ambiental"] },

  // DIGITAL (LGPD/MCI)
  { slug: "pet-lgpd-vazamento", nome: "Petição — Vazamento de Dados (LGPD)", descricao: "LGPD art. 42 + CDC — dano moral coletivo/individual", area: "digital", tipoPeca: "peticao_inicial", campos: ["autor", "controlador", "dataVazamento", "dadosVazados"], tags: ["digital", "lgpd"] },
  { slug: "notificacao-lgpd", nome: "Notificação Extrajudicial — LGPD", descricao: "LGPD art. 18 — exercício de direitos do titular", area: "digital", tipoPeca: "parecer", campos: ["titular", "dadosTratados", "direitoViolado"], tags: ["digital", "lgpd"] },
];

/** Busca templates por área. */
export function templatesByArea(area: string): TemplateDef[] {
  return TEMPLATES.filter((t) => t.area === area);
}

/** Templates mais comuns (tags = "core") para destaque na home. */
export function coreTemplates(): TemplateDef[] {
  return TEMPLATES.filter((t) => t.tags.includes("core"));
}

/** Total de templates. */
export function totalTemplates(): number {
  return TEMPLATES.length;
}