// assistente.ts — Porte TS do classificador determinístico de intenção + extração de entidades
//
// Porta do backend Python:
//  - assistente/intencoes.py  → INTENCOES, PRIORIDADE, pontuar(), classificar()
//  - core/entidades.py          → extrair() com 12 categorias de entidades
//  - core/texto.py              → normalizar() (importado de @/lib/lexvalida_port)
//
// DIFERENCIAL CRÍTICO (fix vs Python original):
//  ENTIDADES SÃO SOMENTE REFORÇO — não ativam intenção sozinhas.
//  No Python, a linha `if p == 0 and not any(ent.get(e) for e in cfg.get("entidades", {}))` permitia
//  entidades dispararem intenção quando nenhum padrão batia. Isto gera ruído: palavras como "edital"
//  num texto longo sem verbo de intenção de licitação disparam "licitacao". Aqui, a regra passa a ser:
//  se pattern_score == 0 → skip (entidades só somam peso). Isto garante tie-break mais estável.
//
// Fórmula de confiança: min(1, melhor/4) * (0.6 if tie else 1)
//  - melhor/4: cap de 1.0 para 4 matches de padrão (cada padrão conta como 2 pontos)
//  - 0.6 em empate (top1 == top2 em score): penaliza ambiguidade
//
// 17 intents com pesos:
//  briefing, intimacao, prazo, redigir, processo, lei, sumula, pesquisa, verificar,
//  prescricao, intercorrente, valor_causa, licitacao, contradicoes, legislativo, jurimetria, ajuda

import { normalizar } from "@/lib/lexvalida_port";

// ─────────────────────────────────────── entidades

// Regex CNJ: 0001234-56.2024.8.26.0100 (aceita sem hífen/ponto também)
const RX_CNJ = /\b(\d{7})-?(\d{2})\.?(\d{4})\.?(\d)\.?(\d{2})\.?(\d{4})\b/g;

// Regex OAB: "OAB/SP 123456" ou "123456/SP"
const RX_OAB = /\b(?:oab\s*\/?\s*)?(\d{3,6})\s*\/\s*([A-Z]{2})\b/gi;

const MESES = [
  "janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho",
  "agosto", "setembro", "outubro", "novembro", "dezembro",
];

const RX_DATA_NUM = /\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b/g;
const RX_DATA_EXT = new RegExp(
  `\\b(\\d{1,2})(?:o|o)?\\s+de\\s+(${MESES.join("|")})(?:\\s+de\\s+(\\d{4}))?\\b`,
  "g",
);
const RX_ISO = /\b(\d{4})-(\d{2})-(\d{2})\b/g;

const NUM_EXTENSO: Record<string, number> = {
  um: 1, dois: 2, tres: 3, cinco: 5, dez: 10, quinze: 15, vinte: 20, trinta: 30,
  "quarenta e oito": 48, sessenta: 60, noventa: 90,
};

const RX_DIAS = new RegExp(
  `\\b(\\d{1,3}|${Object.keys(NUM_EXTENSO)
    .sort((a, b) => b.length - a.length)
    .join("|")})\\s*(?:\\((?:[a-z\\s]+)\\)\\s*)?dias?(\\s+(?:uteis|corridos))?`,
  "g",
);

const RX_VALOR = /r\$\s*([\d.]+(?:,\d{2})?)/gi;

const SIGLAS_LEI: Record<string, string> = {
  cpc: "cpc", cc: "cc", "codigo civil": "cc", cdc: "cdc", clt: "clt", cf: "cf", constituicao: "cf",
  cp: "cp", "codigo penal": "cp", cpp: "cpp", ctn: "ctn", eca: "eca", lindb: "lindb", lgpd: "lgpd",
  eoab: "eoab", "estatuto da advocacia": "eoab", ctb: "ctb", lef: "l6830", "lei 6.830": "l6830",
  "lei 9.099": "l9099", "lei 11.419": "l11419", "lei 14.133": "l14133", "lei 8.245": "l8245",
  "lei 12.016": "l12016", "lei 8.429": "l8429", "lei 9.784": "l9784", "lei 11.101": "l11101",
  "lei 8.213": "l8213", "lei 11.340": "l11340", "lei 11.343": "l11343", "lei 6.938": "pnma",
  "lei 9.605": "lca", "decreto 6.514": "d6514",
};

