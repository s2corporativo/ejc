import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  Building2,
  Check,
  Pencil,
  Search,
  Settings2,
  UserRound,
  Wallet,
} from "lucide-react";
import api from "../lib/api";
import { Modal, Spinner, fmtMoney } from "../components/UI";
import { toast } from "../components/Toast";

interface CommissionRow {
  id: string;
  case_id: string;
  advogado_id?: string | null;
  advogado?: string | null;
  cliente?: string | null;
  caso?: string | null;
  numero_interno?: string | null;
  data_pagamento?: string | null;
  bruto_recebido: number;
  despesas_deduzidas: number;
  base_liquida: number;
  percentual_advogado: number;
  valor_advogado: number;
  valor_escritorio: number;
  regra_nome?: string | null;
  withdrawal_id?: string | null;
  status: string;
}

interface RuleRow {
  id: string;
  nome: string;
  escopo: "padrao" | "area" | "advogado" | "caso";
  percentual_advogado: number;
  descontar_despesas: boolean;
  prioridade: number;
  ativo: boolean;
  area?: string | null;
  advogado_id?: string | null;
  advogado_nome?: string | null;
  case_id?: string | null;
  caso_titulo?: string | null;
  numero_interno?: string | null;
}

interface Options {
  advogados: Array<{ id: string; full_name: string; role: string }>;
  casos: Array<{
    id: string;
    titulo: string;
    numero_interno?: string;
    area?: string;
  }>;
  areas: string[];
}

const STATUS_LABEL: Record<string, string> = {
  calculada: "Calculada",
  a_aprovar: "A aprovar",
  a_pagar: "A pagar",
  paga: "Paga",
  rejeitada: "Rejeitada",
};

const STATUS_CLASS: Record<string, string> = {
  calculada:
    "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
  a_aprovar:
    "bg-amber-50 text-amber-700 dark:bg-amber-400/10 dark:text-amber-300",
  a_pagar: "bg-blue-50 text-blue-700 dark:bg-blue-400/10 dark:text-blue-300",
  paga: "bg-emerald-50 text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300",
  rejeitada: "bg-rose-50 text-rose-700 dark:bg-rose-400/10 dark:text-rose-300",
};

const EMPTY_RULE = {
  nome: "",
  escopo: "padrao" as RuleRow["escopo"],
  percentual_advogado: "50",
  descontar_despesas: true,
  area: "",
  advogado_id: "",
  case_id: "",
};

function fmtDate(value?: string | null) {
  if (!value) return "—";
  const raw = String(value).slice(0, 10).split("-");
  return raw.length === 3 ? raw.reverse().join("/") : value;
}

function ruleTarget(rule: RuleRow) {
  if (rule.escopo === "caso") {
    return (
      [rule.numero_interno, rule.caso_titulo].filter(Boolean).join(" · ") ||
      "Caso"
    );
  }
  if (rule.escopo === "advogado") return rule.advogado_nome || "Advogado";
  if (rule.escopo === "area") return rule.area || "Área";
  return "Todos os casos";
}

