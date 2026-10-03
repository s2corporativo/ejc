import assert from "node:assert/strict";
import {
  mkdtempSync,
  mkdirSync,
  writeFileSync,
  readFileSync,
  rmSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { inspectCssEntry } from "./auditar-css-imports.mjs";

function fixture(t, files, main = 'import "./styles/global.css";') {
  const dir = mkdtempSync(path.join(tmpdir(), "ejc-css-imports-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const src = path.join(dir, "src");
  mkdirSync(path.join(src, "styles"), { recursive: true });
  const entry = path.join(src, "main.tsx");
  writeFileSync(entry, main);
  for (const [name, content] of Object.entries(files)) {
    writeFileSync(path.join(src, name), content);
  }
  return inspectCssEntry(entry, src);
}

test("expande imports relativos em ordem e ignora imports dentro de comentários JS", (t) => {
  const result = fixture(
    t,
    {
      "styles/global.css":
        '@import "./fonts.css"; @import "../index.css"; @import url("./tokens.css");',
      "styles/fonts.css":
        '@font-face { font-family: "Example"; src: url("/font.woff2"); }',
      "index.css": "@tailwind base;",
      "styles/tokens.css": ":root { --a: 1; }",
    },
    '// import "./ghost.css";\nimport "./styles/global.css";',
  );
  assert.deepEqual(result.entryImports, ["./styles/global.css"]);
  assert.deepEqual(result.globalImports, [
    "./styles/fonts.css",
    "./index.css",
    "./styles/tokens.css",
  ]);
  assert.deepEqual(result.errors, []);
});

test("composição aninhada mantém a sequência e não perde folhas repetidas", (t) => {
  const result = fixture(t, {
    "styles/global.css": '@import "./base.css"; @import "./tokens.css";',
    "styles/base.css": '@import "./tokens.css";',
    "styles/tokens.css": ":root { --a: 1; }",
  });
  assert.deepEqual(result.globalImports, [
    "./styles/tokens.css",
    "./styles/tokens.css",
  ]);
  assert.deepEqual(result.errors, []);
});

for (const qualifier of [
  "screen and (min-width: 600px)",
  "layer(base)",
  "supports(display: grid)",
]) {
  test(`não aceita import com condição: ${qualifier}`, (t) => {
    const result = fixture(t, {
      "styles/global.css": `@import "./tokens.css" ${qualifier};`,
    });
    assert.equal(result.errors.length, 1);
    assert.match(result.errors[0], /condicionado/);
  });
}

test("ciclo de imports é erro, sem truncar silenciosamente a composição", (t) => {
  const result = fixture(t, { "styles/global.css": '@import "./global.css";' });
  assert.match(result.errors[0], /ciclo/);
});

test("folha ausente é erro", (t) => {
  const result = fixture(t, {
    "styles/global.css": '@import "./missing.css";',
  });
  assert.match(result.errors[0], /não foi possível ler CSS/);
});

test("composição com regras ou import aninhado é erro", (t) => {
  const result = fixture(t, {
    "styles/global.css": '@import "./tokens.css"; body { color: red; }',
  });
  assert.match(result.errors[0], /mistura imports e regras/);
  const nested = fixture(t, {
    "styles/global.css": '@media screen { @import "./tokens.css"; }',
  });
  assert.match(nested.errors[0], /mistura imports e regras/);
});

test("import remoto ou fora de src é erro", (t) => {
  for (const specifier of [
    "https://example.invalid/a.css",
    "../../outside.css",
  ]) {
    const result = fixture(t, {
      "styles/global.css": `@import "${specifier}";`,
    });
    assert.match(result.errors[0], /fora de src/);
  }
});

test("a entrada real mantém as nove folhas autorizadas e os tokens finais", () => {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const governance = JSON.parse(
    readFileSync(path.join(root, "scripts/css-governance.json"), "utf8"),
  );
  const result = inspectCssEntry(
    path.join(root, "src/main.tsx"),
    path.join(root, "src"),
  );
  assert.deepEqual(result.errors, []);
  assert.deepEqual(result.entryImports, [governance.global_entry]);
  assert.deepEqual(result.globalImports, governance.allowed_global_imports);
  assert.equal(result.globalImports.length, governance.max_global_css_imports);
  assert.equal(result.globalImports.at(-1), governance.tokens_must_be_last);
});
