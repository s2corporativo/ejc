import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  User,
  Briefcase,
  Clock,
  FileText,
  DollarSign,
  AlertTriangle,
  ChevronRight,
  ArrowLeft,
  TrendingUp,
  CheckCircle,
  XCircle,
  Calendar,
  Scale,
  ClipboardList,
  Plus,
  Send,
  MessageCircle,
  Mail,
  Phone,
  X,
  Download,
  Receipt,
  Bot,
} from "lucide-react";
import api from "../lib/api";
import { StatusBadge } from "../components/UI";

interface DossieData {
  cliente: {
    id: number;
    nome: string;
    email: string;
    telefone: string;
    cpf_cnpj: string;
    tipo: string;
    created_at: string;
  };
  resumo: {
    total_casos: number;
    casos_ativos: number;
    casos_encerrados: number;
    prazos_proximos: number;
    docs_total: number;
    honorarios_total: number;
    honorarios_recebido: number;
    honorarios_pendente: number;
    status_breakdown: Record<string, number>;
    area_breakdown: Record<string, number>;
  };
  casos: Array<{
    id: number;
    numero_interno: string;
    titulo: string;
    area: string;
    status: string;
    fase: string;
    created_at: string;
    updated_at: string;
  }>;
  prazos: Array<{
    id: number;
    case_id: number;
    descricao: string;
    due_date: string;
    dias_restantes: number;
    tipo: string;
    urgente: boolean;
  }>;
  documentos_recentes: Array<{
    id: number;
    case_id: number;
    nome: string;
    tipo: string;
    created_at: string;
  }>;
}

const fmt = (v: number) =>
  v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

const STATUS_LABEL: Record<string, string> = {
  em_andamento: "Em andamento",
  ativo: "Ativo",
  encerrado: "Encerrado",
  arquivado: "Arquivado",
  suspenso: "Suspenso",
  aguardando: "Aguardando",
};

const AREA_LABEL: Record<string, string> = {
  civel: "Cível",
  trabalhista: "Trabalhista",
  penal: "Penal",
  empresarial: "Empresarial",
  administrativo: "Administrativo",
  bancario: "Bancário",
  tributario: "Tributário",
  ambiental: "Ambiental",
};

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  color = "bronze",
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}) {
  const colors: Record<string, string> = {
    bronze: "bg-bronze-50 text-bronze-deep border-bronze-pale",
    navy: "bg-navy-50 text-navy-700 border-navy-100",
    emerald: "bg-success-50 text-success-700 border-success-200",
    amber: "bg-warn-50 text-warn-700 border-warn-200",
    red: "bg-danger-50 text-danger-700 border-danger-200",
  };
  return (
    <div className={`card border p-4 flex items-start gap-3 ${colors[color]}`}>
      <div className="mt-0.5 p-2 rounded-lg bg-white/60">
        <Icon className="w-4 h-4" />
      </div>
      <div className="min-w-0">
        <p className="label-caps text-current opacity-70">{label}</p>
        <p className="text-2xl font-serif font-normal leading-tight">{value}</p>
        {sub && <p className="text-xs mt-0.5 opacity-60">{sub}</p>}
      </div>
    </div>
  );
}

function PrazoRow({ p }: { p: DossieData["prazos"][0] }) {
  return (
    <Link
      to={`/casos/${p.case_id}`}
      className="flex items-center gap-3 px-4 py-2.5 hover:bg-bronze-50/60 transition-colors group"
    >
      <div
        className={`w-2 h-2 rounded-full flex-shrink-0 ${p.urgente ? "bg-danger-500" : p.dias_restantes <= 15 ? "bg-warn-400" : "bg-success-400"}`}
      />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-navy-900 truncate">{p.descricao}</p>
        <p className="text-xs text-slate-400 mt-0.5">Caso #{p.case_id}</p>
      </div>
      <div className="text-right flex-shrink-0">
        <p
          className={`text-xs font-medium ${p.urgente ? "text-danger-600" : p.dias_restantes <= 15 ? "text-warn-600" : "text-slate-500"}`}
        >
          {p.dias_restantes === 0
            ? "Hoje"
            : p.dias_restantes === 1
              ? "Amanhã"
              : `${p.dias_restantes}d`}
        </p>
        <p className="text-[10px] text-slate-400">
          {new Date(p.due_date + "T00:00:00").toLocaleDateString("pt-BR")}
        </p>
      </div>
      <ChevronRight className="w-3 h-3 text-slate-300 group-hover:text-bronze transition-colors" />
    </Link>
  );
}

