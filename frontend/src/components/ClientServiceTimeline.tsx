import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  ClipboardCheck,
  Clock,
  FileText,
  ListTodo,
  MessageSquare,
  Plus,
  RotateCcw,
  UserCheck,
  X,
  XCircle,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";
import { Spinner } from "./UI";
import { detalheErro } from "../utils/erro";

type AtendimentoTipo =
  | "reuniao_presencial"
  | "reuniao_virtual"
  | "ligacao"
  | "email"
  | "whatsapp"
  | "protocolo"
  | "visita"
  | "outros";

type TimelineFilter = "todos" | "pendentes" | "atrasados" | "atendidos";
type Prioridade = "baixa" | "normal" | "alta" | "urgente";
type ContatoStatus = "iniciado" | "confirmado" | "nao_concluido";

export interface ClientTimelineCase {
  id: string | number;
  numero_interno: string;
  titulo: string;
}

/** Evento de outra fonte (documento, abertura de caso…) já carregado pela
 *  página — mesclado cronologicamente na linha do tempo, sem novas chamadas. */
export interface ClientTimelineExtraEvent {
  id: string;
  label: string;
  titulo: string;
  data: string;
  link?: string;
}

interface Responsavel {
  id: string;
  nome: string;
  role: string;
}

interface AuditEntry {
  id: string;
  acao: string;
  detalhes?: string | null;
  usuario_nome: string;
  usuario_role?: string | null;
  data?: string | null;
}

export interface ClientServiceEntry {
  id: string;
  client_id: string;
  case_id?: string | null;
  tipo: AtendimentoTipo;
  data_atendimento: string;
  resumo: string;
  solicitacao?: string | null;
  solicitacao_atendida: boolean;
  solicitacao_atrasada?: boolean;
  solicitacao_prazo?: string | null;
  solicitacao_prioridade?: Prioridade;
  solicitacao_responsavel_id?: string | null;
  atendida_em?: string | null;
  task_id?: string | null;
  contato_status?: ContatoStatus;
  proximo_passo?: string | null;
  pode_editar: boolean;
}

interface TimelineResponse {
  total: number;
  resumo_solicitacoes?: {
    pendentes: number;
    atrasadas: number;
    atendidas: number;
  };
  items: ClientServiceEntry[];
}

interface Props {
  clientId: string | number;
  cases?: ClientTimelineCase[];
  extraEvents?: ClientTimelineExtraEvent[];
  /** Abre o formulário de novo atendimento já na montagem (ação rápida). */
  autoOpenForm?: boolean;
}

const TIPO_LABEL: Record<AtendimentoTipo, string> = {
  reuniao_presencial: "Reunião presencial",
  reuniao_virtual: "Reunião virtual",
  ligacao: "Ligação",
  email: "E-mail",
  whatsapp: "WhatsApp",
  protocolo: "Protocolo",
  visita: "Visita",
  outros: "Outro",
};

const PRIORIDADE_LABEL: Record<Prioridade, string> = {
  baixa: "Baixa",
  normal: "Normal",
  alta: "Alta",
  urgente: "Urgente",
};

const PRIORIDADE_STYLE: Record<Prioridade, string> = {
  baixa: "bg-slate-100 text-slate-600",
  normal: "bg-info-50 text-info-700",
  alta: "bg-orange-50 text-orange-700",
  urgente: "bg-red-50 text-red-700",
};

const CONTATO_LABEL: Record<ContatoStatus, string> = {
  iniciado: "Contato iniciado",
  confirmado: "Contato confirmado",
  nao_concluido: "Contato não concluído",
};

function nowForInput() {
  const agora = new Date();
  const local = new Date(agora.getTime() - agora.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function formatDateTime(value: string) {
  const data = new Date(value);
  if (Number.isNaN(data.getTime())) return { dia: "Data inválida", hora: "" };
  return {
    dia: data.toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "long",
      year: "numeric",
    }),
    hora: data.toLocaleTimeString("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
    }),
  };
}

