import { type ReactNode, useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";

const TYPE_LABEL: Record<string, string> = {
  prazo: "Prazo",
  audiencia: "Audiência",
  tarefa: "Tarefa",
  reuniao: "Reunião",
  compromisso: "Compromisso",
  diligencia: "Diligência",
  suspensao: "Suspensão",
  intimacao: "Intimação",
  todos: "Todos",
};

/**
 * Compatibilidade para deep-link `?tipo=` da Central unificada.
 *
 * A Central legada mantém o filtro em estado local. Este adaptador reconhece
 * semanticamente os botões oficiais do filtro e ativa somente o rótulo pedido,
 * sem alterar dados, endpoints ou regras de prazo. Pode ser removido quando a
 * página passar a inicializar `filterTipo` diretamente pelos search params.
 */
export default function LegacyActivityQueryAdapter({
  children,
}: {
  children: ReactNode;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [searchParams] = useSearchParams();
  const requested = searchParams.get("tipo") || "";
  const label = TYPE_LABEL[requested];

  useEffect(() => {
    const root = rootRef.current;
    if (!root || !label) return;

    let applying = false;
    const aplicar = () => {
      if (applying) return;
      const candidates = Array.from(root.querySelectorAll("button"));
      const button = candidates.find(
        (item) => item.textContent?.trim() === label,
      );
      if (!button || button.className.includes("bg-navy")) return;
      applying = true;
      button.click();
      queueMicrotask(() => {
        applying = false;
      });
    };

    aplicar();
    const observer = new MutationObserver(aplicar);
    observer.observe(root, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, [label]);

  return <div ref={rootRef}>{children}</div>;
}
