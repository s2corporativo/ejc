import { ReactNode, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Bot,
  CheckCircle2,
  Clock,
  Eye,
  FileClock,
  FileText,
  ChevronDown,
  Filter,
  Inbox,
  Info,
  Loader2,
  PauseCircle,
  PenLine,
  PlusCircle,
  ScanSearch,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  X,
  XCircle,
} from "lucide-react";

type Tone =
  | "slate"
  | "blue"
  | "green"
  | "amber"
  | "orange"
  | "red"
  | "purple"
  | "violet"
  | "teal"
  | "ouro";
type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "ai";

const toneClasses: Record<Tone, string> = {
  slate: "bg-slate-100 text-slate-700 ring-slate-200",
  blue: "bg-primary-50 text-primary-700 ring-primary-200",
  green: "bg-success-50 text-success-700 ring-success-200",
  amber: "bg-warn-50 text-warn-700 ring-warn-200",
  // Laranja/violeta/verde-azulado usam a paleta padrão do Tailwind (default
  // preservado porque tailwind.config estende, não substitui, `colors`) para
  // dar tons próprios aos status do Command Center sem inventar novos tokens.
  orange: "bg-orange-50 text-orange-700 ring-orange-200",
  red: "bg-danger-50 text-danger-700 ring-danger-200",
  purple: "bg-ai-50 text-ai-700 ring-ai-200",
  violet: "bg-violet-50 text-violet-700 ring-violet-200",
  teal: "bg-teal-50 text-teal-700 ring-teal-200",
  // Ouro institucional — apenas destaque pontual (nunca tom padrão)
  ouro: "bg-ouro-palha text-ouro-profundo ring-ouro-claro/60",
};

// Barra SUPERIOR de 3px do KPI card (idioma Verdelimp) na cor do
// indicador — mapeada nos tokens de cor EXISTENTES do EJC. Desenhada via
// ::before (mesmo padrão dos KPI cards do dashboard em site-system.css)
// em vez de border-top: as regras globais de `.card` fora de @layer
// (site-system.css `border: 1px solid`, `.ejc-modern-scope :where(.card)`
// com border-color !important e `.dark .card` em index.css) vêm depois na
// cascata e atropelariam utilities `border-t-*` nos dois temas.
const toneBarClasses: Record<Tone, string> = {
  slate: "before:bg-slate-400",
  blue: "before:bg-primary-400",
  green: "before:bg-success-500",
  amber: "before:bg-warn-500",
  orange: "before:bg-orange-500",
  red: "before:bg-danger-500",
  purple: "before:bg-ai-500",
  violet: "before:bg-violet-500",
  teal: "before:bg-teal-500",
  ouro: "before:bg-ouro-claro",
};

