import { describe, it, expect } from "vitest";
import { useEffect, useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { asList } from "./list";

// Componente mínimo que replica o padrão real do EJC: busca uma lista da API
// e renderiza cada item. Usa asList() para tolerar array cru OU envelope
// { items } / { data } sem quebrar (tela branca era o sintoma do bug #28).
function ListaCasos({ fetcher }: { fetcher: () => Promise<unknown> }) {
  const [rows, setRows] = useState<{ id: string; titulo: string }[]>([]);
  useEffect(() => {
    fetcher().then((resp) =>
      setRows(asList<{ id: string; titulo: string }>(resp)),
    );
  }, [fetcher]);
  return (
    <ul>
      {rows.map((r) => (
        <li key={r.id}>{r.titulo}</li>
      ))}
    </ul>
  );
}

describe("componente que consome lista de API", () => {
  it("renderiza itens quando a resposta vem embrulhada em { items }", async () => {
    const fetcher = () =>
      Promise.resolve({
        items: [
          { id: "1", titulo: "Caso Alfa" },
          { id: "2", titulo: "Caso Beta" },
        ],
      });
    render(<ListaCasos fetcher={fetcher} />);
    await waitFor(() => {
      expect(screen.getByText("Caso Alfa")).toBeTruthy();
      expect(screen.getByText("Caso Beta")).toBeTruthy();
    });
  });

  it("não quebra quando a resposta é um envelope inesperado (renderiza vazio)", async () => {
    const fetcher = () => Promise.resolve({ erro: "sem dados" });
    const { container } = render(<ListaCasos fetcher={fetcher} />);
    await waitFor(() => {
      expect(container.querySelectorAll("li").length).toBe(0);
    });
  });
});
