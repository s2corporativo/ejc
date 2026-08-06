import { useEffect, useState } from "react";
import { Link } from "react-router";
import {
  Scale,
  FileText,
  DollarSign,
  Bell,
  ChevronRight,
  CheckCircle,
  AlertCircle,
  FileUp,
  PenLine,
  MessageCircle,
} from "lucide-react";
import api from "../../lib/api";
import { useAuth } from "../../stores/auth";
import { asList } from "../../lib/list";
import { fmtDate } from "../../components/UI";
import { CASE_STATUS_LABEL, isCasoAtivo } from "../../types/caseStatus";

/** Cor por status; RÓTULO vem do vocabulário canônico (types/caseStatus.ts). */
const STATUS_COR: Record<string, string> = {
  aberto: "bg-warn-100 text-warn-700",
  em_instrucao: "bg-primary-100 text-primary-700",
  em_producao: "bg-primary-100 text-primary-700",
  protocolado: "bg-primary-100 text-primary-700",
  encerrado: "bg-success-100 text-success-700",
  arquivado: "bg-slate-100 text-slate-500",
};

const fmtR$ = (v: number) =>
  v?.toLocaleString("pt-BR", { style: "currency", currency: "BRL" }) ??
  "R$ 0,00";

interface Pendencia {
  to: string;
  icon: typeof FileUp;
  texto: string;
  cta: string;
}

