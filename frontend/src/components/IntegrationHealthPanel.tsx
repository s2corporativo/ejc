import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CircleOff,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";
import { SectionCard, Spinner } from "./UI";

export type IntegrationState = "ready" | "attention" | "disabled";

export type IntegrationItem = {
  key: string;
  label: string;
  group: string;
  enabled: boolean;
  configured: boolean;
  status: IntegrationState;
  detail: string;
  mode?: string | null;
};

type IntegrationPayload = {
  mode: "configuration_only";
  checked_at: string;
  summary: {
    total: number;
    ready: number;
    attention: number;
    disabled: number;
  };
  items: IntegrationItem[];
  notice: string;
};

const STATUS_META = {
  ready: {
    label: "Configurada",
    className: "badge-success",
    icon: CheckCircle2,
    iconClass: "text-success-600 bg-success-50",
  },
  attention: {
    label: "Atenção",
    className: "badge-warn",
    icon: AlertTriangle,
    iconClass: "text-warn-700 bg-warn-50",
  },
  disabled: {
    label: "Desabilitada",
    className: "badge-neutral",
    icon: CircleOff,
    iconClass: "text-slate-500 bg-slate-100",
  },
} as const;

export function groupIntegrationItems(items: IntegrationItem[]) {
  const groups = new Map<string, IntegrationItem[]>();
  for (const item of items) {
    groups.set(item.group, [...(groups.get(item.group) ?? []), item]);
  }
  return Array.from(groups.entries());
}

export default function IntegrationHealthPanel() {
  const [data, setData] = useState<IntegrationPayload | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get<IntegrationPayload>(
        "/system-modules/integrations",
      );
      setData(response.data);
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail ||
          "Não foi possível carregar o status das integrações.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const groups = useMemo(
    () => groupIntegrationItems(data?.items ?? []),
    [data?.items],
  );

  return (
    <div className="space-y-5">
      <SectionCard
        title="Status de configuração"
        subtitle="Somente habilitação e presença de configuração; nenhum segredo é retornado ao navegador."
      >
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="grid flex-1 grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ["Total", data?.summary.total ?? "—"],
              ["Configuradas", data?.summary.ready ?? "—"],
              ["Atenção", data?.summary.attention ?? "—"],
              ["Desabilitadas", data?.summary.disabled ?? "—"],
            ].map(([label, value]) => (
              <div key={label} className="card p-3">
                <div className="text-xs text-slate-400">{label}</div>
                <div className="mt-1 text-xl font-semibold text-slate-800">
                  {value}
                </div>
              </div>
            ))}
          </div>
          <button
            type="button"
            className="btn-secondary"
            disabled={loading}
            onClick={load}
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Atualizar
          </button>
        </div>

        <div className="rounded-xl border border-primary-200 bg-primary-50/50 p-4 text-sm text-slate-600">
          <div className="flex items-start gap-2">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary-600" />
            <div>
              {data?.notice ||
                "Este painel não revela chaves, senhas, tokens ou conteúdo do ambiente."}
              {data?.checked_at && (
                <div className="mt-1 text-xs text-slate-400">
                  Verificado em{" "}
                  {new Date(data.checked_at).toLocaleString("pt-BR")}
                </div>
              )}
            </div>
          </div>
        </div>
      </SectionCard>

      {loading && !data ? (
        <Spinner />
      ) : (
        groups.map(([group, items]) => (
          <SectionCard key={group} title={group}>
            <div className="grid gap-3 md:grid-cols-2">
              {items.map((item) => {
                const meta = STATUS_META[item.status];
                const Icon = meta.icon;
                return (
                  <div
                    key={item.key}
                    className="card flex items-start gap-3 p-4"
                  >
                    <span className={`rounded-xl p-2.5 ${meta.iconClass}`}>
                      <Icon className="h-5 w-5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="text-sm font-semibold text-slate-800">
                          {item.label}
                        </div>
                        <span className={`badge ${meta.className}`}>
                          {meta.label}
                        </span>
                      </div>
                      <p className="mt-1 text-xs leading-5 text-slate-500">
                        {item.detail}
                      </p>
                      {item.mode && (
                        <div className="mt-2 text-[11px] text-slate-400">
                          Modo: {item.mode}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </SectionCard>
        ))
      )}
    </div>
  );
}
