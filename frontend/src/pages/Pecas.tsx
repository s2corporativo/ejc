import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import {
  ClipboardCheck,
  Eye,
  FileDown,
  FolderOpen,
  LayoutTemplate,
  MoreHorizontal,
  PenLine,
  Plus,
  Printer,
  Save,
  SearchCheck,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Stamp,
} from "lucide-react";

import api from "../lib/api";
import type { LegalDoc, Paged } from "../types";
import {
  Badge,
  Button,
  Empty,
  EmptyState,
  Modal,
  PageHeader,
  Spinner,
  fmtDate,
  fmtMoney,
} from "../components/UI";
import { toast } from "../components/Toast";
import Markdown from "../components/Markdown";
import PecaGeneratorModal from "../components/PecaGeneratorModal";
import CaseFilterChip from "../components/CaseFilterChip";
import FichaTriagem, {
  type FichaStatus,
  type FichaTriagemCampos,
} from "../components/FichaTriagem";
import { useIaStatus } from "../lib/iaStatus";
import { ROTULO_IA_NAO_ATIVADA } from "../lib/iaErro";
import { useCasoFiltro } from "../contexts/useCasoFiltro";
import {
  dataLocalISO,
  mensagemErroProtocolo,
  montarPayloadProtocolo,
  temProtocoloRegistrado,
} from "../lib/protocoloPeca";

async function blobErrorDetail(e: any): Promise<string | undefined> {
  let detail = e.response?.data?.detail;
  if (!detail && e.response?.data instanceof Blob) {
    try {
      detail = JSON.parse(await e.response.data.text())?.detail;
    } catch {
      return undefined;
    }
  }
  return typeof detail === "object" && detail !== null
    ? (detail.mensagem ?? JSON.stringify(detail).slice(0, 200))
    : detail;
}

function errDetail(e: any, fallback: string): string {
  const d = e?.response?.data?.detail;
  if (typeof d === "string" && d) return d;
  if (d && typeof d === "object")
    return d.mensagem ?? JSON.stringify(d).slice(0, 200);
  return fallback;
}

const TIPOS_MANUAIS = [
  "peticao_inicial",
  "contestacao",
  "recurso",
  "contrarrazoes",
  "parecer",
  "contrato",
  "procuracao",
  "notificacao_extrajudicial",
  "defesa_ambiental",
  "outro",
];

const STATUS_POS_APROVACAO = new Set(["aprovada", "final", "protocolada"]);

type FaseVisual = "elaboracao" | "revisao" | "aprovadas" | "protocoladas";

const FASES: {
  key: FaseVisual;
  label: string;
  statuses: string[];
  descricao: string;
}[] = [
  {
    key: "elaboracao",
    label: "Em elaboração",
    statuses: ["rascunho", "em_revisao"],
    descricao: "Minutas e peças ainda em conferência",
  },
  {
    key: "revisao",
    label: "Revisadas",
    statuses: ["corrigida"],
    descricao: "Revisão registrada, aguardando aprovação",
  },
  {
    key: "aprovadas",
    label: "Aprovadas",
    statuses: ["aprovada", "final"],
    descricao: "Assinadas ou prontas para protocolo",
  },
  {
    key: "protocoladas",
    label: "Protocoladas",
    statuses: ["protocolada"],
    descricao: "Com protocolo registrado",
  },
];

type CitacaoBloqueio = {
  mensagem?: string;
  politica?: string;
  score?: number;
  motivos?: string[];
  bloqueantes?: { rotulo?: string; aviso?: string; status?: string }[];
};

function faseDaPeca(status: string): FaseVisual | "outro" {
  return FASES.find((f) => f.statuses.includes(status))?.key ?? "outro";
}

function faseLabel(status: string): string {
  return FASES.find((f) => f.statuses.includes(status))?.label ?? status;
}

