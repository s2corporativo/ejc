import { ReactNode } from "react";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Bot,
  CheckCircle2,
  FileText,
  ChevronDown,
  Filter,
  Inbox,
  Loader2,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";

type Tone = "slate" | "blue" | "green" | "amber" | "red" | "purple";
type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "ai";

const toneClasses: Record<Tone, string> = {
  slate: "bg-slate-100 text-slate-700 ring-slate-200",
  blue: "bg-blue-50 text-blue-700 ring-blue-200",
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  amber: "bg-amber-50 text-amber-700 ring-amber-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  purple: "bg-violet-50 text-violet-700 ring-violet-200",
};

const buttonClasses: Record<ButtonVariant, string> = {
  primary: "bg-[#b5822e] text-white hover:bg-[#9a6c1f] focus:ring-[#b5822e]",
  secondary:
    "bg-white text-slate-700 border border-slate-200 hover:bg-slate-50 focus:ring-[#b5822e]",
  ghost:
    "bg-transparent text-slate-600 hover:bg-slate-100 focus:ring-slate-400",
  danger: "bg-red-600 text-white hover:bg-red-700 focus:ring-red-500",
  ai: "bg-violet-600 text-white hover:bg-violet-700 focus:ring-violet-500",
};

export function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export function Button({
  children,
  icon,
  variant = "primary",
  size = "md",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  children?: ReactNode;
  icon?: ReactNode;
  variant?: ButtonVariant;
  size?: "sm" | "md" | "lg" | "icon";
}) {
  const sizeClass = {
    sm: "h-8 px-3 text-xs",
    md: "h-10 px-4 text-sm",
    lg: "h-11 px-5 text-sm",
    icon: "h-10 w-10 p-0",
  }[size];
  return (
    <button
      {...props}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-all",
        "focus:outline-none focus:ring-2 focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50",
        sizeClass,
        buttonClasses[variant],
        className,
      )}
    >
      {icon}
      {children}
    </button>
  );
}

export function Card({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("card", className)}>{children}</div>;
}

