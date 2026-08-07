import { useEffect, useState, useCallback, useMemo } from "react";
import { useParams, useNavigate, useSearchParams, Link } from "react-router";
import {
  User,
  Briefcase,
  Clock,
  FileText,
  DollarSign,
  ChevronRight,
  ArrowLeft,
  TrendingUp,
  CheckCircle,
  Calendar,
  Scale,
  ClipboardList,
  Plus,
  MessageCircle,
  Mail,
  Phone,
  X,
  Download,
  Receipt,
  Bot,
  ExternalLink,
  KeyRound,
  Zap,
  AlertTriangle,
} from "lucide-react";
import api from "../lib/api";
import ClientServiceTimeline, {
  type ClientTimelineExtraEvent,
} from "../components/ClientServiceTimeline";
import { soDigitos } from "../utils/phone";
import { toast } from "../components/Toast";
import { areaLabel } from "../lib/areas";
import {
  PageHeader,
  Spinner,
  StatusBadge,
  fmtMoney,
  ConfirmModal,
  Modal,
} from "../components/UI";

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
  // Degradação por seção: o backend isola cada agregação e nomeia aqui a que
  // não pôde ser carregada, em vez de responder 500 e deixar a ficha fechada.
  // Sem esta lista o usuário veria "0 prazos" achando que não há prazo — a
  // falha silenciosa que o padrão de erro do EJC proíbe.
  secoes_indisponiveis?: string[];
}

const ROTULO_SECAO: Record<string, string> = {
  casos: "casos",
  prazos: "prazos",
  documentos: "documentos",
  honorarios: "financeiro",
  resumo_casos: "resumo dos casos",
};

export function AvisoSecoesIndisponiveis({
  secoes,
  onRecarregar,
}: {
  secoes: string[];
  onRecarregar: () => void;
}) {
  if (!secoes.length) return null;
  const nomes = secoes.map((s) => ROTULO_SECAO[s] ?? s);
  const lista =
    nomes.length === 1
      ? nomes[0]
      : `${nomes.slice(0, -1).join(", ")} e ${nomes[nomes.length - 1]}`;
  return (
    <div
      role="status"
      className="card border border-warn-200 bg-warn-50 text-warn-700 p-4 flex items-start gap-3"
    >
      <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
      <div className="text-sm">
        <p className="font-medium">
          Ficha carregada parcialmente: {lista} não {nomes.length === 1 ? "pôde" : "puderam"} ser
          carregad{nomes.length === 1 ? "a" : "as"}.
        </p>
        <p className="mt-1">
          Os demais dados desta tela estão completos. O erro foi registrado para a
          equipe técnica.
        </p>
        <button
          type="button"
          onClick={onRecarregar}
          className="mt-2 underline underline-offset-2 font-medium"
        >
          Tentar novamente
        </button>
      </div>
    </div>
  );
}

