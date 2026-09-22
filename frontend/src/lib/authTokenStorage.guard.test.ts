// @vitest-environment node
import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));

function files(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (name === "node_modules" || name === "dist") continue;
    if (statSync(path).isDirectory()) out.push(...files(path));
    else if (
      /\.tsx?$/.test(name) &&
      !/\.(?:test|spec)\.tsx?$/.test(name)
    ) out.push(path);
  }
  return out;
}

describe("guard de bearer no storage", () => {
  it("não lê nem grava ejc_access em localStorage/sessionStorage", () => {
    const findings: string[] = [];
    for (const path of files(ROOT)) {
      const src = readFileSync(path, "utf8");
      const patterns = [
        /localStorage\.(?:getItem|setItem)\(\s*["']ejc_access["']/g,
        /sessionStorage\.(?:getItem|setItem)\(\s*["']ejc_access["']/g,
      ];
      for (const pattern of patterns) {
        if (pattern.test(src)) findings.push(path);
      }
    }
    expect(findings).toEqual([]);
  });
});
