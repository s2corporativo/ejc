import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BellRing,
  CheckCircle2,
  Clock3,
  Loader2,
  Mail,
  MessageCircle,
  RefreshCw,
  ShieldCheck,
  Smartphone,
  Trash2,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";
import { SectionCard, cn } from "./UI";

type ChannelAvailability = {
  push: boolean;
  email: boolean;
  whatsapp: boolean;
};

type Preferences = {
  user_id: string;
  push_enabled: boolean;
  email_enabled: boolean;
  whatsapp_enabled: boolean;
  prazos_enabled: boolean;
  tarefas_enabled: boolean;
  intimacoes_enabled: boolean;
  audiencias_enabled: boolean;
  documentos_enabled: boolean;
  assinaturas_enabled: boolean;
  financeiro_enabled: boolean;
  diario_oficial_enabled: boolean;
  resumo_diario: boolean;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  timezone: string;
  created_at?: string | null;
  updated_at?: string | null;
};

type PreferenceEnvelope = {
  preferences: Preferences;
  available_channels: ChannelAvailability;
  effective_channels: ChannelAvailability;
  mandatory_internal_types: string[];
  notice: string;
};

type PushDevice = {
  id: string;
  created_at?: string | null;
};

type PushDeviceList = {
  data: PushDevice[];
  total: number;
  notice: string;
};

const CHANNELS = [
  {
    key: "push_enabled" as const,
    availability: "push" as const,
    label: "Push no navegador",
    description: "Alertas nos dispositivos inscritos no EJC.",
    icon: BellRing,
  },
  {
    key: "email_enabled" as const,
    availability: "email" as const,
    label: "E-mail",
    description: "Mensagens enviadas pelo SMTP institucional.",
    icon: Mail,
  },
  {
    key: "whatsapp_enabled" as const,
    availability: "whatsapp" as const,
    label: "WhatsApp",
    description: "Mensagens externas quando a integração estiver habilitada.",
    icon: MessageCircle,
  },
];

const CATEGORIES = [
  ["prazos_enabled", "Prazos"],
  ["tarefas_enabled", "Tarefas"],
  ["intimacoes_enabled", "Intimações"],
  ["audiencias_enabled", "Audiências"],
  ["documentos_enabled", "Documentos"],
  ["assinaturas_enabled", "Assinaturas"],
  ["financeiro_enabled", "Financeiro"],
  ["diario_oficial_enabled", "Diário Oficial"],
] as const;

function formatDate(value?: string | null) {
  if (!value) return "Data indisponível";
  return new Date(value).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function urlBase64ToUint8Array(value: string) {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  return Uint8Array.from([...raw].map((char) => char.charCodeAt(0)));
}

function Toggle({
  checked,
  disabled,
  onChange,
  label,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-6 w-11 rounded-full transition-colors",
        checked ? "bg-primary-600" : "bg-slate-200",
        disabled && "cursor-not-allowed opacity-50",
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform",
          checked ? "translate-x-5" : "translate-x-0.5",
        )}
      />
    </button>
  );
}

