import { useState, useEffect, useCallback } from "react";
import { RefreshCw, Check, AlertCircle, Calendar, Repeat } from "lucide-react";
import api from "../lib/api";

interface Despesa {
  id: string;
  categoria: string;
  descricao: string;
  valor: number;
  recorrencia: string;
  competencia?: string;
  status: string;
}

const CAT_LABEL: Record<string, string> = {
  infraestrutura: "Infraestrutura",
  tecnologia: "Tecnologia",
  pessoal: "Pessoal / Pró-labore",
  oab: "OAB / Anuidade",
  marketing: "Marketing",
  operacao: "Operação",
  fiscal: "Fiscal / Contab.",
  investimento: "Investimento",
  outro: "Outros",
};

function fmtR$(v: number) {
  return (v ?? 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}

export default function DespesasRecorrentes() {
  const [recorrentes, setRecorrentes] = useState<Despesa[]>([]);
  const [loading, setLoading] = useState(true);
  const [gerando, setGerando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [targetComp, setTargetComp] = useState(() => {
    const now = new Date();
    const next = new Date(now.getFullYear(), now.getMonth() + 1, 1);
    return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}`;
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/v1/despesas", {
        params: { recorrente: true },
      });
      setRecorrentes(
        (res.data ?? []).filter(
          (d: Despesa & { recorrente: boolean }) => d.recorrente,
        ),
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function gerarProximoMes() {
    setGerando(true);
    setMsg(null);
    try {
      let count = 0;
      for (const d of recorrentes) {
        await api.post("/v1/despesas", {
          categoria: d.categoria,
          descricao: d.descricao,
          valor: d.valor,
          tipo: "fixo",
          recorrente: true,
          recorrencia: d.recorrencia,
          status: "pendente",
          competencia: targetComp,
        });
        count++;
      }
      setMsg(
        `${count} despesas geradas para ${targetComp.split("-").reverse().join("/")}`,
      );
    } catch (e: any) {
      setMsg(`Erro: ${e.response?.data?.detail ?? "Falha ao gerar despesas"}`);
    } finally {
      setGerando(false);
    }
  }

  const total = recorrentes.reduce((s, d) => s + d.valor, 0);

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-5">
      <div>
        <div className="eyebrow mb-2">Financeiro</div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-950">
          Despesas Recorrentes
        </h1>
        <p className="text-slate-500 text-sm mt-1">
          Geração automática de lançamentos mensais
        </p>
      </div>

      {/* Action card */}
      <div className="bg-white rounded-xl border border-slate-200 p-5">
        <h2 className="font-semibold text-slate-800 mb-3 flex items-center gap-2">
          <Repeat className="w-4 h-4 text-blue-500" />
          Gerar lançamentos para novo mês
        </h2>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 border border-slate-200 rounded-lg px-3 py-2">
            <Calendar className="w-4 h-4 text-slate-400" />
            <input
              type="month"
              className="text-sm text-slate-700 outline-none bg-transparent"
              value={targetComp}
              onChange={(e) => setTargetComp(e.target.value)}
            />
          </div>
          <button
            onClick={gerarProximoMes}
            disabled={gerando || recorrentes.length === 0}
            className="flex items-center gap-2 px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
          >
            {gerando ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Check className="w-4 h-4" />
            )}
            Gerar {recorrentes.length} lançamentos
          </button>
        </div>
        {msg && (
          <div
            className={`mt-3 flex items-center gap-2 text-sm px-3 py-2 rounded-lg ${
              msg.startsWith("Erro")
                ? "bg-red-50 text-red-700"
                : "bg-emerald-50 text-emerald-700"
            }`}
          >
            {msg.startsWith("Erro") ? (
              <AlertCircle className="w-4 h-4" />
            ) : (
              <Check className="w-4 h-4" />
            )}
            {msg}
          </div>
        )}
      </div>

      {/* Summary */}
      <div className="bg-slate-50 rounded-xl border border-slate-200 p-4 flex items-center justify-between">
        <span className="text-sm text-slate-600">
          {recorrentes.length} despesas recorrentes cadastradas
        </span>
        <span className="font-semibold text-slate-800">
          Total mensal: {fmtR$(total)}
        </span>
      </div>

      {/* List */}
      {loading ? (
        <div className="text-center py-10 text-slate-400">Carregando...</div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3 text-left">Categoria</th>
                <th className="px-4 py-3 text-left">Descrição</th>
                <th className="px-4 py-3 text-left">Recorrência</th>
                <th className="px-4 py-3 text-right">Valor</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {recorrentes.map((d) => (
                <tr key={d.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 text-slate-500">
                    {CAT_LABEL[d.categoria] ?? d.categoria}
                  </td>
                  <td className="px-4 py-3 text-slate-800 font-medium">
                    {d.descricao}
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full capitalize">
                      {d.recorrencia}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right font-semibold text-slate-800">
                    {fmtR$(d.valor)}
                  </td>
                </tr>
              ))}
              {recorrentes.length === 0 && (
                <tr>
                  <td
                    colSpan={4}
                    className="px-4 py-10 text-center text-slate-400"
                  >
                    Nenhuma despesa recorrente cadastrada. Crie despesas com a
                    opção "Recorrente" em Despesas.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
