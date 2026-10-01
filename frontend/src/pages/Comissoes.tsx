import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Building2,
  Check,
  FileCheck2,
  Pencil,
  Search,
  Settings2,
  SlidersHorizontal,
  Upload,
  UserRound,
  Wallet,
} from "lucide-react";
import api from "../lib/api";
import ExtratoSocio from "../components/ExtratoSocio";
import { Modal, Spinner, fmtMoney } from "../components/UI";
import { toast } from "../components/Toast";
import { apiErrorMessage } from "../lib/apiError";
import {
  COMMISSION_STATUS_LABELS,
  type CommissionStatus,
} from "../lib/financeiro";
import type {
  CommissionConference,
  CommissionForecast,
  CommissionLawyerSummary,
  CommissionListResponse,
  CommissionStatement,
  CommissionSummary,
  FinanceClosing,
} from "../types/financeiro";

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
  valor_advogado_efetivo: number;
  valor_escritorio_efetivo: number;
  ajustes_advogado: number;
  saldo_ajuste_pendente: number;
  ajustes_qtd: number;
  regra_nome?: string | null;
  regra_escopo?: string | null;
  withdrawal_id?: string | null;
  valor_ordem_pagamento?: number | null;
  status: CommissionStatus;
  payment_method?: string | null;
  payment_reference?: string | null;
  comprovante_doc_id?: string | null;
  payment_batch_id?: string | null;
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

const STATUS_LABEL = COMMISSION_STATUS_LABELS;

