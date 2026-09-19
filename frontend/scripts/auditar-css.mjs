#!/usr/bin/env node
/**
 * Auditor conservador de CSS do EJC.
 *
 * Objetivos:
 * 1) medir regras customizadas potencialmente órfãs;
 * 2) impedir que novas "camadas finais" globais sejam adicionadas ao main.tsx;
 * 3) garantir que os tokens canônicos --ejc-* continuem sendo a última camada.
 *
 * A detecção de órfãos é apenas informativa: classes montadas dinamicamente podem
 * gerar falso positivo. O gate bloqueante atua somente sobre a governança das
 * camadas globais, que é determinística.
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
      /"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|\`(?:[^\`\\]|\\.)*\`/gs,
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
      `Governança CSS OK — ${imports.length}/${max} camadas globais; tokens canônicos por último.`,
    );
  }
  return ok;
}

const args = new Set(process.argv.slice(2));
const report = auditOrphans();

if (args.has("--json")) {
  console.log(JSON.stringify({ globalImports: globalCssImports(), report }, null, 2));
} else {
  console.log("Auditoria conservadora de CSS — EJC\n");
  console.log(
    `${"arquivo".padEnd(52)}${"linhas".padStart(8)}${"regras".padStart(8)}${"órfãs*".padStart(9)}`,
  );
  console.log("-".repeat(77));
  for (const item of report) {
    console.log(
      `${item.file.padEnd(52)}${String(item.lines).padStart(8)}${String(item.rules).padStart(8)}${String(item.orphanRules).padStart(9)}`,
    );
  }
  console.log("\n* órfãs = heurística informativa; não é gate destrutivo.");
}

if (args.has("--verificar") && !verifyGovernance()) {
  process.exit(1);
}