// Rótulos de área vêm da taxonomia canônica (lib/areas.ts — enum CaseArea).

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
function PendingItemsPanel({
  clientId,
  abrirNovaSignal = 0,
  onItemsChange,
}: {
  clientId: string | number;
  /** Incrementado pelo painel de ações rápidas para abrir o formulário de
   *  solicitação de documento já pré-configurado. */
  abrirNovaSignal?: number;
  onItemsChange?: (items: PendingItem[]) => void;
}) {
  const [items, setItems] = useState<PendingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [pendenteExcluir, setPendenteExcluir] = useState<string | null>(null);
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
      onItemsChange?.(res.data || []);
    } catch {
      setItems([]);
      onItemsChange?.([]);
      toast.error("Não foi possível carregar as pendências do cliente");
    } finally {
      setLoading(false);
    }
  }, [clientId, onItemsChange]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (abrirNovaSignal > 0) {
      setShowAdd(true);
      setForm((f) => ({ ...f, type: "documento" }));
    }
  }, [abrirNovaSignal]);

  async function create() {
    if (!form.title.trim()) return;
    try {
      await api.post(`/v1/clients/${clientId}/pending-items`, {
        ...form,
        due_date: form.due_date || undefined,
      });
      setForm({ title: "", type: "documento", description: "", due_date: "" });
      setShowAdd(false);
      load();
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Não foi possível criar a pendência",
      );
    }
  }

  async function updateStatus(id: string, status: string) {
    try {
      await api.patch(`/v1/clients/${clientId}/pending-items/${id}`, {
        status,
      });
      load();
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Não foi possível atualizar a pendência",
      );
    }
  }

  function remove(id: string) {
    setPendenteExcluir(id);
  }

  async function confirmarExclusao() {
    if (!pendenteExcluir) return;
    try {
      await api.delete(
        `/v1/clients/${clientId}/pending-items/${pendenteExcluir}`,
      );
      setPendenteExcluir(null);
      load();
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Não foi possível excluir a pendência",
      );
    }
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
              className="input py-1.5 text-xs"
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
              className="input py-1.5 text-xs"
              value={form.due_date}
              onChange={(e) => setForm({ ...form, due_date: e.target.value })}
              placeholder="Prazo"
            />
          </div>
          <input
            type="text"
            placeholder="Título da pendência *"
            className="input py-1.5 text-xs"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <input
            type="text"
            placeholder="Descrição (opcional)"
            className="input py-1.5 text-xs"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <div className="flex gap-2 justify-end">
            <button
              onClick={() => setShowAdd(false)}
              className="btn-ghost px-3 py-1 text-xs"
            >
              Cancelar
            </button>
            <button onClick={create} className="btn-primary px-3 py-1 text-xs">
              Salvar
            </button>
          </div>
        </div>
      )}

      <div className="divide-y divide-bronze-pale/50">
        {loading && <Spinner />}
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
                  className="input w-auto px-1 py-0.5 text-[10px]"
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

      <ConfirmModal
        open={pendenteExcluir !== null}
        onClose={() => setPendenteExcluir(null)}
        onConfirm={confirmarExclusao}
        title="Remover pendência"
        message="Remover esta pendência?"
        confirmLabel="Remover"
        variant="danger"
      />
    </div>
  );
}

// Desfechos possíveis do contato rápido — mapeados para o vocabulário que o
// backend aceita (PATCH /atendimentos/{id}: contato_status ∈ iniciado |
// confirmado | nao_concluido; detalhe registrado em proximo_passo).
const DESFECHOS_CONTATO: Array<{
  label: string;
  patch: { contato_status: string; proximo_passo?: string };
}> = [
  { label: "Contato concluído", patch: { contato_status: "confirmado" } },
  { label: "Não respondeu", patch: { contato_status: "nao_concluido" } },
  {
    label: "Retorno agendado",
    patch: {
      contato_status: "confirmado",
      proximo_passo: "Retorno agendado com o cliente.",
    },
  },
  {
    label: "Recado deixado",
    patch: {
      contato_status: "nao_concluido",
      proximo_passo: "Recado deixado; aguardando retorno do cliente.",
    },
  },
];

