// Slot de identidade do escritório nos pontos de apresentação da Entrada
// Única: a logomarca real do escritório no lugar da ilustração genérica do
// assistente.
//
// A origem vem SEMPRE de officeBranding.logoPath — não aceita prop `src` de
// propósito: aceitar tornaria cada ponto de uso um caminho hardcoded que
// sobrevive à troca de marca do ambiente (.env VITE_EJC_LOGO_PATH). O PNG é
// transparente, então o dimensionamento depende de object-fit (ver
// .ejc-assistente em ejc-dashboard-premium.css).
import { useCallback, useState } from "react";
import { cn } from "../../components/UI";
import { officeBranding } from "../../config/officeBranding";

export function IdentidadeAssistente({ className }: { className?: string }) {
  const [falhou, setFalhou] = useState(false);

  // Callback estável: arrow inline no JSX recria o handler a cada render e
  // dispara o lint de props em componentes de lista.
  const onError = useCallback(() => setFalhou(true), []);

  // O `alt` é derivado do nome do escritório configurado — a auditoria de
  // acessibilidade reprova <img> sem alternativa textual, e o nome do
  // escritório já é a descrição correta da marca.
  const alt = `Logomarca ${officeBranding.officeName}`;

  if (falhou) {
    return (
      <span
        role="img"
        aria-label={alt}
        className={cn("ejc-assistente--fallback", className)}
      >
        DT
      </span>
    );
  }

  return (
    <img
      src={officeBranding.logoPath}
      alt={alt}
      className={cn("ejc-assistente", className)}
      onError={onError}
      loading="lazy"
      decoding="async"
    />
  );
}
