import { CSSProperties } from "react";
import { cn } from "../../lib/cn";

/**
 * Blocos de carregamento (pulse) — preferíveis ao <Spinner /> quando a
 * página conhece o formato do conteúdo que vai chegar (listas, cards,
 * tabelas), pois evitam "salto" de layout.
 *
 * @example
 * {loading ? <SkeletonList rows={5} /> : <Table>…</Table>}
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

/**
 * Lista de linhas em pulse — placeholder de listas e tabelas.
 * Larguras levemente variadas para leitura mais natural.
 */
export function SkeletonList({
  rows = 4,
  withAvatar = false,
  className,
}: {
  rows?: number;
  /** Círculo à esquerda de cada linha (listas com avatar/ícone). */
  withAvatar?: boolean;
  className?: string;
}) {
  const widths = ["w-full", "w-11/12", "w-4/5", "w-full", "w-3/4"];
  return (
    <div className={cn("space-y-3", className)} aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3">
          {withAvatar && <Skeleton circle width={32} height={32} />}
          <Skeleton className={cn("h-4", widths[i % widths.length])} />
        </div>
      ))}
    </div>
  );
}

/**
 * Card em pulse — placeholder de StatCard/SectionCard enquanto carrega.
 */
export function SkeletonCard({
  lines = 3,
  header = true,
  className,
}: {
  /** Linhas de "texto" no corpo. */
  lines?: number;
  /** Exibe barra de título mais curta no topo. */
  header?: boolean;
  className?: string;
}) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "rounded-xl border border-slate-200 bg-white p-5",
        className,
      )}
    >
      {header && <Skeleton className="mb-4 h-5 w-1/3" />}
      <SkeletonList rows={lines} />
    </div>
  );
}
