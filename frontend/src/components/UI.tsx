import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { cn } from "../lib/cn";
import {
  AlertCircle,
  AlertTriangle,
  Archive,
  ArrowDown,
  ArrowUp,
  Bot,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  Eye,
  FileClock,
  FileText,
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
  Upload,
  X,
  XCircle,
} from "lucide-react";
import {
  addDays,
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameMonth,
  startOfMonth,
  startOfWeek,
} from "date-fns";
import { ptBR } from "date-fns/locale";
import { Skeleton } from "./base/Skeleton";

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
  | "ai"
  | "ouro";
type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "ai";

const toneClasses: Record<Tone, string> = {
  slate: "bg-slate-100 text-slate-700 ring-slate-200",
  // "blue" é tom INFORMATIVO de status (novo/em análise/em produção…) e
  // usa a paleta `info` (azul céu) — o ouro `primary` fica reservado à
  // marca/ações, para o dourado nunca virar cor de status genérica.
  blue: "bg-info-50 text-info-700 ring-info-200",
  green: "bg-success-50 text-success-700 ring-success-200",
  amber: "bg-warn-50 text-warn-700 ring-warn-200",
  // Laranja/violeta/verde-azulado usam a paleta padrão do Tailwind (default
  // preservado porque tailwind.config estende, não substitui, `colors`) para
  // dar tons próprios aos status do Command Center sem inventar novos tokens.
  orange: "bg-orange-50 text-orange-700 ring-orange-200",
  red: "bg-danger-50 text-danger-700 ring-danger-200",
  // Roxo/violeta legados são neutros informativos; `ai` é exclusivo da IA.
  purple: "bg-info-50 text-info-700 ring-info-200",
  violet: "bg-info-50 text-info-700 ring-info-200",
  teal: "bg-teal-50 text-teal-700 ring-teal-200",
  ai: "bg-ai-50 text-ai-700 ring-ai-200",
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
  blue: "before:bg-info-500",
  green: "before:bg-success-500",
  amber: "before:bg-warn-500",
  orange: "before:bg-orange-500",
  red: "before:bg-danger-500",
  purple: "before:bg-info-500",
  violet: "before:bg-info-500",
  teal: "before:bg-teal-500",
  ai: "before:bg-ai-500",
  ouro: "before:bg-ouro-claro",
};

// Botões no idioma flat/compacto (padrão Verdelimp, cores EJC): primary
// em ouro CHAPADO #8F7117 (texto branco 4,6:1+ AA, sem gradiente/sombra),
// secundário NEUTRO (branco com borda 1px), ghost terciário.
// Foco com ring dourado acessível.
const buttonClasses: Record<ButtonVariant, string> = {
  primary:
    "bg-primary-600 text-white hover:bg-primary-700 active:bg-primary-800 focus:ring-primary-500/40",
  secondary:
    "border border-gray-300 bg-white text-slate-700 hover:bg-slate-50 active:bg-slate-100 focus:ring-primary-500/30 dark:border-white/[0.14] dark:bg-white/[0.07] dark:text-slate-200 dark:hover:bg-white/[0.12]",
  ghost:
    "bg-transparent text-slate-600 hover:bg-slate-900/[0.05] focus:ring-primary-500/30 dark:text-slate-300 dark:hover:bg-white/[0.06]",
  danger:
    "bg-danger-600 text-white hover:bg-danger-700 focus:ring-danger-500/40",
  ai: "bg-ai-600 text-white hover:bg-ai-500 active:bg-ai-700 focus:ring-ai-500/40",
};

// Implementação única em src/lib/cn.ts; re-exportada aqui porque diversos
// consumidores do design system importam `cn` de UI.
export { cn };

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
    md: "h-9 px-4 text-[13px]",
    lg: "h-10 px-5 text-sm",
    icon: "h-9 w-9 p-0",
  }[size];
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
const STATUS_REGISTRY: Record<
  string,
  { tone: Tone; icon: StatusIcon; label: string }
