import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "../../lib/cn";

export function Page({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return <main className={cn("space-y-6", className)} {...props} />;
}

export function PageHeader({
  className,
  ...props
}: HTMLAttributes<HTMLElement>) {
  return (
    <header
      className={cn(
        "flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between",
        className,
      )}
      {...props}
    />
  );
}

export function PageTitle({
  className,
  ...props
}: HTMLAttributes<HTMLHeadingElement>) {
  // Título de página denso (~20px/700) na cor escura da marca
  return (
    <h1
      className={cn(
        "text-xl font-bold tracking-tight text-primary-900",
        className,
      )}
      {...props}
    />
  );
}

export function PageDescription({
  className,
  ...props
}: HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={cn(
        "mt-1 max-w-3xl text-sm leading-6 text-slate-500",
        className,
      )}
      {...props}
    />
  );
}

export function PageActions({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement> & { children?: ReactNode }) {
  return (
    <div
      className={cn("flex flex-wrap items-center gap-2", className)}
      {...props}
    >
      {children}
    </div>
  );
}

export function PageGrid({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return (
    <section
      className={cn("grid gap-4 md:grid-cols-2 xl:grid-cols-3", className)}
      {...props}
    />
  );
}