// Botões no idioma flat/compacto (padrão Verdelimp, cores EJC): primary
// em ouro CHAPADO #8F7117 (texto branco 4,6:1+ AA, sem gradiente/sombra),
// secundário NEUTRO (branco com borda 1px), ghost terciário.
// Foco com ring dourado acessível.
const buttonClasses: Record<ButtonVariant, string> = {
  primary:
    "bg-ouro text-white hover:bg-ouro-profundo active:bg-ouro-profundo focus:ring-ouro/40",
  secondary:
    "border border-gray-300 bg-white text-slate-700 hover:bg-slate-50 active:bg-slate-100 focus:ring-ouro/30 dark:border-white/[0.14] dark:bg-white/[0.07] dark:text-slate-200 dark:hover:bg-white/[0.12]",
  ghost:
    "bg-transparent text-slate-600 hover:bg-slate-900/[0.05] focus:ring-ouro/30 dark:text-slate-300 dark:hover:bg-white/[0.06]",
  danger:
    "bg-danger-600 text-white hover:bg-danger-700 focus:ring-danger-500/40",
  ai: "bg-ai-600 text-white hover:bg-ai-500 active:bg-ai-700 focus:ring-ai-500/40",
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
  as: Component,
  to,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  children?: ReactNode;
  icon?: ReactNode;
  variant?: ButtonVariant;
  size?: "sm" | "md" | "lg" | "icon";
  as?: typeof Link;
  to?: string;
}) {
  const sizeClass = {
    sm: "h-8 px-3 text-xs",
    md: "h-9 px-4 text-[13px]",
    lg: "h-10 px-5 text-sm",
    icon: "h-9 w-9 p-0",
  }[size];

  const content = (
    <>
      {icon}
      {children}
    </>
  );

  if (Component && to) {
    return (
      <Component
        to={to}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded-lg font-bold transition-all duration-150 ease-out active:scale-[.98]",
          "focus:outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50",
          sizeClass,
          buttonClasses[variant],
          className,
        )}
      >
        {content}
      </Component>
    );
  }

  return (
    <button
      {...props}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg font-bold transition-all duration-150 ease-out active:scale-[.98]",
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

type StatusIcon = typeof CheckCircle2;

// Normaliza um status vindo do backend/telas para uma chave estável:
// minúsculas, sem acento, com `_`/`-`/espaços colapsados. Assim
// "Em Revisão", "em_revisao" e "em-revisao" caem na mesma entrada.
function normalizeStatus(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// Vocabulário canônico de status do EJC Command Center (cor + ÍCONE + texto —
// nunca só cor, cumprindo WCAG 2.2). Sinônimos legados apontam para a mesma
// entrada para não quebrar as telas que já emitem esses valores.
const STATUS_REGISTRY: Record<string, { tone: Tone; icon: StatusIcon; label: string }> = {
  novo: { tone: "blue", icon: PlusCircle, label: "Novo" },
  "em analise": { tone: "purple", icon: ScanSearch, label: "Em análise" },
  triagem: { tone: "purple", icon: ScanSearch, label: "Em análise" },
  "aguardando cliente": { tone: "amber", icon: Clock, label: "Aguardando cliente" },
  "aguardando documento": { tone: "orange", icon: FileClock, label: "Aguardando documento" },
  "em producao": { tone: "blue", icon: PenLine, label: "Em produção" },
  "em revisao": { tone: "violet", icon: Eye, label: "Em revisão" },
  protocolado: { tone: "teal", icon: Send, label: "Protocolado" },
  concluido: { tone: "green", icon: CheckCircle2, label: "Concluído" },
  suspenso: { tone: "slate", icon: PauseCircle, label: "Suspenso" },
  critico: { tone: "red", icon: AlertTriangle, label: "Crítico" },
};

// Tons dos status legados que ainda NÃO fazem parte do vocabulário canônico —
// preservam exatamente a aparência anterior (cor + rótulo, sem ícone).
const LEGACY_STATUS_TONE: Record<string, Tone> = {
  ativo: "green",
  aberto: "green",
  aprovada: "green",
  pago: "green",
  pendente: "amber",
  vencido: "red",
  atrasado: "red",
  cancelado: "red",
  rejeitado: "red",
  ia: "purple",
  rascunho: "slate",
  arquivado: "slate",
  encerrado: "slate",
};

export function StatusBadge({ value }: { value?: string | null }) {
  if (!value) return <Badge tone="slate">sem status</Badge>;
  const key = normalizeStatus(value);
  const meta = STATUS_REGISTRY[key];
  if (meta) {
    const Icon = meta.icon;
    return (
      <Badge tone={meta.tone} className="gap-1">
        <Icon className="h-3 w-3 shrink-0" aria-hidden="true" />
        {meta.label}
      </Badge>
    );
  }
  return (
    <Badge tone={LEGACY_STATUS_TONE[key] || "slate"}>
      {value.replace(/_/g, " ")}
    </Badge>
  );
}

// Grau de risco do caso (baixo/médio/alto/crítico) com cor + ícone + texto.
const RISK_REGISTRY: Record<string, { tone: Tone; icon: StatusIcon; label: string }> = {
  baixo: { tone: "green", icon: ShieldCheck, label: "Risco baixo" },
  medio: { tone: "amber", icon: ShieldAlert, label: "Risco médio" },
  alto: { tone: "orange", icon: ShieldAlert, label: "Risco alto" },
  critico: { tone: "red", icon: ShieldAlert, label: "Risco crítico" },
};

export function RiskBadge({ value }: { value?: string | null }) {
  if (!value) return <Badge tone="slate">Risco —</Badge>;
  const meta = RISK_REGISTRY[normalizeStatus(value)];
  if (!meta) {
    return <Badge tone="slate">Risco {value.replace(/_/g, " ")}</Badge>;
  }
  const Icon = meta.icon;
  return (
    <Badge tone={meta.tone} className="gap-1">
      <Icon className="h-3 w-3 shrink-0" aria-hidden="true" />
      {meta.label}
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
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-black/[0.05] bg-white p-3 shadow-sm">
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
        {eyebrow && <div className="eyebrow mb-1.5">{eyebrow}</div>}
        {/* Título denso (~20px/700) na cor escura da marca + filete ouro */}
        <h1 className="text-xl font-bold tracking-tight text-primary-900">
          {title}
        </h1>
        <div className="mt-1.5 h-0.5 w-10 rounded-full bg-ouro-claro" />
        {subtitle && (
          <p className="mt-1.5 max-w-3xl text-sm text-slate-500">{subtitle}</p>
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
    <Card
      className={cn(
        "relative overflow-hidden rounded-[10px] p-4",
        "before:absolute before:inset-x-0 before:top-0 before:h-[3px] before:content-['']",
        toneBarClasses[tone],
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            {label}
          </p>
          <div className="mt-1.5 text-xl font-bold tracking-tight text-slate-950 tabular-nums">
            {value}
          </div>
          {subtitle && (
            <p className="mt-1 text-xs text-slate-400">{subtitle}</p>
          )}
        </div>
        {icon && (
          <div
            className={cn(
              "rounded-lg p-2 ring-1 ring-inset",
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
                ? "bg-success-50 text-success-700"
                : "bg-danger-50 text-danger-700",
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
        "overflow-hidden rounded-xl border border-black/[0.05] bg-white shadow-sm",
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
  // Segmentado tonal SEM borda; aba ativa em branco elevado com
  // indicador dourado FINO (filete 2px) — dourado como acento cirúrgico.
  return (
    <div className="flex gap-1 overflow-x-auto rounded-xl bg-slate-900/[0.04] p-1 dark:bg-white/[0.06]">
      {items.map((item) => (
        <button
          key={item.value}
          type="button"
          onClick={() => onChange(item.value)}
          className={cn(
            "relative flex h-9 shrink-0 items-center gap-2 rounded-lg px-3 text-sm font-medium transition-all",
            value === item.value
              ? "bg-white text-ouro-profundo shadow-sm after:absolute after:inset-x-3 after:bottom-1 after:h-0.5 after:rounded-full after:bg-ouro-claro dark:bg-white/[0.1] dark:text-[#E5CE7F]"
              : "text-slate-600 hover:bg-slate-900/[0.04] dark:text-slate-300 dark:hover:bg-white/[0.05]",
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
      <summary className="flex h-10 cursor-pointer list-none items-center gap-2 rounded-lg bg-slate-900/[0.05] px-3 text-sm font-medium text-slate-700 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-200 dark:hover:bg-white/[0.12]">
        {label}
        <ChevronDown className="h-4 w-4 text-slate-400" />
      </summary>
      <div className="absolute right-0 z-40 mt-2 min-w-48 rounded-xl border border-slate-200 bg-white p-2 shadow-md">
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
      <span className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 hidden -translate-x-1/2 whitespace-nowrap rounded-md bg-slate-950 px-2 py-1 text-xs text-white shadow-md group-hover:block">
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
          "w-full max-h-[90vh] overflow-auto rounded-2xl border border-slate-200 bg-white shadow-float animate-pop",
          sizeClass,
        )}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-100 bg-white px-5 py-4">
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
          <div className="sticky bottom-0 z-10 flex items-center justify-end gap-2 border-t border-slate-100 bg-white px-5 py-4">
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
      className="fixed inset-0 z-50 animate-fade-in bg-slate-950/45"
      onClick={onClose}
    >
      <aside
        role="dialog"
        aria-modal="true"
        className={cn(
          "absolute inset-y-0 right-0 flex w-full flex-col border-l border-slate-200 bg-white shadow-float animate-slide-in-right",
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

// Skeletons de carregamento (pulse) — implementação em components/base/.
// Re-exportados aqui para manter o ponto único de import das páginas.
export { Skeleton, SkeletonList, SkeletonCard } from "./base/Skeleton";

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

/**
 * Estado de ERRO de carregamento — par do <EmptyState /> para quando a
 * requisição falha (em vez de simplesmente não ter dados). Oferece uma ação
 * de "tentar novamente" para não deixar o usuário sem saída.
 */
export function ErrorState({
  title = "Não foi possível carregar",
  message = "Ocorreu um erro ao buscar estes dados. Tente novamente em instantes.",
  icon: Icon = AlertCircle,
  onRetry,
  retryLabel = "Tentar novamente",
}: {
  title?: string;
  message?: string;
  icon?: typeof AlertCircle;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center rounded-xl border border-dashed border-danger-200 bg-danger-50/40 px-6 py-12 text-center"
    >
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-danger-100 text-danger-600">
        <Icon className="h-6 w-6" />
      </div>
      <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      {message && (
        <p className="mt-1 max-w-md text-sm text-slate-500">{message}</p>
      )}
      {onRetry && (
        <div className="mt-4">
          <Button variant="secondary" onClick={onRetry}>
            {retryLabel}
          </Button>
        </div>
      )}
    </div>
  );
}

/**
 * Empty state didático. API aditiva — os usos legados com `message`/`icon`
 * continuam válidos; os novos podem explicar o vazio e oferecer uma saída.
 *
 * @example legado
 * <Empty message="Nenhum caso encontrado" />
 *
 * @example didático
 * <Empty
 *   titulo="Nenhum caso ainda"
 *   descricao="Cadastre o primeiro caso para acompanhar prazos e honorários."
 *   acao={<Button onClick={abrirWizard}>Novo caso</Button>}
 * />
 */
export function Empty({
  message,
  icon: Icon = Inbox,
  titulo,
  descricao,
  acao,
}: {
  /** Legado — vira o título quando `titulo` não é informado. */
  message?: string;
  icon?: typeof Inbox;
  /** Título curto do estado vazio (tem precedência sobre `message`). */
  titulo?: string;
  /** Texto explicativo: por que está vazio e o que fazer a seguir. */
  descricao?: string;
  /** Ação de saída (ex.: <Button> ou <Link>) exibida abaixo do texto. */
  acao?: ReactNode;
}) {
  return (
    <EmptyState
      title={titulo ?? message ?? "Nada encontrado"}
      message={descricao}
      icon={Icon}
      action={acao}
    />
  );
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center p-12">
      <Loader2 className="h-8 w-8 animate-spin text-ouro" />
    </div>
  );
}

// Barra shimmer branco+ouro (grafite no `.dark`) — reutilizada pelas células
// do SkeletonTable. Decorativa: `aria-hidden` (quem expõe o estado de
// carregamento é o container com role="status"). A classe `.ejc-skeleton`
// (index.css) traz o brilho dourado sutil.
function SkeletonBar({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("ejc-skeleton", className)} />;
}

/**
 * SkeletonTable — placeholder de carregamento no FORMATO de uma tabela,
 * dentro do mesmo container `.card` das listas core (Casos, Clientes).
 * Mostra `rows` linhas × `cols` células com shimmer branco+ouro (grafite no
 * tema escuro) enquanto os dados chegam — evita o "salto" de layout do
 * <Spinner />. Acessível: `role="status"` + `aria-busy` no container (com
 * rótulo sr-only); células individuais `aria-hidden`.
 */
export function SkeletonTable({
  rows = 6,
  cols = 5,
}: {
  rows?: number;
  cols?: number;
}) {
  return (
    <div
      className="card overflow-hidden"
      role="status"
      aria-busy="true"
      aria-live="polite"
    >
      <span className="sr-only">Carregando…</span>
      {/* Cabeçalho */}
      <div className="flex gap-4 border-b border-bronze-pale/40 bg-bronze-50/50 px-4 py-3">
        {Array.from({ length: cols }).map((_, i) => (
          <SkeletonBar key={i} className="h-3 flex-1" />
        ))}
      </div>
      {/* Linhas */}
      <div className="divide-y divide-bronze-pale/40">
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="flex items-center gap-4 px-4 py-3.5">
            {Array.from({ length: cols }).map((_, c) => (
              <SkeletonBar
                key={c}
                className={cn("h-4 flex-1", c === 0 && "max-w-[7rem]")}
              />
            ))}
          </div>
        ))}
      </div>
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

// Ciclo de validação humana de uma saída de IA. Torna EXPLÍCITO o grau de
// confiança editorial — nenhuma conclusão de IA deve parecer um fato já
// confirmado (requisito central do diagnóstico do Command Center).
const VALIDATION_REGISTRY: Record<string, { tone: Tone; icon: StatusIcon; label: string }> = {
  "nao revisado": { tone: "slate", icon: Clock, label: "Não revisado" },
  "em revisao": { tone: "amber", icon: Eye, label: "Em revisão" },
  validado: { tone: "green", icon: CheckCircle2, label: "Validado" },
  rejeitado: { tone: "red", icon: XCircle, label: "Rejeitado" },
  "parcialmente validado": {
    tone: "amber",
    icon: ShieldAlert,
    label: "Parcialmente validado",
  },
};

export function HumanValidationStatus({ value }: { value?: string | null }) {
  const meta = VALIDATION_REGISTRY[normalizeStatus(value || "nao revisado")];
  const resolved = meta ?? VALIDATION_REGISTRY["nao revisado"];
  const Icon = resolved.icon;
  return (
    <Badge tone={resolved.tone} className="gap-1">
      <Icon className="h-3 w-3 shrink-0" aria-hidden="true" />
      {resolved.label}
    </Badge>
  );
}

// Citação de fonte usada por uma resposta de IA (documento, legislação ou
// precedente). Vira link quando há `href`; caso contrário, chip estático.
export function SourceCitation({
  tipo,
  titulo,
  referencia,
  href,
}: {
  tipo?: string;
  titulo: string;
  referencia?: string;
  href?: string;
}) {
  const inner = (
    <span className="inline-flex max-w-full items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-600">
      <FileText className="h-3.5 w-3.5 shrink-0 text-slate-400" />
      {tipo && <span className="font-medium text-slate-500">{tipo}:</span>}
      <span className="truncate">{titulo}</span>
      {referencia && <span className="shrink-0 text-slate-400">· {referencia}</span>}
    </span>
  );
  return href ? (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex max-w-full hover:opacity-80"
    >
      {inner}
    </a>
  ) : (
    inner
  );
}

// Legenda que enquadra a leitura de uma saída de IA: separa o que consta nos
// documentos, o que é inferência do modelo e o que ainda não foi confirmado.
// Reforça, no ponto de consumo, que a IA pode misturar as três coisas.
export function AIFactualityLegend({ className }: { className?: string }) {
  const items: Array<{ tone: Tone; icon: StatusIcon; label: string }> = [
    { tone: "green", icon: CheckCircle2, label: "Consta nos documentos" },
    { tone: "purple", icon: Bot, label: "Inferência da IA" },
    { tone: "amber", icon: AlertTriangle, label: "Não confirmado / lacuna" },
  ];
  return (
    <div
      className={cn(
        "rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2",
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <Badge key={item.label} tone={item.tone} className="gap-1">
              <Icon className="h-3 w-3 shrink-0" aria-hidden="true" />
              {item.label}
            </Badge>
          );
        })}
      </div>
      <p className="mt-1.5 text-[11px] leading-4 text-slate-500">
        A IA pode misturar fatos, inferências e lacunas. Valide cada ponto nas
        fontes antes de usar — a validação profissional continua obrigatória.
      </p>
    </div>
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
