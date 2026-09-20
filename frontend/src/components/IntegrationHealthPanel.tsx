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
  credential_state?: string | null;
  operational_state?: string | null;
  last_operational_at?: string | null;
  /** Conectores judiciais: o que a integração oferece ao fluxo do caso
   * (`capacidades` em GET /system-modules/integrations). Ausente nos demais. */
  capacidades?: Record<string, boolean> | null;
};

const ROTULO_CAPACIDADE: Record<string, string> = {
  consultar_processo: "consultar processo",
  sincronizar_movimentacoes: "movimentações",
  partes: "partes",
  audiencias: "audiências",
  baixar_documentos: "documentos",
  intimacoes: "intimações",
  protocolar: "protocolar",
};

export function capacidadesDoItem(item: IntegrationItem) {
  const caps = item.capacidades;
  if (!caps) return [];
  return Object.keys(ROTULO_CAPACIDADE).map((chave) => ({
    chave,
    rotulo: ROTULO_CAPACIDADE[chave],
    ativa: Boolean(caps[chave]),
  }));
}

/**
 * Estado do overlay do Cofre de Credenciais NESTE processo do backend
 * (`credential_overlay` em GET /system-modules/integrations). Campo opcional:
 * backend anterior ao Cofre simplesmente não o envia.
 */
export type CredentialOverlayState = {
  status?: string | null; // aplicado | falho | nao_aplicado | indisponivel
  aplicado?: boolean;
  aplicado_em?: string | null;
  campos?: number | null;
  erro_tipo?: string | null;
  falhas?: number | null;
};

type IntegrationPayload = {
  mode: "configuration_only" | "configuration_and_runtime";
  checked_at: string;
  summary: {
    total: number;
    ready: number;
    attention: number;
    disabled: number;
  };
  items: IntegrationItem[];
  credential_overlay?: CredentialOverlayState | null;
  notice: string;
};

const STATUS_META = {
  ready: {
    label: "Pronta",
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

/**
 * Aviso do overlay do Cofre — `null` quando não há o que avisar.
 *
 * Sem isto o painel MENTE no pior momento: com o overlay falho o backend segue
 * com os valores do arquivo de ambiente, que não conhece revogação, e cada item
 * abaixo continua sendo pintado de "Configurada" a partir desse mesmo Settings
 * — inclusive uma credencial já REVOGADA no cofre. O aviso é de painel (e não
 * por item) porque a degradação é do processo inteiro, não de uma integração.
 */
export function avisoOverlayCofre(
  overlay?: CredentialOverlayState | null,
): string | null {
  if (!overlay) return null; // backend sem o campo — nada a declarar
  if (overlay.aplicado) return null;
  if (overlay.status === "indisponivel") {
    return (
      "Não foi possível ler o estado do Cofre de Credenciais neste processo — " +
      "os estados abaixo podem não refletir o cofre."
    );
  }
  const motivo = overlay.erro_tipo ? ` (${overlay.erro_tipo})` : "";
  const tentativas =
    overlay.falhas && overlay.falhas > 1
      ? ` ${overlay.falhas} tentativas falharam até agora.`
      : "";
  return (
    `Cofre de Credenciais NÃO aplicado neste processo${motivo}: o backend está ` +
    "usando os valores do arquivo de ambiente, que não conhece revogação — uma " +
    "credencial revogada no cofre continua valendo até a reaplicação " +
    "(automática, a cada 10 min). Os estados abaixo podem dizer “Configurada” " +
    `para uma integração que já deveria estar sem credencial.${tentativas}`
  );
}

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
  const avisoOverlay = useMemo(
    () => avisoOverlayCofre(data?.credential_overlay),
    [data?.credential_overlay],
  );
  const runtimeDisponivel = data?.mode === "configuration_and_runtime";
  const statusSubtitle = runtimeDisponivel
    ? "Combina configuração, Cofre de Credenciais e última evidência operacional persistida; nenhum segredo é retornado ao navegador."
    : "Mostra habilitação e presença de configuração. Este backend não forneceu evidência operacional; nenhum segredo é retornado ao navegador.";

  return (
    <div className="space-y-5">
      <SectionCard
        title="Status das integrações"
        subtitle={statusSubtitle}
      >
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="grid flex-1 grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ["Total", data?.summary.total ?? "—"],
              [
                runtimeDisponivel ? "Prontas" : "Configuradas",
                data?.summary.ready ?? "—",
              ],
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

        {avisoOverlay && (
          <div
            role="alert"
            className="mb-4 flex items-start gap-2 rounded-xl border border-warn-200 bg-warn-50 p-4 text-sm text-warn-800"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <div className="font-semibold">
                Credenciais do Cofre fora de uso
              </div>
              <p className="mt-1 leading-5">{avisoOverlay}</p>
            </div>
          </div>
        )}

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
                          {item.status === "ready" && !runtimeDisponivel
                            ? "Configurada"
                            : meta.label}
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
                      {(item.operational_state || item.last_operational_at) && (
                        <div className="mt-1 text-[11px] text-slate-400">
                          {item.operational_state
                            ? `Operação: ${item.operational_state}`
                            : "Operação: sem evidência"}
                          {item.last_operational_at &&
                            ` · última evidência ${new Date(
                              item.last_operational_at,
                            ).toLocaleString("pt-BR")}`}
                        </div>
                      )}
                      {item.capacidades && (
                        <ul
                          className="mt-2 flex flex-wrap gap-1"
                          aria-label={`Capacidades de ${item.label}`}
                        >
                          {capacidadesDoItem(item).map((cap) => (
                            <li
                              key={cap.chave}
                              className={`rounded-full border px-2 py-0.5 text-[11px] ${
                                cap.ativa
                                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                                  : "border-slate-200 text-slate-400 line-through"
                              }`}
                            >
                              {cap.rotulo}
                            </li>
                          ))}
                        </ul>
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
