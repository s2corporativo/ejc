import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-router", () => ({ useNavigate: () => vi.fn() }));
vi.mock("../lib/api", () => ({ default: { get: vi.fn() } }));
vi.mock("../stores/auth", () => ({
  useAuth: (selector: (state: { user: { role: string } }) => unknown) =>
    selector({ user: { role: "advogado" } }),
}));
vi.mock("../stores/moduleLifecycle", () => ({
  useModuleLifecycleStore: (
    selector: (state: { settings: Record<string, unknown> }) => unknown,
  ) => selector({ settings: {} }),
}));

import CommandPalette from "./CommandPalette";

describe("CommandPalette — stacking no modo privacidade", () => {
  it("renderiza o diálogo acima do aviso fixo de privacidade", () => {
    render(<CommandPalette privacyMode />);

    act(() => {
      window.dispatchEvent(new Event("ejc-open-search"));
    });

    const dialog = screen.getByRole("dialog", {
      name: "Busca global do sistema",
    });
    expect(dialog.parentElement).toHaveClass("z-[90]");
  });
});