const _RX_SIGLA = Object.keys(SIGLAS_LEI)
  .sort((a, b) => b.length - a.length)
  .map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
  .join("|");

const RX_DISPOSITIVO = new RegExp(
  `\\bart(?:igo)?s?\\.?\\s*(\\d{1,4}(?:\\.\\d{3})?)\\s*(?:o|o)?(?:\\s*-\\s*([a-z]))?` +
    `(?:[^.;\\n]{0,40}?)\\b(?:d[oa]s?\\s+|,\\s*)?(${_RX_SIGLA})\\b`,
  "gi",
);

const RX_SUMULA = /\bsumula\s*(vinculante\s*)?(?:n[o.]*\s*)?(\d{1,4})\s*(?:d[oa]\s+)?(stf|stj|tst)?/gi;

const RX_TRIBUNAL = /\b(tj[a-z]{2}|trt\s?\d{1,2}|trf\s?\d|stj|stf|tst|tse)\b/gi;

const UF_LIST = "ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj rn ro rr rs sc se sp to".split(" ");

// 22 tipos de peça (especificação: ~21)
const TIPOS_PECA: { rx: RegExp; nome: string }[] = [
  { rx: /peticao inicial|\binicial\b|ajuizar|propor (?:uma )?acao|ingressar com acao/i, nome: "Petição inicial" },
  { rx: /contestacao|contestar|defesa do reu/i, nome: "Contestação" },
  { rx: /replica|impugnacao a[o] contestacao/i, nome: "Réplica" },
  { rx: /contrarrazoes/i, nome: "Contrarrazões" },
  { rx: /apelacao|apelar/i, nome: "Apelação" },
  { rx: /agravo de instrumento/i, nome: "Agravo de instrumento" },
  { rx: /agravo interno/i, nome: "Agravo interno" },
  { rx: /embargos de declaracao|embargos declaratorios/i, nome: "Embargos de declaração" },
  { rx: /recurso inominado/i, nome: "Recurso inominado" },
  { rx: /recurso especial/i, nome: "Recurso especial" },
  { rx: /recurso extraordinario/i, nome: "Recurso extraordinário" },
  { rx: /recurso ordinario/i, nome: "Recurso ordinário" },
  { rx: /mandado de seguranca/i, nome: "Mandado de segurança" },
  { rx: /tutela (?:de urgencia|antecipada|cautelar)|liminar/i, nome: "Pedido de tutela de urgência" },
  { rx: /impugnacao (?:ao |do )?edital|impugnar (?:o )?edital/i, nome: "Impugnação ao edital" },
  { rx: /recurso administrativo/i, nome: "Recurso administrativo" },
  { rx: /defesa (?:do |ao )?auto de infracao|defesa administrativa/i, nome: "Defesa administrativa" },
  { rx: /notificacao extrajudicial/i, nome: "Notificação extrajudicial" },
  { rx: /cumprimento de sentenca/i, nome: "Cumprimento de sentença" },
  { rx: /execucao de titulo/i, nome: "Execução de título extrajudicial" },
  { rx: /manifestacao|peticao simples|peticao intermediaria/i, nome: "Manifestação" },
  { rx: /parecer/i, nome: "Parecer" },
];

