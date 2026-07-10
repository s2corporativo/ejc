import { useEffect, useMemo, useState } from "react";
import {
  Eye,
  EyeOff,
  Loader2,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  ShieldCheck,
} from "lucide-react";
import api from "../lib/api";
import { getModuleCatalog } from "../config/moduleRegistry";
import {
  useModuleLifecycleStore,
  type ModuleLifecycleOverride,
  type ModuleLifecycleStatus,
} from "../stores/moduleLifecycle";
import { toast } from "./Toast";
import { SectionCard, cn } from "./UI";

const STATUS_OPTIONS: Array<{
  value: ModuleLifecycleStatus;
  label: string;
  description: string;
}> = [
  { value: "active", label: "Ativo", description: "Disponível normalmente" },
  { value: "beta", label: "Beta", description: "Disponível em validação" },
  { value: "hidden", label: "Oculto", description: "Sem menu, acesso direto permitido" },
  { value: "legacy", label: "Legado", description: "Disponível durante transição" },
  { value: "disabled", label: "Desabilitado", description: "Rota bloqueada ou redirecionada" },
];

type Draft = {
  enabled: boolean;
  menu_visible: boolean;
  status: ModuleLifecycleStatus;
  replacement_route: string;
  removal_date: string;
  reason: string;
};

function defaultDraft(module: ReturnType<typeof getModuleCatalog>[number]): Draft {
  const status = (module.status ?? "active") as ModuleLifecycleStatus;
  return {
    enabled: status !== "disabled",
    menu_visible: status !== "hidden" && status !== "disabled",
    status,
    replacement_route: "",
    removal_date: "",
    reason: "",
  };
}

function overrideDraft(setting: ModuleLifecycleOverride): Draft {
  return {
    enabled: setting.enabled,
    menu_visible: setting.menu_visible,
    status: setting.status,
    replacement_route: setting.replacement_route ?? "",
    removal_date: setting.removal_date ?? "",
    reason: setting.reason ?? "",
  };
}

function normalizeStatus(draft: Draft, status: ModuleLifecycleStatus): Draft {
  if (status === "disabled") {
    return { ...draft, status, enabled: false, menu_visible: false };
  }
  if (status === "hidden") {
    return { ...draft, status, enabled: true, menu_visible: false };
  }
  return { ...draft, status, enabled: true };
}

