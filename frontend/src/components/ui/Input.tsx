import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

interface FieldChromeProps {
  label?: string;
  hint?: string;
  error?: string;
  leftIcon?: ReactNode;
  rightSlot?: ReactNode;
}

export type InputProps = Omit<InputHTMLAttributes<HTMLInputElement>, keyof FieldChromeProps> & FieldChromeProps;

export function Input({ label, hint, error, leftIcon, rightSlot, className, id, ...props }: InputProps) {
  return (
    <label className="block space-y-1.5">
      {label && <span className="label mb-0">{label}</span>}
      <span className="relative block">
        {leftIcon && <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">{leftIcon}</span>}
        <input
          id={id}
          className={cn("input h-10", !!leftIcon && "pl-9", !!rightSlot && "pr-10", error && "ring-2 ring-danger-500/20", className)}
          {...props}
        />
        {rightSlot && <span className="absolute right-3 top-1/2 -translate-y-1/2">{rightSlot}</span>}
      </span>
      {(error || hint) && <span className={cn("block text-xs", error ? "text-danger-600" : "text-slate-500")}>{error || hint}</span>}
    </label>
  );
}

export type SelectProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, keyof FieldChromeProps> & FieldChromeProps;

export function Select({ label, hint, error, leftIcon, className, children, ...props }: SelectProps) {
  return (
    <label className="block space-y-1.5">
      {label && <span className="label mb-0">{label}</span>}
      <span className="relative block">
        {leftIcon && <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">{leftIcon}</span>}
        <select className={cn("select input h-10 appearance-none", !!leftIcon && "pl-9", error && "ring-2 ring-danger-500/20", className)} {...props}>
          {children}
        </select>
      </span>
      {(error || hint) && <span className={cn("block text-xs", error ? "text-danger-600" : "text-slate-500")}>{error || hint}</span>}
    </label>
  );
}

export type TextareaProps = Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, keyof FieldChromeProps> & FieldChromeProps;

export function Textarea({ label, hint, error, className, ...props }: TextareaProps) {
  return (
    <label className="block space-y-1.5">
      {label && <span className="label mb-0">{label}</span>}
      <textarea className={cn("textarea input min-h-28 resize-y", error && "ring-2 ring-danger-500/20", className)} {...props} />
      {(error || hint) && <span className={cn("block text-xs", error ? "text-danger-600" : "text-slate-500")}>{error || hint}</span>}
    </label>
  );
}
