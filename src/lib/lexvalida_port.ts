// lexvalida_port.ts — Porte TypeScript de núcleo determinístico do LexValida
//
// Porta 5 módulos do backend Python original:
//  - core/texto.py         → semAcento(), normalizar()
//  - core/salvaguardas.py  → promessasDeResultado(), meritoPrescricao(), cdcVicioFato(), verificarSalvaguardas()
//  - core/valor_causa.py   → calcularValorCausa() (6 tipos de pedido, 3 relações)
//  - core/triagem.py        → classificarDocumento() (12 tipos) + providenciasPorTipo()
//  - core/julgador.py      → simularJulgador() (5 checklists) + tipoCanonico() + vedacaoSurpresa() (10 matérias)
//
// PRINCÍPIOS:
// - Tudo determinístico; nada delega ao LLM.
// - Regex com flag `gi` aplicada sobre texto normalizado (lowercase + sem acento).
// - `meritoPrescricao` usa [\s\S] para casar entre parágrafos.
// - `prestacoes.mesesRestantes`: null ≠ 0 (null => 12 vincendas por padrão; 0 => só vencidas).

// ─────────────────────────────────────── texto (normalização)

export function semAcento(texto: string): string {
  if (!texto) return "";
  return (texto || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, ""); // remove combining diacritics
}

export function normalizar(texto: string): string {
  return semAcento(texto || "").toLowerCase();
}

// ─────────────────────────────────────── salvaguardas

// 10 regex de "promessa de resultado" (aplicadas em texto normalizado)
const RE_PROMESSAS: RegExp[] = [
  /garant\w*\s+(?:de\s+|o\s+|a\s+)?(?:exito|resultado|vitoria|sucesso|ganho)/gi,
  /certeza\s+de\s+(?:exito|vitoria|sucesso|ganhar)/gi,
  /\b(?:vamos|iremos|vai|ira)\s+(?:certamente\s+)?ganhar\s+(?:a\s+causa|o\s+processo|a\s+acao)/gi,
  /100%\s*de\s*(?:chance|exito|certeza|sucesso)/gi,
  /(?:exito|vitoria|sucesso|resultado|ganho)\s+(?:\w+\s+){0,2}(?:garantid[oa]s?|assegurad[oa]s?)/gi,
  /(?:impossivel|nao\s+ha\s+como|nao\s+tem\s+como)\s+(?:\w+\s+){0,2}perder/gi,
  /risco\s+(?:zero|nulo|inexistente|nenhum)\s+de\s+(?:perda|perder|derrota|insucesso)/gi,
  /(?:com\s+certeza|certamente|sem\s+duvida)\s+(?:\w+\s+){0,2}(?:ganha\w*|vence\w*|ter\s+exito)/gi,
  /\d{1,3}\s*%\s*(?:\w+\s+){0,3}(?:exito|ganh\w*|vitoria|proced\w*|sucesso|provimento)/gi,
  /praticamente\s+(?:cert[oa]|garantid[oa]s?|assegurad[oa]s?|inevitave(?:l|is)|ganh\w*)/gi,
];

export function promessasDeResultado(texto: string): string[] {
  const t = normalizar(texto);
  const achados: string[] = [];
  for (const rx of RE_PROMESSAS) {
    // Recria a regex global para resetar lastIndex e evitar loop infinito
    const r = new RegExp(rx.source, rx.flags);
    let m: RegExpExecArray | null;
    while ((m = r.exec(t)) !== null) {
      achados.push(m[0].slice(0, 80));
      if (m.index === r.lastIndex) r.lastIndex++; // evita loop em match vazio
    }
  }
  return achados;
}

// ─── meritoPrescricao: trechos que qualificam prescrição/decadência como extinção SEM resolução de mérito
// CPC, art. 487, II qualifica como COM resolução de mérito — gerar alerta de correção pontual.
// CRÍTICO: usa [\s\S] para casar entre parágrafos (ao contrário do Python original).

