import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { readdir, readFile, rm, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(__dirname, "__out__", "homologacao-modulos");
const BASELINE = path.resolve(__dirname, "visual-baseline.json");
const update = process.argv.includes("--update");

async function runHomologacao() {
  await rm(OUT, { recursive: true, force: true });
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [path.join(__dirname, "homologacao-modulos.mjs")], {
      cwd: path.resolve(__dirname, ".."),
      stdio: "inherit",
      env: { ...process.env, HOMOLOGACAO_SCREENSHOT_DIR: OUT },
    });
    child.on("error", reject);
    child.on("exit", (code) =>
      code === 0 ? resolve() : reject(new Error(`homologacao-modulos saiu com ${code}`)),
    );
  });
}

async function hashes() {
  const names = (await readdir(OUT)).filter((name) => name.endsWith(".png")).sort();
  const result = {};
  for (const name of names) {
    const bytes = await readFile(path.join(OUT, name));
    result[name] = createHash("sha256").update(bytes).digest("hex");
  }
  return result;
}

await runHomologacao();
const current = await hashes();
if (Object.keys(current).length !== 40) {
  throw new Error(`esperadas 40 capturas canônicas; obtidas ${Object.keys(current).length}`);
}

if (update || !existsSync(BASELINE)) {
  await writeFile(
    BASELINE,
    JSON.stringify({ schema_version: 1, renderer: "playwright-1.63.0-noble", screenshots: current }, null, 2) + "\n",
  );
  console.log(`baseline visual atualizado: ${BASELINE}`);
  process.exit(0);
}

const expected = JSON.parse(await readFile(BASELINE, "utf8")).screenshots || {};
const allNames = [...new Set([...Object.keys(expected), ...Object.keys(current)])].sort();
const changed = allNames.filter((name) => expected[name] !== current[name]);
if (changed.length) {
  console.error("REGRESSÃO VISUAL: diferenças detectadas:");
  for (const name of changed) {
    console.error(` - ${name}: esperado=${expected[name] || "ausente"} atual=${current[name] || "ausente"}`);
  }
  console.error("Revise as imagens e, se a mudança for intencional, rode npm run test:visual:update.");
  process.exit(1);
}
console.log(`REGRESSÃO VISUAL: OK — ${allNames.length} capturas idênticas à baseline.`);
