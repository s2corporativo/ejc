import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const DIR = dirname(fileURLToPath(import.meta.url));
const api = readFileSync(join(DIR, "api.ts"), "utf-8");

describe("FE-10 — fachada HTTP única do DPT360", () => {
  it("mantém radar e relatório no módulo canônico", () => {
    expect(api).toContain("export type DptRadarToday");
    expect(api).toContain("export async function getDptRadarToday");
    expect(api).toContain("export type DptExecutiveReport");
    expect(api).toContain("export async function getDptExecutiveReport");
    expect(api.match(/from \"\.\.\/\.\.\/lib\/api\"/g)).toHaveLength(1);
  });

  it("não deixa módulos HTTP paralelos no domínio DPT360", () => {
    expect(existsSync(join(DIR, "radarApi.ts"))).toBe(false);
    expect(existsSync(join(DIR, "reportApi.ts"))).toBe(false);
    expect(readFileSync(join(DIR, "DptRadar.tsx"), "utf-8")).toContain(
      'from "./api"',
    );
    expect(readFileSync(join(DIR, "DptReports.tsx"), "utf-8")).toContain(
      'from "./api"',
    );
  });
});
