import type { HTMLAttributes } from "react";
import { cn } from "../../lib/cn";

type BadgeVariant = "neutral" | "success" | "warn" | "danger" | "info" | "gold";

const variantClass: Record<BadgeVariant, string> = {
  neutral: "badge-neutral",
  success: "badge-success",
  warn: "badge-warn",
  danger: "badge-danger",
  info: "badge-info",
  gold: "badge-gold",
};

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

export function Badge({
  variant = "neutral",
  className,
  ...props
}: BadgeProps) {
  return (
    <span
      className={cn("badge", variantClass[variant], className)}
      {...props}
    />
  );
}
