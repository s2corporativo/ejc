import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CalendarClock,
  CheckCircle2,
  Clock3,
  Loader2,
  Pencil,
  ShieldAlert,
} from "lucide-react";
import api from "../lib/api";
import { useAuth } from "../stores/auth";
import { toast } from "./Toast";

type Urgency = "baixa" | "media" | "alta" | "critica";
type WaitingOn = "ninguem" | "cliente" | "terceiro" | "tribunal" | "interno";
type OriginType = "manual" | "documento" | "movimento" | "prazo" | "tarefa";

interface NextAction {
  id: string;
  title: string;
  owner_id: string;
  due_at: string;
  urgency: Urgency;
  blocked: boolean;
  blocked_reason?: string | null;
  waiting_on: WaitingOn;
  origin_type: OriginType;
  origin_id?: string | null;
}

interface NextActionWaiver {
  reason: string;
  expires_at: string;
}

interface AssignableUser {
  id: string;
  full_name: string;
  role: string;
}

interface OperationalView {
  case_id: string;
  estado_operacional:
    | "onboarding"
    | "planejamento"
    | "em_andamento"
    | "aguardando_cliente"
    | "aguardando_terceiro"
    | "providencia_urgente"
    | "negociacao"
    | "encerramento"
    | "encerrado";
  next_action: NextAction | null;
  waiver: NextActionWaiver | null;
  enforcement_enabled: boolean;
}

interface ActionDraft {
  title: string;
  ownerId: string;
  dueAt: string;
  urgency: Urgency;
  blocked: boolean;
  blockedReason: string;
  waitingOn: WaitingOn;
  originType: OriginType;
  originId: string | null;
}

type FormMode = "action" | "replacement" | "waiver" | null;

const STATE_LABELS: Record<OperationalView["estado_operacional"], string> = {
  onboarding: "Onboarding",
  planejamento: "Planejamento",
  em_andamento: "Em andamento",
  aguardando_cliente: "Aguardando cliente",
  aguardando_terceiro: "Aguardando terceiro",
  providencia_urgente: "Providência urgente",
  negociacao: "Negociação",
  encerramento: "Encerramento",
  encerrado: "Encerrado",
};

const URGENCY_LABELS: Record<Urgency, string> = {
  baixa: "Baixa",
  media: "Média",
  alta: "Alta",
  critica: "Crítica",
};

const URGENCY_CLASSES: Record<Urgency, string> = {
  baixa: "border-slate-200 bg-slate-50 text-slate-700",
  media: "border-blue-200 bg-blue-50 text-blue-700",
  alta: "border-amber-200 bg-amber-50 text-amber-800",
  critica: "border-red-200 bg-red-50 text-red-700",
};

const WRITABLE_ROLES = new Set([
  "superadmin",
  "admin",
  "socio",
  "advogado",
  "advogado_auxiliar",
]);

