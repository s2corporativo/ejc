import { toast } from "../components/Toast";
import Markdown from "../components/Markdown";
import React, { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams, useNavigate } from "react-router-dom";
import {
  Sparkles,
  ChevronLeft,
  RefreshCw,
  ShieldCheck,
  Copy,
  Archive,
  ArchiveRestore,
} from "lucide-react";
import api from "../lib/api";
import { asList } from "../lib/list";
import MotorTeses from "../components/MotorTeses";
import LinhaDoTempoProcessual from "../components/visual/LinhaDoTempoProcessual";
import MatrizRisco from "../components/visual/MatrizRisco";
import BadgesAlerta from "../components/visual/BadgesAlerta";
import CalculadoraAcordo from "../components/visual/CalculadoraAcordo";
import AnaliseEstrategica from "../components/AnaliseEstrategica";
import IntakeAnalise from "../components/IntakeAnalise";
import ConversaoChecklist from "../components/ConversaoChecklist";
import ProvasCaso from "../components/ProvasCaso";
import DossieEstrategicoCaso from "../components/DossieEstrategicoCaso";
import CaseBreadcrumb from "../components/CaseBreadcrumb";
import type { Case } from "../types";
import {
  PageHeader,
  StatusBadge,
  Spinner,
  fmtDate,
  fmtMoney,
  Modal,
  ConfirmModal,
  Alert,
  Textarea,
  FieldLabel,
  Badge,
  Empty,
} from "../components/UI";
import { useAuth } from "../stores/auth";
import { RAMOS } from "./ramos/ramosConfig";
import type { FerramentaConfig } from "./ramos/ramosConfig";

