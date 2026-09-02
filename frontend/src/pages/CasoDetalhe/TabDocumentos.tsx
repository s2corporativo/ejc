import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  FileText,
  FileUp,
  Link2,
  Search,
  Upload,
  X,
} from "lucide-react";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { toast } from "../../components/Toast";
import { Button, Spinner } from "../../components/UI";
import DocumentDrawer from "../../components/documents/DocumentDrawer";
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge";
import { useAuth } from "../../stores/auth";
import {
  duplicateDetail,
  getDocumentPolicy,
  listDocuments,
  uploadDocument,
  type DocumentItem,
  type DocumentPolicy,
} from "../../services/documents";
import CaseDocumentActions from "./CaseDocumentActions";

const CAN_LINK = new Set([
  "superadmin",
  "admin",
  "socio",
  "advogado",
  "advogado_auxiliar",
  "estagiario",
]);
const SOCIO_PLUS = new Set(["superadmin", "admin", "socio"]);
const LEGACY_TYPES = [
  { value: "outro", label: "Outro" },
  { value: "peticao", label: "Petição" },
  { value: "decisao", label: "Decisão" },
  { value: "contrato", label: "Contrato" },
  { value: "procuracao", label: "Procuração" },
  { value: "prova", label: "Prova" },
];

type DocumentoCandidato = {
  id: string;
  titulo?: string | null;
  filename?: string | null;
  case_id?: string | null;
  confidencialidade?: string | null;
  created_at?: string | null;
};

type TipoDoc = { tipo_key: string; nome: string };

function detalheErro(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (detail && typeof detail === "object") {
    const message = (detail as { message?: unknown; mensagem?: unknown }).message ??
      (detail as { mensagem?: unknown }).mensagem;
    if (typeof message === "string") return message;
  }
  return fallback;
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleDateString("pt-BR");
}

function extOf(name?: string | null) {
  const value = name || "";
  const index = value.lastIndexOf(".");
  return index >= 0 ? value.slice(index).toLowerCase() : "";
}

function withoutExt(name: string) {
  const index = name.lastIndexOf(".");
  return index > 0 ? name.slice(0, index) : name;
}

function confLabel(value: string) {
  return ({
    normal: "Normal",
    interno: "Interno",
    restrito: "Restrito",
    confidencial: "Confidencial",
    segredo_justica: "Segredo de justiça",
  })[value] || value;
}

