import { useState, useEffect, useCallback } from "react";
import { AlertTriangle, Calendar, Repeat } from "lucide-react";
import api from "../lib/api";
import { Spinner, ErrorState } from "../components/UI";

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
  const [error, setError] = useState(false);
  const [targetComp, setTargetComp] = useState(() => {
    const now = new Date();
    const next = new Date(now.getFullYear(), now.getMonth() + 1, 1);
    return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}`;
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const res = await api.get("/despesas", {
        params: { recorrente: true },
      });
      setRecorrentes(
        (res.data ?? []).filter(
          (d: Despesa & { recorrente: boolean }) => d.recorrente,
        ),
      );
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const total = recorrentes.reduce((s, d) => s + d.valor, 0);

  return (
    <div className="space-y-5">
      {/*
        Fail-closed temporário: a implementação histórica gerava N POSTs no
        browser e copiava `recorrente: true` para os novos lançamentos. Sem
        template_id/run idempotente no banco, um duplo clique/reexecução podia
        duplicar o mês e os próprios lançamentos passavam a funcionar como
        novos "templates". A geração fica indisponível até o schema financeiro
        idempotente previsto na Issue #969 entrar em migration linear.
      */}
      <div className="card p-5">
        <h2 className="font-semibold text-slate-800 mb-3 flex items-center gap-2">
          <Repeat className="w-4 h-4 text-primary-500" />
          Gerar lançamentos para novo mês
        </h2>
        <div className="flex flex-wrap items-center gap-4">
          <div className="input flex w-auto items-center gap-2">
            <Calendar className="w-4 h-4 text-slate-400" />
            <input
              type="month"
              className="text-sm text-slate-700 outline-none bg-transparent"
              value={targetComp}
              onChange={(e) => setTargetComp(e.target.value)}
            />
          </div>
          <button
            type="button"
            disabled
            title="Aguardando geração idempotente no backend"
            className="btn-primary opacity-50 cursor-not-allowed"
          >
            Gerar {recorrentes.length} lançamentos
          </button>
        </div>
        <div className="mt-3 flex items-start gap-2 rounded-lg bg-warn-50 px-3 py-2 text-sm text-warn-800">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            Geração automática temporariamente bloqueada para evitar lançamentos
            duplicados. Os cadastros recorrentes continuam visíveis; a geração
            será reativada quando o backend tiver template separado e chave
            idempotente por competência.
          </span>
        </div>
      </div>

      <div className="rounded-xl bg-slate-900/[0.04] p-4 flex items-center justify-between dark:bg-white/[0.06]">
        <span className="text-sm text-slate-600">
          {recorrentes.length} despesas recorrentes cadastradas
        </span>
        <span className="font-semibold text-slate-800">
          Total mensal: {fmtR$(total)}
        </span>
      </div>

      {loading ? (
        <Spinner />
      ) : error ? (
        <ErrorState
          message="Não foi possível carregar as despesas recorrentes. Tente novamente."
          onRetry={load}
        />
      ) : (
        <div className="card overflow-hidden">
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
                    <span className="text-xs bg-primary-50 text-primary-600 px-2 py-0.5 rounded-full capitalize">
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