export function SectionCard({
  title,
  subtitle,
  actions,
  children,
  className,
}: {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("section-card", className)}>
      {(title || actions) && (
        <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <div className="min-w-0">
            {title && (
              <h2 className="text-sm font-semibold text-slate-950">{title}</h2>
            )}
            {subtitle && (
              <p className="mt-1 text-xs text-slate-500">{subtitle}</p>
            )}
          </div>
          {actions && (
            <div className="flex shrink-0 items-center gap-2">{actions}</div>
          )}
        </div>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Badge({
  children,
  tone = "slate",
  className,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset",
        toneClasses[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

const STATUS_TONE: Record<string, Tone> = {
  ativo: "green",
  aberto: "green",
  concluido: "green",
  aprovada: "green",
  pago: "green",
  triagem: "amber",
  pendente: "amber",
  em_revisao: "amber",
  suspenso: "amber",
  vencido: "red",
  atrasado: "red",
  cancelado: "red",
  rejeitado: "red",
  critico: "red",
  ia: "purple",
  rascunho: "slate",
  arquivado: "slate",
  encerrado: "slate",
};

export function StatusBadge({ value }: { value?: string | null }) {
  const label = value || "sem status";
  return (
    <Badge tone={STATUS_TONE[label] || "slate"}>
      {label.replace(/_/g, " ")}
    </Badge>
  );
}

export function PriorityBadge({ value }: { value?: string | null }) {
  const priority = (value || "normal").toLowerCase();
  const tone: Tone =
    priority === "alta" || priority === "critica"
      ? "red"
      : priority === "media"
        ? "amber"
        : "slate";
  return <Badge tone={tone}>{priority}</Badge>;
}

export function FieldLabel({
  children,
  required,
}: {
  children: ReactNode;
  required?: boolean;
}) {
  return (
    <label className="mb-1.5 block text-xs font-medium text-slate-600">
      {children}
      {required && <span className="ml-1 text-red-500">*</span>}
    </label>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cn("input", props.className)} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cn("input", props.className)} />;
}

export function Textarea(
  props: React.TextareaHTMLAttributes<HTMLTextAreaElement>,
) {
  return (
    <textarea
      {...props}
      className={cn("input min-h-24 resize-y", props.className)}
    />
  );
}

export function SearchBar({
  value,
  onChange,
  placeholder = "Buscar",
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="pl-9"
      />
    </div>
  );
}

export function FilterBar({
  children,
  onClear,
}: {
  children: ReactNode;
  onClear?: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white p-3">
      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
        <SlidersHorizontal className="h-4 w-4" />
        Filtros
      </div>
      <div className="flex flex-1 flex-wrap items-center gap-2">{children}</div>
      {onClear && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          icon={<Filter className="h-3.5 w-3.5" />}
          onClick={onClear}
        >
          Limpar
        </Button>
      )}
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  eyebrow,
  actions,
}: {
  title: string;
  subtitle?: string;
  eyebrow?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <div className="eyebrow mb-2">{eyebrow}</div>}
        <h1 className="text-2xl font-semibold tracking-tight text-slate-950 md:text-3xl">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-2 max-w-3xl text-sm text-slate-500">{subtitle}</p>
        )}
      </div>
      {actions && (
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {actions}
        </div>
      )}
    </div>
  );
}

export function StatCard({
  label,
  value,
  subtitle,
  icon,
  tone = "blue",
  trend,
}: {
  label: string;
  value: ReactNode;
  subtitle?: string;
  icon?: ReactNode;
  tone?: Tone;
  trend?: "up" | "down";
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            {label}
          </p>
          <div className="mt-2 text-2xl font-semibold text-slate-950">
            {value}
          </div>
          {subtitle && (
            <p className="mt-1 text-xs text-slate-500">{subtitle}</p>
          )}
        </div>
        {icon && (
          <div
            className={cn(
              "rounded-xl p-2.5 ring-1 ring-inset",
              toneClasses[tone],
            )}
          >
            {icon}
          </div>
        )}
      </div>
      {trend && (
        <div className="mt-3 flex items-center gap-1 text-xs text-slate-500">
          {trend === "up" ? (
            <ArrowUp className="h-3.5 w-3.5 text-emerald-600" />
          ) : (
            <ArrowDown className="h-3.5 w-3.5 text-red-600" />
          )}
          Tendencia {trend === "up" ? "positiva" : "de atencao"}
        </div>
      )}
    </Card>
  );
}

export function Table({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-xl border border-slate-200 bg-white",
        className,
      )}
    >
      <div className="overflow-x-auto">
        <table className="table">{children}</table>
      </div>
    </div>
  );
}

export function Tabs({
  items,
  value,
  onChange,
}: {
  items: Array<{ value: string; label: string; icon?: ReactNode }>;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex gap-1 overflow-x-auto rounded-xl border border-slate-200 bg-white p-1">
      {items.map((item) => (
        <button
          key={item.value}
          type="button"
          onClick={() => onChange(item.value)}
          className={cn(
            "flex h-9 shrink-0 items-center gap-2 rounded-lg px-3 text-sm font-medium transition-all",
            value === item.value
              ? "bg-blue-600 text-white shadow-sm"
              : "text-slate-600 hover:bg-slate-100",
          )}
        >
          {item.icon}
          {item.label}
        </button>
      ))}
    </div>
  );
}

export function Dropdown({
  label,
  children,
}: {
  label: ReactNode;
  children: ReactNode;
}) {
  return (
    <details className="relative">
      <summary className="flex h-10 cursor-pointer list-none items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 hover:bg-slate-50">
        {label}
        <ChevronDown className="h-4 w-4 text-slate-400" />
      </summary>
      <div className="absolute right-0 z-40 mt-2 min-w-48 rounded-xl border border-slate-200 bg-white p-2 shadow-lg">
        {children}
      </div>
    </details>
  );
}

export function Tooltip({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <span className="group relative inline-flex">
      {children}
      <span className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 hidden -translate-x-1/2 whitespace-nowrap rounded-md bg-slate-950 px-2 py-1 text-xs text-white shadow-lg group-hover:block">
        {label}
      </span>
    </span>
  );
}