export default function ModuleLifecycleSettings() {
  const {
    settings,
    protectedKeys,
    loaded,
    loading,
    load,
    upsertLocal,
    removeLocal,
  } = useModuleLifecycleStore();
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState("todos");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    void load();
  }, [load]);

  const modules = getModuleCatalog();
  const groups = useMemo(
    () => ["todos", ...Array.from(new Set(modules.map((module) => module.group)))],
    [modules],
  );
  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    return modules.filter((module) => {
      if (group !== "todos" && module.group !== group) return false;
      if (!term) return true;
      return `${module.key} ${module.label} ${module.path} ${module.group}`
        .toLowerCase()
        .includes(term);
    });
  }, [modules, query, group]);

  const selected = selectedKey
    ? modules.find((module) => module.key === selectedKey) ?? null
    : null;
  const selectedOverride = selectedKey ? settings[selectedKey] : undefined;
  const selectedProtected = Boolean(
    selectedKey && protectedKeys.includes(selectedKey),
  );

  const openEditor = (moduleKey: string) => {
    const module = modules.find((item) => item.key === moduleKey);
    if (!module) return;
    setSelectedKey(moduleKey);
    setDraft(
      settings[moduleKey]
        ? overrideDraft(settings[moduleKey])
        : defaultDraft(module),
    );
  };

  const save = async () => {
    if (!selectedKey || !draft) return;
    setSaving(true);
    try {
      const { data } = await api.put<ModuleLifecycleOverride>(
        `/system-modules/settings/${selectedKey}`,
        {
          ...draft,
          replacement_route: draft.replacement_route.trim() || null,
          removal_date: draft.removal_date || null,
          reason: draft.reason.trim() || null,
        },
      );
      upsertLocal(data);
      setDraft(overrideDraft(data));
      toast.success("Lifecycle do módulo atualizado.");
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail ||
          "Não foi possível atualizar o módulo.",
      );
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    if (!selectedKey || !selectedOverride || !selected) return;
    setSaving(true);
    try {
      await api.delete(`/system-modules/settings/${selectedKey}`);
      removeLocal(selectedKey);
      setDraft(defaultDraft(selected));
      toast.success("Override removido; manifesto local restaurado.");
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail || "Não foi possível remover o override.",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-primary-200 bg-primary-50/50 p-4 text-sm text-slate-600">
        <div className="flex items-start gap-3">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-primary-600" />
          <div>
            <div className="font-semibold text-slate-800">
              Feature flag não substitui autorização
            </div>
            <p className="mt-1">
              O lifecycle controla menu e disponibilidade da rota. Toda operação
              continua sujeita ao RBAC do backend.
            </p>
          </div>
        </div>
      </div>

      <SectionCard
        title="Módulos e funcionalidades"
        subtitle="Overrides auditados sobre o manifesto central. Módulos sem override seguem o código versionado."
      >
        <div className="mb-4 flex flex-col gap-3 md:flex-row">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
            <input
              className="input pl-9"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Buscar módulo, rota ou grupo..."
            />
          </div>
          <select
            className="input md:w-56"
            value={group}
            onChange={(event) => setGroup(event.target.value)}
          >
            {groups.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
          <button type="button" className="btn-secondary" onClick={load}>
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            Atualizar
          </button>
        </div>

        {!loaded ? (
          <div className="py-10 text-center text-sm text-slate-400">
            Carregando lifecycle...
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-200">
            <table className="table w-full text-sm">
              <thead>
                <tr>
                  <th className="text-left">Módulo</th>
                  <th className="text-left">Grupo</th>
                  <th className="text-left">Status efetivo</th>
                  <th className="text-left">Menu</th>
                  <th className="text-left">Override</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {filtered.map((module) => {
                  const override = settings[module.key];
                  const status = override?.status ?? module.status ?? "active";
                  const visible = override
                    ? override.menu_visible && override.enabled
                    : status !== "hidden" && status !== "disabled";
                  return (
                    <tr key={module.key}>
                      <td>
                        <div className="font-medium text-slate-800">
                          {module.label}
                        </div>
                        <div className="font-mono text-[11px] text-slate-400">
                          {module.path} · {module.key}
                        </div>
                      </td>
                      <td className="text-slate-600">{module.group}</td>
                      <td>
                        <span
                          className={`badge ${
                            status === "active"
                              ? "badge-success"
                              : status === "beta"
                                ? "badge-warn"
                                : status === "disabled"
                                  ? "badge-danger"
                                  : "badge-neutral"
                          }`}
                        >
                          {status}
                        </span>
                      </td>
                      <td>
                        <span className="inline-flex items-center gap-1 text-xs text-slate-500">
                          {visible ? (
                            <Eye className="h-3.5 w-3.5" />
                          ) : (
                            <EyeOff className="h-3.5 w-3.5" />
                          )}
                          {visible ? "Visível" : "Oculto"}
                        </span>
                      </td>
                      <td className="text-xs text-slate-500">
                        {override ? "Banco" : "Manifesto"}
                      </td>
                      <td className="text-right">
                        <button
                          type="button"
                          className="btn-ghost text-xs"
                          onClick={() => openEditor(module.key)}
                        >
                          Configurar
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {selected && draft && (
        <SectionCard
          title={`Configurar: ${selected.label}`}
          subtitle={`${selected.path} · ${selected.key}`}
        >
          {selectedProtected && (
            <div className="mb-4 rounded-lg border border-warn-200 bg-warn-50 p-3 text-sm text-warn-800">
              Módulo estrutural protegido: pode receber motivo e metadados, mas
              não pode ser ocultado ou desabilitado.
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="label">Status</label>
              <select
                className="input"
                value={draft.status}
                disabled={selectedProtected}
                onChange={(event) =>
                  setDraft(
                    normalizeStatus(
                      draft,
                      event.target.value as ModuleLifecycleStatus,
                    ),
                  )
                }
              >
                {STATUS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label} — {option.description}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Rota substituta</label>
              <input
                className="input"
                value={draft.replacement_route}
                onChange={(event) =>
                  setDraft({ ...draft, replacement_route: event.target.value })
                }
                placeholder="/casos ou /inteligencia?tab=..."
              />
            </div>
            <div>
              <label className="label">Remoção planejada</label>
              <input
                type="date"
                className="input"
                value={draft.removal_date}
                onChange={(event) =>
                  setDraft({ ...draft, removal_date: event.target.value })
                }
              />
            </div>
            <div className="flex items-end gap-5 pb-2">
              <label className="flex items-center gap-2 text-sm text-slate-600">
                <input
                  type="checkbox"
                  checked={draft.enabled}
                  disabled={selectedProtected || draft.status === "disabled"}
                  onChange={(event) =>
                    setDraft({ ...draft, enabled: event.target.checked })
                  }
                />
                Habilitado
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-600">
                <input
                  type="checkbox"
                  checked={draft.menu_visible}
                  disabled={
                    selectedProtected ||
                    draft.status === "hidden" ||
                    draft.status === "disabled"
                  }
                  onChange={(event) =>
                    setDraft({ ...draft, menu_visible: event.target.checked })
                  }
                />
                Exibir no menu
              </label>
            </div>
          </div>
          <div className="mt-4">
            <label className="label">Motivo / plano de transição</label>
            <textarea
              rows={3}
              className="input"
              value={draft.reason}
              onChange={(event) =>
                setDraft({ ...draft, reason: event.target.value })
              }
              placeholder="Explique por que o módulo está beta, legado, oculto ou desabilitado."
            />
          </div>

          <div className="mt-5 flex flex-wrap justify-end gap-2">
            {selectedOverride && (
              <button
                type="button"
                className="btn-secondary"
                disabled={saving}
                onClick={reset}
              >
                <RotateCcw className="h-4 w-4" /> Restaurar manifesto
              </button>
            )}
            <button
              type="button"
              className="btn-primary"
              disabled={saving}
              onClick={save}
            >
              {saving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Salvar lifecycle
            </button>
          </div>
        </SectionCard>
      )}
    </div>
  );
}
