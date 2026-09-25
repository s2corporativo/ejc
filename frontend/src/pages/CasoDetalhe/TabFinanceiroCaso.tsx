import { useEffect, useState } from "react";
import api from "../../lib/api";
import type { Case, Fee } from "../../types";
import { toast } from "../../components/Toast";
import { Empty, Spinner, fmtMoney } from "../../components/UI";
import { useAuth } from "../../stores/auth";

interface ResumoFinanceiro {
  classificacao_financeira: "normal" | "pro_bono" | "causa_propria";
  valor_pleiteado?: number | null;
  valor_recebido: number;
  credito_advogado: number;
  parcela_escritorio: number;
  pendente_sucumbencia: boolean;
  pendente_exito: boolean;
  regra_rateio: string;
  advogado_responsavel_id?: string | null;
  advogado_responsavel_nome?: string | null;
  rateio_pendente_quantidade?: number;
  rateio_pendente_valor?: number;
  rateio_pendente_sem_responsavel?: boolean;
}

export default function TabFinanceiroCaso({ caso }: { caso: Case }) {
  const user = useAuth((state) => state.user);
  const podeReconciliar = new Set(["superadmin", "admin", "socio", "advogado"]).has(
    user?.role || "",
  );
  const [resumo, setResumo] = useState<ResumoFinanceiro | null>(null);
  const [fees, setFees] = useState<Fee[]>([]);
  const [loading, setLoading] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [recebendo, setRecebendo] = useState(false);
  const [reconciliando, setReconciliando] = useState(false);
  const [valorRecebido, setValorRecebido] = useState("");
  const [form, setForm] = useState({
    classificacao_financeira: caso.classificacao_financeira ?? "normal",
    valor_pleiteado: caso.valor_pleiteado?.toString() ?? "",
    pendente_sucumbencia: !!caso.pendente_sucumbencia,
    pendente_exito: !!caso.pendente_exito,
  });

  const carregar = async () => {
    setLoading(true);
    try {
      const [r, f] = await Promise.all([
        api.get(`/cases/${caso.id}/financeiro/resumo`),
        api.get("/fees/", { params: { case_id: caso.id, page_size: 100 } }),
      ]);
      setResumo(r.data);
      setForm({
        classificacao_financeira: r.data.classificacao_financeira ?? "normal",
        valor_pleiteado:
          r.data.valor_pleiteado == null ? "" : String(r.data.valor_pleiteado),
        pendente_sucumbencia: !!r.data.pendente_sucumbencia,
        pendente_exito: !!r.data.pendente_exito,
      });
      setFees(Array.isArray(f.data?.data) ? f.data.data : []);
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao carregar o financeiro do caso");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void carregar();
  }, [caso.id]);

  const salvar = async () => {
    setSalvando(true);
    try {
      await api.patch(`/cases/${caso.id}`, {
        classificacao_financeira: form.classificacao_financeira,
        valor_pleiteado:
          form.valor_pleiteado === "" ? null : Number(form.valor_pleiteado),
        pendente_sucumbencia: form.pendente_sucumbencia,
        pendente_exito: form.pendente_exito,
      });
      toast.success("Dados econômicos do caso atualizados.");
      await carregar();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao salvar dados econômicos");
    } finally {
      setSalvando(false);
    }
  };

  const registrar = async () => {
    const valor = Number(valorRecebido);
    if (!Number.isFinite(valor) || valor <= 0) {
      toast.error("Informe um valor recebido maior que zero.");
      return;
    }
    setRecebendo(true);
    try {
      const { data } = await api.post(
        `/cases/${caso.id}/financeiro/recebimentos`,
        { valor },
      );
      setValorRecebido("");
      toast.success(
        data?.rateio?.rateio_pendente
          ? "Recebimento registrado; rateio pendente até definir o responsável."
          : data?.rateio?.regra === "institucional_integral_escritorio"
            ? "Recebimento lançado: 100% para o escritório."
            : "Recebimento lançado: 50% responsável / 50% escritório.",
      );
      await carregar();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao registrar recebimento");
    } finally {
      setRecebendo(false);
    }
  };


  const reconciliarRateios = async () => {
    if (!podeReconciliar || (resumo?.rateio_pendente_quantidade ?? 0) === 0) return;
    setReconciliando(true);
    try {
      const { data } = await api.post(
        `/cases/${caso.id}/financeiro/reconciliar-rateios`,
        { confirmar: true },
      );
      const total = Number(data?.reconciliacao?.valor_total || 0);
      toast.success(
        `${data?.reconciliacao?.reconciliados || 0} rateio(s) reconciliado(s) · ${fmtMoney(total)}.`,
      );
      await carregar();
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Falha ao reconciliar os rateios pendentes",
      );
    } finally {
      setReconciliando(false);
    }
  };

  if (loading && !resumo) return <Spinner />;

  return (
    <div className="space-y-5">
      <div className="card p-5">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Classificação e resultado econômico
        </h3>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <label className="label">Classificação</label>
            <select
              className="input w-full"
              value={form.classificacao_financeira}
              onChange={(e) =>
                setForm({ ...form, classificacao_financeira: e.target.value as any })
              }
            >
              <option value="normal">Normal</option>
              <option value="pro_bono">Pro bono</option>
              <option value="causa_propria">Causa própria</option>
            </select>
          </div>
          <div>
            <label className="label">Valor pleiteado (R$)</label>
            <input
              type="number"
              min="0"
              step="0.01"
              className="input w-full"
              value={form.valor_pleiteado}
              onChange={(e) => setForm({ ...form, valor_pleiteado: e.target.value })}
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={form.pendente_sucumbencia}
              onChange={(e) =>
                setForm({ ...form, pendente_sucumbencia: e.target.checked })
              }
            />
            Ainda falta receber sucumbência
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={form.pendente_exito}
              onChange={(e) => setForm({ ...form, pendente_exito: e.target.checked })}
            />
            Ainda falta receber honorário de êxito
          </label>
        </div>
        <button
          onClick={salvar}
          disabled={salvando}
          className="btn-primary mt-4"
        >
          {salvando ? "Salvando..." : "Salvar dados do caso"}
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <div className="card p-4">
          <p className="text-xs uppercase text-slate-400">Recebido</p>
          <p className="mt-1 text-xl font-semibold">{fmtMoney(resumo?.valor_recebido)}</p>
        </div>
        <div className="card p-4">
          <p className="text-xs uppercase text-slate-400">Crédito do responsável</p>
          <p className="mt-1 text-xl font-semibold">{fmtMoney(resumo?.credito_advogado)}</p>
        </div>
        <div className="card p-4">
          <p className="text-xs uppercase text-slate-400">Parcela do escritório</p>
          <p className="mt-1 text-xl font-semibold">{fmtMoney(resumo?.parcela_escritorio)}</p>
        </div>
      </div>

      {(resumo?.rateio_pendente_sem_responsavel ||
        (resumo?.rateio_pendente_quantidade ?? 0) > 0) && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <p className="font-semibold">Reconciliação financeira pendente</p>
          <p className="mt-1">
            Responsável jurídico: {resumo?.advogado_responsavel_nome || "não definido"}.
            {(resumo?.rateio_pendente_quantidade ?? 0) > 0
              ? ` ${resumo?.rateio_pendente_quantidade} recebimento(s), total de ${fmtMoney(resumo?.rateio_pendente_valor)}, ainda aguardam rateio.`
              : ""}
          </p>
          {resumo?.rateio_pendente_sem_responsavel && (
            <p className="mt-1 font-medium">
              O recebimento pode ser registrado, mas o rateio 50/50 ficará pendente até a definição do advogado responsável.
            </p>
          )}
          {podeReconciliar &&
            (resumo?.rateio_pendente_quantidade ?? 0) > 0 &&
            !resumo?.rateio_pendente_sem_responsavel && (
              <button
                type="button"
                className="btn-secondary mt-3"
                disabled={reconciliando}
                onClick={reconciliarRateios}
              >
                {reconciliando ? "Reconciliando..." : "Reconciliar rateios pendentes"}
              </button>
            )}
        </div>
      )}

      <div className="card p-5">
        <h3 className="font-semibold">Registrar valor recebido</h3>
        <p className="mt-1 text-xs text-slate-500">
          Registre aqui receita de honorários efetivamente recebida pelo escritório,
          não valores pertencentes ao cliente. {resumo?.regra_rateio === "institucional_integral_escritorio" ? "Carteira institucional: 100% escritório." : "Rateio: 50% responsável / 50% escritório."}
        </p>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <input
            type="number"
            min="0.01"
            step="0.01"
            className="input flex-1"
            placeholder="Valor recebido (R$)"
            value={valorRecebido}
            onChange={(e) => setValorRecebido(e.target.value)}
          />
          <button
            className="btn-primary"
            disabled={recebendo}
            onClick={registrar}
          >
            {recebendo ? "Lançando..." : "Lançar no financeiro"}
          </button>
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="border-b border-slate-100 px-4 py-3">
          <h3 className="font-semibold">Lançamentos financeiros do caso</h3>
        </div>
        {fees.length === 0 ? (
          <div className="p-5"><Empty message="Nenhum lançamento financeiro" /></div>
        ) : (
          <div className="divide-y divide-slate-100">
            {fees.map((f) => (
              <div key={f.id} className="flex items-center justify-between px-4 py-3 text-sm">
                <div>
                  <p className="font-medium text-slate-800">{f.descricao}</p>
                  <p className="text-xs capitalize text-slate-400">
                    {f.tipo.replace(/_/g, " ")} · {f.status}
                  </p>
                </div>
                <span className="font-semibold">{fmtMoney(f.valor)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
