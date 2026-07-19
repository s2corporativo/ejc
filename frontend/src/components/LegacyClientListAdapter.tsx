import { type ReactNode, useEffect, useRef } from "react";

/**
 * Adaptador temporário e localizado para a lista legada de clientes.
 *
 * A tabela possui sete células por linha, mas o cabeçalho histórico declara
 * apenas seis colunas. O adaptador insere o cabeçalho "Ações" somente quando:
 * - reconhece a tabela de clientes pelos títulos canônicos;
 * - a primeira linha possui exatamente uma célula a mais que o cabeçalho;
 * - a coluna ainda não foi corrigida.
 *
 * Nenhum dado é lido ou enviado; a operação é estritamente semântica/visual.
 * Pode ser removido quando `Clientes.tsx` migrar para o componente Table do DS.
 */
export default function LegacyClientListAdapter({
  children,
}: {
  children: ReactNode;
}) {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const corrigir = () => {
      for (const table of root.querySelectorAll("table")) {
        const headerRow = table.querySelector("thead tr");
        const firstBodyRow = table.querySelector("tbody tr");
        if (!headerRow || !firstBodyRow) continue;

        const headers = Array.from(headerRow.querySelectorAll("th"));
        const cells = Array.from(firstBodyRow.querySelectorAll("td"));
        const labels = headers.map(
          (header) => header.textContent?.trim() || "",
        );
        const tabelaDeClientes =
          labels.includes("Nome / Razão") && labels.includes("CPF / CNPJ");
        if (!tabelaDeClientes) continue;
        if (headerRow.querySelector('[data-ejc-client-actions="true"]'))
          continue;
        if (cells.length !== headers.length + 1 || headers.length < 4) continue;

        const actions = document.createElement("th");
        actions.textContent = "Ações";
        actions.className = "px-4 py-3 text-right";
        actions.dataset.ejcClientActions = "true";
        headerRow.insertBefore(actions, headers[3]);
      }
    };

    corrigir();
    const observer = new MutationObserver(corrigir);
    observer.observe(root, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  return <div ref={rootRef}>{children}</div>;
}
