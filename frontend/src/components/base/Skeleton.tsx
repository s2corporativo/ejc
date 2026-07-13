import { CSSProperties } from "react";
import { cn } from "../../lib/cn";

/**
 * Blocos de carregamento (pulse) — preferíveis ao <Spinner /> quando a
 * página conhece o formato do conteúdo que vai chegar (listas, cards,
 * tabelas), pois evitam "salto" de layout.
 *
 * @example
 * {loading ? <Skeleton height={20} /> : <Row>…</Row>}
 */
export function Skeleton({
  className,
  width,
  height,
  circle,
}: {
  className?: string;
  /** Largura fixa (px ou string CSS). Sem valor: w-full via classe padrão. */
  width?: number | string;
  /** Altura fixa (px ou string CSS). Sem valor: h-4 via classe padrão. */
  height?: number | string;
  /** Círculo (avatar). Aplica rounded-full. */
  circle?: boolean;
}) {
  const style: CSSProperties = {};
  if (width != null) style.width = width;
  if (height != null) style.height = height;
  return (
    <div
      aria-hidden="true"
      style={Object.keys(style).length ? style : undefined}
      className={cn(
        "animate-pulse bg-slate-200/70",
        circle ? "rounded-full" : "rounded-lg",
        // Compat: mesma regra do Skeleton legado de UI.tsx — o className,
        // quando presente, substitui as dimensões padrão.
        className || (width == null && height == null ? "h-4 w-full" : ""),
      )}
    />
  );
}
