import { useCallback, useEffect, useRef, useState } from "react";
import {
  ClipboardCheck,
  Plus,
  LayoutTemplate,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import api from "../lib/api";
import type { LegalDoc, Paged } from "../types";
import {
  Badge,
  PageHeader,
  fmtDate,
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
  mensagemErroProtocolo,
  montarPayloadProtocolo,
  temProtocoloRegistrado,
} from "../lib/protocoloPeca";
import {
  blobErrorDetail,
  errDetail,
  fmtValorCausa,
  STATUS_POS_APROVACAO,
  RISCO_TONE,
  type FaseVisual,
} from "./pecas/pecasCatalogo";
import { ResumoItem } from "./pecas/pecasBadges";
import PecasLista from "./pecas/PecasLista";
import NovaPecaManualModal from "./pecas/NovaPecaManualModal";
import PecaWorkspaceModal from "./pecas/PecaWorkspaceModal";
import RevisaoJuridicaModal, {
  type RevisaoPeca,
} from "./pecas/RevisaoJuridicaModal";
import ProtocoloModal, { type ProtocoloForm } from "./pecas/ProtocoloModal";
import TemplateModal, { AuditoriaModal } from "./pecas/TemplateModal";

// Página de Peças Jurídicas (auditoria §2.6 #10): orquestração — estado,
// chamadas ao backend canônico (/legal-docs) e composição. Catálogos/helpers
// vivem em pecas/pecasCatalogo.ts e a UI (lista, modais, menu de ações) em
// pecas/*.tsx.

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

  const [revisao, setRevisao] = useState<RevisaoPeca | null>(null);
  const [revisando, setRevisando] = useState(false);

  const [tplModal, setTplModal] = useState(false);
  const [templates, setTemplates] = useState<any[]>([]);
  const [casos, setCasos] = useState<any[]>([]);
  const [tplSel, setTplSel] = useState("");
  const [casoSel, setCasoSel] = useState("");

  const [auditoria, setAuditoria] = useState<string | null>(null);
  const [auditoriaTitulo, setAuditoriaTitulo] = useState(
    "Controle de qualidade",
  );
  const [auditando, setAuditando] = useState(false);
  const [printDoc, setPrintDoc] = useState<LegalDoc | null>(null);
  const [gerandoVL, setGerandoVL] = useState<string | null>(null);

  const [protocolo, setProtocolo] = useState<ProtocoloForm | null>(null);
  const [protocolando, setProtocolando] = useState(false);

  const [fichaStatus, setFichaStatus] = useState<FichaStatus>("rascunho");
  const [fichaCampos, setFichaCampos] = useState<FichaTriagemCampos | null>(
    null,
  );
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
      toast.error(
        "Versão final ou protocolada não pode ser editada neste fluxo.",
      );
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
        erro: "Para aprovar apesar das citações não confirmadas, registre uma justificativa por escrito.",
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
      const { data: detalhe } = await api.get<LegalDoc>(
        `/legal-docs/${doc.id}`,
      );
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
      const { data: resultado } = await api.post(
        `/legal-docs/${doc.id}/validar`,
      );
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
                Confirme a ficha de triagem para liberar a geração de peças
                deste caso.
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

      <PecasLista
        data={data}
        erro={erro}
        onRecarregar={load}
        filtroFase={filtroFase}
        onFiltroFase={setFiltroFase}
        casoFiltro={casoFiltro}
        onRemoverFiltro={removerFiltro}
        gerandoVL={gerandoVL}
        onAbrir={abrirDetalhe}
        onPdf={baixarPdf}
        onDocx={baixarDocx}
        onVisualLaw={baixarDocumentoUnico}
        onPrint={imprimirPeca}
        onJuris={checarJurisprudencia}
        onValidar={validarPeca}
        onAuditar={auditarIA}
        onRevisar={abrirRevisao}
        onFinalizar={finalizar}
        onProtocolar={iniciarProtocolo}
      />

      <NovaPecaManualModal
        open={modal}
        onClose={() => setModal(false)}
        form={form}
        setForm={setForm}
        salvando={salvando}
        onSalvar={salvar}
      />

      <PecaWorkspaceModal
        view={view}
        editandoConteudo={editandoConteudo}
        conteudoEdicao={conteudoEdicao}
        setConteudoEdicao={setConteudoEdicao}
        salvandoConteudo={salvandoConteudo}
        onStartEdicao={() => setEditandoConteudo(true)}
        onCancelEdicao={() => {
          setConteudoEdicao(view?.conteudo || "");
          setEditandoConteudo(false);
        }}
        onSalvarConteudo={salvarConteudoWorkspace}
        onFechar={fecharWorkspace}
        onValidar={validarPeca}
        onJuris={checarJurisprudencia}
        onAuditar={auditarIA}
        onProtocolar={iniciarProtocolo}
        onFinalizar={finalizar}
        onRevisar={abrirRevisao}
      />

      <RevisaoJuridicaModal
        revisao={revisao}
        revisando={revisando}
        onChange={setRevisao}
        onFechar={() => setRevisao(null)}
        onDevolver={devolverParaRevisao}
        onAprovar={aprovarEAssinar}
      />

      <ProtocoloModal
        protocolo={protocolo}
        protocolando={protocolando}
        onChange={setProtocolo}
        onFechar={() => setProtocolo(null)}
        onConfirmar={confirmarProtocolo}
      />

      <TemplateModal
        open={tplModal}
        onClose={() => setTplModal(false)}
        templates={templates}
        casos={casos}
        tplSel={tplSel}
        setTplSel={setTplSel}
        casoSel={casoSel}
        setCasoSel={setCasoSel}
        onGerar={gerarDeTemplate}
      />

      <AuditoriaModal
        open={!!auditoria || auditando}
        titulo={auditoriaTitulo}
        carregando={auditando}
        texto={auditoria}
        onClose={() => setAuditoria(null)}
      />

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
            {printDoc.tipo_peca.replace(/_/g, " ")} · v{printDoc.versao} ·{" "}
            {fmtDate(printDoc.created_at)}
          </p>
          <Markdown source={printDoc.conteudo} />
        </div>
      )}
    </div>
  );
}