export default function TabDocumentos({ caseId }: { caseId: string }) {
  const user = useAuth((state) => state.user);
  const role = user?.role || "";
  const canLink = CAN_LINK.has(role);
  const canUseCofre = SOCIO_PLUS.has(role);

  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const [loading, setLoading] = useState(true);
  const [drawerId, setDrawerId] = useState<string | null>(null);

  const [policy, setPolicy] = useState<DocumentPolicy | null>(null);
  const [types, setTypes] = useState<TipoDoc[]>(LEGACY_TYPES.map((item) => ({
    tipo_key: item.value,
    nome: item.label,
  })));
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [type, setType] = useState("outro");
  const [conf, setConf] = useState("normal");
  const [predecessor, setPredecessor] = useState<DocumentItem | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const [linkSearch, setLinkSearch] = useState("");
  const [linkResults, setLinkResults] = useState<DocumentoCandidato[]>([]);
  const [linkTotal, setLinkTotal] = useState(0);
  const [linkLoading, setLinkLoading] = useState(false);
  const [linkError, setLinkError] = useState<string | null>(null);
  const [linkingId, setLinkingId] = useState<string | null>(null);
  const linkSeq = useRef(0);

  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await listDocuments({ caseId, page, pageSize });
      setDocs(result.data || []);
      setTotal(result.total || 0);
    } catch {
      setDocs([]);
      setTotal(0);
      toast.error("Não foi possível carregar os documentos deste caso.");
    } finally {
      setLoading(false);
    }
  }, [caseId, page]);

  useEffect(() => {
    setPage(1);
  }, [caseId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void Promise.all([
      getDocumentPolicy().then(setPolicy).catch(() => setPolicy(null)),
      api
        .get("/documents/tipos")
        .then((response) => {
          const master: TipoDoc[] = Array.isArray(response.data?.data) ? response.data.data : [];
          const keys = new Set(master.map((item) => item.tipo_key));
          setTypes([
            ...master,
            ...LEGACY_TYPES.filter((item) => !keys.has(item.value)).map((item) => ({
              tipo_key: item.value,
              nome: item.label,
            })),
          ]);
        })
        .catch(() => undefined),
    ]);
  }, []);

  useEffect(() => {
    const term = linkSearch.trim();
    const seq = ++linkSeq.current;
    let active = true;
    setLinkResults([]);
    setLinkTotal(0);
    setLinkError(null);
    if (!canLink || !term) {
      setLinkLoading(false);
      return () => {
        active = false;
      };
    }

    setLinkLoading(true);
    const timer = window.setTimeout(async () => {
      try {
        const response = await api.get(`/cases/${caseId}/documentos/candidatos`, {
          params: { search: term, page: 1, page_size: 20 },
        });
        if (!active || seq !== linkSeq.current) return;
        setLinkResults(asList(response.data) as DocumentoCandidato[]);
        setLinkTotal(Number(response.data?.total || 0));
      } catch (error) {
        if (!active || seq !== linkSeq.current) return;
        setLinkError(detalheErro(error, "Não foi possível buscar documentos disponíveis."));
      } finally {
        if (active && seq === linkSeq.current) setLinkLoading(false);
      }
    }, 350);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [canLink, caseId, linkSearch]);

  const chooseFile = (next: File | null) => {
    if (!next) return;
    const allowed = new Set((policy?.extensions || []).map((item) => item.toLowerCase()));
    if (allowed.size > 0 && !allowed.has(extOf(next.name))) {
      toast.error("Formato de arquivo não permitido pela política documental.");
      return;
    }
    const maxBytes = (policy?.max_upload_mb || 0) * 1024 * 1024;
    if (maxBytes > 0 && next.size > maxBytes) {
      toast.error(`Arquivo excede ${policy?.max_upload_mb} MB.`);
      return;
    }
    setFile(next);
    if (!title || predecessor) setTitle(withoutExt(next.name));
  };

  const resetUpload = () => {
    setFile(null);
    setTitle("");
    setType("outro");
    setConf("normal");
    setPredecessor(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  const startNewVersion = (document: DocumentItem) => {
    setPredecessor(document);
    setFile(null);
    setTitle(document.titulo);
    setType(document.tipo || "outro");
    setConf(document.confidencialidade || "normal");
    if (inputRef.current) inputRef.current.value = "";
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const submitUpload = async () => {
    if (!file) {
      toast.error("Selecione um documento para anexar ao caso.");
      return;
    }
    if (!title.trim()) {
      toast.error("Informe o título do documento.");
      return;
    }

    const request = {
      file,
      titulo: title.trim(),
      tipo: type || undefined,
      confidencialidade: conf,
      caseId,
      predecessorId: predecessor?.id,
    };
    setUploading(true);
    try {
      try {
        await uploadDocument(request);
      } catch (error) {
        const duplicate = duplicateDetail(error);
        if (!duplicate) throw error;
        const proceed = window.confirm(
          "Já existe um arquivo idêntico neste caso. Deseja registrar outra cópia mesmo assim? A decisão ficará auditada.",
        );
        if (!proceed) return;
        await uploadDocument({ ...request, allowDuplicate: true });
      }
      toast.success(predecessor ? "Nova versão registrada." : "Documento anexado ao caso.");
      resetUpload();
      setPage(1);
      await load();
    } catch (error) {
      toast.error(detalheErro(error, "Não foi possível anexar o documento ao caso."));
    } finally {
      setUploading(false);
    }
  };

  const linkDocument = async (documentId: string) => {
    if (!canLink) return;
    setLinkingId(documentId);
    try {
      await api.post(`/cases/${caseId}/documentos/${documentId}/vincular`);
      toast.success("Documento vinculado ao caso.");
      setLinkSearch("");
      setLinkResults([]);
      setLinkTotal(0);
      setPage(1);
      await load();
    } catch (error) {
      toast.error(detalheErro(error, "Não foi possível vincular o documento ao caso."));
    } finally {
      setLinkingId(null);
    }
  };

  const formatHelp = useMemo(() => {
    const extensions = policy?.extensions || [];
    const formats = extensions.length
      ? extensions.map((item) => item.replace(".", "").toUpperCase()).join(", ")
      : "formatos definidos pelo servidor";
    return `${formats}${policy?.max_upload_mb ? ` · até ${policy.max_upload_mb} MB` : ""}`;
  }, [policy]);

  return (
    <div className="space-y-4">
      <section className="card space-y-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold text-slate-800">
              {predecessor ? "Enviar nova versão" : "Anexar documento ao caso"}
            </h3>
            <p className="mt-0.5 text-xs text-slate-500">
              {predecessor
                ? `A nova versão ficará ligada à v${predecessor.versao || 1}; a anterior será preservada.`
                : "O arquivo será validado, armazenado e processado pelo fluxo documental do EJC."}
            </p>
          </div>
          {predecessor && (
            <Button variant="ghost" size="sm" onClick={resetUpload} icon={<X size={14} />}>
              Cancelar nova versão
            </Button>
          )}
        </div>

        <div
          role="button"
          tabIndex={0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(event) => event.key === "Enter" && inputRef.current?.click()}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            chooseFile(event.dataTransfer.files?.[0] || null);
          }}
          className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-5 text-center transition ${
            dragging ? "border-primary-500 bg-primary-50" : "border-slate-200 hover:border-primary-300 hover:bg-slate-50"
          }`}
        >
          <FileUp className="h-6 w-6 text-primary-600" />
          <p className="text-sm font-medium text-slate-700">{file?.name || "Arraste um arquivo ou clique para selecionar"}</p>
          <p className="text-xs text-slate-400">{formatHelp}</p>
          <input
            ref={inputRef}
            type="file"
            accept={(policy?.extensions || []).join(",") || undefined}
            className="hidden"
            onChange={(event) => chooseFile(event.target.files?.[0] || null)}
          />
        </div>

        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_180px_180px_auto]">
          <input
            className="input w-full text-sm"
            value={title}
            maxLength={255}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Título do documento"
          />
          <select className="input text-sm" value={type} onChange={(event) => setType(event.target.value)} aria-label="Tipo do documento">
            {types.map((item) => (
              <option key={item.tipo_key} value={item.tipo_key}>{item.nome}</option>
            ))}
          </select>
          <select className="input text-sm" value={conf} onChange={(event) => setConf(event.target.value)} aria-label="Nível de acesso">
            {(policy?.confidentiality || ["normal", "interno", "restrito", "confidencial", "segredo_justica"])
              .filter((value) => canUseCofre || !["restrito", "confidencial", "segredo_justica"].includes(value))
              .map((value) => <option key={value} value={value}>{confLabel(value)}</option>)}
          </select>
          <Button disabled={!file || uploading} onClick={() => void submitUpload()} icon={<Upload size={14} />}>
            {uploading ? "Enviando…" : predecessor ? "Nova versão" : "Anexar"}
          </Button>
        </div>
      </section>

      <CaseDocumentActions caseId={caseId} docs={docs} />

      {canLink && (
        <section className="card space-y-3 p-4">
          <div>
            <h3 className="text-sm font-semibold text-slate-800">Vincular documento já cadastrado</h3>
            <p className="mt-0.5 text-xs text-slate-500">A busca retorna apenas documentos elegíveis segundo o backend.</p>
          </div>
          <label className="relative block">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              className="input w-full pl-9 text-sm"
              value={linkSearch}
              onChange={(event) => setLinkSearch(event.target.value)}
              placeholder="Buscar por título ou arquivo…"
            />
          </label>
          {linkLoading && <p className="text-xs text-slate-400">Buscando…</p>}
          {linkError && <p className="rounded-lg bg-danger-50 p-2 text-xs text-danger-700">{linkError}</p>}
          {!linkLoading && !linkError && linkSearch.trim() && linkResults.length === 0 && (
            <p className="text-xs text-slate-400">Nenhum documento disponível para vínculo.</p>
          )}
          {linkResults.length > 0 && (
            <div className="space-y-1">
              {linkResults.map((document) => (
                <div key={document.id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-100 p-2 text-sm">
                  <div className="min-w-0">
                    <p className="truncate font-medium text-slate-800">{document.titulo || document.filename || "Documento"}</p>
                    <p className="truncate text-xs text-slate-400">
                      {[document.filename, formatDate(document.created_at), document.confidencialidade].filter(Boolean).join(" · ")}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={Boolean(document.case_id) || linkingId === document.id}
                    onClick={() => void linkDocument(document.id)}
                    icon={<Link2 size={13} />}
                  >
                    {document.case_id ? "Indisponível" : linkingId === document.id ? "Vinculando…" : "Vincular"}
                  </Button>
                </div>
              ))}
              {linkTotal > linkResults.length && (
                <p className="pt-1 text-xs text-slate-400">{linkTotal} resultados. Refine a busca para localizar outros.</p>
              )}
            </div>
          )}
        </section>
      )}

      <section className="space-y-2">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-semibold text-slate-800">Documentos ({total})</h2>
          {total > 0 && <span className="text-xs text-slate-400">Página {page} de {pageCount}</span>}
        </div>

        {loading ? (
          <div className="grid min-h-32 place-items-center"><Spinner /></div>
        ) : docs.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-200 p-6 text-center">
            <FileText className="mx-auto text-slate-300" size={28} />
            <p className="mt-2 text-sm font-medium text-slate-600">Nenhum documento vinculado a este caso.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {docs.map((document) => (
              <button
                key={document.id}
                type="button"
                onClick={() => setDrawerId(document.id)}
                className="card flex w-full items-center justify-between gap-3 p-3 text-left transition hover:bg-slate-50"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-slate-800">{document.titulo}</p>
                  <p className="mt-0.5 truncate text-xs text-slate-400">
                    {document.filename} · {document.tipo?.replaceAll("_", " ") || "Não classificado"} · v{document.versao || 1}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <DocumentStatusBadge document={document} />
                  <span className="text-xs text-slate-400">{formatDate(document.created_at)}</span>
                </div>
              </button>
            ))}
          </div>
        )}

        {total > pageSize && (
          <div className="flex justify-end gap-2 pt-2">
            <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))} icon={<ChevronLeft size={14} />}>
              Anterior
            </Button>
            <Button size="sm" variant="secondary" disabled={page >= pageCount} onClick={() => setPage((value) => Math.min(pageCount, value + 1))} icon={<ChevronRight size={14} />}>
              Próxima
            </Button>
          </div>
        )}
      </section>

      <DocumentDrawer
        documentId={drawerId}
        onClose={() => setDrawerId(null)}
        onNewVersion={(document) => {
          setDrawerId(null);
          startNewVersion(document);
        }}
        onChanged={() => void load()}
      />
    </div>
  );
}