function formatCompactDate(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function emptyForm() {
  return {
    tipo: "whatsapp" as AtendimentoTipo,
    data_atendimento: nowForInput(),
    resumo: "",
    solicitacao: "",
    case_id: "",
    solicitacao_atendida: false,
    solicitacao_prazo: "",
    solicitacao_prioridade: "normal" as Prioridade,
    solicitacao_responsavel_id: "",
    criar_tarefa: true,
  };
}

export default function ClientServiceTimeline({
  clientId,
  cases = [],
  extraEvents = [],
  autoOpenForm = false,
}: Props) {
  const [items, setItems] = useState<ClientServiceEntry[]>([]);
  const [responsaveis, setResponsaveis] = useState<Responsavel[]>([]);
  const [total, setTotal] = useState(0);
  const [resumoSolicitacoes, setResumoSolicitacoes] = useState<{
    pendentes: number;
    atrasadas: number;
    atendidas: number;
  } | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [saving, setSaving] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(autoOpenForm);
  const [filter, setFilter] = useState<TimelineFilter>("todos");
  const [form, setForm] = useState(emptyForm);
  const [expandedAuditId, setExpandedAuditId] = useState<string | null>(null);
  const [loadingAuditId, setLoadingAuditId] = useState<string | null>(null);
  const [auditById, setAuditById] = useState<Record<string, AuditEntry[]>>({});

  const load = useCallback(
    async (targetPage = 1, append = false) => {
      if (append) setLoadingMore(true);
      else setLoading(true);
      try {
        const response = await api.get<TimelineResponse>("/atendimentos", {
          params: {
            client_id: String(clientId),
            page: targetPage,
            per_page: 100,
          },
        });
        const incoming = response.data.items ?? [];
        setItems((current) => (append ? [...current, ...incoming] : incoming));
        setTotal(response.data.total ?? 0);
        setResumoSolicitacoes(response.data.resumo_solicitacoes ?? null);
        setPage(targetPage);
      } catch (error: unknown) {
        toast.error(
          detalheErro(error, "Não foi possível carregar a linha do tempo."),
        );
        if (!append) {
          setItems([]);
          setTotal(0);
          setResumoSolicitacoes(null);
        }
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [clientId],
  );

  const loadResponsaveis = useCallback(async () => {
    try {
      const response = await api.get<Responsavel[]>(
        "/atendimentos/responsaveis",
      );
      setResponsaveis(Array.isArray(response.data) ? response.data : []);
    } catch {
      setResponsaveis([]);
    }
  }, []);

  useEffect(() => {
    load(1, false);
    loadResponsaveis();
  }, [load, loadResponsaveis]);

  const responsavelById = useMemo(
    () =>
      new Map(
        responsaveis.map((responsavel) => [responsavel.id, responsavel.nome]),
      ),
    [responsaveis],
  );

  const pendentesCarregadas = useMemo(
    () =>
      items.filter(
        (item) => Boolean(item.solicitacao) && !item.solicitacao_atendida,
      ).length,
    [items],
  );
  const atrasadasCarregadas = useMemo(
    () => items.filter((item) => item.solicitacao_atrasada).length,
    [items],
  );
  const atendidasCarregadas = useMemo(
    () =>
      items.filter(
        (item) => Boolean(item.solicitacao) && item.solicitacao_atendida,
      ).length,
    [items],
  );

  const pendentes = resumoSolicitacoes?.pendentes ?? pendentesCarregadas;
  const atrasados = resumoSolicitacoes?.atrasadas ?? atrasadasCarregadas;
  const atendidos = resumoSolicitacoes?.atendidas ?? atendidasCarregadas;

  const filteredItems = useMemo(() => {
    if (filter === "pendentes") {
      return items.filter(
        (item) => Boolean(item.solicitacao) && !item.solicitacao_atendida,
      );
    }
    if (filter === "atrasados") {
      return items.filter((item) => item.solicitacao_atrasada);
    }
    if (filter === "atendidos") {
      return items.filter(
        (item) => Boolean(item.solicitacao) && item.solicitacao_atendida,
      );
    }
    return items;
  }, [filter, items]);

  // Linha do tempo unificada: mescla eventos extras (documentos, casos) já
  // carregados pela página, em ordem cronológica decrescente. Enquanto houver
  // páginas de atendimentos não carregadas, só entram extras mais recentes que
  // o atendimento mais antigo em tela, para não furar a cronologia.
  type TimelineRow =
    | { kind: "atendimento"; date: number; item: ClientServiceEntry }
    | { kind: "extra"; date: number; extra: ClientTimelineExtraEvent };

  const rows = useMemo<TimelineRow[]>(() => {
    const base: TimelineRow[] = filteredItems.map((item) => ({
      kind: "atendimento",
      date: new Date(item.data_atendimento).getTime(),
      item,
    }));
    if (filter !== "todos" || extraEvents.length === 0) {
      return base.sort((a, b) => b.date - a.date);
    }
    const oldestLoaded =
      items.length < total && items.length > 0
        ? Math.min(
            ...items.map((item) => new Date(item.data_atendimento).getTime()),
          )
        : Number.NEGATIVE_INFINITY;
    const extras: TimelineRow[] = extraEvents
      .map((extra) => ({
        kind: "extra" as const,
        date: new Date(extra.data).getTime(),
        extra,
      }))
      .filter((row) => Number.isFinite(row.date) && row.date >= oldestLoaded);
    return [...base, ...extras].sort((a, b) => b.date - a.date);
  }, [filteredItems, filter, extraEvents, items, total]);

  async function createEntry() {
    const resumo = form.resumo.trim();
    const solicitacao = form.solicitacao.trim();
    if (resumo.length < 10) {
      toast.error("O recado deve ter pelo menos 10 caracteres.");
      return;
    }
    const dataAtendimento = new Date(form.data_atendimento);
    if (!form.data_atendimento || Number.isNaN(dataAtendimento.getTime())) {
      toast.error("Informe uma data e hora válidas.");
      return;
    }

    let prazo: string | undefined;
    if (solicitacao && form.solicitacao_prazo) {
      const dataPrazo = new Date(form.solicitacao_prazo);
      if (Number.isNaN(dataPrazo.getTime())) {
        toast.error("Informe um prazo válido para a solicitação.");
        return;
      }
      prazo = dataPrazo.toISOString();
    }

    setSaving(true);
    try {
      await api.post("/atendimentos", {
        client_id: String(clientId),
        case_id: form.case_id || undefined,
        tipo: form.tipo,
        data_atendimento: dataAtendimento.toISOString(),
        resumo,
        solicitacao: solicitacao || undefined,
        solicitacao_atendida: Boolean(solicitacao) && form.solicitacao_atendida,
        solicitacao_prazo: prazo,
        solicitacao_prioridade: form.solicitacao_prioridade,
        solicitacao_responsavel_id:
          form.solicitacao_responsavel_id || undefined,
        criar_tarefa: Boolean(solicitacao) && form.criar_tarefa,
        contato_status: "confirmado",
      });
      toast.success("Atendimento registrado na linha do tempo.");
      setForm(emptyForm());
      setShowForm(false);
      await load(1, false);
    } catch (error: unknown) {
      toast.error(detalheErro(error, "Não foi possível salvar o atendimento."));
    } finally {
      setSaving(false);
    }
  }

  async function toggleAttended(item: ClientServiceEntry) {
    setUpdatingId(item.id);
    try {
      await api.patch(`/atendimentos/${item.id}`, {
        solicitacao_atendida: !item.solicitacao_atendida,
      });
      toast.success(
        item.solicitacao_atendida
          ? "Solicitação reaberta."
          : "Solicitação marcada como atendida.",
      );
      await load(1, false);
    } catch (error: unknown) {
      toast.error(
        detalheErro(error, "Não foi possível atualizar a solicitação."),
      );
    } finally {
      setUpdatingId(null);
    }
  }

  async function updateContact(
    item: ClientServiceEntry,
    contatoStatus: ContatoStatus,
  ) {
    setUpdatingId(item.id);
    try {
      await api.patch(`/atendimentos/${item.id}`, {
        contato_status: contatoStatus,
      });
      toast.success(
        contatoStatus === "confirmado"
          ? "Contato confirmado."
          : "Contato registrado como não concluído.",
      );
      await load(1, false);
    } catch (error: unknown) {
      toast.error(detalheErro(error, "Não foi possível atualizar o contato."));
    } finally {
      setUpdatingId(null);
    }
  }

  async function toggleAudit(itemId: string) {
    if (expandedAuditId === itemId) {
      setExpandedAuditId(null);
      return;
    }
    setExpandedAuditId(itemId);
    if (auditById[itemId]) return;

    setLoadingAuditId(itemId);
    try {
      const response = await api.get<AuditEntry[]>(
        `/atendimentos/${itemId}/historico`,
      );
      setAuditById((current) => ({
        ...current,
        [itemId]: response.data ?? [],
      }));
    } catch (error: unknown) {
      toast.error(
        detalheErro(
          error,
          "Não foi possível carregar o histórico de auditoria.",
        ),
      );
    } finally {
      setLoadingAuditId(null);
    }
  }

  return (
    <section
      className="space-y-4"
      aria-labelledby="timeline-atendimentos-title"
    >
      <div className="card p-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p
              id="timeline-atendimentos-title"
              className="eyebrow flex items-center gap-2"
            >
              <MessageSquare className="h-3.5 w-3.5" />
              Linha do tempo de atendimento
            </p>
            <p className="mt-1 text-sm text-slate-500">
              Contatos, recados, solicitações, responsáveis e cumprimento do
              prazo acordado.
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              setShowForm((current) => !current);
              setForm(emptyForm());
            }}
            className="btn-primary self-start text-xs"
          >
            {showForm ? (
              <X className="h-3.5 w-3.5" />
            ) : (
              <Plus className="h-3.5 w-3.5" />
            )}
            {showForm ? "Fechar" : "Novo atendimento"}
          </button>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
          <div className="rounded-lg bg-slate-50 p-3">
            <p className="text-[10px] uppercase tracking-wide text-slate-400">
              Registros
            </p>
            <p className="mt-1 text-lg font-semibold text-navy-900">{total}</p>
          </div>
          <div className="rounded-lg bg-warn-50 p-3">
            <p className="text-[10px] uppercase tracking-wide text-warn-600">
              Pendentes
            </p>
            <p className="mt-1 text-lg font-semibold text-warn-700">
              {pendentes}
            </p>
          </div>
          <div className="rounded-lg bg-red-50 p-3">
            <p className="text-[10px] uppercase tracking-wide text-red-600">
              Atrasadas
            </p>
            <p className="mt-1 text-lg font-semibold text-red-700">
              {atrasados}
            </p>
          </div>
          <div className="rounded-lg bg-success-50 p-3">
            <p className="text-[10px] uppercase tracking-wide text-success-600">
              Atendidas
            </p>
            <p className="mt-1 text-lg font-semibold text-success-700">
              {atendidos}
            </p>
          </div>
        </div>
      </div>

      {showForm && (
        <div className="card p-4 animate-fade-in">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="text-xs font-medium text-slate-600">
              Canal do atendimento
              <select
                className="input mt-1"
                value={form.tipo}
                onChange={(event) =>
                  setForm({
                    ...form,
                    tipo: event.target.value as AtendimentoTipo,
                  })
                }
              >
                {Object.entries(TIPO_LABEL).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs font-medium text-slate-600">
              Dia e hora
              <input
                type="datetime-local"
                className="input mt-1"
                value={form.data_atendimento}
                onChange={(event) =>
                  setForm({ ...form, data_atendimento: event.target.value })
                }
                required
              />
            </label>
            <label className="text-xs font-medium text-slate-600 md:col-span-2">
              Recado / registro do atendimento
              <textarea
                className="input mt-1 min-h-24 resize-y"
                value={form.resumo}
                onChange={(event) =>
                  setForm({ ...form, resumo: event.target.value })
                }
                placeholder="Ex.: Cliente informou que recebeu a intimação e pediu retorno."
                maxLength={4000}
                required
              />
            </label>
            <label className="text-xs font-medium text-slate-600 md:col-span-2">
              O que foi solicitado
              <textarea
                className="input mt-1 min-h-20 resize-y"
                value={form.solicitacao}
                onChange={(event) =>
                  setForm({
                    ...form,
                    solicitacao: event.target.value,
                    solicitacao_atendida: event.target.value.trim()
                      ? form.solicitacao_atendida
                      : false,
                  })
                }
                placeholder="Descreva o pedido do cliente, se houver."
                maxLength={4000}
              />
            </label>

            {form.solicitacao.trim() && (
              <>
                <label className="text-xs font-medium text-slate-600">
                  Responsável pela solicitação
                  <select
                    className="input mt-1"
                    value={form.solicitacao_responsavel_id}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        solicitacao_responsavel_id: event.target.value,
                      })
                    }
                  >
                    <option value="">Quem registra</option>
                    {responsaveis.map((responsavel) => (
                      <option key={responsavel.id} value={responsavel.id}>
                        {responsavel.nome}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-xs font-medium text-slate-600">
                  Prioridade
                  <select
                    className="input mt-1"
                    value={form.solicitacao_prioridade}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        solicitacao_prioridade: event.target
                          .value as Prioridade,
                      })
                    }
                  >
                    {Object.entries(PRIORIDADE_LABEL).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-xs font-medium text-slate-600">
                  Prazo acordado
                  <input
                    type="datetime-local"
                    className="input mt-1"
                    value={form.solicitacao_prazo}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        solicitacao_prazo: event.target.value,
                      })
                    }
                  />
                </label>
                <label className="flex items-center gap-2 self-end rounded-lg border border-slate-200 px-3 py-2.5 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={form.criar_tarefa}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        criar_tarefa: event.target.checked,
                      })
                    }
                  />
                  Criar tarefa vinculada
                </label>
              </>
            )}

            <label className="text-xs font-medium text-slate-600">
              Caso relacionado (opcional)
              <select
                className="input mt-1"
                value={form.case_id}
                onChange={(event) =>
                  setForm({ ...form, case_id: event.target.value })
                }
              >
                <option value="">Sem vínculo com caso</option>
                {cases.map((clientCase) => (
                  <option key={clientCase.id} value={clientCase.id}>
                    {clientCase.numero_interno} — {clientCase.titulo}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 self-end rounded-lg border border-slate-200 px-3 py-2.5 text-xs text-slate-600">
              <input
                type="checkbox"
                checked={form.solicitacao_atendida}
                disabled={!form.solicitacao.trim()}
                onChange={(event) =>
                  setForm({
                    ...form,
                    solicitacao_atendida: event.target.checked,
                  })
                }
              />
              Solicitação já foi atendida
            </label>
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <button
              type="button"
              className="btn-ghost text-xs"
              onClick={() => setShowForm(false)}
              disabled={saving}
            >
              Cancelar
            </button>
            <button
              type="button"
              className="btn-primary text-xs"
              onClick={createEntry}
              disabled={saving}
            >
              {saving ? "Salvando..." : "Registrar atendimento"}
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2" aria-label="Filtrar atendimentos">
        {(
          [
            ["todos", "Todos"],
            ["pendentes", "Solicitações pendentes"],
            ["atrasados", "Atrasadas"],
            ["atendidos", "Solicitações atendidas"],
          ] as Array<[TimelineFilter, string]>
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            aria-pressed={filter === value}
            onClick={() => setFilter(value)}
            className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
              filter === value
                ? "border-bronze bg-bronze-50 text-bronze-deep"
                : "border-slate-200 bg-white text-slate-500 hover:border-bronze-pale"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {loading && <Spinner />}

      {!loading && rows.length === 0 && (
        <div className="card p-8 text-center">
          <MessageSquare className="mx-auto h-8 w-8 text-slate-300" />
          <p className="mt-2 text-sm font-medium text-slate-600">
            Nenhum atendimento neste filtro
          </p>
          <p className="mt-1 text-xs text-slate-400">
            Registre o primeiro contato para iniciar a linha do tempo.
          </p>
        </div>
      )}

      {!loading && rows.length > 0 && (
        <div className="card p-4">
          <ol className="relative ml-3 border-l border-bronze-pale">
            {rows.map((row) => {
              if (row.kind === "extra") {
                const { extra } = row;
                const dateTime = formatDateTime(extra.data);
                return (
                  <li
                    key={`extra-${extra.id}`}
                    className="relative pb-6 pl-6 last:pb-0"
                  >
                    <span
                      className="absolute -left-2 top-1 flex h-4 w-4 items-center justify-center rounded-full border-2 border-white bg-slate-300"
                      aria-hidden="true"
                    />
                    <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/60 px-4 py-2.5">
                      <p className="text-xs capitalize text-slate-400">
                        {dateTime.dia}
                      </p>
                      <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-600">
                        <span className="badge badge-neutral text-[10px]">
                          {extra.label}
                        </span>
                        <span className="min-w-0 truncate">{extra.titulo}</span>
                        {extra.link && (
                          <Link
                            to={extra.link}
                            className="text-xs font-medium text-bronze hover:text-bronze-dark"
                          >
                            Abrir
                          </Link>
                        )}
                      </p>
                    </div>
                  </li>
                );
              }
              const { item } = row;
              const dateTime = formatDateTime(item.data_atendimento);
              const hasRequest = Boolean(item.solicitacao?.trim());
              const prioridade = item.solicitacao_prioridade ?? "normal";
              const contatoStatus = item.contato_status ?? "confirmado";
              const prazo = formatCompactDate(item.solicitacao_prazo);
              const auditEntries = auditById[item.id] ?? [];
              return (
                <li key={item.id} className="relative pb-6 pl-6 last:pb-0">
                  <span
                    className={`absolute -left-2 top-1 flex h-4 w-4 items-center justify-center rounded-full border-2 border-white ${
                      item.solicitacao_atrasada
                        ? "bg-red-500"
                        : hasRequest
                          ? item.solicitacao_atendida
                            ? "bg-success-500"
                            : "bg-warn-400"
                          : "bg-bronze"
                    }`}
                    aria-hidden="true"
                  />
                  <article className="rounded-xl border border-slate-100 bg-white p-4 shadow-sm">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <p className="text-sm font-semibold capitalize text-navy-900">
                          {dateTime.dia}
                        </p>
                        <p className="mt-0.5 flex items-center gap-1 text-xs text-slate-400">
                          <Clock className="h-3 w-3" />
                          {dateTime.hora} · {TIPO_LABEL[item.tipo] ?? item.tipo}
                        </p>
                        <p className="mt-1 flex items-center gap-1 text-[11px] text-slate-500">
                          <UserCheck className="h-3 w-3" />
                          {CONTATO_LABEL[contatoStatus]}
                        </p>
                      </div>
                      {hasRequest ? (
                        <span
                          className={`badge self-start ${
                            item.solicitacao_atrasada
                              ? "bg-red-50 text-red-700"
                              : item.solicitacao_atendida
                                ? "badge-success"
                                : "badge-warn"
                          }`}
                        >
                          {item.solicitacao_atrasada
                            ? "Solicitação atrasada"
                            : item.solicitacao_atendida
                              ? "Solicitação atendida"
                              : "Solicitação pendente"}
                        </span>
                      ) : (
                        <span className="badge badge-neutral self-start">
                          Sem solicitação
                        </span>
                      )}
                    </div>

                    <div className="mt-3 space-y-3 text-sm">
                      <div>
                        <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                          Recado
                        </p>
                        <p className="mt-1 whitespace-pre-wrap text-slate-700">
                          {item.resumo}
                        </p>
                      </div>

                      {hasRequest && (
                        <div
                          className={`rounded-lg p-3 ${
                            item.solicitacao_atrasada
                              ? "bg-red-50/70"
                              : "bg-slate-50"
                          }`}
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                              O que foi solicitado
                            </p>
                            <span
                              className={`rounded-full px-2 py-1 text-[10px] font-semibold ${
                                PRIORIDADE_STYLE[prioridade]
                              }`}
                            >
                              {PRIORIDADE_LABEL[prioridade]}
                            </span>
                          </div>
                          <p className="mt-1 whitespace-pre-wrap text-slate-700">
                            {item.solicitacao}
                          </p>
                          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500">
                            {item.solicitacao_responsavel_id && (
                              <span className="flex items-center gap-1">
                                <UserCheck className="h-3 w-3" />
                                {responsavelById.get(
                                  item.solicitacao_responsavel_id,
                                ) ?? "Responsável"}
                              </span>
                            )}
                            {prazo && (
                              <span
                                className={`flex items-center gap-1 ${
                                  item.solicitacao_atrasada
                                    ? "font-semibold text-red-700"
                                    : ""
                                }`}
                              >
                                {item.solicitacao_atrasada ? (
                                  <AlertTriangle className="h-3 w-3" />
                                ) : (
                                  <CalendarClock className="h-3 w-3" />
                                )}
                                Prazo: {prazo}
                              </span>
                            )}
                          </div>
                          {item.solicitacao_atendida && item.atendida_em && (
                            <p className="mt-2 text-[11px] text-success-700">
                              Atendida em {formatCompactDate(item.atendida_em)}
                            </p>
                          )}
                        </div>
                      )}

                      {item.proximo_passo && (
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                            Próximo passo
                          </p>
                          <p className="mt-1 whitespace-pre-wrap text-slate-600">
                            {item.proximo_passo}
                          </p>
                        </div>
                      )}

                      {contatoStatus === "iniciado" && item.pode_editar && (
                        <div className="rounded-lg border border-info-100 bg-info-50 p-3 dark:border-info-900 dark:bg-info-950/40">
                          <p className="text-xs font-medium text-info-800 dark:text-info-200">
                            Confirme o resultado deste contato.
                          </p>
                          <div className="mt-2 flex flex-wrap gap-2">
                            <button
                              type="button"
                              className="btn-outline text-xs"
                              disabled={updatingId === item.id}
                              onClick={() => updateContact(item, "confirmado")}
                            >
                              <CheckCircle className="h-3.5 w-3.5" />
                              Confirmar contato
                            </button>
                            <button
                              type="button"
                              className="btn-ghost text-xs"
                              disabled={updatingId === item.id}
                              onClick={() =>
                                updateContact(item, "nao_concluido")
                              }
                            >
                              <XCircle className="h-3.5 w-3.5" />
                              Não concluído
                            </button>
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3">
                      <div className="flex flex-wrap items-center gap-3 text-xs">
                        {item.case_id && (
                          <Link
                            to={`/casos/${item.case_id}`}
                            className="font-medium text-bronze hover:text-bronze-dark"
                          >
                            Ver caso
                          </Link>
                        )}
                        {item.task_id && (
                          <Link
                            to="/tarefas"
                            className="flex items-center gap-1 font-medium text-bronze hover:text-bronze-dark"
                          >
                            <ListTodo className="h-3 w-3" />
                            Ver tarefa
                          </Link>
                        )}
                        <Link
                          to={`/clientes/${clientId}?tab=documentos`}
                          className="flex items-center gap-1 text-slate-500 hover:text-bronze"
                        >
                          <FileText className="h-3 w-3" />
                          Documentos
                        </Link>
                      </div>
                      {hasRequest && item.pode_editar && (
                        <button
                          type="button"
                          className={
                            item.solicitacao_atendida
                              ? "btn-ghost text-xs"
                              : "btn-outline text-xs"
                          }
                          disabled={updatingId === item.id}
                          onClick={() => toggleAttended(item)}
                        >
                          {item.solicitacao_atendida ? (
                            <RotateCcw className="h-3.5 w-3.5" />
                          ) : (
                            <CheckCircle className="h-3.5 w-3.5" />
                          )}
                          {updatingId === item.id
                            ? "Atualizando..."
                            : item.solicitacao_atendida
                              ? "Reabrir solicitação"
                              : "Marcar como atendida"}
                        </button>
                      )}
                    </div>

                    <div className="mt-3 border-t border-slate-100 pt-3">
                      <button
                        type="button"
                        className="flex items-center gap-1 text-[11px] font-medium text-slate-500 hover:text-bronze"
                        onClick={() => toggleAudit(item.id)}
                        aria-expanded={expandedAuditId === item.id}
                      >
                        <ClipboardCheck className="h-3 w-3" />
                        Histórico de auditoria
                        {expandedAuditId === item.id ? (
                          <ChevronUp className="h-3 w-3" />
                        ) : (
                          <ChevronDown className="h-3 w-3" />
                        )}
                      </button>

                      {expandedAuditId === item.id && (
                        <div className="mt-2 rounded-lg bg-slate-50 p-3">
                          {loadingAuditId === item.id ? (
                            <p className="text-xs text-slate-500">
                              Carregando histórico...
                            </p>
                          ) : auditEntries.length === 0 ? (
                            <p className="text-xs text-slate-500">
                              Nenhum evento de auditoria disponível.
                            </p>
                          ) : (
                            <ol className="space-y-2">
                              {auditEntries.map((event) => (
                                <li
                                  key={event.id}
                                  className="text-[11px] text-slate-600"
                                >
                                  <span className="font-semibold capitalize text-slate-700">
                                    {event.acao}
                                  </span>{" "}
                                  por {event.usuario_nome}
                                  {event.data &&
                                    ` em ${formatCompactDate(event.data)}`}
                                  {event.detalhes && (
                                    <span className="mt-0.5 block text-slate-500">
                                      {event.detalhes}
                                    </span>
                                  )}
                                </li>
                              ))}
                            </ol>
                          )}
                        </div>
                      )}
                    </div>
                  </article>
                </li>
              );
            })}
          </ol>

          {items.length < total && (
            <div className="mt-4 flex justify-center border-t border-slate-100 pt-4">
              <button
                type="button"
                className="btn-outline text-xs"
                onClick={() => load(page + 1, true)}
                disabled={loadingMore}
              >
                {loadingMore ? "Carregando..." : "Carregar mais atendimentos"}
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
