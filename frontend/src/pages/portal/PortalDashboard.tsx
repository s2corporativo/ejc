import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Scale,
  FileText,
  DollarSign,
  Bell,
  ChevronRight,
  CheckCircle,
  AlertCircle,
} from "lucide-react";
import api from "../../lib/api";
import { useAuth } from "../../stores/auth";
import { asList } from "../../lib/list";

const STATUS: Record<string, [string, string]> = {
  triagem: ["Em análise", "bg-warn-100 text-warn-700"],
  ativo: ["Em andamento", "bg-primary-100 text-primary-700"],
  suspenso: ["Suspenso", "bg-slate-100 text-slate-600"],
  encerrado: ["Encerrado", "bg-success-100 text-success-700"],
  arquivado: ["Arquivado", "bg-slate-100 text-slate-500"],
};

const fmtR$ = (v: number) =>
  v?.toLocaleString("pt-BR", { style: "currency", currency: "BRL" }) ??
  "R$ 0,00";

export default function PortalDashboard() {
  const { user } = useAuth();
  const [casos, setCasos] = useState<any[]>([]);
  const [financeiro, setFinanceiro] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.allSettled([
      api.get("/portal/meus-casos"),
      api.get("/portal/financeiro"),
    ])
      .then(([c, f]) => {
        if (c.status === "fulfilled") setCasos(asList(c.value.data));
        if (f.status === "fulfilled") setFinanceiro(f.value.data);
      })
      .finally(() => setLoading(false));
  }, []);

  const ativos = casos.filter((c) => c.status === "ativo").length;
  const pendente = financeiro?.total_pendente ?? 0;
  const honPago = financeiro?.total_pago ?? 0;

  return (
    <div className="space-y-6">
      {/* Welcome */}
      <div className="card p-6">
        <h1 className="text-xl font-bold text-slate-800">
          Olá, {user?.full_name?.split(" ")[0] ?? "cliente"}
        </h1>
        <p className="text-slate-500 text-sm mt-1">
          Acompanhe seus processos e documentos em um só lugar.
        </p>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <div className="card p-4 flex items-center gap-3">
          <div className="p-2.5 bg-primary-50 rounded-lg">
            <Scale className="w-5 h-5 text-primary-600" />
          </div>
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wide">
              Casos ativos
            </p>
            <p className="text-2xl font-bold text-slate-800">
              {loading ? "…" : ativos}
            </p>
          </div>
        </div>
        <div className="card p-4 flex items-center gap-3">
          <div className="p-2.5 bg-warn-50 rounded-lg">
            <DollarSign className="w-5 h-5 text-warn-600" />
          </div>
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wide">
              A pagar
            </p>
            <p className="text-2xl font-bold text-slate-800">
              {loading ? "…" : fmtR$(pendente)}
            </p>
          </div>
        </div>
        <div className="card p-4 flex items-center gap-3">
          <div className="p-2.5 bg-success-50 rounded-lg">
            <CheckCircle className="w-5 h-5 text-success-600" />
          </div>
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wide">
              Pago
            </p>
            <p className="text-2xl font-bold text-slate-800">
              {loading ? "…" : fmtR$(honPago)}
            </p>
          </div>
        </div>
      </div>

      {/* Quick links */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          {
            to: "/portal/casos",
            label: "Casos",
            icon: Scale,
            color: "text-primary-600 bg-primary-50",
          },
          {
            to: "/portal/documentos",
            label: "Documentos",
            icon: FileText,
            color: "text-ai-600 bg-ai-50",
          },
          {
            to: "/portal/financeiro",
            label: "Financeiro",
            icon: DollarSign,
            color: "text-success-600 bg-success-50",
          },
          {
            to: "/portal/mensagens",
            label: "Mensagens",
            icon: Bell,
            color: "text-warn-600 bg-warn-50",
          },
        ].map(({ to, label, icon: Icon, color }) => (
          <Link
            key={to}
            to={to}
            className="card p-4 flex flex-col items-center gap-2 transition-all"
          >
            <div className={`p-2.5 rounded-lg ${color}`}>
              <Icon className="w-5 h-5" />
            </div>
            <span className="text-sm font-medium text-slate-700">{label}</span>
          </Link>
        ))}
      </div>

      {/* Recent cases */}
      {!loading && casos.length > 0 && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-slate-800">Meus processos</h2>
            <Link
              to="/portal/casos"
              className="text-xs text-primary-600 hover:underline"
            >
              Ver todos
            </Link>
          </div>
          <div className="space-y-2">
            {casos.slice(0, 5).map((c) => {
              const [label, cor] = STATUS[c.status] ?? [
                c.status,
                "bg-slate-100 text-slate-500",
              ];
              return (
                <Link
                  key={c.id}
                  to={`/portal/casos/${c.id}`}
                  className="flex items-center gap-3 p-3 rounded-lg border border-slate-100 hover:bg-slate-50 transition-colors"
                >
                  <Scale className="w-4 h-4 text-slate-400 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800 truncate">
                      {c.titulo}
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      {c.numero_processo || c.numero_interno || "—"}
                    </p>
                  </div>
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded-full font-medium flex-shrink-0 ${cor}`}
                  >
                    {label}
                  </span>
                  <ChevronRight className="w-4 h-4 text-slate-300 flex-shrink-0" />
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {/* Pending payments */}
      {!loading && pendente > 0 && (
        <div className="bg-warn-50 border border-warn-200 rounded-xl p-4 flex items-center gap-4">
          <AlertCircle className="w-6 h-6 text-warn-600 flex-shrink-0" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-warn-800">
              Você tem valores pendentes
            </p>
            <p className="text-xs text-warn-700 mt-0.5">
              {fmtR$(pendente)} aguardando pagamento
            </p>
          </div>
          <Link
            to="/portal/financeiro"
            className="px-3 py-1.5 bg-warn-600 text-white text-sm rounded-lg hover:bg-warn-700"
          >
            Ver detalhes
          </Link>
        </div>
      )}
    </div>
  );
}