const STATUS_CLASS: Record<CommissionStatus, string> = {
  calculada:
    "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
  a_aprovar:
    "bg-amber-50 text-amber-700 dark:bg-amber-400/10 dark:text-amber-300",
  a_pagar: "bg-blue-50 text-blue-700 dark:bg-blue-400/10 dark:text-blue-300",
  paga: "bg-emerald-50 text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300",
  rejeitada: "bg-rose-50 text-rose-700 dark:bg-rose-400/10 dark:text-rose-300",
  estornada:
    "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400",
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

export default function Comissoes({
  competencia,
  focusId,
}: {
  competencia: string;
  focusId?: string;
}) {
  const [rows, setRows] = useState<CommissionRow[]>([]);
  const [resumo, setResumo] = useState<CommissionSummary>({});
  const [porAdvogado, setPorAdvogado] = useState<CommissionLawyerSummary[]>([]);
  const [previsao, setPrevisao] = useState<CommissionForecast>({});
  const [conferencia, setConferencia] = useState<CommissionConference | null>(
    null,
  );
  const [fechamento, setFechamento] = useState<FinanceClosing | null>(null);
  const [loading, setLoading] = useState(true);
  const [busca, setBusca] = useState("");
  const [status, setStatus] = useState<"" | CommissionStatus>("");

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

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [pagamentoOpen, setPagamentoOpen] = useState(false);
  const [pagando, setPagando] = useState(false);
  const [paymentForm, setPaymentForm] = useState({
    method: "pix",
    date: new Date().toISOString().slice(0, 10),
    reference: "",
    observacao: "",
  });
  const [proofFile, setProofFile] = useState<File | null>(null);

  const [ajusteRow, setAjusteRow] = useState<CommissionRow | null>(null);
  const [ajusteForm, setAjusteForm] = useState({ valor: "", motivo: "" });
  const [ajustando, setAjustando] = useState(false);

  const [extratoOpen, setExtratoOpen] = useState(false);
  const [extrato, setExtrato] = useState<CommissionStatement | null>(null);
  const [extratoLoading, setExtratoLoading] = useState(false);
  const [acaoId, setAcaoId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { competencia };
      const [baseResp, previsaoResp, conferenciaResp, fechamentoResp] =
        await Promise.all([
          api.get<CommissionListResponse<CommissionRow>>(
            "/financeiro/comissoes",
            { params },
          ),
          api.get<CommissionForecast>("/financeiro/comissoes/previsao", {
            params,
          }),
          api.get<CommissionConference>("/financeiro/comissoes/conferencia", {
            params,
          }),
          api.get<FinanceClosing>(
            `/financeiro/comissoes/fechamentos/${competencia}`,
          ),
        ]);
      const base = baseResp.data;
      setRows(base.data ?? []);
      setResumo(base.resumo ?? {});
      setPorAdvogado(base.por_advogado ?? []);
      setPrevisao(previsaoResp.data ?? {});
      setConferencia(conferenciaResp.data ?? null);
      setFechamento(fechamentoResp.data ?? null);
      setSelected(new Set());
    } catch (e: unknown) {
      toast.error(apiErrorMessage(e, "Falha ao carregar comissões."));
    } finally {
      setLoading(false);
    }
  }, [competencia]);

  const loadRules = useCallback(async () => {
    try {
      const [r, o] = await Promise.all([
        api.get("/financeiro/comissoes/regras"),
        api.get("/financeiro/comissoes/opcoes"),
      ]);
      setRules(Array.isArray(r.data) ? r.data : []);
      setOptions(o.data ?? { advogados: [], casos: [], areas: [] });
    } catch (e: unknown) {
      toast.error(apiErrorMessage(e, "Falha ao carregar regras."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (regrasOpen) void loadRules();
  }, [regrasOpen, loadRules]);

  useEffect(() => {
    if (!focusId || !rows.length) return;
    requestAnimationFrame(() => {
      const row = rows.find(
        (item) => item.id === focusId || item.withdrawal_id === focusId,
      );
      if (!row) return;
      document
        .getElementById(`finance-commission-${row.id}`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }, [focusId, rows]);

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
        row.valor_advogado_efetivo,
      ]
        .filter((v) => v != null)
        .join(" ")
        .toLocaleLowerCase("pt-BR")
        .includes(termo);
    });
  }, [rows, busca, status]);

  const payableIds = visiveis
    .filter((r) => r.status === "a_pagar" && r.withdrawal_id)
    .map((r) => r.withdrawal_id as string);

  async function workflow(row: CommissionRow, action: "submit" | "approve") {
    if (acaoId) return;
    if (action !== "submit" && !row.withdrawal_id) return;
    setAcaoId(row.id);
    try {
      if (action === "submit") {
        await api.post(`/financeiro/comissoes/${row.id}/enviar-aprovacao`);
        toast.success("Comissão enviada para aprovação.");
      } else {
        await api.patch(`/partner-withdrawals/${row.withdrawal_id}/approve`);
        toast.success("Comissão aprovada.");
      }
      await load();
    } catch (e: unknown) {
      toast.error(apiErrorMessage(e, "Não foi possível atualizar a comissão."));
    } finally {
      setAcaoId(null);
    }
  }

  function toggleSelected(withdrawalId: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(withdrawalId)) next.delete(withdrawalId);
      else next.add(withdrawalId);
      return next;
    });
  }

  function selectAllPayable() {
    setSelected((current) =>
      current.size === payableIds.length ? new Set() : new Set(payableIds),
    );
  }

  function openSinglePayment(row: CommissionRow) {
    if (!row.withdrawal_id) return;
    setSelected(new Set([row.withdrawal_id]));
    setPagamentoOpen(true);
  }

  async function uploadProof(): Promise<string | null> {
    if (!proofFile) return null;
    const fd = new FormData();
    fd.append("file", proofFile);
    fd.append("titulo", `Comprovante de comissões ${paymentForm.date}`);
    fd.append("tipo", "outro");
    fd.append("confidencialidade", "confidencial");
    const { data } = await api.post("/documents/upload", fd);
    return data?.id || null;
  }

  async function pagarSelecionadas() {
    if (selected.size === 0 || pagando) return;
    setPagando(true);
    try {
      const comprovanteId = await uploadProof();
      const paidAt = new Date(`${paymentForm.date}T12:00:00`).toISOString();
      const { data } = await api.post("/financeiro/comissoes/lotes-pagamento", {
        withdrawal_ids: Array.from(selected),
        payment_method: paymentForm.method,
        paid_at: paidAt,
        payment_reference: paymentForm.reference || null,
        comprovante_doc_id: comprovanteId,
        observacao: paymentForm.observacao || null,
      });
      toast.success(`Lote pago: ${fmtMoney(Number(data?.total_pago || 0))}.`);
      setPagamentoOpen(false);
      setProofFile(null);
      setPaymentForm({
        method: "pix",
        date: new Date().toISOString().slice(0, 10),
        reference: "",
        observacao: "",
      });
      await load();
    } catch (e: unknown) {
      toast.error(
        apiErrorMessage(e, "Não foi possível registrar o pagamento em lote."),
      );
    } finally {
      setPagando(false);
    }
  }

  async function salvarAjuste() {
    if (!ajusteRow || ajustando) return;
    const valor = Number(ajusteForm.valor.replace(",", "."));
    if (
      !Number.isFinite(valor) ||
      valor === 0 ||
      ajusteForm.motivo.trim().length < 3
    ) {
      toast.error("Informe valor diferente de zero e motivo do ajuste.");
      return;
    }
    setAjustando(true);
    try {
      await api.post(`/financeiro/comissoes/${ajusteRow.id}/ajustes`, {
        valor_advogado: valor,
        motivo: ajusteForm.motivo.trim(),
      });
      toast.success(
        valor > 0
          ? "Ajuste positivo registrado."
          : "Ajuste negativo registrado.",
      );
      setAjusteRow(null);
      setAjusteForm({ valor: "", motivo: "" });
      await load();
    } catch (e: unknown) {
      toast.error(apiErrorMessage(e, "Falha ao registrar ajuste."));
    } finally {
      setAjustando(false);
    }
  }

  async function abrirExtrato() {
    if (!competencia) {
      toast.error("Selecione uma competência para abrir o extrato mensal.");
      return;
    }
    setExtratoOpen(true);
    setExtratoLoading(true);
    try {
      const { data } = await api.get("/financeiro/comissoes/extrato-mensal", {
        params: { competencia },
      });
      setExtrato(data);
    } catch (e: unknown) {
      setExtratoOpen(false);
      toast.error(apiErrorMessage(e, "Falha ao carregar extrato."));
    } finally {
      setExtratoLoading(false);
    }
  }

  async function fecharMes() {
    if (!competencia) return;
    try {
      await api.post("/financeiro/comissoes/fechamentos", { competencia });
      toast.success(`Competência ${competencia} fechada em snapshot.`);
      await load();
    } catch (e: unknown) {
      toast.error(apiErrorMessage(e, "Falha ao fechar competência."));
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
      await load();
    } catch (e: unknown) {
      toast.error(apiErrorMessage(e, "Falha ao salvar regra."));
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
      await load();
    } catch (e: unknown) {
      toast.error(apiErrorMessage(e, "Falha ao alterar regra."));
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">
            Comissões
          </h2>
          <p className="mt-0.5 text-xs text-slate-500">
            Competência {competencia}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="btn-secondary"
            onClick={abrirExtrato}
          >
            <FileCheck2 className="h-4 w-4" />
            Extrato
          </button>
          <button
            type="button"
            className="btn-secondary"
            disabled={!competencia || !!fechamento?.id}
            onClick={fecharMes}
          >
            <Check className="h-4 w-4" />
            {fechamento?.id ? "Mês fechado" : "Fechar mês"}
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
      </div>

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
        {(
          [
            ["A aprovar", resumo.a_aprovar, UserRound],
            ["A pagar", resumo.a_pagar, Wallet],
            ["Pago no período", resumo.paga_periodo, Check],
            ["Previsto", previsao.total, SlidersHorizontal],
            ["Ajustes pendentes", resumo.ajustes_pendentes, AlertTriangle],
          ] as Array<[string, number | string | undefined, typeof UserRound]>
        ).map(([label, value, Icon]) => (
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

      {Number(previsao.indeterminadas || 0) > 0 && (
        <p className="px-1 text-xs text-slate-400">
          {previsao.indeterminadas} honorário(s) de êxito sem base monetária
          permanecem fora da previsão em reais.
        </p>
      )}

      {competencia && conferencia && conferencia.itens.length > 0 && (
        <section className="rounded-2xl border border-amber-200 bg-amber-50/60 p-4 dark:border-amber-900/50 dark:bg-amber-950/20">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-600" />
            <h3 className="text-sm font-semibold text-amber-900 dark:text-amber-200">
              Conferência antes do fechamento
            </h3>
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            {conferencia.itens.map((item) => (
              <div
                key={item.codigo}
                className="rounded-xl bg-white/70 px-3 py-2 text-xs dark:bg-white/[0.04]"
              >
                <strong>{item.titulo}</strong>
                <span className="ml-2 text-slate-500">
                  {item.qtd} item(ns)
                  {item.valor != null
                    ? ` · ${fmtMoney(Number(item.valor))}`
                    : ""}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {porAdvogado.length > 0 && (
        <section className="card overflow-hidden">
          <div className="border-b border-slate-100 px-4 py-3 dark:border-slate-800">
            <h3 className="font-semibold">Resumo por advogado</h3>
          </div>
          <div className="grid gap-2 p-3 md:grid-cols-2 xl:grid-cols-3">
            {porAdvogado.map((item) => (
              <div
                key={item.advogado_id}
                className="rounded-xl border border-slate-100 p-3 dark:border-slate-800"
              >
                <div className="flex items-center justify-between gap-2">
                  <strong className="truncate text-sm">{item.advogado}</strong>
                  <ExtratoSocio
                    userId={item.advogado_id ?? ""}
                    nome={item.advogado ?? "Advogado"}
                  />
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-slate-500">
                  <span>Recebido: {fmtMoney(Number(item.recebido || 0))}</span>
                  <span>
                    Comissão: {fmtMoney(Number(item.comissao_gerada || 0))}
                  </span>
                  <span>Pago: {fmtMoney(Number(item.comissao_paga || 0))}</span>
                  <span>Saldo: {fmtMoney(Number(item.saldo || 0))}</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

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
          onChange={(e) => setStatus(e.target.value as "" | CommissionStatus)}
        >
          <option value="">Todos os status</option>
          <option value="calculada">Calculada</option>
          <option value="a_aprovar">A aprovar</option>
          <option value="a_pagar">A pagar</option>
          <option value="paga">Paga</option>
          <option value="estornada">Estornada</option>
          <option value="rejeitada">Rejeitada</option>
        </select>
        {payableIds.length > 0 && (
          <button
            type="button"
            className="btn-ghost text-xs"
            onClick={selectAllPayable}
          >
            {selected.size === payableIds.length
              ? "Limpar seleção"
              : "Selecionar a pagar"}
          </button>
        )}
        {selected.size > 0 && (
          <button
            type="button"
            className="btn-primary"
            onClick={() => setPagamentoOpen(true)}
          >
            Pagar {selected.size} selecionada(s)
          </button>
        )}
      </div>

      {loading ? (
        <Spinner />
      ) : visiveis.length === 0 ? (
        <div className="card p-8 text-center text-sm text-slate-400">
          Nenhuma comissão encontrada.
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[1120px] text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-400 dark:bg-white/[0.04]">
              <tr>
                <th className="w-10 px-3 py-3" />
                <th className="px-4 py-3 text-left">Advogado</th>
                <th className="px-4 py-3 text-left">Cliente / caso</th>
                <th className="px-4 py-3 text-right">Recebido</th>
                <th className="px-4 py-3 text-right">Base líquida</th>
                <th className="px-4 py-3 text-right">Comissão</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {visiveis.map((row) => (
                <tr
                  id={`finance-commission-${row.id}`}
                  key={row.id}
                  className={
                    focusId === row.id || focusId === row.withdrawal_id
                      ? "ring-2 ring-inset ring-primary-400 bg-primary-50/50 dark:bg-primary-400/10"
                      : ""
                  }
                >
                  <td className="px-3 py-3 text-center">
                    {row.status === "a_pagar" && row.withdrawal_id && (
                      <input
                        type="checkbox"
                        checked={selected.has(row.withdrawal_id)}
                        onChange={() =>
                          toggleSelected(row.withdrawal_id as string)
                        }
                        aria-label="Selecionar comissão para pagamento"
                      />
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-800 dark:text-slate-100">
                      {row.advogado || "Sem responsável"}
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1 text-[11px] text-slate-400">
                      <span>{row.regra_nome || "Regra histórica"}</span>
                      {row.regra_escopo === "caso" && (
                        <span className="rounded bg-blue-50 px-1.5 py-0.5 text-blue-700 dark:bg-blue-400/10 dark:text-blue-300">
                          Regra do caso
                        </span>
                      )}
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
                  <td className="px-4 py-3 text-right">
                    <div>{fmtMoney(Number(row.base_liquida || 0))}</div>
                    {Number(row.despesas_deduzidas || 0) > 0 && (
                      <div className="text-[11px] text-slate-400">
                        despesas {fmtMoney(Number(row.despesas_deduzidas))}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right font-semibold">
                    <div>
                      {fmtMoney(Number(row.valor_advogado_efetivo || 0))}
                    </div>
                    {Number(row.ajustes_advogado || 0) !== 0 && (
                      <div
                        className={`text-[11px] ${
                          Number(row.ajustes_advogado) < 0
                            ? "text-rose-500"
                            : "text-emerald-600"
                        }`}
                      >
                        ajuste {fmtMoney(Number(row.ajustes_advogado))}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-1 text-xs font-medium ${
                        STATUS_CLASS[row.status] || STATUS_CLASS.calculada
                      }`}
                    >
                      {STATUS_LABEL[row.status] || row.status}
                    </span>
                    {row.status === "paga" && row.payment_method && (
                      <div className="mt-1 text-[11px] text-slate-400">
                        {row.payment_method}
                        {row.payment_reference
                          ? ` · ${row.payment_reference}`
                          : ""}
                        {row.comprovante_doc_id ? " · comprovante" : ""}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap items-center justify-end gap-1">
                      {row.advogado_id && (
                        <ExtratoSocio
                          userId={row.advogado_id}
                          nome={row.advogado || "Advogado"}
                        />
                      )}
                      <button
                        type="button"
                        className="btn-ghost px-2 py-1 text-xs"
                        onClick={() => {
                          setAjusteRow(row);
                          setAjusteForm({ valor: "", motivo: "" });
                        }}
                      >
                        Ajustar
                      </button>
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
                          onClick={() => openSinglePayment(row)}
                        >
                          Pagar
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="px-1 text-[11px] text-slate-400">
        Realizado e previsão permanecem separados. Estornos e correções geram
        ajustes auditáveis; o valor original nunca é reescrito.
      </p>

      <Modal
        open={pagamentoOpen}
        onClose={() => setPagamentoOpen(false)}
        title="Pagar comissões"
      >
        <div className="space-y-4">
          <div className="rounded-xl bg-slate-50 p-3 text-sm dark:bg-white/[0.04]">
            {selected.size} comissão(ões) selecionada(s). Ajustes pendentes do
            mesmo advogado serão compensados automaticamente no lote.
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Forma</label>
              <select
                className="input"
                value={paymentForm.method}
                onChange={(e) =>
                  setPaymentForm({ ...paymentForm, method: e.target.value })
                }
              >
                <option value="pix">PIX</option>
                <option value="transferencia">Transferência</option>
                <option value="ted">TED</option>
                <option value="dinheiro">Dinheiro</option>
                <option value="outro">Outro</option>
              </select>
            </div>
            <div>
              <label className="label">Data</label>
              <input
                type="date"
                className="input"
                value={paymentForm.date}
                onChange={(e) =>
                  setPaymentForm({ ...paymentForm, date: e.target.value })
                }
              />
            </div>
          </div>
          <div>
            <label className="label">Referência / ID da transferência</label>
            <input
              className="input"
              value={paymentForm.reference}
              onChange={(e) =>
                setPaymentForm({ ...paymentForm, reference: e.target.value })
              }
            />
          </div>
          <div>
            <label className="label">Comprovante</label>
            <label className="input flex cursor-pointer items-center gap-2">
              <Upload className="h-4 w-4 text-slate-400" />
              <span className="truncate text-sm">
                {proofFile?.name || "Selecionar arquivo"}
              </span>
              <input
                type="file"
                className="hidden"
                onChange={(e) => setProofFile(e.target.files?.[0] || null)}
              />
            </label>
          </div>
          <div>
            <label className="label">Observação</label>
            <textarea
              className="input min-h-20"
              value={paymentForm.observacao}
              onChange={(e) =>
                setPaymentForm({ ...paymentForm, observacao: e.target.value })
              }
            />
          </div>
          <button
            type="button"
            className="btn-primary w-full justify-center"
            disabled={pagando}
            onClick={pagarSelecionadas}
          >
            {pagando ? "Registrando..." : "Confirmar pagamento"}
          </button>
        </div>
      </Modal>

      <Modal
        open={!!ajusteRow}
        onClose={() => setAjusteRow(null)}
        title="Ajustar comissão"
      >
        <div className="space-y-4">
          <p className="text-sm text-slate-500">
            Use valor positivo para acrescentar e negativo para reduzir. O
            lançamento original será preservado.
          </p>
          <div>
            <label className="label">Valor do ajuste (R$)</label>
            <input
              className="input"
              type="number"
              step="0.01"
              value={ajusteForm.valor}
              onChange={(e) =>
                setAjusteForm({ ...ajusteForm, valor: e.target.value })
              }
              placeholder="-100,00 ou 100,00"
            />
          </div>
          <div>
            <label className="label">Motivo *</label>
            <textarea
              className="input min-h-24"
              value={ajusteForm.motivo}
              onChange={(e) =>
                setAjusteForm({ ...ajusteForm, motivo: e.target.value })
              }
            />
          </div>
          <button
            type="button"
            className="btn-primary w-full justify-center"
            disabled={ajustando}
            onClick={salvarAjuste}
          >
            {ajustando ? "Salvando..." : "Registrar ajuste"}
          </button>
        </div>
      </Modal>

      <Modal
        open={extratoOpen}
        onClose={() => setExtratoOpen(false)}
        title={
          competencia ? `Extrato de comissões · ${competencia}` : "Extrato"
        }
        wide
      >
        {extratoLoading ? (
          <div className="flex justify-center py-10">
            <Spinner />
          </div>
        ) : extrato ? (
          <div className="space-y-4">
            {extrato.fechamento?.id && (
              <div className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-800 dark:bg-emerald-400/10 dark:text-emerald-300">
                Competência fechada em {fmtDate(extrato.fechamento.closed_at)}.
                O snapshot histórico permanece preservado.
              </div>
            )}
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {[
                ["Recebido", extrato.resumo?.recebido],
                ["Comissões", extrato.resumo?.comissoes],
                ["Pago", extrato.resumo?.pago],
                ["Saldo de ajustes", extrato.resumo?.ajustes_pendentes],
              ].map(([label, value]) => (
                <div
                  key={String(label)}
                  className="rounded-xl border border-slate-100 p-3 dark:border-slate-800"
                >
                  <p className="text-xs text-slate-400">{label}</p>
                  <p className="mt-1 font-semibold">
                    {fmtMoney(Number(value || 0))}
                  </p>
                </div>
              ))}
            </div>
            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {(extrato.por_advogado ?? []).map((item) => (
                <div
                  key={item.advogado_id || item.advogado}
                  className="grid grid-cols-2 gap-2 py-3 text-sm md:grid-cols-5"
                >
                  <strong>{item.advogado}</strong>
                  <span>Recebido {fmtMoney(Number(item.recebido || 0))}</span>
                  <span>Comissão {fmtMoney(Number(item.comissoes || 0))}</span>
                  <span>Pago {fmtMoney(Number(item.pago || 0))}</span>
                  <span>Saldo {fmtMoney(Number(item.saldo || 0))}</span>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </Modal>

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