// ── WhatsApp / Comunicação ──────────────────────────────────────────────────
function ComunicacaoRapida({
  cliente,
  onRegistrado,
}: {
  cliente: {
    id?: string | number;
    nome: string;
    telefone?: string;
    whatsapp?: string;
    email?: string;
  };
  onRegistrado?: () => void;
}) {
  const [followUp, setFollowUp] = useState<{
    id: string;
    tipo: string;
  } | null>(null);
  const [salvandoDesfecho, setSalvandoDesfecho] = useState(false);

  const registrarAtendimento = (tipo: string, resumo: string) => {
    if (!cliente.id) return;
    api
      .post("/atendimentos", {
        client_id: String(cliente.id),
        tipo,
        data_atendimento: new Date().toISOString(),
        resumo: resumo.length >= 10 ? resumo : resumo + " — contato iniciado",
        contato_status: "iniciado",
      })
      .then((r) => {
        // Ao voltar o foco para a aba, o mini-modal pede o desfecho do contato.
        if (r.data?.id) setFollowUp({ id: String(r.data.id), tipo });
        onRegistrado?.();
      })
      .catch(() => {
        toast.error(
          "Não foi possível registrar o contato no histórico de atendimentos",
        );
      });
  };

  const concluirContato = async (patch: {
    contato_status: string;
    proximo_passo?: string;
  }) => {
    if (!followUp) return;
    setSalvandoDesfecho(true);
    try {
      await api.patch(`/atendimentos/${followUp.id}`, patch);
      toast.success("Desfecho do contato registrado no histórico");
      setFollowUp(null);
      onRegistrado?.();
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail ||
          "Não foi possível registrar o desfecho do contato",
      );
    } finally {
      setSalvandoDesfecho(false);
    }
  };

  const phone = cliente.whatsapp || cliente.telefone;
  if (!phone && !cliente.email) return null;
  const digits = soDigitos(phone);
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
                "Contato iniciado via WhatsApp com " + cliente.nome,
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
              registrarAtendimento(
                "ligacao",
                "Tentativa de ligação iniciada para " + cliente.nome,
              )
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
                "Contato por e-mail iniciado para " + cliente.nome,
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
              "Agendamento de reunião iniciado com " + cliente.nome,
            )
          }
          className="flex items-center gap-1 px-2.5 py-1.5 bg-ai-600 text-white rounded-lg hover:bg-ai-700 transition-colors text-xs font-medium"
        >
          <Calendar className="w-3.5 h-3.5" /> Reunião
        </a>
      </div>

      {/* Mini-modal de confirmação pós-contato */}
      <Modal
        open={followUp !== null}
        onClose={() => setFollowUp(null)}
        title="Como terminou o contato?"
      >
        <div className="space-y-3">
          <p className="text-sm text-slate-500">
            O contato foi registrado como <strong>iniciado</strong>. Informe o
            desfecho para manter o histórico de atendimento fiel.
          </p>
          <div className="grid grid-cols-2 gap-2">
            {DESFECHOS_CONTATO.map(({ label, patch }) => (
              <button
                key={label}
                type="button"
                disabled={salvandoDesfecho}
                onClick={() => concluirContato(patch)}
                className="btn-outline justify-center text-xs"
              >
                {label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setFollowUp(null)}
            className="btn-ghost w-full justify-center text-xs"
          >
            Decidir depois (confirme na linha do tempo)
          </button>
        </div>
      </Modal>
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
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail ||
          "Não foi possível carregar o relatório financeiro",
      );
    } finally {
      setLoading(false);
    }
  };

  const exportarCSV = () => {
    if (!rel) {
      toast.error("Carregue o relatório antes de exportar");
      return;
    }
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
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const validTabs = [
    "resumo",
    "atendimentos",
    "casos",
    "prazos",
    "financeiro",
    "documentos",
    // "ia_cliente" sai dos deep-links enquanto a aba está oculta do seletor
    // (painel "Em breve" preservado no código para reativação futura).
  ];
  const [data, setData] = useState<DossieData | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState("");
  const [abaAtiva, setAbaAtiva] = useState(
    requestedTab && validTabs.includes(requestedTab) ? requestedTab : "resumo",
  );

  useEffect(() => {
    const tab = searchParams.get("tab");
    if (tab && validTabs.includes(tab)) setAbaAtiva(tab);
  }, [searchParams]);

  const carregarDossie = useCallback(() => {
    if (!clientId) return;
    api
      .get(`/clients/${clientId}/dossie`)
      .then((r: { data: DossieData }) => setData(r.data))
      .catch(() => setErro("Não foi possível carregar o dossiê."))
      .finally(() => setLoading(false));
  }, [clientId]);

  useEffect(() => {
    carregarDossie();
  }, [carregarDossie]);

  // Edição de perfil inline (PATCH /clients/{id}) — a rota /clientes/:id é a
  // própria Ficha Mestra, então "Editar perfil" abre um modal aqui mesmo.
  const [editOpen, setEditOpen] = useState(false);
  const [editForm, setEditForm] = useState({
    nome: "",
    email: "",
    telefone: "",
    whatsapp: "",
  });
  const [salvandoEdit, setSalvandoEdit] = useState(false);

  const abrirEdicao = () => {
    const c: any = data?.cliente ?? {};
    setEditForm({
      nome: c.nome || "",
      email: c.email || "",
      telefone: c.telefone || "",
      whatsapp: c.whatsapp || "",
    });
    setEditOpen(true);
  };

  const salvarEdicao = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editForm.nome.trim()) {
      toast.error("O nome do cliente é obrigatório");
      return;
    }
    setSalvandoEdit(true);
    try {
      await api.patch(`/clients/${clientId}`, {
        nome: editForm.nome.trim(),
        email: editForm.email.trim() || null,
        telefone: editForm.telefone.trim() || null,
        whatsapp: editForm.whatsapp.trim() || null,
      });
      toast.success("Perfil do cliente atualizado");
      setEditOpen(false);
      carregarDossie();
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      toast.error(
        typeof detail === "string"
          ? detail
          : "Não foi possível atualizar o perfil",
      );
    } finally {
      setSalvandoEdit(false);
    }
  };

  const baixarDocumento = async (docId: string | number, nome: string) => {
    try {
      const r = await api.get(`/documents/${docId}/download`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(r.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = nome || `documento-${docId}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Não foi possível baixar o documento",
      );
    }
  };

  // ── Indicadores de relacionamento (topo) ─────────────────────────────────
  const [ultimaInteracao, setUltimaInteracao] = useState<string | null>(null);
  const [indicadoresProntos, setIndicadoresProntos] = useState(false);
  const [pendingItems, setPendingItems] = useState<PendingItem[]>([]);
  const [responsavelNome, setResponsavelNome] = useState<string | null>(null);

  const carregarUltimaInteracao = useCallback(async () => {
    if (!clientId) return;
    try {
      const r = await api.get("/atendimentos", {
        params: { client_id: clientId, page: 1, per_page: 1 },
      });
      setUltimaInteracao(r.data?.items?.[0]?.data_atendimento ?? null);
    } catch {
      // Indicador opcional — a ficha continua funcional sem ele.
    } finally {
      setIndicadoresProntos(true);
    }
  }, [clientId]);

  useEffect(() => {
    carregarUltimaInteracao();
  }, [carregarUltimaInteracao]);

  useEffect(() => {
    if (!clientId) return;
    (async () => {
      try {
        const [cliRes, respRes] = await Promise.all([
          api.get(`/clients/${clientId}`),
          api.get("/atendimentos/responsaveis"),
        ]);
        const rid = cliRes.data?.responsavel_id;
        if (!rid) return;
        const lista = Array.isArray(respRes.data) ? respRes.data : [];
        setResponsavelNome(lista.find((u: any) => u.id === rid)?.nome ?? null);
      } catch {
        // Responsável é opcional no cabeçalho.
      }
    })();
  }, [clientId]);

  const handlePendingItems = useCallback(
    (items: PendingItem[]) => setPendingItems(items),
    [],
  );

  // Carga inicial das pendências para os indicadores do topo — o painel da aba
  // Resumo mantém a lista atualizada via onItemsChange quando montado.
  useEffect(() => {
    if (!clientId) return;
    api
      .get(`/v1/clients/${clientId}/pending-items`)
      .then((r) => setPendingItems(r.data || []))
      .catch(() => {
        // Indicador opcional — o painel de pendências reporta o erro ao usuário.
      });
  }, [clientId]);

  // ── Ações rápidas ────────────────────────────────────────────────────────
  const [solicitarDocSignal, setSolicitarDocSignal] = useState(0);
  const [acessoOpen, setAcessoOpen] = useState(false);
  const [acessoForm, setAcessoForm] = useState({
    email: "",
    senha_inicial: "",
  });
  const [criandoAcesso, setCriandoAcesso] = useState(false);

  const criarAcessoPortal = async () => {
    if (!acessoForm.email.trim() || acessoForm.senha_inicial.length < 8) {
      toast.error("Informe e-mail e senha inicial com no mínimo 8 caracteres");
      return;
    }
    setCriandoAcesso(true);
    try {
      await api.post(`/clients/${clientId}/criar-acesso`, {
        email: acessoForm.email.trim(),
        senha_inicial: acessoForm.senha_inicial,
      });
      toast.success(
        "Acesso criado — informe o e-mail e a senha inicial ao cliente",
      );
      setAcessoOpen(false);
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Não foi possível criar o acesso ao portal",
      );
    } finally {
      setCriandoAcesso(false);
    }
  };

  // Fontes extras da linha do tempo (documentos e aberturas de caso) — dados
  // que o dossiê já carregou; nenhuma chamada adicional.
  const eventosExtras = useMemo<ClientTimelineExtraEvent[]>(() => {
    if (!data) return [];
    return [
      ...data.documentos_recentes.map((d) => ({
        id: `doc-${d.id}`,
        label: "Documento",
        titulo: d.nome,
        data: d.created_at,
        link: `/casos/${d.case_id}`,
      })),
      ...data.casos.map((c) => ({
        id: `caso-${c.id}`,
        label: "Caso aberto",
        titulo: c.titulo,
        data: c.created_at,
        link: `/casos/${c.id}`,
      })),
    ];
  }, [data]);

  if (loading) return <Spinner />;

  if (erro || !data)
    return (
      <div className="flex items-center justify-center h-64 text-danger-500 text-sm">
        {erro || "Erro"}
      </div>
    );

  const { cliente, resumo, casos, prazos, documentos_recentes } = data;

  // Indicadores de relacionamento derivados
  const diasSemContato = ultimaInteracao
    ? Math.max(
        0,
        Math.floor(
          (Date.now() - new Date(ultimaInteracao).getTime()) / 86_400_000,
        ),
      )
    : null;
  const pendenciasAtivas = pendingItems.filter((i) => i.status !== "concluido");
  const pendenciasVencidas = pendenciasAtivas.filter(
    (i) => i.due_date && new Date(i.due_date + "T23:59:59") < new Date(),
  ).length;
  const proximaProvidencia =
    pendenciasAtivas
      .filter((i) => i.due_date)
      .sort((a, b) => a.due_date!.localeCompare(b.due_date!))[0] ?? null;

  const taxaRecebimento =
    resumo.honorarios_total > 0
      ? Math.round((resumo.honorarios_recebido / resumo.honorarios_total) * 100)
      : 0;

  const abas = [
    { id: "resumo", label: "Resumo", icon: TrendingUp },
    { id: "atendimentos", label: "Atendimentos", icon: MessageCircle },
    { id: "casos", label: "Casos", icon: Briefcase },
    { id: "prazos", label: "Prazos", icon: Calendar },
    { id: "financeiro", label: "Financeiro", icon: DollarSign },
    { id: "documentos", label: "Documentos", icon: FileText },
    // PENTE FINO 2026-07 (onda 2): a aba "IA do Cliente" fica FORA do seletor
    // até existir implementação real — o painel abaixo (abaAtiva ===
    // "ia_cliente") é mantido para reativação futura sem retrabalho.
  ];

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6 animate-rise">
      <AvisoSecoesIndisponiveis
        secoes={data.secoes_indisponiveis ?? []}
        onRecarregar={() => {
          setLoading(true);
          carregarDossie();
        }}
      />
      {/* Header */}
      <div className="flex items-start gap-3">
        <button
          onClick={() => navigate(-1)}
          className="btn-ghost p-2 rounded-lg mt-1"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div className="flex-1 min-w-0">
          <PageHeader
            eyebrow="Ficha Mestra do Cliente"
            title={cliente.nome}
            subtitle={
              [cliente.cpf_cnpj, cliente.email, cliente.telefone]
                .filter(Boolean)
                .join(" · ") || undefined
            }
            actions={
              <>
                <a
                  href="/portal"
                  target="_blank"
                  rel="noreferrer"
                  className="btn-ghost text-xs"
                  title="Abrir o Portal do Cliente em uma nova aba"
                >
                  <ExternalLink className="w-3 h-3" /> Portal do Cliente
                </a>
                <button onClick={abrirEdicao} className="btn-outline text-xs">
                  <User className="w-3 h-3" /> Editar perfil
                </button>
              </>
            }
          />
        </div>
      </div>

      {/* Indicadores de relacionamento */}
      <div className="card divide-x divide-bronze-pale/50 grid grid-cols-2 lg:grid-cols-4 xl:flex">
        <div className="px-4 py-3 xl:flex-1 min-w-0">
          <p className="label-caps text-slate-400">Última interação</p>
          <p className="text-sm font-medium text-navy-900 mt-0.5">
            {ultimaInteracao
              ? new Date(ultimaInteracao).toLocaleDateString("pt-BR")
              : indicadoresProntos
                ? "Sem registros"
                : "…"}
          </p>
        </div>
        <div className="px-4 py-3 xl:flex-1 min-w-0">
          <p className="label-caps text-slate-400">Sem contato há</p>
          <p
            className={`text-sm font-medium mt-0.5 ${
              diasSemContato !== null && diasSemContato > 30
                ? "text-danger-600"
                : "text-navy-900"
            }`}
          >
            {diasSemContato === null
              ? "—"
              : diasSemContato === 0
                ? "Hoje"
                : `${diasSemContato} dia${diasSemContato > 1 ? "s" : ""}`}
          </p>
        </div>
        <div className="px-4 py-3 xl:flex-1 min-w-0">
          <p className="label-caps text-slate-400">Pendências vencidas</p>
          <p
            className={`text-sm font-medium mt-0.5 flex items-center gap-1 ${
              pendenciasVencidas > 0 ? "text-danger-600" : "text-success-600"
            }`}
          >
            {pendenciasVencidas > 0 && (
              <AlertTriangle className="w-3.5 h-3.5" />
            )}
            {pendenciasVencidas}
          </p>
        </div>
        <div className="px-4 py-3 xl:flex-1 min-w-0">
          <p className="label-caps text-slate-400">Próxima providência</p>
          <p
            className="text-sm font-medium text-navy-900 mt-0.5 truncate"
            title={proximaProvidencia?.title}
          >
            {proximaProvidencia
              ? `${proximaProvidencia.title} · ${new Date(
                  proximaProvidencia.due_date + "T12:00:00",
                ).toLocaleDateString("pt-BR")}`
              : "—"}
          </p>
        </div>
        {responsavelNome && (
          <div className="px-4 py-3 xl:flex-1 min-w-0 col-span-2 lg:col-span-4 xl:col-auto">
            <p className="label-caps text-slate-400">Responsável</p>
            <p className="text-sm font-medium text-navy-900 mt-0.5 truncate">
              {responsavelNome}
            </p>
          </div>
        )}
      </div>

      {/* Seletor de Abas (Ficha Mestra - Seção 2.113) */}
      <div className="flex border-b border-bronze-pale overflow-x-auto no-scrollbar">
        {abas.map((aba) => (
          <button
            key={aba.id}
            onClick={() => {
              setAbaAtiva(aba.id);
              setSearchParams({ tab: aba.id }, { replace: true });
            }}
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
              value={fmtMoney(resumo.honorarios_total)}
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
          {/* Painel de ações rápidas */}
          <div className="card p-4">
            <p className="eyebrow mb-3 flex items-center gap-2">
              <Zap className="w-3 h-3" /> Ações rápidas
            </p>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => {
                  setAbaAtiva("atendimentos");
                  setSearchParams(
                    { tab: "atendimentos", novo: "1" },
                    { replace: true },
                  );
                }}
                className="btn-outline text-xs"
              >
                <MessageCircle className="w-3.5 h-3.5" /> Registrar atendimento
              </button>
              <button
                onClick={() => setSolicitarDocSignal((s) => s + 1)}
                className="btn-outline text-xs"
              >
                <FileText className="w-3.5 h-3.5" /> Solicitar documento
              </button>
              <Link
                to={`/casos/novo?client_id=${clientId}`}
                className="btn-outline text-xs"
              >
                <Briefcase className="w-3.5 h-3.5" /> Cadastrar caso
              </Link>
              <Link
                to="/atividades"
                title="Agendar na Central de Atividades"
                className="btn-outline text-xs"
              >
                <Calendar className="w-3.5 h-3.5" /> Agendar reunião
              </Link>
              <button
                onClick={() => {
                  setAcessoForm({
                    email: cliente.email || "",
                    senha_inicial: "",
                  });
                  setAcessoOpen(true);
                }}
                className="btn-outline text-xs"
              >
                <KeyRound className="w-3.5 h-3.5" /> Acesso ao portal
              </button>
            </div>
          </div>

          <div className="grid lg:grid-cols-2 gap-4">
            <PendingItemsPanel
              clientId={clientId!}
              abrirNovaSignal={solicitarDocSignal}
              onItemsChange={handlePendingItems}
            />
            <ComunicacaoRapida
              cliente={cliente}
              onRegistrado={carregarUltimaInteracao}
            />
          </div>
        </div>
      )}

      {abaAtiva === "atendimentos" && (
        <div className="animate-fade-in">
          <ClientServiceTimeline
            clientId={clientId!}
            cases={casos}
            extraEvents={eventosExtras}
            autoOpenForm={searchParams.get("novo") === "1"}
          />
        </div>
      )}

      {abaAtiva === "casos" && (
        <div className="card overflow-hidden animate-fade-in">
          <div className="px-4 py-3 border-b border-bronze-pale flex items-center justify-between">
            <p className="eyebrow flex items-center gap-2">
              <Briefcase className="w-3 h-3" /> Carteira de Casos (
              {casos.length})
            </p>
            <Link
              to={`/casos/novo?client_id=${clientId}`}
              className="btn-outline text-[10px] py-1"
            >
              + Novo caso
            </Link>
          </div>
          <div className="divide-y divide-bronze-pale/50">
            {casos.map((c) => (
              <Link
                key={c.id}
                to={`/casos/${c.id}`}
                className="flex items-center gap-3 px-4 py-3 hover:bg-bronze-50/60 transition-colors group"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-navy-900 font-medium truncate">
                    {c.titulo}
                  </p>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    {c.numero_interno} · {areaLabel(c.area) || c.area}
                  </p>
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
          <RelatorioFinanceiro
            clientId={clientId!}
            clienteNome={cliente.nome}
          />
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
              <div
                key={doc.id}
                className="flex items-center gap-3 px-4 py-3 hover:bg-bronze-50/60 transition-colors group"
              >
                <Link to={`/casos/${doc.case_id}`} className="flex-1 min-w-0">
                  <p className="text-sm text-navy-900 font-medium truncate">
                    {doc.nome}
                  </p>
                  <p className="text-[10px] text-slate-400 mt-0.5">
                    Caso #{doc.case_id} · {doc.tipo}
                  </p>
                </Link>
                <button
                  onClick={() => baixarDocumento(doc.id, doc.nome)}
                  title="Baixar documento"
                  className="p-1"
                >
                  <Download className="w-4 h-4 text-slate-300 group-hover:text-bronze" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {abaAtiva === "ia_cliente" && (
        <div className="card p-8 text-center space-y-4 animate-fade-in">
          <Bot className="w-12 h-12 mx-auto text-bronze-pale" />
          <h3 className="text-lg font-serif">IA do Cliente (Análise 360º)</h3>
          <p className="text-sm text-slate-500 max-w-md mx-auto">
            A análise estratégica automática do histórico deste cliente (padrões
            de litígio, riscos financeiros e oportunidades) ainda está em
            desenvolvimento. Enquanto isso, use a Pesquisa e IA com o caso do
            cliente selecionado.
          </p>
          <span className="inline-block text-xs font-medium text-slate-400 border border-bronze-pale rounded-full px-3 py-1">
            Em breve
          </span>
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
                  {areaLabel(area) || area}{" "}
                  <span className="ml-1 font-semibold">{n}</span>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Modal — Conceder acesso ao Portal do Cliente */}
      <Modal
        open={acessoOpen}
        onClose={() => setAcessoOpen(false)}
        title="Acesso ao Portal do Cliente"
      >
        <div className="space-y-4">
          <p className="text-sm text-slate-500">
            {cliente.nome} — o cliente trocará a senha no primeiro login.
          </p>
          <div>
            <label className="label">E-mail de login *</label>
            <input
              type="email"
              className="input"
              autoComplete="off"
              value={acessoForm.email}
              onChange={(e) =>
                setAcessoForm((p) => ({ ...p, email: e.target.value }))
              }
            />
          </div>
          <div>
            <label className="label">Senha inicial (mín. 8) *</label>
            <input
              type="password"
              className="input"
              autoComplete="new-password"
              value={acessoForm.senha_inicial}
              onChange={(e) =>
                setAcessoForm((p) => ({ ...p, senha_inicial: e.target.value }))
              }
            />
          </div>
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={() => setAcessoOpen(false)}
              className="btn-secondary flex-1"
            >
              Cancelar
            </button>
            <button
              type="button"
              onClick={criarAcessoPortal}
              disabled={criandoAcesso}
              className="btn-primary flex-1"
            >
              {criandoAcesso ? "Criando..." : "Criar acesso"}
            </button>
          </div>
        </div>
      </Modal>

      {/* Modal — Editar perfil do cliente */}
      <Modal
        open={editOpen}
        onClose={() => setEditOpen(false)}
        title="Editar perfil do cliente"
      >
        <form onSubmit={salvarEdicao} className="space-y-4">
          <div>
            <label className="label">Nome *</label>
            <input
              className="input"
              value={editForm.nome}
              onChange={(e) =>
                setEditForm((p) => ({ ...p, nome: e.target.value }))
              }
            />
          </div>
          <div>
            <label className="label">E-mail</label>
            <input
              type="email"
              className="input"
              value={editForm.email}
              onChange={(e) =>
                setEditForm((p) => ({ ...p, email: e.target.value }))
              }
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Telefone</label>
              <input
                className="input"
                value={editForm.telefone}
                onChange={(e) =>
                  setEditForm((p) => ({ ...p, telefone: e.target.value }))
                }
              />
            </div>
            <div>
              <label className="label">WhatsApp</label>
              <input
                className="input"
                value={editForm.whatsapp}
                onChange={(e) =>
                  setEditForm((p) => ({ ...p, whatsapp: e.target.value }))
                }
              />
            </div>
          </div>
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={() => setEditOpen(false)}
              className="btn-secondary flex-1"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={salvandoEdit}
              className="btn-primary flex-1"
            >
              {salvandoEdit ? <Spinner /> : "Salvar"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