> = {
  novo: { tone: "blue", icon: PlusCircle, label: "Novo" },
  "em analise": { tone: "blue", icon: ScanSearch, label: "Em análise" },
  triagem: { tone: "blue", icon: ScanSearch, label: "Em análise" },
  // Migration 126 — estados novos de caso. `aberto` já tinha tom no mapa
  // legado; `em instrucao` (chave normalizada sem underscore) era buraco.
  aberto: { tone: "green", icon: PlusCircle, label: "Aberto" },
  "em instrucao": { tone: "blue", icon: FileClock, label: "Em instrução" },
  "aguardando cliente": {
    tone: "amber",
    icon: Clock,
    label: "Aguardando cliente",
  },
  "aguardando documento": {
    tone: "orange",
    icon: FileClock,
    label: "Aguardando documento",
  },
  "em producao": { tone: "blue", icon: PenLine, label: "Em produção" },
  "em revisao": { tone: "blue", icon: Eye, label: "Em revisão" },
  protocolado: { tone: "teal", icon: Send, label: "Protocolado" },
  concluido: { tone: "green", icon: CheckCircle2, label: "Concluído" },
  // Estados terminais do ciclo do caso — mesmos ícone+texto em toda tela
  // (antes caíam no mapa legado, sem ícone).
  encerrado: { tone: "slate", icon: CheckCircle2, label: "Encerrado" },
  arquivado: { tone: "slate", icon: Archive, label: "Arquivado" },
  suspenso: { tone: "slate", icon: PauseCircle, label: "Suspenso" },
  critico: { tone: "red", icon: AlertTriangle, label: "Crítico" },
  // Processamento assíncrono do Raio-X (fila → em processamento →
  // aguardando conferência/documentos pendentes, ou erro).
  fila: { tone: "blue", icon: Clock, label: "Na fila" },
  "em processamento": { tone: "blue", icon: FileClock, label: "Processando" },
  "aguardando conferencia": {
    tone: "amber",
    icon: Eye,
    label: "Aguardando conferência",
  },
  "documentos pendentes": {
    tone: "orange",
    icon: FileClock,
    label: "Documentos pendentes",
  },
  erro: { tone: "red", icon: AlertTriangle, label: "Erro" },
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
  ia: "ai",
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
const RISK_REGISTRY: Record<
  string,
  { tone: Tone; icon: StatusIcon; label: string }
> = {
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
    <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wide text-slate-500">
      {children}
      {required && <span className="ml-1 text-danger-500">*</span>}
    </label>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cn("input", props.className)} />;
}

// Checkbox de sigilo reforçado de IA (Issue #1194) — mesmo campo em qualquer
// form de criação/edição de caso; centraliza o texto e o estilo para os dois
// formulários (NovoCasoWizard, Casos.tsx) não divergirem.
export function SigiloReforcadoField({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className="sm:col-span-2">
      <label className="flex items-center gap-2 text-sm text-slate-600">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
        Sigilo reforçado — caso de crime sexual ou envolve menor
      </label>
      <p className="mt-1 text-xs text-slate-400">
        A IA deste caso passa a exigir provedor local (Ollama); nenhum conteúdo
        dele vai a provedor externo, nem pseudonimizado.
      </p>
    </div>
  );
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
      {/* `shrink-0` incondicional anulava o `flex-wrap`: o container ficava preso
          à largura de max-content e TRANSBORDAVA em vez de quebrar a linha —
          116px em /prazos, /agenda, /tarefas e /intimacoes no tablet, e o botão
          primário cortado em /casos no celular.

          Mas removê-lo por completo custou caro do outro lado: com o container
          livre para encolher, o subtítulo (`max-w-3xl`) disputava a linha e as
          ações quebravam em DUAS linhas mesmo a 1440px, onde antes cabiam numa
          só. Medido: /agenda, /intimacoes, /prazos e /tarefas passavam de 647×34
          para 540×75 no desktop.

          `lg:shrink-0` fica com os dois lados: abaixo de 1024px o container pode
          encolher e quebrar a linha (some o transbordo); de 1024px para cima ele
          volta a não encolher, e quem cede espaço é o título — o comportamento
          original. Ambos os regimes conferidos por medição em cinco larguras. */}
      {actions && (
        <div className="flex flex-wrap items-center gap-2 lg:shrink-0">
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
        "relative overflow-hidden rounded-[10px] p-4 hover:shadow-card-hover",
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

// "error" é alias aditivo de "danger" (compatibilidade com telas novas).
type AlertVariant = "info" | "success" | "warning" | "danger" | "error";

const alertConfig: Record<
  Exclude<AlertVariant, "error">,
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
  const config = alertConfig[variant === "error" ? "danger" : variant];
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
const VALIDATION_REGISTRY: Record<
  string,
  { tone: Tone; icon: StatusIcon; label: string }
> = {
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
      {referencia && (
        <span className="shrink-0 text-slate-400">· {referencia}</span>
      )}
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
            {/* h2, não h1: este cabeçalho é de um DOCUMENTO exibido
                dentro de uma página que já tem `PageHeader` como h1.
                Medido em /documentos: dois h1 idênticos ("Documentos"),
                e o leitor de tela perde a âncora da página. */}
            <h2 className="visual-law-document-title">{title}</h2>
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

// Formatadores canônicos pt-BR — implementação única em utils/formato.ts
// (re-export mantido aqui porque ~20 telas já importam de components/UI).
export { fmtMoney, fmtDate, fmtDateTime } from "../utils/formato";

/* ══════════════════════════════════════════════════════════════════════════
   DESIGN SYSTEM CANÔNICO EJC — primitivos da identidade DPT
   (PROMPT MESTRE, seção 11: nenhum módulo inventa novamente estes componentes.)
   Cores/raio/sombra via tokens de src/styles/ejc-tokens.css (grupo tailwind
   `ejc-*`); tipografia display via font-serif (Playfair Display). Tudo com
   foco visível, estados disabled e contraste AA. Tema escuro herda dos tokens.
   ══════════════════════════════════════════════════════════════════════════ */

const EJC_FOCUS =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ejc-focus-ring)]";

/** Botão quadrado só de ícone — `label` é obrigatório (a11y). */
export function IconButton({
  label,
  className,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      {...props}
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex h-9 w-9 items-center justify-center rounded-lg border border-ejc-border bg-ejc-surface text-ejc-text-secondary transition-colors hover:bg-ejc-surface-muted hover:text-ejc-text disabled:cursor-not-allowed disabled:opacity-50",
        EJC_FOCUS,
        className,
      )}
    >
      {children}
    </button>
  );
}