// ── Tipos ──────────────────────────────────────────────────────────────────
type PendingItem = {
  id: string;
  type: string;
  title: string;
  description?: string;
  status: string;
  due_date?: string;
  created_at: string;
};

const PENDING_STATUS_COLOR: Record<string, string> = {
  pendente: "bg-yellow-100 text-yellow-700",
  solicitado: "bg-primary-100 text-primary-700",
  recebido: "bg-ai-100 text-ai-700",
  em_analise: "bg-orange-100 text-orange-700",
  concluido: "bg-green-100 text-green-700",
};
const PENDING_STATUS_LABEL: Record<string, string> = {
  pendente: "Pendente",
  solicitado: "Solicitado",
  recebido: "Recebido",
  em_analise: "Em análise",
  concluido: "Concluído",
};

// ── PendingItemsPanel ───────────────────────────────────────────────────────
function PendingItemsPanel({ clientId }: { clientId: string | number }) {
  const [items, setItems] = useState<PendingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({
    title: "",
    type: "documento",
    description: "",
    due_date: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(`/v1/clients/${clientId}/pending-items`);
      setItems(res.data || []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [clientId]);

  useEffect(() => {
    load();
  }, [load]);

  async function create() {
    if (!form.title.trim()) return;
    await api.post(`/v1/clients/${clientId}/pending-items`, {
      ...form,
      due_date: form.due_date || undefined,
    });
    setForm({ title: "", type: "documento", description: "", due_date: "" });
    setShowAdd(false);
    load();
  }

  async function updateStatus(id: string, status: string) {
    await api.patch(`/v1/clients/${clientId}/pending-items/${id}`, { status });
    load();
  }

  async function remove(id: string) {
    if (!window.confirm("Remover pendência?")) return;
    await api.delete(`/v1/clients/${clientId}/pending-items/${id}`);
    load();
  }

  const active = items.filter((i) => i.status !== "concluido");
  const done = items.filter((i) => i.status === "concluido");

  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-bronze-pale flex items-center justify-between">
        <p className="eyebrow flex items-center gap-2">
          <ClipboardList className="w-3 h-3" />
          Pendências do Cliente
          {active.length > 0 && (
            <span className="badge badge-warn text-[10px]">
              {active.length}
            </span>
          )}
        </p>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="flex items-center gap-1 text-xs text-bronze hover:text-bronze-dark font-medium transition-colors"
        >
          <Plus className="w-3 h-3" /> Adicionar
        </button>
      </div>

      {showAdd && (
        <div className="p-3 bg-slate-50 border-b border-bronze-pale/50 space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <select
              className="text-xs border border-slate-200 rounded px-2 py-1.5"
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value })}
            >
              <option value="documento">Documento</option>
              <option value="informacao">Informação</option>
              <option value="assinatura">Assinatura</option>
              <option value="pagamento">Pagamento</option>
              <option value="procuracao">Procuração</option>
              <option value="certidao">Certidão</option>
              <option value="outro">Outro</option>
            </select>
            <input
              type="date"
              className="text-xs border border-slate-200 rounded px-2 py-1.5"
              value={form.due_date}
              onChange={(e) => setForm({ ...form, due_date: e.target.value })}
              placeholder="Prazo"
            />
          </div>
          <input
            type="text"
            placeholder="Título da pendência *"
            className="w-full text-xs border border-slate-200 rounded px-2 py-1.5"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <input
            type="text"
            placeholder="Descrição (opcional)"
            className="w-full text-xs border border-slate-200 rounded px-2 py-1.5"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <div className="flex gap-2 justify-end">
            <button
              onClick={() => setShowAdd(false)}
              className="text-xs text-slate-500 px-3 py-1 hover:bg-slate-100 rounded"
            >
              Cancelar
            </button>
            <button
              onClick={create}
              className="text-xs bg-bronze text-white px-3 py-1 rounded hover:bg-bronze-dark transition-colors"
            >
              Salvar
            </button>
          </div>
        </div>
      )}

      <div className="divide-y divide-bronze-pale/50">
        {loading && (
          <p className="px-4 py-4 text-xs text-slate-400 text-center">
            Carregando...
          </p>
        )}
        {!loading && active.length === 0 && done.length === 0 && (
          <div className="px-4 py-5 flex items-center gap-2 text-sm text-success-600">
            <CheckCircle className="w-4 h-4" /> Sem pendências em aberto
          </div>
        )}
        {active.map((item) => (
          <div
            key={item.id}
            className="flex items-start gap-3 px-4 py-2.5 hover:bg-bronze-50/40 transition-colors group"
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm text-navy-900 font-medium truncate">
                  {item.title}
                </span>
                <span
                  className={`badge text-[10px] ${PENDING_STATUS_COLOR[item.status] ?? "bg-slate-100 text-slate-500"}`}
                >
                  {PENDING_STATUS_LABEL[item.status] ?? item.status}
                </span>
                <span className="text-[10px] text-slate-400 uppercase">
                  {item.type}
                </span>
              </div>
              {item.description && (
                <p className="text-xs text-slate-500 mt-0.5 truncate">
                  {item.description}
                </p>
              )}
              {item.due_date && (
                <p className="text-[10px] text-slate-400 mt-0.5">
                  Prazo:{" "}
                  {new Date(item.due_date + "T12:00:00").toLocaleDateString(
                    "pt-BR",
                  )}
                </p>
              )}
            </div>
            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
              {item.status !== "concluido" && (
                <select
                  className="text-[10px] border border-slate-200 rounded px-1 py-0.5 bg-white"
                  value={item.status}
                  onChange={(e) => updateStatus(item.id, e.target.value)}
                >
                  <option value="pendente">Pendente</option>
                  <option value="solicitado">Solicitado</option>
                  <option value="recebido">Recebido</option>
                  <option value="em_analise">Em análise</option>
                  <option value="concluido">Concluído</option>
                </select>
              )}
              <button
                onClick={() => remove(item.id)}
                className="p-1 text-slate-300 hover:text-danger-500 transition-colors"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          </div>
        ))}
        {done.length > 0 && (
          <details className="group/done">
            <summary className="px-4 py-2 text-xs text-slate-400 cursor-pointer hover:text-slate-600 list-none flex items-center gap-1">
              <CheckCircle className="w-3 h-3" /> {done.length} concluída(s)
            </summary>
            {done.map((item) => (
              <div
                key={item.id}
                className="flex items-center gap-3 px-4 py-2 opacity-50"
              >
                <CheckCircle className="w-3 h-3 text-success-500 flex-shrink-0" />
                <span className="text-xs text-slate-500 line-through truncate">
                  {item.title}
                </span>
              </div>
            ))}
          </details>
        )}
      </div>
    </div>
  );
}

