import { useState, useEffect, useCallback, useMemo } from "react";
import { useSearchParams, Link } from "react-router-dom";
import {
  PageHeader,
  Spinner,
  Empty,
  EmptyState,
  ErrorState,
} from "../components/UI";
import { toast } from "../components/Toast";
import {
  Calendar,
  CalendarClock,
  ChevronDown,
  Clock,
  CheckCircle,
  ExternalLink,
  Filter,
  List,
  LayoutGrid,
  Bell,
  FileText,
  Gavel,
  Pause,
  ClipboardList,
  Users,
  UserPlus,
  User as UserIcon,
  MapPin,
  Plus,
  AlertTriangle,
  X,
} from "lucide-react";
import api from "../lib/api";
import { asList } from "../lib/list";
import { addCaseContext, readCaseContext } from "../lib/caseContext";
import { Modal } from "../components/UI";

type ItemType =
  | "prazo"
  | "tarefa"
  | "suspensao"
  | "intimacao"
  | "audiencia"
  | "reuniao"
  | "compromisso"
  | "diligencia";

const ITEM_TYPES: readonly ItemType[] = [
  "prazo",
  "tarefa",
  "suspensao",
  "intimacao",
  "audiencia",
  "reuniao",
  "compromisso",
  "diligencia",
];

export function isItemType(value: string | null): value is ItemType {
  return ITEM_TYPES.includes(value as ItemType);
}

/** Fonte (router de backend) que serve o item — decide quais ações existem. */
type Fonte = "prazo" | "tarefa" | "agenda" | "intimacao" | "suspensao";

/** Evento colidente devolvido por POST/PATCH /agenda-eventos/ no campo
 *  `conflito_agenda` (double-booking: AVISA, não bloqueia). */
interface ConflitoEvento {
  id: string;
  titulo: string;
  tipo?: string | null;
  data_evento?: string | null;
  hora?: string | null;
  local?: string | null;
}

/** Extrai a lista de conflitos da resposta do backend com segurança. */
function extrairConflitos(data: unknown): ConflitoEvento[] {
  const lista = (data as { conflito_agenda?: unknown } | null)?.conflito_agenda;
  return Array.isArray(lista) ? (lista as ConflitoEvento[]) : [];
}

export type ActivityView = "lista" | "calendario" | "timeline" | "kanban";

export function isActivityView(value: string | null): value is ActivityView {
  return ["lista", "calendario", "timeline", "kanban"].includes(value ?? "");
}

/** Situações REAIS existentes nos modelos do backend:
 *  - deadlines: pendente | concluido | vencido | cancelado
 *  - tasks: a_fazer | fazendo | concluida
 *  - agenda_eventos: pendente | concluido
 *  - intimações (DJEN): pendente | tratada
 *  - suspensões: sem status (informativas)
 */
export type Situacao = "nao_tratado" | "em_execucao" | "concluido" | "cancelado";

/** Colunas do kanban / filtro de situação: cancelado NÃO tem coluna própria —
 *  agrupa com concluído, mas mantém rótulo/estilo distintos (badge neutra). */
export type SituacaoColuna = Exclude<Situacao, "cancelado">;

export function situacaoDe(status?: string | null): Situacao {
  const s = (status ?? "").toLowerCase();
  if (s === "cancelado") return "cancelado"; // NÃO é concluído — rótulo próprio
  if (["concluido", "concluida", "tratada"].includes(s)) return "concluido";
  if (s === "fazendo") return "em_execucao";
  return "nao_tratado"; // pendente, a_fazer, vencido, sem status
}

/** Agrupamento para coluna do kanban e filtro (cancelado → junto de concluído). */
export function situacaoColunaDe(status?: string | null): SituacaoColuna {
  const s = situacaoDe(status);
  return s === "cancelado" ? "concluido" : s;
}

/** A view vw_atividades devolve tipo 'agenda' para eventos; o subtipo real
 *  (reuniao/audiencia/diligencia/compromisso) vem de /agenda-eventos/. */
export function mapAgendaTipo(tipo?: string | null): ItemType {
  if (
    tipo === "reuniao" ||
    tipo === "audiencia" ||
    tipo === "diligencia" ||
    tipo === "compromisso"
  )
    return tipo;
  return "compromisso"; // 'outro' e desconhecidos
}

interface Activity {
  id: string;
  tipo: ItemType;
  fonte: Fonte;
  titulo: string;
  descricao?: string;
  date: string;
  dias_restantes?: number;
  urgencia?: string;
  status: string;
  case_id?: string;
  caso_titulo?: string;
  responsavel_id?: string;
  prioridade?: string;
  hora?: string;
  local?: string;
  origem: string;
}

interface Responsavel {
  id: string;
  nome: string;
  role?: string;
}

function fmtDate(d: string) {
  if (!d) return "—";
  const dt = new Date(d.includes("T") ? d : d + "T12:00:00");
  return dt.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function fmtRelative(dias?: number) {
  if (dias === undefined || dias === null) return "";
  if (dias < 0) return `${Math.abs(dias)}d atraso`;
  if (dias === 0) return "Hoje";
  if (dias === 1) return "Amanhã";
  return `em ${dias}d`;
}

const URGENCIA_COLOR: Record<string, string> = {
  vencido: "text-danger-700 bg-danger-50 border-danger-200",
  critico: "text-orange-700 bg-orange-50 border-orange-200",
  atencao: "text-yellow-700 bg-yellow-50 border-yellow-200",
  normal: "text-slate-600 bg-white border-slate-200",
};

const PRIO_COLOR: Record<string, string> = {
  alta: "bg-danger-100 text-danger-700",
  media: "bg-warn-100 text-warn-700",
  baixa: "bg-slate-100 text-slate-500",
};

const TIPO_CONFIG: Record<
  ItemType,
  { label: string; icon: React.ElementType; color: string }
> = {
  prazo: { label: "Prazo", icon: Clock, color: "text-danger-600" },
  tarefa: { label: "Tarefa", icon: ClipboardList, color: "text-primary-600" },
  suspensao: { label: "Suspensão", icon: Pause, color: "text-ai-600" },
  intimacao: { label: "Intimação", icon: Bell, color: "text-warn-600" },
  audiencia: { label: "Audiência", icon: Gavel, color: "text-rose-600" },
  reuniao: { label: "Reunião", icon: Users, color: "text-cyan-600" },
  compromisso: {
    label: "Compromisso",
    icon: Calendar,
    color: "text-primary-600",
  },
  diligencia: { label: "Diligência", icon: MapPin, color: "text-success-600" },
};

const SITUACAO_CONFIG: { key: SituacaoColuna; label: string; cor: string }[] = [
  { key: "nao_tratado", label: "Não tratado", cor: "bg-slate-400" },
  { key: "em_execucao", label: "Em execução", cor: "bg-primary-500" },
  { key: "concluido", label: "Concluído", cor: "bg-success-500" },
];

function tipoCfg(tipo: ItemType) {
  return TIPO_CONFIG[tipo] ?? TIPO_CONFIG.compromisso;
}

function apiErro(e: unknown, fallback: string): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response
    ?.data?.detail;
  return typeof detail === "string" ? detail : fallback;
}

