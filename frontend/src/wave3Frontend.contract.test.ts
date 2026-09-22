import { describe, expect, it } from "vitest";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const src = resolve(__dirname);
const app = readFileSync(resolve(src, "App.tsx"), "utf8");

function sourceFiles(): string[] {
  const files: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = resolve(dir, entry.name);
      if (entry.isDirectory()) walk(path);
      else if (/\.(ts|tsx)$/.test(entry.name)) files.push(path);
    }
  };
  walk(src);
  return files;
}

describe("Wave 3 — limpeza e carregamento frontend", () => {
  it("não reintroduz os componentes órfãos FE-01/02/03", () => {
    for (const name of [
      "ConteudoJuridico.tsx",
      "DashboardAiChat.tsx",
      "CaseClosureModal.tsx",
      "DeadlineRiskStrip.tsx",
      "JurisprudentialAlertsStrip.tsx",
    ]) {
      expect(existsSync(resolve(src, "pages", name))).toBe(false);
      expect(existsSync(resolve(src, "components", name))).toBe(false);
    }

    const references = sourceFiles()
      .filter(
        (file) =>
          !file.endsWith("wave3Frontend.contract.test.ts") &&
          !/\.test\.(ts|tsx)$/.test(file),
      )
      .flatMap((file) => readFileSync(file, "utf8").split("\n"))
      .filter((line) =>
        /ConteudoJuridico|DashboardAiChat|CaseClosureModal|DeadlineRiskStrip|JurisprudentialAlertsStrip/.test(
          line,
        ),
      );
    expect(references).toEqual([]);
  });

  it("mantém Login e superfícies globais fora do bundle eager", () => {
    expect(app).toContain('lazy(() => import("./pages/Login"))');
    expect(app).toContain('import("./components/EntradaUniversalGlobal")');
    expect(app).toContain('import("./components/FlowEnhancements")');
    expect(app).toContain('import("./components/PortalLayout")');
    expect(app).not.toContain('from "./pages/LoginModern"');
    expect(app).not.toContain('from "./components/PortalLayout"');
  });
});
