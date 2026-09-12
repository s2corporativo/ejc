import type { ButtonHTMLAttributes, ReactNode, ElementType } from "react";
import { Link } from "react-router-dom";
import { cn } from "../../lib/cn";

type ButtonVariant = "primary" | "secondary" | "outline" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg" | "icon";

const variantClass: Record<ButtonVariant, string> = {
  primary: "btn-primary",
  secondary: "btn-secondary",
  outline: "btn-outline",
  ghost: "btn-ghost",
  danger: "btn-danger",
};

const sizeClass: Record<ButtonSize, string> = {
  sm: "px-3 py-1.5 text-xs rounded-lg",
  md: "px-4 py-2 text-[13px] rounded-lg",
  lg: "px-5 py-2.5 text-sm rounded-lg",
  icon: "p-2",
};

export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "size"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  as?: ElementType;
  to?: string;
}

export function Button({
  variant = "primary",
  size = "md",
  leftIcon,
  rightIcon,
  className,
  children,
  type = "button",
  as: Component,
  to,
  ...props
}: ButtonProps) {
  const content = (
    <>
      {leftIcon}
      <span>{children}</span>
      {rightIcon}
    </>
  );

  if (Component && to) {
    return (
      <Component
        to={to}
        className={cn("btn", variantClass[variant], sizeClass[size], className)}
      >
        {content}
      </Component>
    );
  }

  return (
    <button
      type={type}
      className={cn("btn", variantClass[variant], sizeClass[size], className)}
      {...props}
    >
      {content}
    </button>
  );
}
