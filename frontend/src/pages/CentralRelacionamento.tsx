import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router";
import {
  Users,
  TrendingUp,
  MessageCircle,
  Phone,
  Mail,
  UserCheck,
  Clock,
  ChevronRight,
  RefreshCw,
  Star,
} from "lucide-react";
import api from "../lib/api";
import { soDigitos } from "../utils/phone";
import { AtendimentoStats } from "../components/Dashboards";
import { Button, PageHeader, Spinner } from "../components/UI";
import { asList } from "../lib/list";

interface FunilData {
  total_cadastros: number;
  // já vem na escala 0–100 (ou null) do backend
  taxa_conversao_geral: number | null;
  por_estagio: Record<string, number>;
  por_origem: {
    origem: string;
    total: number;
    convertidos: number;
    taxa_conversao: number | null;
  }[];
  nota?: string;
}

// Formata taxa 0–100 → "NN%"; null/NaN/Infinity → "—"
function fmtTaxa(v?: number | null): string {
  return Number.isFinite(v) ? `${Math.round(v as number)}%` : "—";
}

interface ClienteRecente {
  id: string;
  nome: string;
  telefone?: string;
  email?: string;
  whatsapp?: string;
  status: string;
  etapa_funil?: string;
  origem_lead?: string;
  area_interesse?: string;
  created_at: string;
}

function fmtDate(d: string) {
  return new Date(d).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
  });
}

