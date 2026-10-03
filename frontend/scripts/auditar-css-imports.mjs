import { readFileSync } from "node:fs";
import path from "node:path";
import postcss from "postcss";
import ts from "typescript";

// Expande a composição sem perder a ordem ou esconder folhas do gate global.
export function inspectCssEntry(mainPath, srcRoot) {
  const source = ts.createSourceFile(
    mainPath,
    readFileSync(mainPath, "utf8"),
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const entryImports = source.statements
    .filter(
      (node) =>
        ts.isImportDeclaration(node) &&
        ts.isStringLiteral(node.moduleSpecifier),
    )
    .map((node) => node.moduleSpecifier.text)
    .filter((name) => name.endsWith(".css"));
  const globalImports = [];
  const errors = [];

  function expand(specifier, parent, stack) {
    const file = path.resolve(path.dirname(parent), specifier);
    const relative = path.relative(srcRoot, file);
    if (
      !specifier.startsWith(".") ||
      relative.startsWith("..") ||
      path.isAbsolute(relative)
    ) {
      errors.push(`import CSS fora de src: ${specifier}`);
      return;
    }
    if (stack.includes(file)) {
      errors.push(`ciclo de imports CSS: ${relative}`);
      return;
    }
    let root;
    try {
      root = postcss.parse(readFileSync(file, "utf8"), { from: file });
    } catch (error) {
      errors.push(`não foi possível ler CSS ${relative}: ${error.message}`);
      return;
    }
    const imports = [];
    root.walkAtRules("import", (node) => imports.push(node));
    if (!imports.length) {
      globalImports.push(`./${relative.split(path.sep).join("/")}`);
      return;
    }
    // A composição é só uma lista de imports incondicionais. Qualificadores
    // layer/supports/media mudariam a cascata e exigem análise específica.
    if (
      root.nodes.some(
        (node) =>
          node.type !== "comment" &&
          !(node.type === "atrule" && node.name === "import"),
      )
    ) {
      errors.push(`composição CSS mistura imports e regras: ${relative}`);
      return;
    }
    for (const node of imports) {
      const match = node.params.match(
        /^(?:["']([^"']+)["']|url\(\s*["']?([^"')\s]+)["']?\s*\))\s*$/,
      );
      if (!match) {
        errors.push(
          `import CSS condicionado ou inválido em ${relative}: ${node.params}`,
        );
        continue;
      }
      expand(match[1] ?? match[2], file, [...stack, file]);
    }
  }
  for (const specifier of entryImports) expand(specifier, mainPath, []);
  return { entryImports, globalImports, errors };
}
