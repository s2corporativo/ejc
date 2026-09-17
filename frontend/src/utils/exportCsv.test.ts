import { describe, expect, it } from "vitest";
import { sanitizeCsvCell } from "./exportCsv";

describe("sanitizeCsvCell", () => {
  it.each([
    "=HYPERLINK(\"https://exemplo.invalid\")",
    "+SUM(1,2)",
    "-1+2",
    "@SUM(A1:A2)",
    "\t=cmd",
    "\r+SUM(1,2)",
    "  @SUM(A1:A2)",
  ])("neutraliza fórmula textual: %s", (payload) => {
    const cell = sanitizeCsvCell(payload);
    const decoded = cell.startsWith('"') && cell.endsWith('"')
      ? cell.slice(1, -1).replace(/""/g, '"')
      : cell;
    expect(decoded).toBe(`'${payload}`);
  });

  it("não converte número negativo real em texto", () => {
    expect(sanitizeCsvCell(-12.5)).toBe("-12.5");
  });

  it("mantém escaping de aspas, vírgulas e quebras", () => {
    expect(sanitizeCsvCell('a,"b"\nc')).toBe('"a,""b""\nc"');
  });
});