const PD = "(?:prescri(?:c|t)(?:ao|cional)|decaden(?:c|t)(?:ial)?)"; // prescrição/decadência (em texto normalizado)
const JAN = "[\\s\\S]{0,220}?"; // gap até 220 chars (cross-paragraph)
const SEM_MERITO = "sem\\s+resolu(?:c|t)(?:ao)\\s+d[eo]\\s+m[eé]rito";
const RX_MERITO: { rx: RegExp; correcao: string; groupIdx: number }[] = [
  { rx: new RegExp(`${PD}${JAN}(${SEM_MERITO})`, "gi"), correcao: "com resolução de mérito (CPC, art. 487, II)", groupIdx: 1 },
  { rx: new RegExp(`(${SEM_MERITO})${JAN}${PD}`, "gi"), correcao: "com resolução de mérito (CPC, art. 487, II)", groupIdx: 1 },
  { rx: new RegExp(`${PD}${JAN}(art(?:igo)?\\.?\\s*485\\b)`, "gi"), correcao: "art. 487, II,", groupIdx: 1 },
  { rx: new RegExp(`(art(?:igo)?\\.?\\s*485\\b)${JAN}${PD}`, "gi"), correcao: "art. 487, II,", groupIdx: 1 },
];

const RX_NEGACAO = /\bnao\b/i;
const RX_OUTRO_485 = new RegExp(
  "ilegitimidade|ilegitim[oa]|carencia\\s+de\\s+acao|falta\\s+de\\s+interesse|" +
    "ausencia\\s+de\\s+(?:pressuposto|legitimidade|interesse)|litispendencia|coisa\\s+julgada|" +
    "perempcao|convencao\\s+de\\s+arbitragem|desistencia|abandono\\s+d[oa]\\s+(?:causa|processo)|" +
    "morte\\s+d[ea]\\s+parte|indeferimento\\s+d[ae]\\s+(?:peticao\\s+)?inicial",
  "i",
);

export interface MeritoPrescricaoAchado {
  trecho: string;
  correcao: string;
  contexto: string;
}

export function meritoPrescricao(texto: string): MeritoPrescricaoAchado[] {
  const t = normalizar(texto);
  const achados: MeritoPrescricaoAchado[] = [];
  for (const cfg of RX_MERITO) {
    const r = new RegExp(cfg.rx.source, cfg.rx.flags);
    let m: RegExpExecArray | null;
    while ((m = r.exec(t)) !== null) {
      const groupStart = m.index + (m[0].indexOf(m[cfg.groupIdx] || ""));
      const before = t.slice(Math.max(0, groupStart - 35), groupStart);
      const fullMatch = m[0] || "";
      if (RX_NEGACAO.test(before) || RX_OUTRO_485.test(fullMatch)) {
        if (m.index === r.lastIndex) r.lastIndex++;
        continue;
      }
      achados.push({
        trecho: m[cfg.groupIdx] || "",
        correcao: cfg.correcao,
        contexto: fullMatch.slice(0, 240),
      });
      if (m.index === r.lastIndex) r.lastIndex++;
    }
  }
  return achados;
}

// ─── CDC: vício (decadência, art. 26) x fato do produto/serviço (prescrição, art. 27)

const JAN_CDC = "[^\\n.]{0,160}"; // gap (não cruza parágrafo)
const RX_VICIO = "vicio\\s+(?:do\\s+|de\\s+)?(?:produto|servico)";
const RX_FATO =
  "fato\\s+(?:do\\s+|de\\s+)?(?:produto|servico)|defeito\\s+que\\s+causa(?:m)?\\s+dano|acidente\\s+de\\s+consumo";
const PRESC = "(?:prescri(?:c|t)(?:ao|cional)|prescrev\\w*)";
const DECAD = "(?:decadenc(?:i|t)\\w*|decai\\w*)";

const RX_VICIO_PRESCR = new RegExp(`(?:${RX_VICIO})${JAN_CDC}${PRESC}|${PRESC}${JAN_CDC}(?:${RX_VICIO})`, "gi");
const RX_FATO_DECAD = new RegExp(`(?:${RX_FATO})${JAN_CDC}${DECAD}|${DECAD}${JAN_CDC}(?:${RX_FATO})`, "gi");
const RX_CUMULA = new RegExp(
  "(?:conjuntamente|em\\s+conjunto|simultaneamente|sem\\s+distin(?:guir|cao)|mesmo\\s+prazo|mesmo\\s+regime)",
  "i",
);
const RX_VICIO_TEST = new RegExp(RX_VICIO, "i");
const RX_FATO_TEST = new RegExp(RX_FATO, "i");

