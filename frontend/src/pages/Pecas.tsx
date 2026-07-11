import { useEffect, useState } from "react";
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
  fmtDate,
} from "../components/UI";
import PecaGeneratorModal from "../components/PecaGeneratorModal";
import CaseFilterChip from "../components/CaseFilterChip";
import { useCasoFiltro } from "../contexts/useCasoFiltro";

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

export default function Pecas() {
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
        label: `Validar HITL ${v.score ?? ""}/100`,
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
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha na validação jurídica");
    } finally {
      setAuditando(false);
    }
  };

  const [erro, setErro] = useState(false);

  // Modo Caso: `?caso=` na URL vence; sem query, o caso ativo preenche.
  // GET /legal-docs/ já aceita case_id (fecha o GAP do link_modulo da jornada).
  const { casoFiltro, casoFiltroNome, removerFiltro } = useCasoFiltro();

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
      await api.post("/legal-docs/", form);
      setModal(false);
      setForm({ tipo_peca: "peticao_inicial", ai_generated: false });
      load();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro");
    } finally {
      setSalvando(false);
    }
  };

  const abrirDetalhe = async (id: string) => {
    const { data } = await api.get(`/legal-docs/${id}`);
    setView(data);
  };

  const registrarRevisao = async (aprovado: boolean) => {
    if (!revisao) return;
    await api.post(`/legal-docs/${revisao.doc.id}/revisar`, {
      aprovado,
      notas: revisao.notas,
    });
    setRevisao(null);
    load();
  };

  // BUG-08 (HITL): aprovação humana obrigatória de peças geradas por IA.
  // Único caminho para aprovar peça de IA; exige observações não vazias.
  const aprovarPeca = async () => {
    if (!aprovacao) return;
    const observacoes = aprovacao.observacoes.trim();
    if (!observacoes) return;
    setAprovando(true);
    try {
      await api.patch(`/legal-docs/${aprovacao.doc.id}/aprovar`, {
        observacoes,
      });
      setAprovacao(null);
      load();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao aprovar peça");
    } finally {
      setAprovando(false);
    }
  };

  const avancarStatus = async (doc: LegalDoc, status: string) => {
    try {
      await api.patch(`/legal-docs/${doc.id}`, { status });
      load();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro");
    }
  };

  const abrirTpl = async () => {
    const [t, c] = await Promise.all([
      api.get("/templates/"),
      api.get("/cases/", { params: { page_size: 100 } }),
    ]);
    setTemplates(t.data.data);
    setCasos(c.data.data);
    // Modo Caso: pré-seleciona o caso filtrado ao gerar de template.
    setCasoSel((prev) => prev || casoFiltro || "");
    setTplModal(true);
  };

  const gerarDeTemplate = async () => {
    if (!tplSel || !casoSel) {
      toast.error("Escolha template e caso");
      return;
    }
    await api.post(`/templates/${tplSel}/gerar`, { case_id: casoSel });
    setTplModal(false);
    load();
  };

  const baixarPdf = async (doc: LegalDoc) => {
    const r = await api.get(`/legal-docs/${doc.id}/pdf`, {
      responseType: "blob",
    });
    const url = URL.createObjectURL(r.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${doc.titulo}.pdf`;
    a.click();
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
      toast.error(
        e.response?.data?.detail || "Falha ao exportar DOCX. Tente novamente.",
      );
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
    } catch (e: any) {
      let detail = e.response?.data?.detail;
      // responseType blob: erros 422/503 chegam como Blob JSON — extrai o detail
      if (!detail && e.response?.data instanceof Blob) {
        try {
          detail = JSON.parse(await e.response.data.text())?.detail;
        } catch {
          /* corpo não-JSON — usa mensagem padrão */
        }
      }
      const msg =
        typeof detail === "object" && detail !== null
          ? (detail.mensagem ?? JSON.stringify(detail).slice(0, 200))
          : detail;
      toast.error(msg || "Falha ao gerar o documento único de impressão.");
    } finally {
      setGerandoVL(null);
    }
  };

  const imprimirPeca = async (doc: LegalDoc) => {
    try {
      // A listagem pode não trazer o conteúdo completo — busca a peça inteira
      const { data } = await api.get(`/legal-docs/${doc.id}`);
      setPrintDoc(data);
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Falha ao carregar a peça para impressão.",
      );
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
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail?.mensagem ||
          e.response?.data?.detail ||
          "Falha na checagem de jurisprudencia",
      );
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
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "IA indisponível");
    } finally {
      setAuditando(false);
    }
  };

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
              onClick={() => setModalIA(true)}
              className="btn btn-primary flex items-center gap-2"
            >
              <Sparkles size={15} />
              Gerar com IA
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
      ) : data.data.length === 0 ? (
        <Empty message="Nenhuma peça cadastrada" />
      ) : (
        <>
        {/* Mobile (<md): cards empilhados com os fluxos essenciais —
            visualizar, baixar e revisar/aprovar (HITL) usáveis em 390px. */}
        <div className="space-y-2 md:hidden">
          {(Array.isArray(data.data) ? data.data : []).map((p) => (
            <div key={p.id} className="card p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-medium text-navy break-words">
                    {p.titulo}
                  </div>
                  <div className="mt-0.5 text-xs capitalize text-slate-400">
                    {p.tipo_peca.replace(/_/g, " ")} · v{p.versao} ·{" "}
                    {fmtDate(p.created_at)}
                  </div>
                </div>
                <StatusBadge value={p.status} />
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {p.ai_generated ? (
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
                )}
                {(() => {
                  const v = validacaoLabel(p);
                  return <span className={`badge ${v.cls}`}>{v.label}</span>;
                })()}
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
                {p.ai_generated &&
                  p.status !== "aprovada" &&
                  p.status !== "versao_final" && (
                    <button
                      className="btn-primary px-2.5 py-1.5 text-xs"
                      onClick={() => setAprovacao({ doc: p, observacoes: "" })}
                    >
                      <ShieldCheck size={14} /> Revisar e Aprovar
                    </button>
                  )}
                {(p.human_reviewed || !p.ai_generated) &&
                  p.status === "corrigida" &&
                  p.validacao_juridica?.apto_fluxo && (
                    <button
                      className="btn-ghost px-2.5 py-1.5 text-xs text-success-700"
                      onClick={() => avancarStatus(p, "aprovada")}
                    >
                      Aprovar
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
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Origem</th>
                <th className="px-4 py-3">Validação</th>
                <th className="px-4 py-3">v</th>
                <th className="px-4 py-3">Criada</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(Array.isArray(data.data) ? data.data : []).map((p) => (
                <tr key={p.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium text-navy">
                    {p.titulo}
                  </td>
                  <td className="px-4 py-3 text-xs capitalize">
                    {p.tipo_peca.replace(/_/g, " ")}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge value={p.status} />
                  </td>
                  <td className="px-4 py-3">
                    {p.ai_generated ? (
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
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {(() => {
                      const v = validacaoLabel(p);
                      return (
                        <span className={`badge ${v.cls}`}>{v.label}</span>
                      );
                    })()}
                  </td>
                  <td className="px-4 py-3 text-slate-400">v{p.versao}</td>
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
                      <FileDown size={15} /> {gerandoVL === p.id ? "Gerando..." : "VL"}
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
                    {p.ai_generated &&
                      p.status !== "aprovada" &&
                      p.status !== "versao_final" && (
                        <button
                          className="btn-ghost px-2 py-1 text-emerald-700 text-xs"
                          title="Revisão humana obrigatória (HITL) para aprovar peça de IA"
                          onClick={() =>
                            setAprovacao({ doc: p, observacoes: "" })
                          }
                        >
                          Revisar e Aprovar
                        </button>
                      )}
                    {(p.human_reviewed || !p.ai_generated) &&
                      p.status === "corrigida" &&
                      p.validacao_juridica?.apto_fluxo && (
                        <button
                          className="btn-ghost px-2 py-1 text-success-700 text-xs"
                          onClick={() => avancarStatus(p, "aprovada")}
                        >
                          Aprovar
                        </button>
                      )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
          <div className="mb-3 p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-700">
            <strong>Validação jurídica:</strong>{" "}
            {view.validacao_juridica.status} · Score{" "}
            {view.validacao_juridica.score ?? "—"}/
            {view.validacao_juridica.score_minimo ?? 75} · HITL{" "}
            {view.validacao_juridica.hitl ?? "pendente"}
            <br />
            {view.validacao_juridica.motivo}
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