/** Metadados extras exibidos quando os endpoints já os fornecem. */
function ActivityMeta({
  item,
  nomeDe,
}: {
  item: Activity;
  nomeDe: (id?: string) => string | undefined;
}) {
  const resp = nomeDe(item.responsavel_id);
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-1">
      {item.caso_titulo &&
        (item.case_id ? (
          <Link
            to={`/casos/${item.case_id}`}
            className="text-xs text-primary-600 hover:underline truncate max-w-[220px]"
            title="Abrir caso"
          >
            {item.caso_titulo}
          </Link>
        ) : (
          <span className="text-xs text-slate-400 truncate max-w-[220px]">
            {item.caso_titulo}
          </span>
        ))}
      {resp && (
        <span className="inline-flex items-center gap-1 text-xs text-slate-500">
          <UserIcon className="w-3 h-3" /> {resp}
        </span>
      )}
      {item.prioridade && (
        <span
          className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${PRIO_COLOR[item.prioridade] ?? PRIO_COLOR.baixa}`}
        >
          {item.prioridade}
        </span>
      )}
      {(item.hora || item.local) && (
        <span className="text-xs text-slate-400 truncate">
          {[item.hora, item.local].filter(Boolean).join(" · ")}
        </span>
      )}
      <span className="text-[10px] text-slate-400 uppercase tracking-wide">
        {item.origem}
      </span>
    </div>
  );
}

function ActivityRow({
  item,
  nomeDe,
  onConcluir,
  onReagendar,
  onAtribuir,
  podeAtribuir,
}: {
  item: Activity;
  nomeDe: (id?: string) => string | undefined;
  onConcluir: (item: Activity) => void;
  onReagendar: (item: Activity) => void;
  onAtribuir: (item: Activity) => void;
  podeAtribuir: boolean;
}) {
  const cfg = tipoCfg(item.tipo);
  const Icon = cfg.icon;
  const urg = item.urgencia ?? "normal";
  const situ = situacaoDe(item.status);
  // Cancelado também é estado final: sem destaque de urgência nem ação de
  // concluir — mas com badge própria (neutra), não o selo verde "Concluído".
  const finalizado = situ === "concluido" || situ === "cancelado";
  const podeConcluir =
    !finalizado &&
    ["prazo", "tarefa", "agenda", "intimacao"].includes(item.fonte);
  const podeReagendar = ["prazo", "tarefa", "agenda"].includes(item.fonte);
  const btn =
    "p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors";
  return (
    <div
      className={`flex items-start gap-3 px-4 py-3 border-b border-slate-100 hover:bg-slate-50/60 transition-colors last:border-0 ${urg === "vencido" && !finalizado ? "bg-danger-50/30" : urg === "critico" && !finalizado ? "bg-orange-50/20" : ""}`}
    >
      <div className={`mt-0.5 flex-shrink-0 ${cfg.color}`}>
        <Icon className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <p
            className={`text-sm font-medium leading-snug ${finalizado ? "text-slate-400 line-through" : "text-slate-800"}`}
          >
            {item.titulo}
          </p>
          <div className="flex items-center gap-2 flex-shrink-0">
            {situ === "concluido" ? (
              <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full border text-success-700 bg-success-50 border-success-200">
                Concluído
              </span>
            ) : situ === "cancelado" ? (
              <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full border text-slate-500 bg-slate-50 border-slate-200">
                Cancelado
              </span>
            ) : (
              <span
                className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${URGENCIA_COLOR[urg]}`}
              >
                {fmtRelative(item.dias_restantes)}
              </span>
            )}
            <span className="text-[10px] text-slate-400 uppercase font-medium">
              {cfg.label}
            </span>
          </div>
        </div>
        <ActivityMeta item={item} nomeDe={nomeDe} />
        {item.descricao && (
          <p className="text-xs text-slate-500 mt-0.5 truncate">
            {item.descricao}
          </p>
        )}
        <div className="flex items-center justify-between mt-1">
          <p className="text-[10px] text-slate-400">{fmtDate(item.date)}</p>
          <div className="flex items-center gap-0.5">
            {item.case_id && (
              <Link
                to={`/casos/${item.case_id}`}
                className={btn}
                title="Abrir caso"
                aria-label="Abrir caso"
              >
                <ExternalLink className="w-3.5 h-3.5" />
              </Link>
            )}
            {podeReagendar && (
              <button
                onClick={() => onReagendar(item)}
                className={btn}
                title="Reagendar"
                aria-label="Reagendar"
              >
                <CalendarClock className="w-3.5 h-3.5" />
              </button>
            )}
            {podeAtribuir && ["prazo", "tarefa"].includes(item.fonte) && (
              <button
                onClick={() => onAtribuir(item)}
                className={btn}
                title="Atribuir responsável"
                aria-label="Atribuir responsável"
              >
                <UserPlus className="w-3.5 h-3.5" />
              </button>
            )}
            {podeConcluir && (
              <button
                onClick={() => onConcluir(item)}
                className={`${btn} hover:text-success-700`}
                title={
                  item.fonte === "intimacao"
                    ? "Confirmar (marcar como tratada)"
                    : "Concluir"
                }
                aria-label={
                  item.fonte === "intimacao"
                    ? "Confirmar intimação"
                    : "Concluir"
                }
              >
                <CheckCircle className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function CalendarView({ items }: { items: Activity[] }) {
  const today = new Date();
  const [month, setMonth] = useState(today.getMonth());
  const [year, setYear] = useState(today.getFullYear());

  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const firstDay = new Date(year, month, 1).getDay();

  const itemsByDay = useMemo(() => {
    const map: Record<string, Activity[]> = {};
    items.forEach((item) => {
      const d = item.date?.slice(0, 10);
      if (d) map[d] = [...(map[d] ?? []), item];
    });
    return map;
  }, [items]);

  const monthNames = [
    "Jan",
    "Fev",
    "Mar",
    "Abr",
    "Mai",
    "Jun",
    "Jul",
    "Ago",
    "Set",
    "Out",
    "Nov",
    "Dez",
  ];
  const dayNames = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];

  function prevMonth() {
    if (month === 0) {
      setMonth(11);
      setYear((y) => y - 1);
    } else setMonth((m) => m - 1);
  }

  function nextMonth() {
    if (month === 11) {
      setMonth(0);
      setYear((y) => y + 1);
    } else setMonth((m) => m + 1);
  }

  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
        <button
          onClick={prevMonth}
          aria-label="Mês anterior"
          title="Mês anterior"
          className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors text-slate-500"
        >
          ◂
        </button>
        <h3 className="font-semibold text-slate-800">
          {monthNames[month]} {year}
        </h3>
        <button
          onClick={nextMonth}
          aria-label="Próximo mês"
          title="Próximo mês"
          className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors text-slate-500"
        >
          ▸
        </button>
      </div>
      <div className="p-3">
        <div className="grid grid-cols-7 gap-1 mb-1">
          {dayNames.map((d) => (
            <div
              key={d}
              className="text-center text-[10px] font-semibold text-slate-400 py-1"
            >
              {d}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7 gap-1">
          {Array.from({ length: firstDay }).map((_, i) => (
            <div key={`e${i}`} />
          ))}
          {Array.from({ length: daysInMonth }).map((_, i) => {
            const day = i + 1;
            const key = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
            const dayItems = itemsByDay[key] ?? [];
            const isToday =
              day === today.getDate() &&
              month === today.getMonth() &&
              year === today.getFullYear();
            const hasUrgent = dayItems.some((it) =>
              ["vencido", "critico"].includes(it.urgencia ?? ""),
            );
            return (
              <div
                key={day}
                className={`relative min-h-[44px] rounded-lg p-1 text-center cursor-default
                ${isToday ? "bg-primary-600 text-white" : dayItems.length > 0 ? "bg-slate-50 hover:bg-slate-100" : ""}
                transition-colors`}
                title={dayItems.map((it) => it.titulo).join(", ")}
              >
                <span
                  className={`text-xs font-medium ${isToday ? "text-white" : "text-slate-700"}`}
                >
                  {day}
                </span>
                {dayItems.length > 0 && (
                  <div className="flex flex-wrap gap-0.5 justify-center mt-0.5">
                    {dayItems.slice(0, 3).map((it, idx) => (
                      <div
                        key={idx}
                        className={`w-1.5 h-1.5 rounded-full ${
                          it.tipo === "prazo"
                            ? hasUrgent
                              ? "bg-danger-500"
                              : "bg-danger-300"
                            : it.tipo === "tarefa"
                              ? "bg-primary-400"
                              : it.tipo === "suspensao"
                                ? "bg-ai-400"
                                : "bg-warn-400"
                        }`}
                      />
                    ))}
                    {dayItems.length > 3 && (
                      <span className="text-[9px] text-slate-500">
                        +{dayItems.length - 3}
                      </span>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function TimelineView({ items }: { items: Activity[] }) {
  const grupos: { titulo: string; cor: string; itens: Activity[] }[] = [
    {
      titulo: "Vencidos",
      cor: "bg-danger-500",
      itens: items.filter((i) => (i.dias_restantes ?? 1) < 0),
    },
    {
      titulo: "Hoje",
      cor: "bg-orange-500",
      itens: items.filter((i) => i.dias_restantes === 0),
    },
    {
      titulo: "Próximos 7 dias",
      cor: "bg-warn-500",
      itens: items.filter(
        (i) => (i.dias_restantes ?? 99) > 0 && (i.dias_restantes ?? 99) <= 7,
      ),
    },
    {
      titulo: "Depois",
      cor: "bg-slate-400",
      itens: items.filter((i) => (i.dias_restantes ?? 99) > 7),
    },
    {
      titulo: "Sem data",
      cor: "bg-slate-300",
      itens: items.filter(
        (i) => i.dias_restantes === undefined || i.dias_restantes === null,
      ),
    },
  ].filter((g) => g.itens.length > 0);

  if (items.length === 0) {
    return (
      <EmptyState
        icon={CheckCircle}
        title="Nenhuma atividade na linha do tempo"
      />
    );
  }

  return (
    <div className="card p-5">
      <div className="relative pl-6">
        <div className="absolute left-2 top-1 bottom-1 w-px bg-slate-200" />
        {grupos.map((g) => (
          <div key={g.titulo} className="mb-6 last:mb-0">
            <div className="flex items-center gap-2 mb-3 -ml-6">
              <span
                className={`w-4 h-4 rounded-full ${g.cor} ring-4 ring-white relative z-10`}
              />
              <span className="text-sm font-semibold text-slate-700">
                {g.titulo}
              </span>
              <span className="text-xs text-slate-400">({g.itens.length})</span>
            </div>
            <div className="space-y-2">
              {g.itens.map((item) => {
                const cfg = tipoCfg(item.tipo);
                const Icon = cfg.icon;
                return (
                  <div
                    key={`${item.fonte}-${item.id}`}
                    className="flex items-start gap-2.5 bg-slate-50/60 rounded-lg px-3 py-2"
                  >
                    <Icon
                      className={`w-4 h-4 mt-0.5 flex-shrink-0 ${cfg.color}`}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-slate-700 truncate">
                        {item.titulo}
                      </p>
                      {item.caso_titulo && (
                        <p className="text-xs text-slate-400 truncate">
                          {item.caso_titulo}
                        </p>
                      )}
                    </div>
                    <span className="text-xs text-slate-400 flex-shrink-0">
                      {fmtRelative(item.dias_restantes)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Kanban por SITUAÇÃO (não tratado | em execução | concluído) — os únicos
 *  estados que existem de fato nos modelos. Arrastar um cartão muda o status
 *  no backend quando o tipo suporta a transição. */
function KanbanAtividades({
  items,
  nomeDe,
  onMove,
}: {
  items: Activity[];
  nomeDe: (id?: string) => string | undefined;
  onMove: (item: Activity, alvo: Situacao) => void;
}) {
  const [drag, setDrag] = useState<string | null>(null);
  if (items.length === 0) {
    return <Empty message="Nada na agenda" />;
  }
  return (
    <div className="flex gap-3 overflow-x-auto pb-3">
      {SITUACAO_CONFIG.map(({ key, label, cor }) => {
        // Cancelado divide a coluna "Concluído", mas com badge própria no cartão.
        const itens = items.filter((i) => situacaoColunaDe(i.status) === key);
        return (
          <div
            key={key}
            className="flex-shrink-0 w-72 bg-slate-50 rounded-xl"
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => {
              const item = items.find((i) => `${i.fonte}-${i.id}` === drag);
              setDrag(null);
              if (item && situacaoColunaDe(item.status) !== key)
                onMove(item, key);
            }}
          >
            <div className="px-3 py-2.5 flex items-center gap-2 border-b border-slate-200">
              <span className={`w-2.5 h-2.5 rounded-full ${cor}`} />
              <span className="text-sm font-semibold text-slate-700">
                {label}
              </span>
              <span className="ml-auto text-[11px] text-slate-400 bg-slate-900/[0.05] rounded-full px-1.5 dark:bg-white/[0.07]">
                {itens.length}
              </span>
            </div>
            <div className="p-2 space-y-2 max-h-[60vh] overflow-y-auto">
              {itens.map((it) => {
                const cfg = tipoCfg(it.tipo);
                const Icon = cfg.icon;
                const resp = nomeDe(it.responsavel_id);
                return (
                  <div
                    key={`${it.fonte}-${it.id}`}
                    draggable
                    onDragStart={() => setDrag(`${it.fonte}-${it.id}`)}
                    className={`bg-white rounded-lg border p-2.5 cursor-grab active:cursor-grabbing ${it.urgencia === "vencido" && key !== "concluido" ? "border-danger-200" : "border-slate-200"}`}
                  >
                    <div className="flex items-center gap-1.5 mb-1">
                      <Icon className={`w-3.5 h-3.5 ${cfg.color}`} />
                      <span className="text-[10px] text-slate-400 uppercase font-medium">
                        {cfg.label}
                      </span>
                      {situacaoDe(it.status) === "cancelado" && (
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded border border-slate-200 bg-slate-50 text-slate-500">
                          Cancelado
                        </span>
                      )}
                      {it.prioridade && (
                        <span
                          className={`ml-auto text-[10px] font-semibold px-1.5 py-0.5 rounded ${PRIO_COLOR[it.prioridade] ?? PRIO_COLOR.baixa}`}
                        >
                          {it.prioridade}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-slate-700">{it.titulo}</p>
                    {it.caso_titulo &&
                      (it.case_id ? (
                        <Link
                          to={`/casos/${it.case_id}`}
                          className="text-xs text-primary-600 hover:underline truncate block mt-0.5"
                        >
                          {it.caso_titulo}
                        </Link>
                      ) : (
                        <p className="text-xs text-slate-400 mt-0.5 truncate">
                          {it.caso_titulo}
                        </p>
                      ))}
                    <div className="flex items-center justify-between mt-1">
                      <p
                        className={`text-[11px] ${it.urgencia === "vencido" && key !== "concluido" ? "text-danger-600 font-semibold" : "text-slate-400"}`}
                      >
                        {fmtRelative(it.dias_restantes)}
                      </p>
                      {resp && (
                        <span className="text-[10px] text-slate-400 inline-flex items-center gap-0.5">
                          <UserIcon className="w-3 h-3" /> {resp.split(" ")[0]}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

const NOVO_OPCOES: {
  key: string;
  label: string;
  categoria: "prazo" | "tarefa" | "agenda";
  tipo?: string;
}[] = [
  { key: "prazo", label: "Novo prazo", categoria: "prazo" },
  { key: "tarefa", label: "Nova tarefa", categoria: "tarefa" },
  {
    key: "audiencia",
    label: "Audiência",
    categoria: "agenda",
    tipo: "audiencia",
  },
  { key: "reuniao", label: "Reunião", categoria: "agenda", tipo: "reuniao" },
  {
    key: "compromisso",
    label: "Compromisso",
    categoria: "agenda",
    tipo: "compromisso",
  },
  {
    key: "diligencia",
    label: "Diligência",
    categoria: "agenda",
    tipo: "diligencia",
  },
];

export default function CentralAtividades() {
  const [searchParams, setSearchParams] = useSearchParams();
  const contextCaseId = readCaseContext(searchParams);
  const rawView = searchParams.get("view");
  const view: ActivityView = isActivityView(rawView) ? rawView : "lista";
  const setView = (next: ActivityView) => {
    const params = new URLSearchParams(searchParams);
    params.set("view", next);
    setSearchParams(params, { replace: true });
  };
  const rawTipo = searchParams.get("tipo");
  const filterTipo: ItemType | "todos" = isItemType(rawTipo)
    ? rawTipo
    : "todos";
  const setFilterTipo = (next: ItemType | "todos") => {
    const params = new URLSearchParams(searchParams);
    if (next === "todos") params.delete("tipo");
    else params.set("tipo", next);
    setSearchParams(params, { replace: true });
  };

  const [items, setItems] = useState<Activity[]>([]);
  const [responsaveis, setResponsaveis] = useState<Responsavel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [modal, setModal] = useState(false);
  const [menuNovo, setMenuNovo] = useState(false);
  const [form, setForm] = useState<any>({
    categoria: "agenda",
    tipo: "reuniao",
    data: "",
    case_id: contextCaseId,
  });
  const [reag, setReag] = useState<{ item: Activity; data: string } | null>(
    null,
  );
  const [atrib, setAtrib] = useState<{
    item: Activity;
    responsavel_id: string;
  } | null>(null);
  // Conflito de horário devolvido ao criar/editar evento — aviso não silencioso.
  const [conflitos, setConflitos] = useState<ConflitoEvento[]>([]);
  const [filterUrgencia, setFilterUrgencia] = useState<string>("todos");
  const [filterSituacao, setFilterSituacao] = useState<SituacaoColuna | "todos">(
    "todos",
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      // Fonte primária: GET /atividades (vw_atividades) — já entrega
      // responsavel_id, prioridade e subtipo por item, para TODOS os itens
      // visíveis (sem o corte de responsável do /deadlines/ nem o limite de
      // página do /agenda-eventos/). Único enriquecimento restante:
      // hora/local dos eventos de agenda, que a view não expõe. É
      // best-effort: se falhar, a central continua funcionando com o feed.
      const [ativ, agendaR] = await Promise.allSettled([
        api.get("/atividades", { params: { apenas_pendentes: false } }),
        api.get("/agenda-eventos/", { params: { page_size: 500 } }),
      ]);
      if (ativ.status !== "fulfilled") {
        setError(true);
        return;
      }
      const agendaMap: Record<string, any> = {};
      if (agendaR.status === "fulfilled")
        asList(agendaR.value.data).forEach((a: any) => (agendaMap[a.id] = a));

      const all: Activity[] = asList(ativ.value.data).map((a: any) => {
        const bruto: string = a.tipo;
        const fonte: Fonte = bruto === "agenda" ? "agenda" : (bruto as Fonte);
        const evento = fonte === "agenda" ? agendaMap[a.id] : undefined;
        const origem =
          fonte === "prazo"
            ? "Prazos"
            : fonte === "tarefa"
              ? "Tarefas"
              : fonte === "agenda"
                ? "Agenda"
                : fonte === "intimacao"
                  ? "DJEN"
                  : "Tribunais";
        return {
          id: a.id,
          tipo:
            fonte === "agenda"
              ? mapAgendaTipo(a.subtipo ?? evento?.tipo)
              : (bruto as ItemType),
          fonte,
          titulo: a.titulo,
          descricao: a.descricao,
          date: a.date,
          dias_restantes: a.dias_restantes ?? undefined,
          urgencia: a.urgencia ?? "normal",
          status: a.status,
          case_id: a.case_id,
          caso_titulo: a.caso_titulo,
          responsavel_id: a.responsavel_id ?? undefined,
          prioridade: a.prioridade ?? undefined,
          hora: evento?.hora ?? undefined,
          local: evento?.local ?? undefined,
          origem,
        };
      });
      setItems(all);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    // Lista de equipe para atribuir/exibir responsável. Sem permissão (403)
    // a central apenas oculta o recurso de atribuição.
    api
      .get("/atendimentos/responsaveis")
      .then((r) => setResponsaveis(asList(r.data)))
      .catch(() => setResponsaveis([]));
  }, []);

  const nomeDe = useCallback(
    (id?: string) => responsaveis.find((u) => u.id === id)?.nome,
    [responsaveis],
  );

  // ── Ações diretas ──────────────────────────────────────────────────────────
  const concluir = async (item: Activity) => {
    try {
      if (item.fonte === "prazo")
        await api.patch(`/deadlines/${item.id}`, { status: "concluido" });
      else if (item.fonte === "tarefa")
        await api.patch(`/tasks/${item.id}`, { status: "concluida" });
      else if (item.fonte === "agenda")
        await api.patch(`/agenda-eventos/${item.id}`, { concluido: true });
      else if (item.fonte === "intimacao")
        await api.post(`/intimacoes/${item.id}/processar`);
      else {
        toast.info("Suspensões são informativas — nada a concluir");
        return;
      }
      toast.success(
        item.fonte === "intimacao"
          ? "Intimação marcada como tratada"
          : "Item concluído",
      );
      load();
    } catch (e) {
      toast.error(apiErro(e, "Erro ao concluir o item"));
    }
  };

  // Double-booking: o evento JÁ foi criado/editado (a política é AVISAR, não
  // bloquear). O aviso não pode ser silencioso → toast + banner persistente.
  const avisarConflitos = (lista: ConflitoEvento[]) => {
    setConflitos(lista);
    if (lista.length) {
      const resumo = lista
        .map((c) => `“${c.titulo}”${c.hora ? ` às ${c.hora}` : ""}`)
        .join("; ");
      toast.error(
        `Evento salvo, mas há conflito de horário com ${lista.length} ` +
          `evento(s): ${resumo}`,
      );
    }
  };

  const salvarReagendamento = async () => {
    if (!reag) return;
    if (!reag.data) {
      toast.error("Informe a nova data");
      return;
    }
    const { item } = reag;
    try {
      let conflitoResp: ConflitoEvento[] = [];
      if (item.fonte === "prazo")
        await api.patch(`/deadlines/${item.id}`, { data_prazo: reag.data });
      else if (item.fonte === "tarefa")
        await api.patch(`/tasks/${item.id}`, { data_limite: reag.data });
      else if (item.fonte === "agenda") {
        const { data } = await api.patch(`/agenda-eventos/${item.id}`, {
          data_evento: reag.data,
        });
        conflitoResp = extrairConflitos(data);
      } else {
        toast.error("Este tipo de item não permite reagendamento");
        return;
      }
      toast.success("Data atualizada");
      setReag(null);
      avisarConflitos(conflitoResp);
      load();
    } catch (e) {
      toast.error(apiErro(e, "Erro ao reagendar"));
    }
  };

  const salvarAtribuicao = async () => {
    if (!atrib) return;
    if (!atrib.responsavel_id) {
      toast.error("Escolha o responsável");
      return;
    }
    const { item } = atrib;
    try {
      if (item.fonte === "prazo")
        await api.patch(`/deadlines/${item.id}`, {
          responsavel_id: atrib.responsavel_id,
        });
      else if (item.fonte === "tarefa")
        await api.patch(`/tasks/${item.id}`, {
          responsavel_id: atrib.responsavel_id,
        });
      else {
        toast.error("Este tipo de item não permite atribuição");
        return;
      }
      toast.success("Responsável atribuído");
      setAtrib(null);
      load();
    } catch (e) {
      toast.error(apiErro(e, "Erro ao atribuir responsável"));
    }
  };

  const moverSituacao = async (item: Activity, alvo: Situacao) => {
    try {
      if (item.fonte === "tarefa") {
        const status =
          alvo === "concluido"
            ? "concluida"
            : alvo === "em_execucao"
              ? "fazendo"
              : "a_fazer";
        await api.patch(`/tasks/${item.id}`, { status });
      } else if (alvo === "em_execucao") {
        toast.info("O estado «Em execução» só existe para tarefas");
        return;
      } else if (item.fonte === "prazo") {
        await api.patch(`/deadlines/${item.id}`, {
          status: alvo === "concluido" ? "concluido" : "pendente",
        });
      } else if (item.fonte === "agenda") {
        await api.patch(`/agenda-eventos/${item.id}`, {
          concluido: alvo === "concluido",
        });
      } else if (item.fonte === "intimacao") {
        if (alvo === "concluido") {
          await api.post(`/intimacoes/${item.id}/processar`);
        } else {
          toast.info("Intimação tratada não pode voltar a pendente por aqui");
          return;
        }
      } else {
        toast.info("Suspensões são informativas — sem situação");
        return;
      }
      toast.success("Situação atualizada");
      load();
    } catch (e) {
      toast.error(apiErro(e, "Erro ao mover o item"));
    }
  };

  const abrirNovo = (opcao: (typeof NOVO_OPCOES)[number]) => {
    setMenuNovo(false);
    setForm({
      categoria: opcao.categoria,
      tipo: opcao.tipo ?? "reuniao",
      prioridade: "media",
      data: "",
      case_id: contextCaseId,
    });
    setModal(true);
  };

  const salvarNovo = async () => {
    if (!form.titulo?.trim()) {
      toast.error("Título é obrigatório");
      return;
    }
    try {
      if (form.categoria === "prazo") {
        if (!form.data) {
          toast.error("Data do prazo é obrigatória");
          return;
        }
        await api.post(
          "/deadlines/",
          addCaseContext(
            {
              titulo: form.titulo,
              data_prazo: form.data,
              prioridade: form.prioridade || "media",
              descricao: form.descricao || undefined,
              responsavel_id: form.responsavel_id || undefined,
            },
            form.case_id,
          ),
        );
        toast.success("Prazo criado");
      } else if (form.categoria === "tarefa") {
        await api.post(
          "/tasks/",
          addCaseContext(
            {
              titulo: form.titulo,
              prioridade: form.prioridade || "media",
              data_limite: form.data || undefined,
              descricao: form.descricao || undefined,
              responsavel_id: form.responsavel_id || undefined,
            },
            form.case_id,
          ),
        );
        toast.success("Tarefa criada");
      } else {
        if (!form.data) {
          toast.error("Data do evento é obrigatória");
          return;
        }
        const { data } = await api.post(
          "/agenda-eventos/",
          addCaseContext(
            {
              titulo: form.titulo,
              tipo: form.tipo,
              data_evento: form.data,
              hora: form.hora || undefined,
              local: form.local || undefined,
              descricao: form.descricao || undefined,
            },
            form.case_id,
          ),
        );
        const conf = extrairConflitos(data);
        if (conf.length) {
          avisarConflitos(conf);
        } else {
          setConflitos([]); // limpa aviso obsoleto de um salvamento anterior
          toast.success("Evento criado");
        }
      }
      setModal(false);
      load();
    } catch (e) {
      toast.error(apiErro(e, "Erro ao salvar"));
    }
  };

  const filtered = items.filter((item) => {
    if (contextCaseId && item.case_id !== contextCaseId) return false;
    if (filterTipo !== "todos" && item.tipo !== filterTipo) return false;
    if (filterUrgencia !== "todos" && item.urgencia !== filterUrgencia)
      return false;
    // Filtro agrupa cancelado com concluído (badge distingue na listagem).
    if (
      filterSituacao !== "todos" &&
      situacaoColunaDe(item.status) !== filterSituacao
    )
      return false;
    return true;
  });

  // Cancelado também não conta como pendente nas estatísticas de urgência.
  // Com contexto de caso ativo, as estatísticas refletem só o caso — mas NÃO
  // aplicam os filtros de tipo/urgência/situação da UI: os cards de urgência
  // são os próprios botões de filtro e não podem se auto-zerar.
  const pendentes = (
    contextCaseId ? items.filter((i) => i.case_id === contextCaseId) : items
  ).filter((i) => situacaoColunaDe(i.status) !== "concluido");
  const stats = {
    vencido: pendentes.filter((i) => i.urgencia === "vencido").length,
    critico: pendentes.filter((i) => i.urgencia === "critico").length,
    atencao: pendentes.filter((i) => i.urgencia === "atencao").length,
    normal: pendentes.filter((i) => i.urgencia === "normal").length,
  };

  const tituloModal =
    form.categoria === "prazo"
      ? "Novo prazo"
      : form.categoria === "tarefa"
        ? "Nova tarefa"
        : "Novo evento de agenda";

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <PageHeader
        title="Agenda e Prazos"
        subtitle={
          contextCaseId
            ? "Atividades vinculadas ao caso selecionado"
            : "Prazos, tarefas, audiências, compromissos e intimações em uma única tela"
        }
        actions={
          <>
            <button
              onClick={() => setView("lista")}
              aria-label="Visualização em lista"
              title="Lista"
              className={`p-2 rounded-lg transition-colors ${view === "lista" ? "bg-navy text-white" : "bg-slate-900/[0.05] text-slate-500 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300"}`}
            >
              <List className="w-4 h-4" />
            </button>
            <button
              onClick={() => setView("calendario")}
              aria-label="Visualização em calendário"
              title="Calendário"
              className={`p-2 rounded-lg transition-colors ${view === "calendario" ? "bg-navy text-white" : "bg-slate-900/[0.05] text-slate-500 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300"}`}
            >
              <Calendar className="w-4 h-4" />
            </button>
            <button
              onClick={() => setView("timeline")}
              aria-label="Visualização em timeline"
              title="Timeline"
              className={`p-2 rounded-lg transition-colors ${view === "timeline" ? "bg-navy text-white" : "bg-slate-900/[0.05] text-slate-500 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300"}`}
            >
              <FileText className="w-4 h-4" />
            </button>
            <button
              onClick={() => setView("kanban")}
              aria-label="Visualização em quadro"
              title="Quadro"
              className={`p-2 rounded-lg transition-colors ${view === "kanban" ? "bg-navy text-white" : "bg-slate-900/[0.05] text-slate-500 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300"}`}
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
            <div className="relative">
              <button
                onClick={() => setMenuNovo((v) => !v)}
                aria-haspopup="menu"
                aria-expanded={menuNovo}
                className="flex items-center gap-1 px-3 py-2 bg-success-600 text-white rounded-lg text-sm hover:bg-success-700"
              >
                <Plus className="w-4 h-4" /> Novo{" "}
                <ChevronDown className="w-3.5 h-3.5" />
              </button>
              {menuNovo && (
                <>
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setMenuNovo(false)}
                  />
                  <div
                    role="menu"
                    className="absolute right-0 mt-1 z-20 w-44 bg-white border border-slate-200 rounded-xl shadow-md py-1 dark:bg-slate-800 dark:border-slate-700"
                  >
                    {NOVO_OPCOES.map((op) => (
                      <button
                        key={op.key}
                        role="menuitem"
                        onClick={() => abrirNovo(op)}
                        className="w-full text-left px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-700"
                      >
                        {op.label}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          </>
        }
      />

      {/* Aviso de double-booking — não silencioso. O evento já foi criado/
          editado (política do backend: AVISA, não bloqueia). */}
      {conflitos.length > 0 && (
        <div
          role="alert"
          className="mb-5 rounded-xl border border-warn-200 bg-warn-50 px-4 py-3"
        >
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0 text-warn-600" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-warn-800">
                Conflito de horário na agenda
              </p>
              <p className="text-xs text-warn-700 mt-0.5">
                O evento foi salvo, mas coincide com {conflitos.length}{" "}
                compromisso(s) do mesmo responsável no mesmo horário:
              </p>
              <ul className="mt-2 space-y-1">
                {conflitos.map((c) => (
                  <li
                    key={c.id}
                    className="flex items-center gap-2 text-xs text-warn-800"
                  >
                    <Clock className="w-3.5 h-3.5 shrink-0 text-warn-600" />
                    <span className="font-medium truncate">{c.titulo}</span>
                    {c.hora && (
                      <span className="text-warn-700">· {c.hora}</span>
                    )}
                    {c.local && (
                      <span className="text-warn-600 truncate">
                        · {c.local}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
            <button
              onClick={() => setConflitos([])}
              aria-label="Dispensar aviso de conflito"
              className="p-1 -m-1 text-warn-600 hover:text-warn-800 shrink-0"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-4 gap-3 mb-5">
        {[
          {
            key: "vencido",
            label: "Vencidos",
            color: "bg-danger-50 border-danger-200 text-danger-700",
          },
          {
            key: "critico",
            label: "Críticos (≤3d)",
            color: "bg-orange-50 border-orange-200 text-orange-700",
          },
          {
            key: "atencao",
            label: "Atenção (≤7d)",
            color: "bg-yellow-50 border-yellow-200 text-yellow-700",
          },
          {
            key: "normal",
            label: "Em dia",
            color: "bg-green-50 border-green-200 text-green-700",
          },
        ].map(({ key, label, color }) => (
          <button
            key={key}
            onClick={() =>
              setFilterUrgencia(filterUrgencia === key ? "todos" : key)
            }
            className={`border rounded-xl p-3 text-left transition-all hover:shadow-sm ${color} ${filterUrgencia === key ? "ring-2 ring-offset-1 ring-slate-400" : ""}`}
          >
            <div className="text-2xl font-bold">
              {stats[key as keyof typeof stats]}
            </div>
            <div className="text-xs font-medium mt-0.5">{label}</div>
          </button>
        ))}
      </div>

      <div className="flex gap-2 mb-2 flex-wrap">
        <div className="flex items-center gap-1 text-xs text-slate-500 mr-1">
          <Filter className="w-3.5 h-3.5" /> Tipo:
        </div>
        {(
          [
            "todos",
            "prazo",
            "audiencia",
            "tarefa",
            "reuniao",
            "compromisso",
            "diligencia",
            "suspensao",
            "intimacao",
          ] as const
        ).map((t) => (
          <button
            key={t}
            onClick={() => setFilterTipo(t)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${filterTipo === t ? "bg-navy text-white" : "bg-slate-900/[0.05] text-slate-600 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300"}`}
          >
            {t === "todos" ? "Todos" : TIPO_CONFIG[t]?.label}
          </button>
        ))}
      </div>

      <div className="flex gap-2 mb-4 flex-wrap items-center">
        <div className="flex items-center gap-1 text-xs text-slate-500 mr-1">
          <Filter className="w-3.5 h-3.5" /> Situação:
        </div>
        {(
          [
            { key: "todos", label: "Todas" },
            ...SITUACAO_CONFIG.map(({ key, label }) => ({ key, label })),
          ] as { key: SituacaoColuna | "todos"; label: string }[]
        ).map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setFilterSituacao(key)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${filterSituacao === key ? "bg-navy text-white" : "bg-slate-900/[0.05] text-slate-600 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {loading ? (
        <Spinner />
      ) : error ? (
        <ErrorState
          message="Não foi possível carregar as atividades. Verifique sua conexão e tente novamente."
          onRetry={load}
        />
      ) : view === "calendario" ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <CalendarView items={filtered} />
          </div>
          <div className="card overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100">
              <p className="text-sm font-semibold text-slate-700">
                Próximas atividades
              </p>
            </div>
            <div className="overflow-y-auto max-h-80">
              {filtered.slice(0, 20).map((item) => (
                <ActivityRow
                  key={`${item.fonte}-${item.id}`}
                  item={item}
                  nomeDe={nomeDe}
                  onConcluir={concluir}
                  onReagendar={(it) =>
                    setReag({ item: it, data: it.date?.slice(0, 10) ?? "" })
                  }
                  onAtribuir={(it) =>
                    setAtrib({
                      item: it,
                      responsavel_id: it.responsavel_id ?? "",
                    })
                  }
                  podeAtribuir={responsaveis.length > 0}
                />
              ))}
            </div>
          </div>
        </div>
      ) : view === "kanban" ? (
        <KanbanAtividades
          items={filtered}
          nomeDe={nomeDe}
          onMove={moverSituacao}
        />
      ) : view === "timeline" ? (
        <TimelineView items={filtered} />
      ) : (
        <div className="card overflow-hidden">
          {filtered.length === 0 ? (
            <div className="py-16 text-center">
              <CheckCircle className="w-10 h-10 text-success-400 mx-auto mb-3" />
              <p className="text-slate-500 font-medium">
                Nenhuma atividade encontrada
              </p>
              <p className="text-slate-400 text-sm mt-1">
                Todos os prazos, tarefas e suspensões estão em dia
              </p>
            </div>
          ) : (
            filtered.map((item) => (
              <ActivityRow
                key={`${item.fonte}-${item.id}`}
                item={item}
                nomeDe={nomeDe}
                onConcluir={concluir}
                onReagendar={(it) =>
                  setReag({ item: it, data: it.date?.slice(0, 10) ?? "" })
                }
                onAtribuir={(it) =>
                  setAtrib({
                    item: it,
                    responsavel_id: it.responsavel_id ?? "",
                  })
                }
                podeAtribuir={responsaveis.length > 0}
              />
            ))
          )}
        </div>
      )}

      {/* ── Novo prazo / tarefa / evento (formulário adaptado ao tipo) ── */}
      <Modal open={modal} onClose={() => setModal(false)} title={tituloModal}>
        <div className="space-y-3">
          {form.case_id && (
            <div className="rounded-lg border border-primary-200 bg-primary-50 px-3 py-2 text-xs text-primary-700">
              Este item será vinculado ao caso aberto.
            </div>
          )}
          <input
            className="input w-full text-sm"
            placeholder="Título *"
            value={form.titulo ?? ""}
            onChange={(e) => setForm({ ...form, titulo: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-2">
            {form.categoria === "agenda" ? (
              <select
                className="input text-sm"
                value={form.tipo}
                onChange={(e) => setForm({ ...form, tipo: e.target.value })}
              >
                <option value="reuniao">Reunião</option>
                <option value="compromisso">Compromisso</option>
                <option value="diligencia">Diligência</option>
                <option value="audiencia">Audiência</option>
                <option value="outro">Outro</option>
              </select>
            ) : (
              <select
                className="input text-sm"
                value={form.prioridade ?? "media"}
                onChange={(e) =>
                  setForm({ ...form, prioridade: e.target.value })
                }
              >
                <option value="baixa">Prioridade baixa</option>
                <option value="media">Prioridade média</option>
                <option value="alta">Prioridade alta</option>
              </select>
            )}
            <input
              type="date"
              className="input text-sm"
              title="Formato: dd/mm/aaaa"
              aria-label={
                form.categoria === "prazo"
                  ? "Data do prazo (dd/mm/aaaa)"
                  : form.categoria === "tarefa"
                    ? "Data limite (dd/mm/aaaa)"
                    : "Data do evento (dd/mm/aaaa)"
              }
              value={form.data ?? ""}
              onChange={(e) => setForm({ ...form, data: e.target.value })}
            />
          </div>
          {form.categoria === "agenda" ? (
            <div className="grid grid-cols-2 gap-2">
              <input
                className="input text-sm"
                placeholder="Hora (ex: 14:30)"
                value={form.hora ?? ""}
                onChange={(e) => setForm({ ...form, hora: e.target.value })}
              />
              <input
                className="input text-sm"
                placeholder="Local"
                value={form.local ?? ""}
                onChange={(e) => setForm({ ...form, local: e.target.value })}
              />
            </div>
          ) : (
            responsaveis.length > 0 && (
              <select
                className="input w-full text-sm"
                value={form.responsavel_id ?? ""}
                onChange={(e) =>
                  setForm({ ...form, responsavel_id: e.target.value })
                }
              >
                <option value="">Responsável (eu mesmo)</option>
                {responsaveis.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.nome}
                  </option>
                ))}
              </select>
            )
          )}
          <textarea
            className="input w-full text-sm"
            rows={2}
            placeholder="Descrição"
            value={form.descricao ?? ""}
            onChange={(e) => setForm({ ...form, descricao: e.target.value })}
          />
          <div className="flex gap-2 justify-end">
            <button onClick={() => setModal(false)} className="btn-ghost">
              Cancelar
            </button>
            <button
              onClick={salvarNovo}
              className="px-4 py-2 bg-success-600 text-white text-sm rounded-lg hover:bg-success-700"
            >
              Salvar
            </button>
          </div>
        </div>
      </Modal>

      {/* ── Reagendar ── */}
      <Modal
        open={reag !== null}
        onClose={() => setReag(null)}
        title="Reagendar"
      >
        {reag && (
          <div className="space-y-3">
            <p className="text-sm text-slate-600 truncate">
              {reag.item.titulo}
            </p>
            <input
              type="date"
              className="input w-full text-sm"
              title="Formato: dd/mm/aaaa"
              aria-label="Nova data (dd/mm/aaaa)"
              value={reag.data}
              onChange={(e) => setReag({ ...reag, data: e.target.value })}
            />
            <div className="flex gap-2 justify-end">
              <button onClick={() => setReag(null)} className="btn-ghost">
                Cancelar
              </button>
              <button
                onClick={salvarReagendamento}
                className="px-4 py-2 bg-success-600 text-white text-sm rounded-lg hover:bg-success-700"
              >
                Salvar
              </button>
            </div>
          </div>
        )}
      </Modal>

      {/* ── Atribuir responsável ── */}
      <Modal
        open={atrib !== null}
        onClose={() => setAtrib(null)}
        title="Atribuir responsável"
      >
        {atrib && (
          <div className="space-y-3">
            <p className="text-sm text-slate-600 truncate">
              {atrib.item.titulo}
            </p>
            <select
              className="input w-full text-sm"
              aria-label="Responsável"
              value={atrib.responsavel_id}
              onChange={(e) =>
                setAtrib({ ...atrib, responsavel_id: e.target.value })
              }
            >
              <option value="">Selecione…</option>
              {responsaveis.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.nome}
                  {u.role ? ` (${u.role})` : ""}
                </option>
              ))}
            </select>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setAtrib(null)} className="btn-ghost">
                Cancelar
              </button>
              <button
                onClick={salvarAtribuicao}
                className="px-4 py-2 bg-success-600 text-white text-sm rounded-lg hover:bg-success-700"
              >
                Salvar
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
