import { describe, expect, it } from "vitest";
import {
  CANONICAL_ROUTES,
  LEGACY_CANONICAL_REDIRECTS,
} from "../canonicalRoutes";

describe("canonical routes", () => {
  it("uses semantic area-of-practice naming", () => {
    expect(CANONICAL_ROUTES.areasAtuacao).toBe("/areas-de-atuacao");
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