function StatCard({
  label,
  value,
  icon: Icon,
  color = "blue",
  sub,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  color?: "blue" | "green" | "amber" | "red" | "slate";
  sub?: string;
}) {
  const cls = {
    blue: "bg-primary-50 text-primary-600",
    green: "bg-success-50 text-success-600",
    amber: "bg-warn-50 text-warn-600",
    red: "bg-danger-50 text-danger-600",
    slate: "bg-slate-100 text-slate-500",
  }[color];
  return (
    <div className="card p-4 flex items-center gap-4">
      <div className={`p-3 rounded-lg ${cls}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-xs text-slate-500 uppercase tracking-wide">
          {label}
        </p>
        <p className="text-xl font-bold text-slate-800 mt-0.5">{value}</p>
        {sub && <p className="text-xs text-slate-400">{sub}</p>}
      </div>
    </div>
  );
}

const ETAPA_LABEL: Record<string, string> = {
  lead: "Lead",
  contato: "Contato",
  reuniao: "Reunião",
  proposta: "Proposta",
  convertido: "Convertido",
  perdido: "Perdido",
};
const ETAPA_COLOR: Record<string, string> = {
  lead: "bg-slate-100 text-slate-600",
  contato: "bg-primary-100 text-primary-700",
  reuniao: "bg-warn-100 text-warn-700",
  proposta: "bg-ai-100 text-ai-700",
  convertido: "bg-success-100 text-success-700",
  perdido: "bg-danger-100 text-danger-600",
};

export default function CentralRelacionamento() {
  const [funil, setFunil] = useState<FunilData | null>(null);
  const [clientes, setClientes] = useState<ClienteRecente[]>([]);
  const [leads, setLeads] = useState<ClienteRecente[]>([]);
  const [loading, setLoading] = useState(true);
  const nav = useNavigate();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [funilRes, clientesRes, leadsRes] = await Promise.allSettled([
        api.get("/analytics/funil"),
        api.get("/clients/?page_size=10&status=ativo"),
        api.get("/clients/?page_size=20&status=lead"),
      ]);
      if (funilRes.status === "fulfilled") setFunil(funilRes.value.data);
      if (clientesRes.status === "fulfilled") {
        const d = clientesRes.value.data;
        setClientes(asList<ClienteRecente>(d));
      }
      if (leadsRes.status === "fulfilled") {
        const d = leadsRes.value.data;
        setLeads(asList<ClienteRecente>(d));
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const ativos = funil?.por_estagio?.ativo ?? 0;
  const leadCount = funil?.por_estagio?.lead ?? leads.length;
  const taxa = fmtTaxa(funil?.taxa_conversao_geral);

  const openWA = (phone: string, nome: string) => {
    const d = soDigitos(phone);
    const wa = d.startsWith("55") ? d : "55" + d;
    window.open(
      `https://wa.me/${wa}?text=${encodeURIComponent("Olá " + nome + "!")}`,
      "_blank",
    );
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <PageHeader
        title="Central de Relacionamento"
        subtitle="Funil CRM, captação e engajamento de clientes"
        actions={
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => nav("/crm-leads")}
              className="btn-primary text-sm"
            >
              <Users className="w-4 h-4" /> Funil de Leads
            </button>
            <Button
              onClick={load}
              variant="secondary"
              size="icon"
              aria-label="Atualizar"
              icon={
                <RefreshCw
                  className={`w-4 h-4 text-slate-400 ${loading ? "animate-spin" : ""}`}
                />
              }
            />
          </div>
        }
      />

      <AtendimentoStats />

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total de clientes"
          value={funil?.total_cadastros ?? "—"}
          icon={Users}
          color="slate"
        />
        <StatCard
          label="Ativos"
          value={ativos}
          icon={UserCheck}
          color="green"
          sub="clientes com casos abertos"
        />
        <StatCard
          label="Leads em aberto"
          value={leadCount}
          icon={Clock}
          color="amber"
          sub="aguardando conversão"
        />
        <StatCard
          label="Taxa de conversão"
          value={taxa}
          icon={TrendingUp}
          color="blue"
          sub="leads → ativos"
        />
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Funil por estágio */}
        <div className="card p-5">
          <h2 className="font-semibold text-slate-800 mb-4">
            Funil por estágio
          </h2>
          {loading ? (
            <Spinner />
          ) : (
            <div className="space-y-2.5">
              {[
                { k: "lead", l: "Leads" },
                { k: "ativo", l: "Ativos" },
                { k: "inativo", l: "Inativos" },
                { k: "arquivado", l: "Arquivados" },
              ].map(({ k, l }) => {
                const v = funil?.por_estagio?.[k] ?? 0;
                const total = funil?.total_cadastros ?? 1;
                const pct = Math.round((v / total) * 100);
                return (
                  <div key={k}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-slate-600">{l}</span>
                      <span className="font-semibold text-slate-800">{v}</span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary-500 rounded-full"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          <button
            onClick={() => nav("/crm-leads")}
            className="mt-4 w-full text-xs text-primary-600 hover:underline flex items-center justify-center gap-1"
          >
            Ver funil de leads <ChevronRight className="w-3 h-3" />
          </button>
        </div>

        {/* Por origem */}
        <div className="card p-5">
          <h2 className="font-semibold text-slate-800 mb-4">
            Por origem de captação
          </h2>
          {loading ? (
            <Spinner />
          ) : !funil?.por_origem?.length ? (
            <p className="text-slate-400 text-sm text-center py-6">
              Sem dados de origem ainda
            </p>
          ) : (
            <div className="space-y-2">
              {funil.por_origem.map((o, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between py-2 border-b border-slate-50 last:border-0 text-sm"
                >
                  <div className="flex items-center gap-2">
                    <Star className="w-3 h-3 text-warn-400" />
                    <span className="text-slate-700 capitalize">
                      {o.origem || "Não informado"}
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-slate-800 font-medium">
                      {o.total}
                    </span>
                    <span className="text-slate-400 text-xs ml-1">
                      · {fmtTaxa(o.taxa_conversao)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Leads recentes */}
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-slate-800">Leads recentes</h2>
            <button
              onClick={() => nav("/crm-leads")}
              className="text-xs text-primary-600 hover:underline"
            >
              Ver todos
            </button>
          </div>
          <div className="space-y-2">
            {loading ? (
              <Spinner />
            ) : leads.length === 0 ? (
              <p className="text-slate-400 text-sm text-center py-6">
                Nenhum lead cadastrado
              </p>
            ) : (
              leads.slice(0, 8).map((lead) => (
                <div
                  key={lead.id}
                  className="flex items-center gap-3 py-2 border-b border-slate-50 last:border-0 group"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800 truncate">
                      {lead.nome}
                    </p>
                    <div className="flex items-center gap-2 mt-0.5">
                      {lead.etapa_funil && (
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${ETAPA_COLOR[lead.etapa_funil] ?? "bg-slate-100 text-slate-500"}`}
                        >
                          {ETAPA_LABEL[lead.etapa_funil] ?? lead.etapa_funil}
                        </span>
                      )}
                      {lead.area_interesse && (
                        <span className="text-[10px] text-slate-400">
                          {lead.area_interesse}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    {(lead.whatsapp || lead.telefone) && (
                      <button
                        onClick={() =>
                          openWA(lead.whatsapp || lead.telefone!, lead.nome)
                        }
                        className="p-1 bg-green-50 text-green-600 rounded hover:bg-green-100"
                      >
                        <MessageCircle className="w-3 h-3" />
                      </button>
                    )}
                    {lead.email && (
                      <a
                        href={`mailto:${lead.email}`}
                        className="p-1 bg-slate-50 text-slate-500 rounded hover:bg-slate-100"
                      >
                        <Mail className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                  <span className="text-[10px] text-slate-400 flex-shrink-0">
                    {fmtDate(lead.created_at)}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Clientes ativos recentes */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-slate-800">
            Clientes ativos — contato rápido
          </h2>
          <button
            onClick={() => nav("/clientes")}
            className="text-xs text-primary-600 hover:underline"
          >
            Ver todos
          </button>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
          {loading ? (
            <Spinner />
          ) : clientes.length === 0 ? (
            <p className="text-slate-400 text-sm">
              Nenhum cliente ativo encontrado
            </p>
          ) : (
            clientes.map((c) => (
              <div
                key={c.id}
                className="flex items-center gap-3 p-3 rounded-lg border border-slate-100 hover:bg-slate-50 group"
              >
                <div className="w-8 h-8 bg-slate-100 rounded-full flex items-center justify-center flex-shrink-0">
                  <Users className="w-4 h-4 text-slate-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-800 truncate">
                    {c.nome}
                  </p>
                  {c.email && (
                    <p className="text-xs text-slate-400 truncate">{c.email}</p>
                  )}
                </div>
                <div className="flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  {(c.whatsapp || c.telefone) && (
                    <button
                      onClick={() => openWA(c.whatsapp || c.telefone!, c.nome)}
                      className="p-1.5 bg-green-50 text-green-600 rounded-lg hover:bg-green-100"
                    >
                      <MessageCircle className="w-3.5 h-3.5" />
                    </button>
                  )}
                  {c.telefone && (
                    <a
                      href={`tel:${c.telefone}`}
                      className="p-1.5 bg-primary-50 text-primary-600 rounded-lg hover:bg-primary-100"
                    >
                      <Phone className="w-3.5 h-3.5" />
                    </a>
                  )}
                  {c.email && (
                    <a
                      href={`mailto:${c.email}`}
                      className="p-1.5 bg-slate-50 text-slate-500 rounded-lg hover:bg-slate-100"
                    >
                      <Mail className="w-3.5 h-3.5" />
                    </a>
                  )}
                  <button
                    onClick={() => nav(`/clientes/${c.id}`)}
                    className="p-1.5 bg-slate-50 text-slate-500 rounded-lg hover:bg-slate-100"
                  >
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
