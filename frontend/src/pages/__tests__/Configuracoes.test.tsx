/**
 * Regressão do gate de admin em /configuracoes?tab=administracao (achado da
 * revisão de segurança pós-limpeza de menu).
 *
 * Antes desta mudança, `/administracao/configuracoes` era uma rota própria
 * protegida por `RoleOnly roles={ROLES.administradores}` e coberta por
 * `moduleRegistry.test.ts` (canRoleAccessPath). A limpeza fundiu essa rota em
 * `/configuracoes?tab=administracao`, e o gate virou lógica em componente:
 * `isAdmin` controla tanto a presença da aba "Administração" na lista de tabs
 * quanto a renderização do conteúdo da aba. `canRoleAccessPath` não tem noção
 * de `?tab=`, então esse teste de rota antigo não pode mais cobrir o caso —
 * este arquivo substitui aquela cobertura no nível de componente.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

// stores/theme lê `window.matchMedia` na inicialização do store (fora do
// jsdom por padrão, sem polyfill no setup de testes deste repo). O tema não é
// o que este teste cobre — mocka o store para evitar o crash e manter o
// escopo focado no gate de administração.
vi.mock("../../stores/theme", () => ({
  useThemeStore: () => ({ theme: "light", setTheme: vi.fn() }),
  THEME_LABELS: { light: "Claro", dark: "Escuro", system: "Sistema" },
}));

import Configuracoes from "../Configuracoes";
import { useAuth } from "../../stores/auth";
import type { User } from "../../types";

function setUser(role: string) {
  const user: User = {
    email: "user@example.com",
    full_name: "Usuário de Teste",
    role,
  } as User;
  useAuth.setState({ user, status: "authenticated" });
}

const renderPage = (search: string) =>
  render(
    <MemoryRouter initialEntries={[`/configuracoes${search}`]}>
      <Configuracoes />
    </MemoryRouter>,
  );

describe("Configuracoes — gate de administração preservado após a fusão de rota", () => {
  beforeEach(() => {
    useAuth.setState({ user: null, status: "unauthenticated" });
    localStorage.clear();
  });

  it("perfil não-admin com ?tab=administracao: sem aba Administração, cai para Pessoal", async () => {
    setUser("advogado");
    renderPage("?tab=administracao");

    // Aguarda o conteúdo real da página (evita asserção durante estado transitório).
    expect(
      await screen.findByRole("heading", { name: /Configurações/ }),
    ).toBeTruthy();

    // (a) a aba "Administração" não deve existir na lista de tabs.
    expect(screen.queryByRole("button", { name: /Administração/ })).toBeNull();

    // (b) fallback para a aba "Pessoal" — conteúdo de Aparência/Conta visível,
    // e nenhum link admin-only (ex.: "Usuários e acessos") vazou para a tela.
    expect(screen.getByText("Aparência")).toBeTruthy();
    expect(screen.queryByText("Usuários e acessos")).toBeNull();
    expect(screen.queryByText("Governança da IA")).toBeNull();
  });

  it("perfil admin com ?tab=administracao: aba Administração aparece e seu conteúdo renderiza", async () => {
    setUser("admin");
    renderPage("?tab=administracao");

    expect(
      await screen.findByRole("heading", { name: /Administração do EJC/ }),
    ).toBeTruthy();

    // A aba existe na lista de tabs...
    expect(screen.getByRole("button", { name: /Administração/ })).toBeTruthy();

    // ...e como veio via ?tab=administracao, seu conteúdo é o que renderiza.
    expect(screen.getByText("Usuários e acessos")).toBeTruthy();
    expect(screen.getByText("Governança da IA")).toBeTruthy();
  });

  it("perfil superadmin também enxerga a aba Administração", async () => {
    setUser("superadmin");
    renderPage("?tab=administracao");

    expect(
      await screen.findByRole("heading", { name: /Administração do EJC/ }),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: /Administração/ })).toBeTruthy();
  });
});
