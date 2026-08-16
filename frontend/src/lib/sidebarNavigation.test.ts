import { describe, expect, it } from "vitest";

import { isSidebarNavigationCollapsed } from "./sidebarNavigation";

describe("isSidebarNavigationCollapsed", () => {
  it("mantém a navegação expandida na gaveta móvel mesmo após recolher o desktop", () => {
    expect(isSidebarNavigationCollapsed(true, true)).toBe(false);
  });

  it("preserva o estado compacto no desktop quando a gaveta móvel está fechada", () => {
    expect(isSidebarNavigationCollapsed(true, false)).toBe(true);
    expect(isSidebarNavigationCollapsed(false, false)).toBe(false);
  });
});