// ── WhatsApp / Comunicação ──────────────────────────────────────────────────
function ComunicacaoRapida({
  cliente,
}: {
  cliente: {
    id?: string | number;
    nome: string;
    telefone?: string;
    whatsapp?: string;
    email?: string;
  };
}) {
  const registrarAtendimento = (tipo: string, resumo: string) => {
    if (!cliente.id) return;
    api
      .post("/atendimentos", {
        client_id: String(cliente.id),
        tipo,
        data_atendimento: new Date().toISOString(),
        resumo: resumo.length >= 10 ? resumo : resumo + " — contato registrado",
      })
      .catch(() => {});
  };
  const phone = cliente.whatsapp || cliente.telefone;
  if (!phone && !cliente.email) return null;
  const digits = phone ? phone.replace(/\D/g, "") : "";
  const wa = digits.startsWith("55") ? digits : "55" + digits;
  return (
    <div className="card p-3 flex items-center gap-3">
      <span className="text-xs font-medium text-slate-500 eyebrow">
        Contato rápido
      </span>
      <div className="flex gap-2 ml-auto">
        {phone && (
          <a
            href={`https://wa.me/${wa}?text=${encodeURIComponent("Olá " + cliente.nome + "!")}`}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() =>
              registrarAtendimento(
                "whatsapp",
                "Contato via WhatsApp com " + cliente.nome,
              )
            }
            className="flex items-center gap-1 px-2.5 py-1.5 bg-green-500 text-white rounded-lg hover:bg-green-600 transition-colors text-xs font-medium"
          >
            <MessageCircle className="w-3.5 h-3.5" /> WhatsApp
          </a>
        )}
        {phone && (
          <a
            href={`tel:${phone}`}
            onClick={() =>
              registrarAtendimento("ligacao", "Ligação para " + cliente.nome)
            }
            className="flex items-center gap-1 px-2.5 py-1.5 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors text-xs font-medium"
          >
            <Phone className="w-3.5 h-3.5" /> Ligar
          </a>
        )}
        {cliente.email && (
          <a
            href={`mailto:${cliente.email}`}
            onClick={() =>
              registrarAtendimento(
                "email",
                "E-mail enviado para " + cliente.nome,
              )
            }
            className="flex items-center gap-1 px-2.5 py-1.5 bg-slate-600 text-white rounded-lg hover:bg-slate-700 transition-colors text-xs font-medium"
          >
            <Mail className="w-3.5 h-3.5" /> E-mail
          </a>
        )}
        <a
          href={`https://calendar.google.com/calendar/u/0/r/eventedit?text=${encodeURIComponent("Reunião — " + cliente.nome)}`}
          target="_blank"
          rel="noopener noreferrer"
          onClick={() =>
            registrarAtendimento(
              "reuniao_virtual",
              "Reunião agendada com " + cliente.nome,
            )
          }
          className="flex items-center gap-1 px-2.5 py-1.5 bg-ai-600 text-white rounded-lg hover:bg-ai-700 transition-colors text-xs font-medium"
        >
          <Calendar className="w-3.5 h-3.5" /> Reunião
        </a>
      </div>
    </div>
  );
}