// Item 4.4: baixa um documento do caso reutilizando o endpoint ja validado
// GET /documents/:id/download (mesmo padrao de Documentos.tsx).
async function baixarDoc(docId: string, filename: string) {
  try {
    const r = await api.get(`/documents/${docId}/download`, {
      responseType: "blob",
    });
    const url = URL.createObjectURL(r.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename || "documento";
    a.click();
    URL.revokeObjectURL(url);
  } catch {
    toast.error("Nao foi possivel baixar o documento.");
  }
}

const TABS = [
  { key: "resumo", label: "Resumo" },
  { key: "processos", label: "Processos" },
  { key: "timeline", label: "Timeline" },
  { key: "mensagens", label: "Mensagens" },
  { key: "partes", label: "Partes" },
  { key: "etiquetas", label: "Etiquetas" },
  { key: "checklists", label: "Checklists" },
  { key: "documentos", label: "Documentos" },
  { key: "provas", label: "Provas" },
  { key: "contratos", label: "Contratos" },
  { key: "procuracoes", label: "Procurações" },
  { key: "prazos", label: "Prazos" },
  { key: "audiencias", label: "Audiências" },
  { key: "financeiro", label: "Financeiro" },
  { key: "custos", label: "Centro de Custos" },
  { key: "liquidez", label: "Acordo & Liquidez" },
  { key: "teses", label: "Teses" },
  { key: "teses-sugeridas", label: "Teses sugeridas" },
  { key: "jurisprudencia", label: "Jurisprudência" },
  { key: "precedentes", label: "Precedentes" },
  { key: "score", label: "Score Jurídico" },
  { key: "risco", label: "Índice de Risco" },
  { key: "memoria", label: "Memória" },
  { key: "jurimetria", label: "Jurimetria" },
  { key: "dossie", label: "Dossiê Estratégico" },
  { key: "iaDefensiva", label: "IA Defensiva" },
  { key: "ferramentas", label: "⚡ Ferramentas" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

const GROUPS: { label: string; tabs: TabKey[] }[] = [
  {
    label: "Visão",
    tabs: ["resumo", "processos", "score", "risco", "jurimetria"],
  },
  {
    label: "Andamentos",
    tabs: ["timeline", "mensagens", "partes", "etiquetas", "checklists"],
  },
  {
    label: "Documentos",
    tabs: ["documentos", "provas", "contratos", "procuracoes"],
  },
  { label: "Prazos & Agenda", tabs: ["prazos", "audiencias"] },
  { label: "Financeiro", tabs: ["financeiro", "custos", "liquidez"] },
  {
    label: "Inteligência",
    tabs: [
      "teses",
      "teses-sugeridas",
      "jurisprudencia",
      "precedentes",
      "memoria",
      "dossie",
      "iaDefensiva",
      "ferramentas",
    ],
  },
];

// Pendência retornada pelo DELETE /cases/{id} em 422 (bloqueio condicional R2)
interface PendenciaExclusao {
  tipo: string;
  id: string | number;
  descricao: string;
}

// detail pode vir como string ou como objeto { mensagem, pendencias } — nunca
// renderizar objeto cru no toast.
function detalheErro(e: unknown, fallback: string): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response
    ?.data?.detail;
  if (typeof detail === "string") return detail;
  if (
    detail &&
    typeof detail === "object" &&
    typeof (detail as { mensagem?: unknown }).mensagem === "string"
  ) {
    return (detail as { mensagem: string }).mensagem;
  }
  return fallback;
}

function RiscoChip({ nivel }: { nivel?: string }) {
  const map: Record<string, string> = {
    baixo: "bg-green-100 text-green-700",
    medio: "bg-yellow-100 text-yellow-700",
    alto: "bg-orange-100 text-orange-700",
    critico: "bg-danger-100 text-danger-700",
  };
  if (!nivel) return null;
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full font-medium ${map[nivel] ?? "bg-gray-100"}`}
    >
      Risco {nivel}
    </span>
  );
}

// ── Tab: Resumo ──────────────────────────────────────────────────────────────
function ExtratoCaso({ caso }: { caso: Case }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<any>(null);
  const [erro, setErro] = useState("");
  const fmt = (v: number) =>
    (v ?? 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  const abrir = async () => {
    setOpen(true);
    if (!data) {
      setErro("");
      try {
        const r = await api.get(`/extratos/detalhado/${caso.id}`);
        setData(r.data);
      } catch (e: any) {
        setErro(
          e?.response?.data?.detail || "Falha ao carregar o extrato do caso.",
        );
      }
    }
  };
  if (
    !["superadmin", "admin", "socio", "advogado"].includes(user?.role || "")
  ) {
    return null;
  }

  return (
    <>
      <button onClick={abrir} className="btn-secondary flex items-center gap-1">
        📊 Extrato do caso
      </button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Extrato financeiro do caso"
      >
        {erro ? (
          <div className="py-8 text-center text-danger-600 text-sm">{erro}</div>
        ) : !data ? (
          <Spinner />
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              {[
                ["Entradas", data.resumo?.entradas, "text-success-600"],
                ["A receber", data.resumo?.a_receber, "text-warn-600"],
                ["Saídas (custos)", data.resumo?.saidas, "text-danger-600"],
                [
                  "Saldo",
                  data.resumo?.saldo,
                  (data.resumo?.saldo ?? 0) >= 0
                    ? "text-success-700"
                    : "text-danger-700",
                ],
              ].map(([l, v, cls]: any) => (
                <div key={l} className="bg-slate-50 rounded-lg p-3">
                  <p className="text-xs text-slate-500">{l}</p>
                  <p className={`text-base font-bold ${cls}`}>
                    {fmt(Number(v))}
                  </p>
                </div>
              ))}
            </div>
            {(data.honorarios ?? []).length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase mb-1">
                  Honorários
                </p>
                <div className="max-h-40 overflow-y-auto divide-y divide-slate-100">
                  {data.honorarios.map((h: any, i: number) => (
                    <div
                      key={i}
                      className="flex justify-between text-xs py-1.5"
                    >
                      <span className="text-slate-600 capitalize">
                        {h.tipo?.replace(/_/g, " ")} · {h.status}
                      </span>
                      <span className="font-medium">{fmt(h.valor)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>
    </>
  );
}

function AreasCaso({ caso }: { caso: Case }) {
  const TODAS = [
    "civil",
    "trabalhista",
    "consumidor",
    "familia",
    "ambiental",
    "criminal",
    "previdenciario",
    "empresarial",
    "tributario",
    "administrativo",
    "bancario",
    "imobiliario",
    "digital_lgpd",
  ];
  const [areas, setAreas] = useState<any[]>([]);
  const [add, setAdd] = useState("");
  const load = () =>
    api
      .get(`/cases/${caso.id}/areas`)
      .then((r) => setAreas(r.data?.areas ?? []))
      .catch(() => {});
  useEffect(() => {
    load(); /* eslint-disable-next-line */
  }, [caso.id]);
  const adicionar = async () => {
    if (!add) return;
    await api.post(`/cases/${caso.id}/areas`, { area: add });
    setAdd("");
    load();
  };
  const remover = async (a: string) => {
    if (!confirm("Remover esta área do caso?")) return;
    try {
      await api.delete(`/cases/${caso.id}/areas/${a}`);
      load();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao remover área");
    }
  };
  const disponiveis = TODAS.filter((t) => !areas.some((a) => a.area === t));
  return (
    <div className="card p-4">
      <h3 className="font-semibold mb-2 text-sm text-slate-500 uppercase tracking-wide">
        Áreas do caso
      </h3>
      <div className="flex flex-wrap gap-2 items-center">
        {areas.map((a) => (
          <span
            key={a.area}
            className={`inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full ${a.principal ? "bg-navy text-white" : "bg-slate-100 text-slate-600"}`}
          >
            {a.principal && "★ "}
            {a.area.replace(/_/g, " ")}
            {!a.principal && (
              <button
                onClick={() => remover(a.area)}
                className="ml-1 opacity-60 hover:opacity-100"
              >
                ×
              </button>
            )}
          </span>
        ))}
        {disponiveis.length > 0 && (
          <span className="inline-flex items-center gap-1">
            <select
              value={add}
              onChange={(e) => setAdd(e.target.value)}
              className="input text-xs px-2 py-1"
            >
              <option value="">+ área relacionada</option>
              {disponiveis.map((t) => (
                <option key={t} value={t}>
                  {t.replace(/_/g, " ")}
                </option>
              ))}
            </select>
            {add && (
              <button
                onClick={adicionar}
                className="text-xs bg-bronze text-white px-2 py-1 rounded-lg"
              >
                Add
              </button>
            )}
          </span>
        )}
      </div>
    </div>
  );
}

function TabResumo({ caso }: { caso: Case }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [iaModal, setIaModal] = useState(false);
  const [iaResp, setIaResp] = useState<any>(null);
  const [iaLoading, setIaLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [movs, setMovs] = useState<any[]>([]);
  const [novoMov, setNovoMov] = useState("");
  const [encModal, setEncModal] = useState(false);
  const [encLoading, setEncLoading] = useState(false);
  const [archiveModal, setArchiveModal] = useState(false);
  const [archiveLoading, setArchiveLoading] = useState(false);
  const [archiveReason, setArchiveReason] = useState("");
  const [reabrindo, setReabrindo] = useState(false);
  const [enc, setEnc] = useState({
    resultado: "exito_total",
    motivo_resultado: "",
    provas_determinantes: "",
    licoes_aprendidas: "",
    alimentar_rag: true,
  });
  const [gerando, setGerando] = useState(false);
  const [honModal, setHonModal] = useState(false);
  const [honLoading, setHonLoading] = useState(false);
  const [honDesc, setHonDesc] = useState("");
  const [honResp, setHonResp] = useState<any>(null);
  // R2 — arquivar / excluir
  const [arqModal, setArqModal] = useState(false);
  const [arqLoading, setArqLoading] = useState(false);
  const [delModal, setDelModal] = useState(false);
  const [delLoading, setDelLoading] = useState(false);
  const [delMotivo, setDelMotivo] = useState("");
  const [pendencias, setPendencias] = useState<PendenciaExclusao[] | null>(
    null,
  );
  // Exclusão restrita a administração/sócios (soft delete → Lixeira)
  const podeExcluir = ["superadmin", "admin", "socio"].includes(
    user?.role || "",
  );

  const arquivar = async () => {
    setArqLoading(true);
    try {
      await api.post(`/cases/${caso.id}/arquivar`);
      toast.success("Caso arquivado.");
      window.location.reload();
    } catch (e) {
      toast.error(detalheErro(e, "Falha ao arquivar o caso"));
      setArqLoading(false);
    }
  };

  const desarquivar = async () => {
    setArqLoading(true);
    try {
      await api.post(`/cases/${caso.id}/desarquivar`);
      toast.success("Caso desarquivado.");
      window.location.reload();
    } catch (e) {
      toast.error(detalheErro(e, "Falha ao desarquivar o caso"));
      setArqLoading(false);
    }
  };

  const excluir = async () => {
    const motivo = delMotivo.trim();
    if (motivo.length < 5) {
      toast.error("Informe o motivo da exclusão (mínimo 5 caracteres).");
      return;
    }
    setDelLoading(true);
    setPendencias(null);
    try {
      await api.delete(`/cases/${caso.id}`, { data: { motivo } });
      toast.success("Caso excluído — enviado para a Lixeira.");
      navigate("/casos");
    } catch (e: any) {
      const detail =
        e?.response?.status === 422 ? e?.response?.data?.detail : null;
      if (
        detail &&
        Array.isArray(detail.pendencias) &&
        detail.pendencias.length
      ) {
        setPendencias(detail.pendencias as PendenciaExclusao[]);
      } else {
        toast.error(detalheErro(e, "Falha ao excluir o caso"));
      }
    } finally {
      setDelLoading(false);
    }
  };

  useEffect(() => {
    api
      .get(`/cases/${caso.id}/movimentos`)
      .then((r) => setMovs(asList(r.data)))
      .catch(() => {});
  }, [caso.id]);

  const encerrar = async () => {
    setEncLoading(true);
    try {
      await api.post(`/cases/${caso.id}/encerrar`, enc);
      setEncModal(false);
      toast.error(
        "Caso encerrado. Conhecimento registrado na base institucional (precedente RAG + memória + tese).",
      );
      window.location.reload();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao encerrar");
    } finally {
      setEncLoading(false);
    }
  };

  const reabrir = async () => {
    setReabrindo(true);
    try {
      if (caso.status === "arquivado") {
        await api.post(`/cases/${caso.id}/desarquivar`);
        toast.success("Caso desarquivado.");
      } else {
        await api.patch(`/cases/${caso.id}`, { status: "ativo" });
        toast.success("Caso reaberto.");
      }
      window.location.reload();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao reabrir caso");
    } finally {
      setReabrindo(false);
    }
  };

  const arquivarCaso = async () => {
    setArchiveLoading(true);
    try {
      await api.post(`/cases/${caso.id}/arquivar`, {
        motivo: archiveReason || undefined,
      });
      setArchiveModal(false);
      toast.success("Caso arquivado com histórico preservado.");
      window.location.reload();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao arquivar caso");
    } finally {
      setArchiveLoading(false);
    }
  };

  const gerarDocs = async () => {
    setGerando(true);
    try {
      const { data } = await api.post(`/cases/${caso.id}/gerar-documentos`);
      toast.error(
        `${data.gerados?.length || 0} minuta(s) gerada(s): Procuração, Contrato de Honorários e Relatório Inicial. Veja na aba Documentos do caso.`,
      );
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao gerar documentos");
    } finally {
      setGerando(false);
    }
  };
  const sugerirHonorarios = async () => {
    setHonLoading(true);
    setHonResp(null);
    try {
      const { data } = await api.post("/ai/sugestao-honorarios", {
        area: caso.area,
        descricao: honDesc || caso.titulo,
        valor_causa: caso.valor_causa || undefined,
      });
      setHonResp(data);
    } catch (e: any) {
      setHonResp({ erro: e.response?.data?.detail || "Falha na sugestão" });
    } finally {
      setHonLoading(false);
    }
  };

  const analisarIA = async () => {
    setIaModal(true);
    setIaLoading(true);
    setIaResp(null);
    try {
      const { data } = await api.post("/ai/analisar-caso", {
        descricao_fatos: caso.descricao_fatos,
        area: caso.area,
        case_id: caso.id,
        nomes_proteger: [caso.parte_contraria].filter(Boolean),
      });
      setIaResp(data);
    } catch (e: any) {
      setIaResp({ erro: e.response?.data?.detail || "Falha na análise" });
    } finally {
      setIaLoading(false);
    }
  };

  const addMov = async () => {
    if (!novoMov.trim()) return;
    await api.post(`/cases/${caso.id}/movimentos`, {
      tipo: "nota",
      descricao: novoMov,
    });
    setNovoMov("");
    api
      .get(`/cases/${caso.id}/movimentos`)
      .then((r) => setMovs(asList(r.data)))
      .catch(() => {});
  };

  const syncDataJud = async () => {
    if (!caso.processo_principal?.numero_cnj) {
      toast.error("Adicione um processo com número CNJ antes de sincronizar.");
      return;
    }
    setSyncing(true);
    try {
      const { data } = await api.post(`/cases/${caso.id}/sincronizar-processo`);
      toast.success(data.detail || "Dados sincronizados com DataJud.");
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao sincronizar");
    } finally {
      setSyncing(false);
    }
  };

  // #R8 — conversão em judicial passa pelo checklist bloqueante (ConversaoChecklist)
  const [convModal, setConvModal] = useState(false);

  const casoEncerrado =
    caso.status === "encerrado" || caso.status === "arquivado";

  return (
    <div className="space-y-5">
      {casoEncerrado && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
          <p className="text-sm text-amber-800">
            Este caso está{" "}
            <strong>
              {caso.status === "arquivado" ? "arquivado" : "encerrado"}
            </strong>
            . Edições e novos lançamentos estão bloqueados enquanto ele não for
            reaberto.
          </p>
          <button
            onClick={reabrir}
            disabled={reabrindo}
            className="btn-secondary flex items-center gap-1 whitespace-nowrap border-amber-300 text-amber-800"
          >
            {caso.status === "arquivado" ? (
              <ArchiveRestore
                size={14}
                className={reabrindo ? "animate-spin" : ""}
              />
            ) : (
              <RefreshCw
                size={14}
                className={reabrindo ? "animate-spin" : ""}
              />
            )}
            {reabrindo
              ? "Reabrindo..."
              : caso.status === "arquivado"
                ? "Desarquivar caso"
                : "Reabrir caso"}
          </button>
        </div>
      )}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={analisarIA}
          className="btn-primary flex items-center gap-1"
        >
          <Sparkles size={14} /> Análise IA
        </button>
        <button
          onClick={syncDataJud}
          disabled={syncing}
          className="btn-secondary flex items-center gap-1"
        >
          <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
          {syncing ? "Consultando..." : "Sincronizar DataJud"}
        </button>
        <button
          onClick={gerarDocs}
          disabled={gerando}
          className="btn-secondary flex items-center gap-1"
        >
          📄 {gerando ? "Gerando..." : "Gerar documentos"}
        </button>
        <button
          onClick={() => {
            setHonDesc(caso.titulo);
            setHonResp(null);
            setHonModal(true);
          }}
          className="btn-secondary flex items-center gap-1"
        >
          💰 Honorários (OAB)
        </button>
        {caso.status !== "encerrado" && caso.status !== "arquivado" && (
          <button
            onClick={() => setEncModal(true)}
            className="btn-secondary flex items-center gap-1"
          >
            ✓ Encerrar caso
          </button>
        )}
        {caso.status !== "arquivado" ? (
          <button
            onClick={() => setArqModal(true)}
            className="btn-secondary flex items-center gap-1"
          >
            🗄️ Arquivar
          </button>
        ) : (
          <button
            onClick={desarquivar}
            disabled={arqLoading}
            className="btn-secondary flex items-center gap-1"
          >
            🗄️ {arqLoading ? "Desarquivando..." : "Desarquivar"}
          </button>
        )}
        {podeExcluir && (
          <button
            onClick={() => {
              setDelMotivo("");
              setPendencias(null);
              setDelModal(true);
            }}
            className="btn-secondary flex items-center gap-1 text-danger-600 border-danger-200 hover:bg-danger-50"
          >
            🗑️ Excluir
          </button>
        )}
        <button
          onClick={() => navigate(`/casos/${caso.id}/sala-de-guerra`)}
          className="btn-secondary flex items-center gap-1"
        >
          ⚔️ Sala de Guerra
        </button>
        <ExtratoCaso caso={caso} />
        {(caso as any).case_type === "extrajudicial" &&
          !(caso as any).linked_judicial_case_id && (
            <button
              onClick={() => setConvModal(true)}
              className="btn-secondary flex items-center gap-1 text-primary-700 border-primary-200"
            >
              ⚖️ Converter em processo judicial
            </button>
          )}
        {(caso as any).linked_judicial_case_id && (
          <button
            onClick={() =>
              navigate(`/casos/${(caso as any).linked_judicial_case_id}`)
            }
            className="btn-secondary flex items-center gap-1 text-primary-700 border-primary-200"
          >
            🔗 Ver caso vinculado
          </button>
        )}
      </div>

      <Modal
        open={archiveModal}
        onClose={() => setArchiveModal(false)}
        title="Arquivar caso"
      >
        <div className="space-y-4">
          <p className="text-sm text-slate-600">
            O caso sairá da lista de ativos, mas o histórico, documentos,
            prazos, financeiro e registros de IA continuam preservados.
          </p>
          <div>
            <label className="label">Motivo do arquivamento</label>
            <textarea
              className="input min-h-[96px]"
              value={archiveReason}
              onChange={(e) => setArchiveReason(e.target.value)}
              placeholder="Opcional"
            />
          </div>
          <div className="flex justify-end gap-2">
            <button
              className="btn-secondary"
              onClick={() => setArchiveModal(false)}
            >
              Cancelar
            </button>
            <button
              className="btn-primary"
              disabled={archiveLoading}
              onClick={arquivarCaso}
            >
              {archiveLoading ? "Arquivando..." : "Arquivar caso"}
            </button>
          </div>
        </div>
      </Modal>

      <AreasCaso caso={caso} />

      <div className="grid lg:grid-cols-2 gap-5">
        <div className="card p-5">
          <h3 className="font-semibold mb-3 text-sm text-slate-500 uppercase tracking-wide">
            Dados do Processo
          </h3>
          <div className="grid grid-cols-2 gap-y-2 gap-x-4 text-sm">
            <div>
              <span className="text-slate-400">Área:</span>{" "}
              <span className="capitalize ml-1">{caso.area}</span>
            </div>
            <div>
              <span className="text-slate-400">Status:</span>{" "}
              <StatusBadge value={caso.status} />
            </div>
            <div>
              <span className="text-slate-400">Fase:</span>{" "}
              <span className="capitalize ml-1">
                {caso.fase?.replace(/_/g, " ")}
              </span>
            </div>
            <div>
              <span className="text-slate-400">Prioridade:</span>{" "}
              <span className="capitalize ml-1">{caso.prioridade}</span>
            </div>
            <div>
              <span className="text-slate-400">Parte contrária:</span>{" "}
              <span className="ml-1">{caso.parte_contraria || "—"}</span>
            </div>
            {["superadmin", "admin", "socio", "advogado"].includes(
              user?.role || "",
            ) && (
              <div>
                <span className="text-slate-400">Valor:</span>{" "}
                <span className="ml-1">{fmtMoney(caso.valor_causa)}</span>
              </div>
            )}
            {caso.comarca && (
              <div>
                <span className="text-slate-400">Comarca/Vara:</span>{" "}
                <span className="ml-1">
                  {caso.comarca} {caso.vara && `· ${caso.vara}`}
                </span>
              </div>
            )}
            {caso.data_prescricao && (
              <div className="text-danger-700 font-medium">
                <span className="text-slate-400">Prescrição:</span>{" "}
                <span className="ml-1">{fmtDate(caso.data_prescricao)}</span>
              </div>
            )}
          </div>
        </div>

        <div className="card p-5">
          <h3 className="font-semibold mb-3 text-sm text-slate-500 uppercase tracking-wide">
            Timeline Recente
          </h3>
          <div className="text-sm text-slate-400 mb-2">
            <input
              value={novoMov}
              onChange={(e) => setNovoMov(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addMov()}
              placeholder="Nova anotação... (Enter para salvar)"
              className="input w-full text-xs"
            />
          </div>
          <div className="max-h-40 overflow-auto divide-y divide-slate-100">
            {movs.map((e) => (
              <div key={e.id} className="py-1.5 flex justify-between text-xs">
                <span className="text-slate-600">{e.descricao}</span>
                <span className="text-slate-400 ml-2 shrink-0">
                  {fmtDate(e.created_at)}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {caso.descricao_fatos && (
        <div className="card p-5">
          <h3 className="font-semibold mb-2 text-sm text-slate-500">
            Descrição dos Fatos
          </h3>
          <p className="text-sm text-slate-700 leading-relaxed">
            {caso.descricao_fatos}
          </p>
        </div>
      )}

      {/* Intake — Análise Completa (IA): área, teses, estratégia, honorários e módulos */}
      <IntakeAnalise caseId={caso.id} />

      {(caso as any).tese_principal && (
        <div className="grid lg:grid-cols-2 gap-5">
          {(caso as any).tese_principal && (
            <div className="card p-5">
              <h3 className="font-semibold mb-2 text-sm text-green-600">
                Pontos Fortes
              </h3>
              <p className="text-sm text-slate-700">
                {(caso as any).pontos_fortes}
              </p>
            </div>
          )}
          {(caso as any).pontos_fracos && (
            <div className="card p-5">
              <h3 className="font-semibold mb-2 text-sm text-danger-600">
                Pontos de Atenção
              </h3>
              <p className="text-sm text-slate-700">
                {(caso as any).pontos_fracos}
              </p>
            </div>
          )}
        </div>
      )}

      {iaModal && (
        <Modal
          open={iaModal}
          onClose={() => setIaModal(false)}
          title="Análise de IA — EJC Núcleo Cognitivo"
        >
          {iaLoading ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : iaResp?.erro ? (
            <p className="text-danger-600">{iaResp.erro}</p>
          ) : (
            <div className="space-y-3 text-sm">
              {iaResp?.analise && (
                <p className="text-slate-700 leading-relaxed">
                  {iaResp.analise}
                </p>
              )}
              {iaResp?.pontos_fortes?.length > 0 && (
                <div>
                  <p className="font-semibold text-green-700 mb-1">
                    Pontos Fortes
                  </p>
                  <ul className="list-disc pl-4 space-y-0.5">
                    {iaResp.pontos_fortes.map((p: string, i: number) => (
                      <li key={i}>{p}</li>
                    ))}
                  </ul>
                </div>
              )}
              {iaResp?.pontos_fracos?.length > 0 && (
                <div>
                  <p className="font-semibold text-danger-700 mb-1">
                    Pontos de Atenção
                  </p>
                  <ul className="list-disc pl-4 space-y-0.5">
                    {iaResp.pontos_fracos.map((p: string, i: number) => (
                      <li key={i}>{p}</li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="text-xs text-warn-600 border-t pt-2">
                ⚠️ Rascunho gerado por IA — revisão humana obrigatória (OAB)
              </p>
            </div>
          )}
        </Modal>
      )}

      {encModal && (
        <Modal
          open={encModal}
          onClose={() => setEncModal(false)}
          title="Encerrar caso — Pós-Mortem"
        >
          <div className="space-y-3">
            <p className="text-xs text-slate-500">
              Ao encerrar, o conhecimento do caso vira ativo institucional:{" "}
              <b>precedente na RAG</b> + <b>memória institucional</b> +{" "}
              <b>tese no banco</b>. Tudo como rascunho revisável (OAB).
            </p>
            <div>
              <label className="label">Resultado</label>
              <select
                className="input w-full"
                value={enc.resultado}
                onChange={(e) => setEnc({ ...enc, resultado: e.target.value })}
              >
                <option value="exito_total">Êxito total</option>
                <option value="exito_parcial">Êxito parcial</option>
                <option value="acordo">Acordo</option>
                <option value="improcedente">Improcedente</option>
              </select>
            </div>
            <div>
              <label className="label">Motivo do resultado</label>
              <textarea
                rows={2}
                className="input w-full"
                value={enc.motivo_resultado}
                onChange={(e) =>
                  setEnc({ ...enc, motivo_resultado: e.target.value })
                }
              />
            </div>
            <div>
              <label className="label">Provas determinantes</label>
              <textarea
                rows={2}
                className="input w-full"
                value={enc.provas_determinantes}
                onChange={(e) =>
                  setEnc({ ...enc, provas_determinantes: e.target.value })
                }
              />
            </div>
            <div>
              <label className="label">Lições aprendidas</label>
              <textarea
                rows={2}
                className="input w-full"
                value={enc.licoes_aprendidas}
                onChange={(e) =>
                  setEnc({ ...enc, licoes_aprendidas: e.target.value })
                }
              />
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={enc.alimentar_rag}
                onChange={(e) =>
                  setEnc({ ...enc, alimentar_rag: e.target.checked })
                }
              />
              Alimentar a base de conhecimento (RAG)
            </label>
            <button
              onClick={encerrar}
              disabled={encLoading}
              className="btn-primary w-full"
            >
              {encLoading ? "Encerrando..." : "Confirmar encerramento"}
            </button>
          </div>
        </Modal>
      )}

      {honModal && (
        <Modal
          open={honModal}
          onClose={() => setHonModal(false)}
          title="Sugestão de honorários — Tabela OAB/MG"
        >
          <div className="space-y-3">
            <div>
              <label className="label">Serviço / ato</label>
              <input
                className="input w-full"
                value={honDesc}
                onChange={(e) => setHonDesc(e.target.value)}
              />
            </div>
            <p className="text-xs text-slate-400">
              Área: <span className="capitalize">{caso.area}</span> · Valor da
              causa: {fmtMoney(caso.valor_causa)}
            </p>
            <button
              onClick={sugerirHonorarios}
              disabled={honLoading}
              className="btn-primary w-full"
            >
              {honLoading ? "Consultando a tabela…" : "Sugerir honorários"}
            </button>
            {honResp?.erro && (
              <p className="text-sm text-danger-600">{honResp.erro}</p>
            )}
            {honResp?.sugestao && (
              <div className="text-sm space-y-1.5 border-t border-bronze-pale pt-3">
                <div>
                  <span className="text-slate-400">Mínimo OAB:</span>{" "}
                  <b className="text-navy">
                    {honResp.sugestao.honorario_minimo_oab}
                  </b>
                </div>
                <div>
                  <span className="text-slate-400">Recomendado:</span>{" "}
                  <b className="text-navy">
                    {honResp.sugestao.honorario_recomendado}
                  </b>
                </div>
                <div>
                  <span className="text-slate-400">Êxito:</span>{" "}
                  <b className="text-navy">
                    {honResp.sugestao.percentual_exito}
                  </b>
                </div>
                {honResp.sugestao.fundamento && (
                  <p className="text-xs text-slate-500">
                    {honResp.sugestao.fundamento}
                  </p>
                )}
                <p className="text-xs text-warn-600">{honResp.aviso}</p>
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* R2 — Arquivar (confirmação simples) */}
      <ConfirmModal
        open={arqModal}
        onClose={() => setArqModal(false)}
        onConfirm={arquivar}
        variant="primary"
        title="Arquivar caso"
        message="O caso sai das listagens ativas, mas nada é apagado. Ele fica disponível na aba Arquivados e pode ser desarquivado a qualquer momento."
        confirmLabel="Arquivar"
        loading={arqLoading}
      />

      {/* R2 — Excluir (confirmação forte: digitar EXCLUIR + motivo ≥ 5 chars) */}
      <ConfirmModal
        open={delModal}
        onClose={() => {
          setDelModal(false);
          setPendencias(null);
        }}
        onConfirm={excluir}
        variant="danger"
        title="Excluir caso"
        message={`Esta ação envia o caso "${caso.titulo}" para a Lixeira e fica registrada na Auditoria com o motivo informado.`}
        typeToConfirm="EXCLUIR"
        confirmLabel="Excluir caso"
        loading={delLoading}
      >
        <div className="mt-3">
          <FieldLabel required>
            Motivo da exclusão (mínimo 5 caracteres)
          </FieldLabel>
          <Textarea
            value={delMotivo}
            onChange={(e) => setDelMotivo(e.target.value)}
            rows={3}
            placeholder="Ex.: caso duplicado, cadastro de teste..."
          />
        </div>
        {pendencias && pendencias.length > 0 && (
          <Alert
            variant="danger"
            title="Pendências impedem a exclusão"
            className="mt-3"
          >
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              {pendencias.map((p, i) => (
                <li key={`${p.tipo}-${p.id ?? i}`}>
                  <span className="capitalize">
                    {String(p.tipo).replace(/_/g, " ")}
                  </span>
                  {p.descricao ? ` — ${p.descricao}` : ""}
                </li>
              ))}
            </ul>
            <button
              type="button"
              onClick={() => {
                setDelModal(false);
                setPendencias(null);
                arquivar();
              }}
              disabled={arqLoading}
              className="btn-secondary mt-3 flex items-center gap-1 text-xs"
            >
              🗄️ Arquivar em vez disso
            </button>
          </Alert>
        )}
      </ConfirmModal>

      {/* #R8 — Checklist bloqueante de conversão extrajudicial → judicial */}
      <ConversaoChecklist
        caseId={caso.id}
        open={convModal}
        onClose={() => setConvModal(false)}
        onSuccess={() => {
          setTimeout(() => {
            window.location.assign(`/casos/${caso.id}?tab=processos`);
          }, 700);
        }}
      />
    </div>
  );
}

// ── Tab: Timeline completa ───────────────────────────────────────────────────
function TabTimeline({ caseId }: { caseId: string }) {
  const [ts, setTs] = useState<any[]>([]);
  const [tsForm, setTsForm] = useState({ descricao: "", horas: 1 });
  const [showTsForm, setShowTsForm] = useState(false);

  useEffect(() => {
    api
      .get(`/timesheet/casos/${caseId}`)
      .then((r) => setTs(asList(r.data)))
      .catch(() => setTs([]));
  }, [caseId]);

  const addTimesheet = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.post("/timesheet", { case_id: caseId, ...tsForm });
    setShowTsForm(false);
    api
      .get(`/timesheet/casos/${caseId}`)
      .then((r) => setTs(asList(r.data)))
      .catch(() => setTs([]));
  };

  const totalHoras = ts.reduce((a, t) => a + (t.minutos ?? 0) / 60, 0);

  return (
    <div className="space-y-6">
      <LinhaDoTempoProcessual caseId={caseId} />

      <div>
        <div className="flex justify-between items-center mb-3">
          <h3 className="font-semibold text-sm text-gray-500 uppercase">
            Timesheet ({totalHoras.toFixed(1)}h registradas)
          </h3>
          <button
            onClick={() => setShowTsForm(!showTsForm)}
            className="btn-secondary text-xs"
          >
            + Lançar horas
          </button>
        </div>
        {showTsForm && (
          <form onSubmit={addTimesheet} className="card p-4 space-y-3 mb-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="label">Atividade</label>
                <input
                  required
                  value={tsForm.descricao}
                  onChange={(e) =>
                    setTsForm((f) => ({ ...f, descricao: e.target.value }))
                  }
                  placeholder="Ex: Elaboração de petição..."
                  className="input w-full text-sm"
                />
              </div>
              <div>
                <label className="label">Horas</label>
                <input
                  type="number"
                  step="0.5"
                  min="0.5"
                  value={tsForm.horas}
                  onChange={(e) =>
                    setTsForm((f) => ({
                      ...f,
                      horas: parseFloat(e.target.value),
                    }))
                  }
                  className="input w-full text-sm"
                />
              </div>
            </div>
            <div className="flex gap-2">
              <button type="submit" className="btn-primary text-sm">
                Salvar
              </button>
              <button
                type="button"
                onClick={() => setShowTsForm(false)}
                className="btn-secondary text-sm"
              >
                Cancelar
              </button>
            </div>
          </form>
        )}
        <div className="space-y-2">
          {ts.map((t, i) => (
            <div
              key={t.id ?? i}
              className="card p-3 flex flex-wrap justify-between items-center gap-2 text-sm"
            >
              <span className="min-w-0 flex-1 break-words text-gray-700">
                {t.descricao}
              </span>
              <div className="flex items-center gap-3 shrink-0">
                <span className="text-gray-400 text-xs">{fmtDate(t.data)}</span>
                <span className="font-mono font-semibold text-primary-600">
                  {((t.minutos ?? 0) / 60).toFixed(1)}h
                </span>
              </div>
            </div>
          ))}
          {ts.length === 0 && !showTsForm && (
  <Empty message="Nenhuma hora lançada" />
          )}
        </div>
      </div>
    </div>
  );
}

// ── Tab: Partes ──────────────────────────────────────────────────────────────
// ── Tab: Checklists (estáticos + por legislação via IA · HITL) ───────────────
function TabChecklists({ caseId }: { caseId: string }) {
  const [cks, setCks] = useState<any[]>([]);
  const [gatilho, setGatilho] = useState("pre_protocolo");
  const [gerando, setGerando] = useState(false);
  const carregar = () =>
    api
      .get(`/checklists/casos/${caseId}`)
      .then((r) => setCks(r.data ?? []))
      .catch(() => {});
  useEffect(() => {
    carregar();
  }, [caseId]);

  const gerarIA = async () => {
    setGerando(true);
    try {
      await api.post(`/checklists/caso/${caseId}/gerar-ia`, { gatilho });
      toast.success("Checklist gerado por legislação (rascunho — revise).");
      carregar();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao gerar");
    } finally {
      setGerando(false);
    }
  };

  const marcar = async (ckId: string, itemId: string, concluido: boolean) => {
    try {
      await api.patch(`/checklists/${ckId}/itens/${itemId}/marcar`, {
        concluido,
      });
      carregar();
    } catch {
      /* noop */
    }
  };

  const CAT_COR: Record<string, string> = {
    documentos: "bg-primary-100 text-primary-700",
    diligencias: "bg-warn-100 text-warn-700",
    prazos: "bg-danger-100 text-danger-700",
    audiencia: "bg-ai-100 text-ai-700",
    financeiro: "bg-green-100 text-green-700",
    comunicacao: "bg-cyan-100 text-cyan-700",
    outros: "bg-slate-100 text-slate-600",
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center flex-wrap gap-2">
        <div>
          <h2 className="font-semibold">Checklists do caso</h2>
          <p className="text-xs text-gray-400">
            Providências por área e legislação pertinente. Rascunho de IA —
            revisão humana obrigatória (OAB); não cria prazos.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={gatilho}
            onChange={(e) => setGatilho(e.target.value)}
            className="input text-sm py-1"
          >
            <option value="pre_processo">Antes de virar processo</option>
            <option value="pre_protocolo">Antes do protocolo</option>
            <option value="geral">Geral</option>
          </select>
          <button
            onClick={gerarIA}
            disabled={gerando}
            className="btn-primary text-sm flex items-center gap-1"
          >
            <Sparkles size={14} />{" "}
            {gerando ? "Gerando…" : "Gerar por legislação (IA)"}
          </button>
        </div>
      </div>

      {cks.length === 0 && (
        <Empty message="Nenhum checklist neste caso. Gere um por legislação acima." />
      )}

      {cks.map((ck) => (
        <div key={ck.id} className="card p-4">
          <div className="flex justify-between items-center mb-2">
            <h3 className="font-medium text-sm">{ck.nome}</h3>
            <span className="text-xs text-gray-400">
              {ck.itens_ok}/{ck.total_itens} · {ck.progresso_pct}%
            </span>
          </div>
          <div className="w-full h-1.5 bg-gray-100 rounded-full mb-3 overflow-hidden">
            <div
              className="h-full bg-green-500"
              style={{ width: `${ck.progresso_pct || 0}%` }}
            />
          </div>
          <ul className="space-y-1.5">
            {(ck.itens || []).map((i: any) => (
              <li key={i.id} className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={!!i.concluido}
                  onChange={(e) => marcar(ck.id, i.id, e.target.checked)}
                  className="mt-1"
                />
                <span className="flex-1">
                  <span
                    className={i.concluido ? "line-through text-gray-400" : ""}
                  >
                    {i.texto}
                  </span>
                  {i.obrigatorio && (
                    <span className="text-[10px] text-danger-500 ml-1">*</span>
                  )}
                  <span
                    className={`ml-2 text-[10px] px-1.5 py-0.5 rounded-full ${CAT_COR[i.categoria] || "bg-slate-100 text-slate-600"}`}
                  >
                    {i.categoria}
                  </span>
                  {i.dica && (
                    <span className="block text-xs text-gray-400">
                      {i.dica}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

// ── Tab: Processos (entidade Processo — 1 Caso : N Processos) ─────────────────
function TabProcessos({ caseId }: { caseId: string }) {
  const [procs, setProcs] = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [arquivo, setArquivo] = useState<"ativos" | "arquivados" | "todos">(
    "ativos",
  );
  const vazio = {
    tipo: "judicial",
    numero_cnj: "",
    instancia: "",
    tribunal: "",
    comarca: "",
    vara: "",
    fase: "",
    valor_causa: "",
  };
  const [form, setForm] = useState<any>(vazio);
  const TIPOS: Record<string, string> = {
    judicial: "Judicial",
    recurso: "Recurso",
    cautelar: "Cautelar",
    execucao: "Execução",
    administrativo: "Administrativo",
    extrajudicial: "Extrajudicial",
  };
  const TIPO_COR: Record<string, string> = {
    judicial: "bg-primary-100 text-primary-700",
    recurso: "bg-ai-100 text-ai-700",
    cautelar: "bg-warn-100 text-warn-700",
    execucao: "bg-danger-100 text-danger-700",
    administrativo: "bg-cyan-100 text-cyan-700",
    extrajudicial: "bg-slate-100 text-slate-600",
  };
  const carregar = () =>
    api
      .get(`/cases/${caseId}/processes`, { params: { arquivo } })
      .then((r) => setProcs(asList(r.data)))
      .catch(() => {});
  useEffect(() => {
    carregar();
  }, [caseId, arquivo]);

  const salvar = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post(`/cases/${caseId}/processes`, {
        ...form,
        valor_causa: form.valor_causa ? Number(form.valor_causa) : null,
      });
      setForm(vazio);
      setShowForm(false);
      carregar();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Falha ao criar processo");
    } finally {
      setSaving(false);
    }
  };
  const remover = async (pid: string) => {
    if (!confirm("Remover este processo?")) return;
    try {
      await api.delete(`/processes/${pid}`);
      carregar();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Falha ao remover");
    }
  };
  const arquivar = async (pid: string) => {
    const motivo = prompt("Motivo do arquivamento (opcional)") || "";
    try {
      await api.post(`/processes/${pid}/arquivar`, {
        motivo: motivo || undefined,
      });
      toast.success("Processo arquivado.");
      carregar();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Falha ao arquivar");
    }
  };
  const desarquivar = async (pid: string) => {
    try {
      await api.post(`/processes/${pid}/desarquivar`);
      toast.success("Processo desarquivado.");
      carregar();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Falha ao desarquivar");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="font-semibold">Processos do caso</h2>
          <p className="text-xs text-gray-400">
            Um caso pode ter múltiplos processos (principal, recurso, cautelar,
            execução) — inclusive em tribunais distintos.
          </p>
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <div className="flex rounded-lg overflow-hidden bg-slate-900/[0.05] dark:bg-white/[0.07]">
            {[
              ["ativos", "Ativos"],
              ["arquivados", "Arquivados"],
              ["todos", "Todos"],
            ].map(([k, label]) => (
              <button
                key={k}
                onClick={() => setArquivo(k as typeof arquivo)}
                className={`px-3 py-1.5 text-xs font-medium ${arquivo === k ? "bg-navy text-white" : "text-slate-600 hover:bg-slate-900/[0.09] dark:text-slate-300 dark:hover:bg-white/[0.12]"}`}
              >
                {label}
              </button>
            ))}
          </div>
          <button
            onClick={() => setShowForm(!showForm)}
            className="btn-primary text-sm"
          >
            + Processo
          </button>
        </div>
      </div>

      {showForm && (
        <form onSubmit={salvar} className="card p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <label className="label">Tipo</label>
              <select
                value={form.tipo}
                onChange={(e) =>
                  setForm((f: any) => ({ ...f, tipo: e.target.value }))
                }
                className="input w-full"
              >
                {Object.entries(TIPOS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Nº CNJ</label>
              <input
                value={form.numero_cnj}
                onChange={(e) =>
                  setForm((f: any) => ({ ...f, numero_cnj: e.target.value }))
                }
                className="input w-full"
                placeholder="0000000-00.0000.0.00.0000"
              />
            </div>
            <div>
              <label className="label">Instância</label>
              <input
                value={form.instancia}
                onChange={(e) =>
                  setForm((f: any) => ({ ...f, instancia: e.target.value }))
                }
                className="input w-full"
                placeholder="1ª / 2ª / STJ"
              />
            </div>
            <div>
              <label className="label">Fase</label>
              <input
                value={form.fase}
                onChange={(e) =>
                  setForm((f: any) => ({ ...f, fase: e.target.value }))
                }
                className="input w-full"
                placeholder="Conhecimento / Recursal"
              />
            </div>
            <div>
              <label className="label">Tribunal</label>
              <input
                value={form.tribunal}
                onChange={(e) =>
                  setForm((f: any) => ({ ...f, tribunal: e.target.value }))
                }
                className="input w-full"
              />
            </div>
            <div>
              <label className="label">Comarca</label>
              <input
                value={form.comarca}
                onChange={(e) =>
                  setForm((f: any) => ({ ...f, comarca: e.target.value }))
                }
                className="input w-full"
              />
            </div>
            <div>
              <label className="label">Vara</label>
              <input
                value={form.vara}
                onChange={(e) =>
                  setForm((f: any) => ({ ...f, vara: e.target.value }))
                }
                className="input w-full"
              />
            </div>
            <div>
              <label className="label">Valor da causa</label>
              <input
                type="number"
                step="0.01"
                value={form.valor_causa}
                onChange={(e) =>
                  setForm((f: any) => ({ ...f, valor_causa: e.target.value }))
                }
                className="input w-full"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={saving}
              className="btn-primary text-sm"
            >
              {saving ? "Salvando…" : "Salvar"}
            </button>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="btn-secondary text-sm"
            >
              Cancelar
            </button>
          </div>
        </form>
      )}

      <div className="space-y-2">
        {procs.map((p) => (
          <div key={p.id} className="card p-4">
            <div className="flex justify-between items-start gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <span
                    className={`text-xs font-semibold px-2 py-0.5 rounded-full ${TIPO_COR[p.tipo] || "bg-slate-100 text-slate-600"}`}
                  >
                    {TIPOS[p.tipo] || p.tipo}
                  </span>
                  <span className="font-medium text-sm">
                    {p.numero_cnj || "(sem número)"}
                  </span>
                  <StatusBadge value={p.status || "ativo"} />
                  {p.instancia && (
                    <span className="text-xs text-gray-500">
                      · {p.instancia} instância
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-600">
                  {[p.tribunal, p.comarca, p.vara]
                    .filter(Boolean)
                    .join(" · ") || "—"}
                  {p.fase ? ` · fase: ${p.fase}` : ""}
                </p>
                {p.valor_causa != null && (
                  <p className="text-xs text-gray-400 mt-0.5">
                    Valor da causa: {fmtMoney(p.valor_causa)}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                {p.status === "arquivado" ? (
                  <button
                    onClick={() => desarquivar(p.id)}
                    className="text-blue-600 hover:text-blue-800 text-xs"
                  >
                    Desarquivar
                  </button>
                ) : (
                  <button
                    onClick={() => arquivar(p.id)}
                    className="text-slate-500 hover:text-slate-800 text-xs"
                  >
                    Arquivar
                  </button>
                )}
                <button
                  onClick={() => remover(p.id)}
                  className="text-red-400 hover:text-red-600 text-xs"
                >
                  Remover
                </button>
              </div>
            </div>
          </div>
        ))}
        {procs.length === 0 && !showForm && (
          <Empty message="Nenhum processo cadastrado neste caso ainda." />
        )}
      </div>
    </div>
  );
}

function TabPartes({ caseId }: { caseId: string }) {
  const [partes, setPartes] = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    tipo: "autor",
    nome: "",
    cpf_cnpj: "",
    email: "",
    telefone: "",
    representante_legal: "",
    oab: "",
  });
  const TIPOS: Record<string, string> = {
    autor: "Autor",
    reu: "Réu",
    terceiro_interessado: "Terceiro",
    litisconsorte_ativo: "Litisconsorte Ativo",
    litisconsorte_passivo: "Litisconsorte Passivo",
    assistente: "Assistente",
    amicus_curiae: "Amicus Curiae",
    mp: "MP",
    perito: "Perito",
  };

  useEffect(() => {
    api
      .get(`/cases/${caseId}/partes`)
      .then((r) => setPartes(asList(r.data)))
      .catch(() => {});
  }, [caseId]);

  const salvar = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.post(`/cases/${caseId}/partes`, form);
    setShowForm(false);
    api
      .get(`/cases/${caseId}/partes`)
      .then((r) => setPartes(asList(r.data)))
      .catch(() => {});
  };

  const remover = async (id: string) => {
    if (!confirm("Remover esta parte?")) return;
    try {
      await api.delete(`/cases/${caseId}/partes/${id}`);
      setPartes((p) => p.filter((x) => x.id !== id));
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao remover parte");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="font-semibold text-gray-900">
          Partes Processuais ({partes.length})
        </h2>
        <button
          onClick={() => setShowForm(!showForm)}
          className="btn-primary text-sm"
        >
          + Adicionar
        </button>
      </div>
      {showForm && (
        <form onSubmit={salvar} className="card p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <label className="label">Tipo</label>
              <select
                value={form.tipo}
                onChange={(e) =>
                  setForm((f) => ({ ...f, tipo: e.target.value }))
                }
                className="input w-full"
              >
                {Object.entries(TIPOS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Nome *</label>
              <input
                required
                value={form.nome}
                onChange={(e) =>
                  setForm((f) => ({ ...f, nome: e.target.value }))
                }
                className="input w-full"
              />
            </div>
            <div>
              <label className="label">CPF/CNPJ</label>
              <input
                value={form.cpf_cnpj}
                onChange={(e) =>
                  setForm((f) => ({ ...f, cpf_cnpj: e.target.value }))
                }
                className="input w-full"
              />
            </div>
            <div>
              <label className="label">Email</label>
              <input
                type="email"
                value={form.email}
                onChange={(e) =>
                  setForm((f) => ({ ...f, email: e.target.value }))
                }
                className="input w-full"
              />
            </div>
            <div>
              <label className="label">Representante Legal</label>
              <input
                value={form.representante_legal}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    representante_legal: e.target.value,
                  }))
                }
                className="input w-full"
              />
            </div>
            <div>
              <label className="label">OAB</label>
              <input
                value={form.oab}
                onChange={(e) =>
                  setForm((f) => ({ ...f, oab: e.target.value }))
                }
                className="input w-full"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <button type="submit" className="btn-primary text-sm">
              Salvar
            </button>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="btn-secondary text-sm"
            >
              Cancelar
            </button>
          </div>
        </form>
      )}
      <div className="space-y-2">
        {partes.map((p) => (
          <div key={p.id} className="card p-4 flex justify-between items-start">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="font-medium text-sm">{p.nome}</span>
                <span className="text-xs bg-primary-100 text-primary-700 px-2 py-0.5 rounded-full">
                  {TIPOS[p.tipo] || p.tipo}
                </span>
              </div>
              <div className="text-xs text-gray-500 flex flex-wrap gap-x-3">
                {p.cpf_cnpj && <span>{p.cpf_cnpj}</span>}
                {p.email && <span>{p.email}</span>}
                {p.representante_legal && (
                  <span>
                    Adv: {p.representante_legal}
                    {p.oab ? ` (OAB ${p.oab})` : ""}
                  </span>
                )}
              </div>
            </div>
            <button
              onClick={() => remover(p.id)}
              className="text-danger-400 hover:text-danger-600 text-xs ml-4"
            >
              Remover
            </button>
          </div>
        ))}
        {partes.length === 0 && !showForm && (
          <Empty message="Nenhuma parte cadastrada" />
        )}
      </div>
    </div>
  );
}

// ── Tab: Score Jurídico ──────────────────────────────────────────────────────
function TabScore({ caseId }: { caseId: string }) {
  const [scores, setScores] = useState<any[]>([]);
  const [calc, setCalc] = useState(false);
  const DIMS = [
    { k: "pedido", l: "Pedido", max: 15 },
    { k: "causa_de_pedir", l: "Causa de Pedir", max: 15 },
    { k: "fundamentacao", l: "Fundamentação", max: 20 },
    { k: "provas", l: "Provas", max: 20 },
    { k: "jurisprudencia", l: "Jurisprudência", max: 15 },
    { k: "documentos_obrigatorios", l: "Documentos Obrigatórios", max: 10 },
    { k: "conformidade_formal", l: "Conformidade Formal", max: 5 },
  ];

  useEffect(() => {
    api
      .get(`/cases/${caseId}/score-juridico`)
      .then((r) => setScores(r.data))
      .catch(() => {});
  }, [caseId]);

  const calcular = async () => {
    setCalc(true);
    try {
      await api.post(`/cases/${caseId}/score-juridico/calcular`);
      api
        .get(`/cases/${caseId}/score-juridico`)
        .then((r) => setScores(r.data))
        .catch(() => {});
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha no cálculo");
    } finally {
      setCalc(false);
    }
  };

  const top = scores[0];
  const getBarColor = (pct: number) =>
    pct >= 80
      ? "bg-green-500"
      : pct >= 60
        ? "bg-primary-500"
        : pct >= 40
          ? "bg-yellow-500"
          : "bg-danger-500";
  const getLabel = (t: number) =>
    t >= 80
      ? { l: "Excelente", c: "text-green-600" }
      : t >= 60
        ? { l: "Bom", c: "text-primary-600" }
        : t >= 40
          ? { l: "Regular", c: "text-yellow-600" }
          : { l: "Fraco", c: "text-danger-600" };

  return (
    <div className="space-y-5">
      <div className="flex justify-between items-center">
        <h2 className="font-semibold">Score Jurídico</h2>
        <button
          onClick={calcular}
          disabled={calc}
          className="btn-primary flex items-center gap-1 text-sm"
        >
          {calc ? (
            <>
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin inline-block" />
              Calculando...
            </>
          ) : (
            "⚡ Calcular com IA"
          )}
        </button>
      </div>
      {top ? (
        <>
          <div className="card p-5">
            <div className="flex items-start gap-6 mb-4">
              <div className="text-center min-w-[80px]">
                <div className="text-5xl font-black text-gray-900">
                  {top.total}
                </div>
                <div className="text-sm text-gray-400">/100</div>
                <div
                  className={`text-sm font-semibold mt-1 ${getLabel(top.total).c}`}
                >
                  {getLabel(top.total).l}
                </div>
              </div>
              <div className="flex-1 space-y-2">
                {DIMS.map((d) => {
                  const v = Number(top[d.k] ?? 0);
                  const pct = Math.round((v / d.max) * 100);
                  return (
                    <div key={d.k}>
                      <div className="flex justify-between text-xs mb-0.5">
                        <span className="text-gray-600">{d.l}</span>
                        <span className="text-gray-400 font-mono">
                          {v}/{d.max}
                        </span>
                      </div>
                      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${getBarColor(pct)}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
            {top.recomendacoes && (
              <div className="bg-warn-50 border border-warn-200 rounded-lg p-3 mt-3">
                <p className="text-xs font-semibold text-warn-800 mb-1">
                  Recomendações da IA
                </p>
                <ul className="space-y-0.5">
                  {(typeof top.recomendacoes === "string"
                    ? JSON.parse(top.recomendacoes)
                    : (top.recomendacoes as string[])
                  ).map((r: string, i: number) => (
                    <li key={i} className="text-xs text-warn-700">
                      • {r}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="text-xs text-warn-500 mt-2">
              ⚠️ Gerado por IA — revisão humana obrigatória
            </p>
          </div>
          {scores.length > 1 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase mb-2">
                Histórico
              </p>
              <div className="space-y-1">
                {scores.slice(1).map((s) => (
                  <div
                    key={s.id}
                    className="flex justify-between items-center p-3 card text-sm"
                  >
                    <span className="text-gray-500">
                      {fmtDate(s.created_at)}
                    </span>
                    <span className={`font-bold ${getLabel(s.total).c}`}>
                      {s.total}/100 — {getLabel(s.total).l}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="text-center py-16 text-gray-400">
          <p className="text-2xl mb-2">📊</p>
          <p>Nenhum score calculado ainda</p>
          <p className="text-xs mt-1">
            Clique em "Calcular com IA" para analisar a qualidade jurídica do
            caso
          </p>
        </div>
      )}
    </div>
  );
}

// ── Tab: Índice de Risco ─────────────────────────────────────────────────────
function TabRisco({ caseId }: { caseId: string }) {
  const [data, setData] = useState<any>(null);
  const [recalc, setRecalc] = useState(false);
  const NIVEL: Record<
    string,
    { c: string; bg: string; border: string; bar: string }
  > = {
    baixo: {
      c: "text-green-700",
      bg: "bg-green-50",
      border: "border-green-200",
      bar: "bg-green-500",
    },
    medio: {
      c: "text-yellow-700",
      bg: "bg-yellow-50",
      border: "border-yellow-200",
      bar: "bg-yellow-500",
    },
    alto: {
      c: "text-orange-700",
      bg: "bg-orange-50",
      border: "border-orange-200",
      bar: "bg-orange-500",
    },
    critico: {
      c: "text-danger-700",
      bg: "bg-danger-50",
      border: "border-danger-200",
      bar: "bg-danger-500",
    },
  };
  const FATORES: Record<string, string> = {
    prazo_vencido: "Prazo Vencido",
    audiencia_perdida: "Audiência Perdida",
    sem_documentos: "Sem Documentos",
    valor_alto: "Valor Alto (>500k)",
    valor_medio: "Valor Médio (>100k)",
    processo_antigo: "Processo Antigo (+3 anos)",
  };

  useEffect(() => {
    api
      .get(`/cases/${caseId}/indice-risco`)
      .then((r) => setData(r.data))
      .catch(() => {});
  }, [caseId]);

  const recalcular = async () => {
    setRecalc(true);
    try {
      await api.post(`/cases/${caseId}/indice-risco/recalcular`);
      api
        .get(`/cases/${caseId}/indice-risco`)
        .then((r) => setData(r.data))
        .catch(() => {});
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha no recálculo");
    } finally {
      setRecalc(false);
    }
  };

  const nivel = data?.atual?.risco_nivel as string | undefined;
  const cfg = nivel ? NIVEL[nivel] : null;
  const indice = Number(data?.atual?.indice_risco ?? 0);
  const fatores = Object.entries(data?.atual?.risco_fatores ?? {}).filter(
    ([, v]) => Boolean(v),
  );

  return (
    <div className="space-y-5">
      <MatrizRisco caseId={caseId} />
      <div className="flex justify-between items-center">
        <h2 className="font-semibold">Índice de Risco</h2>
        <button
          onClick={recalcular}
          disabled={recalc}
          className="btn-secondary text-sm"
        >
          {recalc ? "Calculando..." : "↻ Recalcular"}
        </button>
      </div>
      <div
        className={`card p-5 border ${cfg?.border ?? "border-gray-200"} ${cfg?.bg ?? ""}`}
      >
        <div className="flex items-center gap-6">
          <div className="text-center min-w-[80px]">
            <div className={`text-6xl font-black ${cfg?.c ?? "text-gray-900"}`}>
              {indice}
            </div>
            <div className="text-sm text-gray-400">/100</div>
          </div>
          <div className="flex-1">
            <div
              className={`text-xl font-bold ${cfg?.c ?? "text-gray-400"} mb-2 capitalize`}
            >
              Risco {nivel ?? "—"}
            </div>
            <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${cfg?.bar ?? "bg-gray-400"}`}
                style={{ width: `${indice}%` }}
              />
            </div>
            <div className="flex justify-between text-xs text-gray-400 mt-1">
              <span>Baixo 0–25</span>
              <span>Médio 26–50</span>
              <span>Alto 51–75</span>
              <span>Crítico 76–100</span>
            </div>
          </div>
        </div>
        {fatores.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {fatores.map(([f]) => (
              <span
                key={f}
                className="text-xs bg-white border border-orange-200 text-orange-700 px-2 py-0.5 rounded-full"
              >
                ⚠ {FATORES[f] || f}
              </span>
            ))}
          </div>
        )}
        {!nivel && (
          <p className="text-center text-gray-400 text-sm mt-2">
            Clique em "Recalcular" para calcular o índice
          </p>
        )}
      </div>
      {data?.historico?.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase mb-2">
            Histórico
          </p>
          <div className="space-y-1">
            {(data.historico as any[]).map((h, i) => (
              <div
                key={i}
                className="flex justify-between items-center p-3 card text-sm"
              >
                <span className="text-gray-500">{fmtDate(h.created_at)}</span>
                <span className={`font-bold ${NIVEL[h.nivel]?.c ?? ""}`}>
                  {h.indice} — {h.nivel}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Tab: Jurisprudência (RAG) ─────────────────────────────────────────────────
function TabJurisprudencia({ caseId, caso }: { caseId: string; caso: Case }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const buscar = async () => {
    const q = query || caso.descricao_fatos || "";
    if (!q.trim()) return;
    setLoading(true);
    setSearched(true);
    try {
      const { data } = await api.get("/rag/buscar", {
        params: { q, limite: 10 },
      });
      setResults(data?.resultados ?? []);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <h2 className="font-semibold">Jurisprudência via RAG</h2>
      <div className="flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && buscar()}
          placeholder="Buscar jurisprudência relevante para este caso..."
          className="input flex-1 text-sm"
        />
        <button
          onClick={buscar}
          disabled={loading}
          className="btn-primary text-sm"
        >
          {loading ? "Buscando..." : "🔍 Buscar"}
        </button>
      </div>
      {!searched && caso.descricao_fatos && (
        <button
          onClick={buscar}
          className="text-sm text-primary-600 hover:underline"
        >
          Buscar jurisprudência relevante automaticamente
        </button>
      )}
      <div className="space-y-3">
        {results.map((r, i) => (
          <div key={i} className="card p-4">
            <div className="flex justify-between mb-2">
              <span className="text-xs bg-primary-100 text-primary-700 px-2 py-0.5 rounded">
                {r.categoria}
              </span>
              <span className="text-xs text-gray-400">
                Relevância: {(r.score * 100).toFixed(0)}%
              </span>
            </div>
            <p className="text-sm text-gray-700 leading-relaxed">
              {r.conteudo}
            </p>
            {r.fonte && (
              <p className="text-xs text-gray-400 mt-2">Fonte: {r.fonte}</p>
            )}
          </div>
        ))}
        {searched && results.length === 0 && !loading && (
          <Empty message="Nenhum resultado encontrado para esta busca" />
        )}
        {!searched && (
          <p className="text-center py-8 text-gray-400 text-sm">
            Digite um termo para buscar jurisprudência na base de conhecimento
          </p>
        )}
      </div>
    </div>
  );
}

// ── Tab genérico: lista simples ──────────────────────────────────────────────
function TabLista({
  titulo,
  endpoint,
  renderItem,
  empty,
}: {
  titulo: string;
  endpoint: string;
  renderItem: (item: any) => JSX.Element;
  empty: string;
}) {
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => {
    api
      .get(endpoint)
      .then((r) =>
        setItems(asList(r.data)),
      )
      .catch(() => {});
  }, [endpoint]);
  return (
    <div className="space-y-4">
      <h2 className="font-semibold">
        {titulo} ({items.length})
      </h2>
      <div className="space-y-2">
        {items.map((item, i) => (
          <div key={item.id || i}>{renderItem(item)}</div>
        ))}
        {items.length === 0 && (
          <p className="text-center py-8 text-gray-400 text-sm">{empty}</p>
        )}
      </div>
    </div>
  );
}

// ── Tab: Mensagens (chat cliente↔escritório) ─────────────────────────────────
function TabMensagens({ caseId }: { caseId: string }) {
  const [msgs, setMsgs] = useState<any[]>([]);
  const [txt, setTxt] = useState("");
  const [sending, setSending] = useState(false);
  const carregar = () =>
    api
      .get(`/cases/${caseId}/mensagens`)
      .then((r) => setMsgs(asList(r.data)))
      .catch(() => {});
  useEffect(() => {
    carregar();
  }, [caseId]);
  const enviar = async () => {
    if (!txt.trim()) return;
    setSending(true);
    try {
      await api.post(`/cases/${caseId}/mensagens`, { mensagem: txt });
      setTxt("");
      carregar();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao enviar");
    } finally {
      setSending(false);
    }
  };
  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-semibold">Mensagens com o cliente</h2>
        <p className="text-xs text-gray-400">
          Conversa visível ao cliente no Portal — evite expor dados sensíveis
          desnecessários.
        </p>
      </div>
      <div className="card p-4 max-h-[28rem] overflow-auto space-y-2 bg-gray-50">
        {msgs.map((m) => (
          <div
            key={m.id}
            className={`flex ${m.autor_tipo === "escritorio" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[75%] rounded-lg px-3 py-2 text-sm ${m.autor_tipo === "escritorio" ? "bg-primary-600 text-white" : "bg-white border border-gray-200"}`}
            >
              <Markdown source={m.mensagem} />
              <p
                className={`text-[10px] mt-1 ${m.autor_tipo === "escritorio" ? "text-primary-100" : "text-gray-400"}`}
              >
                {m.autor_nome ||
                  (m.autor_tipo === "cliente" ? "Cliente" : "Escritório")}{" "}
                · {fmtDate(m.created_at)}
              </p>
            </div>
          </div>
        ))}
        {msgs.length === 0 && (
          <p className="text-center text-gray-400 text-sm py-10">
            Nenhuma mensagem ainda
          </p>
        )}
      </div>
      <div className="flex gap-2">
        <input
          value={txt}
          onChange={(e) => setTxt(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && enviar()}
          placeholder="Escreva uma mensagem ao cliente…"
          className="input flex-1"
        />
        <button
          onClick={enviar}
          disabled={sending || !txt.trim()}
          className="btn-primary"
        >
          Enviar
        </button>
      </div>
    </div>
  );
}

// ── Tab: Etiquetas ───────────────────────────────────────────────────────────
function TabEtiquetas({ caseId }: { caseId: string }) {
  const [todas, setTodas] = useState<any[]>([]);
  const [doCaso, setDoCaso] = useState<any[]>([]);
  const [nome, setNome] = useState("");
  const [cor, setCor] = useState("#AA8660");
  const CORES = [
    "#AA8660",
    "#0f1f3d",
    "#1D9E75",
    "#D85A30",
    "#E24B4A",
    "#26417a",
    "#EF9F27",
    "#7C5E40",
  ];

  const carregar = () => {
    api
      .get("/etiquetas")
      .then((r) => setTodas(r.data))
      .catch(() => {});
    api
      .get(`/cases/${caseId}/etiquetas`)
      .then((r) => setDoCaso(asList(r.data)))
      .catch(() => {});
  };
  useEffect(() => {
    carregar();
  }, [caseId]);

  const atribuir = async (id: string) => {
    await api.post(`/cases/${caseId}/etiquetas`, { etiqueta_id: id });
    carregar();
  };
  const remover = async (id: string) => {
    if (!confirm("Remover esta etiqueta do caso?")) return;
    try {
      await api.delete(`/cases/${caseId}/etiquetas/${id}`);
      setDoCaso((p) => p.filter((x) => x.id !== id));
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao remover etiqueta");
    }
  };
  const criar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!nome.trim()) return;
    const { data } = await api.post("/etiquetas", { nome, cor });
    setNome("");
    await api.post(`/cases/${caseId}/etiquetas`, { etiqueta_id: data.id });
    carregar();
  };
  const disponiveis = todas.filter((t) => !doCaso.some((d) => d.id === t.id));
  const Chip = ({ e, onX }: { e: any; onX?: () => void }) => (
    <span
      className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full text-white"
      style={{ background: e.cor || "#AA8660" }}
    >
      {e.nome}
      {onX && (
        <button onClick={onX} className="ml-0.5 opacity-80 hover:opacity-100">
          ×
        </button>
      )}
    </span>
  );

  return (
    <div className="space-y-5 max-w-2xl">
      <div>
        <h2 className="font-semibold mb-2">Etiquetas do caso</h2>
        <div className="flex flex-wrap gap-2">
          {doCaso.map((e) => (
            <Chip key={e.id} e={e} onX={() => remover(e.id)} />
          ))}
          {doCaso.length === 0 && (
            <p className="text-sm text-gray-400">
              Nenhuma etiqueta neste caso.
            </p>
          )}
        </div>
      </div>

      {disponiveis.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-500 mb-2">
            Adicionar existente
          </h3>
          <div className="flex flex-wrap gap-2">
            {disponiveis.map((e) => (
              <button
                key={e.id}
                onClick={() => atribuir(e.id)}
                className="opacity-80 hover:opacity-100"
              >
                <Chip e={e} />
              </button>
            ))}
          </div>
        </div>
      )}

      <form onSubmit={criar} className="card p-4 space-y-3">
        <h3 className="text-sm font-semibold text-gray-700">
          Criar nova etiqueta
        </h3>
        <div className="flex gap-2 items-center">
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder="Nome da etiqueta"
            className="input flex-1"
          />
          <button type="submit" className="btn-primary text-sm">
            Criar + aplicar
          </button>
        </div>
        <div className="flex gap-1.5">
          {CORES.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCor(c)}
              className={`w-6 h-6 rounded-full ${cor === c ? "ring-2 ring-offset-1 ring-navy" : ""}`}
              style={{ background: c }}
              aria-label={c}
            />
          ))}
        </div>
      </form>
    </div>
  );
}