export function cdcVicioFato(texto: string): string[] {
  const t = normalizar(texto);
  const alertas: string[] = [];
  if (RX_VICIO_PRESCR.test(t)) {
    alertas.push(
      "Vício do produto ou serviço associado a prescrição: o regime do vício é decadencial (CDC, art. 26); " +
        "prescrição de 5 anos é do fato do produto ou serviço (CDC, art. 27).",
    );
  }
  if (RX_FATO_DECAD.test(t)) {
    alertas.push(
      "Fato do produto ou serviço associado a decadência: a pretensão de reparação pelo fato prescreve " +
        "(CDC, art. 27); decadência é do vício (CDC, art. 26).",
    );
  }
  // reset lastIndex de regex globais
  const vicioTest = new RegExp(RX_VICIO_TEST.source, RX_VICIO_TEST.flags);
  const fatoTest = new RegExp(RX_FATO_TEST.source, RX_FATO_TEST.flags);
  const cumulaTest = new RegExp(RX_CUMULA.source, RX_CUMULA.flags);
  if (vicioTest.test(t) && fatoTest.test(t) && cumulaTest.test(t)) {
    alertas.push(
      "Vício e fato do produto ou serviço tratados em conjunto: fundamente separadamente cada regime " +
        "(CDC, arts. 12 a 14 e 18 a 20; prazos dos arts. 26 e 27).",
    );
  }
  return alertas;
}

export interface SalvaguardasResult {
  promessas: string[];
  meritoPrescricao: MeritoPrescricaoAchado[];
  cdc: string[];
}

export function verificarSalvaguardas(texto: string): SalvaguardasResult {
  return {
    promessas: promessasDeResultado(texto),
    meritoPrescricao: meritoPrescricao(texto),
    cdc: cdcVicioFato(texto),
  };
}

// ─────────────────────────────────────── valor da causa (CPC, art. 292)

const BASES: Record<string, string> = {
  cobranca: "CPC, art. 292, I",
  ato_juridico: "CPC, art. 292, II",
  alimentos: "CPC, art. 292, III",
  bem: "CPC, art. 292, IV",
  indenizacao: "CPC, art. 292, V",
  prestacoes: "CPC, art. 292, §§ 1º e 2º",
};

export type TipoPedido = keyof typeof BASES;
export type RelacaoPedidos = "cumulados" | "alternativos" | "subsidiarios";

export interface PedidoInput {
  tipo: TipoPedido;
  descricao?: string;
  // cobranca — aceita camelCase OU snake_case (Python original)
  principalCorrigido?: number | string;
  principal_corrigido?: number | string;
  jurosVencidos?: number | string;
  juros_vencidos?: number | string;
  penalidades?: number | string;
  // alimentos / prestacoes
  prestacaoMensal?: number | string;
  prestacao_mensal?: number | string;
  vencidas?: number;
  mesesRestantes?: number | null; // null ≠ 0: null => 12 vincendas (padrão)
  meses_restantes?: number | null;
  tempoIndeterminado?: boolean;
  tempo_indeterminado?: boolean;
  // ato_juridico / bem / indenizacao
  valor?: number | string;
}

export interface ValorCausaResult {
  valorDaCausa: string;
  memoria: string[];
  alertas: string[];
}

function toDec(v: number | string | undefined): number {
  if (v === undefined || v === null) return 0;
  const n = typeof v === "string" ? parseFloat(v.replace(/\./g, "").replace(",", ".")) : v;
  return isFinite(n) ? n : 0;
}