// ── Relatório Financeiro do Cliente ─────────────────────────────────────────
function RelatorioFinanceiro({
  clientId,
  clienteNome,
}: {
  clientId: string | number;
  clienteNome: string;
}) {
  const [rel, setRel] = useState<any>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const fmtm = (v: number) =>
    (v ?? 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

  const carregar = async () => {
    setLoading(true);
    try {
      const r = await api.get(`/clients/${clientId}/relatorio-financeiro`);
      setRel(r.data);
      setOpen(true);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  };

  const exportarCSV = () => {
    if (!rel) return;
    const linhas: string[] = ["Data;Tipo;Categoria;Descrição;Caso;Valor"];
    for (const e of rel.extrato ?? []) {
      linhas.push(
        [
          e.data,
          e.tipo,
          e.categoria,
          (e.descricao || "").replace(/;/g, ","),
          (e.caso || "").replace(/;/g, ","),
          String(e.valor).replace(".", ","),
        ].join(";"),
      );
    }
    const blob = new Blob(["\ufeff" + linhas.join("\n")], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `extrato-${clienteNome.replace(/\s+/g, "_")}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const imprimir = () => window.print();

  const r = rel?.resumo;
  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-bronze-pale flex items-center justify-between">
        <p className="eyebrow flex items-center gap-2">
          <Receipt className="w-3 h-3" /> Relatório Financeiro
        </p>
        <div className="flex gap-2">
          {open && rel && (
            <>
              <button
                onClick={exportarCSV}
                className="flex items-center gap-1 text-xs text-bronze hover:text-bronze-dark font-medium"
              >
                <Download className="w-3 h-3" /> CSV
              </button>
              <button
                onClick={imprimir}
                className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 font-medium"
              >
                <FileText className="w-3 h-3" /> PDF
              </button>
            </>
          )}
          {!open && (
            <button
              onClick={carregar}
              disabled={loading}
              className="flex items-center gap-1 text-xs text-bronze hover:text-bronze-dark font-medium"
            >
              {loading ? "Gerando..." : "Gerar relatório"}
            </button>
          )}
        </div>
      </div>

      {open && r && (
        <div className="p-4 space-y-4">
          {/* Cards resumo */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {[
              { l: "Total honorários", v: fmtm(r.total), c: "text-navy-900" },
              { l: "Recebido", v: fmtm(r.recebido), c: "text-success-600" },
              { l: "Pendente", v: fmtm(r.pendente), c: "text-warn-600" },
              {
                l: "Êxito recebido",
                v: fmtm(r.exito_recebido),
                c: "text-bronze-deep",
              },
              {
                l: "Contratuais",
                v: fmtm(r.honorarios_contratuais),
                c: "text-navy-700",
              },
              {
                l: "Custas/despesas",
                v: fmtm(r.custas_despesas),
                c: "text-slate-600",
              },
              {
                l: "Despesas pagas",
                v: fmtm(r.despesas_pagas),
                c: "text-danger-500",
              },
              {
                l: "Resultado líquido",
                v: fmtm(r.resultado_liquido),
                c:
                  r.resultado_liquido >= 0
                    ? "text-success-600"
                    : "text-danger-600",
              },
            ].map(({ l, v, c }) => (
              <div key={l} className="bg-slate-50 rounded-lg p-2.5">
                <p className="text-[10px] text-slate-500 uppercase tracking-wide">
                  {l}
                </p>
                <p className={`text-sm font-bold mt-0.5 ${c}`}>{v}</p>
              </div>
            ))}
          </div>

          {/* Extrato */}
          {(rel.extrato ?? []).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase mb-2">
                Extrato
              </p>
              <div className="max-h-64 overflow-y-auto divide-y divide-slate-100">
                {rel.extrato.map((e: any, i: number) => (
                  <div
                    key={i}
                    className="flex items-center justify-between py-2 text-xs"
                  >
                    <div className="min-w-0">
                      <span className="text-slate-700">{e.descricao}</span>
                      {e.caso && (
                        <span className="text-slate-400 ml-1">· {e.caso}</span>
                      )}
                      <span className="text-slate-300 ml-1">
                        {new Date(e.data + "T12:00").toLocaleDateString(
                          "pt-BR",
                        )}
                      </span>
                    </div>
                    <span
                      className={`font-semibold flex-shrink-0 ml-2 ${e.tipo === "credito" ? "text-success-600" : "text-danger-500"}`}
                    >
                      {e.tipo === "credito" ? "+" : "−"} {fmtm(e.valor)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function DossieCliente() {
  const { clientId } = useParams<{ clientId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<DossieData | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState("");
  const [abaAtiva, setAbaAtiva] = useState("resumo");

  useEffect(() => {
    if (!clientId) return;
    api
      .get(`/clients/${clientId}/dossie`)
      .then((r: { data: DossieData }) => setData(r.data))
      .catch(() => setErro("Não foi possível carregar o dossiê."))
      .finally(() => setLoading(false));
  }, [clientId]);

  if (loading)
    return (
      <div className="flex items-center justify-center h-64 text-slate-400">
        <div className="text-center">
          <Scale className="w-8 h-8 mx-auto mb-3 animate-pulse text-bronze-pale" />
          <p className="text-sm">Carregando dossiê…</p>
        </div>
      </div>
    );

  if (erro || !data)
    return (
      <div className="flex items-center justify-center h-64 text-danger-500 text-sm">
        {erro || "Erro"}
      </div>
    );

  const { cliente, resumo, casos, prazos, documentos_recentes } = data;
  const taxaRecebimento =
    resumo.honorarios_total > 0
      ? Math.round((resumo.honorarios_recebido / resumo.honorarios_total) * 100)
      : 0;

  const abas = [
    { id: "resumo", label: "Resumo", icon: TrendingUp },
    { id: "casos", label: "Casos", icon: Briefcase },
    { id: "prazos", label: "Prazos", icon: Calendar },
    { id: "financeiro", label: "Financeiro", icon: DollarSign },
    { id: "documentos", label: "Documentos", icon: FileText },
    { id: "ia_cliente", label: "IA do Cliente", icon: Bot },
  ];

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6 animate-rise">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate(-1)}
          className="btn-ghost p-2 rounded-lg"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div className="flex-1 min-w-0">
          <p className="eyebrow">Ficha Mestra do Cliente</p>
          <h1 className="text-2xl">{cliente.nome}</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            {cliente.cpf_cnpj && (
              <span className="mr-3">{cliente.cpf_cnpj}</span>
            )}
            {cliente.email && <span className="mr-3">{cliente.email}</span>}
            {cliente.telefone && <span>{cliente.telefone}</span>}
          </p>
        </div>
        <Link to={`/clientes/${clientId}`} className="btn-outline text-xs">
          <User className="w-3 h-3" /> Editar perfil
        </Link>
      </div>

      {/* Seletor de Abas (Ficha Mestra - Seção 2.113) */}
      <div className="flex border-b border-bronze-pale overflow-x-auto no-scrollbar">
        {abas.map((aba) => (
          <button
            key={aba.id}
            onClick={() => setAbaAtiva(aba.id)}
            className={`flex items-center gap-2 px-6 py-3 text-sm font-medium transition-all border-b-2 whitespace-nowrap ${
              abaAtiva === aba.id
                ? "border-bronze text-bronze"
                : "border-transparent text-slate-400 hover:text-slate-600"
            }`}
          >
            <aba.icon className="w-4 h-4" />
            {aba.label}
          </button>
        ))}
      </div>

      {/* Conteúdo Dinâmico por Aba */}
      {abaAtiva === "resumo" && (
        <div className="space-y-6 animate-fade-in">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard
              icon={Briefcase}
              label="Casos"
              value={resumo.total_casos}
              sub={`${resumo.casos_ativos} ativos`}
              color="navy"
            />
            <StatCard
              icon={Clock}
              label="Prazos próximos"
              value={resumo.prazos_proximos}
              sub="próximos 60 dias"
              color={resumo.prazos_proximos > 0 ? "amber" : "emerald"}
            />
            <StatCard
              icon={DollarSign}
              label="Honorários"
              value={fmt(resumo.honorarios_total)}
              sub={`${taxaRecebimento}% recebido`}
              color="bronze"
            />
            <StatCard
              icon={FileText}
              label="Documentos"
              value={resumo.docs_total}
              sub="em todos os casos"
              color="bronze"
            />
          </div>
          <div className="grid lg:grid-cols-2 gap-4">
            <PendingItemsPanel clientId={clientId!} />
            <ComunicacaoRapida cliente={cliente} />
          </div>
        </div>
      )}

      {abaAtiva === "casos" && (
        <div className="card overflow-hidden animate-fade-in">
          <div className="px-4 py-3 border-b border-bronze-pale flex items-center justify-between">
            <p className="eyebrow flex items-center gap-2">
              <Briefcase className="w-3 h-3" /> Carteira de Casos ({casos.length})
            </p>
            <Link to={`/casos/novo?client_id=${clientId}`} className="btn-outline text-[10px] py-1">
              + Novo caso
            </Link>
          </div>
          <div className="divide-y divide-bronze-pale/50">
            {casos.map((c) => (
              <Link key={c.id} to={`/casos/${c.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-bronze-50/60 transition-colors group">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-navy-900 font-medium truncate">{c.titulo}</p>
                  <p className="text-[11px] text-slate-400 mt-0.5">{c.numero_interno} · {AREA_LABEL[c.area] ?? c.area}</p>
                </div>
                <StatusBadge value={c.status} />
                <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-bronze" />
              </Link>
            ))}
          </div>
        </div>
      )}

      {abaAtiva === "prazos" && (
        <div className="card overflow-hidden animate-fade-in">
          <div className="px-4 py-3 border-b border-bronze-pale">
            <p className="eyebrow flex items-center gap-2">
              <Calendar className="w-3 h-3" /> Agenda de Prazos
            </p>
          </div>
          <div className="divide-y divide-bronze-pale/50">
            {prazos.map((p) => (
              <PrazoRow key={p.id} p={p} />
            ))}
          </div>
        </div>
      )}

      {abaAtiva === "financeiro" && (
        <div className="space-y-4 animate-fade-in">
          <RelatorioFinanceiro clientId={clientId!} clienteNome={cliente.nome} />
        </div>
      )}

      {abaAtiva === "documentos" && (
        <div className="card overflow-hidden animate-fade-in">
          <div className="px-4 py-3 border-b border-bronze-pale">
            <p className="eyebrow flex items-center gap-2">
              <FileText className="w-3 h-3" /> Acervo Documental
            </p>
          </div>
          <div className="divide-y divide-bronze-pale/50">
            {documentos_recentes.map((doc) => (
              <Link key={doc.id} to={`/casos/${doc.case_id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-bronze-50/60 transition-colors group">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-navy-900 font-medium truncate">{doc.nome}</p>
                  <p className="text-[10px] text-slate-400 mt-0.5">Caso #{doc.case_id} · {doc.tipo}</p>
                </div>
                <Download className="w-4 h-4 text-slate-300 group-hover:text-bronze" />
              </Link>
            ))}
          </div>
        </div>
      )}

      {abaAtiva === "ia_cliente" && (
        <div className="card p-8 text-center space-y-4 animate-fade-in">
          <Bot className="w-12 h-12 mx-auto text-bronze-pale animate-pulse" />
          <h3 className="text-lg font-serif">IA do Cliente (Análise 360º)</h3>
          <p className="text-sm text-slate-500 max-w-md mx-auto">
            O Cérebro do EJC está processando o histórico deste cliente para identificar padrões de litígio, riscos financeiros e oportunidades estratégicas.
          </p>
          <button className="btn-primary">Iniciar Análise Estratégica</button>
        </div>
      )}

      {/* Distribuição por área */}
      {Object.keys(resumo.area_breakdown).length > 1 && (
        <div className="card p-4">
          <p className="eyebrow mb-3 flex items-center gap-2">
            <Scale className="w-3 h-3" /> Distribuição por área
          </p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(resumo.area_breakdown)
              .sort((a, b) => b[1] - a[1])
              .map(([area, n]) => (
                <div
                  key={area}
                  className="badge badge-neutral px-3 py-1 text-xs"
                >
                  {AREA_LABEL[area] ?? area}{" "}
                  <span className="ml-1 font-semibold">{n}</span>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Comunicação Rápida */}
      <ComunicacaoRapida cliente={cliente} />

      {/* Relatório Financeiro */}
      <RelatorioFinanceiro clientId={cliente.id} clienteNome={cliente.nome} />

      {/* Pendências do Cliente */}
      <PendingItemsPanel clientId={cliente.id} />
    </div>
  );
}