export default function Comissoes({ onBack }: { onBack: () => void }) {
  const [rows, setRows] = useState<CommissionRow[]>([]);
  const [resumo, setResumo] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const [busca, setBusca] = useState("");
  const [status, setStatus] = useState("");
  const [regrasOpen, setRegrasOpen] = useState(false);
  const [rules, setRules] = useState<RuleRow[]>([]);
  const [options, setOptions] = useState<Options>({
    advogados: [],
    casos: [],
    areas: [],
  });
  const [ruleForm, setRuleForm] = useState({ ...EMPTY_RULE });
  const [editRuleId, setEditRuleId] = useState<string | null>(null);
  const [salvandoRule, setSalvandoRule] = useState(false);
  const [acaoId, setAcaoId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/financeiro/comissoes");
      setRows(Array.isArray(data?.data) ? data.data : []);
      setResumo(data?.resumo ?? {});
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Falha ao carregar comissões.");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadRules = useCallback(async () => {
    try {
      const [r, o] = await Promise.all([
        api.get("/financeiro/comissoes/regras"),
        api.get("/financeiro/comissoes/opcoes"),
      ]);
      setRules(Array.isArray(r.data) ? r.data : []);
      setOptions(o.data ?? { advogados: [], casos: [], areas: [] });
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Falha ao carregar regras.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (regrasOpen) void loadRules();
  }, [regrasOpen, loadRules]);

  const visiveis = useMemo(() => {
    const termo = busca.trim().toLocaleLowerCase("pt-BR");
    return rows.filter((row) => {
      if (status && row.status !== status) return false;
      if (!termo) return true;
      return [
        row.advogado,
        row.cliente,
        row.caso,
        row.numero_interno,
        row.bruto_recebido,
        row.valor_advogado,
      ]
        .filter((v) => v != null)
        .join(" ")
        .toLocaleLowerCase("pt-BR")
        .includes(termo);
    });
  }, [rows, busca, status]);

  async function workflow(
    row: CommissionRow,
    action: "submit" | "approve" | "pay",
  ) {
    if (acaoId) return;
    if (action !== "submit" && !row.withdrawal_id) return;
    setAcaoId(row.id);
    try {
      if (action === "submit") {
        await api.post(`/financeiro/comissoes/${row.id}/enviar-aprovacao`);
        toast.success("Comissão enviada para aprovação.");
      } else {
        await api.patch(`/partner-withdrawals/${row.withdrawal_id}/${action}`);
        toast.success(
          action === "approve"
            ? "Comissão aprovada."
            : "Comissão marcada como paga.",
        );
      }
      await load();
    } catch (e: any) {
      toast.error(
        e?.response?.data?.detail || "Não foi possível atualizar a comissão.",
      );
    } finally {
      setAcaoId(null);
    }
  }

  function editRule(rule: RuleRow) {
    setEditRuleId(rule.id);
    setRuleForm({
      nome: rule.nome,
      escopo: rule.escopo,
      percentual_advogado: String(rule.percentual_advogado),
      descontar_despesas: rule.descontar_despesas,
      area: rule.area || "",
      advogado_id: rule.advogado_id || "",
      case_id: rule.case_id || "",
    });
  }

  function resetRule() {
    setEditRuleId(null);
    setRuleForm({ ...EMPTY_RULE });
  }

  async function saveRule() {
    const pct = Number(ruleForm.percentual_advogado);
    if (
      !ruleForm.nome.trim() ||
      !Number.isFinite(pct) ||
      pct < 0 ||
      pct > 100
    ) {
      toast.error("Informe nome e percentual entre 0% e 100%.");
      return;
    }
    if (ruleForm.escopo === "area" && !ruleForm.area) {
      toast.error("Selecione a área.");
      return;
    }
    if (ruleForm.escopo === "advogado" && !ruleForm.advogado_id) {
      toast.error("Selecione o advogado.");
      return;
    }
    if (ruleForm.escopo === "caso" && !ruleForm.case_id) {
      toast.error("Selecione o caso.");
      return;
    }

    setSalvandoRule(true);
    try {
      if (editRuleId) {
        await api.patch(`/financeiro/comissoes/regras/${editRuleId}`, {
          nome: ruleForm.nome.trim(),
          percentual_advogado: pct,
          descontar_despesas: ruleForm.descontar_despesas,
        });
      } else {
        await api.post("/financeiro/comissoes/regras", {
          nome: ruleForm.nome.trim(),
          escopo: ruleForm.escopo,
          percentual_advogado: pct,
          descontar_despesas: ruleForm.descontar_despesas,
          prioridade: 100,
          area: ruleForm.escopo === "area" ? ruleForm.area : null,
          advogado_id:
            ruleForm.escopo === "advogado" ? ruleForm.advogado_id : null,
          case_id: ruleForm.escopo === "caso" ? ruleForm.case_id : null,
        });
      }
      toast.success(editRuleId ? "Regra atualizada." : "Regra criada.");
      resetRule();
      await loadRules();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Falha ao salvar regra.");
    } finally {
      setSalvandoRule(false);
    }
  }

  async function toggleRule(rule: RuleRow) {
    try {
      await api.patch(`/financeiro/comissoes/regras/${rule.id}`, {
        ativo: !rule.ativo,
      });
      await loadRules();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Falha ao alterar regra.");
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button type="button" className="btn-ghost" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
          Honorários
        </button>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => setRegrasOpen(true)}
        >
          <Settings2 className="h-4 w-4" />
          Regras
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {[
          ["A aprovar", resumo.a_aprovar, UserRound],
          ["A pagar", resumo.a_pagar, Wallet],
          ["Pago no mês", resumo.paga_mes, Check],
          ["Parcela do escritório", resumo.escritorio_total, Building2],
        ].map(([label, value, Icon]: any) => (
          <div key={label} className="card p-4">
            <div className="flex items-center gap-2 text-slate-400">
              <Icon className="h-4 w-4" />
              <span className="text-xs font-medium uppercase tracking-wide">
                {label}
              </span>
            </div>
            <p className="mt-2 text-xl font-semibold text-slate-900 dark:text-white">
              {fmtMoney(Number(value || 0))}
            </p>
          </div>
        ))}
      </div>

      <div className="card flex flex-wrap items-center gap-2 p-3">
        <div className="flex min-w-[240px] flex-1 items-center gap-2 rounded-lg border border-slate-200 px-3 dark:border-slate-700">
          <Search className="h-4 w-4 text-slate-400" />
          <input
            className="min-w-0 flex-1 bg-transparent py-2 text-sm outline-none"
            placeholder="Buscar advogado, cliente, caso ou valor"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </div>
        <select
          className="input w-auto"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">Todos os status</option>
          <option value="calculada">Calculada</option>
          <option value="a_aprovar">A aprovar</option>
          <option value="a_pagar">A pagar</option>
          <option value="paga">Paga</option>
          <option value="rejeitada">Rejeitada</option>
        </select>
      </div>

      {loading ? (
        <Spinner />
      ) : visiveis.length === 0 ? (
        <div className="card p-8 text-center text-sm text-slate-400">
          Nenhuma comissão encontrada.
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[980px] text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-400 dark:bg-white/[0.04]">
              <tr>
                <th className="px-4 py-3 text-left">Advogado</th>
                <th className="px-4 py-3 text-left">Cliente / caso</th>
                <th className="px-4 py-3 text-right">Recebido</th>
                <th className="px-4 py-3 text-right">Despesas</th>
                <th className="px-4 py-3 text-right">Base líquida</th>
                <th className="px-4 py-3 text-right">%</th>
                <th className="px-4 py-3 text-right">Comissão</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {visiveis.map((row) => (
                <tr key={row.id}>
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-800 dark:text-slate-100">
                      {row.advogado || "Sem responsável"}
                    </div>
                    <div className="text-[11px] text-slate-400">
                      {row.regra_nome || "Regra histórica"}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-700 dark:text-slate-200">
                      {row.cliente || "Cliente"}
                    </div>
                    <div className="max-w-[260px] truncate text-xs text-slate-400">
                      {[row.numero_interno, row.caso]
                        .filter(Boolean)
                        .join(" · ")}
                      {" · "}
                      {fmtDate(row.data_pagamento)}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right font-medium">
                    {fmtMoney(Number(row.bruto_recebido || 0))}
                  </td>
                  <td className="px-4 py-3 text-right text-slate-500">
                    {fmtMoney(Number(row.despesas_deduzidas || 0))}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {fmtMoney(Number(row.base_liquida || 0))}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {Number(row.percentual_advogado || 0).toLocaleString(
                      "pt-BR",
                    )}
                    %
                  </td>
                  <td className="px-4 py-3 text-right font-semibold">
                    {fmtMoney(Number(row.valor_advogado || 0))}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-1 text-xs font-medium ${
                        STATUS_CLASS[row.status] || STATUS_CLASS.calculada
                      }`}
                    >
                      {STATUS_LABEL[row.status] || row.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {row.status === "calculada" && (
                      <button
                        type="button"
                        className="btn-secondary px-2.5 py-1 text-xs"
                        disabled={acaoId === row.id}
                        onClick={() => workflow(row, "submit")}
                      >
                        Enviar p/ aprovação
                      </button>
                    )}
                    {row.status === "a_aprovar" && row.withdrawal_id && (
                      <button
                        type="button"
                        className="btn-secondary px-2.5 py-1 text-xs"
                        disabled={acaoId === row.id}
                        onClick={() => workflow(row, "approve")}
                      >
                        Aprovar
                      </button>
                    )}
                    {row.status === "a_pagar" && row.withdrawal_id && (
                      <button
                        type="button"
                        className="btn-primary px-2.5 py-1 text-xs"
                        disabled={acaoId === row.id}
                        onClick={() => workflow(row, "pay")}
                      >
                        Pagar
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="px-1 text-[11px] text-slate-400">
        Comissão é calculada apenas sobre recebimentos efetivos. Alterações de
        regra não modificam rateios históricos.
      </p>

      <Modal
        open={regrasOpen}
        onClose={() => {
          setRegrasOpen(false);
          resetRule();
        }}
        title="Regras de comissão"
        wide
      >
        <div className="space-y-5">
          <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label className="label">Nome da regra</label>
                <input
                  className="input"
                  value={ruleForm.nome}
                  onChange={(e) =>
                    setRuleForm({ ...ruleForm, nome: e.target.value })
                  }
                  placeholder="Ex.: João — Contencioso empresarial"
                />
              </div>
              <div>
                <label className="label">Escopo</label>
                <select
                  className="input"
                  disabled={!!editRuleId}
                  value={ruleForm.escopo}
                  onChange={(e) =>
                    setRuleForm({
                      ...ruleForm,
                      escopo: e.target.value as RuleRow["escopo"],
                      area: "",
                      advogado_id: "",
                      case_id: "",
                    })
                  }
                >
                  <option value="padrao">Padrão do escritório</option>
                  <option value="area">Área</option>
                  <option value="advogado">Advogado</option>
                  <option value="caso">Caso específico</option>
                </select>
              </div>
              <div>
                <label className="label">Comissão do advogado (%)</label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  className="input"
                  value={ruleForm.percentual_advogado}
                  onChange={(e) =>
                    setRuleForm({
                      ...ruleForm,
                      percentual_advogado: e.target.value,
                    })
                  }
                />
              </div>

              {ruleForm.escopo === "area" && (
                <div className="sm:col-span-2">
                  <label className="label">Área</label>
                  <select
                    className="input"
                    disabled={!!editRuleId}
                    value={ruleForm.area}
                    onChange={(e) =>
                      setRuleForm({ ...ruleForm, area: e.target.value })
                    }
                  >
                    <option value="">Selecione...</option>
                    {options.areas.map((area) => (
                      <option key={area} value={area}>
                        {area}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {ruleForm.escopo === "advogado" && (
                <div className="sm:col-span-2">
                  <label className="label">Advogado</label>
                  <select
                    className="input"
                    disabled={!!editRuleId}
                    value={ruleForm.advogado_id}
                    onChange={(e) =>
                      setRuleForm({
                        ...ruleForm,
                        advogado_id: e.target.value,
                      })
                    }
                  >
                    <option value="">Selecione...</option>
                    {options.advogados.map((adv) => (
                      <option key={adv.id} value={adv.id}>
                        {adv.full_name}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {ruleForm.escopo === "caso" && (
                <div className="sm:col-span-2">
                  <label className="label">Caso</label>
                  <select
                    className="input"
                    disabled={!!editRuleId}
                    value={ruleForm.case_id}
                    onChange={(e) =>
                      setRuleForm({ ...ruleForm, case_id: e.target.value })
                    }
                  >
                    <option value="">Selecione...</option>
                    {options.casos.map((caso) => (
                      <option key={caso.id} value={caso.id}>
                        {[caso.numero_interno, caso.titulo]
                          .filter(Boolean)
                          .join(" · ")}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <label className="sm:col-span-2 flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
                <input
                  type="checkbox"
                  checked={ruleForm.descontar_despesas}
                  onChange={(e) =>
                    setRuleForm({
                      ...ruleForm,
                      descontar_despesas: e.target.checked,
                    })
                  }
                />
                Descontar despesas efetivamente pagas do caso antes de calcular
                a comissão
              </label>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              {editRuleId && (
                <button type="button" className="btn-ghost" onClick={resetRule}>
                  Cancelar edição
                </button>
              )}
              <button
                type="button"
                className="btn-primary"
                disabled={salvandoRule}
                onClick={saveRule}
              >
                {salvandoRule
                  ? "Salvando..."
                  : editRuleId
                    ? "Salvar regra"
                    : "Criar regra"}
              </button>
            </div>
          </div>

          <div className="max-h-72 divide-y divide-slate-100 overflow-y-auto dark:divide-slate-800">
            {rules.map((rule) => (
              <div key={rule.id} className="flex items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-sm font-medium text-slate-800 dark:text-slate-100">
                      {rule.nome}
                    </p>
                    {!rule.ativo && (
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">
                        inativa
                      </span>
                    )}
                  </div>
                  <p className="truncate text-xs text-slate-400">
                    {ruleTarget(rule)} ·{" "}
                    {Number(rule.percentual_advogado).toLocaleString("pt-BR")}%
                    {rule.descontar_despesas
                      ? " · líquido após despesas"
                      : " · sobre bruto"}
                  </p>
                </div>
                <button
                  type="button"
                  className="btn-ghost p-2"
                  title="Editar"
                  onClick={() => editRule(rule)}
                >
                  <Pencil className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  className="btn-ghost px-2 py-1 text-xs"
                  onClick={() => toggleRule(rule)}
                >
                  {rule.ativo ? "Desativar" : "Ativar"}
                </button>
              </div>
            ))}
          </div>
        </div>
      </Modal>
    </div>
  );
}
