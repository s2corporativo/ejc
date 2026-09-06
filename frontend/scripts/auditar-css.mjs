#!/usr/bin/env node
/**
 * Auditor de CSS órfão do EJC.
 *
 * Cruza o vocabulário de classes realmente presente no código-fonte
 * (JSX/TS + index.html) com os seletores declarados nas camadas CSS e
 * relata as regras que nenhum elemento pode alcançar.
 *
 * É deliberadamente conservador: uma regra só é considerada órfã quando
 * NENHUM dos seletores da lista é alcançável, e qualquer construção
 * dinâmica de classe (`ejc-${x}`) preserva o prefixo correspondente.
 *
 * Uso:
 *   node scripts/auditar-css.mjs              # relatório legível
 *   node scripts/auditar-css.mjs --json       # saída estruturada
 *   node scripts/auditar-css.mjs --verificar  # falha se houver regressão
 *                                             # acima do teto registrado
 */
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const raiz = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DIR_FONTE = path.join(raiz, "src");
const TETO = path.join(raiz, "scripts", "css-orfao-teto.json");

const EXT_FONTE = new Set([".ts", ".tsx", ".js", ".jsx", ".html"]);

function listar(dir, filtro, acc = []) {
  for (const nome of readdirSync(dir)) {
    const alvo = path.join(dir, nome);
    const info = statSync(alvo);
    if (info.isDirectory()) listar(alvo, filtro, acc);
    else if (filtro(alvo)) acc.push(alvo);
  }
  return acc;
}

/** Remove comentários `/* *​/` preservando o comprimento em linhas. */
function semComentarios(css) {
  return css.replace(/\/\*[\s\S]*?\*\//g, (bloco) =>
    bloco.replace(/[^\n]/g, " "),
  );
}

/**
 * Vocabulário de classes: todo literal de string do código-fonte é
 * quebrado em tokens. Cobre `className="a b"`, `cn("a", cond && "b")`,
 * mapas de variantes e atributos de HTML.
 */