// ── Tab: Memória Institucional ───────────────────────────────────────────────
function TabMemoria({ caseId }: { caseId: string }) {
  const [itens, setItens] = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    tipo: "tese_vencedora",
    titulo: "",
    conteudo: "",
    resultado: "favoravel",
    area_direito: "",
  });
  const TIPOS: Record<string, string> = {
    tese_vencedora: "Tese Vencedora",
    estrategia: "Estratégia",
    peticao: "Petição",
    recurso: "Recurso",
    parecer: "Parecer",
    contrato: "Contrato",
    decisao: "Decisão",
    acordo: "Acordo",
  };
  const RES: Record<string, string> = {
    favoravel: "text-green-700 bg-green-100",
    desfavoravel: "text-danger-700 bg-danger-100",
    parcial: "text-yellow-700 bg-yellow-100",
    acordo: "text-primary-700 bg-primary-100",
    em_andamento: "text-gray-700 bg-gray-100",
  };

  const carregar = () =>
    api
      .get(`/memoria-institucional?case_id=${caseId}`)
      .then((r) => setItens(asList(r.data)))
      .catch(() => {});
  useEffect(() => {
    carregar();
  }, [caseId]);

  const salvar = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.post("/memoria-institucional", { ...form, case_id: caseId });
    setShowForm(false);
    setForm({
      tipo: "tese_vencedora",
      titulo: "",
      conteudo: "",
      resultado: "favoravel",
      area_direito: "",
    });
    carregar();
  };
  const remover = async (id: string) => {
    if (!confirm("Remover este registro de memória?")) return;
    try {
      await api.delete(`/memoria-institucional/${id}`);
      setItens((p) => p.filter((x) => x.id !== id));
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao remover registro");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="font-semibold">
          Memória Institucional ({itens.length})
        </h2>
        <button
          onClick={() => setShowForm(!showForm)}
          className="btn-primary text-sm"
        >
          + Registrar
        </button>
      </div>
      <p className="text-xs text-gray-400">
        O que funcionou neste caso — para reaproveitar em casos futuros.
      </p>
      {showForm && (
        <form onSubmit={salvar} className="card p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <label className="label">Tipo</label>
              <select
                value={form.tipo}
                onChange={(e) =>
                  setForm((f) => ({ ...f, tipo: e.target.value }))
                }
                className="input w-full"
              >
                {Object.entries(TIPOS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Resultado</label>
              <select
                value={form.resultado}
                onChange={(e) =>
                  setForm((f) => ({ ...f, resultado: e.target.value }))
                }
                className="input w-full"
              >
                {Object.keys(RES).map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-span-2">
              <label className="label">Título *</label>
              <input
                required
                value={form.titulo}
                onChange={(e) =>
                  setForm((f) => ({ ...f, titulo: e.target.value }))
                }
                className="input w-full"
              />
            </div>
            <div className="col-span-2">
              <label className="label">Conteúdo *</label>
              <textarea
                required
                rows={3}
                value={form.conteudo}
                onChange={(e) =>
                  setForm((f) => ({ ...f, conteudo: e.target.value }))
                }
                className="input w-full"
              />
            </div>
            <div>
              <label className="label">Área do Direito</label>
              <input
                value={form.area_direito}
                onChange={(e) =>
                  setForm((f) => ({ ...f, area_direito: e.target.value }))
                }
                className="input w-full"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <button type="submit" className="btn-primary text-sm">
              Salvar
            </button>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="btn-secondary text-sm"
            >
              Cancelar
            </button>
          </div>
        </form>
      )}
      <div className="space-y-2">
        {itens.map((m) => (
          <div key={m.id} className="card p-4">
            <div className="flex justify-between items-start">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <span className="font-medium text-sm">{m.titulo}</span>
                  <span className="text-xs bg-primary-100 text-primary-700 px-2 py-0.5 rounded-full">
                    {TIPOS[m.tipo] || m.tipo}
                  </span>
                  {m.resultado && (
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${RES[m.resultado] || "bg-gray-100"}`}
                    >
                      {m.resultado}
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-600 leading-relaxed">
                  {m.conteudo}
                </p>
                <p className="text-xs text-gray-400 mt-1">
                  {m.area_direito} · {fmtDate(m.created_at)}
                </p>
              </div>
              <button
                onClick={() => remover(m.id)}
                className="text-danger-400 hover:text-danger-600 text-xs ml-4"
              >
                Remover
              </button>
            </div>
          </div>
        ))}
        {itens.length === 0 && !showForm && (
          <p className="text-center py-8 text-gray-400 text-sm">
            Nenhum registro de memória para este caso
          </p>
        )}
      </div>
    </div>
  );
}

// ── Tab placeholder (módulo ainda não disponível) ────────────────────────────
function TabEmBreve({
  titulo,
  descricao,
}: {
  titulo: string;
  descricao: string;
}) {
  return (
    <div className="space-y-4">
      <h2 className="font-semibold">{titulo}</h2>
      <div className="card p-8 text-center text-gray-400 border border-dashed">
        <p className="text-3xl mb-2">🚧</p>
        <p className="font-medium text-gray-500">
          Módulo em implementação (FASE 8)
        </p>
        <p className="text-xs mt-1">{descricao}</p>
      </div>
    </div>
  );
}

// ── Componente principal ──────────────────────────────────────────────────────

// ── Mapa área do caso → slugs de ramo ────────────────────────────────────────
const AREA_PARA_RAMO: Record<string, string[]> = {
  empresarial: ["empresarial"],
  civil: ["civel", "bancario"],
  criminal: ["penal"],
  trabalhista: ["trabalhista"],
  tributario: ["administrativo"],
  ambiental: ["administrativo"],
  consumidor: ["civel"],
  familia: ["civel"],
  previdenciario: [],
};

// ── Mini Ferramenta (reutiliza lógica do RamoBase, independente) ──────────────
function MiniFerramentaCalc({ f }: { f: FerramentaConfig }) {
  function rotulo(v: string) {
    return v.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }
  const [vals, setVals] = React.useState<Record<string, any>>(() => {
    const init: Record<string, any> = {};
    f.campos.forEach((c) => {
      if (c.default !== undefined) init[c.nome] = c.default;
    });
    return init;
  });
  const [res, setRes] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(false);
  const [erro, setErro] = React.useState<string | null>(null);

  const calcular = async () => {
    setLoading(true);
    setErro(null);
    setRes(null);
    try {
      const r = await api.get(f.endpoint, { params: vals });
      setRes(r.data);
    } catch (e: any) {
      setErro(e.response?.data?.detail || "Falha no cálculo");
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    if (f.autoLoad) calcular();
  }, [f.id]); // eslint-disable-line

  return (
    <div className="border border-gray-200 rounded-lg p-3 bg-white">
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-xs font-semibold text-navy">{f.titulo}</span>
        {f.autoLoad && res && (
          <span className="text-[10px] text-green-600 bg-green-50 px-1 rounded">
            ● ao vivo
          </span>
        )}
      </div>
      <p className="text-[11px] text-slate-400 mb-2">{f.baseLegal}</p>
      {f.campos.length > 0 && (
        <div className="grid grid-cols-2 gap-1.5 mb-2">
          {f.campos.map((c) => (
            <div key={c.nome}>
              <label className="text-[10px] text-slate-500 block mb-0.5">
                {c.label}
              </label>
              {c.tipo === "select" ? (
                <select
                  className="input text-xs py-1"
                  value={vals[c.nome] ?? ""}
                  onChange={(e) =>
                    setVals({ ...vals, [c.nome]: e.target.value })
                  }
                >
                  <option value="">—</option>
                  {c.opcoes?.map((o) => (
                    <option key={o} value={o}>
                      {rotulo(o)}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className="input text-xs py-1"
                  type={c.tipo}
                  step={c.tipo === "number" ? "0.01" : undefined}
                  value={vals[c.nome] ?? ""}
                  onChange={(e) =>
                    setVals({ ...vals, [c.nome]: e.target.value })
                  }
                />
              )}
            </div>
          ))}
        </div>
      )}
      {(!f.autoLoad || f.campos.length > 0) && (
        <button
          className="btn-gold text-xs py-1 px-3 mt-1"
          disabled={loading}
          onClick={calcular}
        >
          {loading ? "..." : f.campos.length === 0 ? "Atualizar" : "Calcular"}
        </button>
      )}
      {erro && <p className="text-xs text-danger-600 mt-2">{erro}</p>}
      {res && (
        <div className="mt-2 p-2 bg-gold-50 rounded text-[11px] space-y-0.5 border border-gold-200">
          {typeof res === "object" &&
            Object.entries(res as Record<string, any>).map(([k, v]) => {
              if (k === "aviso")
                return (
                  <p
                    key={k}
                    className="text-slate-400 italic pt-1 mt-1 border-t border-gold-200"
                  >
                    {String(v)}
                  </p>
                );
              if (typeof v === "object" && v !== null) return null;
              return (
                <div key={k} className="flex justify-between gap-1">
                  <span className="text-slate-500">{rotulo(k)}</span>
                  <span className="font-medium text-navy text-right">
                    {typeof v === "boolean"
                      ? v
                        ? "✓ Sim"
                        : "✗ Não"
                      : String(v)}
                  </span>
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
}

// ── Análise de Contrato com IA ────────────────────────────────────────────────
function AnaliseContratoIA({ caseId }: { caseId: string }) {
  const [texto, setTexto] = React.useState("");
  const [tipo, setTipo] = React.useState("prestacao_servicos");
  const [resultado, setResultado] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(false);
  const [tab, setTab] = React.useState<"analise" | "comparar">("analise");
  const [texto2, setTexto2] = React.useState("");
  const [compResult, setCompResult] = React.useState<any>(null);
  const [compLoading, setCompLoading] = React.useState(false);

  const analisar = async () => {
    if (texto.trim().length < 100) {
      toast.error("Cole pelo menos 100 caracteres do contrato");
      return;
    }
    setLoading(true);
    setResultado(null);
    try {
      const { data } = await api.post("/ai/analisar-contrato", {
        texto_contrato: texto,
        tipo_contrato: tipo,
        case_id: caseId,
      });
      setResultado(data);
    } catch (e: any) {
      setResultado({ erro: e.response?.data?.detail || "Falha" });
    } finally {
      setLoading(false);
    }
  };

  const comparar = async () => {
    if (texto.trim().length < 50 || texto2.trim().length < 50) {
      toast.error("Cole os dois contratos para comparar");
      return;
    }
    setCompLoading(true);
    setCompResult(null);
    try {
      // Prompt de comparação montado no servidor (modo "comparacao") —
      // o cliente envia apenas os dois textos brutos.
      const { data } = await api.post("/ai/analisar-contrato", {
        texto_contrato: texto,
        texto_contrato_2: texto2,
        modo: "comparacao",
        tipo_contrato: tipo,
        case_id: caseId,
      });
      setCompResult(data);
    } catch (e: any) {
      setCompResult({ erro: e.response?.data?.detail || "Falha" });
    } finally {
      setCompLoading(false);
    }
  };

  const TIPOS = [
    "prestacao_servicos",
    "compra_venda",
    "locacao",
    "parceria_empresarial",
    "honorarios_advocaticios",
    "financiamento",
    "franquia",
    "trabalho_autonomo",
    "sigiloso_nda",
    "fornecimento",
    "empreitada",
    "licenca_uso",
    "outro",
  ];

  return (
    <div className="border border-gray-200 rounded-xl p-4 bg-white">
      <div className="flex items-center gap-2 mb-3">
        <Sparkles size={16} className="text-gold-600" />
        <h3 className="font-serif font-semibold text-navy text-sm">
          Análise de Contrato com IA
        </h3>
        <span className="text-[10px] bg-warn-100 text-warn-700 px-2 py-0.5 rounded-full font-medium">
          MINUTA · revisão obrigatória
        </span>
      </div>

      {/* Sub-tabs */}
      <div className="flex gap-1 mb-3 border-b border-gray-100">
        {(["analise", "comparar"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`text-xs px-3 py-1.5 font-medium border-b-2 -mb-px transition-colors ${
              tab === t
                ? "border-gold-500 text-gold-700"
                : "border-transparent text-slate-400 hover:text-slate-600"
            }`}
          >
            {t === "analise" ? "Analisar contrato" : "Comparar versões"}
          </button>
        ))}
      </div>

      <div className="mb-3">
        <label className="text-[11px] text-slate-500 mb-1 block">
          Tipo de contrato
        </label>
        <select
          className="input text-sm"
          value={tipo}
          onChange={(e) => setTipo(e.target.value)}
        >
          {TIPOS.map((t) => (
            <option key={t} value={t}>
              {t.replace(/_/g, " ").replace(/\w/g, (c) => c.toUpperCase())}
            </option>
          ))}
        </select>
      </div>

      {tab === "analise" ? (
        <>
          <textarea
            className="input text-sm font-mono"
            rows={8}
            placeholder="Cole aqui o texto completo do contrato para análise..."
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
          />
          <div className="flex items-center justify-between mt-2">
            <span className="text-[11px] text-slate-400">
              {texto.length} chars
            </span>
            <button
              className="btn-gold text-sm"
              disabled={loading}
              onClick={analisar}
            >
              {loading ? (
                <>
                  <Spinner /> Analisando...
                </>
              ) : (
                "🔍 Identificar brechas e riscos"
              )}
            </button>
          </div>
          {resultado && <ResultadoContratoIA data={resultado} />}
        </>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] font-semibold text-slate-600 mb-1 block">
                Contrato A (original / atual)
              </label>
              <textarea
                className="input text-xs font-mono"
                rows={7}
                placeholder="Cole o Contrato A..."
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
              />
            </div>
            <div>
              <label className="text-[11px] font-semibold text-slate-600 mb-1 block">
                Contrato B (proposta / nova versão)
              </label>
              <textarea
                className="input text-xs font-mono"
                rows={7}
                placeholder="Cole o Contrato B..."
                value={texto2}
                onChange={(e) => setTexto2(e.target.value)}
              />
            </div>
          </div>
          <div className="flex justify-end mt-2">
            <button
              className="btn-gold text-sm"
              disabled={compLoading}
              onClick={comparar}
            >
              {compLoading ? (
                <>
                  <Spinner /> Comparando...
                </>
              ) : (
                "⚖️ Comparar contratos"
              )}
            </button>
          </div>
          {compResult && <ResultadoContratoIA data={compResult} />}
        </>
      )}
    </div>
  );
}

function ResultadoContratoIA({ data }: { data: any }) {
  if (data.erro)
    return (
      <div className="mt-3 p-3 bg-danger-50 text-danger-700 text-xs rounded">
        {data.erro}
      </div>
    );
  return (
    <div className="mt-3 border border-gold-200 rounded-lg bg-gold-50 p-4">
      <Markdown
        source={data.resposta}
        className="prose prose-sm max-w-none text-navy text-xs leading-relaxed"
      />
      {data.fontes?.length > 0 && (
        <div className="mt-3 pt-3 border-t border-gold-200">
          <p className="text-[10px] font-semibold text-gold-700 uppercase mb-1">
            Fontes utilizadas
          </p>
          <div className="flex flex-wrap gap-1">
            {data.fontes.map((f: any, i: number) => (
              <span
                key={i}
                className="text-[10px] bg-white border border-gold-200 px-1.5 py-0.5 rounded text-slate-600"
              >
                {f.titulo?.slice(0, 50)}
              </span>
            ))}
          </div>
        </div>
      )}
      {(data.aviso || data.aviso_hitl) && (
        <p className="text-[11px] text-warn-700 mt-2 italic">
          {data.aviso || data.aviso_hitl}
        </p>
      )}
    </div>
  );
}

// -- IA Defensiva / Contestacao ------------------------------------------------
function IaDefensivaCaso({ caso }: { caso: Case }) {
  const [etapa, setEtapa] = React.useState("fluxo_completo");
  const [rito, setRito] = React.useState("comum");
  const [area, setArea] = React.useState(caso.area || "civil");
  const [nivelInteligencia, setNivelInteligencia] = React.useState("alto");
  const [peticao, setPeticao] = React.useState(caso.descricao_fatos || "");
  const [docsAutor, setDocsAutor] = React.useState("");
  const [docsDefesa, setDocsDefesa] = React.useState("");
  const [analises, setAnalises] = React.useState("");
  const [resultado, setResultado] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(false);
  const [historico, setHistorico] = React.useState<any[]>([]);
  const [histLoading, setHistLoading] = React.useState(false);
  const [histSelecionado, setHistSelecionado] = React.useState<string | null>(
    null,
  );

  const etapas = [
    ["fluxo_completo", "Fluxo completo"],
    ["analise_inicial", "1. Analise da inicial"],
    ["fragilidades", "2. Fragilidades"],
    ["teses_defensivas", "3. Teses defensivas"],
    ["provas_comparativas", "4. Provas comparativas"],
    ["esqueleto_contestacao", "5. Esqueleto da contestacao"],
    ["redigir_contestacao", "6. Redigir contestacao"],
    ["jec_triagem_minuta", "AcioneJus JEC"],
  ];

  const linhas = (txt: string) =>
    txt
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);

  const carregarHistorico = async () => {
    setHistLoading(true);
    try {
      const { data } = await api.get(`/ia-defensiva/historico/${caso.id}`);
      setHistorico(data.data || []);
    } catch {
      setHistorico([]);
    } finally {
      setHistLoading(false);
    }
  };

  React.useEffect(() => {
    carregarHistorico();
  }, [caso.id]);

  const atualizarStatus = async (logId: string, status: string) => {
    try {
      await api.patch(`/ia-defensiva/historico/${logId}/status`, { status });
      toast.error(`Status atualizado para ${status}.`);
      await carregarHistorico();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao atualizar status");
    }
  };

  const abrirHistorico = (item: any) => {
    setResultado({
      resposta: item.resposta,
      aviso: "Resultado historico da IA Defensiva. Revisao humana obrigatoria.",
    });
    setHistSelecionado(item.id);
  };

  const executar = async () => {
    if (peticao.trim().length < 50) {
      toast.error(
        "Cole a peticao inicial, relato ou base factual com ao menos 50 caracteres.",
      );
      return;
    }
    setLoading(true);
    setResultado(null);
    try {
      const { data } = await api.post("/ia-defensiva/analisar", {
        etapa,
        peticao_inicial: peticao,
        rito,
        area,
        nivel_inteligencia: nivelInteligencia,
        documentos_autor: linhas(docsAutor),
        documentos_defesa: linhas(docsDefesa),
        analises_anteriores: analises || undefined,
        case_id: caso.id,
        momento: "detalhe_caso",
        dados_formais: {
          numero_processo:
            (caso as any).numero_processo ||
            (caso as any).processo_principal?.numero_cnj ||
            "",
          titulo_caso: caso.titulo,
          cliente:
            (caso as any).cliente_nome || (caso as any).client_name || "",
          parte_contraria: caso.parte_contraria || "",
          valor_causa: caso.valor_causa ?? "",
        },
      });
      setResultado(data);
    } catch (e: any) {
      setResultado({
        erro: e.response?.data?.detail || "Falha ao executar IA defensiva",
      });
    } finally {
      setLoading(false);
    }
  };

  const statusClass = (status: string) => {
    const map: Record<string, string> = {
      gerado: "bg-warn-50 text-warn-700 ring-warn-200",
      revisado: "bg-primary-50 text-primary-700 ring-primary-200",
      aplicado: "bg-success-50 text-success-700 ring-success-200",
      descartado: "bg-slate-100 text-slate-500 ring-slate-200",
    };
    return map[status] || "bg-slate-100 text-slate-600 ring-slate-200";
  };

  const etapaResumo = (texto?: string) => {
    const t = texto || "";
    const match = t.match(/^#\s+([^\n]+)/m);
    return match?.[1]?.replace(/_/g, " ") || "IA Defensiva";
  };

  const copiar = async () => {
    const texto = resultado?.resposta || "";
    if (!texto) return;
    await navigator.clipboard.writeText(texto);
    toast.success("Resultado copiado para a area de transferencia.");
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-ai-100 bg-ai-50/70 p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <ShieldCheck size={18} className="text-ai-700" />
              <h2 className="text-sm font-semibold text-slate-950">
                IA Defensiva do Caso
              </h2>
            </div>
            <p className="mt-1 max-w-3xl text-xs leading-relaxed text-slate-600">
              Analisa peticao inicial, fragilidades, provas, teses e estrutura
              contestacao com modo de alta inteligencia juridica. Todo resultado
              e rascunho interno sujeito a revisao humana obrigatoria.
            </p>
          </div>
          <span className="rounded-full bg-white px-3 py-1 text-[11px] font-semibold text-ai-700 ring-1 ring-ai-100">
            Nivel {nivelInteligencia}
          </span>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]">
        <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="grid gap-3 md:grid-cols-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                Inteligencia
              </label>
              <select
                className="input text-sm"
                value={nivelInteligencia}
                onChange={(e) => setNivelInteligencia(e.target.value)}
              >
                <option value="padrao">Padrao</option>
                <option value="alto">Alto</option>
                <option value="maximo">Maximo</option>
              </select>
              <p className="mt-1 text-[10px] text-slate-400">
                Alto usa raciocinio estrategico. Maximo prioriza profundidade e
                autocritica.
              </p>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                Etapa
              </label>
              <select
                className="input text-sm"
                value={etapa}
                onChange={(e) => setEtapa(e.target.value)}
              >
                {etapas.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                Rito
              </label>
              <select
                className="input text-sm"
                value={rito}
                onChange={(e) => setRito(e.target.value)}
              >
                {["comum", "sumario", "JEC", "CLT", "penal", "outro"].map(
                  (r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ),
                )}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                Area
              </label>
              <input
                className="input text-sm"
                value={area}
                onChange={(e) => setArea(e.target.value)}
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">
              Peticao inicial, relato ou base factual
            </label>
            <textarea
              className="input min-h-[260px] text-sm leading-relaxed"
              value={peticao}
              onChange={(e) => setPeticao(e.target.value)}
              placeholder="Cole aqui a peticao inicial completa ou o relato base do caso..."
            />
            <div className="mt-1 text-right text-[11px] text-slate-400">
              {peticao.length} caracteres
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                Documentos do autor
              </label>
              <textarea
                className="input min-h-[110px] text-xs"
                value={docsAutor}
                onChange={(e) => setDocsAutor(e.target.value)}
                placeholder="Um documento por linha"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                Documentos da defesa
              </label>
              <textarea
                className="input min-h-[110px] text-xs"
                value={docsDefesa}
                onChange={(e) => setDocsDefesa(e.target.value)}
                placeholder="Um documento por linha"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">
              Analises anteriores ou observacoes
            </label>
            <textarea
              className="input min-h-[90px] text-xs"
              value={analises}
              onChange={(e) => setAnalises(e.target.value)}
              placeholder="Opcional: cole analises anteriores, estrategia ja definida ou pontos de atencao"
            />
          </div>

          <button
            className="btn-primary w-full justify-center"
            disabled={loading}
            onClick={executar}
          >
            {loading ? (
              <>
                <Spinner /> Executando analise...
              </>
            ) : (
              <>
                <ShieldCheck size={16} /> Executar IA Defensiva
              </>
            )}
          </button>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold text-slate-950">
                Resultado
              </h3>
              <p className="text-xs text-slate-500">
                Rascunho interno para revisao do advogado responsavel.
              </p>
            </div>
            {resultado?.resposta && (
              <button className="btn-secondary h-9 text-xs" onClick={copiar}>
                <Copy size={14} /> Copiar
              </button>
            )}
          </div>

          {!resultado && !loading && (
            <div className="flex min-h-[420px] items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50 text-center text-sm text-slate-400">
              Preencha os dados e execute a analise defensiva.
            </div>
          )}
          {loading && (
            <div className="flex min-h-[420px] items-center justify-center gap-2 rounded-lg bg-slate-50 text-sm text-slate-500">
              <Spinner /> Processando estrategia defensiva...
            </div>
          )}
          {resultado?.erro && (
            <div className="rounded-lg border border-danger-200 bg-danger-50 p-3 text-sm text-danger-700">
              {resultado.erro}
            </div>
          )}
          {resultado?.resposta && (
            <div className="max-h-[720px] overflow-auto rounded-lg border border-ai-100 bg-ai-50/30 p-4">
              <Markdown
                source={resultado.resposta}
                className="text-sm leading-7 text-slate-800"
              />
              {resultado.aviso && (
                <p className="mt-4 border-t border-ai-100 pt-3 text-xs font-medium text-ai-700">
                  {resultado.aviso}
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-3 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <h3 className="text-sm font-semibold text-slate-950">
              Historico e revisao humana
            </h3>
            <p className="text-xs text-slate-500">
              Cada execucao fica vinculada ao caso e pode ser marcada como
              revisada, aplicada ou descartada.
            </p>
          </div>
          <button
            className="btn-secondary h-9 text-xs"
            onClick={carregarHistorico}
            disabled={histLoading}
          >
            {histLoading ? <Spinner /> : <RefreshCw size={14} />} Atualizar
          </button>
        </div>
        {historico.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-5 text-center text-sm text-slate-400">
            Nenhuma analise defensiva registrada para este caso.
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {historico.map((item) => (
              <div
                key={item.id}
                className={`rounded-lg border p-3 text-xs ${histSelecionado === item.id ? "border-ai-300 bg-ai-50" : "border-slate-200 bg-white"}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <button
                    className="text-left font-semibold text-slate-800 hover:text-ai-700"
                    onClick={() => abrirHistorico(item)}
                  >
                    {etapaResumo(item.resposta)}
                  </button>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 font-semibold ring-1 ${statusClass(item.status_hitl)}`}
                  >
                    {item.status_hitl}
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-slate-400">
                  {item.created_at ? fmtDate(item.created_at) : "sem data"} ·{" "}
                  {item.modelo || "modelo"}
                </p>
                <p className="mt-2 line-clamp-3 text-slate-500">
                  {(item.resposta || "").replace(/[#*_]/g, " ").slice(0, 220)}
                </p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  <button
                    className="rounded-md border border-primary-200 px-2 py-1 text-primary-700 hover:bg-primary-50"
                    onClick={() => atualizarStatus(item.id, "revisado")}
                  >
                    Revisado
                  </button>
                  <button
                    className="rounded-md border border-success-200 px-2 py-1 text-success-700 hover:bg-success-50"
                    onClick={() => atualizarStatus(item.id, "aplicado")}
                  >
                    Aplicado
                  </button>
                  <button
                    className="rounded-md border border-slate-200 px-2 py-1 text-slate-500 hover:bg-slate-50"
                    onClick={() => atualizarStatus(item.id, "descartado")}
                  >
                    Descartar
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Tab Ferramentas — contextual ao caso ──────────────────────────────────────
function TabFerramentas({ caso }: { caso: Case }) {
  const slugs = AREA_PARA_RAMO[caso.area] ?? [];
  const configs = slugs.map((s) => RAMOS[s]).filter(Boolean);
  const [ramoAtivo, setRamoAtivo] = React.useState(slugs[0] ?? "");
  const cfg = configs.find((c) => c.slug === ramoAtivo) ?? configs[0];

  // Agrupar ferramentas por grupo
  const grupos = cfg
    ? (() => {
        const g: Record<string, FerramentaConfig[]> = {};
        cfg.ferramentas.forEach((f) => {
          const key = f.grupo ?? "Calculadoras";
          if (!g[key]) g[key] = [];
          g[key].push(f);
        });
        return g;
      })()
    : {};

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-navy-50 border border-navy-100 rounded-xl p-4">
        <h2 className="font-serif font-bold text-navy text-sm mb-0.5">
          Ferramentas para este caso
        </h2>
        <p className="text-xs text-slate-500">
          Calculadoras e análises IA filtradas pela área{" "}
          <strong>{caso.area}</strong>. Todos os resultados são minutas —
          revisão obrigatória.
        </p>
      </div>

      {/* Ramo sub-tabs (se houver mais de um) */}
      {configs.length > 1 && (
        <div className="flex gap-1 border-b border-gray-200">
          {configs.map((c) => (
            <button
              key={c.slug}
              onClick={() => setRamoAtivo(c.slug)}
              className={`text-xs px-3 py-2 font-medium border-b-2 -mb-px whitespace-nowrap transition-colors ${
                ramoAtivo === c.slug
                  ? "border-gold-500 text-gold-700"
                  : "border-transparent text-slate-400 hover:text-slate-600"
              }`}
            >
              {c.titulo.replace("Direito ", "")}
            </button>
          ))}
        </div>
      )}

      {/* Calculadoras agrupadas */}
      {cfg ? (
        Object.entries(grupos).map(([grupo, ferrs]) => (
          <div key={grupo}>
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
              {grupo}
            </h3>
            <div className="grid md:grid-cols-2 gap-3">
              {ferrs.map((f) => (
                <MiniFerramentaCalc key={f.id} f={f} />
              ))}
            </div>
          </div>
        ))
      ) : (
        <div className="text-center py-8 text-slate-400 text-sm">
          Nenhuma ferramenta específica para a área <strong>{caso.area}</strong>
          .
          <br />
          Acesse Ramos no menu lateral para as calculadoras gerais.
        </div>
      )}

      {/* Análise Estratégica IA — sempre disponível */}
      <AnaliseEstrategica caseId={caso.id} />

      {/* Análise de Contrato IA — sempre disponível */}
      <AnaliseContratoIA caseId={caso.id} />
    </div>
  );
}

// ── Tab: Teses sugeridas (Banco de Teses ranqueado ao caso) ──────────────────
interface TeseSugerida {
  id: string;
  titulo: string;
  tema: string | null;
  ramo: string | null;
  resumo: string;
  score: number;
  distancia: number;
  taxa_sucesso: number | null;
  vezes_venceu: number | null;
  vezes_usada: number | null;
  tribunal: string | null;
}

interface TesesSugeridasResp {
  case_id: string;
  estrategia: string | null;
  area: string | null;
  palavras_chave: string[];
  total: number;
  teses: TeseSugerida[];
}

function TabTesesSugeridas({ caseId }: { caseId: string }) {
  const [loading, setLoading] = useState(true);
  const [resp, setResp] = useState<TesesSugeridasResp | null>(null);

  useEffect(() => {
    let ativo = true;
    setLoading(true);
    api
      .get<TesesSugeridasResp>(`/cases/${caseId}/teses-sugeridas`, {
        params: { k: 5 },
      })
      .then((r) => {
        if (ativo) setResp(r.data);
      })
      .catch(() => {
        if (ativo) {
          setResp(null);
          toast.error("Falha ao carregar teses sugeridas.");
        }
      })
      .finally(() => {
        if (ativo) setLoading(false);
      });
    return () => {
      ativo = false;
    };
  }, [caseId]);

  if (loading) return <Spinner />;

  const teses = resp?.teses ?? [];
  if (!resp || resp.total === 0 || teses.length === 0) {
    return <Empty message="Nenhuma tese aderente encontrada" />;
  }

  const pctExito = (taxa: number | null): string =>
    taxa == null ? "—" : `${Math.round(taxa * 100)}%`;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-semibold">Teses sugeridas</h2>
        <p className="text-xs text-slate-400">
          Teses do Banco de Teses mais aderentes a este caso, ranqueadas por
          desempenho histórico. Rascunho de apoio — revisão humana obrigatória
          (OAB).
          {resp.palavras_chave.length > 0 && (
            <> Palavras-chave: {resp.palavras_chave.join(", ")}.</>
          )}
        </p>
      </div>

      <div className="space-y-3">
        {teses.map((t) => (
          <div key={t.id} className="card p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="font-medium text-sm text-slate-800">
                  {t.titulo}
                </h3>
                {t.tema && (
                  <p className="text-xs text-slate-400 mt-0.5">{t.tema}</p>
                )}
              </div>
              {t.ramo && <Badge tone="purple">{t.ramo}</Badge>}
            </div>

            {t.resumo && (
              <p className="text-sm text-slate-600 mt-2 leading-relaxed">
                {t.resumo}
              </p>
            )}

            <div className="flex flex-wrap items-center gap-2 mt-3">
              <Badge tone="green">Êxito {pctExito(t.taxa_sucesso)}</Badge>
              <Badge tone="slate">{t.vezes_venceu ?? 0} vitória(s)</Badge>
              {typeof t.vezes_usada === "number" && (
                <Badge tone="slate">{t.vezes_usada} uso(s)</Badge>
              )}
              {t.tribunal && <Badge tone="slate">{t.tribunal}</Badge>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function CasoDetalhe() {
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const [caso, setCaso] = useState<Case | null>(null);

  const activeTab = (searchParams.get("tab") as TabKey) || "resumo";

  useEffect(() => {
    if (!id) return;
    api
      .get(`/cases/${id}`)
      .then((r) => setCaso(r.data))
      .catch(() => navigate("/casos"));
  }, [id]);

  if (!caso) {
    return (
      <div className="flex justify-center items-center h-64">
        <Spinner />
      </div>
    );
  }

  const renderTab = () => {
    if (!id) return null;
    switch (activeTab) {
      case "resumo":
        return <TabResumo caso={caso} />;
      case "processos":
        return <TabProcessos caseId={id} />;
      case "timeline":
        return <TabTimeline caseId={id} />;
      case "mensagens":
        return <TabMensagens caseId={id} />;
      case "partes":
        return <TabPartes caseId={id} />;
      case "etiquetas":
        return <TabEtiquetas caseId={id} />;
      case "checklists":
        return <TabChecklists caseId={id} />;
      case "score":
        return <TabScore caseId={id} />;
      case "risco":
        return <TabRisco caseId={id} />;
      case "jurisprudencia":
        return <TabJurisprudencia caseId={id} caso={caso} />;
      case "documentos":
        return (
          <TabLista
            titulo="Documentos"
            endpoint={`/documents/?case_id=${id}`}
            empty="Nenhum documento vinculado a este caso"
            renderItem={(d) => (
              <div
                className="card p-3 flex justify-between items-center text-sm cursor-pointer hover:bg-slate-50"
                onClick={() =>
                  baixarDoc(d.id, d.filename || d.nome_arquivo || d.titulo)
                }
                title="Clique para baixar"
              >
                <span className="text-gray-800">
                  {d.titulo || d.filename || d.nome_arquivo}
                </span>
                <span className="text-gray-400 text-xs">
                  {d.tipo_peca || d.tipo}
                </span>
              </div>
            )}
          />
        );
      case "provas":
        return <ProvasCaso caseId={id} />;
      case "contratos":
        return (
          <TabLista
            titulo="Contratos"
            endpoint={`/contratos?case_id=${id}`}
            empty="Nenhum contrato vinculado"
            renderItem={(c) => (
              <div className="card p-3 flex justify-between items-center text-sm">
                <span className="text-gray-800">
                  {c.titulo || c.tipo_contrato}
                </span>
                <span className="text-gray-500">{fmtMoney(c.valor_total)}</span>
              </div>
            )}
          />
        );
      case "procuracoes":
        return (
          <TabLista
            titulo="Procurações"
            endpoint={`/procuracoes/?client_id=${(caso as any).client_id ?? ""}`}
            empty="Nenhuma procuração do cliente"
            renderItem={(p) => (
              <div className="card p-3 text-sm flex justify-between items-center">
                <span className="text-gray-800">
                  {p.tipo_poderes || "Procuração"}
                </span>
                {p.data_validade && (
                  <span className="text-gray-400 text-xs">
                    Vence: {fmtDate(p.data_validade)}
                  </span>
                )}
              </div>
            )}
          />
        );
      case "prazos":
        return (
          <TabLista
            titulo="Prazos"
            endpoint={`/deadlines/?case_id=${id}&status=`}
            empty="Nenhum prazo cadastrado"
            renderItem={(d) => (
              <div className="card p-3 flex justify-between items-center text-sm">
                <span className="text-gray-800">{d.titulo}</span>
                <span
                  className={`font-medium text-xs ${
                    (d.dias_restantes ?? 1) <= 0
                      ? "text-danger-600"
                      : (d.dias_restantes ?? 99) <= 7
                        ? "text-orange-600"
                        : "text-gray-500"
                  }`}
                >
                  {fmtDate(d.data_prazo)}
                </span>
              </div>
            )}
          />
        );
      case "audiencias":
        return (
          <TabLista
            titulo="Audiências"
            endpoint={`/deadlines/?case_id=${id}&tipo=audiencia&status=`}
            empty="Nenhuma audiência cadastrada"
            renderItem={(a) => (
              <div className="card p-3 flex justify-between items-center text-sm">
                <span className="text-gray-800">{a.titulo}</span>
                <span className="text-gray-500 text-xs">
                  {fmtDate(a.data_prazo)}
                </span>
              </div>
            )}
          />
        );
      case "financeiro":
        return (
          <TabLista
            titulo="Honorários e Pagamentos"
            endpoint={`/fees/?case_id=${id}`}
            empty="Nenhum lançamento financeiro"
            renderItem={(f) => (
              <div className="card p-3 flex justify-between items-center text-sm">
                <span className="text-gray-800">{f.descricao}</span>
                <span
                  className={
                    f.status === "pago"
                      ? "text-green-600 font-medium"
                      : "text-orange-600"
                  }
                >
                  {fmtMoney(f.valor)}
                </span>
              </div>
            )}
          />
        );
      case "custos":
        return (
          <TabLista
            titulo="Centro de Custos"
            endpoint={`/centro-custos?case_id=${id}`}
            empty="Nenhum lançamento de custo"
            renderItem={(c) => (
              <div className="card p-3 flex justify-between items-center text-sm">
                <span className="text-gray-800">{c.descricao}</span>
                <span
                  className={
                    c.pago ? "text-green-600 font-medium" : "text-orange-600"
                  }
                >
                  {fmtMoney(c.valor)}
                </span>
              </div>
            )}
          />
        );
      case "liquidez":
        return (
          <CalculadoraAcordo
            caseId={id}
            valorCausaInicial={
              caso.valor_causa ?? caso.processo_principal?.valor_causa ?? null
            }
            tribunalInicial={
              caso.tribunal ?? caso.processo_principal?.tribunal ?? null
            }
          />
        );
      case "teses":
        return (
          <div className="space-y-4">
            <MotorTeses caso={caso} />
            <TabLista
              titulo="Teses Vinculadas"
              endpoint={`/teses/casos/${id}`}
              empty="Nenhuma tese vinculada a este caso"
              renderItem={(t) => (
                <div className="card p-3 text-sm">
                  <span className="font-medium text-gray-800">
                    {t.titulo || t.tese_id || t.id}
                  </span>
                  {t.descricao && (
                    <p className="text-gray-500 text-xs mt-1">{t.descricao}</p>
                  )}
                </div>
              )}
            />
          </div>
        );
      case "teses-sugeridas":
        return <TabTesesSugeridas caseId={id} />;
      case "precedentes":
        return (
          <TabLista
            titulo="Precedentes Internos (jurisprudência do escritório na área)"
            endpoint={`/jurisprudencias?area=${encodeURIComponent(caso.area || "")}&per_page=50`}
            empty="Nenhuma jurisprudência interna cadastrada nesta área"
            renderItem={(j) => (
              <div className="card p-3 text-sm">
                <div className="flex justify-between items-start gap-2">
                  <span className="font-medium text-gray-800">{j.titulo}</span>
                  {j.tribunal && (
                    <span className="text-xs text-gray-400 shrink-0">
                      {j.tribunal}
                    </span>
                  )}
                </div>
                {j.ementa && (
                  <p className="text-gray-600 text-xs mt-1">
                    {j.ementa.slice(0, 180)}
                    {j.ementa.length > 180 ? "…" : ""}
                  </p>
                )}
                <div className="flex gap-2 mt-1 text-xs text-gray-400">
                  {j.area_juridica && <span>{j.area_juridica}</span>}
                  {j.resultado && <span>· {j.resultado}</span>}
                  {j.favorito && <span>· ★</span>}
                  {typeof j.vezes_citada === "number" && (
                    <span>· {j.vezes_citada}× citada</span>
                  )}
                </div>
              </div>
            )}
          />
        );
      case "memoria":
        return <TabMemoria caseId={id} />;
      case "jurimetria":
        return (
          <TabEmBreve
            titulo="Jurimetria"
            descricao="A jurimetria é agregada (por área/tribunal/magistrado) e fica no menu Jurimetria — não há recorte por caso individual."
          />
        );
      case "dossie":
        return <DossieEstrategicoCaso caseId={id} />;
      case "iaDefensiva":
        return <IaDefensivaCaso caso={caso} />;
      case "ferramentas":
        return <TabFerramentas caso={caso} />;
      default:
        return (
          <div className="text-center py-8 text-gray-400">
            Aba em desenvolvimento
          </div>
        );
    }
  };

  const grupoAtivo =
    GROUPS.find((g) => g.tabs.includes(activeTab)) ?? GROUPS[0];
  const activeTabLabel =
    TABS.find((t) => t.key === activeTab)?.label ?? "Resumo";
  const numeroProcesso =
    (caso as any).processo_principal?.numero_cnj ||
    (caso as any).numero_processo;

  return (
    <div className="space-y-5">
      <CaseBreadcrumb caseId={caso.id} titulo={caso.titulo} tela={activeTabLabel} />
      {/* Sticky header + tabs */}
      <div className="sticky top-[4.25rem] z-20 rounded-2xl border border-slate-200 bg-white/95 shadow-sm backdrop-blur-xl">
        <div className="flex flex-col gap-4 px-4 py-4 lg:flex-row lg:items-start lg:justify-between">
          <button
            onClick={() => navigate("/casos")}
            className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500 transition-colors hover:bg-slate-50 hover:text-slate-800"
          >
            <ChevronLeft size={18} />
          </button>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              {caso.numero_interno && (
                <span className="text-xs font-semibold uppercase tracking-wide text-primary-700">
                  {caso.numero_interno}
                </span>
              )}
              <StatusBadge value={caso.status} />
              <RiscoChip nivel={(caso as any).risco_nivel ?? caso.risco} />
            </div>
            <h1 className="mt-2 truncate text-xl font-semibold text-slate-950 md:text-2xl">
              {caso.titulo}
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
              <span className="capitalize">
                Area:{" "}
                <strong className="font-medium text-slate-700">
                  {caso.area || "nao informada"}
                </strong>
              </span>
              {numeroProcesso && (
                <span>
                  Processo:{" "}
                  <strong className="font-medium text-slate-700">
                    {numeroProcesso}
                  </strong>
                </span>
              )}
              {caso.valor_causa != null && (
                <span>
                  Valor:{" "}
                  <strong className="font-medium text-slate-700">
                    {fmtMoney(caso.valor_causa)}
                  </strong>
                </span>
              )}
              {caso.created_at && (
                <span>
                  Abertura:{" "}
                  <strong className="font-medium text-slate-700">
                    {fmtDate(caso.created_at)}
                  </strong>
                </span>
              )}
            </div>
            {/* Visual Law — badges de alerta do caso (falha silenciosa) */}
            <BadgesAlerta caseId={caso.id} className="mt-2" />
          </div>
          <div className="grid grid-cols-2 gap-2 sm:flex sm:shrink-0">
            <button
              onClick={() => setSearchParams({ tab: "iaDefensiva" })}
              className="btn-secondary h-9 text-xs"
            >
              <Sparkles size={14} /> IA do caso
            </button>
            <button
              onClick={() => setSearchParams({ tab: "processos" })}
              className="btn-secondary h-9 text-xs"
            >
              Processos
            </button>
          </div>
        </div>
        {/* Tab bar — grupos */}
        <div className="border-t border-slate-100 px-3 py-2">
          <div className="flex gap-1 overflow-x-auto scrollbar-thin">
            {GROUPS.map((g) => {
              const ativo = g.tabs.includes(activeTab);
              return (
                <button
                  key={g.label}
                  onClick={() => setSearchParams({ tab: g.tabs[0] })}
                  className={`h-9 flex-shrink-0 rounded-lg px-3 text-sm font-medium transition-all ${
                    ativo
                      ? "bg-primary-600 text-white shadow-sm shadow-primary-600/20"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-950"
                  }`}
                >
                  {g.label}
                </button>
              );
            })}
          </div>
        </div>
        {/* Sub-abas do grupo ativo */}
        {(() => {
          const grp = grupoAtivo;
          if (grp.tabs.length <= 1) return null;
          return (
            <div className="flex gap-2 overflow-x-auto border-t border-slate-100 bg-slate-50/70 px-3 py-2 scrollbar-thin">
              <span className="hidden text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400 sm:inline-flex sm:items-center">
                {grp.label}
              </span>
              {grp.tabs.map((k) => {
                const t = TABS.find((x) => x.key === k)!;
                return (
                  <button
                    key={k}
                    onClick={() => setSearchParams({ tab: k })}
                    className={`h-8 flex-shrink-0 rounded-full px-3 text-xs font-medium transition-colors ${
                      activeTab === k
                        ? "bg-slate-950 text-white"
                        : "text-slate-600 hover:bg-white hover:text-slate-950"
                    }`}
                  >
                    {t.label}
                  </button>
                );
              })}
            </div>
          );
        })()}
      </div>

      <div className="flex items-center justify-between">
        <div>
          <div className="eyebrow">Caso</div>
          <h2 className="mt-1 text-lg font-semibold text-slate-950">
            {activeTabLabel}
          </h2>
        </div>
      </div>

      <div>{renderTab()}</div>
    </div>
  );
}