/** Campo de busca com ícone, atalho de teclado opcional e botão de limpar. */
export function SearchInput({
  value,
  onChange,
  onClear,
  placeholder = "Buscar…",
  shortcut,
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & {
  value: string;
  onChange: (value: string) => void;
  onClear?: () => void;
  placeholder?: string;
  /** Ex.: "⌘ K" — exibido à direita quando o campo está vazio. */
  shortcut?: string;
  className?: string;
}) {
  return (
    <div className={cn("relative flex items-center", className)}>
      <Search
        className="pointer-events-none absolute left-3 h-4 w-4 text-ejc-text-subtle"
        aria-hidden="true"
      />
      <input
        {...props}
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={cn(
          "h-10 w-full rounded-lg border border-ejc-border bg-ejc-surface pl-9 pr-9 text-sm text-ejc-text placeholder:text-ejc-text-subtle focus:outline-none focus:ring-2 focus:ring-[var(--ejc-focus-ring)] disabled:cursor-not-allowed disabled:opacity-60",
        )}
      />
      {value ? (
        <button
          type="button"
          onClick={() => {
            onChange("");
            onClear?.();
          }}
          aria-label="Limpar busca"
          className="absolute right-2 rounded-md p-1 text-ejc-text-secondary hover:bg-ejc-surface-muted hover:text-ejc-text"
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      ) : shortcut ? (
        <kbd className="pointer-events-none absolute right-3 rounded border border-ejc-border px-1.5 py-0.5 text-[10px] font-medium text-ejc-text-subtle">
          {shortcut}
        </kbd>
      ) : null}
    </div>
  );
}

/** Painel branco com cabeçalho serifado e rodapé opcional (idioma da referência). */
export function Panel({
  title,
  icon,
  actions,
  footer,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section
      className={cn(
        "overflow-hidden rounded-2xl border border-ejc-border bg-ejc-surface shadow-[var(--ejc-shadow-sm)]",
        className,
      )}
    >
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-ejc-border px-4 py-3">
          <h3 className="flex min-w-0 items-center gap-2 font-serif text-[17px] font-semibold text-ejc-text">
            {icon && (
              <span aria-hidden="true" className="shrink-0 text-ejc-gold-ink">
                {icon}
              </span>
            )}
            <span className="truncate">{title}</span>
          </h3>
          {actions && (
            <div className="flex shrink-0 items-center gap-2">{actions}</div>
          )}
        </header>
      )}
      <div className={cn("p-4", bodyClassName)}>{children}</div>
      {footer && (
        <footer className="border-t border-ejc-border px-4 py-3">
          {footer}
        </footer>
      )}
    </section>
  );
}

const metricToneClasses = {
  default: "border-ejc-border bg-ejc-surface text-ejc-text",
  primary:
    "border-transparent bg-[linear-gradient(160deg,var(--ejc-primary),var(--ejc-primary-dark))] text-white",
} as const;