export default function Pecas() {
  const { disponivel: iaDisponivel } = useIaStatus();
  const { casoFiltro, casoFiltroNome, removerFiltro } = useCasoFiltro();

  const [data, setData] = useState<Paged<LegalDoc> | null>(null);
  const [erro, setErro] = useState(false);
  const [filtroFase, setFiltroFase] = useState<"todos" | FaseVisual>("todos");

  const [modalIA, setModalIA] = useState(false);
  const [modal, setModal] = useState(false);
  const [view, setView] = useState<LegalDoc | null>(null);
  const [editandoConteudo, setEditandoConteudo] = useState(false);
  const [conteudoEdicao, setConteudoEdicao] = useState("");
  const [salvandoConteudo, setSalvandoConteudo] = useState(false);
  const [form, setForm] = useState<any>({
    tipo_peca: "peticao_inicial",
    ai_generated: false,
  });
  const [salvando, setSalvando] = useState(false);

  const [revisao, setRevisao] = useState<{
    doc: LegalDoc;
    notas: string;
    erro?: string;
    bloqueio?: CitacaoBloqueio;
    justificativa?: string;
  } | null>(null);
  const [revisando, setRevisando] = useState(false);

  const [tplModal, setTplModal] = useState(false);
  const [templates, setTemplates] = useState<any[]>([]);
  const [casos, setCasos] = useState<any[]>([]);
  const [tplSel, setTplSel] = useState("");
  const [casoSel, setCasoSel] = useState("");

  const [auditoria, setAuditoria] = useState<string | null>(null);
  const [auditoriaTitulo, setAuditoriaTitulo] = useState("Controle de qualidade");
  const [auditando, setAuditando] = useState(false);
  const [printDoc, setPrintDoc] = useState<LegalDoc | null>(null);
  const [gerandoVL, setGerandoVL] = useState<string | null>(null);

  const [protocolo, setProtocolo] = useState<{
    doc: LegalDoc;
    numero: string;
    tribunal: string;
    data: string;
  } | null>(null);
  const [protocolando, setProtocolando] = useState(false);

  const [fichaStatus, setFichaStatus] = useState<FichaStatus>("rascunho");
  const [fichaCampos, setFichaCampos] = useState<FichaTriagemCampos | null>(null);
  const [refreshFicha, setRefreshFicha] = useState(0);
  const fichaRef = useRef<HTMLDivElement>(null);
  const fichaConfirmada = fichaStatus === "confirmada";

  useEffect(() => {
    if (!printDoc) return;
    const t = window.setTimeout(() => {
      window.print();
      setPrintDoc(null);
    }, 150);
    return () => window.clearTimeout(t);
  }, [printDoc]);

  const onFichaStatus = useCallback(
    (status: FichaStatus, campos: FichaTriagemCampos) => {
      setFichaStatus(status);
      setFichaCampos(campos);
    },
    [],
  );

  const irParaFicha = useCallback(() => {
    toast.error("Confirme a ficha de triagem antes de gerar a peça");
    fichaRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const abrirGeradorIA = () => {
    if (casoFiltro && !fichaConfirmada) {
      irParaFicha();
      return;
    }
    setModalIA(true);
  };

  const onNeedFicha = useCallback(() => {
    setModalIA(false);
    setFichaStatus("rascunho");
    setRefreshFicha((n) => n + 1);
    window.setTimeout(irParaFicha, 60);
  }, [irParaFicha]);

  const load = useCallback(() => {
    setErro(false);
    return api
      .get("/legal-docs/", {
        params: { page_size: 50, case_id: casoFiltro },
      })
      .then((r) => setData(r.data))
      .catch(() => {
        setErro(true);
        toast.error("Falha ao carregar peças");
      });
  }, [casoFiltro]);

  useEffect(() => {
    load();
  }, [load]);

  const salvar = async () => {
    if (!form.titulo || !form.conteudo) {
      toast.error("Título e conteúdo obrigatórios");
      return;
    }
    setSalvando(true);
    try {
      await api.post("/legal-docs/", {
        ...form,
        case_id: form.case_id ?? casoFiltro ?? null,
      });
      setModal(false);
      setForm({ tipo_peca: "peticao_inicial", ai_generated: false });
      toast.success("Peça criada como rascunho");
      load();
    } catch (e: any) {
      toast.error(errDetail(e, "Erro ao salvar a peça"));
    } finally {
      setSalvando(false);
    }
  };

  const abrirDetalhe = async (id: string) => {
    try {
      const { data: detalhe } = await api.get(`/legal-docs/${id}`);
      setView(detalhe);
      setConteudoEdicao(detalhe.conteudo || "");
      setEditandoConteudo(false);
    } catch (e: any) {
      toast.error(errDetail(e, "Falha ao carregar a peça"));
    }
  };

  const fecharWorkspace = () => {
    setView(null);
    setEditandoConteudo(false);
    setConteudoEdicao("");
  };

  const salvarConteudoWorkspace = async () => {
    if (!view) return;
    if (view.status === "final" || view.status === "protocolada") {
      toast.error("Versão final ou protocolada não pode ser editada neste fluxo.");
      return;
    }
    const novoConteudo = conteudoEdicao.trim();
    if (!novoConteudo) {
      toast.error("O conteúdo da peça não pode ficar vazio.");
      return;
    }
    if (novoConteudo === (view.conteudo || "").trim()) {
      setEditandoConteudo(false);
      toast.info("Nenhuma alteração de conteúdo para salvar.");
      return;
    }

    setSalvandoConteudo(true);
    try {
      const { data: atualizada } = await api.patch(`/legal-docs/${view.id}`, {
        conteudo: conteudoEdicao,
      });
      setView(atualizada);
      setConteudoEdicao(atualizada.conteudo || conteudoEdicao);
      setEditandoConteudo(false);
      toast.success(
        "Nova versão salva. Validação e revisão devem ser refeitas antes da aprovação.",
      );
      load();
    } catch (e: any) {
      toast.error(errDetail(e, "Falha ao salvar a nova versão da peça"));
    } finally {
      setSalvandoConteudo(false);
    }
  };

  const abrirRevisao = (doc: LegalDoc) => {
    setRevisao({
      doc,
      notas: doc.notas_revisao || "",
    });
  };

  const devolverParaRevisao = async () => {
    if (!revisao) return;
    setRevisando(true);
    setRevisao({ ...revisao, erro: undefined });
    try {
      await api.post(`/legal-docs/${revisao.doc.id}/revisar`, {
        aprovado: false,
        notas: revisao.notas,
      });
      toast.success("Peça devolvida para revisão");
      setRevisao(null);
      fecharWorkspace();
      load();
    } catch (e: any) {
      setRevisao({
        ...revisao,
        erro: errDetail(e, "Falha ao devolver a peça para revisão"),
      });
    } finally {
      setRevisando(false);
    }
  };

  const aprovarEAssinar = async () => {
    if (!revisao) return;
    const observacoes = revisao.notas.trim();
    if (revisao.doc.ai_generated && !observacoes) {
      setRevisao({
        ...revisao,
        erro: "Descreva as observações da revisão antes de aprovar uma peça gerada por IA.",
      });
      return;
    }

    const justificativa = (revisao.justificativa || "").trim();
    if (revisao.bloqueio && !justificativa) {
      setRevisao({
        ...revisao,
        erro:
          "Para aprovar apesar das citações não confirmadas, registre uma justificativa por escrito.",
      });
      return;
    }

    setRevisando(true);
    setRevisao({ ...revisao, erro: undefined });
    try {
      await api.post(`/legal-docs/${revisao.doc.id}/conferir-e-assinar`, {
        observacoes: observacoes || null,
        ...(revisao.bloqueio
          ? {
              override_citacoes: true,
              justificativa_override: justificativa,
            }
          : {}),
      });
      toast.success("Peça revisada, aprovada e assinada");
      setRevisao(null);
      fecharWorkspace();
      load();
    } catch (e: any) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail;
      if (status === 409 && detail?.erro === "citacoes_nao_verificadas") {
        setRevisao({
          ...revisao,
          bloqueio: {
            mensagem: detail.mensagem,
            politica: detail.politica,
            score: detail.score,
            motivos: Array.isArray(detail.motivos) ? detail.motivos : [],
            bloqueantes: Array.isArray(detail.bloqueantes)
              ? detail.bloqueantes
              : [],
          },
          erro: undefined,
        });
      } else {
        setRevisao({
          ...revisao,
          erro: errDetail(e, "Falha ao revisar e aprovar a peça"),
        });
      }
    } finally {
      setRevisando(false);
    }
  };

  const finalizar = async (doc: LegalDoc) => {
    try {
      await api.patch(`/legal-docs/${doc.id}`, { status: "final" });
      toast.success("Versão final registrada — peça pronta para protocolo");
      fecharWorkspace();
      load();
    } catch (e: any) {
      toast.error(errDetail(e, "Falha ao finalizar a peça"));
    }
  };

  const iniciarProtocolo = async (doc: LegalDoc) => {
    try {
      const { data: detalhe } = await api.get<LegalDoc>(`/legal-docs/${doc.id}`);
      if (temProtocoloRegistrado(detalhe)) {
        await api.patch(`/legal-docs/${doc.id}`, { status: "protocolada" });
        toast.success("Peça marcada como protocolada");
        fecharWorkspace();
        load();
        return;
      }
      setProtocolo({ doc, numero: "", tribunal: "", data: "" });
    } catch (e: any) {
      toast.error(
        mensagemErroProtocolo(
          e?.response?.status,
          e?.response?.data?.detail,
          "Falha ao iniciar o protocolo",
        ),
      );
    }
  };

  const confirmarProtocolo = async () => {
    if (!protocolo) return;
    const payload = montarPayloadProtocolo(protocolo);
    if (!payload) {
      toast.error("Informe o número do protocolo");
      return;
    }

    setProtocolando(true);
    try {
      await api.patch(`/legal-docs/${protocolo.doc.id}/protocolo`, payload);
      await api.patch(`/legal-docs/${protocolo.doc.id}`, {
        status: "protocolada",
      });
      toast.success("Protocolo registrado");
      setProtocolo(null);
      fecharWorkspace();
      load();
    } catch (e: any) {
      toast.error(
        mensagemErroProtocolo(e?.response?.status, e?.response?.data?.detail),
      );
    } finally {
      setProtocolando(false);
    }
  };

  const abrirTpl = async () => {
    try {
      const [t, c] = await Promise.all([
        api.get("/templates/"),
        api.get("/cases/", { params: { page_size: 100 } }),
      ]);
      setTemplates(t.data.data);
      setCasos(c.data.data);
      setCasoSel((prev) => prev || casoFiltro || "");
      setTplModal(true);
    } catch (e: any) {
      toast.error(errDetail(e, "Falha ao carregar templates e casos"));
    }
  };

  const gerarDeTemplate = async () => {
    if (!tplSel || !casoSel) {
      toast.error("Escolha template e caso");
      return;
    }
    try {
      await api.post(`/templates/${tplSel}/gerar`, { case_id: casoSel });
      setTplModal(false);
      toast.success("Rascunho gerado a partir do template");
      load();
    } catch (e: any) {
      toast.error(errDetail(e, "Falha ao gerar a peça do template"));
    }
  };

  const baixarPdf = async (doc: LegalDoc) => {
    const aprovada = STATUS_POS_APROVACAO.has(doc.status);
    try {
      const r = aprovada
        ? await api.get(`/legal-docs/${doc.id}/pdf`, { responseType: "blob" })
        : await api.get(`/legal-docs/${doc.id}/pdf-minuta`, {
            responseType: "blob",
          });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = aprovada ? `${doc.titulo}.pdf` : `${doc.titulo}-minuta.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      toast.error((await blobErrorDetail(e)) || "Falha ao gerar PDF");
    }
  };

  const baixarDocx = async (doc: LegalDoc) => {
    try {
      const r = await api.get(`/legal-docs/${doc.id}/exportar-docx`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${doc.titulo}.docx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      toast.error(errDetail(e, "Falha ao exportar DOCX"));
    }
  };

  const baixarDocumentoUnico = async (doc: LegalDoc) => {
    if (gerandoVL) return;
    setGerandoVL(doc.id);
    try {
      const r = await api.get(
        `/legal-docs/${doc.id}/documento-unico-impressao`,
        { responseType: "blob" },
      );
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${doc.titulo} — Documento Único.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      toast.error(
        (await blobErrorDetail(e)) || "Falha ao gerar o documento único",
      );
    } finally {
      setGerandoVL(null);
    }
  };

  const imprimirPeca = async (doc: LegalDoc) => {
    try {
      const { data: detalhe } = await api.get(`/legal-docs/${doc.id}`);
      setPrintDoc(detalhe);
    } catch (e: any) {
      toast.error(errDetail(e, "Falha ao carregar a peça para impressão"));
    }
  };

  const validarPeca = async (doc: LegalDoc) => {
    setAuditando(true);
    setAuditoriaTitulo("Revisão jurídica");
    setAuditoria(null);
    try {
      const { data: resultado } = await api.post(`/legal-docs/${doc.id}/validar`);
      setAuditoria(
        `VALIDAÇÃO JURÍDICA\nVeredito: ${resultado.veredito}\nScore: ${resultado.score_confianca}/100\n\n${resultado.resposta}\n\n${resultado.aviso || ""}`,
      );
      if (view?.id === doc.id) {
        await abrirDetalhe(doc.id);
      }
      load();
    } catch (e: any) {
      toast.error(errDetail(e, "Falha na validação jurídica"));
    } finally {
      setAuditando(false);
    }
  };

  const checarJurisprudencia = async (doc: LegalDoc) => {
    setAuditando(true);
    setAuditoriaTitulo("Jurisprudência e citações");
    setAuditoria(null);
    try {
      const { data: resultado } = await api.get(
        `/legal-docs/${doc.id}/jurisprudencia-check`,
      );
      const problemas = resultado.problemas?.length
        ? resultado.problemas.map((p: string) => `- ${p}`).join("\n")
        : "Nenhum problema encontrado.";
      const validadas = resultado.citacoes_validadas?.length
        ? resultado.citacoes_validadas.join("\n")
        : "Nenhuma citação validada detectada.";
      setAuditoria(
        `CHECK DE JURISPRUDÊNCIA\nStatus: ${resultado.apto ? "APTA" : "BLOQUEADA"}\n\nProblemas:\n${problemas}\n\nValidadas:\n${validadas}\n\nRegra: ${resultado.regra}`,
      );
    } catch (e: any) {
      toast.error(errDetail(e, "Falha na checagem de jurisprudência"));
    } finally {
      setAuditando(false);
    }
  };

  const auditarIA = async (doc: LegalDoc) => {
    setAuditando(true);
    setAuditoriaTitulo("Crítica da peça");
    setAuditoria(null);
    try {
      const { data: resultado } = await api.post("/ai/auditar-peca", {
        peca_id: doc.id,
        tipo_peca: doc.tipo_peca,
      });
      const aviso = resultado.aviso || resultado.aviso_hitl;
      setAuditoria(
        (resultado.resposta ?? resultado.conteudo) +
          (aviso ? `\n\n${aviso}` : ""),
      );
    } catch (e: any) {
      toast.error(errDetail(e, "IA indisponível"));
    } finally {
      setAuditando(false);
    }
  };

  const validacaoLabel = (doc: LegalDoc) => {
    const v = doc.validacao_juridica;
    if (!v || v.status === "sem_validacao")
      return { label: "Não revisada", tone: "slate" as const };
    if (v.apto_fluxo)
      return { label: `Apta ${v.score ?? ""}/100`, tone: "green" as const };
    if (v.status === "pendente_revisao")
      return {
        label: `Atenção ${v.score ?? ""}/100`,
        tone: "amber" as const,
      };
    return { label: `Bloqueada ${v.score ?? ""}/100`, tone: "red" as const };
  };

  const origemBadge = (doc: LegalDoc) =>
    doc.ai_generated ? (
      doc.human_reviewed ? (
        <Badge tone="green">IA revisada</Badge>
      ) : (
        <Badge tone="amber">IA · revisar</Badge>
      )
    ) : (
      <Badge tone="slate">Manual</Badge>
    );

  const casoLink = (doc: LegalDoc) =>
    doc.case_id ? (
      <Link
        to={`/casos/${doc.case_id}`}
        className="inline-flex items-center gap-1 text-xs text-primary-700 hover:underline"
      >
        <FolderOpen size={13} /> Ver caso
      </Link>
    ) : (
      <span className="text-xs text-slate-400">sem caso</span>
    );

  const proximaAcao = (doc: LegalDoc) => {
    if (doc.status === "protocolada") return null;
    if (doc.status === "final") {
      return (
        <button
          className="btn-primary px-3 py-1.5 text-xs"
          onClick={() => iniciarProtocolo(doc)}
        >
          <Stamp size={14} /> Protocolar
        </button>
      );
    }
    if (doc.status === "aprovada") {
      return (
        <button
          className="btn-primary px-3 py-1.5 text-xs"
          onClick={() => finalizar(doc)}
        >
          Finalizar
        </button>
      );
    }
    return (
      <button
        className="btn-primary px-3 py-1.5 text-xs"
        onClick={() => abrirRevisao(doc)}
      >
        <ShieldCheck size={14} /> Revisar peça
      </button>
    );
  };

  const docs = data && Array.isArray(data.data) ? data.data : [];
  const docsVisiveis =
    filtroFase === "todos"
      ? docs
      : docs.filter((doc) => faseDaPeca(doc.status) === filtroFase);

  return (
    <div>
      <PageHeader
        title="Peças Jurídicas"
        subtitle={`${data?.total ?? 0} peças · produção, revisão e protocolo em um único fluxo`}
        actions={
          <div className="flex flex-wrap gap-2">
            <button className="btn-ghost" onClick={abrirTpl}>
              <LayoutTemplate size={16} /> Usar modelo
            </button>
            <button
              onClick={abrirGeradorIA}
              disabled={!iaDisponivel}
              title={iaDisponivel ? undefined : ROTULO_IA_NAO_ATIVADA}
              className="btn btn-primary flex items-center gap-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Sparkles size={15} />
              {iaDisponivel ? "Criar peça" : "IA não ativada"}
            </button>
            <button className="btn-gold" onClick={() => setModal(true)}>
              <Plus size={16} /> Manual
            </button>
          </div>
        }
      />

      {casoFiltro && (
        <div className="mb-4">
          <CaseFilterChip nome={casoFiltroNome} onRemove={removerFiltro} />
        </div>
      )}

      {casoFiltro && (
        <div className="mb-6 space-y-4">
          {fichaConfirmada && fichaCampos ? (
            <div className="card flex flex-wrap items-center gap-x-6 gap-y-2 border-l-4 border-l-success-400 p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-success-700">
                <ShieldCheck size={16} /> Triagem confirmada
              </div>
              <ResumoItem label="Competência" valor={fichaCampos.competencia} />
              <ResumoItem label="Rito" valor={fichaCampos.rito} />
              <ResumoItem
                label="Valor"
                valor={
                  fichaCampos.valor_causa
                    ? fmtValorCausa(fichaCampos.valor_causa)
                    : "—"
                }
              />
              <div className="flex items-center gap-1.5">
                <span className="text-xs uppercase tracking-wide text-slate-400">
                  Risco
                </span>
                <Badge tone={RISCO_TONE[fichaCampos.risco_processual]}>
                  {fichaCampos.risco_processual}
                </Badge>
              </div>
            </div>
          ) : (
            <div className="flex items-start gap-2 rounded-lg border border-warn-200 bg-warn-50 px-4 py-3 text-xs text-warn-800">
              <ClipboardCheck size={15} className="mt-0.5 shrink-0" />
              <span>
                Confirme a ficha de triagem para liberar a geração de peças deste caso.
              </span>
            </div>
          )}
          <div ref={fichaRef}>
            <FichaTriagem
              caseId={casoFiltro}
              onStatusChange={onFichaStatus}
              refreshSignal={refreshFicha}
            />
          </div>
        </div>
      )}

      <div className="mb-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setFiltroFase("todos")}
          className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
            filtroFase === "todos"
              ? "bg-navy text-white"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          Todas · {docs.length}
        </button>
        {FASES.map((fase) => {
          const total = docs.filter((doc) =>
            fase.statuses.includes(doc.status),
          ).length;
          return (
            <button
              key={fase.key}
              type="button"
              onClick={() => setFiltroFase(fase.key)}
              title={fase.descricao}
              className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                filtroFase === fase.key
                  ? "bg-navy text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {fase.label} · {total}
            </button>
          );
        })}
      </div>

      {erro && !data ? (
        <EmptyState
          title="Falha ao carregar peças"
          message="Não foi possível carregar a lista. Verifique sua conexão e tente novamente."
          action={
            <Button variant="primary" onClick={load}>
              Tentar novamente
            </Button>
          }
        />
      ) : !data ? (
        <Spinner />
      ) : docs.length === 0 ? (
        casoFiltro ? (
          <EmptyState
            title="Nenhuma peça neste caso"
            message="Você está vendo apenas as peças do caso filtrado."
            action={
              <Button variant="secondary" onClick={removerFiltro}>
                Ver todas as peças
              </Button>
            }
          />
        ) : (
          <Empty message="Nenhuma peça cadastrada" />
        )
      ) : docsVisiveis.length === 0 ? (
        <EmptyState
          title="Nenhuma peça nesta etapa"
          message="Altere o filtro para visualizar outras fases do fluxo."
          action={
            <Button variant="secondary" onClick={() => setFiltroFase("todos")}>
              Ver todas
            </Button>
          }
        />
      ) : (
        <>
          <div className="space-y-2 md:hidden">
            {docsVisiveis.map((doc) => {
              const validacao = validacaoLabel(doc);
              return (
                <div key={doc.id} className="card p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <button
                        type="button"
                        onClick={() => abrirDetalhe(doc.id)}
                        className="text-left font-medium text-navy hover:underline"
                      >
                        {doc.titulo}
                      </button>
                      <div className="mt-1 text-xs text-slate-400">
                        {doc.tipo_peca.replace(/_/g, " ")} · v{doc.versao}.0 · {fmtDate(doc.created_at)}
                      </div>
                    </div>
                    <Badge tone="slate">{faseLabel(doc.status)}</Badge>
                  </div>

                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    {origemBadge(doc)}
                    <Badge tone={validacao.tone}>{validacao.label}</Badge>
                    {casoLink(doc)}
                  </div>

                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <button
                      className="btn-ghost px-3 py-1.5 text-xs"
                      onClick={() => abrirDetalhe(doc.id)}
                    >
                      <Eye size={14} /> Abrir
                    </button>
                    {proximaAcao(doc)}
                    <MaisAcoes
                      doc={doc}
                      gerandoVL={gerandoVL === doc.id}
                      onPdf={baixarPdf}
                      onDocx={baixarDocx}
                      onVisualLaw={baixarDocumentoUnico}
                      onPrint={imprimirPeca}
                      onJuris={checarJurisprudencia}
                      onValidar={validarPeca}
                      onAuditar={auditarIA}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          <div className="card hidden overflow-visible md:block">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase text-slate-400">
                <tr>
                  <th className="px-4 py-3">Peça</th>
                  <th className="px-4 py-3">Fase</th>
                  <th className="px-4 py-3">Origem</th>
                  <th className="px-4 py-3">Revisão</th>
                  <th className="px-4 py-3">Caso</th>
                  <th className="px-4 py-3 text-right">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {docsVisiveis.map((doc) => {
                  const validacao = validacaoLabel(doc);
                  return (
                    <tr key={doc.id} className="hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() => abrirDetalhe(doc.id)}
                          className="text-left font-medium text-navy hover:underline"
                        >
                          {doc.titulo}
                        </button>
                        <div className="mt-1 text-xs capitalize text-slate-400">
                          {doc.tipo_peca.replace(/_/g, " ")} · v{doc.versao}.0 · {fmtDate(doc.created_at)}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <Badge tone="slate">{faseLabel(doc.status)}</Badge>
                      </td>
                      <td className="px-4 py-3">{origemBadge(doc)}</td>
                      <td className="px-4 py-3">
                        <Badge tone={validacao.tone}>{validacao.label}</Badge>
                      </td>
                      <td className="px-4 py-3">{casoLink(doc)}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            className="btn-ghost px-3 py-1.5 text-xs"
                            onClick={() => abrirDetalhe(doc.id)}
                          >
                            <Eye size={14} /> Abrir
                          </button>
                          {proximaAcao(doc)}
                          <MaisAcoes
                            doc={doc}
                            gerandoVL={gerandoVL === doc.id}
                            onPdf={baixarPdf}
                            onDocx={baixarDocx}
                            onVisualLaw={baixarDocumentoUnico}
                            onPrint={imprimirPeca}
                            onJuris={checarJurisprudencia}
                            onValidar={validarPeca}
                            onAuditar={auditarIA}
                          />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      <Modal open={modal} onClose={() => setModal(false)} title="Nova peça manual" wide>
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label">Título *</label>
              <input
                className="input"
                value={form.titulo || ""}
                onChange={(e) => setForm({ ...form, titulo: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Tipo</label>
              <select
                className="input"
                value={form.tipo_peca}
                onChange={(e) => setForm({ ...form, tipo_peca: e.target.value })}
              >
                {TIPOS_MANUAIS.map((tipo) => (
                  <option key={tipo} value={tipo}>
                    {tipo.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="label">Conteúdo * (markdown)</label>
            <textarea
              className="input min-h-[260px] font-mono text-xs"
              value={form.conteudo || ""}
              onChange={(e) => setForm({ ...form, conteudo: e.target.value })}
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={form.ai_generated}
              onChange={(e) =>
                setForm({ ...form, ai_generated: e.target.checked })
              }
            />
            Conteúdo recebeu assistência de IA
          </label>
          <div className="flex justify-end">
            <button
              className="btn-primary"
              disabled={salvando}
              onClick={salvar}
            >
              {salvando ? "Salvando..." : "Salvar peça"}
            </button>
          </div>
        </div>
      </Modal>

      <Modal
        open={!!view}
        onClose={fecharWorkspace}
        title={view?.titulo ? `Workspace Jurídico · ${view.titulo}` : "Workspace Jurídico"}
        wide
      >
        {view && (
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
            <div className="min-w-0">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="slate">{faseLabel(view.status)}</Badge>
                  {origemBadge(view)}
                  <Badge tone="slate">v{view.versao}.0</Badge>
                  {view.codigo_peca && (
                    <Badge tone="ouro" className="font-mono">
                      {view.codigo_peca}
                    </Badge>
                  )}
                </div>
                {view.status !== "final" && view.status !== "protocolada" && (
                  <div className="flex items-center gap-2">
                    {editandoConteudo ? (
                      <>
                        <button
                          type="button"
                          className="btn-ghost px-3 py-1.5 text-xs"
                          disabled={salvandoConteudo}
                          onClick={() => {
                            setConteudoEdicao(view.conteudo || "");
                            setEditandoConteudo(false);
                          }}
                        >
                          Cancelar
                        </button>
                        <button
                          type="button"
                          className="btn-primary px-3 py-1.5 text-xs"
                          disabled={salvandoConteudo}
                          onClick={salvarConteudoWorkspace}
                        >
                          <Save size={14} />
                          {salvandoConteudo ? "Salvando..." : "Salvar nova versão"}
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        className="btn-ghost px-3 py-1.5 text-xs"
                        onClick={() => setEditandoConteudo(true)}
                      >
                        <PenLine size={14} /> Editar texto
                      </button>
                    )}
                  </div>
                )}
              </div>

              {editandoConteudo ? (
                <div className="space-y-2">
                  <textarea
                    className="input min-h-[62vh] w-full font-mono text-sm leading-6"
                    value={conteudoEdicao}
                    onChange={(e) => setConteudoEdicao(e.target.value)}
                    aria-label="Conteúdo editável da peça"
                  />
                  <p className="text-xs text-amber-700">
                    Salvar cria nova versão lógica e exige nova validação/revisão antes da aprovação.
                  </p>
                </div>
              ) : (
                <div className="min-h-[55vh] rounded-xl border border-slate-100 bg-white p-5">
                  <Markdown source={view.conteudo} className="text-sm text-slate-700" />
                </div>
              )}
            </div>

            <aside className="space-y-3 border-t border-slate-100 pt-4 lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  Inteligência jurídica
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  Fontes, validação e crítica ficam separados do texto. A IA não altera a peça sem ação explícita do advogado.
                </p>
              </div>

              {view.validacao_juridica ? (
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
                  <div className="font-medium text-slate-800">Validação</div>
                  <div className="mt-1">
                    {view.validacao_juridica.status} · score {view.validacao_juridica.score ?? "—"}/
                    {view.validacao_juridica.score_minimo ?? 75}
                  </div>
                  {view.validacao_juridica.motivo && (
                    <div className="mt-1">{view.validacao_juridica.motivo}</div>
                  )}
                </div>
              ) : (
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-500">
                  Ainda sem validação jurídica registrada.
                </div>
              )}

              {view.notas_revisao && (
                <div className="rounded-lg border border-success-200 bg-success-50 p-3 text-xs text-slate-700">
                  <div className="font-medium">Notas da revisão</div>
                  <div className="mt-1">{view.notas_revisao}</div>
                </div>
              )}

              {view.case_id && (
                <Link
                  to={`/casos/${view.case_id}`}
                  className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs text-primary-700 hover:bg-slate-50"
                >
                  <FolderOpen size={14} /> Abrir caso vinculado
                </Link>
              )}

              <button
                className="btn-ghost w-full justify-start text-xs"
                onClick={() => validarPeca(view)}
              >
                <ShieldCheck size={14} /> Revisão jurídica
              </button>
              <button
                className="btn-ghost w-full justify-start text-xs"
                onClick={() => checarJurisprudencia(view)}
              >
                <SearchCheck size={14} /> Jurisprudência e citações
              </button>
              <button
                className="btn-ghost w-full justify-start text-xs"
                onClick={() => auditarIA(view)}
              >
                <Sparkles size={14} /> Crítica da peça
              </button>

              <div className="border-t border-slate-100 pt-3">
                {view.status === "final" ? (
                  <button
                    className="btn-primary w-full justify-center"
                    onClick={() => iniciarProtocolo(view)}
                  >
                    <Stamp size={14} /> Protocolar
                  </button>
                ) : view.status === "aprovada" ? (
                  <button
                    className="btn-primary w-full justify-center"
                    onClick={() => finalizar(view)}
                  >
                    Finalizar peça
                  </button>
                ) : view.status !== "protocolada" ? (
                  <button
                    className="btn-primary w-full justify-center"
                    disabled={editandoConteudo}
                    title={editandoConteudo ? "Salve ou cancele a edição antes de revisar" : undefined}
                    onClick={() => abrirRevisao(view)}
                  >
                    <ShieldCheck size={14} /> Revisar peça
                  </button>
                ) : (
                  <div className="rounded-lg bg-success-50 p-3 text-center text-xs font-medium text-success-700">
                    Protocolo registrado
                  </div>
                )}
              </div>
            </aside>
          </div>
        )}
      </Modal>

      <Modal
        open={!!revisao}
        onClose={() => setRevisao(null)}
        title="Revisão jurídica da peça"
        wide
      >
        {revisao && (
          <div className="space-y-4">
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
              <strong className="text-slate-800">{revisao.doc.titulo}</strong>
              <p className="mt-1 text-xs">
                Revise o conteúdo, registre suas observações e escolha entre devolver para ajustes ou concluir a aprovação e assinatura.
              </p>
            </div>

            <textarea
              className="input min-h-[130px]"
              placeholder={
                revisao.doc.ai_generated
                  ? "Observações da revisão (obrigatórias para aprovar peça de IA)"
                  : "Observações da revisão"
              }
              value={revisao.notas}
              onChange={(e) =>
                setRevisao({ ...revisao, notas: e.target.value, erro: undefined })
              }
            />

            {revisao.bloqueio && (
              <div className="rounded-lg border-2 border-amber-300 bg-amber-50 p-3">
                <div className="flex items-center gap-2 text-sm font-bold text-amber-800">
                  <ShieldAlert size={16} /> Citações não confirmadas
                </div>
                <p className="mt-1 text-xs text-amber-800">
                  {revisao.bloqueio.mensagem ||
                    "O sistema encontrou citações que não pôde confirmar na base oficial."}
                </p>
                {!!revisao.bloqueio.bloqueantes?.length && (
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-amber-800">
                    {revisao.bloqueio.bloqueantes.map((b, i) => (
                      <li key={i}>
                        <strong>{b.rotulo || "citação"}</strong>
                        {b.aviso ? ` — ${b.aviso}` : ""}
                      </li>
                    ))}
                  </ul>
                )}
                <textarea
                  className="input mt-3 min-h-[80px] text-xs"
                  placeholder="Justificativa para eventual override (obrigatória)"
                  value={revisao.justificativa || ""}
                  onChange={(e) =>
                    setRevisao({
                      ...revisao,
                      justificativa: e.target.value,
                      erro: undefined,
                    })
                  }
                />
              </div>
            )}

            {revisao.erro && (
              <div className="rounded-lg border border-danger-300 bg-danger-50 px-3 py-2 text-xs text-danger-700">
                <strong>Não foi possível concluir:</strong> {revisao.erro}
              </div>
            )}

            <div className="flex flex-wrap justify-end gap-2">
              <button
                className="btn-ghost"
                disabled={revisando}
                onClick={devolverParaRevisao}
              >
                Devolver para revisão
              </button>
              <button
                className="btn-primary"
                disabled={
                  revisando ||
                  (revisao.doc.ai_generated && !revisao.notas.trim())
                }
                onClick={aprovarEAssinar}
              >
                <ShieldCheck size={15} />
                {revisando ? "Processando..." : "Aprovar e assinar"}
              </button>
            </div>
          </div>
        )}
      </Modal>

      <Modal
        open={!!protocolo}
        onClose={() => setProtocolo(null)}
        title="Registrar protocolo"
      >
        <p className="mb-3 text-sm text-slate-600">
          Registre o comprovante do peticionamento para concluir o fluxo da peça.
        </p>
        <div className="space-y-3">
          <div>
            <label className="label">Número do protocolo *</label>
            <input
              className="input"
              value={protocolo?.numero || ""}
              onChange={(e) =>
                protocolo &&
                setProtocolo({ ...protocolo, numero: e.target.value })
              }
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label">Tribunal/sistema</label>
              <input
                className="input"
                placeholder="Ex.: TJMG — PJe"
                value={protocolo?.tribunal || ""}
                onChange={(e) =>
                  protocolo &&
                  setProtocolo({ ...protocolo, tribunal: e.target.value })
                }
              />
            </div>
            <div>
              <label className="label">Data do protocolo</label>
              <input
                type="date"
                className="input"
                max={dataLocalISO()}
                value={protocolo?.data || ""}
                onChange={(e) =>
                  protocolo &&
                  setProtocolo({ ...protocolo, data: e.target.value })
                }
              />
            </div>
          </div>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button className="btn-ghost" onClick={() => setProtocolo(null)}>
            Cancelar
          </button>
          <button
            className="btn-primary"
            disabled={protocolando || !protocolo?.numero.trim()}
            onClick={confirmarProtocolo}
          >
            <Stamp size={15} />
            {protocolando ? "Registrando..." : "Registrar e concluir"}
          </button>
        </div>
      </Modal>

      <Modal
        open={tplModal}
        onClose={() => setTplModal(false)}
        title="Usar modelo"
      >
        <div className="space-y-3">
          <select
            className="input"
            value={tplSel}
            onChange={(e) => setTplSel(e.target.value)}
          >
            <option value="">Escolha o modelo…</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.titulo}
              </option>
            ))}
          </select>
          <select
            className="input"
            value={casoSel}
            onChange={(e) => setCasoSel(e.target.value)}
          >
            <option value="">Vincular ao caso…</option>
            {casos.map((c) => (
              <option key={c.id} value={c.id}>
                {c.numero_interno} — {c.titulo}
              </option>
            ))}
          </select>
          <p className="text-xs text-slate-500">
            O modelo preenche a estrutura com os dados do caso e cria uma nova peça em elaboração.
          </p>
          <button
            className="btn-primary w-full justify-center"
            onClick={gerarDeTemplate}
          >
            Criar a partir do modelo
          </button>
        </div>
      </Modal>

      <Modal
        open={!!auditoria || auditando}
        onClose={() => setAuditoria(null)}
        title={auditoriaTitulo}
        wide
      >
        {auditando ? (
          <Spinner />
        ) : (
          <Markdown
            source={auditoria}
            className="max-h-[60vh] overflow-auto text-sm"
          />
        )}
      </Modal>

      <PecaGeneratorModal
        open={modalIA}
        onClose={() => setModalIA(false)}
        caseId={casoFiltro}
        onNeedFicha={onNeedFicha}
        onConcluido={() => {
          load();
        }}
      />

      {printDoc && (
        <div className="print-view">
          <h1 className="print-view-title">{printDoc.titulo}</h1>
          <p className="print-view-meta">
            {printDoc.tipo_peca.replace(/_/g, " ")} · v{printDoc.versao} · {fmtDate(printDoc.created_at)}
          </p>
          <Markdown source={printDoc.conteudo} />
        </div>
      )}
    </div>
  );
}

function MaisAcoes({
  doc,
  gerandoVL,
  onPdf,
  onDocx,
  onVisualLaw,
  onPrint,
  onJuris,
  onValidar,
  onAuditar,
}: {
  doc: LegalDoc;
  gerandoVL: boolean;
  onPdf: (doc: LegalDoc) => void;
  onDocx: (doc: LegalDoc) => void;
  onVisualLaw: (doc: LegalDoc) => void;
  onPrint: (doc: LegalDoc) => void;
  onJuris: (doc: LegalDoc) => void;
  onValidar: (doc: LegalDoc) => void;
  onAuditar: (doc: LegalDoc) => void;
}) {
  return (
    <details className="relative">
      <summary className="btn-ghost list-none cursor-pointer px-2.5 py-1.5 text-xs [&::-webkit-details-marker]:hidden">
        <MoreHorizontal size={16} />
        <span className="sr-only">Mais ações</span>
      </summary>
      <div className="absolute right-0 z-30 mt-1 w-52 rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg">
        <MenuAction label="PDF" icon={<FileDown size={14} />} onClick={() => onPdf(doc)} />
        <MenuAction label="DOCX" icon={<FileDown size={14} />} onClick={() => onDocx(doc)} />
        <MenuAction
          label={gerandoVL ? "Gerando Visual Law..." : "Documento único / Visual Law"}
          icon={<FileDown size={14} />}
          disabled={gerandoVL}
          onClick={() => onVisualLaw(doc)}
        />
        <MenuAction label="Imprimir" icon={<Printer size={14} />} onClick={() => onPrint(doc)} />
        <div className="my-1 border-t border-slate-100" />
        <MenuAction
          label="Revisão jurídica"
          icon={<ShieldCheck size={14} />}
          onClick={() => onValidar(doc)}
        />
        <MenuAction
          label="Jurisprudência e citações"
          icon={<SearchCheck size={14} />}
          onClick={() => onJuris(doc)}
        />
        <MenuAction
          label="Crítica da peça"
          icon={<Sparkles size={14} />}
          onClick={() => onAuditar(doc)}
        />
      </div>
    </details>
  );
}

function MenuAction({
  label,
  icon,
  onClick,
  disabled = false,
}: {
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-50"
    >
      {icon}
      {label}
    </button>
  );
}

const RISCO_TONE: Record<
  FichaTriagemCampos["risco_processual"],
  "green" | "amber" | "red"
> = {
  baixo: "green",
  medio: "amber",
  alto: "red",
};

function fmtValorCausa(v: string): string {
  const n = Number(
    String(v)
      .replace(/[^\d.,-]/g, "")
      .replace(/\.(?=\d{3})/g, "")
      .replace(",", "."),
  );
  return Number.isFinite(n) && v.trim() !== "" ? fmtMoney(n) : v;
}

function ResumoItem({ label, valor }: { label: string; valor?: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs uppercase tracking-wide text-slate-400">
        {label}
      </span>
      <span className="text-sm font-medium text-navy">{valor || "—"}</span>
    </div>
  );
}
