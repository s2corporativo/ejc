import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronRight, Scale, Search } from "lucide-react";
import api from "../../lib/api";
import { EmptyState, ErrorState, Spinner, fmtDate } from "../../components/UI";
import { CASE_STATUS_LABEL, isCasoAtivo } from "../../types/caseStatus";

/** Cor por status; o RÓTULO vem do vocabulário canônico (types/caseStatus.ts),
 * para o portal do cliente não divergir da área interna. */
const STATUS_COR: Record<string, string> = {
  aberto: "bg-warn-100 text-warn-700",
  em_instrucao: "bg-primary-100 text-primary-700",
  em_producao: "bg-primary-100 text-primary-700",
  protocolado: "bg-primary-100 text-primary-700",
  encerrado: "bg-success-100 text-success-700",
  arquivado: "bg-slate-100 text-slate-500",
};

const AREA_ICON: Record<string, string> = {
  civel: "⚖️",
  trabalhista: "🦺",
  criminal: "🔒",
  tributario: "📋",
  empresarial: "🏢",
  ambiental: "🌿",
  previdenciario: "🛡️",
};

export default function PortalCasos() {
  const [casos, setCasos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [busca, setBusca] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    setError(false);
    api
      .get("/portal/meus-casos")
      .then((r) =>
        setCasos(
          Array.isArray(r.data)
            ? r.data
            : Array.isArray(r.data?.data)
              ? r.data.data
              : [],
        ),
      )
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = casos.filter(
    (c) =>
      !busca ||
      c.titulo?.toLowerCase().includes(busca.toLowerCase()) ||
      c.numero_processo?.toLowerCase().includes(busca.toLowerCase()) ||
      c.numero_interno?.toLowerCase().includes(busca.toLowerCase()),
  );

  const ativos = casos.filter((c) => isCasoAtivo(c.status)).length;
  const encerrados = casos.filter(
    (c) => c.status === "encerrado" || c.status === "arquivado",
  ).length;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-800">Meus processos</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          {casos.length} total · {ativos} em andamento · {encerrados} encerrados
        </p>
      </div>

      {/* Search */}
      {casos.length > 3 && (
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            className="input pl-9 pr-4 py-2.5"
            placeholder="Buscar processo..."
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </div>
      )}

      {/* Lista */}
      {loading ? (
        <Spinner />
      ) : error ? (
        <ErrorState
          message="Não foi possível carregar seus processos."
          onRetry={load}
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={Scale}
          title={
            busca ? "Nenhum processo encontrado" : "Nenhum processo no momento"
          }
          message={
            busca
              ? "Tente buscar por outro termo, número do processo ou título."
              : "Quando o escritório cadastrar um processo para você, ele aparecerá aqui automaticamente."
          }
        />
      ) : (
        <div className="space-y-2">
          {filtered.map((c) => {
            const label =
              CASE_STATUS_LABEL[
                c.status as keyof typeof CASE_STATUS_LABEL
              ] ?? c.status;
            const cor = STATUS_COR[c.status] ?? "bg-slate-100 text-slate-600";
            const areaEmoji = AREA_ICON[c.area?.toLowerCase()] ?? "📁";
            return (
              <Link
                key={c.id}
                to={`/portal/casos/${c.id}`}
                className="card p-4 flex items-center justify-between gap-4 hover:border-primary-200 transition-all block"
              >
                <div className="flex items-start gap-3 min-w-0">
                  <div className="w-10 h-10 bg-slate-50 rounded-xl flex items-center justify-center flex-shrink-0 text-lg">
                    {areaEmoji}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-800 truncate">
                      {c.titulo}
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      {[c.numero_processo || c.numero_interno, c.comarca]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                    <span
                      className={`inline-block mt-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium ${cor}`}
                    >
                      {label}
                    </span>
                    {c.created_at && (
                      <span className="ml-2 text-[10px] text-slate-400">
                        No escritório desde {fmtDate(c.created_at)}
                      </span>
                    )}
                  </div>
                </div>
                <ChevronRight className="w-5 h-5 text-slate-300 flex-shrink-0" />
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
