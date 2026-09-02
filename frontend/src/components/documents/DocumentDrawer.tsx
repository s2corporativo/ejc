import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  Download,
  FileClock,
  FileText,
  History,
  Lock,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "../Toast";
import { Spinner } from "../UI";
import { useAuth } from "../../stores/auth";
import {
  ATTENTION_LABEL,
  classifyDocument,
  getDocument,
  getDocumentBlob,
  getDocumentGovernance,
  getDocumentHistory,
  getDocumentVersions,
  publishDocumentToPortal,
  reprocessDocument,
  setDocumentRag,
  updateDocumentGovernance,
  verifyDocumentIntegrity,
  type DocumentClassification,
  type DocumentGovernance,
  type DocumentHistoryResponse,
  type DocumentItem,
  type DocumentVersionResponse,
} from "../../services/documents";
import DocumentStatusBadge from "./DocumentStatusBadge";

type Tab = "documento" | "inteligencia" | "historico" | "governanca";

const SOCIO_PLUS = new Set(["superadmin", "admin", "socio"]);
const ADVOGADO_PLUS = new Set(["superadmin", "admin", "socio", "advogado"]);
const INTERNO = new Set([
  "superadmin",
  "admin",
  "socio",
  "advogado",
  "advogado_auxiliar",
  "estagiario",
]);

const extDe = (nome?: string | null) => {
  const value = nome || "";
  const index = value.lastIndexOf(".");
  return index >= 0 ? value.slice(index).toLowerCase() : "";
};

const fmtData = (value?: string | null) =>
  value
    ? new Intl.DateTimeFormat("pt-BR", {
        dateStyle: "short",
        timeStyle: "short",
      }).format(new Date(value))
    : "—";

const fmtBytes = (value?: number | null) => {
  if (!value) return "—";
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
};

const iaLabel = (status?: string | null) => {
  if (["completed", "concluido"].includes(status || "")) return "Disponível";
  if (["pending", "processing"].includes(status || "")) return "Processando";
  if (["failed", "stale"].includes(status || "")) return "Precisa de atenção";
  return "Não analisado";
};

const integrityLabel = (status?: string | null) => {
  if (["verified", "registered"].includes(status || "")) return "Verificado";
  if (["divergent", "error", "unavailable"].includes(status || "")) return "Atenção";
  return "Verificação pendente";
};

