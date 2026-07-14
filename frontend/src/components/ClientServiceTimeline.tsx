import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  CheckCircle,
  Clock,
  MessageSquare,
  Plus,
  RotateCcw,
  X,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";
import { Spinner } from "./UI";

type AtendimentoTipo =
  | "reuniao_presencial"
  | "reuniao_virtual"
  | "ligacao"
  | "email"
  | "whatsapp"
  | "protocolo"
  | "visita"
  | "outros";

type TimelineFilter = "todos" | "pendentes" | "atendidos";

export interface ClientTimelineCase {
  id: string | number;
  numero_interno: string;
  titulo: string;
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
  atendida_em?: string | null;
  proximo_passo?: string | null;
  pode_editar: boolean;
}

interface TimelineResponse {
  total: number;
  items: ClientServiceEntry[];
}

interface Props {
  clientId: string | number;
  cases?: ClientTimelineCase[];
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

function emptyForm() {
  return {
    tipo: "whatsapp" as AtendimentoTipo,
    data_atendimento: nowForInput(),
    resumo: "",
    solicitacao: "",
    case_id: "",
    solicitacao_atendida: false,
  };
}

export default function ClientServiceTimeline({
  clientId,
  cases = [],
}: Props) {
  const [items, setItems] = useState<ClientServiceEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [filter, setFilter] = useState<TimelineFilter>("todos");
  const [form, setForm] = useState(emptyForm);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get<TimelineResponse>("/atendimentos", {
        params: { client_id: String(clientId), page: 1, per_page: 100 },
      });
      setItems(response.data.items ?? []);
      setTotal(response.data.total ?? 0);
    } catch (error: any) {
      toast.error(
        error.response?.data?.detail ||
          "Não foi possível carregar a linha do tempo.",
      );
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [clientId]);

  useEffect(() => {
    load();
  }, [load]);

  const pendentes = useMemo(
    () =>
      items.filter(
        (item) => Boolean(item.solicitacao) && !item.solicitacao_atendida,
      ).length,
    [items],
  );
  const atendidos = useMemo(
    () =>
      items.filter(
        (item) => Boolean(item.solicitacao) && item.solicitacao_atendida,
      ).length,
    [items],
  );

  const filteredItems = useMemo(() => {
    if (filter === "pendentes") {
      return items.filter(
        (item) => Boolean(item.solicitacao) && !item.solicitacao_atendida,
      );
    }
    if (filter === "atendidos") {
      return items.filter(
        (item) => Boolean(item.solicitacao) && item.solicitacao_atendida,
      );
    }
    return items;
  }, [filter, items]);

  async function createEntry() {
    const resumo = form.resumo.trim();
    const solicitacao = form.solicitacao.trim();
    if (resumo.length < 10) {
      toast.error("O recado deve ter pelo menos 10 caracteres.");
      return;
    }

    setSaving(true);
    try {
      await api.post("/atendimentos", {
        client_id: String(clientId),
        case_id: form.case_id || undefined,
        tipo: form.tipo,
        data_atendimento: new Date(form.data_atendimento).toISOString(),
        resumo,
        solicitacao: solicitacao || undefined,
        solicitacao_atendida:
          Boolean(solicitacao) && form.solicitacao_atendida,
      });
      toast.success("Atendimento registrado na linha do tempo.");
      setForm(emptyForm());
      setShowForm(false);
      await load();
    } catch (error: any) {
      toast.error(
        error.response?.data?.detail || "Não foi possível salvar o atendimento.",
      );
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
      await load();
    } catch (error: any) {
      toast.error(
        error.response?.data?.detail ||
          "Não foi possível atualizar a solicitação.",
      );
    } finally {
      setUpdatingId(null);
    }
  }

  return (
    <section className="space-y-4" aria-labelledby="timeline-atendimentos-title">
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
              Dia, hora, recado e acompanhamento das solicitações do cliente.
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

        <div className="mt-4 grid grid-cols-3 gap-2">
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

      {!loading && filteredItems.length === 0 && (
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

      {!loading && filteredItems.length > 0 && (
        <div className="card p-4">
          {total > items.length && (
            <p className="mb-4 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
              Exibindo os {items.length} atendimentos mais recentes de {total}.
            </p>
          )}
          <ol className="relative ml-3 border-l border-bronze-pale">
            {filteredItems.map((item) => {
              const dateTime = formatDateTime(item.data_atendimento);
              const hasRequest = Boolean(item.solicitacao?.trim());
              return (
                <li key={item.id} className="relative pb-6 pl-6 last:pb-0">
                  <span
                    className={`absolute -left-2 top-1 flex h-4 w-4 items-center justify-center rounded-full border-2 border-white ${
                      hasRequest
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
                      </div>
                      {hasRequest ? (
                        <span
                          className={`badge self-start ${
                            item.solicitacao_atendida
                              ? "badge-success"
                              : "badge-warn"
                          }`}
                        >
                          {item.solicitacao_atendida
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
                        <div className="rounded-lg bg-slate-50 p-3">
                          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                            O que foi solicitado
                          </p>
                          <p className="mt-1 whitespace-pre-wrap text-slate-700">
                            {item.solicitacao}
                          </p>
                          {item.solicitacao_atendida && item.atendida_em && (
                            <p className="mt-2 text-[11px] text-success-700">
                              Atendida em{" "}
                              {new Date(item.atendida_em).toLocaleString(
                                "pt-BR",
                                {
                                  dateStyle: "short",
                                  timeStyle: "short",
                                },
                              )}
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
                    </div>

                    <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3">
                      <div className="text-xs text-slate-400">
                        {item.case_id && (
                          <Link
                            to={`/casos/${item.case_id}`}
                            className="font-medium text-bronze hover:text-bronze-dark"
                          >
                            Ver caso relacionado
                          </Link>
                        )}
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
                  </article>
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </section>
  );
}