/** Card de indicador — número + rótulo, clicável (href ou onClick). */
export function MetricCard({
  label,
  value,
  icon,
  tone = "default",
  href,
  onClick,
  className,
}: {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  tone?: keyof typeof metricToneClasses;
  href?: string;
  onClick?: () => void;
  className?: string;
}) {
  const dark = tone === "primary";
  const inner = (
    <>
      {icon && (
        <span
          aria-hidden="true"
          className={cn(
            "flex h-10 w-10 items-center justify-center rounded-xl",
            dark
              ? "bg-white/10 text-ejc-gold-bright"
              : "bg-ejc-gold-soft text-ejc-gold-ink",
          )}
        >
          {icon}
        </span>
      )}
      <div className="mt-3">
        <strong
          className={cn(
            "block font-serif text-[28px] leading-none tracking-tight",
            dark ? "text-white" : "text-ejc-text",
          )}
        >
          {value}
        </strong>
        <small
          className={cn(
            "mt-1.5 block text-[13px] font-medium",
            dark ? "text-white/70" : "text-ejc-text-secondary",
          )}
        >
          {label}
        </small>
      </div>
      <ChevronRight
        aria-hidden="true"
        className={cn(
          "absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2",
          dark ? "text-white/50" : "text-ejc-text-subtle",
        )}
      />
    </>
  );
  const base = cn(
    "relative flex flex-col rounded-2xl border p-5 transition-all",
    metricToneClasses[tone],
    (href || onClick) &&
      "hover:-translate-y-0.5 hover:shadow-[var(--ejc-shadow-md)]",
    EJC_FOCUS,
    className,
  );
  const ariaLabel = `${label}: ${typeof value === "string" || typeof value === "number" ? value : ""}`;
  if (href) {
    return (
      <Link to={href} className={base} aria-label={ariaLabel}>
        {inner}
      </Link>
    );
  }
  if (onClick) {
    return (
      <button type="button" onClick={onClick} className={base} aria-label={ariaLabel}>
        {inner}
      </button>
    );
  }
  return <div className={base}>{inner}</div>;
}

/** Contêiner padrão de página (largura máxima + respiro vertical). */
export function PageContainer({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mx-auto w-full max-w-[1600px] space-y-4", className)}>
      {children}
    </div>
  );
}

export type TabItem = {
  key: string;
  label: ReactNode;
  badge?: ReactNode;
};