export default function DocumentDrawer({
  documentId,
  onClose,
  onNewVersion,
  onChanged,
}: {
  documentId: string | null;
  onClose: () => void;
  onNewVersion: (document: DocumentItem) => void;
  onChanged: () => void;
}) {
  const user = useAuth((state) => state.user);
  const role = user?.role || "";
  const canGovern = SOCIO_PLUS.has(role);
  const canAnalyze = ADVOGADO_PLUS.has(role);
  const canClassify = INTERNO.has(role);

  const [tab, setTab] = useState<Tab>("documento");
  const [document, setDocument] = useState<DocumentItem | null>(null);
  const [versions, setVersions] = useState<DocumentVersionResponse | null>(null);
  const [history, setHistory] = useState<DocumentHistoryResponse | null>(null);
  const [governance, setGovernance] = useState<DocumentGovernance | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [classification, setClassification] = useState<DocumentClassification | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState(false);
  const [hold, setHold] = useState(false);
  const [holdReason, setHoldReason] = useState("");
  const [retentionDate, setRetentionDate] = useState("");
  const [changeReason, setChangeReason] = useState("");

  const previewKind = useMemo(() => {
    const ext = extDe(document?.filename);
    if (ext === ".pdf") return "pdf";
    if ([".jpg", ".jpeg", ".png"].includes(ext)) return "image";
    return null;
  }, [document?.filename]);

  const ragEnabled = useMemo(
    () => ![null, undefined, "", "not_indexed", "disabled"].includes(document?.rag_status),
    [document?.rag_status],
  );

  useEffect(() => {
    if (!documentId) return;
    let active = true;
    setTab("documento");
    setLoading(true);
    setDocument(null);
    setClassification(null);
    setVersions(null);
    setHistory(null);
    setGovernance(null);
    setPreviewError(false);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);

    Promise.all([
      getDocument(documentId),
      getDocumentVersions(documentId).catch(() => null),
      getDocumentHistory(documentId).catch(() => null),
    ])
      .then(([detail, vers, hist]) => {
        if (!active) return;
        setDocument(detail);
        setVersions(vers);
        setHistory(hist);
      })
      .catch(() => {
        if (active) toast.error("Não foi possível abrir o documento");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    if (canGovern) {
      getDocumentGovernance(documentId)
        .then((gov) => {
          if (!active) return;
          setGovernance(gov);
          setHold(Boolean(gov.legal_hold));
          setHoldReason(gov.legal_hold_reason || "");
          setRetentionDate(gov.retention_until ? gov.retention_until.slice(0, 10) : "");
        })
        .catch(() => {
          if (active) setGovernance(null);
        });
    }

    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId, canGovern]);

  useEffect(
    () => () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    },
    [previewUrl],
  );

  const ensurePreview = async () => {
    if (!document || !previewKind || previewUrl || busy === "preview") return;
    setBusy("preview");
    setPreviewError(false);
    try {
      const blob = await getDocumentBlob(document.id);
      setPreviewUrl(URL.createObjectURL(blob));
    } catch {
      setPreviewError(true);
    } finally {
      setBusy("");
    }
  };

  useEffect(() => {
    if (tab === "documento" && previewKind) void ensurePreview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, previewKind, document?.id]);

  const download = async () => {
    if (!document) return;
    setBusy("download");
    try {
      const blob = await getDocumentBlob(document.id);
      const url = URL.createObjectURL(blob);
      const anchor = window.document.createElement("a");
      anchor.href = url;
      anchor.download = document.filename || document.titulo;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Falha ao baixar o documento");
    } finally {
      setBusy("");
    }
  };

  const suggestType = async () => {
    if (!document) return;
    setBusy("classify");
    try {
      setClassification(await classifyDocument(document.id, false));
    } catch {
      toast.error("Não foi possível analisar o tipo do documento");
    } finally {
      setBusy("");
    }
  };

  const applySuggestedType = async () => {
    if (!document || !classification?.tipo_sugerido) return;
    setBusy("apply-classification");
    try {
      const result = await classifyDocument(document.id, true);
      setDocument((current) =>
        current ? { ...current, tipo: result.tipo_atual || result.tipo_sugerido } : current,
      );
      setClassification(result);
      toast.success("Tipo confirmado");
      onChanged();
    } catch {
      toast.error("Falha ao confirmar o tipo");
    } finally {
      setBusy("");
    }
  };

  const reprocess = async () => {
    if (!document) return;
    setBusy("analysis");
    try {
      await reprocessDocument(document.id);
      setDocument((current) => (current ? { ...current, analysis_status: "pending" } : current));
      toast.success("Análise enviada para processamento");
      onChanged();
    } catch {
      toast.error("Não foi possível iniciar a análise");
    } finally {
      setBusy("");
    }
  };

  const toggleRag = async () => {
    if (!document) return;
    if (!document.case_id) {
      toast.error("Vincule o documento a um caso antes de usá-lo na inteligência");
      return;
    }
    setBusy("rag");
    try {
      await setDocumentRag(document.id, !ragEnabled);
      const detail = await getDocument(document.id);
      setDocument(detail);
      toast.success(
        ragEnabled
          ? "Documento removido da inteligência deste caso"
          : "Documento disponibilizado para a inteligência deste caso",
      );
      onChanged();
    } catch {
      toast.error("Não foi possível alterar o uso na inteligência");
    } finally {
      setBusy("");
    }
  };

  const verifyIntegrity = async () => {
    if (!document) return;
    setBusy("integrity");
    try {
      await verifyDocumentIntegrity(document.id);
      toast.success("Verificação de integridade iniciada");
      onChanged();
    } catch {
      toast.error("Não foi possível iniciar a verificação");
    } finally {
      setBusy("");
    }
  };

  const togglePortal = async () => {
    if (!document) return;
    setBusy("portal");
    try {
      await publishDocumentToPortal(document.id, !document.publicado_portal);
      setDocument((current) =>
        current ? { ...current, publicado_portal: !current.publicado_portal } : current,
      );
      toast.success(
        document.publicado_portal
          ? "Documento retirado do Portal do Cliente"
          : "Documento disponibilizado no Portal do Cliente",
      );
      onChanged();
    } catch {
      toast.error("Não foi possível alterar a publicação no Portal");
    } finally {
      setBusy("");
    }
  };

  const saveGovernance = async () => {
    if (!document || !canGovern) return;
    if (changeReason.trim().length < 5) {
      toast.error("Informe o motivo da alteração de governança");
      return;
    }
    if (hold && holdReason.trim().length < 5) {
      toast.error("Informe o motivo da preservação obrigatória");
      return;
    }
    setBusy("governance");
    try {
      const gov = await updateDocumentGovernance(document.id, {
        retention_until: retentionDate ? `${retentionDate}T23:59:59Z` : null,
        legal_hold: hold,
        legal_hold_reason: hold ? holdReason.trim() : null,
        motivo_alteracao: changeReason.trim(),
      });
      setGovernance(gov);
      setChangeReason("");
      setDocument((current) =>
        current
          ? {
              ...current,
              legal_hold: gov.legal_hold,
              retention_until: gov.retention_until,
            }
          : current,
      );
      toast.success("Governança documental atualizada");
      onChanged();
    } catch {
      toast.error("Não foi possível atualizar a governança");
    } finally {
      setBusy("");
    }
  };

  if (!documentId) return null;

  const tabs: Array<{ key: Tab; label: string; icon: typeof FileText; visible: boolean }> = [
    { key: "documento", label: "Documento", icon: FileText, visible: true },
    { key: "inteligencia", label: "Inteligência", icon: Brain, visible: true },
    { key: "historico", label: "Histórico", icon: History, visible: true },
    { key: "governanca", label: "Governança", icon: ShieldCheck, visible: canGovern },
  ];

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/30" role="dialog" aria-modal="true">
      <button className="h-full flex-1 cursor-default" onClick={onClose} aria-label="Fechar painel" />
      <aside className="flex h-full w-full max-w-2xl flex-col bg-white shadow-2xl dark:bg-slate-950">
        <header className="border-b border-slate-200 px-5 py-4 dark:border-slate-800">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="truncate text-lg font-semibold text-navy dark:text-white">
                  {document?.titulo || "Documento"}
                </h2>
                {document && <DocumentStatusBadge document={document} />}
              </div>
              <p className="mt-1 truncate text-xs text-slate-400">
                {document?.filename || "Carregando…"}
              </p>
            </div>
            <button className="btn-ghost shrink-0 px-2 py-2" onClick={onClose} title="Fechar">
              <X size={18} />
            </button>
          </div>

          <nav className="mt-4 flex gap-1 overflow-x-auto" aria-label="Seções do documento">
            {tabs.filter((item) => item.visible).map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-2 text-sm ${
                  tab === key
                    ? "bg-slate-900 text-white dark:bg-white dark:text-slate-950"
                    : "text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-900"
                }`}
                onClick={() => setTab(key)}
              >
                <Icon size={14} /> {label}
              </button>
            ))}
          </nav>
        </header>

        <div className="flex-1 overflow-y-auto p-5">
          {loading || !document ? (
            <div className="py-16"><Spinner /></div>
          ) : tab === "documento" ? (
            <div className="space-y-5">
              {previewKind && (
                <div className="overflow-hidden rounded-xl border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900">
                  {busy === "preview" && !previewUrl ? (
                    <div className="py-16"><Spinner /></div>
                  ) : previewError ? (
                    <div className="p-6 text-sm text-slate-500">
                      A pré-visualização não está disponível. O arquivo continua disponível para download.
                    </div>
                  ) : previewUrl && previewKind === "pdf" ? (
                    <iframe src={previewUrl} title={document.titulo} className="h-[48vh] w-full" />
                  ) : previewUrl ? (
                    <img src={previewUrl} alt={document.titulo} className="mx-auto max-h-[48vh] object-contain" />
                  ) : null}
                </div>
              )}

              <div className="grid gap-3 sm:grid-cols-2">
                <Info label="Tipo" value={document.tipo ? document.tipo.replace(/_/g, " ") : "Pendente"} />
                <Info label="Versão" value={`Versão ${document.versao || 1}`} />
                <Info label="Enviado em" value={fmtData(document.created_at)} />
                <Info label="Tamanho" value={fmtBytes(document.size_bytes)} />
                <Info label="Caso" value={document.case_id ? "Vinculado a caso" : "Sem caso"} />
                <Info label="Confidencialidade" value={document.confidencialidade.replace(/_/g, " ")} />
              </div>

              {(document.attention_reasons || []).length > 0 && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/20 dark:text-amber-200">
                  <div className="mb-2 flex items-center gap-2 font-medium">
                    <AlertTriangle size={15} /> Este documento precisa de atenção
                  </div>
                  <ul className="space-y-1 text-xs">
                    {(document.attention_reasons || []).map((reason) => (
                      <li key={reason}>• {ATTENTION_LABEL[reason] || reason}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="flex flex-wrap gap-2">
                <button className="btn-primary" onClick={download} disabled={busy === "download"}>
                  <Download size={15} /> {busy === "download" ? "Baixando…" : "Baixar"}
                </button>
                <button className="btn-ghost" onClick={() => onNewVersion(document)}>
                  <Upload size={15} /> Enviar nova versão
                </button>
                {canAnalyze && document.confidencialidade === "normal" && document.client_id && (
                  <button className="btn-ghost" onClick={togglePortal} disabled={busy === "portal"}>
                    {document.publicado_portal ? "Retirar do Portal" : "Disponibilizar no Portal"}
                  </button>
                )}
              </div>
            </div>
          ) : tab === "inteligencia" ? (
            <div className="space-y-5">
              <div className="grid gap-3 sm:grid-cols-2">
                <Info label="IA" value={iaLabel(document.analysis_status)} />
                <Info label="Segurança" value={integrityLabel(document.integrity_status)} />
                <Info
                  label="Inteligência do caso"
                  value={ragEnabled ? "Documento disponível para a IA" : "Não utilizado pela IA"}
                />
                <Info label="Última atualização da IA" value={fmtData(document.analysis_updated_at)} />
              </div>

              {canAnalyze && (
                <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
                  <div className="mb-3 flex items-center gap-2 font-medium text-navy dark:text-white">
                    <Sparkles size={16} /> Analisar documento
                  </div>
                  <p className="mb-3 text-sm text-slate-500">
                    A análise é um apoio ao trabalho jurídico. Classificação e conclusões relevantes continuam sujeitas à revisão humana.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <button className="btn-primary" onClick={reprocess} disabled={busy === "analysis" || !document.case_id}>
                      <RefreshCw size={14} /> {busy === "analysis" ? "Enviando…" : "Analisar documento"}
                    </button>
                    <button className="btn-ghost" onClick={toggleRag} disabled={busy === "rag" || !document.case_id}>
                      <Brain size={14} />
                      {ragEnabled ? "Não usar na inteligência deste caso" : "Usar na inteligência deste caso"}
                    </button>
                  </div>
                  {!document.case_id && (
                    <p className="mt-2 text-xs text-amber-600">Vincule o documento a um caso para habilitar inteligência contextual.</p>
                  )}
                </div>
              )}

              {canClassify && (
                <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
                  <div className="mb-2 font-medium text-navy dark:text-white">Tipo documental</div>
                  <p className="text-sm text-slate-500">
                    Atual: <span className="font-medium">{document.tipo?.replace(/_/g, " ") || "não definido"}</span>
                  </p>
                  <button className="btn-ghost mt-3" onClick={suggestType} disabled={busy === "classify"}>
                    <Sparkles size={14} /> {busy === "classify" ? "Analisando…" : "Sugerir tipo"}
                  </button>
                  {classification?.tipo_sugerido && (
                    <div className="mt-3 rounded-lg bg-slate-50 p-3 dark:bg-slate-900">
                      <div className="text-sm font-medium text-navy dark:text-white">
                        Sugestão: {classification.tipo_sugerido.replace(/_/g, " ")}
                      </div>
                      {classification.justificativa && (
                        <p className="mt-1 text-xs text-slate-500">{classification.justificativa}</p>
                      )}
                      {!classification.aplicado && (
                        <button className="btn-primary mt-3" onClick={applySuggestedType} disabled={busy === "apply-classification"}>
                          <CheckCircle2 size={14} /> Confirmar tipo sugerido
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : tab === "historico" ? (
            <div className="space-y-6">
              <section>
                <div className="mb-3 flex items-center justify-between gap-2">
                  <h3 className="flex items-center gap-2 font-medium text-navy dark:text-white">
                    <FileClock size={16} /> Versões
                  </h3>
                  <button className="btn-ghost px-2 py-1 text-sm" onClick={() => onNewVersion(document)}>
                    <Upload size={14} /> Nova versão
                  </button>
                </div>
                <div className="space-y-2">
                  {(versions?.data || [document]).map((version) => (
                    <div key={version.id} className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-800">
                      <div>
                        <div className="text-sm font-medium text-navy dark:text-white">
                          Versão {version.versao || 1}
                          {"is_current" in version && version.is_current ? " · atual" : ""}
                        </div>
                        <div className="text-xs text-slate-400">{fmtData(version.created_at)}</div>
                      </div>
                      <span className="text-xs text-slate-400">{version.filename}</span>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <h3 className="mb-3 flex items-center gap-2 font-medium text-navy dark:text-white">
                  <History size={16} /> Histórico de ações
                </h3>
                {(history?.data || []).length === 0 ? (
                  <p className="text-sm text-slate-400">Nenhuma ação registrada para exibição.</p>
                ) : (
                  <div className="space-y-2">
                    {(history?.data || []).map((event, index) => (
                      <div key={`${event.action}-${event.created_at}-${index}`} className="flex items-center justify-between border-b border-slate-100 py-2 text-sm dark:border-slate-900">
                        <span className="font-medium text-slate-600 dark:text-slate-300">{event.action.replace(/_/g, " ")}</span>
                        <span className="text-xs text-slate-400">{fmtData(event.created_at)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </div>
          ) : (
            <div className="space-y-5">
              <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
                <div className="mb-2 flex items-center gap-2 font-medium text-navy dark:text-white">
                  <Lock size={16} /> Preservação obrigatória
                </div>
                <p className="mb-4 text-sm text-slate-500">
                  Quando ativa, a eliminação definitiva fica bloqueada. Use apenas quando houver fundamento jurídico ou operacional documentado.
                </p>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={hold} onChange={(e) => setHold(e.target.checked)} />
                  Ativar preservação obrigatória
                </label>
                {hold && (
                  <div className="mt-3">
                    <label className="label">Motivo da preservação *</label>
                    <textarea className="input min-h-24" value={holdReason} onChange={(e) => setHoldReason(e.target.value)} />
                  </div>
                )}
              </div>

              <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
                <label className="label">Manter ao menos até</label>
                <input type="date" className="input" value={retentionDate} onChange={(e) => setRetentionDate(e.target.value)} />
                <p className="mt-1 text-xs text-slate-400">
                  O EJC não presume prazo legal. A data deve decorrer da política ou análise jurídica aplicável.
                </p>
              </div>

              <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div>
                    <div className="font-medium text-navy dark:text-white">Integridade</div>
                    <div className="text-sm text-slate-500">{integrityLabel(document.integrity_status)}</div>
                  </div>
                  <button className="btn-ghost" onClick={verifyIntegrity} disabled={busy === "integrity"}>
                    <ShieldCheck size={14} /> Verificar integridade
                  </button>
                </div>
              </div>

              <div>
                <label className="label">Motivo desta alteração *</label>
                <textarea
                  className="input min-h-20"
                  value={changeReason}
                  onChange={(e) => setChangeReason(e.target.value)}
                  placeholder="Registre de forma objetiva a razão da alteração."
                />
              </div>
              <button className="btn-primary" onClick={saveGovernance} disabled={busy === "governance" || !governance}>
                {busy === "governance" ? "Salvando…" : "Salvar governança"}
              </button>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-1 text-sm font-medium capitalize text-slate-700 dark:text-slate-200">{value}</div>
    </div>
  );
}