export default function PortalDashboard() {
  const { user } = useAuth();
  const [casos, setCasos] = useState<any[]>([]);
  const [fees, setFees] = useState<any[]>([]);
  const [solicitacoes, setSolicitacoes] = useState<any[]>([]);
  const [assinaturas, setAssinaturas] = useState<any[]>([]);
  const [mensagensNaoLidas, setMensagensNaoLidas] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Somente endpoints acessíveis ao cliente_externo (/portal/* e /signatures,
    // que filtra por client_id no backend). Nunca chamar rotas de staff aqui.
    Promise.allSettled([
      api.get("/portal/meus-casos"),
      api.get("/portal/financeiro"),
      api.get("/portal/solicitacoes-documentos"),
      api.get("/signatures/"),
      // Contagem SEM efeito colateral (não marca como lida) — próprio p/ badge.
      api.get("/portal/mensagens/nao-lidas"),
    ])
      .then(([c, f, s, a, m]) => {
        if (c.status === "fulfilled") setCasos(asList(c.value.data));
        if (f.status === "fulfilled") setFees(asList(f.value.data));
        if (s.status === "fulfilled") setSolicitacoes(asList(s.value.data));
        if (a.status === "fulfilled") setAssinaturas(asList(a.value.data));
        if (m.status === "fulfilled")
          setMensagensNaoLidas(Number(m.value.data?.nao_lidas) || 0);
      })
      .finally(() => setLoading(false));
  }, []);

  const ativos = casos.filter((c) => isCasoAtivo(c.status)).length;
  // O backend retorna a lista de lançamentos ({data: [...]}) — os totais são
  // derivados aqui no frontend.
  const pendente = fees
    .filter((f) => f.status === "pendente" || f.status === "atrasado")
    .reduce((s, f) => s + (f.valor ?? 0), 0);
  const honPago = fees
    .filter((f) => f.status === "pago")
    .reduce((s, f) => s + (f.valor ?? 0), 0);

  // ── Pendências do cliente, em ordem de prioridade:
  // 1) documento solicitado  2) assinatura pendente  3) mensagem nova
  // 4) pagamento em aberto. (Contagem de mensagens via
  // /portal/mensagens/nao-lidas — sem efeito colateral.)
  const docsPendentes = solicitacoes.reduce(
    (n, s) =>
      n +
      (Array.isArray(s.itens)
        ? s.itens.filter((i: any) => i.status === "pendente").length
        : 0),
    0,
  );
  const assinaturasPendentes = assinaturas.filter(
    (a) => a.status === "pendente",
  ).length;
  const pagamentosAbertos = fees.filter(
    (f) => f.status === "pendente" || f.status === "atrasado",
  ).length;

  const pendencias: Pendencia[] = [];
  if (docsPendentes > 0)
    pendencias.push({
      to: "/portal/documentos",
      icon: FileUp,
      texto: `${docsPendentes} documento${docsPendentes > 1 ? "s" : ""} solicitado${docsPendentes > 1 ? "s" : ""} pelo escritório aguardando envio`,
      cta: "Enviar",
    });
  if (assinaturasPendentes > 0)
    pendencias.push({
      to: "/portal/assinaturas",
      icon: PenLine,
      texto: `${assinaturasPendentes} documento${assinaturasPendentes > 1 ? "s" : ""} aguardando sua assinatura`,
      cta: "Assinar",
    });
  if (mensagensNaoLidas > 0)
    pendencias.push({
      to: "/portal/mensagens",
      icon: MessageCircle,
      texto: `${mensagensNaoLidas} ${mensagensNaoLidas > 1 ? "mensagens novas" : "mensagem nova"} do escritório`,
      cta: "Ler",
    });
  if (pagamentosAbertos > 0)
    pendencias.push({
      to: "/portal/financeiro",
      icon: DollarSign,
      texto: `${pagamentosAbertos} pagamento${pagamentosAbertos > 1 ? "s" : ""} em aberto (${fmtR$(pendente)})`,
      cta: "Ver",
    });
  const totalPendencias =
    docsPendentes +
    assinaturasPendentes +
    mensagensNaoLidas +
    pagamentosAbertos;

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

      {/* Ação mais importante: pendências do cliente */}
      {!loading &&
        (totalPendencias > 0 ? (
          <div className="bg-warn-50 border border-warn-200 rounded-xl p-4">
            <div className="flex items-center gap-3 mb-3">
              <AlertCircle className="w-6 h-6 text-warn-600 flex-shrink-0" />
              <p className="text-sm font-semibold text-warn-800">
                Você tem {totalPendencias} pendência
                {totalPendencias > 1 ? "s" : ""}
              </p>
            </div>
            <div className="space-y-2">
              {pendencias.map(({ to, icon: Icon, texto, cta }) => (
                <Link
                  key={to}
                  to={to}
                  className="flex items-center gap-3 p-3 rounded-lg bg-white border border-warn-100 hover:border-warn-300 transition-colors"
                >
                  <Icon className="w-4 h-4 text-warn-600 flex-shrink-0" />
                  <span className="flex-1 text-sm text-slate-700">{texto}</span>
                  <span className="text-xs font-semibold text-warn-700 flex-shrink-0">
                    {cta}
                  </span>
                  <ChevronRight className="w-4 h-4 text-warn-300 flex-shrink-0" />
                </Link>
              ))}
            </div>
          </div>
        ) : (
          <div className="bg-success-50 border border-success-200 rounded-xl p-4 flex items-center gap-3">
            <CheckCircle className="w-6 h-6 text-success-600 flex-shrink-0" />
            <div>
              <p className="text-sm font-semibold text-success-700">
                Você está em dia
              </p>
              <p className="text-xs text-success-600 mt-0.5">
                Nenhum documento, assinatura ou pagamento pendente no momento.
              </p>
            </div>
          </div>
        ))}

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
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
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
            to: "/portal/assinaturas",
            label: "Assinaturas",
            icon: PenLine,
            color: "text-primary-600 bg-primary-50",
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
              const label =
                CASE_STATUS_LABEL[c.status as keyof typeof CASE_STATUS_LABEL] ??
                c.status;
              const cor = STATUS_COR[c.status] ?? "bg-slate-100 text-slate-500";
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
                      {c.created_at &&
                        ` · No escritório desde ${fmtDate(c.created_at)}`}
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
    </div>
  );
}
