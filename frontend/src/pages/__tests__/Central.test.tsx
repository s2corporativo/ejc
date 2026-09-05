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

// Superfície PADRÃO de atividades desde a consolidação de Agenda/Prazos: a
// `CentralAtividades` legada só entra em deep-link com `?tipo=`/`?view=`. Sem
// este mock, quem é barrado do relacionamento cai num painel que o teste não
// conhece e a asserção do fallback não encontra nada.
vi.mock("../CentralAtividadesSimplificada", () => ({
  default: () => <div>PAINEL_ATIVIDADES_SIMPLIFICADO</div>,
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
      // A propriedade de segurança: mesmo entrando pela URL da aba de
      // relacionamento, o painel de atendimentos não é renderizado nem
      // oferecido — o usuário cai na superfície de atividades.
      expect(screen.queryByText("PAINEL_ATENDIMENTOS")).toBeNull();
      expect(
        screen.queryByRole("tab", { name: /Atendimentos de Clientes/ }),
      ).toBeNull();
      expect(screen.getByText("PAINEL_ATIVIDADES_SIMPLIFICADO")).toBeTruthy();
    },
  );
});
