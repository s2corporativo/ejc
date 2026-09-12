import { ReactNode } from "react";
import { cn } from "../../lib/cn";

/**
 * Grid estilo Bento — layout modular inspirado nos dashboards modernos
 * (Apple, Linear, Vercel). Cada célula é independente e pode ter tamanhos
 * variados através das classes colSpan/rowSpan.
 *
 * @example
 * <BentoGrid>
 *   <BentoGridCell colSpan={2} rowSpan={1}>Widget grande</BentoGridCell>
 *   <BentoGridCell>Widget pequeno</BentoGridCell>
 * </BentoGrid>
 */
export function BentoGrid({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4",
        className,
      )}
    >
      {children}
    </div>
  );
}

/**
 * Célula individual do Bento Grid. Suporta spans customizados e
 * hierarquia visual automática baseada no conteúdo.
 */
export function BentoGridCell({
  children,
  colSpan = 1,
  rowSpan = 1,
  variant = "default",
  className,
}: {
  children: ReactNode;
  colSpan?: number;
  rowSpan?: number;
  /**
   * Variante visual:
   * - default: card padrão com borda sutil
   * - highlight: destaque com gradiente ouro (para KPIs críticos)
   * - warning: tom âmbar para alertas
   * - danger: tom vermelho para urgências
   */
  variant?: "default" | "highlight" | "warning" | "danger";
  className?: string;
}) {
  const baseStyles = "rounded-2xl p-5 transition-all duration-200";
  
  const variantStyles = {
    default: "border border-slate-200 bg-white hover:shadow-md dark:border-slate-700 dark:bg-slate-800",
    highlight: "border border-ouro/30 bg-gradient-to-br from-ouro-palha/10 to-ouro/5 hover:shadow-lg hover:from-ouro-palha/20 hover:to-ouro/10",
    warning: "border border-warn-300 bg-warn-50 hover:bg-warn-100 dark:border-warn-700/50 dark:bg-warn-900/20",
    danger: "border border-danger-300 bg-danger-50 hover:bg-danger-100 dark:border-danger-700/50 dark:bg-danger-900/20",
  };

  const spanClasses = {
    1: "col-span-1",
    2: "col-span-2",
    3: "col-span-3",
    4: "col-span-4",
  };

  return (
    <div
      className={cn(
        baseStyles,
        variantStyles[variant],
        spanClasses[Math.min(colSpan, 4) as keyof typeof spanClasses],
        rowSpan > 1 && "row-span-2",
        className,
      )}
      style={{
        gridColumn: colSpan > 1 ? `span ${colSpan} / span ${colSpan}` : undefined,
        gridRow: rowSpan > 1 ? `span ${rowSpan} / span ${rowSpan}` : undefined,
      }}
    >
      {children}
    </div>
  );
}

/**
 * Header de célula do Bento Grid — título + subtítulo + ação opcional.
 */
export function BentoGridHeader({
  eyebrow,
  title,
  subtitle,
  action,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-4 flex items-start justify-between">
      <div className="min-w-0 flex-1">
        {eyebrow && (
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            {eyebrow}
          </p>
        )}
        <h3 className="truncate text-base font-semibold text-slate-900 dark:text-slate-100">
          {title}
        </h3>
        {subtitle && (
          <p className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">
            {subtitle}
          </p>
        )}
      </div>
      {action && <div className="ml-2 shrink-0">{action}</div>}
    </div>
  );
}

/**
 * Conteúdo principal da célula — wrapper com espaçamento consistente.
 */
export function BentoGridContent({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-3", className)}>
      {children}
    </div>
  );
}

/**
 * Footer de célula — ações secundárias ou links "ver mais".
 */
export function BentoGridFooter({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mt-4 flex items-center justify-between border-t border-slate-100 pt-3 dark:border-slate-700", className)}>
      {children}
    </div>
  );
}