function localDateTime(value: string | Date): string {
  const date = typeof value === "string" ? new Date(value) : value;
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function initialDueAt(days = 1): string {
  const date = new Date(Date.now() + days * 86_400_000);
  date.setHours(17, 0, 0, 0);
  return localDateTime(date);
}

function newDraft(ownerId: string): ActionDraft {
  return {
    title: "",
    ownerId,
    dueAt: initialDueAt(),
    urgency: "media",
    blocked: false,
    blockedReason: "",
    waitingOn: "ninguem",
    originType: "manual",
    originId: null,
  };
}

function draftFromAction(action: NextAction): ActionDraft {
  return {
    title: action.title,
    ownerId: action.owner_id,
    dueAt: localDateTime(action.due_at),
    urgency: action.urgency,
    blocked: action.blocked,
    blockedReason: action.blocked_reason || "",
    waitingOn: action.waiting_on,
    originType: action.origin_type,
    originId: action.origin_id || null,
  };
}

function fmtDateTime(value: string): string {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function errorMessage(error: any, fallback: string): string {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
  return fallback;
}

function actionPayload(draft: ActionDraft) {
  return {
    title: draft.title.trim(),
    owner_id: draft.ownerId,
    due_at: new Date(draft.dueAt).toISOString(),
    urgency: draft.urgency,
    blocked: draft.blocked,
    blocked_reason: draft.blocked ? draft.blockedReason.trim() : null,
    waiting_on: draft.blocked ? draft.waitingOn : "ninguem",
    origin_type: draft.originType,
    origin_id: draft.originType === "manual" ? null : draft.originId,
  };
}

function validateDraft(draft: ActionDraft): string | null {
  if (draft.title.trim().length < 3) {
    return "Descreva a próxima ação com pelo menos 3 caracteres.";
  }
  if (!draft.ownerId)
    return "Defina o responsável do caso antes da próxima ação.";
  const dueAt = new Date(draft.dueAt);
  if (Number.isNaN(dueAt.getTime()) || dueAt <= new Date()) {
    return "A data esperada deve estar no futuro.";
  }
  if (draft.blocked && draft.blockedReason.trim().length < 5) {
    return "Explique o bloqueio com pelo menos 5 caracteres.";
  }
  return null;
}

export default function CaseNextActionPanel({
  caseId,
  responsibleId,
  closed = false,
}: {
  caseId: string;
  responsibleId?: string;
  closed?: boolean;
}) {
  const { user } = useAuth();
  const defaultOwnerId = responsibleId || user?.id || "";
  const [view, setView] = useState<OperationalView | null>(null);
  const [assignees, setAssignees] = useState<AssignableUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [mode, setMode] = useState<FormMode>(null);
  const [draft, setDraft] = useState<ActionDraft>(() =>
    newDraft(defaultOwnerId),
  );
  const [completionNote, setCompletionNote] = useState("");
  const [waiverReason, setWaiverReason] = useState("");
  const [waiverExpiresAt, setWaiverExpiresAt] = useState(initialDueAt(7));

  const canWrite = useMemo(
    () => !closed && WRITABLE_ROLES.has(user?.role || ""),
    [closed, user?.role],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get<OperationalView>(
        "/cases/" + caseId + "/proxima-acao",
      );
      setView(data);
      if (canWrite) {
        try {
          const response = await api.get<{ data: AssignableUser[] }>(
            "/cases/" + caseId + "/proxima-acao/responsaveis",
          );
          setAssignees(response.data.data || []);
        } catch {
          setAssignees([]);
        }
      }
    } catch (error) {
      toast.error(
        errorMessage(error, "Não foi possível carregar a próxima ação."),
      );
    } finally {
      setLoading(false);
    }
  }, [canWrite, caseId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!draft.ownerId && defaultOwnerId) {
      setDraft((current) => ({ ...current, ownerId: defaultOwnerId }));
    }
  }, [defaultOwnerId, draft.ownerId]);

  const closeForm = () => {
    setMode(null);
    setCompletionNote("");
    setWaiverReason("");
    setWaiverExpiresAt(initialDueAt(7));
  };

  const startAction = () => {
    setDraft(
      view?.next_action
        ? draftFromAction(view.next_action)
        : newDraft(defaultOwnerId),
    );
    setMode("action");
  };

  const startReplacement = () => {
    setDraft(newDraft(defaultOwnerId));
    setCompletionNote("");
    setMode("replacement");
  };

  const saveAction = async () => {
    const validation = validateDraft(draft);
    if (validation) {
      toast.error(validation);
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await api.put<OperationalView>(
        "/cases/" + caseId + "/proxima-acao",
        actionPayload(draft),
      );
      setView(data);
      closeForm();
      toast.success("Próxima ação registrada e incluída na linha do tempo.");
    } catch (error) {
      toast.error(
        errorMessage(error, "Não foi possível salvar a próxima ação."),
      );
    } finally {
      setSubmitting(false);
    }
  };

  const completeWithReplacement = async () => {
    const validation = validateDraft(draft);
    if (validation) {
      toast.error(validation);
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await api.post<OperationalView>(
        "/cases/" + caseId + "/proxima-acao/concluir",
        {
          completion_note: completionNote.trim() || null,
          replacement: actionPayload(draft),
        },
      );
      setView(data);
      closeForm();
      toast.success("Ação concluída e próxima providência registrada.");
    } catch (error) {
      toast.error(errorMessage(error, "Não foi possível concluir a ação."));
    } finally {
      setSubmitting(false);
    }
  };

  const completeWithoutReplacement = async () => {
    if (
      !window.confirm(
        "Concluir sem criar outra ação? O caso ficará sinalizado como pendente.",
      )
    ) {
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await api.post<OperationalView>(
        "/cases/" + caseId + "/proxima-acao/concluir",
        { completion_note: completionNote.trim() || null },
      );
      setView(data);
      closeForm();
      toast.success("Ação concluída. O caso está sem próxima ação.");
    } catch (error) {
      toast.error(errorMessage(error, "Não foi possível concluir a ação."));
    } finally {
      setSubmitting(false);
    }
  };

  const saveWaiver = async () => {
    if (waiverReason.trim().length < 10) {
      toast.error("A justificativa deve ter pelo menos 10 caracteres.");
      return;
    }
    const expiresAt = new Date(waiverExpiresAt);
    if (Number.isNaN(expiresAt.getTime()) || expiresAt <= new Date()) {
      toast.error("A validade da dispensa deve estar no futuro.");
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await api.post<OperationalView>(
        "/cases/" + caseId + "/proxima-acao/dispensar",
        {
          reason: waiverReason.trim(),
          expires_at: expiresAt.toISOString(),
        },
      );
      setView(data);
      closeForm();
      toast.success("Dispensa temporária registrada com auditoria.");
    } catch (error) {
      toast.error(
        errorMessage(error, "Não foi possível registrar a dispensa."),
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <section className="rounded-xl border border-blue-100 bg-white p-4 shadow-sm">
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Loader2 size={16} className="animate-spin text-blue-600" />
          Carregando núcleo operacional...
        </div>
      </section>
    );
  }

  if (!view) return null;

  const action = view.next_action;
  const overdue = Boolean(action && new Date(action.due_at) < new Date());

  return (
    <section className="rounded-xl border border-blue-100 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <CalendarClock size={18} className="text-blue-600" />
            <h3 className="font-semibold text-slate-900">
              Próxima ação do caso
            </h3>
            <span className="rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
              {STATE_LABELS[view.estado_operacional]}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            O que fazer, por quem, até quando e com qual impedimento.
          </p>
        </div>
        {canWrite && mode === null && (
          <div className="flex flex-wrap gap-2">
            <button
              onClick={startAction}
              className="btn-secondary flex items-center gap-1"
            >
              <Pencil size={14} />
              {action ? "Editar" : "Definir próxima ação"}
            </button>
            {action && (
              <button
                onClick={startReplacement}
                className="btn-primary flex items-center gap-1"
              >
                <CheckCircle2 size={14} />
                Concluir e criar seguinte
              </button>
            )}
            <button
              onClick={() => setMode("waiver")}
              className="btn-secondary flex items-center gap-1"
            >
              <ShieldAlert size={14} />
              Dispensa temporária
            </button>
          </div>
        )}
      </div>

      {action ? (
        <div className="mt-4 grid gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4 md:grid-cols-[1fr_auto]">
          <div>
            <p className="font-medium text-slate-900">{action.title}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              <span
                className={
                  "rounded-full border px-2 py-0.5 font-medium " +
                  URGENCY_CLASSES[action.urgency]
                }
              >
                {URGENCY_LABELS[action.urgency]}
              </span>
              <span
                className={
                  "flex items-center gap-1 " +
                  (overdue ? "font-semibold text-red-700" : "text-slate-600")
                }
              >
                <Clock3 size={13} />
                {overdue ? "Vencida em " : "Até "}
                {fmtDateTime(action.due_at)}
              </span>
              <span className="text-slate-500">Responsável atribuído</span>
            </div>
            {action.blocked && (
              <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                <strong>Bloqueio:</strong> {action.blocked_reason}
                {action.waiting_on !== "ninguem" && (
                  <span className="ml-1">• aguardando {action.waiting_on}</span>
                )}
              </div>
            )}
          </div>
          <div className="text-right text-xs text-slate-500">
            Origem: {action.origin_type}
          </div>
        </div>
      ) : view.waiver ? (
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <p className="font-medium">Exceção temporária vigente</p>
          <p className="mt-1">{view.waiver.reason}</p>
          <p className="mt-2 text-xs">
            Válida até {fmtDateTime(view.waiver.expires_at)}. Depois disso, o
            caso volta automaticamente à fila de pendências.
          </p>
        </div>
      ) : (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <p className="font-medium">Caso ativo sem próxima ação</p>
          <p className="mt-1">
            Defina a providência seguinte ou registre uma exceção temporária
            justificada.
          </p>
        </div>
      )}

      {(mode === "action" || mode === "replacement") && (
        <div className="mt-4 space-y-4 rounded-lg border border-blue-200 bg-blue-50/40 p-4">
          <div>
            <h4 className="font-medium text-slate-900">
              {mode === "replacement"
                ? "Concluir e criar a ação seguinte"
                : action
                  ? "Editar próxima ação"
                  : "Definir próxima ação"}
            </h4>
            {mode === "replacement" && (
              <label className="mt-3 block">
                <span className="mb-1 block text-xs font-medium text-slate-700">
                  Nota de conclusão da ação atual
                </span>
                <textarea
                  value={completionNote}
                  onChange={(event) => setCompletionNote(event.target.value)}
                  className="input min-h-20 w-full"
                  maxLength={2000}
                  placeholder="Resultado obtido, documento gerado ou providência cumprida"
                />
              </label>
            )}
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <label className="md:col-span-2">
              <span className="mb-1 block text-xs font-medium text-slate-700">
                Providência
              </span>
              <input
                value={draft.title}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    title: event.target.value,
                  }))
                }
                className="input w-full"
                maxLength={255}
                placeholder="Ex.: Revisar contestação e enviar para aprovação"
              />
            </label>
            <label className="md:col-span-2">
              <span className="mb-1 block text-xs font-medium text-slate-700">
                Responsável
              </span>
              <select
                value={draft.ownerId}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    ownerId: event.target.value,
                  }))
                }
                className="input w-full"
                disabled={assignees.length === 0}
              >
                {!draft.ownerId && <option value="">Selecione</option>}
                {draft.ownerId &&
                  !assignees.some((item) => item.id === draft.ownerId) && (
                    <option value={draft.ownerId}>Responsável atual</option>
                  )}
                {assignees.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.full_name} — {item.role.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span className="mb-1 block text-xs font-medium text-slate-700">
                Data esperada
              </span>
              <input
                type="datetime-local"
                value={draft.dueAt}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    dueAt: event.target.value,
                  }))
                }
                className="input w-full"
              />
            </label>
            <label>
              <span className="mb-1 block text-xs font-medium text-slate-700">
                Urgência
              </span>
              <select
                value={draft.urgency}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    urgency: event.target.value as Urgency,
                  }))
                }
                className="input w-full"
              >
                <option value="baixa">Baixa</option>
                <option value="media">Média</option>
                <option value="alta">Alta</option>
                <option value="critica">Crítica</option>
              </select>
            </label>
          </div>

          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={draft.blocked}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  blocked: event.target.checked,
                  blockedReason: event.target.checked
                    ? current.blockedReason
                    : "",
                  waitingOn: event.target.checked
                    ? current.waitingOn
                    : "ninguem",
                }))
              }
            />
            Existe impedimento para executar esta ação
          </label>

          {draft.blocked && (
            <div className="grid gap-3 md:grid-cols-2">
              <label>
                <span className="mb-1 block text-xs font-medium text-slate-700">
                  Aguardando
                </span>
                <select
                  value={draft.waitingOn}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      waitingOn: event.target.value as WaitingOn,
                    }))
                  }
                  className="input w-full"
                >
                  <option value="ninguem">Ninguém</option>
                  <option value="cliente">Cliente</option>
                  <option value="terceiro">Terceiro</option>
                  <option value="tribunal">Tribunal/órgão</option>
                  <option value="interno">Equipe interna</option>
                </select>
              </label>
              <label>
                <span className="mb-1 block text-xs font-medium text-slate-700">
                  Motivo do bloqueio
                </span>
                <input
                  value={draft.blockedReason}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      blockedReason: event.target.value,
                    }))
                  }
                  className="input w-full"
                  maxLength={1000}
                />
              </label>
            </div>
          )}

          {!draft.ownerId && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              O caso ainda não tem responsável. Defina-o nos dados do caso antes
              de salvar a próxima ação.
            </div>
          )}

          <div className="flex flex-wrap justify-end gap-2">
            <button
              onClick={closeForm}
              disabled={submitting}
              className="btn-secondary"
            >
              Cancelar
            </button>
            {mode === "replacement" && action && !view.enforcement_enabled && (
              <button
                onClick={completeWithoutReplacement}
                disabled={submitting}
                className="btn-secondary text-amber-800"
              >
                Concluir sem seguinte
              </button>
            )}
            <button
              onClick={
                mode === "replacement" ? completeWithReplacement : saveAction
              }
              disabled={submitting || !draft.ownerId}
              className="btn-primary flex items-center gap-2"
            >
              {submitting && <Loader2 size={14} className="animate-spin" />}
              {mode === "replacement" ? "Concluir e substituir" : "Salvar ação"}
            </button>
          </div>
        </div>
      )}

      {mode === "waiver" && (
        <div className="mt-4 space-y-3 rounded-lg border border-amber-200 bg-amber-50/60 p-4">
          <div>
            <h4 className="font-medium text-amber-950">
              Dispensa temporária de próxima ação
            </h4>
            <p className="mt-1 text-xs text-amber-800">
              Use apenas quando não houver providência concreta. A
              justificativa, validade e autor ficam auditados.
            </p>
          </div>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-700">
              Justificativa
            </span>
            <textarea
              value={waiverReason}
              onChange={(event) => setWaiverReason(event.target.value)}
              className="input min-h-20 w-full"
              maxLength={2000}
              placeholder="Ex.: aguardando definição externa sem providência executável no período"
            />
          </label>
          <label className="block max-w-sm">
            <span className="mb-1 block text-xs font-medium text-slate-700">
              Válida até (máximo 90 dias)
            </span>
            <input
              type="datetime-local"
              value={waiverExpiresAt}
              onChange={(event) => setWaiverExpiresAt(event.target.value)}
              className="input w-full"
            />
          </label>
          <div className="flex justify-end gap-2">
            <button
              onClick={closeForm}
              disabled={submitting}
              className="btn-secondary"
            >
              Cancelar
            </button>
            <button
              onClick={saveWaiver}
              disabled={submitting}
              className="btn-primary flex items-center gap-2"
            >
              {submitting && <Loader2 size={14} className="animate-spin" />}
              Registrar dispensa
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
