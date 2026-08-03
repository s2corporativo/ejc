import { useEffect, useRef, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { toast } from "../components/Toast";
import Markdown from "../components/Markdown";
import {
  Plus,
  Sparkles,
  ShieldCheck,
  Eye,
  FileDown,
  LayoutTemplate,
  Printer,
  SearchCheck,
  ClipboardCheck,
  FolderOpen,
  Stamp,
} from "lucide-react";
import api from "../lib/api";
import type { LegalDoc, Paged } from "../types";
import {
  PageHeader,
  StatusBadge,
  Modal,
  Empty,
  EmptyState,
  Spinner,
  Button,
  Badge,
  fmtDate,
  fmtMoney,
} from "../components/UI";
import PecaGeneratorModal from "../components/PecaGeneratorModal";
import CaseFilterChip from "../components/CaseFilterChip";
import { ROTULO_IA_NAO_ATIVADA } from "../lib/iaErro";
import {
  montarPayloadProtocolo,
  temProtocoloRegistrado,
  mensagemErroProtocolo,
  dataLocalISO,
} from "../lib/protocoloPeca";
import { useIaStatus } from "../lib/iaStatus";
import { useCasoFiltro } from "../contexts/useCasoFiltro";
import { detalheErro, statusErro, detalheBruto } from "../utils/erro";
import FichaTriagem, {
  type FichaTriagemCampos,
  type FichaStatus,
} from "../components/FichaTriagem";

// responseType blob: erros 4xx/5xx chegam como Blob JSON — extrai o `detail`
// legível para o toast (senão a falha seria silenciosa ou ilegível).
async function blobErrorDetail(e: any): Promise<string | undefined> {
  let detail = e.response?.data?.detail;
  if (!detail && e.response?.data instanceof Blob) {
    try {
      detail = JSON.parse(await e.response.data.text())?.detail;
    } catch {
      /* corpo não-JSON — usa mensagem padrão do chamador */
    }
  }
  return typeof detail === "object" && detail !== null
    ? (detail.mensagem ?? JSON.stringify(detail).slice(0, 200))
    : detail;
}

// `detail` pode chegar como string OU objeto ({mensagem, ...}) — normaliza
// para o toast nunca renderizar "[object Object]" nem falhar em silêncio.

const TIPOS = [
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

// ── Fila de produção ─────────────────────────────────────────────────────────
// Etapas REAIS do backend (PecaStatus em app/models/legal_doc.py):
// rascunho → em_revisao → corrigida → aprovada → final → protocolada.
// NÃO inventar status aqui — o backend rejeita valores fora do enum.
const FILA: { key: string; label: string; desc: string }[] = [
  // O valor `rascunho` é o enum do backend e não muda. O rótulo nomeia a AÇÃO
  // pendente do advogado, não o grau de acabamento do texto — a peça já está
  // escrita e o que falta é conferência e assinatura.
  {
    key: "rascunho",
    label: "Minuta final",
    desc: "Conferir e assinar",
  },
  {
    key: "em_revisao",
    label: "Em revisão",
    desc: "Aguardando (ou reprovada na) revisão humana",
  },
  {
    key: "corrigida",
    label: "Corrigida",
    desc: "Revisão registrada — pronta para aprovação",
  },
  { key: "aprovada", label: "Aprovada", desc: "Aprovação humana registrada" },
  { key: "final", label: "Versão final", desc: "Pronta para protocolo" },
  { key: "protocolada", label: "Protocolada", desc: "Entregue ao juízo" },
];
// Status em que a peça já passou da aprovação (não reexibir "Revisar e Aprovar").
// Espelha STATUS_EXIGE_REVISAO do backend (legal_docs.py).
const STATUS_POS_APROVACAO = new Set(["aprovada", "final", "protocolada"]);

export default function Pecas() {
  const { disponivel: iaDisponivel } = useIaStatus();
  const [data, setData] = useState<Paged<LegalDoc> | null>(null);
  const [modalIA, setModalIA] = useState(false);
  const [modal, setModal] = useState(false);
  const [view, setView] = useState<LegalDoc | null>(null);
  const [revisao, setRevisao] = useState<{
    doc: LegalDoc;
    notas: string;
  } | null>(null);
  const [aprovacao, setAprovacao] = useState<{
    doc: LegalDoc;
    observacoes: string;
  } | null>(null);
  const [aprovando, setAprovando] = useState(false);
  const [form, setForm] = useState<any>({
    tipo_peca: "peticao_inicial",
    ai_generated: false,
  });
  const [salvando, setSalvando] = useState(false);
  const [tplModal, setTplModal] = useState(false);
  const [templates, setTemplates] = useState<any[]>([]);
  const [casos, setCasos] = useState<any[]>([]);
  const [tplSel, setTplSel] = useState("");
  const [casoSel, setCasoSel] = useState("");
  const [auditoria, setAuditoria] = useState<string | null>(null);
  const [auditando, setAuditando] = useState(false);
  const [printDoc, setPrintDoc] = useState<LegalDoc | null>(null);

  // Dispara a impressão somente depois que a .print-view estiver renderizada
  useEffect(() => {
    if (!printDoc) return;
    const t = window.setTimeout(() => {
      window.print();
      setPrintDoc(null);
    }, 150);
    return () => window.clearTimeout(t);
  }, [printDoc]);

  const validacaoLabel = (doc: LegalDoc) => {
    const v = doc.validacao_juridica;
    if (!v || v.status === "sem_validacao")
      return { label: "Sem validação", cls: "bg-slate-100 text-slate-600" };
    if (v.apto_fluxo)
      return {
        label: `Validada ${v.score ?? ""}/100`,
        cls: "bg-success-100 text-success-700",
      };
    if (v.status === "pendente_revisao")
      return {
        label: `Revisão pendente ${v.score ?? ""}/100`,
        cls: "bg-warn-100 text-warn-700",
      };
    if (v.status === "score_baixo")
      return {
        label: `Score baixo ${v.score ?? ""}/100`,
        cls: "bg-danger-100 text-danger-700",
      };
    return { label: "Bloqueada", cls: "bg-danger-100 text-danger-700" };
  };

  const validarPeca = async (doc: LegalDoc) => {
    setAuditando(true);
    setAuditoria(null);
    try {
      const { data } = await api.post(`/legal-docs/${doc.id}/validar`);
      setAuditoria(
        `VALIDAÇÃO JURÍDICA\nVeredito: ${data.veredito}\nScore: ${data.score_confianca}/100\nLog HITL: ${data.ai_log_id}\n\n${data.resposta}\n\n${data.aviso}`,
      );
      load();
    } catch (e: unknown) {
      toast.error(detalheErro(e, "Falha na validação jurídica"));
    } finally {
      setAuditando(false);
    }
  };

  const [erro, setErro] = useState(false);

  // Modo Caso: `?caso=` na URL vence; sem query, o caso ativo preenche.
  // GET /legal-docs/ já aceita case_id (fecha o GAP do link_modulo da jornada).
  const { casoFiltro, casoFiltroNome, removerFiltro } = useCasoFiltro();

  // ── Gate da Ficha de Triagem (só quando há caso vinculado) ──────────
  // Sem caso (geração avulsa) a ficha NÃO é exigida. Com caso, a peça só é
  // liberada após a ficha estar "confirmada". O 409 do backend é o fallback.
  const [fichaStatus, setFichaStatus] = useState<FichaStatus>("rascunho");
  const [fichaCampos, setFichaCampos] = useState<FichaTriagemCampos | null>(
    null,
  );
  const [refreshFicha, setRefreshFicha] = useState(0);
  const fichaRef = useRef<HTMLDivElement>(null);
  const fichaConfirmada = fichaStatus === "confirmada";

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

  // Abre o gerador de IA respeitando o gate: com caso e sem ficha confirmada,
  // leva o usuário à ficha em vez de abrir o modal.
  const abrirGeradorIA = () => {
    if (casoFiltro && !fichaConfirmada) {
      irParaFicha();
      return;
    }
    setModalIA(true);
  };

  // Fallback: backend barrou a geração (409 need_ficha_triagem).
  const onNeedFicha = useCallback(() => {
    setModalIA(false);
    setFichaStatus("rascunho");
    setRefreshFicha((n) => n + 1);
    setTimeout(irParaFicha, 60);
  }, [irParaFicha]);

  const load = () => {
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
  };
  useEffect(() => {
    load();
  }, [casoFiltro]);

  const salvar = async () => {
    if (!form.titulo || !form.conteudo) {
      toast.error("Título e conteúdo obrigatórios");
      return;
    }
    setSalvando(true);
    try {
      // Modo Caso: peça manual criada com o filtro ativo nasce vinculada ao caso.
      await api.post("/legal-docs/", {
        ...form,
        case_id: form.case_id ?? casoFiltro ?? null,
      });
      setModal(false);
      setForm({ tipo_peca: "peticao_inicial", ai_generated: false });
      toast.success("Peça criada como rascunho");
      load();
    } catch (e: unknown) {
      toast.error(detalheErro(e, "Erro ao salvar a peça"));
    } finally {
      setSalvando(false);
    }
  };

  const abrirDetalhe = async (id: string) => {
    try {
      const { data } = await api.get(`/legal-docs/${id}`);
      setView(data);
    } catch (e: unknown) {
      toast.error(detalheErro(e, "Falha ao carregar a peça"));
    }
  };

  const registrarRevisao = async (aprovado: boolean) => {
    if (!revisao) return;
    try {
      await api.post(`/legal-docs/${revisao.doc.id}/revisar`, {
        aprovado,
        notas: revisao.notas,
      });
      toast.success(
        aprovado
          ? "Revisão registrada — peça marcada como corrigida"
          : "Revisão reprovada — peça devolvida para revisão",
      );
      setRevisao(null);
      load();
    } catch (e: unknown) {
      toast.error(detalheErro(e, "Falha ao registrar a revisão"));
    }
  };

  // BUG-08 (HITL): aprovação humana obrigatória de peças geradas por IA.
  // Único caminho para aprovar peça de IA; exige observações não vazias.
  // Um só ato no backend (POST /conferir-e-assinar): valida juridicamente se
  // preciso, registra a revisão HITL e assina — tudo numa transação.
  const aprovarPeca = async () => {
    if (!aprovacao) return;
    const observacoes = aprovacao.observacoes.trim();
    if (!observacoes) return;
    setAprovando(true);
    try {
      await api.post(`/legal-docs/${aprovacao.doc.id}/conferir-e-assinar`, {
        observacoes,
      });
      setAprovacao(null);
      toast.success("Peça conferida e assinada com revisão humana registrada");
      load();
    } catch (e: unknown) {
      toast.error(detalheErro(e, "Falha ao conferir e assinar a peça"));
    } finally {
      setAprovando(false);
    }
  };

  const avancarStatus = async (doc: LegalDoc, status: string) => {
    // FLX-070: "protocolada" exige comprovante registrado ANTES (o backend
    // devolve 422 no PATCH direto) — desvia para o fluxo de protocolo.
    if (status === "protocolada") {
      await iniciarProtocolo(doc);
      return;
    }
    try {
      await api.patch(`/legal-docs/${doc.id}`, { status });
      const etapa = FILA.find((s) => s.key === status);
      toast.success(`Peça movida para "${etapa?.label ?? status}"`);
      load();
    } catch (e: unknown) {
      toast.error(detalheErro(e, "Falha ao mudar o status da peça"));
    }
  };

  // ── FLX-070: registrar protocolo → status "protocolada" ────────────────
  const [protocolo, setProtocolo] = useState<{
    doc: LegalDoc;
    numero: string;
    tribunal: string;
    data: string;
  } | null>(null);
  const [protocolando, setProtocolando] = useState(false);

  // Se a peça já tem numero_protocolo (a listagem não traz; o detalhe sim),
  // pula o modal e vai direto ao PATCH de status. Cancelar o modal não move.
  const iniciarProtocolo = async (doc: LegalDoc) => {
    try {
      const { data } = await api.get<LegalDoc>(`/legal-docs/${doc.id}`);
      if (temProtocoloRegistrado(data)) {
        await api.patch(`/legal-docs/${doc.id}`, { status: "protocolada" });
        toast.success('Peça movida para "Protocolada"');
        load();
        return;
      }
      setProtocolo({ doc, numero: "", tribunal: "", data: "" });
    } catch (e: unknown) {
      toast.error(
        mensagemErroProtocolo(
          statusErro(e),
          detalheBruto(e),
          'Falha ao mover a peça para "Protocolada"',
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
      // 1) registra o comprovante (número/tribunal/data) na peça
      await api.patch(`/legal-docs/${protocolo.doc.id}/protocolo`, payload);
    } catch (e: unknown) {
      // Peça segue onde estava — modal aberto para corrigir e tentar de novo.
      toast.error(mensagemErroProtocolo(statusErro(e), detalheBruto(e)));
      setProtocolando(false);
      return;
    }
    try {
      // 2) só então move o status (gates de HITL/validação continuam valendo)
      await api.patch(`/legal-docs/${protocolo.doc.id}`, {
        status: "protocolada",
      });
      toast.success('Protocolo registrado — peça movida para "Protocolada"');
    } catch (e: unknown) {
      // Protocolo JÁ registrado: um novo "Protocolar" pula o modal e só move.
      toast.error(
        detalheErro(
          e,
          "Protocolo registrado, mas não foi possível mover o status. Tente novamente.",
        ),
      );
    } finally {
      setProtocolando(false);
      setProtocolo(null);
      load();
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
      // Modo Caso: pré-seleciona o caso filtrado ao gerar de template.
      setCasoSel((prev) => prev || casoFiltro || "");
      setTplModal(true);
    } catch (e: unknown) {
      toast.error(detalheErro(e, "Falha ao carregar templates e casos"));
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
    } catch (e: unknown) {
      toast.error(detalheErro(e, "Falha ao gerar a peça do template"));
    }
  };

  // Peça ainda não aprovada baixa o PDF de LEITURA (/pdf-minuta, marcado como
  // minuta, sem gate de protocolo) — o advogado precisa ler antes de assinar.
  // Aprovada/final/protocolada segue no PDF de protocolo (/pdf, com gates).
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
    } catch (e: unknown) {
      toast.error((await blobErrorDetail(e)) || "Falha ao gerar o PDF.");
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
    } catch (e: unknown) {
      toast.error(detalheErro(e, "Falha ao exportar DOCX. Tente novamente."));
    }
  };

  // Geração cara (weasyprint + mesclagem de anexos) e rate-limited (5/min):
  // trava o botão da linha durante a chamada para evitar disparo duplo.
  const [gerandoVL, setGerandoVL] = useState<string | null>(null);

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
    } catch (e: unknown) {
      toast.error(
        (await blobErrorDetail(e)) ||
          "Falha ao gerar o documento único de impressão.",
      );
    } finally {
      setGerandoVL(null);
    }
  };

  const imprimirPeca = async (doc: LegalDoc) => {
    try {
      // A listagem pode não trazer o conteúdo completo — busca a peça inteira
      const { data } = await api.get(`/legal-docs/${doc.id}`);
      setPrintDoc(data);
    } catch (e: unknown) {
      toast.error(detalheErro(e, "Falha ao carregar a peça para impressão."));
    }
  };

  const checarJurisprudencia = async (doc: LegalDoc) => {
    setAuditando(true);
    setAuditoria(null);
    try {
      const { data } = await api.get(
        `/legal-docs/${doc.id}/jurisprudencia-check`,
      );
      const problemas = data.problemas?.length
        ? data.problemas.map((p: string) => `- ${p}`).join("\n")
        : "Nenhum problema encontrado.";
      const validadas = data.citacoes_validadas?.length
        ? data.citacoes_validadas.join("\n")
        : "Nenhuma citação validada detectada.";
      setAuditoria(
        `CHECK DE JURISPRUDENCIA\nStatus: ${data.apto ? "APTA" : "BLOQUEADA"}\n\nProblemas:\n${problemas}\n\nValidadas:\n${validadas}\n\nRegra: ${data.regra}`,
      );
    } catch (e: unknown) {
      toast.error(detalheErro(e, "Falha na checagem de jurisprudencia"));
    } finally {
      setAuditando(false);
    }
  };

  const auditarIA = async (doc: LegalDoc) => {
    setAuditando(true);
    setAuditoria(null);
    try {
      // Envia apenas o id — o backend busca o conteúdo com RBAC/ownership.
      const { data } = await api.post("/ai/auditar-peca", {
        peca_id: doc.id,
        tipo_peca: doc.tipo_peca,
      });
      const aviso = data.aviso || data.aviso_hitl;
      setAuditoria(
        (data.resposta ?? data.conteudo) + (aviso ? "\n\n" + aviso : ""),
      );
    } catch (e: unknown) {
      toast.error(detalheErro(e, "IA indisponível"));
    } finally {
      setAuditando(false);
    }
  };

  // ── Fila de produção: agrupa pelas etapas reais do backend ────────────────
  const docs = data && Array.isArray(data.data) ? data.data : [];
  const grupos = FILA.map((s) => ({
    ...s,
    itens: docs.filter((p) => p.status === s.key),
  }));
  // Defensivo: status fora do enum conhecido (nunca some da tela).
  const foraFila = docs.filter((p) => !FILA.some((s) => s.key === p.status));

  // Origem manual/IA + estado da revisão humana (HITL) — badge compartilhada.
  const origemBadge = (p: LegalDoc) =>
    p.ai_generated ? (
      p.human_reviewed ? (
        <span className="badge bg-success-100 text-success-700 gap-1">
          <ShieldCheck size={12} /> IA revisada
        </span>
      ) : (
        <span className="badge bg-warn-100 text-warn-700 gap-1">
          <Sparkles size={12} /> IA — aguarda revisão
        </span>
      )
    ) : (
      <span className="text-xs text-slate-400">manual</span>
    );

  // Link para o caso vinculado (a listagem só expõe case_id, sem título).
  const casoLink = (p: LegalDoc) =>
    p.case_id ? (
      <Link
        to={`/casos/${p.case_id}`}
        className="inline-flex items-center gap-1 text-xs text-primary-700 hover:underline"
        title="Abrir o caso vinculado"
      >
        <FolderOpen size={13} /> Ver caso
      </Link>
    ) : (
      <span className="text-xs text-slate-400">sem caso</span>
    );

  const podeRevisarAprovar = (p: LegalDoc) =>
    p.ai_generated && !STATUS_POS_APROVACAO.has(p.status);

  const podeAprovarDireto = (p: LegalDoc) =>
    (p.human_reviewed || !p.ai_generated) &&
    p.status === "corrigida" &&
    p.validacao_juridica?.apto_fluxo;

  // FLX-070: o registro de protocolo aceita peça aprovada/final (backend:
  // STATUS_EXIGE_REVISAO) — daí o botão nessas duas etapas da fila.
  const podeProtocolar = (p: LegalDoc) =>
    p.status === "aprovada" || p.status === "final";

  return (
    <div>
      <PageHeader
        title="Peças Jurídicas"
        subtitle={`${data?.total ?? 0} peças`}
        actions={
          <div className="flex gap-2">
            <button className="btn-ghost" onClick={abrirTpl}>
              <LayoutTemplate size={16} /> De template
            </button>
            <button
              onClick={abrirGeradorIA}
              disabled={!iaDisponivel}
              title={iaDisponivel ? undefined : ROTULO_IA_NAO_ATIVADA}
              className="btn btn-primary flex items-center gap-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Sparkles size={15} />
              {iaDisponivel ? "Gerar com IA" : "IA não ativada"}
            </button>
            <button className="btn-gold" onClick={() => setModal(true)}>
              <Plus size={16} /> Nova peça
            </button>
          </div>
        }
      />

      {casoFiltro && (
        <div className="mb-4">
          <CaseFilterChip nome={casoFiltroNome} onRemove={removerFiltro} />
        </div>
      )}

      {/* Ficha de triagem: gate obrigatório antes de gerar peça com caso. */}
      {casoFiltro && (
        <div className="mb-6 space-y-4">
          {fichaConfirmada && fichaCampos && (
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
          )}
          {!fichaConfirmada && (
            <div className="flex items-start gap-2 rounded-lg border border-warn-200 bg-warn-50 px-4 py-3 text-xs text-warn-800">
              <ClipboardCheck size={15} className="mt-0.5 shrink-0" />
              <span>
                Este caso ainda não tem ficha de triagem confirmada. Preencha e
                confirme a ficha abaixo para liberar a geração de peças.
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
          // Filtro de caso ativo: peças sem vínculo (ex.: demonstrativos das
          // calculadoras) ficam ocultas — oferecer a visão completa evita o
          // "salvei e sumiu" relatado na auditoria de usabilidade.
          <EmptyState
            title="Nenhuma peça neste caso"
            message="Você está vendo apenas as peças do caso filtrado. Peças sem vínculo (como demonstrativos de calculadoras) aparecem na lista completa."
            action={
              <Button variant="secondary" onClick={removerFiltro}>
                Ver todas as peças
              </Button>
            }
          />
        ) : (
          <Empty message="Nenhuma peça cadastrada" />
        )
      ) : (
        <>
          {/* Contadores da fila de produção — todas as etapas do enum, mesmo
            vazias, para o fluxo completo ficar visível de relance. */}
          <div className="mb-4 flex flex-wrap items-center gap-2">
            {grupos.map((g) => (
              <span
                key={g.key}
                className={`badge ${
                  g.itens.length
                    ? "bg-primary-100 text-primary-700"
                    : "bg-slate-100 text-slate-400"
                }`}
                title={g.desc}
              >
                {g.label}: {g.itens.length}
              </span>
            ))}
            {foraFila.length > 0 && (
              <span className="badge bg-slate-100 text-slate-500">
                Outros: {foraFila.length}
              </span>
            )}
          </div>

          {[
            ...grupos.filter((g) => g.itens.length > 0),
            ...(foraFila.length > 0
              ? [
                  {
                    key: "outros",
                    label: "Outros status",
                    desc: "Status fora da fila padrão de produção",
                    itens: foraFila,
                  },
                ]
              : []),
          ].map((g) => (
            <section key={g.key} className="mb-6">
              <div className="mb-2 flex items-baseline gap-2">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-navy">
                  {g.label}
                </h2>
                <span className="text-xs text-slate-400">
                  {g.itens.length} · {g.desc}
                </span>
              </div>

              {/* Mobile (<md): cards empilhados com os fluxos essenciais —
                visualizar, baixar e revisar/aprovar (HITL) usáveis em 390px. */}
              <div className="space-y-2 md:hidden">
                {g.itens.map((p) => (
                  <div key={p.id} className="card p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="font-medium text-navy break-words">
                          {p.titulo}
                        </div>
                        {p.codigo_peca && (
                          <div className="mt-1">
                            <Badge tone="slate" className="font-mono">
                              {p.codigo_peca}
                            </Badge>
                          </div>
                        )}
                        <div className="mt-0.5 text-xs capitalize text-slate-400">
                          {p.tipo_peca.replace(/_/g, " ")} · v{p.versao}.0 ·{" "}
                          {fmtDate(p.created_at)}
                        </div>
                      </div>
                      <StatusBadge value={p.status} />
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      {origemBadge(p)}
                      {(() => {
                        const v = validacaoLabel(p);
                        return (
                          <span className={`badge ${v.cls}`}>{v.label}</span>
                        );
                      })()}
                      {casoLink(p)}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        className="btn-ghost px-2.5 py-1.5 text-xs"
                        onClick={() => abrirDetalhe(p.id)}
                      >
                        <Eye size={14} /> Ver
                      </button>
                      <button
                        className="btn-ghost px-2.5 py-1.5 text-xs"
                        onClick={() => baixarPdf(p)}
                      >
                        <FileDown size={14} /> PDF
                      </button>
                      {p.ai_generated && !p.human_reviewed && (
                        <button
                          className="btn-ghost px-2.5 py-1.5 text-xs text-warn-700"
                          onClick={() => setRevisao({ doc: p, notas: "" })}
                        >
                          Revisar
                        </button>
                      )}
                      {podeRevisarAprovar(p) && (
                        <button
                          className="btn-primary px-2.5 py-1.5 text-xs"
                          onClick={() =>
                            setAprovacao({ doc: p, observacoes: "" })
                          }
                        >
                          <ShieldCheck size={14} /> Revisar e Aprovar
                        </button>
                      )}
                      {podeAprovarDireto(p) && (
                        <button
                          className="btn-ghost px-2.5 py-1.5 text-xs text-success-700"
                          onClick={() => avancarStatus(p, "aprovada")}
                        >
                          Aprovar
                        </button>
                      )}
                      {podeProtocolar(p) && (
                        <button
                          className="btn-ghost px-2.5 py-1.5 text-xs text-primary-700"
                          onClick={() => avancarStatus(p, "protocolada")}
                        >
                          <Stamp size={14} /> Protocolar
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              <div className="card hidden overflow-x-auto md:block">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-left text-xs uppercase text-slate-400">
                    <tr>
                      <th className="px-4 py-3">Título</th>
                      <th className="px-4 py-3">Tipo</th>
                      <th className="px-4 py-3">Caso</th>
                      <th className="px-4 py-3">Origem</th>
                      <th className="px-4 py-3">Validação</th>
                      <th className="px-4 py-3">v</th>
                      <th className="px-4 py-3">Criada</th>
                      <th className="px-4 py-3"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {g.itens.map((p) => (
                      <tr key={p.id} className="hover:bg-slate-50">
                        <td className="px-4 py-3 font-medium text-navy">
                          <div>{p.titulo}</div>
                          {p.codigo_peca && (
                            <Badge
                              tone="slate"
                              className="mt-1 font-mono font-normal"
                            >
                              {p.codigo_peca}
                            </Badge>
                          )}
                        </td>
                        <td className="px-4 py-3 text-xs capitalize">
                          {p.tipo_peca.replace(/_/g, " ")}
                        </td>
                        <td className="px-4 py-3">{casoLink(p)}</td>
                        <td className="px-4 py-3">{origemBadge(p)}</td>
                        <td className="px-4 py-3">
                          {(() => {
                            const v = validacaoLabel(p);
                            return (
                              <span className={`badge ${v.cls}`}>
                                {v.label}
                              </span>
                            );
                          })()}
                        </td>
                        <td className="px-4 py-3 text-slate-400">
                          v{p.versao}.0
                        </td>
                        <td className="px-4 py-3 text-slate-400">
                          {fmtDate(p.created_at)}
                        </td>
                        <td className="px-4 py-3 flex gap-1">
                          <button
                            className="btn-ghost px-2 py-1"
                            onClick={() => abrirDetalhe(p.id)}
                          >
                            <Eye size={15} />
                          </button>
                          <button
                            className="btn-ghost px-2 py-1"
                            title="Baixar PDF timbrado"
                            onClick={() => baixarPdf(p)}
                          >
                            <FileDown size={15} />
                          </button>
                          <button
                            className="btn-ghost px-2 py-1 text-xs"
                            title="Exportar DOCX"
                            onClick={() => baixarDocx(p)}
                          >
                            <FileDown size={15} /> DOCX
                          </button>
                          <button
                            className="btn-ghost px-2 py-1 text-xs"
                            title="Documento único de impressão (peça + anexos com capas Visual Law)"
                            onClick={() => baixarDocumentoUnico(p)}
                            disabled={gerandoVL !== null}
                          >
                            <FileDown size={15} />{" "}
                            {gerandoVL === p.id ? "Gerando..." : "VL"}
                          </button>
                          <button
                            className="btn-ghost px-2 py-1"
                            title="Imprimir peça"
                            onClick={() => imprimirPeca(p)}
                          >
                            <Printer size={15} />
                          </button>
                          <button
                            className="btn-ghost px-2 py-1"
                            title="Checar jurisprudencia validada"
                            onClick={() => checarJurisprudencia(p)}
                          >
                            <ShieldCheck size={15} />
                          </button>
                          <button
                            className="btn-ghost px-2 py-1"
                            title="Auditar com IA"
                            onClick={() => auditarIA(p)}
                          >
                            <SearchCheck size={15} />
                          </button>
                          <button
                            className="btn-ghost px-2 py-1 text-primary-700"
                            title="Validar juridicamente antes de finalizar"
                            onClick={() => validarPeca(p)}
                          >
                            <ShieldCheck size={15} />
                          </button>
                          {p.ai_generated && !p.human_reviewed && (
                            <button
                              className="btn-ghost px-2 py-1 text-warn-700 text-xs"
                              onClick={() => setRevisao({ doc: p, notas: "" })}
                            >
                              Revisar
                            </button>
                          )}
                          {podeRevisarAprovar(p) && (
                            <button
                              className="btn-ghost px-2 py-1 text-emerald-700 text-xs"
                              title="Revisão do advogado obrigatória para aprovar peça de IA"
                              onClick={() =>
                                setAprovacao({ doc: p, observacoes: "" })
                              }
                            >
                              Revisar e Aprovar
                            </button>
                          )}
                          {podeAprovarDireto(p) && (
                            <button
                              className="btn-ghost px-2 py-1 text-success-700 text-xs"
                              onClick={() => avancarStatus(p, "aprovada")}
                            >
                              Aprovar
                            </button>
                          )}
                          {podeProtocolar(p) && (
                            <button
                              className="btn-ghost px-2 py-1 text-primary-700 text-xs"
                              title="Registrar o protocolo e marcar como protocolada"
                              onClick={() => avancarStatus(p, "protocolada")}
                            >
                              <Stamp size={15} /> Protocolar
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ))}
        </>
      )}

      {/* Nova peça */}
      <Modal
        open={modal}
        onClose={() => setModal(false)}
        title="Nova peça"
        wide
      >
        <div className="space-y-4">
          <div className="grid sm:grid-cols-2 gap-4">
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
                onChange={(e) =>
                  setForm({ ...form, tipo_peca: e.target.value })
                }
              >
                {TIPOS.map((t) => (
                  <option key={t} value={t}>
                    {t.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="label">Conteúdo * (markdown)</label>
            <textarea
              className="input min-h-[240px] font-mono text-xs"
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
            Conteúdo gerado/assistido por IA (exigirá revisão antes de aprovar)
          </label>
          {casoFiltro && (
            <p className="text-xs text-slate-500">
              A peça será vinculada ao caso filtrado
              {casoFiltroNome ? ` (${casoFiltroNome})` : ""} e nascerá como
              rascunho na fila de produção.
            </p>
          )}
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

      {/* Visualizar */}
      <Modal
        open={!!view}
        onClose={() => setView(null)}
        title={view?.titulo || ""}
        wide
      >
        {view?.ai_generated && !view?.human_reviewed && (
          <div className="mb-3 p-3 rounded-lg bg-warn-50 text-warn-800 text-xs font-medium">
            ⚠️ Peça gerada por IA — revisão humana obrigatória antes de aprovar
            (Provimento OAB 205/2021)
          </div>
        )}
        {view?.validacao_juridica && (
          <div className="mb-3 p-3 rounded-lg bg-slate-50 border border-black/[0.05] text-xs text-slate-700">
            <strong>Validação jurídica:</strong>{" "}
            {view.validacao_juridica.status} · Score{" "}
            {view.validacao_juridica.score ?? "—"}/
            {view.validacao_juridica.score_minimo ?? 75} · Revisão do advogado:{" "}
            {view.validacao_juridica.hitl ?? "pendente"}
            {view.validacao_juridica.veredito && (
              <> · Veredito: {view.validacao_juridica.veredito}</>
            )}
            <br />
            {view.validacao_juridica.motivo}
          </div>
        )}
        {view?.notas_revisao && (
          <div className="mb-3 p-3 rounded-lg bg-success-50 border border-black/[0.05] text-xs text-slate-700">
            <strong>Notas da revisão humana:</strong> {view.notas_revisao}
          </div>
        )}
        {view?.case_id && (
          <div className="mb-3 text-xs">
            <Link
              to={`/casos/${view.case_id}`}
              className="inline-flex items-center gap-1 text-primary-700 hover:underline"
            >
              <FolderOpen size={13} /> Abrir o caso vinculado
            </Link>
          </div>
        )}
        <Markdown source={view?.conteudo} className="text-sm text-slate-700" />
      </Modal>

      {/* Revisão HITL */}
      <Modal
        open={!!revisao}
        onClose={() => setRevisao(null)}
        title="Revisão humana (HITL)"
      >
        <p className="text-sm text-slate-600 mb-3">
          Registre sua revisão da peça <strong>{revisao?.doc.titulo}</strong>.
          Ao aprovar, você assume responsabilidade técnica pelo conteúdo.
        </p>
        <textarea
          className="input min-h-[100px]"
          placeholder="Notas da revisão (opcional)"
          value={revisao?.notas || ""}
          onChange={(e) =>
            revisao && setRevisao({ ...revisao, notas: e.target.value })
          }
        />
        <div className="flex justify-end gap-2 mt-4">
          <button
            className="btn-danger"
            onClick={() => registrarRevisao(false)}
          >
            Reprovar
          </button>
          <button
            className="btn-primary"
            onClick={() => registrarRevisao(true)}
          >
            <ShieldCheck size={15} /> Aprovar revisão
          </button>
        </div>
      </Modal>
      {/* Aprovação HITL de peça gerada por IA (BUG-08) */}
      <Modal
        open={!!aprovacao}
        onClose={() => setAprovacao(null)}
        title="Revisar e aprovar peça de IA"
      >
        <p className="text-sm text-slate-600 mb-3">
          Você está prestes a aprovar a peça{" "}
          <strong>{aprovacao?.doc.titulo}</strong>, gerada com auxílio de IA. A
          revisão humana é obrigatória: descreva as observações da sua análise.
          Ao aprovar, você assume a responsabilidade técnica pelo conteúdo.
        </p>
        <textarea
          className="input min-h-[120px]"
          placeholder="Observações da revisão (obrigatório)"
          value={aprovacao?.observacoes || ""}
          onChange={(e) =>
            aprovacao &&
            setAprovacao({ ...aprovacao, observacoes: e.target.value })
          }
        />
        <div className="flex justify-end gap-2 mt-4">
          <button className="btn-ghost" onClick={() => setAprovacao(null)}>
            Cancelar
          </button>
          <button
            className="btn-primary"
            disabled={aprovando || !aprovacao?.observacoes.trim()}
            onClick={aprovarPeca}
          >
            <ShieldCheck size={15} />{" "}
            {aprovando ? "Aprovando..." : "Aprovar peça"}
          </button>
        </div>
      </Modal>
      {/* FLX-070: registrar protocolo antes de mover para "Protocolada".
        Cancelar/fechar NÃO move a peça — nenhum PATCH acontece sem confirmar. */}
      <Modal
        open={!!protocolo}
        onClose={() => setProtocolo(null)}
        title="Registrar protocolo"
      >
        <p className="text-sm text-slate-600 mb-3">
          Para mover <strong>{protocolo?.doc.titulo}</strong> para
          &quot;Protocolada&quot;, registre o comprovante do peticionamento
          (feito fora do sistema, ex.: PJe/eproc). O número do protocolo é a
          prova de tempestividade da peça.
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
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="label">Tribunal/sistema (opcional)</label>
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
              <label className="label">Data do protocolo (opcional)</label>
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
              <p className="mt-1 text-xs text-slate-400">
                Sem data, o registro assume o momento atual.
              </p>
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <button className="btn-ghost" onClick={() => setProtocolo(null)}>
            Cancelar
          </button>
          <button
            className="btn-primary"
            disabled={protocolando || !protocolo?.numero.trim()}
            onClick={confirmarProtocolo}
          >
            <Stamp size={15} />{" "}
            {protocolando ? "Registrando..." : "Registrar e protocolar"}
          </button>
        </div>
      </Modal>
      {/* Modal: gerar de template */}
      <Modal
        open={tplModal}
        onClose={() => setTplModal(false)}
        title="Gerar peça de template"
      >
        <div className="space-y-3">
          <select
            className="input"
            value={tplSel}
            onChange={(e) => setTplSel(e.target.value)}
          >
            <option value="">Escolha o template…</option>
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
            As variáveis ({"{{cliente_nome}}"}, {"{{numero_processo}}"}…) serão
            preenchidas com os dados do caso. A peça nasce como rascunho.
          </p>
          <button
            className="btn-primary w-full justify-center"
            onClick={gerarDeTemplate}
          >
            Gerar rascunho
          </button>
        </div>
      </Modal>

      {/* Modal: resultado da auditoria IA */}
      <Modal
        open={!!auditoria || auditando}
        onClose={() => {
          setAuditoria(null);
        }}
        title="Controle de qualidade da peça"
        wide
      >
        {auditando ? (
          <Spinner />
        ) : (
          <Markdown
            source={auditoria}
            className="text-sm max-h-[60vh] overflow-auto"
          />
        )}
      </Modal>
      <PecaGeneratorModal
        open={modalIA}
        onClose={() => setModalIA(false)}
        caseId={casoFiltro}
        onNeedFicha={onNeedFicha}
        onConcluido={(_logId, _doc) => {
          setModalIA(false);
          load();
        }}
      />

      {/* View de impressão — invisível em tela, única coisa visível no print */}
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

// Semáforo de risco reaproveitando os tons do DS (Badge).
const RISCO_TONE: Record<
  FichaTriagemCampos["risco_processual"],
  "green" | "amber" | "red"
> = {
  baixo: "green",
  medio: "amber",
  alto: "red",
};

// valor_causa é string livre; formata como moeda quando for numérico.
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