/** Abas acessíveis — pílula ativa em esmeralda (idioma da referência). */
export function Tabs({
  items,
  value,
  onChange,
  ariaLabel,
  className,
}: {
  items: readonly TabItem[];
  value: string;
  onChange: (key: string) => void;
  ariaLabel: string;
  className?: string;
}) {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={cn(
        "inline-flex max-w-full items-center gap-1 overflow-x-auto rounded-xl bg-ejc-surface-muted p-1",
        className,
      )}
    >
      {items.map((item) => {
        const active = item.key === value;
        return (
          <button
            key={item.key}
            role="tab"
            type="button"
            aria-selected={active}
            onClick={() => onChange(item.key)}
            className={cn(
              "flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors",
              active
                ? "bg-ejc-primary text-white shadow-[var(--ejc-shadow-sm)]"
                : "text-ejc-text-secondary hover:bg-ejc-surface hover:text-ejc-text",
              EJC_FOCUS,
            )}
          >
            {item.label}
            {item.badge != null && (
              <span
                className={cn(
                  "rounded-full px-1.5 py-0.5 text-[10px] font-semibold",
                  active
                    ? "bg-white/15 text-white"
                    : "bg-ejc-surface text-ejc-text-secondary",
                )}
              >
                {item.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** Janela de páginas com reticências — utilitário do Pagination. */
function paginaWindow(page: number, pageCount: number): (number | "…")[] {
  const pages: (number | "…")[] = [1];
  const start = Math.max(2, page - 1);
  const end = Math.min(pageCount - 1, page + 1);
  if (start > 2) pages.push("…");
  for (let p = start; p <= end; p += 1) pages.push(p);
  if (end < pageCount - 1) pages.push("…");
  if (pageCount >= 2) pages.push(pageCount);
  return pages;
}

/** Paginação canônica com contagem, janela numerada e navegação por teclado. */
export function Pagination({
  page,
  pageCount,
  onChange,
  total,
  unitLabel = "itens",
  className,
}: {
  page: number;
  pageCount: number;
  onChange: (page: number) => void;
  total?: number;
  unitLabel?: string;
  className?: string;
}) {
  if (pageCount <= 1) {
    if (total == null) return null;
    return (
      <div
        className={cn(
          "px-1 py-2 text-xs text-ejc-text-secondary",
          className,
        )}
      >
        {total} {unitLabel}
      </div>
    );
  }
  return (
    <nav
      aria-label="Paginação"
      className={cn(
        "flex items-center justify-between gap-3 px-1 py-2",
        className,
      )}
    >
      <span className="text-xs text-ejc-text-secondary">
        {total != null
          ? `${total} ${unitLabel}`
          : `Página ${page} de ${pageCount}`}
      </span>
      <div className="flex items-center gap-1">
        <IconButton
          label="Página anterior"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        </IconButton>
        {paginaWindow(page, pageCount).map((p, i) =>
          p === "…" ? (
            <span
              key={`gap-${i}`}
              aria-hidden="true"
              className="px-1.5 text-xs text-ejc-text-subtle"
            >
              …
            </span>
          ) : (
            <button
              key={p}
              type="button"
              aria-current={p === page ? "page" : undefined}
              onClick={() => onChange(p)}
              className={cn(
                "h-9 min-w-9 rounded-lg px-2 text-sm font-medium transition-colors",
                p === page
                  ? "bg-ejc-primary text-white"
                  : "text-ejc-text-secondary hover:bg-ejc-surface-muted hover:text-ejc-text",
                EJC_FOCUS,
              )}
            >
              {p}
            </button>
          ),
        )}
        <IconButton
          label="Próxima página"
          disabled={page >= pageCount}
          onClick={() => onChange(page + 1)}
        >
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </IconButton>
      </div>
    </nav>
  );
}

/** Trilha de navegação — último item é a página atual (aria-current). */
export function Breadcrumb({
  items,
  className,
}: {
  items: { label: string; to?: string }[];
  className?: string;
}) {
  return (
    <nav aria-label="Trilha de navegação" className={className}>
      <ol className="flex flex-wrap items-center gap-1.5 text-sm">
        {items.map((item, i) => {
          const last = i === items.length - 1;
          return (
            <li key={`${item.label}-${i}`} className="flex items-center gap-1.5">
              {i > 0 && (
                <ChevronRight
                  aria-hidden="true"
                  className="h-3.5 w-3.5 text-ejc-text-subtle"
                />
              )}
              {!last && item.to ? (
                <Link
                  to={item.to}
                  className="text-ejc-text-secondary transition-colors hover:text-ejc-gold-ink"
                >
                  {item.label}
                </Link>
              ) : (
                <span
                  aria-current={last ? "page" : undefined}
                  className={cn(
                    last && "font-medium text-ejc-text",
                    !last && "text-ejc-text-secondary",
                  )}
                >
                  {item.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/** Barra de filtros — alinhamento e espaçamento canônicos. */
export function FilterBar({
  children,
  ariaLabel = "Filtros",
  className,
}: {
  children: ReactNode;
  ariaLabel?: string;
  className?: string;
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={cn("flex flex-wrap items-center gap-2.5", className)}
    >
      {children}
    </div>
  );
}

/** Passos numerados — concluído (esmeralda), atual (anel ouro), futuro (mudo). */
export function Stepper({
  steps,
  current,
  className,
}: {
  steps: ReactNode[];
  /** Índice do passo atual (0-based). Anteriores são marcados como concluídos. */
  current: number;
  className?: string;
}) {
  return (
    <ol
      aria-label="Etapas"
      className={cn("flex flex-wrap items-center gap-2", className)}
    >
      {steps.map((step, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <li
            key={i}
            aria-current={active ? "step" : undefined}
            className="flex items-center gap-2"
          >
            <span
              className={cn(
                "flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold",
                done && "bg-ejc-primary text-white",
                active &&
                  "bg-ejc-gold-soft text-ejc-gold-ink ring-2 ring-ejc-gold",
                !done && !active && "bg-ejc-surface-muted text-ejc-text-secondary",
              )}
            >
              {done ? (
                <Check className="h-3.5 w-3.5" aria-hidden="true" />
              ) : (
                i + 1
              )}
            </span>
            <span
              className={cn(
                "text-sm",
                active ? "font-semibold text-ejc-text" : "text-ejc-text-secondary",
              )}
            >
              {step}
            </span>
            {i < steps.length - 1 && (
              <span aria-hidden="true" className="mx-1 h-px w-6 bg-ejc-border" />
            )}
          </li>
        );
      })}
    </ol>
  );
}

const timelineDotClasses = {
  gold: "bg-ejc-gold",
  green: "bg-success-500",
  red: "bg-danger-500",
  blue: "bg-info-500",
  gray: "bg-slate-400",
} as const;

/** Linha do tempo vertical — horário, marcador colorido, título e meta. */
export function Timeline({
  items,
  className,
}: {
  items: {
    key?: string;
    title: ReactNode;
    meta?: ReactNode;
    time?: ReactNode;
    dot?: keyof typeof timelineDotClasses;
    onClick?: () => void;
  }[];
  className?: string;
}) {
  return (
    <ol className={cn("space-y-1", className)}>
      {items.map((item, i) => {
        const content = (
          <>
            {item.time != null && (
              <time className="w-11 shrink-0 pt-0.5 text-[13px] font-semibold tabular-nums text-ejc-text">
                {item.time}
              </time>
            )}
            <span
              aria-hidden="true"
              className={cn(
                "mt-1.5 h-2 w-2 shrink-0 rounded-full",
                timelineDotClasses[item.dot ?? "gold"],
              )}
            />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-ejc-text">
                {item.title}
              </span>
              {item.meta != null && (
                <span className="mt-0.5 block truncate text-xs text-ejc-text-secondary">
                  {item.meta}
                </span>
              )}
            </span>
          </>
        );
        return (
          <li key={item.key ?? i}>
            {item.onClick ? (
              <button
                type="button"
                onClick={item.onClick}
                className={cn(
                  "flex w-full items-start gap-3 rounded-xl px-2 py-2.5 text-left transition-colors hover:bg-ejc-surface-muted",
                  EJC_FOCUS,
                )}
              >
                {content}
              </button>
            ) : (
              <div className="flex w-full items-start gap-3 px-2 py-2.5 text-left">
                {content}
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}

export type ActionMenuItem = {
  label: string;
  icon?: ReactNode;
  onSelect: () => void;
  danger?: boolean;
  disabled?: boolean;
};

/** Menu de ações — popover com fecho por Esc/clique externo e foco gerenciado. */
export function ActionMenu({
  trigger,
  items,
  align = "right",
  className,
  triggerClassName,
}: {
  trigger: ReactNode;
  items: ActionMenuItem[];
  align?: "left" | "right";
  className?: string;
  triggerClassName?: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const firstItemRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent | TouchEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    firstItemRef.current?.focus();
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={rootRef} className={cn("relative inline-block", className)}>
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "inline-flex h-9 items-center gap-1.5 rounded-lg border border-ejc-border bg-ejc-surface px-3 text-sm font-medium text-ejc-text transition-colors hover:bg-ejc-surface-muted",
          EJC_FOCUS,
          triggerClassName,
        )}
      >
        {trigger}
        <ChevronDown
          aria-hidden="true"
          className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")}
        />
      </button>
      {open && (
        <div
          role="menu"
          aria-orientation="vertical"
          className={cn(
            "absolute z-50 mt-2 min-w-[13rem] overflow-hidden rounded-xl border border-ejc-border bg-ejc-surface py-1 shadow-[var(--ejc-shadow-lg)] animate-pop",
            align === "right" ? "right-0" : "left-0",
          )}
        >
          {items.map((item, i) => (
            <button
              key={item.label}
              ref={i === 0 ? firstItemRef : undefined}
              role="menuitem"
              type="button"
              disabled={item.disabled}
              onClick={() => {
                setOpen(false);
                item.onSelect();
              }}
              className={cn(
                "flex w-full items-center gap-2.5 px-3.5 py-2 text-left text-sm focus-visible:bg-ejc-surface-muted focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50",
                item.danger
                  ? "text-danger-600 hover:bg-danger-50"
                  : "text-ejc-text hover:bg-ejc-surface-muted",
              )}
            >
              {item.icon && (
                <span aria-hidden="true" className="text-ejc-text-secondary">
                  {item.icon}
                </span>
              )}
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export type ComboboxOption = { value: string; label: string };

/** Seleção canônica (select nativo estilizado — acessível por padrão). */
export function Combobox({
  value,
  onChange,
  options,
  placeholder,
  ariaLabel,
  name,
  disabled,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  options: ComboboxOption[];
  placeholder?: string;
  ariaLabel?: string;
  name?: string;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("relative", className)}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={ariaLabel}
        name={name}
        disabled={disabled}
        className="h-10 w-full appearance-none rounded-lg border border-ejc-border bg-ejc-surface px-3 pr-9 text-sm text-ejc-text transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--ejc-focus-ring)] disabled:cursor-not-allowed disabled:opacity-60"
      >
        {placeholder != null && <option value="">{placeholder}</option>}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <ChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ejc-text-subtle"
      />
    </div>
  );
}

/** Campo de data nativo estilizado (o browser fornece o calendário). */
export function DatePicker({
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className={cn("relative", className)}>
      <input
        type="date"
        {...props}
        className="h-10 w-full rounded-lg border border-ejc-border bg-ejc-surface px-3 pr-9 text-sm text-ejc-text transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--ejc-focus-ring)] disabled:cursor-not-allowed disabled:opacity-60"
      />
      <CalendarDays
        aria-hidden="true"
        className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ejc-text-subtle"
      />
    </div>
  );
}

/** Calendário mensal canônico — marca eventos, hoje (ouro) e dia selecionado. */
export function Calendar({
  month,
  initialMonth,
  events,
  selected,
  onSelectDay,
  onMonthChange,
  className,
}: {
  /** Mês controlado (opcional). Sem ele o componente navega internamente. */
  month?: Date;
  initialMonth?: Date;
  /** Datas ISO "yyyy-MM-dd" que recebem marcador dourado. */
  events?: Iterable<string>;
  /** Data ISO selecionada (anel ouro). */
  selected?: string;
  onSelectDay?: (iso: string) => void;
  onMonthChange?: (month: Date) => void;
  className?: string;
}) {
  const [mesInterno, setMesInterno] = useState<Date>(() =>
    startOfMonth(initialMonth ?? new Date()),
  );
  const mesVisivel = month ? startOfMonth(month) : mesInterno;

  const trocarMes = (delta: number) => {
    const proximo = addMonths(mesVisivel, delta);
    if (!month) setMesInterno(proximo);
    onMonthChange?.(proximo);
  };

  const eventosSet = useMemo(
    () => new Set(events ? Array.from(events) : []),
    [events],
  );

  const dias = useMemo(() => {
    const inicio = startOfWeek(mesVisivel, { weekStartsOn: 0 });
    const fim = endOfWeek(endOfMonth(mesVisivel), { weekStartsOn: 0 });
    return eachDayOfInterval({ start: inicio, end: fim });
  }, [mesVisivel]);

  const dow = useMemo(() => {
    const domingo = startOfWeek(mesVisivel, { weekStartsOn: 0 });
    return Array.from({ length: 7 }, (_, i) =>
      format(addDays(domingo, i), "EEEEE", { locale: ptBR }),
    );
  }, [mesVisivel]);

  const hojeISO = format(new Date(), "yyyy-MM-dd");
  const rotuloMes = (() => {
    const texto = format(mesVisivel, "MMMM 'de' yyyy", { locale: ptBR });
    return texto.charAt(0).toUpperCase() + texto.slice(1);
  })();

  return (
    <section
      aria-label="Calendário"
      className={cn(
        "rounded-2xl border border-ejc-border bg-ejc-surface p-4",
        className,
      )}
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <strong className="min-w-0 truncate font-serif text-[15px] text-ejc-text">
          {rotuloMes}
        </strong>
        <span className="flex shrink-0 items-center gap-1">
          <IconButton label="Mês anterior" onClick={() => trocarMes(-1)}>
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          </IconButton>
          <IconButton label="Mês seguinte" onClick={() => trocarMes(1)}>
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </IconButton>
        </span>
      </div>
      <div className="grid grid-cols-7 gap-y-1 text-center">
        {dow.map((d, i) => (
          <span
            key={`${d}-${i}`}
            aria-hidden="true"
            className="pb-1 text-[11px] font-semibold uppercase text-ejc-text-subtle"
          >
            {d}
          </span>
        ))}
        {dias.map((dia) => {
          const iso = format(dia, "yyyy-MM-dd");
          const temEvento = eventosSet.has(iso);
          const isHoje = iso === hojeISO;
          const isSelecionado = selected === iso;
          return (
            <button
              key={iso}
              type="button"
              aria-label={format(dia, "dd 'de' MMMM 'de' yyyy", { locale: ptBR })}
              aria-current={isHoje ? "date" : undefined}
              onClick={() => onSelectDay?.(iso)}
              className={cn(
                "relative mx-auto flex h-8 w-8 items-center justify-center rounded-full text-[13px] transition-colors",
                !isSameMonth(dia, mesVisivel) && "text-ejc-text-subtle/60",
                isSameMonth(dia, mesVisivel) &&
                  !isHoje &&
                  "text-ejc-text hover:bg-ejc-surface-muted",
                isHoje && "bg-ejc-gold font-semibold text-ejc-primary-dark",
                isSelecionado && !isHoje && "ring-2 ring-ejc-gold",
                EJC_FOCUS,
              )}
            >
              {format(dia, "d")}
              {temEvento && (
                <i
                  aria-hidden="true"
                  className="absolute bottom-0.5 h-1 w-1 rounded-full bg-ejc-gold-deep"
                />
              )}
            </button>
          );
        })}
      </div>
    </section>
  );
}

/** Zona de upload — arrastar-e-soltar + seleção, com lista de arquivos. */
export function FileUploader({
  onFilesChange,
  accept,
  multiple = true,
  disabled,
  hint,
  className,
}: {
  onFilesChange: (files: File[]) => void;
  accept?: string;
  multiple?: boolean;
  disabled?: boolean;
  hint?: string;
  className?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);

  const emit = (next: File[]) => {
    setFiles(next);
    onFilesChange(next);
  };

  return (
    <div className={className}>
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => {
          if (!disabled && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (disabled) return;
          const dropped = Array.from(e.dataTransfer.files);
          emit(multiple ? [...files, ...dropped] : dropped.slice(0, 1));
        }}
        aria-disabled={disabled}
        aria-label="Enviar arquivos"
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-2xl border border-dashed px-6 py-8 text-center transition-colors",
          dragging
            ? "border-ejc-gold bg-ejc-gold-soft/40"
            : "border-ejc-border-strong bg-ejc-surface-muted hover:border-ejc-gold",
          disabled && "cursor-not-allowed opacity-60",
          EJC_FOCUS,
        )}
      >
        <Upload className="h-5 w-5 text-ejc-gold-ink" aria-hidden="true" />
        <p className="text-sm font-medium text-ejc-text">
          Arraste arquivos aqui ou clique para selecionar
        </p>
        {hint && <p className="text-xs text-ejc-text-secondary">{hint}</p>}
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          multiple={multiple}
          disabled={disabled}
          className="hidden"
          onChange={(e) => {
            const selected = Array.from(e.target.files ?? []);
            emit(multiple ? [...files, ...selected] : selected.slice(0, 1));
            e.target.value = "";
          }}
        />
      </div>
      {files.length > 0 && (
        <ul className="mt-2.5 space-y-1.5">
          {files.map((file, i) => (
            <li
              key={`${file.name}-${i}`}
              className="flex items-center gap-3 rounded-lg border border-ejc-border bg-ejc-surface px-3 py-2 text-sm"
            >
              <span className="min-w-0 flex-1 truncate text-ejc-text">
                {file.name}
              </span>
              <span className="shrink-0 text-xs text-ejc-text-secondary">
                {(file.size / 1024).toFixed(0)} KB
              </span>
              <button
                type="button"
                onClick={() => emit(files.filter((_, idx) => idx !== i))}
                aria-label={`Remover ${file.name}`}
                className="shrink-0 rounded-md p-1 text-ejc-text-secondary transition-colors hover:bg-ejc-surface-muted hover:text-danger-600"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export type DataGridColumn<T> = {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  className?: string;
  align?: "left" | "center" | "right";
};

/**
 * Grade de dados canônica — Table + estado vazio + skeleton + paginação.
 * Para casos que escapam do formato, componha `Table` diretamente.
 */
export function DataGrid<T>({
  columns,
  rows,
  keyOf,
  loading = false,
  empty,
  page,
  pageCount,
  total,
  onPageChange,
  unitLabel,
  className,
}: {
  columns: DataGridColumn<T>[];
  rows: T[];
  keyOf: (row: T, index: number) => string;
  loading?: boolean;
  empty?: ReactNode;
  page?: number;
  pageCount?: number;
  total?: number;
  onPageChange?: (page: number) => void;
  unitLabel?: string;
  className?: string;
}) {
  const alignClass = {
    left: "text-left",
    center: "text-center",
    right: "text-right",
  } as const;

  return (
    <div className={className}>
      {loading ? (
        <div className="space-y-2 rounded-2xl border border-ejc-border bg-ejc-surface p-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-2xl border border-ejc-border bg-ejc-surface p-2">
          {empty ?? <EmptyState title="Nenhum registro" />}
        </div>
      ) : (
        <Table>
          <THead>
            <TR zebra={false}>
              {columns.map((col) => (
                <TH
                  key={col.key}
                  className={cn(
                    "px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-ejc-text-secondary",
                    alignClass[col.align ?? "left"],
                    col.className,
                  )}
                >
                  {col.header}
                </TH>
              ))}
            </TR>
          </THead>
          <tbody>
            {rows.map((row, i) => (
              <TR key={keyOf(row, i)}>
                {columns.map((col) => (
                  <TD
                    key={col.key}
                    className={cn(
                      "text-ejc-text",
                      alignClass[col.align ?? "left"],
                      col.className,
                    )}
                  >
                    {col.render(row)}
                  </TD>
                ))}
              </TR>
            ))}
          </tbody>
        </Table>
      )}
      {page != null && pageCount != null && onPageChange && (
        <Pagination
          page={page}
          pageCount={pageCount}
          onChange={onPageChange}
          total={total}
          unitLabel={unitLabel}
        />
      )}
    </div>
  );
}