// 12 áreas (ordem: mais específico primeiro)
const AREAS: { termos: string[]; area: string }[] = [
  { termos: ["execucao fiscal", "divida ativa", "icms", "tributar", "imposto", "iptu", "iss "], area: "tributario" },
  { termos: ["recuperacao judicial", "falencia", "societar", "dissolucao de sociedade", "credito rural", "cedula de produto rural", "agronegocio"], area: "empresarial" },
  { termos: ["reclamatoria", "reclamacao trabalhista", "verbas rescisorias", "horas extras", "vinculo empregaticio", "aviso previo", "fgts", "trabalhist", "clt"], area: "trabalhista" },
  { termos: ["clausula penal"], area: "civil" },
  { termos: ["criminal", "penal", "inquerito", "dosimetria", "flagrante", "habeas corpus", "prisao preventiva", "anpp", "denuncia criminal"], area: "penal" },
  { termos: ["licitac", "edital", "pregao", "14.133", "contrato administrativo"], area: "licitacoes" },
  { termos: ["auto de infracao ambiental", "ibama", "tcfa", "ambiental", "licenciamento", "app ", "reserva legal"], area: "ambiental" },
  { termos: ["improbidade", "processo administrativo", "auto de infracao", "servidor publico", "administrativo"], area: "administrativo" },
  { termos: ["juizado especial", "juizados especiais", "recurso inominado", "lei 9.099", "jec"], area: "juizados" },
  { termos: ["cdc", "consumidor", "relacao de consumo", "vicio do produto", "negativacao", "cadastro de inadimplentes", "plano de saude", "negativa de cobertura", "banco", "tarifa"], area: "consumidor" },
  { termos: ["responsabilidade civil", "dano moral", "danos morais", "dano material", "cobranca", "contrato", "inadimplemento", "locacao", "despejo", "usucapiao", "posse", "alimentos", "divorcio", "inventario"], area: "civil" },
  { termos: ["previdenciar", "inss", "aposentadoria", "beneficio"], area: "previdenciario" },
];

function _ano(a: string): number {
  const y = parseInt(a, 10);
  return y < 100 ? y + 2000 : y;
}

function datas(texto: string, hoje = new Date()): string[] {
  const t = normalizar(texto);
  const out: string[] = [];
  // ISO
  RX_ISO.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = RX_ISO.exec(t)) !== null) {
    try {
      const d = new Date(Date.UTC(parseInt(m[1], 10), parseInt(m[2], 10) - 1, parseInt(m[3], 10)));
      if (!isNaN(d.getTime())) out.push(d.toISOString().slice(0, 10));
    } catch {
      // ignore
    }
  }
  // DD-MM-YYYY (ou / ou .)
  RX_DATA_NUM.lastIndex = 0;
  while ((m = RX_DATA_NUM.exec(t)) !== null) {
    try {
      const d = new Date(Date.UTC(_ano(m[3]), parseInt(m[2], 10) - 1, parseInt(m[1], 10)));
      if (!isNaN(d.getTime())) out.push(d.toISOString().slice(0, 10));
    } catch {
      // ignore
    }
  }
  // Por extenso
  RX_DATA_EXT.lastIndex = 0;
  while ((m = RX_DATA_EXT.exec(t)) !== null) {
    try {
      const ano = m[3] ? parseInt(m[3], 10) : hoje.getFullYear();
      const mes = MESES.indexOf(m[2]) + 1;
      if (mes > 0) {
        const d = new Date(Date.UTC(ano, mes - 1, parseInt(m[1], 10)));
        if (!isNaN(d.getTime())) out.push(d.toISOString().slice(0, 10));
      }
    } catch {
      // ignore
    }
  }
  // Relativas
  const hojeDate = new Date(Date.UTC(hoje.getFullYear(), hoje.getMonth(), hoje.getDate()));
  const relativas: { palavra: string; delta: number }[] = [
    { palavra: "anteontem", delta: -2 },
    { palavra: "ontem", delta: -1 },
    { palavra: "hoje", delta: 0 },
    { palavra: "amanha", delta: 1 },
  ];
  for (const { palavra, delta } of relativas) {
    const rx = new RegExp(`\\b${palavra}\\b`, "i");
    if (rx.test(t)) {
      const d = new Date(hojeDate.getTime() + delta * 86400000);
      out.push(d.toISOString().slice(0, 10));
    }
  }
  // dedup preservando ordem
  const vistos: string[] = [];
  for (const d of out) if (!vistos.includes(d)) vistos.push(d);
  return vistos;
}

export function extrairCNJ(texto: string): string[] {
  const out: string[] = [];
  const r = new RegExp(RX_CNJ.source, "g");
  let m: RegExpExecArray | null;
  while ((m = r.exec(texto || "")) !== null) {
    const n = `${m[1]}-${m[2]}.${m[3]}.${m[4]}.${m[5]}.${m[6]}`;
    if (!out.includes(n)) out.push(n);
  }
  return out;
}