function coletarVocabulario() {
  const classes = new Set();
  const prefixosDinamicos = new Set();
  const arquivos = [
    ...listar(DIR_FONTE, (a) => EXT_FONTE.has(path.extname(a))),
    ...["index.html"]
      .map((a) => path.join(raiz, a))
      .filter((a) => existsSync(a)),
  ];

  for (const arquivo of arquivos) {
    const texto = readFileSync(arquivo, "utf8");
    // Literais de string e template.
    const literais = texto.match(
      /"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`/gs,
    );
    if (!literais) continue;
    for (const bruto of literais) {
      const corpo = bruto.slice(1, -1);
      // Interpolação: `prefixo-${x}` mantém "prefixo-" como dinâmico.
      for (const [, prefixo] of corpo.matchAll(/([A-Za-z][\w-]*[-_])\$\{/g)) {
        prefixosDinamicos.add(prefixo);
      }
      for (const token of corpo.split(/[\s{}$]+/)) {
        if (/^[A-Za-z][\w-]*$/.test(token)) classes.add(token);
      }
    }
  }
  return { classes, prefixosDinamicos };
}

/** Extrai as regras (seletor + intervalo de linhas) de uma folha CSS. */
function extrairRegras(css) {
  const limpo = semComentarios(css);
  const regras = [];
  let profundidade = 0;
  let inicioSeletor = 0;
  let linha = 1;
  const pilha = [];

  for (let i = 0; i < limpo.length; i += 1) {
    const c = limpo[i];
    if (c === "\n") linha += 1;
    if (c === "{") {
      const seletor = limpo.slice(inicioSeletor, i).trim();
      pilha.push({ seletor, linhaInicio: linha, profundidade });
      profundidade += 1;
      inicioSeletor = i + 1;
    } else if (c === "}") {
      profundidade -= 1;
      const bloco = pilha.pop();
      if (bloco && bloco.seletor && !bloco.seletor.startsWith("@")) {
        regras.push({
          seletor: bloco.seletor.replace(/\s+/g, " "),
          linhaInicio: bloco.linhaInicio,
          linhaFim: linha,
        });
      }
      inicioSeletor = i + 1;
    } else if (c === ";" && profundidade === 0) {
      inicioSeletor = i + 1;
    }
  }
  return regras;
}

/** Classes citadas por um seletor simples (sem vírgulas). */
function classesDoSeletor(seletor) {
  return [...seletor.matchAll(/\.(-?[A-Za-z_][\w-]*)/g)].map((m) => m[1]);
}

function alcancavel(seletor, vocab) {
  const classes = classesDoSeletor(seletor);
  // Seletor sem classe (elemento, :root, [attr]) é sempre considerado vivo.
  if (classes.length === 0) return true;
  return classes.every(
    (c) =>
      vocab.classes.has(c) ||
      [...vocab.prefixosDinamicos].some((p) => c.startsWith(p)),
  );
}

function auditar() {
  const vocab = coletarVocabulario();
  const folhas = listar(DIR_FONTE, (a) => path.extname(a) === ".css").sort();

  const relatorio = [];
  for (const folha of folhas) {
    const css = readFileSync(folha, "utf8");
    const totalLinhas = css.split("\n").length;
    const regras = extrairRegras(css);
    const orfas = regras.filter(
      (r) => !r.seletor.split(",").some((s) => alcancavel(s.trim(), vocab)),
    );
    const linhasOrfas = orfas.reduce(
      (soma, r) => soma + (r.linhaFim - r.linhaInicio + 1),
      0,
    );
    relatorio.push({
      arquivo: path.relative(raiz, folha),
      totalLinhas,
      totalRegras: regras.length,
      regrasOrfas: orfas.length,
      linhasOrfas,
      percentual: regras.length
        ? Math.round((orfas.length / regras.length) * 100)
        : 0,
      amostra: orfas.slice(0, 8).map((r) => r.seletor),
    });
  }
  return relatorio;
}

const args = new Set(process.argv.slice(2));
const relatorio = auditar();

if (args.has("--vivas")) {
  const alvo = process.argv.slice(2).find((a) => !a.startsWith("--"));
  const vocab = coletarVocabulario();
  const folhas = listar(DIR_FONTE, (a) => path.extname(a) === ".css").sort();
  for (const folha of folhas) {
    const rel = path.relative(raiz, folha);
    if (alvo && !rel.includes(alvo)) continue;
    const regras = extrairRegras(readFileSync(folha, "utf8"));
    const vivas = regras.filter((r) =>
      r.seletor.split(",").some((s) => alcancavel(s.trim(), vocab)),
    );
    console.log(`\n# ${rel} — ${vivas.length} regras vivas`);
    for (const r of vivas)
      console.log(`  L${r.linhaInicio}-${r.linhaFim}  ${r.seletor}`);
  }
  process.exit(0);
}

if (args.has("--json")) {
  console.log(JSON.stringify(relatorio, null, 2));
  process.exit(0);
}

if (args.has("--verificar")) {
  if (!existsSync(TETO)) {
    console.error(
      `Teto ausente: ${path.relative(raiz, TETO)}. Rode sem --verificar e registre o teto.`,
    );
    process.exit(1);
  }
  const teto = JSON.parse(readFileSync(TETO, "utf8"));
  let falhou = false;
  for (const item of relatorio) {
    const limite = teto[item.arquivo];
    if (limite === undefined) {
      console.error(`FALTA TETO  ${item.arquivo} (órfãs=${item.regrasOrfas})`);
      falhou = true;
    } else if (item.regrasOrfas > limite) {
      console.error(
        `REGRESSÃO   ${item.arquivo}: ${item.regrasOrfas} regras órfãs (teto ${limite})`,
      );
      falhou = true;
    }
  }
  for (const arquivo of Object.keys(teto)) {
    if (!relatorio.some((r) => r.arquivo === arquivo)) {
      console.error(`TETO OBSOLETO ${arquivo} — arquivo não existe mais.`);
      falhou = true;
    }
  }
  if (falhou) process.exit(1);
  console.log("CSS órfão dentro do teto registrado.");
  process.exit(0);
}

const totalOrfas = relatorio.reduce((s, r) => s + r.linhasOrfas, 0);
const total = relatorio.reduce((s, r) => s + r.totalLinhas, 0);
console.log("Auditoria de CSS órfão — EJC\n");
console.log(
  `${"arquivo".padEnd(44)}${"linhas".padStart(8)}${"regras".padStart(8)}${"órfãs".padStart(8)}${"%".padStart(6)}`,
);
console.log("-".repeat(74));
for (const r of relatorio) {
  console.log(
    `${r.arquivo.replace("src/", "").padEnd(44)}${String(r.totalLinhas).padStart(8)}${String(r.totalRegras).padStart(8)}${String(r.regrasOrfas).padStart(8)}${String(r.percentual).padStart(5)}%`,
  );
}
console.log("-".repeat(74));
console.log(
  `total: ${total} linhas de CSS, ~${totalOrfas} linhas em regras inalcançáveis.\n`,
);
for (const r of relatorio.filter((x) => x.percentual >= 50)) {
  console.log(
    `# ${r.arquivo} (${r.percentual}% órfão) — ex.: ${r.amostra.slice(0, 4).join(" | ")}`,
  );
}
