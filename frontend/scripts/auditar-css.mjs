#!/usr/bin/env node
/**
 * Auditor conservador de CSS do EJC.
 *
 * Objetivos:
 * 1) medir regras customizadas potencialmente órfãs;
 * 2) impedir que novas "camadas finais" globais sejam adicionadas ao main.tsx;
 * 3) garantir que os tokens canônicos --ejc-* continuem sendo a última camada;
 * 4) impedir comentário de cabeçalho com `\n` literal, que engole o arquivo.
 *
 * A detecção de órfãos é apenas informativa: classes montadas dinamicamente podem
 * gerar falso positivo. O gate bloqueante atua sobre a governança das camadas
 * globais, sobre a ordem do cascade e sobre comentários quebrados, que são
 * determinísticos.
 */
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SRC = path.join(ROOT, "src");
const GOVERNANCE = path.join(ROOT, "scripts", "css-governance.json");
const MAIN = path.join(SRC, "main.tsx");
const SOURCE_EXT = new Set([".ts", ".tsx", ".js", ".jsx", ".html"]);

function walk(dir, predicate, acc = []) {
  for (const name of readdirSync(dir)) {
    const target = path.join(dir, name);
    const info = statSync(target);
    if (info.isDirectory()) walk(target, predicate, acc);
    else if (predicate(target)) acc.push(target);
  }
  return acc;
}

function stripComments(css) {
  return css.replace(/\/\*[\s\S]*?\*\//g, (block) =>
    block.replace(/[^\n]/g, " "),
  );
}

/**
 * Defeito de CSS observado em 28/09/2026: uma quebra de linha escrita como dois
 * caracteres (barra invertida + n) no lugar do byte 0x0A. O navegador passa a
 * ler o restante como parte do texto do comentário ou como parte do nome do
 * seletor, e a regra desaparece sem erro de build, lint ou teste. O sintoma
 * visto na produção foi um bloco inteiro de tema tratado como comentário.
 *
 * A verificação cobre as duas posições: entre o início e o fim de um comentário
 * (comentário que nunca fecha) e imediatamente depois do fim de um comentário
 * normal (seletor contaminado). Este comentário descreve o defeito sem escrever
 * a sequência, porque o detector a encontraria aqui.
 */
function newlinesEscapados(css) {
  const achados = [];
  const abertura = /\/\*/g;
  let m;
  while ((m = abertura.exec(css)) !== null) {
    const fim = css.indexOf("*/", m.index + 2);
    if (fim === -1) {
      achados.push({ index: m.index, trecho: css.slice(m.index, m.index + 60) });
      break;
    }
    // Entre início e fecho: barra invertida + n (ou r) no corpo do comentário.
    if (/[\\][nr]/.test(css.slice(m.index + 2, fim))) {
      achados.push({ index: m.index, trecho: css.slice(m.index, m.index + 60) });
    }
    // Logo depois do fecho, sem quebra: seletor que começa com barra + n.
    const depois = css.slice(fim + 2);
    const branco = depois.match(/^\s*/)[0].length;
    if (branco === 0 && depois.startsWith("\\")) {
      achados.push({ index: m.index, trecho: css.slice(m.index, m.index + 60) });
    }
    abertura.lastIndex = fim + 2;
  }
  // Comentário sem fecho: o último início é maior que o último fim.
  if (css.lastIndexOf("/*") > css.lastIndexOf("*/")) {
    const i = css.lastIndexOf("/*");
    achados.push({ index: i, trecho: css.slice(i, i + 60) });
  }
  // Sequência fora de comentário, no início de uma linha: quebra de linha
  // escrita à mão no lugar do byte 0x0A. No regex, a barra invertida precisa
  // de duas barras para casar o caractere de barra.
  const linhaEscapada = /^[^\S\n]*\\[nr](?=[^\S\n]*$)/gm;
  for (const linha of css.matchAll(linhaEscapada)) {
    achados.push({ index: linha.index, trecho: JSON.stringify(linha[0]) });
  }
  return achados;
}