export function extrairOAB(texto: string): string[] {
  const out: string[] = [];
  const r = new RegExp(RX_OAB.source, RX_OAB.flags);
  const t = texto || "";
  let m: RegExpExecArray | null;
  while ((m = r.exec(t)) !== null) {
    const uf = (m[2] || "").toUpperCase();
    if (UF_LIST.includes(uf.toLowerCase())) {
      // confere que tem "oab" no contexto próximo
      const ctx = t.slice(Math.max(0, m.index - 12), m.index + m[0].length);
      if (/oab/i.test(ctx)) {
        const oab = `${m[1]}/${uf}`;
        if (!out.includes(oab)) out.push(oab);
      }
    }
  }
  return out;
}

export interface EntidadesResult {
  cnj: string[];
  oabs: string[];
  datas: string[];
  dias: { dias: number; contagem: string | null }[];
  valores: string[];
  dispositivos: string[];
  sumulas: { numero: string; tribunal: string | null; vinculante: boolean }[];
  tribunais: string[];
  tipoPeca: string | null;
  area: string | null;
}

export function extrairEntidades(texto: string, hoje = new Date()): EntidadesResult {
  const t = normalizar(texto);
  const original = texto || "";

  // Dias
  const dias: { dias: number; contagem: string | null }[] = [];
  RX_DIAS.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = RX_DIAS.exec(t)) !== null) {
    let n: number;
    if (/^\d+$/.test(m[1])) n = parseInt(m[1], 10);
    else n = NUM_EXTENSO[m[1]] ?? 0;
    if (n > 0) dias.push({ dias: n, contagem: (m[2] || "").trim() || null });
  }

  // Valores (R$)
  const valores: string[] = [];
  RX_VALOR.lastIndex = 0;
  while ((m = RX_VALOR.exec(t)) !== null) {
    const raw = m[1].replace(/\./g, "").replace(",", ".");
    const n = parseFloat(raw);
    if (isFinite(n)) valores.push(n.toFixed(2));
  }

  // Dispositivos
  const dispositivos: string[] = [];
  RX_DISPOSITIVO.lastIndex = 0;
  while ((m = RX_DISPOSITIVO.exec(t)) !== null) {
    const num = m[1].replace(/\./g, "");
    const suf = m[2] || "";
    const lei = SIGLAS_LEI[m[3]] || m[3];
    const nid = `${lei}-art-${num}${suf ? `-${suf}` : ""}`;
    if (!dispositivos.includes(nid)) dispositivos.push(nid);
  }

  // Súmulas
  const sumulas: { numero: string; tribunal: string | null; vinculante: boolean }[] = [];
  RX_SUMULA.lastIndex = 0;
  while ((m = RX_SUMULA.exec(t)) !== null) {
    sumulas.push({
      numero: m[2],
      tribunal: (m[3] || "").toUpperCase() || null,
      vinculante: !!m[1],
    });
  }

  // Tribunais (somente TJ com UF válido)
  const tribunaisSet = new Set<string>();
  RX_TRIBUNAL.lastIndex = 0;
  while ((m = RX_TRIBUNAL.exec(t)) !== null) {
    const g = m[1].replace(/\s/g, "").toUpperCase();
    if (g.startsWith("TJ")) {
      const uf = g.slice(2);
      if (UF_LIST.includes(uf.toLowerCase())) tribunaisSet.add(g);
    } else {
      tribunaisSet.add(g);
    }
  }

  // Tipo de peça
  let tipoPeca: string | null = null;
  for (const { rx, nome } of TIPOS_PECA) {
    const r = new RegExp(rx.source, rx.flags);
    if (r.test(t)) {
      tipoPeca = nome;
      break;
    }
  }

  // Área
  let area: string | null = null;
  for (const { termos, area: a } of AREAS) {
    if (termos.some((x) => t.includes(x))) {
      area = a;
      break;
    }
  }

  return {
    cnj: extrairCNJ(original),
    oabs: extrairOAB(original),
    datas: datas(original, hoje),
    dias,
    valores,
    dispositivos,
    sumulas,
    tribunais: Array.from(tribunaisSet).sort(),
    tipoPeca,
    area,
  };
}

// ─────────────────────────────────────── Intenções

interface IntentCfg {
  descricao: string;
  padroes: RegExp[];
  entidades?: Record<string, number>;
}

