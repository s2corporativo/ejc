import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = resolve(__dirname, "..", "..");
const palette = readFileSync(resolve(__dirname, "CommandPalette.tsx"), "utf8");
const layout = readFileSync(resolve(__dirname, "LayoutReference.tsx"), "utf8");

describe("CommandPalette — modo privacidade", () => {
  it("permanece montado no shell com a flag explícita", () => {
    expect(layout).toContain("<CommandPalette privacyMode={privacyMode} />");
    expect(layout).not.toContain("!privacyMode && <CommandPalette");
  });

  it("interrompe a busca de entidades antes de chamar /search", () => {
    const effect = palette.slice(
      palette.indexOf("if (privacyMode) {"),
      palette.indexOf("if (!open) return null;"),
    );
    expect(effect).toContain("setRes([])");
    expect(effect).toContain("return;");
    expect(effect.indexOf("return;")).toBeLessThan(effect.indexOf('api\n        .get("/search"'));
  });

  it("não inclui resultados de entidades na navegação por teclado em privacidade", () => {
    expect(palette).toContain("...(privacyMode");
    expect(palette).toContain("? []");
    expect(palette).toContain("res.map((result, index)");
  });
});
