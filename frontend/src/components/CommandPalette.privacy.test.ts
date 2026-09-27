import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const palette = readFileSync(
  resolve(process.cwd(), "src/components/CommandPalette.tsx"),
  "utf8",
);
const layout = readFileSync(
  resolve(process.cwd(), "src/components/LayoutReference.tsx"),
  "utf8",
);

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
    expect(effect.indexOf("return;")).toBeGreaterThanOrEqual(0);
    expect(effect.indexOf("return;")).toBeLessThan(
      effect.indexOf('.get("/search"'),
    );
  });

  it("não inclui resultados de entidades na navegação por teclado em privacidade", () => {
    expect(palette).toContain("...(privacyMode");
    expect(palette).toContain("? []");
    expect(palette).toContain("res.map((result, index)");
  });
});