function fmtBRL(n: number): string {
  return n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function valorPedido(p: PedidoInput): { valor: number; linha: string } {
  const t = p.tipo;
  if (!(t in BASES)) {
    throw new Error(`Tipo de pedido inválido: ${t}. Use ${Object.keys(BASES).sort().join(", ")}`);
  }
  if (t === "cobranca") {
    // Aceita camelCase (principalCorrigido) OU snake_case (principal_corrigido, Python original)
    const principal = toDec(p.principalCorrigido ?? p.principal_corrigido);
    const juros = toDec(p.jurosVencidos ?? p.juros_vencidos);
    const penal = toDec(p.penalidades);
    const v = principal + juros + penal;
    const desc = `principal corrigido R$ ${fmtBRL(principal)} + juros vencidos R$ ${fmtBRL(juros)} + penalidades R$ ${fmtBRL(penal)}`;
    return { valor: v, linha: `${p.descricao || t}: ${desc} = R$ ${fmtBRL(v)} (${BASES[t]})` };
  }
  if (t === "alimentos") {
    const mensal = toDec(p.prestacaoMensal ?? p.prestacao_mensal);
    const v = mensal * 12;
    return { valor: v, linha: `${p.descricao || t}: 12 x R$ ${fmtBRL(mensal)} = R$ ${fmtBRL(v)} (${BASES[t]})` };
  }
  if (t === "prestacoes") {
    const mensal = toDec(p.prestacaoMensal ?? p.prestacao_mensal);
    const vencidas = p.vencidas ?? 0;
    // CRÍTICO: distinguir "null/não informado" de "0 explícito" (Task 43 fix).
    // - null/undefined => 12 vincendas (presunção anual — tempo indeterminado)
    // - 0 explícito com tempoIndeterminado=false => 0 vincendas (só vencidas)
    // - > 12 => 12 vincendas (presunção anual)
    // - 1-12 => esse número de vincendas
    const mesesInput = p.mesesRestantes ?? p.meses_restantes;
    const tempoIndet = p.tempoIndeterminado ?? p.tempo_indeterminado;
    const foiInformado = mesesInput !== undefined && mesesInput !== null;
    const indeterminado = tempoIndet === true || !foiInformado || (typeof mesesInput === "number" && mesesInput > 12);
    const vincendas = indeterminado ? 12 : (typeof mesesInput === "number" ? mesesInput : 0);
    const v = mensal * (vencidas + vincendas);
    const obs = indeterminado
      ? "1 ano: tempo indeterminado ou superior a 1 ano"
      : "soma das prestações restantes";
    return {
      valor: v,
      linha: `${p.descricao || t}: ${vencidas} vencidas + ${vincendas} vincendas (${obs}) x R$ ${fmtBRL(mensal)} = R$ ${fmtBRL(v)} (${BASES[t]})`,
    };
  }
  // ato_juridico, bem, indenizacao
  const v = toDec(p.valor);
  return { valor: v, linha: `${p.descricao || t}: valor informado = R$ ${fmtBRL(v)} (${BASES[t]})` };
}

export function calcularValorCausa(pedidos: PedidoInput[], relacao: RelacaoPedidos = "cumulados"): ValorCausaResult {
  if (!pedidos || pedidos.length === 0) {
    throw new Error("Informe ao menos um pedido.");
  }
  const valores: number[] = [];
  const memoria: string[] = [];
  for (const p of pedidos) {
    const { valor, linha } = valorPedido(p);
    valores.push(valor);
    memoria.push(linha);
  }
  let total: number;
  let regra: string;
  if (relacao === "alternativos") {
    total = Math.max(...valores);
    regra = "Pedidos alternativos: maior valor (CPC, art. 292, VII).";
  } else if (relacao === "subsidiarios") {
    total = valores[0];
    regra = "Pedidos subsidiários: valor do pedido principal (CPC, art. 292, VIII).";
  } else {
    total = valores.reduce((a, b) => a + b, 0);
    regra = "Pedidos cumulados: soma (CPC, art. 292, VI).";
  }
  memoria.push(regra);
  memoria.push(`Valor da causa: R$ ${fmtBRL(total)}.`);
  return {
    valorDaCausa: total.toFixed(2),
    memoria,
    alertas: ["O juiz corrige de ofício o valor em desacordo com o art. 292 (CPC, art. 292, § 3º)."],
  };
}

// ─────────────────────────────────────── triagem de documento

interface TipoTriagem {
  tipo: string;
  rotulo: string;
  fortes: RegExp[];
  apoio: RegExp[];
}

const TIPOS_TRIAGEM: TipoTriagem[] = [
  {
    tipo: "auto_infracao",
    rotulo: "Auto de infração",
    fortes: [/auto\s+de\s+infracao/i],
    apoio: [/ibama|autuad|multa|infracao\s+ambiental|fiscaliza/i],
  },
  {
    tipo: "edital",
    rotulo: "Edital de licitação",
    fortes: [/\bedital\b.{0,80}(pregao|licita|concorrencia)/i, /pregao\s+eletronico/i],
    apoio: [/habilitacao|proposta|sessao\s+publica|abertura/i],
  },
  {
    tipo: "acordao",
    rotulo: "Acórdão",
    fortes: [/\bacordao\b/i, /acordam\s+os/i],
    apoio: [/relator|turma|camara|desembargador|voto/i],
  },
  {
    tipo: "sentenca",
    rotulo: "Sentença",
    fortes: [
      /\bsentenca\b/i,
      /julgo\s+(?:procedente|improcedente|parcialmente)/i,
      /resolvo\s+o\s+merito/i,
      /julgo\s+extint/i,
    ],
    apoio: [/dispositivo|relatorio|fundamentacao|p\.?\s*r\.?\s*i\.?|publique-se/i],
  },
  {
    tipo: "decisao_interlocutoria",
    rotulo: "Decisão interlocutória",
    fortes: [/\bdecisao\b(?! de merito)/i, /\bdefiro\b|\bindefiro\b/i, /tutela\s+(?:de\s+urgencia|provisoria)/i],
    apoio: [/intime-se|cumpra-se/i],
  },
  {
    tipo: "citacao",
    rotulo: "Citação",
    fortes: [/\bcitacao\b/i, /fica\s+(?:o|a)\s+reu?\s+citad/i, /mandado\s+de\s+cit/i],
    apoio: [/contestar|apresentar\s+defesa|audiencia\s+de\s+concili/i],
  },
  {
    tipo: "intimacao_replica",
    rotulo: "Intimação para réplica",
    fortes: [/replica/i, /manifestar(?:-se)?\s+sobre\s+a\s+contestacao/i, /impugnacao\s+a[o]\s+contesta/i],
    apoio: [/intimad|ints intimacao/i, /intimacao/i],
  },
  {
    tipo: "intimacao",
    rotulo: "Intimação",
    fortes: [/\bintimacao\b/i, /fica(?:m)?\s+(?:a\s+parte\s+|as\s+partes\s+)?intimad/i],
    apoio: [/prazo|dias/i],
  },
  {
    tipo: "peticao_inicial",
    rotulo: "Petição inicial",
    fortes: [/excelentissim/i, /dos\s+pedidos/i, /da-se\s+a[o]\s+causa\s+o\s+valor/i],
    apoio: [/requer|dos\s+fatos|do\s+direito/i],
  },
  {
    tipo: "contestacao",
    rotulo: "Contestação",
    fortes: [/\bcontestacao\b/i, /preliminarmente/i, /impugnacao\s+especificada/i],
    apoio: [/reu|requerid/i],
  },
  {
    tipo: "contrato",
    rotulo: "Contrato",
    fortes: [/\bclausula\b/i, /contratante|contratada/i],
    apoio: [/objeto|vigencia|rescisao|foro/i],
  },
  {
    tipo: "notificacao",
    rotulo: "Notificação extrajudicial",
    fortes: [/notificacao\s+extrajudicial/i, /\bnotificante\b|\bnotificad[oa]\b/i],
    apoio: [/prazo/i],
  },
];

function ritoJec(t: string): boolean {
  return /juizado\s+especial|juizados\s+especiais|lei\s+9\.?099|\bjec\b|\bjesp\b|turma\s+recursal/i.test(t);
}

export interface TriagemResult {
  tipo: string;
  rotulo: string;
  confianca: number;
  jec: boolean;
  alternativas: string[];
}

export function classificarDocumento(texto: string): TriagemResult {
  const t = normalizar(texto).slice(0, 60000);
  const pontos: { score: number; tipo: string; rotulo: string }[] = [];
  for (const def of TIPOS_TRIAGEM) {
    const f = def.fortes.reduce((acc, rx) => acc + (rx.test(t) ? 1 : 0), 0);
    const a = def.apoio.reduce((acc, rx) => acc + (rx.test(t) ? 1 : 0), 0);
    if (f > 0) pontos.push({ score: f * 3 + a, tipo: def.tipo, rotulo: def.rotulo });
  }
  const jec = ritoJec(t);
  if (pontos.length === 0) {
    return { tipo: "outro", rotulo: "Documento", confianca: 0.0, jec, alternativas: [] };
  }
  pontos.sort((a, b) => b.score - a.score);
  const top = pontos[0];
  const segundo = pontos.length > 1 ? pontos[1].score : 0;
  const conf = Math.round(Math.min(1.0, top.score / 7) * (segundo === top.score ? 0.6 : 1.0) * 100) / 100;
  return {
    tipo: top.tipo,
    rotulo: top.rotulo,
    confianca: conf,
    jec,
    alternativas: pontos.slice(1, 3).map((p) => p.rotulo),
  };
}

export interface Providencia {
  peca: string;
  dias: number | null;
  contagem: string | null;
  base: string;
  nota: string;
}

export function providenciasPorTipo(tipo: string, jec = false): Providencia[] {
  switch (tipo) {
    case "sentenca":
      if (jec) {
        return [
          {
            peca: "Recurso inominado",
            dias: 10,
            contagem: "uteis",
            base: "Lei 9.099/1995, arts. 42 e 12-A",
            nota: "Contado da ciência da sentença; preparo em 48 horas da interposição (art. 42, § 1º).",
          },
          { peca: "Embargos de declaração", dias: 5, contagem: "uteis", base: "Lei 9.099/1995, arts. 49 e 12-A", nota: "" },
        ];
      }
      return [
        { peca: "Apelação", dias: 15, contagem: "uteis", base: "CPC, arts. 1.003, § 5º, e 1.009", nota: "" },
        { peca: "Embargos de declaração", dias: 5, contagem: "uteis", base: "CPC, art. 1.023", nota: "" },
      ];
    case "decisao_interlocutoria":
      return [
        {
          peca: "Agravo de instrumento",
          dias: 15,
          contagem: "uteis",
          base: "CPC, arts. 1.003, § 5º, e 1.015",
          nota: "Somente nas hipóteses do art. 1.015 (rol taxativo, com interpretação do STJ a conferir).",
        },
        { peca: "Embargos de declaração", dias: 5, contagem: "uteis", base: "CPC, art. 1.023", nota: "" },
      ];
    case "acordao":
      return [
        {
          peca: "Recurso especial ou extraordinário",
          dias: 15,
          contagem: "uteis",
          base: "CPC, arts. 1.003, § 5º, e 1.029",
          nota: "Exige prequestionamento e demais requisitos constitucionais.",
        },
        { peca: "Embargos de declaração", dias: 5, contagem: "uteis", base: "CPC, art. 1.023", nota: "" },
      ];
    case "citacao":
      if (jec) {
        return [
          {
            peca: "Contestação",
            dias: null,
            contagem: null,
            base: "Lei 9.099/1995",
            nota: "No juizado, a defesa é apresentada até a audiência de instrução, conforme o rito local: confira o mandado.",
          },
        ];
      }
      return [
        {
          peca: "Contestação",
          dias: 15,
          contagem: "uteis",
          base: "CPC, art. 335",
          nota: "O termo inicial depende da hipótese do art. 335 (audiência de conciliação, pedido de cancelamento ou art. 231).",
        },
      ];
    case "intimacao_replica":
      return [{ peca: "Réplica", dias: 15, contagem: "uteis", base: "CPC, arts. 350 e 351", nota: "" }];
    case "auto_infracao":
      return [
        {
          peca: "Defesa administrativa",
          dias: 20,
          contagem: "corridos",
          base: "Decreto 6.514/2008, art. 113; contagem contínua: Lei 9.784/1999, art. 66, § 2º",
          nota:
            "Infração ambiental federal, contada da ciência da autuação; prorroga-se ao primeiro dia útil (Lei 9.784/1999, art. 66, § 1º). " +
            "Órgãos estaduais e municipais seguem norma própria.",
        },
      ];
    case "edital":
      return [
        {
          peca: "Impugnação ao edital",
          dias: 3,
          contagem: "uteis_antes",
          base: "Lei 14.133/2021, art. 164",
          nota: "Até 3 dias úteis antes da abertura do certame.",
        },
      ];
    case "contestacao":
      return [
        {
          peca: "Réplica",
          dias: 15,
          contagem: "uteis",
          base: "CPC, arts. 350 e 351",
          nota: "Se a contestação trouxer fato impeditivo, modificativo ou extintivo, ou matéria do art. 337.",
        },
      ];
    default:
      return [];
  }
}

// ─────────────────────────────────────── julgador (checklists)

interface ChecklistItem {
  item: string;
  base: string;
  padroes: RegExp[];
}

const CHECKLISTS: Record<string, ChecklistItem[]> = {
  peticao_inicial: [
    {
      item: "Juízo a que é dirigida",
      base: "CPC, art. 319, I",
      padroes: [/excelentissim/i, /juizo/i, /vara/i, /juiz/i],
    },
    {
      item: "Qualificação das partes",
      base: "CPC, art. 319, II",
      padroes: [/cpf/i, /cnpj/i, /\[cpf_/i, /\[cnpj_/i, /inscrit/i, /residente|domiciliad|sede/i],
    },
    {
      item: "Fatos e fundamentos jurídicos",
      base: "CPC, art. 319, III",
      padroes: [/dos\s+fatos/i, /do\s+direito|fundamento/i],
    },
    {
      item: "Pedido com especificações",
      base: "CPC, art. 319, IV; art. 322",
      padroes: [/dos\s+pedidos|requer|pede/i],
    },
    {
      item: "Valor da causa",
      base: "CPC, art. 319, V; art. 292",
      padroes: [/valor\s+da\s+causa/i, /da-se\s+a\s+causa|da\s+se\s+a\s+causa/i],
    },
    {
      item: "Provas com que pretende demonstrar os fatos",
      base: "CPC, art. 319, VI",
      padroes: [/prova/i, /documentos?\s+anexo|em\s+anexo/i],
    },
    {
      item: "Opção pela audiência de conciliação ou mediação",
      base: "CPC, art. 319, VII; art. 334, § 5º",
      padroes: [/audiencia\s+de\s+(conciliacao|mediacao)/i, /conciliacao/i],
    },
  ],
  contestacao: [
    { item: "Preliminares (art. 337) analisadas", base: "CPC, art. 337", padroes: [/preliminar/i] },
    {
      item: "Impugnação específica dos fatos",
      base: "CPC, art. 341",
      padroes: [/impugna/i, /nao\s+procede|inveridic|contrari/i],
    },
    {
      item: "Concentração da defesa e especificação de provas",
      base: "CPC, art. 336",
      padroes: [/prova/i],
    },
    {
      item: "Pedido de improcedência ou extinção",
      base: "CPC, arts. 485 e 487",
      padroes: [/improceden|extincao|extinto/i],
    },
  ],
  sentenca: [
    {
      item: "Relatório",
      base: "CPC, art. 489, I",
      padroes: [/relatorio|e\s+o\s+relatorio|relatados/i],
    },
    { item: "Fundamentação", base: "CPC, art. 489, II", padroes: [/fundament|decido|passo\s+a\s+decidir/i] },
    {
      item: "Dispositivo",
      base: "CPC, art. 489, III",
      padroes: [/julgo|ante\s+o\s+exposto|isto\s+posto|dispositivo/i],
    },
    {
      item: "Honorários e custas",
      base: "CPC, arts. 82, § 2º, e 85",
      padroes: [/honorario/i, /custas/i],
    },
  ],
  recurso: [
    { item: "Tempestividade demonstrada", base: "CPC, art. 1.003, § 5º", padroes: [/tempestiv/i] },
    {
      item: "Preparo ou justiça gratuita",
      base: "CPC, art. 1.007",
      padroes: [/preparo|custas\s+recursais|justica\s+gratuita|gratuidade/i],
    },
    {
      item: "Razões e pedido de reforma ou anulação",
      base: "CPC, art. 1.010, III e IV",
      padroes: [/reform|anula/i],
    },
    {
      item: "Impugnação específica dos fundamentos da decisão (dialeticidade)",
      base: "CPC, art. 932, III",
      padroes: [/fundamento\s+d[ao]\s+(sentenca|decisao)|a\s+decisao\s+recorrida|a\s+sentenca\s+recorrida/i],
    },
  ],
  tutela_urgencia: [
    {
      item: "Probabilidade do direito demonstrada",
      base: "CPC, art. 300, caput",
      padroes: [/probabilidade\s+do\s+direito|fumus\s+boni\s+iuris|verossimilhanca/i],
    },
    {
      item: "Perigo de dano ou risco ao resultado útil do processo",
      base: "CPC, art. 300, caput",
      padroes: [/perigo\s+de\s+dano|risco\s+ao\s+resultado\s+util|periculum\s+in\s+mora/i],
    },
    {
      item: "Reversibilidade dos efeitos (ou justificativa da exceção)",
      base: "CPC, art. 300, § 3º",
      padroes: [/reversib|irreversib/i],
    },
    {
      item: "Caução ou dispensa fundamentada",
      base: "CPC, art. 300, § 1º",
      padroes: [/caucao|hipossuficien|dispensa\s+de\s+caucao/i],
    },
    {
      item: "Pedido específico da medida e prazo para cumprimento",
      base: "CPC, arts. 297 e 536",
      padroes: [/requer.{0,80}(tutela|liminar)|(tutela|liminar).{0,80}(determin|ordenar)/i],
    },
  ],
};

const ALIASES: { chave: string; canon: string }[] = [
  { chave: "tutela", canon: "tutela_urgencia" },
  { chave: "liminar", canon: "tutela_urgencia" },
  { chave: "contestacao", canon: "contestacao" },
  { chave: "defesa", canon: "contestacao" },
  { chave: "apelacao", canon: "recurso" },
  { chave: "recurso", canon: "recurso" },
  { chave: "agravo", canon: "recurso" },
  { chave: "embargos", canon: "recurso" },
  { chave: "sentenca", canon: "sentenca" },
  { chave: "decisao", canon: "sentenca" },
  { chave: "peticao inicial", canon: "peticao_inicial" },
  { chave: "inicial", canon: "peticao_inicial" },
  { chave: "acao", canon: "peticao_inicial" },
];

export function tipoCanonico(tipoPeca: string): string | null {
  const t = normalizar(tipoPeca);
  for (const { chave, canon } of ALIASES) {
    const r = new RegExp(`\\b${chave}\\b`, "i");
    if (r.test(t)) return canon;
  }
  return null;
}

export interface ChecklistResultItem {
  item: string;
  base: string;
  atendido: boolean;
}

export interface JulgadorResult {
  tipo: string;
  checklist: ChecklistResultItem[];
  pendencias: string[];
  nota: string;
}

export function simularJulgador(texto: string, tipoPeca: string): JulgadorResult {
  const canon = tipoCanonico(tipoPeca);
  if (!canon) {
    return {
      tipo: tipoPeca,
      checklist: [],
      pendencias: [],
      nota: "Sem checklist estrutural cadastrado para este tipo de peça.",
    };
  }
  const t = normalizar(texto);
  const itens: ChecklistResultItem[] = [];
  const pend: string[] = [];
  for (const c of CHECKLISTS[canon]) {
    const ok = c.padroes.some((rx) => rx.test(t));
    itens.push({ item: c.item, base: c.base, atendido: ok });
    if (!ok) pend.push(`${c.item} (${c.base}) não identificado.`);
  }
  return {
    tipo: canon,
    checklist: itens,
    pendencias: pend,
    nota: "Checagem estrutural por presença de elementos; exige revisão humana.",
  };
}

export function listarChecklists(): Record<string, { item: string; base: string }[]> {
  const out: Record<string, { item: string; base: string }[]> = {};
  for (const [k, items] of Object.entries(CHECKLISTS)) {
    out[k] = items.map((c) => ({ item: c.item, base: c.base }));
  }
  return out;
}

// ─────────────────────────────────────── vedação à decisão surpresa (CPC arts. 9º e 10)

const MATERIAS_OFICIO: Record<string, { padrao: string; base: string }> = {
  prescricao: { padrao: "prescri", base: "CPC, art. 487, parágrafo único" },
  decadencia: { padrao: "decaden", base: "CPC, art. 487, parágrafo único" },
  ilegitimidade: { padrao: "ilegitimidade|legitimidade ad causam", base: "CPC, art. 485, VI e § 3º" },
  interesse_processual: { padrao: "falta de interesse|ausencia de interesse", base: "CPC, art. 485, VI e § 3º" },
  incompetencia_absoluta: { padrao: "incompetencia absoluta", base: "CPC, art. 64, § 1º" },
  coisa_julgada: { padrao: "coisa julgada", base: "CPC, art. 485, V e § 3º" },
  litispendencia: { padrao: "litispendencia", base: "CPC, art. 485, V e § 3º" },
  perempcao: { padrao: "perempcao", base: "CPC, art. 485, V" },
  inepcia: { padrao: "inepcia|inepta", base: "CPC, art. 330, I" },
  nulidade_absoluta: { padrao: "nulidade absoluta", base: "CPC, art. 10" },
};

export interface VedacaoSurpresaAchado {
  materia: string;
  base: string;
  mensagem: string;
}

export interface VedacaoSurpresaResult {
  achados: VedacaoSurpresaAchado[];
  nota: string;
}

export function vedacaoSurpresa(textoDecisao: string, textoAutos: string): VedacaoSurpresaResult {
  const dec = normalizar(textoDecisao);
  const aut = normalizar(textoAutos);
  const achados: VedacaoSurpresaAchado[] = [];
  for (const [nome, cfg] of Object.entries(MATERIAS_OFICIO)) {
    const rx = new RegExp(cfg.padrao, "i");
    const rxAut = new RegExp(cfg.padrao, "i");
    if (rx.test(dec) && !rxAut.test(aut)) {
      achados.push({
        materia: nome,
        base: cfg.base,
        mensagem: `Fundamento '${nome}' não consta dos autos: verificar oportunidade prévia de manifestação (CPC, arts. 9º e 10).`,
      });
    }
  }
  return {
    achados,
    nota: "Indício a conferir; ressalvada a improcedência liminar (CPC, art. 332, § 1º).",
  };
}