const INTENCOES: Record<string, IntentCfg> = {
  briefing: {
    descricao: "Resumo do dia: prazos, alertas e pendências",
    padroes: [
      /\bo que (?:eu )?tenho\b/i,
      /resumo do dia/i,
      /\bagenda\b/i,
      /\bpendencias?\b/i,
      /prazos?\s+(?:da|desta|dessa|na)\s+semana/i,
      /\bvencendo\b|\bvencem\b|\bvence\s+(?:hoje|amanh)/i,
      /^bom dia|^boa tarde|^boa noite/i,
      /o que (?:esta|esta)\s+pendente/i,
    ],
  },
  intimacao: {
    descricao: "Registrar intimação colada e calcular o prazo",
    padroes: [
      /fica(?:m)?\b.{0,40}intimad/i,
      /\bintimacao\b.{40,}/i,
    ],
    entidades: { cnj: 1, dias: 1 },
  },
  prazo: {
    descricao: "Calcular prazo processual",
    padroes: [
      /\bprazo\b/i,
      /quando vence/i,
      /\bvencimento\b/i,
      /contar\s+(?:o\s+)?prazo/i,
      /dias\s+uteis/i,
    ],
    entidades: { dias: 2, datas: 1 },
  },
  redigir: {
    descricao: "Redigir peça com supervisão",
    padroes: [
      /\b(?:redij|redigir|elabor|minut|escrev|prepar|faca|fazer|montar|gerar?)\w*\b.{0,40}(?:peca|peti|contesta|recurso|apela|agravo|replica|embargos|inicial|manifesta|impugna|defesa|notifica|parecer|tutela|mandado)/i,
    ],
    entidades: { tipoPeca: 2 },
  },
  processo: {
    descricao: "Consultar processo no DataJud (CNJ)",
    padroes: [/\b(?:consult|andamento|movimenta|situacao do processo|como esta o processo)/i],
    entidades: { cnj: 3 },
  },
  lei: {
    descricao: "Texto de dispositivo legal",
    padroes: [/o que diz|texto d[oa]|redacao d[oa]|transcrev|me mostre o art/i],
    entidades: { dispositivos: 3 },
  },
  sumula: {
    descricao: "Súmula na base",
    padroes: [/\bsumula\b/i],
    entidades: { sumulas: 3 },
  },
  pesquisa: {
    descricao: "Pesquisa de jurisprudência e legislação",
    padroes: [/jurisprud|precedente|entendimento|\bteses?\b|pesquis|julgados?|o que os tribunais/i],
  },
  verificar: {
    descricao: "Verificar citações e riscos de um texto",
    padroes: [
      /\{\{(?:juris|lei):/i,
      /\[\[autos:/i,
      /verifi\w+\s+(?:este|esse|o)\s+texto|confir\w+\s+(?:as\s+)?cita|revis\w+\s+(?:este|esse)\s+texto/i,
    ],
  },
  prescricao: {
    descricao: "Prescrição",
    padroes: [/prescri(?:c|t)(?:ao|cional)|prescreve|prescrit/i],
  },
  intercorrente: {
    descricao: "Prescrição intercorrente",
    padroes: [/intercorrente/i],
  },
  valor_causa: {
    descricao: "Valor da causa",
    padroes: [/valor da causa/i],
    entidades: { valores: 1 },
  },
  licitacao: {
    descricao: "Licitações: impugnação, recurso e habilitação",
    padroes: [
      /\bedital\b|licita|pregao|habilitacao|impugnacao ao edital|impugnar o edital/i,
      /impugna\w*\s+(?:ao\s+|o\s+|do\s+)?edital|recurso\s+(?:na|da)\s+licita|matriz de habilita/i,
    ],
  },
  contradicoes: {
    descricao: "Contradições entre documentos do caso",
    padroes: [/contradi|inconsist|divergencia entre/i],
  },
  legislativo: {
    descricao: "Projetos de lei em tramitação",
    padroes: [
      /projetos?\s+de\s+lei|\bpls?\b\s+\d|proposicao|tramita|congresso|camara dos deputados|senado/i,
      /projetos?\s+de\s+lei|proposicoes/i,
    ],
  },
  jurimetria: {
    descricao: "Jurimetria descritiva (DataJud)",
    padroes: [/jurimetria|estatistic|quantos processos|taxa de (?:proced|acolh|sucesso)/i],
  },
  ajuda: {
    descricao: "O que o assistente faz",
    padroes: [/^ajuda|o que voce (?:faz|sabe)|como funciona|como (?:te\s+|voce\s+)?uso/i],
  },
};

// Empate: a ordem desempata (mais específico primeiro)
const PRIORIDADE: string[] = [
  "intimacao", "intercorrente", "verificar", "redigir", "lei", "sumula", "processo", "valor_causa", "legislativo",
  "licitacao", "contradicoes", "prescricao", "prazo", "jurimetria", "pesquisa", "briefing", "ajuda",
];

// Pesos (cada padrão de intenção conta como 2 pontos; entidades somam reforço)
const PESO_PADRAO = 2;
const LIMIAR_NORMALIZACAO = 4; // score 4 → confiança 1.0

interface PontosItem {
  score: number;
  intent: string;
}

function pontuar(texto: string, ent: EntidadesResult): PontosItem[] {
  const t = normalizar(texto);
  const out: PontosItem[] = [];
  for (const [nome, cfg] of Object.entries(INTENCOES)) {
    // Conta padrões que batem (cada padrão: 2 pontos)
    let p = cfg.padroes.reduce((acc, rx) => {
      const r = new RegExp(rx.source, rx.flags);
      return acc + (r.test(t) ? PESO_PADRAO : 0);
    }, 0);
    // CRÍTICO FIX: entidades são SOMENTE REFORÇO — não ativam intenção sozinhas.
    if (p === 0) continue;
    // soma reforço por entidade
    if (cfg.entidades) {
      for (const [e, peso] of Object.entries(cfg.entidades)) {
        const count = entCount(ent, e);
        if (count > 0) p += peso * count;
      }
    }
    if (p > 0) out.push({ score: p, intent: nome });
  }
  // Heurística especial: texto longo colado com "intimad" → intimação, não prazo genérico
  if ((t.length > 120 && /intimad|intimacao/i.test(t)) || /fica(?:m)?\b.{0,40}intimad/i.test(t)) {
    // força intimação com score alto
    out.splice(out.findIndex((x) => x.intent === "intimacao") + 1, 0, ...[]);
    // remove intimacao se já existe e adiciona score alto
    const idx = out.findIndex((x) => x.intent === "intimacao");
    if (idx >= 0) out[idx].score = 9;
    else out.push({ score: 9, intent: "intimacao" });
  }
  // Ordena por (-score, PRIORIDADE)
  out.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    const pa = PRIORIDADE.indexOf(a.intent);
    const pb = PRIORIDADE.indexOf(b.intent);
    return pa - pb;
  });
  return out;
}

function entCount(ent: EntidadesResult, key: string): number {
  switch (key) {
    case "cnj": return ent.cnj.length;
    case "dias": return ent.dias.length;
    case "datas": return ent.datas.length;
    case "valores": return ent.valores.length;
    case "dispositivos": return ent.dispositivos.length;
    case "sumulas": return ent.sumulas.length;
    case "tipoPeca": return ent.tipoPeca ? 1 : 0;
    default: return 0;
  }
}

export interface ClassificacaoResult {
  intencao: string | null;
  confianca: number;
  candidatas: string[];
  entidades: EntidadesResult;
}

export function classificar(texto: string): ClassificacaoResult {
  const ent = extrairEntidades(texto);
  const ps = pontuar(texto, ent);
  if (ps.length === 0) {
    return { intencao: null, confianca: 0.0, candidatas: [], entidades: ent };
  }
  const melhor = ps[0];
  const segundo = ps.length > 1 ? ps[1].score : 0;
  const conf = Math.round(Math.min(1.0, melhor.score / LIMIAR_NORMALIZACAO) * (segundo === melhor.score ? 0.6 : 1.0) * 100) / 100;
  return {
    intencao: melhor.intent,
    confianca: conf,
    candidatas: ps.slice(0, 3).map((p) => p.intent),
    entidades: ent,
  };
}

export function listarIntencoes(): Record<string, { descricao: string; entidades?: Record<string, number> }> {
  const out: Record<string, { descricao: string; entidades?: Record<string, number> }> = {};
  for (const [k, v] of Object.entries(INTENCOES)) {
    out[k] = { descricao: v.descricao, entidades: v.entidades };
  }
  return out;
}