export default function NotificationPreferences() {
  const [data, setData] = useState<PreferenceEnvelope | null>(null);
  const [form, setForm] = useState<Preferences | null>(null);
  const [devices, setDevices] = useState<PushDeviceList | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyDevice, setBusyDevice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [preferenceResponse, deviceResponse] = await Promise.all([
        api.get<PreferenceEnvelope>("/notifications/preferences"),
        api.get<PushDeviceList>("/notifications/push/subscriptions"),
      ]);
      setData(preferenceResponse.data);
      setForm(preferenceResponse.data.preferences);
      setDevices(deviceResponse.data);
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail ||
          "Não foi possível carregar as preferências de notificação.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const quietEnabled = Boolean(
    form?.quiet_hours_start && form?.quiet_hours_end,
  );

  const hasChanges = useMemo(() => {
    if (!data || !form) return false;
    return JSON.stringify(data.preferences) !== JSON.stringify(form);
  }, [data, form]);

  const patch = <K extends keyof Preferences>(key: K, value: Preferences[K]) => {
    setForm((current) => (current ? { ...current, [key]: value } : current));
  };

  const save = async () => {
    if (!form) return;
    setSaving(true);
    try {
      const payload = {
        push_enabled: form.push_enabled,
        email_enabled: form.email_enabled,
        whatsapp_enabled: form.whatsapp_enabled,
        prazos_enabled: form.prazos_enabled,
        tarefas_enabled: form.tarefas_enabled,
        intimacoes_enabled: form.intimacoes_enabled,
        audiencias_enabled: form.audiencias_enabled,
        documentos_enabled: form.documentos_enabled,
        assinaturas_enabled: form.assinaturas_enabled,
        financeiro_enabled: form.financeiro_enabled,
        diario_oficial_enabled: form.diario_oficial_enabled,
        resumo_diario: form.resumo_diario,
        quiet_hours_start: form.quiet_hours_start,
        quiet_hours_end: form.quiet_hours_end,
        timezone: form.timezone,
      };
      const response = await api.put<PreferenceEnvelope>(
        "/notifications/preferences",
        payload,
      );
      setData(response.data);
      setForm(response.data.preferences);
      toast.success("Preferências de notificações atualizadas.");
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail ||
          "Não foi possível salvar as preferências.",
      );
    } finally {
      setSaving(false);
    }
  };

  const activatePush = async () => {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      toast.error("Este navegador não oferece suporte a Web Push.");
      return;
    }
    setBusyDevice("activate");
    try {
      const { data: vapid } = await api.get("/notifications/push/vapid-key");
      if (!vapid.enabled || !vapid.public_key) {
        toast.error("Web Push não está configurado no servidor.");
        return;
      }
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        toast.error("Permissão de notificações não concedida pelo navegador.");
        return;
      }
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapid.public_key),
      });
      const serialized = subscription.toJSON();
      if (!serialized.endpoint || !serialized.keys?.p256dh || !serialized.keys?.auth) {
        throw new Error("Assinatura push incompleta");
      }
      await api.post("/notifications/push/subscribe", {
        endpoint: serialized.endpoint,
        p256dh: serialized.keys.p256dh,
        auth: serialized.keys.auth,
      });
      toast.success("Dispositivo inscrito para receber push.");
      await load();
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail ||
          "Não foi possível ativar notificações neste dispositivo.",
      );
    } finally {
      setBusyDevice(null);
    }
  };

  const revokeDevice = async (deviceId: string) => {
    setBusyDevice(deviceId);
    try {
      await api.delete(`/notifications/push/subscriptions/${deviceId}`);
      toast.success("Dispositivo push revogado.");
      await load();
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail || "Não foi possível revogar o dispositivo.",
      );
    } finally {
      setBusyDevice(null);
    }
  };

  if (loading && !form) {
    return (
      <div className="flex justify-center py-16 text-slate-400">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }

  if (!form || !data) {
    return (
      <div className="card p-8 text-center text-sm text-slate-500">
        Preferências indisponíveis.
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-primary-200 bg-primary-50/50 p-4">
        <div className="flex items-start gap-3">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-primary-600" />
          <div className="text-sm text-slate-600">
            <div className="font-semibold text-slate-800">
              Alertas internos críticos permanecem obrigatórios
            </div>
            <p className="mt-1">{data.notice}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {data.mandatory_internal_types.map((type) => (
                <span key={type} className="badge badge-info capitalize">
                  {type}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      <SectionCard
        title="Canais externos"
        subtitle="Um canal só envia quando a preferência pessoal e a configuração institucional estiverem ativas."
      >
        <div className="grid gap-3 md:grid-cols-3">
          {CHANNELS.map(({ key, availability, label, description, icon: Icon }) => {
            const available = data.available_channels[availability];
            const effective = data.effective_channels[availability];
            return (
              <div key={key} className="rounded-xl border border-slate-200 bg-white p-4">
                <div className="flex items-start gap-3">
                  <span className="rounded-xl bg-slate-100 p-2.5 text-slate-600">
                    <Icon className="h-5 w-5" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-sm font-semibold text-slate-800">{label}</div>
                      <Toggle
                        label={label}
                        checked={form[key]}
                        disabled={!available}
                        onChange={(checked) => patch(key, checked)}
                      />
                    </div>
                    <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p>
                    <div className="mt-2 text-[11px] text-slate-400">
                      {effective ? (
                        <span className="inline-flex items-center gap-1 text-success-700">
                          <CheckCircle2 className="h-3.5 w-3.5" /> Efetivo
                        </span>
                      ) : available ? (
                        "Desativado pelo usuário"
                      ) : (
                        "Indisponível no servidor"
                      )}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </SectionCard>

      <SectionCard
        title="Categorias para canais externos"
        subtitle="Esses controles não removem alertas críticos do sino interno."
      >
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {CATEGORIES.map(([key, label]) => (
            <div
              key={key}
              className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3"
            >
              <span className="text-sm font-medium text-slate-700">{label}</span>
              <Toggle
                label={label}
                checked={form[key]}
                onChange={(checked) => patch(key, checked)}
              />
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard
        title="Resumo e horário silencioso"
        subtitle="O horário silencioso afeta apenas canais externos e usa o fuso informado."
      >
        <div className="grid gap-4 md:grid-cols-2">
          <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4">
            <div>
              <div className="text-sm font-semibold text-slate-800">Resumo diário</div>
              <div className="text-xs text-slate-500">Agrupa comunicações externas não urgentes.</div>
            </div>
            <Toggle
              label="Resumo diário"
              checked={form.resumo_diario}
              onChange={(checked) => patch("resumo_diario", checked)}
            />
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="flex items-center justify-between">
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-800">
                <Clock3 className="h-4 w-4" /> Horário silencioso
              </div>
              <Toggle
                label="Horário silencioso"
                checked={quietEnabled}
                onChange={(checked) => {
                  patch("quiet_hours_start", checked ? "22:00" : null);
                  patch("quiet_hours_end", checked ? "07:00" : null);
                }}
              />
            </div>
            {quietEnabled && (
              <div className="mt-3 grid grid-cols-2 gap-2">
                <input
                  type="time"
                  className="input"
                  value={(form.quiet_hours_start || "22:00").slice(0, 5)}
                  onChange={(event) => patch("quiet_hours_start", event.target.value)}
                />
                <input
                  type="time"
                  className="input"
                  value={(form.quiet_hours_end || "07:00").slice(0, 5)}
                  onChange={(event) => patch("quiet_hours_end", event.target.value)}
                />
              </div>
            )}
            <input
              className="input mt-3"
              value={form.timezone}
              onChange={(event) => patch("timezone", event.target.value)}
              aria-label="Fuso horário"
            />
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="Dispositivos Web Push"
        subtitle={devices?.notice || "Gerencie somente os dispositivos vinculados à sua conta."}
        actions={
          <button
            type="button"
            className="btn-secondary"
            onClick={() => void load()}
            disabled={loading}
          >
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            Atualizar
          </button>
        }
      >
        <div className="space-y-2">
          {(devices?.data || []).map((device) => (
            <div
              key={device.id}
              className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4"
            >
              <Smartphone className="h-5 w-5 text-primary-600" />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-slate-800">Dispositivo inscrito</div>
                <div className="text-xs text-slate-500">Criado em {formatDate(device.created_at)}</div>
              </div>
              <button
                type="button"
                className="btn-ghost text-danger-600"
                onClick={() => void revokeDevice(device.id)}
                disabled={busyDevice === device.id}
                aria-label="Revogar dispositivo"
              >
                {busyDevice === device.id ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
              </button>
            </div>
          ))}
          {!devices?.total && (
            <div className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
              Nenhum dispositivo inscrito.
            </div>
          )}
          <button
            type="button"
            className="btn-secondary"
            onClick={() => void activatePush()}
            disabled={busyDevice === "activate" || !data.available_channels.push}
          >
            {busyDevice === "activate" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <BellRing className="h-4 w-4" />
            )}
            Ativar neste dispositivo
          </button>
        </div>
      </SectionCard>

      <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4">
        <div className="text-xs text-slate-500">
          Última atualização: {formatDate(form.updated_at)}
        </div>
        <button
          type="button"
          className="btn-primary"
          onClick={() => void save()}
          disabled={!hasChanges || saving}
        >
          {saving && <Loader2 className="h-4 w-4 animate-spin" />}
          Salvar preferências
        </button>
      </div>
    </div>
  );
}
