import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import LegacyClientListAdapter from "../LegacyClientListAdapter";

function ClientTable() {
  return (
    <table>
      <thead>
        <tr>
          <th>Nome / Razão</th>
          <th>Tipo</th>
          <th>CPF / CNPJ</th>
          <th>Contato</th>
          <th>Status</th>
          <th>Desde</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Cliente</td>
          <td>PF</td>
          <td>***</td>
          <td>botões</td>
          <td>contato</td>
          <td>ativo</td>
          <td>data</td>
        </tr>
      </tbody>
    </table>
  );
}

describe("LegacyClientListAdapter", () => {
  it("insere Ações na quarta coluna quando a estrutura legada está desalinhada", async () => {
    render(
      <LegacyClientListAdapter>
        <ClientTable />
      </LegacyClientListAdapter>,
    );

    await waitFor(() => {
      expect(screen.getByRole("columnheader", { name: "Ações" })).toBeTruthy();
    });

    const headers = screen.getAllByRole("columnheader");
    expect(headers.map((header) => header.textContent)).toEqual([
      "Nome / Razão",
      "Tipo",
      "CPF / CNPJ",
      "Ações",
      "Contato",
      "Status",
      "Desde",
    ]);
  });

  it("não altera tabelas que não sejam a lista canônica de clientes", async () => {
    render(
      <LegacyClientListAdapter>
        <table>
          <thead>
            <tr>
              <th>Processo</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>0001</td>
            </tr>
          </tbody>
        </table>
      </LegacyClientListAdapter>,
    );

    await Promise.resolve();
    expect(screen.queryByRole("columnheader", { name: "Ações" })).toBeNull();
  });
});