export function Modal({
  open,
  onClose,
  title,
  children,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  wide?: boolean;
}) {
  if (!open) return null;
  return (
    <div className="modal-backdrop animate-fade-in" onClick={onClose}>
      <div
        className={cn(
          "w-full max-h-[90vh] overflow-auto rounded-2xl border border-slate-200 bg-white shadow-2xl animate-pop",
          wide ? "max-w-4xl" : "max-w-lg",
        )}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-100 bg-white/95 px-5 py-4 backdrop-blur">
          <h2 className="text-base font-semibold text-slate-950">{title}</h2>
          <Button
            type="button"
            onClick={onClose}
            variant="ghost"
            size="icon"
            aria-label="Fechar"
            icon={<X className="h-4 w-4" />}
          />
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-lg bg-slate-200/70",
        className || "h-4 w-full",
      )}
    />
  );
}

export function EmptyState({
  title = "Nada encontrado",
  message,
  icon: Icon = Inbox,
  action,
}: {
  title?: string;
  message?: string;
  icon?: typeof Inbox;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-200 bg-white px-6 py-12 text-center">
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-slate-100 text-slate-400">
        <Icon className="h-6 w-6" />
      </div>
      <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      {message && (
        <p className="mt-1 max-w-md text-sm text-slate-500">{message}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Empty({
  message,
  icon: Icon = Inbox,
}: {
  message: string;
  icon?: typeof Inbox;
}) {
  return <EmptyState title={message} icon={Icon} />;
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center p-12">
      <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
    </div>
  );
}

export function IANotice({
  children = "Rascunho sujeito a revisao humana obrigatoria.",
}: {
  children?: ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-violet-200 bg-violet-50 px-4 py-3 text-sm text-violet-800">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div>{children}</div>
    </div>
  );
}


export function AISurface({
  title = "IA Juridica",
  subtitle = "Rascunho sujeito a revisao humana obrigatoria.",
  actions,
  children,
  className,
}: {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("ai-surface overflow-hidden", className)}>
      <div className="ai-surface-header">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-violet-600 text-white">
            <Bot className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-slate-950">{title}</h2>
            <p className="mt-1 text-xs text-slate-500">{subtitle}</p>
          </div>
        </div>
        {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}

export function ConfidenceBadge({ value }: { value?: number | null }) {
  const score = typeof value === "number" ? Math.max(0, Math.min(100, value)) : null;
  const tone: Tone = score == null ? "slate" : score >= 80 ? "green" : score >= 60 ? "amber" : "red";
  return (
    <Badge tone={tone} className="gap-1">
      <CheckCircle2 className="h-3 w-3" />
      {score == null ? "confianca pendente" : `${score}% confianca`}
    </Badge>
  );
}

export function VisualLawDocument({
  title,
  subtitle,
  meta = [],
  children,
  className,
}: {
  title: string;
  subtitle?: string;
  meta?: Array<{ label: string; value: ReactNode }>;
  children: ReactNode;
  className?: string;
}) {
  return (
    <article className={cn("visual-law-document overflow-hidden", className)}>
      <header className="visual-law-document-header">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-700 text-white">
            <FileText className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h1>{title}</h1>
            {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
          </div>
        </div>
        {meta.length > 0 && (
          <div className="visual-law-meta-grid">
            {meta.map((item) => (
              <div key={item.label} className="visual-law-meta-item">
                <div className="visual-law-meta-label">{item.label}</div>
                <div className="visual-law-meta-value">{item.value}</div>
              </div>
            ))}
          </div>
        )}
      </header>
      <div className="visual-law-document-body">{children}</div>
    </article>
  );
}

export function fmtMoney(v?: number | null) {
  if (v == null) return "—";
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function fmtDate(d?: string | null) {
  if (!d) return "—";
  const date = new Date(d.includes("T") ? d : d + "T12:00:00");
  return date.toLocaleDateString("pt-BR");
}
