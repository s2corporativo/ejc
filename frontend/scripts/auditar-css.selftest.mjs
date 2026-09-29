/**
 * Autoteste do detector de quebra de linha escapada de scripts/auditar-css.mjs.
 *
 * Escreve folhas CSS sintéticas em src/__selftest/ (o auditor só varre
 * src/), roda o relatório JSON do próprio script e compara com o esperado;
 * depois verifica o gate `--verificar` (deve reprovar com defeito e passar
 * sem). Remove a pasta ao final. Exit 1 se qualquer caso divergir.
 */
import { mkdirSync, writeFileSync, rmSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const pasta = resolve(here, "../src/__selftest");
const BS = String.fromCharCode(92);
const NL = BS + "n";

const casos = [
  ["defeito-original.css", `/* cabecalho${NL} *\n${NL}html:not(.dark) { --a: 1 }\n`, true],
  ["escape-apos-comentario.css", `/* tema */${NL}html:not(.dark) { --a: 1 }\n`, true],
  // Dentro de comentário a sequência é só texto: NÃO é defeito.
  ["escape-dentro-comentario.css", `/* ver ${NL} aqui */ a { color: red }\n`, false],
  // Delimitadores dentro de string são texto válido: NÃO abrem comentário.
  ["string-com-delimitador.css", `a::after { content: "/*" }\nb::after { content: '//' }\n`, false],
  ["string-com-aspas-escapadas.css", `a::after { content: "\\"${NL} mais texto }" }\nb { color: blue }\n`, false],
  // Escape dentro de string é escape válido de CSS, não quebra gravada.
  ["escape-dentro-string.css", `a::after { content: "linha1${NL}linha2" }\n`, false],
  ["sem-fecho.css", `a { color: red } /* aberto\n`, true],
  ["linha-isolada.css", `a { color: red }\n${NL} b { color: blue }\n`, true],
  ["limpo-comentario.css", `a { color: red } /* ok */\n.b { color: blue }\n`, false],
  ["limpo-simples.css", `a { color: red }\n`, false],
];

rmSync(pasta, { recursive: true, force: true });
mkdirSync(pasta, { recursive: true });
for (const [nome, conteudo] of casos) writeFileSync(resolve(pasta, nome), conteudo, "utf8");

const auditor = resolve(here, "auditar-css.mjs");
const relatorio = JSON.parse(
  execFileSync("node", [auditor, "--json"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }),
).report;

let falhas = 0;
for (const [nome, , deveDetectar] of casos) {
  const item = relatorio.find((r) => r.file.endsWith(nome));
  const achados = item ? item.brokenComments.length : -1;
  const ok = achados > 0 === deveDetectar;
  if (!ok) falhas += 1;
  console.log(
    `${ok ? "ok    " : "FALHA "} ${achados > 0 ? "DETECTA" : "limpo "} ${String(achados).padStart(2)} — ${nome}`,
  );
}

const reais = relatorio.filter((r) => !casos.some(([nome]) => r.file.endsWith(nome)));
const sujos = reais.filter((r) => r.brokenComments.length);
const reaisOk = sujos.length === 0;
if (!reaisOk) falhas += 1;
console.log(
  `${reaisOk ? "ok    " : "FALHA "} ${reais.length} folhas reais do repositório: ${reaisOk ? "todas limpas" : sujos.map((s) => `${s.file} (${s.brokenComments.length})`).join("; ")}`,
);

// Gate: com defeito sintético precisa reprovar; sem, precisa passar.
writeFileSync(resolve(pasta, "limpo.css"), "a { color: red }\n", "utf8");
const rodaGate = () => {
  try {
    execFileSync("node", [auditor, "--verificar"], { stdio: "ignore" });
    return 0;
  } catch (e) {
    return e.status ?? 1;
  }
};
const comDefeito = rodaGate();
const comDefeitoOk = comDefeito === 1;
if (!comDefeitoOk) falhas += 1;
console.log(`${comDefeitoOk ? "ok    " : "FALHA "} gate --verificar com defeito: exit ${comDefeito} (esperado 1)`);
rmSync(pasta, { recursive: true, force: true });
const limpo = rodaGate();
const limpoOk = limpo === 0;
if (!limpoOk) falhas += 1;
console.log(`${limpoOk ? "ok    " : "FALHA "} gate --verificar sem defeito: exit ${limpo} (esperado 0)`);

console.log(falhas === 0 ? "TODOS OS CASOS OK" : `${falhas} FALHA(S)`);
process.exit(falhas === 0 ? 0 : 1);
