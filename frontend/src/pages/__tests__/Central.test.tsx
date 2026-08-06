import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { useAuth } from "../../stores/auth";
import type { User } from "../../types";

vi.mock("../CentralAtividades", () => ({
  default: () => <div>PAINEL_ATIVIDADES</div>,
}));

vi.mock("../CentralRelacionamento", () => ({
  default: () => <div>PAINEL_ATENDIMENTOS</div>,
}));

import Central from "../Central";

function setUser(role: string) {
  useAuth.setState({
    user: {
      email: `${role}@example.com`,
      full_name: `Usuário ${role}`,
      role,
    } as User,
    status: "authenticated",
  });
}

function renderCentral(role: string) {
  setUser(role);
  return render(
    <MemoryRouter initialEntries={["/atividades?tab=relacionamento"]}>
      <Central />
    </MemoryRouter>,
  );
}

describe("Central — RBAC de atendimentos alinhado ao backend", () => {
  beforeEach(() => {
    useAuth.setState({ user: null, status: "unauthenticated" });
  });

  it.each(["superadmin", "admin", "socio", "advogado", "secretaria"])(
    "%s acessa a aba Atendimentos de Clientes",
    (role) => {
      renderCentral(role);
      expect(screen.getByText("PAINEL_ATENDIMENTOS")).toBeTruthy();
      expect(
        screen.getByRole("tab", { name: /Atendimentos de Clientes/ }),
      ).toBeTruthy();
    },
  );

  it.each(["advogado_auxiliar", "estagiario", "financeiro"])(
    "%s não recebe acesso indevido e volta para Atividades",
    (role) => {
      renderCentral(role);
      expect(screen.getByText("PAINEL_ATIVIDADES")).toBeTruthy();
      expect(
        screen.queryByRole("tab", { name: /Atendimentos de Clientes/ }),
      ).toBeNull();
    },
  );
});