function collectVocabulary() {
  const classes = new Set();
  const dynamicPrefixes = new Set();
  const files = [
    ...walk(SRC, (f) => SOURCE_EXT.has(path.extname(f))),
    path.join(ROOT, "index.html"),
  ].filter((f) => existsSync(f));

  for (const file of files) {
    const text = readFileSync(file, "utf8");
    const literals = text.match(
      /"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|\`(?:[^\`\\\n]|\\.)*\`/gs,
    );
    if (!literals) continue;
    for (const raw of literals) {
      const body = raw.slice(1, -1);
      for (const match of body.matchAll(/([A-Za-z][\w-]*[-_])\$\{/g)) {
        dynamicPrefixes.add(match[1]);
      }
      for (const token of body.split(/[\s{}$]+/)) {
        if (/^[A-Za-z][\w-]*$/.test(token)) classes.add(token);
      }
    }
  }
  return { classes, dynamicPrefixes };
}

function extractRules(css) {
  const clean = stripComments(css);
  const rules = [];
  let depth = 0;
  let selectorStart = 0;
  let line = 1;
  const stack = [];

  for (let i = 0; i < clean.length; i += 1) {
    const c = clean[i];
    if (c === "\n") line += 1;
    if (c === "{") {
      const selector = clean.slice(selectorStart, i).trim();
      stack.push({ selector, lineStart: line, depth });
      depth += 1;
      selectorStart = i + 1;
    } else if (c === "}") {
      depth -= 1;
      const block = stack.pop();
      if (block?.selector && !block.selector.startsWith("@")) {
        rules.push({
          selector: block.selector.replace(/\s+/g, " "),
          lineStart: block.lineStart,
          lineEnd: line,
        });
      }
      selectorStart = i + 1;
    } else if (c === ";" && depth === 0) {
      selectorStart = i + 1;
    }
  }
  return rules;
}

function selectorClasses(selector) {
  return [...selector.matchAll(/\.(-?[A-Za-z_][\w-]*)/g)].map((m) => m[1]);
}

function reachable(selector, vocabulary) {
  const classes = selectorClasses(selector);
  if (classes.length === 0) return true;
  return classes.every(
    (className) =>
      vocabulary.classes.has(className) ||
      [...vocabulary.dynamicPrefixes].some((prefix) =>
        className.startsWith(prefix),
      ),
  );
}

function auditOrphans() {
  const vocabulary = collectVocabulary();
  const styles = walk(SRC, (f) => path.extname(f) === ".css").sort();
  return styles.map((file) => {
    const css = readFileSync(file, "utf8");
    const rules = extractRules(css);
    const orphanRules = rules.filter(
      (rule) =>
        !rule.selector
          .split(",")
          .some((selector) => reachable(selector.trim(), vocabulary)),
    );
    return {
      file: path.relative(ROOT, file),
      lines: css.split("\n").length,
      rules: rules.length,
      orphanRules: orphanRules.length,
      sample: orphanRules.slice(0, 5).map((rule) => rule.selector),
      brokenComments: newlinesEscapados(css),
    };
  });
}

function globalCssImports() {
  const main = readFileSync(MAIN, "utf8");
  return [...main.matchAll(/import\s+["'](.+?\.css)["'];/g)].map(
    (match) => match[1],
  );
}

function verifyGovernance() {
  if (!existsSync(GOVERNANCE)) {
    console.error("ERRO: frontend/scripts/css-governance.json ausente.");
    return false;
  }

  const governance = JSON.parse(readFileSync(GOVERNANCE, "utf8"));
  const imports = globalCssImports();
  const allowed = new Set(governance.allowed_global_imports ?? []);
  const unknown = imports.filter((item) => !allowed.has(item));
  let ok = true;

  const broken = auditOrphans().filter((item) => item.brokenComments.length);
  if (broken.length) {
    for (const item of broken) {
      for (const comment of item.brokenComments) {
        console.error(
          `ERRO: ${item.file}: quebra de linha escrita como dois caracteres na posição ${comment.index} (${comment.trecho}) — o navegador descarta ou contamina a regra seguinte.`,
        );
      }
    }
    ok = false;
  }

  if (unknown.length) {
    console.error(
      `ERRO: nova camada CSS global não autorizada: ${unknown.join(", ")}`,
    );
    ok = false;
  }

  const max = Number(governance.max_global_css_imports ?? allowed.size);
  if (imports.length > max) {
    console.error(
      `ERRO: main.tsx importa ${imports.length} folhas globais; teto atual: ${max}.`,
    );
    ok = false;
  }

  const canonicalLast = governance.tokens_must_be_last;
  if (canonicalLast && imports.at(-1) !== canonicalLast) {
    console.error(
      `ERRO: a última camada CSS deve ser ${canonicalLast}; atual: ${imports.at(-1) ?? "nenhuma"}.`,
    );
    ok = false;
  }

  if (ok) {
    console.log(
      `Governança CSS OK — ${imports.length}/${max} camadas globais; tokens canônicos por último; nenhum comentário quebrado.`,
    );
  }
  return ok;
}

const args = new Set(process.argv.slice(2));
const report = auditOrphans();

if (args.has("--json")) {
  console.log(
    JSON.stringify({ globalImports: globalCssImports(), report }, null, 2),
  );
} else {
  console.log("Auditoria conservadora de CSS — EJC\n");
  console.log(
    `${"arquivo".padEnd(52)}${"linhas".padStart(8)}${"regras".padStart(8)}${"órfãs*".padStart(9)}${"com.quebr.".padStart(13)}`,
  );
  console.log("-".repeat(90));
  for (const item of report) {
    console.log(
      `${item.file.padEnd(52)}${String(item.lines).padStart(8)}${String(item.rules).padStart(8)}${String(item.orphanRules).padStart(9)}${String(item.brokenComments.length).padStart(13)}`,
    );
  }
  console.log("\n* órfãs = heurística informativa; não é gate destrutivo.");
}

if (args.has("--verificar") && !verifyGovernance()) {
  process.exit(1);
}
