import { describe, expect, it } from "vitest";
import {
  CANONICAL_ROUTES,
  LEGACY_CANONICAL_REDIRECTS,
} from "../canonicalRoutes";

describe("canonical routes", () => {
  it("consolida o contexto jurídico no núcleo de inteligência", () => {
    expect(CANONICAL_ROUTES.inteligencia).toBe("/inteligencia");
    expect("areasAtuacao" in CANONICAL_ROUTES).toBe(false);
  });

  it("has unique legacy aliases and canonical destinations", () => {
    const sources = LEGACY_CANONICAL_REDIRECTS.map((item) => item.from);
    expect(new Set(sources).size).toBe(sources.length);
    for (const item of LEGACY_CANONICAL_REDIRECTS) {
      expect(item.from.startsWith("/")).toBe(true);
      expect(item.to.startsWith("/")).toBe(true);
      expect(item.reason.length).toBeGreaterThan(10);
    }
  });
});
