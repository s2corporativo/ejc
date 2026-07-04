import { ReactNode, useEffect, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Bot,
  CheckCircle2,
  FileText,
  ChevronDown,
  Filter,
  Inbox,
  Info,
  Loader2,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";

type Tone = "slate" | "blue" | "green" | "amber" | "red" | "purple";
type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "ai";

const toneClasses: Record<Tone, string> = {
  slate: "bg-slate-100 text-slate-700 ring-slate-200",
  blue: "bg-primary-50 text-primary-700 ring-primary-200",
  green: "bg-success-50 text-success-700 ring-success-200",
  amber: "bg-warn-50 text-warn-700 ring-warn-200",
  red: "bg-danger-50 text-danger-700 ring-danger-200",
  purple: "bg-ai-50 text-ai-700 ring-ai-200",
};

const buttonClasses: Record<ButtonVariant, string> = {
  primary:
    "bg-primary-600 text-white shadow-sm hover:bg-primary-500 active:bg-primary-700 focus:ring-primary-500/40",
  secondary:
    "bg-white text-slate-700 border border-slate-200 hover:bg-slate-50 hover:border-slate-300 focus:ring-primary-500/40",
  ghost:
    "bg-transparent text-slate-600 hover:bg-slate-100 focus:ring-slate-400/40",
  danger:
    "bg-danger-600 text-white hover:bg-danger-700 focus:ring-danger-500/40",
  ai: "bg-ai-600 text-white shadow-sm hover:bg-ai-500 active:bg-ai-700 focus:ring-ai-500/40",
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
        "inline-flex items-center justify-center gap-2 rounded-xl font-medium transition-all duration-150 ease-out active:scale-[.98]",
        "focus:outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50",
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
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium ring-1 ring-inset",
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
      {required && <span className="ml-1 text-danger-500">*</span>}
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
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-slate-400">{label}</p>
          <div className="mt-2 text-3xl font-semibold tracking-tight text-slate-950 tabular-nums">
            {value}
          </div>
          {subtitle && (
            <p className="mt-1 text-xs text-slate-400">{subtitle}</p>
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
        <div className="mt-3">
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold",
              trend === "up"
                ? "bg-success-50 text-success-600"
                : "bg-danger-50 text-danger-500",
            )}
          >
            {trend === "up" ? (
              <ArrowUp className="h-3 w-3" />
            ) : (
              <ArrowDown className="h-3 w-3" />
            )}
            Tendencia {trend === "up" ? "positiva" : "de atencao"}
          </span>
        </div>
      )}
    </Card>
  );
}

/**
 * Tabela padrão: wrapper com `overflow-x-auto` (responsividade), cabeçalho
 * slate (via classe `.table` do index.css) e zebra sutil via <TR>.
 *
 * @example
 * <Table>
 *   <THead>
 *     <TR zebra={false}>
 *       <TH>Cliente</TH>
 *       <TH>Status</TH>
 *     </TR>
 *   </THead>
 *   <tbody>
 *     {itens.map((c) => (
 *       <TR key={c.id}>
 *         <TD>{c.nome}</TD>
 *         <TD><StatusBadge value={c.status} /></TD>
 *       </TR>
 *     ))}
 *   </tbody>
 * </Table>
 */
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

