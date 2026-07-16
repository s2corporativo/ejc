import { useEffect, useState } from "react";
import api from "../lib/api";
import { PageHeader, Empty, Spinner, ErrorState } from "../components/UI";

export default function Auditoria() {
  const [data, setData] = useState<any>(null);
  const [erro, setErro] = useState(false);
  const [acao, setAcao] = useState("");
  const [modulo, setModulo] = useState("");

  const load = () => {
    setErro(false);
    return api
      .get("/audit/", {
        params: {
          acao: acao || undefined,
          entidade: modulo || undefined,
          page_size: 100,
        },
      })
      .then((r) => setData(r.data))
      .catch(() => setErro(true));
  };
  useEffect(() => {
    load();
  }, [acao, modulo]);

  return (
    <div>
      <PageHeader title="Auditoria" subtitle="Logs imutáveis — LGPD art. 37" />

      <div className="flex flex-wrap gap-3 mb-4">
        <select
          className="input w-48"
          value={acao}
          onChange={(e) => setAcao(e.target.value)}
        >
          <option value="">Todas as ações</option>
          {[
            "LOGIN",
            "LOGIN_FALHA",
            "CREATE",
            "UPDATE",
            "DELETE",
            "DOWNLOAD",
            "UPLOAD",
            "AI_USE",
            "CONFLITO_CHECK",
            "PRAZO_ALTERADO",
            "CIENCIA_PRAZO",
            "REVISAO_HITL",
            "PAGAMENTO",
          ].map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
        <select
          className="input w-48"
          value={modulo}
          onChange={(e) => setModulo(e.target.value)}
        >
          <option value="">Todos os módulos</option>
          {[
            "users",
            "clients",
            "cases",
            "deadlines",
            "documents",
            "legal_docs",
            "fees",
            "environmental_cases",
            "procuracoes",
          ].map((e2) => (
            <option key={e2} value={e2}>
              {e2}
            </option>
          ))}
        </select>
      </div>

      {erro ? (
        <ErrorState
          message="Não foi possível carregar os logs de auditoria. Tente novamente."
          onRetry={load}
        />
      ) : !data ? (
        <Spinner />
      ) : (!Array.isArray(data.data) || data.data.length === 0) ? (
        <Empty message="Nenhum log com esses filtros" />
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">Quando</th>
                <th className="px-4 py-3">Ação</th>
                <th className="px-4 py-3">Módulo</th>
                <th className="px-4 py-3">Usuário</th>
                <th className="px-4 py-3">IP</th>
                <th className="px-4 py-3">Detalhes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(Array.isArray(data.data) ? data.data : []).map((l: any) => (
                <tr key={l.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2.5 text-xs text-slate-500">
                    {new Date(l.created_at).toLocaleString("pt-BR")}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className="badge bg-navy-100 text-navy">
                      {l.acao}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-xs">{l.entidade || "—"}</td>
                  <td className="px-4 py-2.5 text-xs">
                    {l.user_nome || l.user_id || "—"}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-slate-400">
                    {l.ip || "—"}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-slate-500 max-w-[280px] truncate">
                    {l.detalhes || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