export function THead({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <thead className={className}>{children}</thead>;
}

export function TR({
  children,
  className,
  zebra = true,
  ...props
}: React.HTMLAttributes<HTMLTableRowElement> & {
  children: ReactNode;
  /** Realce sutil no hover (desligue em <THead>). Sem zebra — divisórias finas. */
  zebra?: boolean;
}) {
  return (
    <tr
      {...props}
      className={cn(
        zebra && "transition-colors hover:bg-slate-50/70",
        className,
      )}
    >
      {children}
    </tr>
  );
}

export function TH({
  children,
  className,
  ...props
}: React.ThHTMLAttributes<HTMLTableCellElement> & {
  children?: ReactNode;
}) {
  return (
    <th {...props} className={className}>
      {children}
    </th>
  );
}

export function TD({
  children,
  className,
  ...props
}: React.TdHTMLAttributes<HTMLTableCellElement> & {
  children?: ReactNode;
}) {
  return (
    <td {...props} className={className}>
      {children}
    </td>
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
              ? "bg-primary-600 text-white shadow-sm"
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

type ModalSize = "sm" | "md" | "lg" | "xl";

const modalSizeClasses: Record<ModalSize, string> = {
  sm: "max-w-sm",
  md: "max-w-lg",
  lg: "max-w-2xl",
  xl: "max-w-4xl",
};

/**
 * Modal genérico: overlay + painel centrado, fecha com Esc e clique no overlay.
 *
 * @example
 * <Modal open={aberto} onClose={() => setAberto(false)} title="Novo caso" size="lg"
 *   footer={<><Button variant="secondary" onClick={fechar}>Cancelar</Button><Button onClick={salvar}>Salvar</Button></>}>
 *   conteúdo…
 * </Modal>
 */
export function Modal({
  open,
  onClose,
  title,
  children,
  wide,
  size,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** Legado — equivale a size="xl". Prefira `size`. */
  wide?: boolean;
  size?: ModalSize;
  footer?: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  const sizeClass = size
    ? modalSizeClasses[size]
    : wide
      ? "max-w-4xl"
      : "max-w-lg";
  return (
    <div className="modal-backdrop animate-fade-in" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          "w-full max-h-[90vh] overflow-auto rounded-2xl border border-slate-200 bg-white shadow-2xl animate-pop",
          sizeClass,
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
        {footer && (
          <div className="sticky bottom-0 z-10 flex items-center justify-end gap-2 border-t border-slate-100 bg-white/95 px-5 py-4 backdrop-blur">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Confirmação forte construída sobre Modal. Com `typeToConfirm`, o botão de
 * confirmação só habilita quando o usuário digita o texto exato (ex.: nome do
 * caso antes de excluir).
 *
 * @example
 * <ConfirmModal
 *   open={confirmando}
 *   onClose={() => setConfirmando(false)}
 *   onConfirm={excluirCaso}
 *   title="Excluir caso"
 *   message="Esta ação move o caso para a lixeira."
 *   typeToConfirm={caso.titulo}
 * />
 */
export function ConfirmModal({
  open,
  onClose,
  onConfirm,
  title = "Confirmar ação",
  message,
  variant = "danger",
  typeToConfirm,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  loading,
  children,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title?: string;
  message?: ReactNode;
  variant?: "danger" | "primary";
  /** Exige digitar este texto exato para habilitar a confirmação. */
  typeToConfirm?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  loading?: boolean;
  children?: ReactNode;
}) {
  const [typed, setTyped] = useState("");
  useEffect(() => {
    if (!open) setTyped("");
  }, [open]);
  const blocked = Boolean(typeToConfirm) && typed !== typeToConfirm;
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      size="sm"
      footer={
        <>
          <Button type="button" variant="secondary" onClick={onClose}>
            {cancelLabel}
          </Button>
          <Button
            type="button"
            variant={variant === "danger" ? "danger" : "primary"}
            disabled={blocked || loading}
            onClick={onConfirm}
            icon={
              loading ? <Loader2 className="h-4 w-4 animate-spin" /> : undefined
            }
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="flex items-start gap-3">
        {variant === "danger" && (
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-danger-50 text-danger-600 ring-1 ring-inset ring-danger-200">
            <AlertTriangle className="h-5 w-5" />
          </div>
        )}
        <div className="min-w-0 flex-1 text-sm text-slate-600">
          {message && <p>{message}</p>}
          {children}
          {typeToConfirm && (
            <div className="mt-4">
              <FieldLabel>
                Digite{" "}
                <span className="font-mono font-semibold text-slate-900">
                  {typeToConfirm}
                </span>{" "}
                para confirmar
              </FieldLabel>
              <Input
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                placeholder={typeToConfirm}
                autoFocus
              />
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}

type DrawerWidth = "sm" | "md" | "lg";

const drawerWidthClasses: Record<DrawerWidth, string> = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-2xl",
};

/**
 * Painel lateral direito deslizante (ajuda contextual, detalhes rápidos).
 * Fecha com Esc e clique no overlay.
 *
 * @example
 * <Drawer open={ajudaAberta} onClose={() => setAjudaAberta(false)} title="Ajuda — Casos" width="md">
 *   conteúdo…
 * </Drawer>
 */
export function Drawer({
  open,
  onClose,
  title,
  children,
  width = "md",
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  width?: DrawerWidth;
  footer?: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 animate-fade-in bg-slate-950/55 backdrop-blur-sm"
      onClick={onClose}
    >
      <aside
        role="dialog"
        aria-modal="true"
        className={cn(
          "absolute inset-y-0 right-0 flex w-full flex-col border-l border-slate-200 bg-white shadow-2xl animate-slide-in-right",
          drawerWidthClasses[width],
        )}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-5 py-4">
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
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
        {footer && (
          <div className="flex shrink-0 items-center justify-end gap-2 border-t border-slate-100 px-5 py-4">
            {footer}
          </div>
        )}
      </aside>
    </div>
  );
}

type AlertVariant = "info" | "success" | "warning" | "danger";

const alertConfig: Record<
  AlertVariant,
  { icon: typeof Info; box: string; iconColor: string; title: string }
> = {
  info: {
    icon: Info,
    box: "border-info-200 bg-info-50 text-info-800",
    iconColor: "text-info-600",
    title: "text-info-900",
  },
  success: {
    icon: CheckCircle2,
    box: "border-success-200 bg-success-50 text-success-800",
    iconColor: "text-success-600",
    title: "text-success-900",
  },
  warning: {
    icon: AlertTriangle,
    box: "border-warn-200 bg-warn-50 text-warn-800",
    iconColor: "text-warn-600",
    title: "text-warn-900",
  },
  danger: {
    icon: AlertCircle,
    box: "border-danger-200 bg-danger-50 text-danger-800",
    iconColor: "text-danger-600",
    title: "text-danger-900",
  },
};

/**
 * Aviso inline com variante semântica.
 *
 * @example
 * <Alert variant="warning" title="Prazo próximo">Vence em 2 dias úteis.</Alert>
 */
export function Alert({
  variant = "info",
  title,
  children,
  className,
}: {
  variant?: AlertVariant;
  title?: string;
  children?: ReactNode;
  className?: string;
}) {
  const config = alertConfig[variant];
  const Icon = config.icon;
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-3 rounded-xl border px-4 py-3 text-sm",
        config.box,
        className,
      )}
    >
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", config.iconColor)} />
      <div className="min-w-0">
        {title && <p className={cn("font-semibold", config.title)}>{title}</p>}
        {children && (
          <div className={title ? "mt-0.5" : undefined}>{children}</div>
        )}
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
      <Loader2 className="h-8 w-8 animate-spin text-primary-600" />
    </div>
  );
}

export function IANotice({
  children = "Rascunho sujeito a revisao humana obrigatoria.",
}: {
  children?: ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-ai-200 bg-ai-50 px-4 py-3 text-sm text-ai-800">
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
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-ai-600 text-white">
            <Bot className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-slate-950">{title}</h2>
            <p className="mt-1 text-xs text-slate-500">{subtitle}</p>
          </div>
        </div>
        {actions && (
          <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>
        )}
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}

export function ConfidenceBadge({ value }: { value?: number | null }) {
  const score =
    typeof value === "number" ? Math.max(0, Math.min(100, value)) : null;
  const tone: Tone =
    score == null
      ? "slate"
      : score >= 80
        ? "green"
        : score >= 60
          ? "amber"
          : "red";
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
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary-700 text-white">
            <FileText className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h1>{title}</h1>
            {subtitle && (
              <p className="mt-1 text-sm text-slate-500">{subtitle}</p>
            )}
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
