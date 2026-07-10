import { useEffect, useState, useRef } from "react";
import { toast } from "../components/Toast";
import { Upload, Download, Search, Lock, Sparkles } from "lucide-react";
import api from "../lib/api";
import {
  PageHeader,
  Modal,
  Empty,
  EmptyState,
  Spinner,
  Button,
  fmtDate,
} from "../components/UI";
import { DocumentosStats } from "../components/Dashboards";
import { asList } from "../lib/list";

/** Item de alternativa devolvido pela classificação por IA. */
type ClassAlternativa = { tipo_key: string; nome: string };

/** Shape de POST /documents/{id}/classificar (aplicar=false|true). */
type ClassResultado = {
  doc_id: string;
  aplicado: boolean;
  tipo_atual: string | null;
  tipo_sugerido: string | null;
  confianca: "alta" | "media" | "baixa" | null;
  alternativas: ClassAlternativa[];
  justificativa: string;
  disponivel: boolean;
  pii_removida?: boolean;
  modelo?: string;
  aviso?: string;
};

const CONF_LABEL: Record<string, string> = {
  alta: "Alta confiança",
  media: "Confiança média",
  baixa: "Baixa confiança",
};

export default function Documentos() {
  const [data, setData] = useState<any>(null);
  const [search, setSearch] = useState("");
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState<any>({ confidencialidade: "normal" });
  const fileRef = useRef<HTMLInputElement>(null);
  const [enviando, setEnviando] = useState(false);
  const [casos, setCasos] = useState<any[]>([]);

  // Classificação de tipo por IA (sugerir → aplicar), confirmação humana obrigatória.
  const [classDoc, setClassDoc] = useState<any | null>(null);
  const [classResult, setClassResult] = useState<ClassResultado | null>(null);
  const [classLoading, setClassLoading] = useState(false);
  const [aplicando, setAplicando] = useState(false);

  const [erro, setErro] = useState(false);
  // Guarda de sequência: só a resposta mais recente aplica setData (evita que
  // a resposta antiga de uma busca com debounce sobrescreva a nova).
  const seq = useRef(0);

  const load = () => {
    const my = ++seq.current;
    setErro(false);
    return api
      .get("/documents/", {
        params: { search: search || undefined, page_size: 50 },
      })
      .then((r) => {
        if (my === seq.current) setData(r.data);
      })
      .catch(() => {
        if (my !== seq.current) return;
        setErro(true);
        toast.error("Falha ao carregar documentos");
      });
  };
  useEffect(() => {
    load();
    // M12: lista de casos para vincular o documento (torna o gate IDOR efetivo).
    api
      .get("/cases/", { params: { page_size: 200 } })
      .then((r) => setCasos(asList(r.data)))
      .catch(() => {});
  }, []);
  useEffect(() => {
    const t = setTimeout(load, 350);
    return () => clearTimeout(t);
  }, [search]);

  const upload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file || !form.titulo) {
      toast.error("Arquivo e título obrigatórios");
      return;
    }
    setEnviando(true);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("titulo", form.titulo);
    fd.append("confidencialidade", form.confidencialidade);
    if (form.tipo) fd.append("tipo", form.tipo);
    if (form.case_id) {
      fd.append("case_id", form.case_id);
      const caso = casos.find((c) => c.id === form.case_id);
      if (caso?.client_id) fd.append("client_id", caso.client_id);
    }
    try {
      await api.post("/documents/upload", fd);
      setModal(false);
      setForm({ confidencialidade: "normal" });
      load();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro no upload");
    } finally {
      setEnviando(false);
    }
  };

  const baixar = async (id: string, filename: string) => {
    const r = await api.get(`/documents/${id}/download`, {
      responseType: "blob",
    });
    const url = URL.createObjectURL(r.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Abre o modal e busca a SUGESTÃO de tipo (aplicar=false — nunca grava aqui).
  const classificar = async (doc: any) => {
    setClassDoc(doc);
    setClassResult(null);
    setClassLoading(true);
    try {
      const r = await api.post<ClassResultado>(
        `/documents/${doc.id}/classificar`,
        null,
        { params: { aplicar: false } },
      );
      setClassResult(r.data);
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao classificar documento");
      setClassDoc(null);
    } finally {
      setClassLoading(false);
    }
  };

  // Persiste o tipo sugerido (aplicar=true) e atualiza a linha na UI.
  const aplicarTipo = async () => {
    if (!classDoc) return;
    setAplicando(true);
    try {
      const r = await api.post<ClassResultado>(
        `/documents/${classDoc.id}/classificar`,
        null,
        { params: { aplicar: true } },
      );
      const novoTipo = r.data.tipo_atual;
      setData((prev: any) =>
        prev
          ? {
              ...prev,
              data: (Array.isArray(prev.data) ? prev.data : []).map((d: any) =>
                d.id === classDoc.id ? { ...d, tipo: novoTipo } : d,
              ),
            }
          : prev,
      );
      toast.success(`Tipo aplicado: ${novoTipo || "—"}`);
      setClassDoc(null);
      setClassResult(null);
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao aplicar o tipo");
    } finally {
      setAplicando(false);
    }
  };

  const fecharClass = () => {
    setClassDoc(null);
    setClassResult(null);
  };

  const confIcon = (c: string) =>
    ["restrito", "confidencial", "segredo_justica"].includes(c) ? (
      <Lock size={13} className="text-danger-500" />
    ) : null;

  return (
    <div>
      <PageHeader
        title="Documentos"
        subtitle="GED do escritório"
        actions={
          <button className="btn-gold" onClick={() => setModal(true)}>
            <Upload size={16} /> Enviar
          </button>
        }
      />

      <DocumentosStats />

      <div className="relative mb-4 max-w-md">
        <Search size={16} className="absolute left-3 top-2.5 text-slate-400" />
        <input
          className="input pl-9"
          placeholder="Buscar documento..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {erro && !data ? (
        <EmptyState
          title="Falha ao carregar documentos"
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
        <Empty message="Nenhum documento" />
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">Título</th>
                <th className="px-4 py-3">Arquivo</th>
                <th className="px-4 py-3">Tipo</th>
                <th className="px-4 py-3">Confidencialidade</th>
                <th className="px-4 py-3">Tamanho</th>
                <th className="px-4 py-3">Enviado em</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(Array.isArray(data.data) ? data.data : []).map((d: any) => (
                <tr key={d.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium text-navy flex items-center gap-1.5">
                    {confIcon(d.confidencialidade)} {d.titulo}
                  </td>
                  <td className="px-4 py-3 text-slate-500 text-xs">
                    {d.filename}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {d.tipo ? (
                      <span className="capitalize">
                        {String(d.tipo).replace(/_/g, " ")}
                      </span>
                    ) : (
                      <span className="text-slate-300">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 capitalize text-xs">
                    {d.confidencialidade.replace(/_/g, " ")}
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs">
                    {d.size_bytes
                      ? `${(d.size_bytes / 1024).toFixed(0)} KB`
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-slate-400">
                    {fmtDate(d.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        className="btn-ghost px-2 py-1"
                        title="Classificar tipo (IA)"
                        disabled={classLoading && classDoc?.id === d.id}
                        onClick={() => classificar(d)}
                      >
                        <Sparkles size={15} />
                      </button>
                      <button
                        className="btn-ghost px-2 py-1"
                        title="Baixar"
                        onClick={() => baixar(d.id, d.filename)}
                      >
                        <Download size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal
        open={modal}
        onClose={() => setModal(false)}
        title="Enviar documento"
      >
        <div className="space-y-4">
          <div>
            <label className="label">Título *</label>
            <input
              className="input"
              value={form.titulo || ""}
              onChange={(e) => setForm({ ...form, titulo: e.target.value })}
            />
          </div>
          <div>
            <label className="label">
              Arquivo * (pdf, docx, jpg, png, xlsx — máx 50MB)
            </label>
            <input
              ref={fileRef}
              type="file"
              className="input"
              accept=".pdf,.docx,.doc,.jpg,.jpeg,.png,.xlsx,.xls,.txt"
            />
          </div>
          <div>
            <label className="label">Vincular ao caso (recomendado)</label>
            <select
              className="input"
              value={form.case_id || ""}
              onChange={(e) =>
                setForm({ ...form, case_id: e.target.value || undefined })
              }
            >
              <option value="">— Sem vínculo —</option>
              {casos.map((c) => (
                <option key={c.id} value={c.id}>
                  {(c.numero_interno ? c.numero_interno + " — " : "") +
                    (c.titulo || "Caso")}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-slate-400">
              Vincular a um caso controla quem pode acessar o documento (sigilo
              do cliente).
            </p>
          </div>
          <div>
            <label className="label">Confidencialidade</label>
            <select
              className="input"
              value={form.confidencialidade}
              onChange={(e) =>
                setForm({ ...form, confidencialidade: e.target.value })
              }
            >
              <option value="normal">Normal</option>
              <option value="interno">Interno</option>
              <option value="restrito">Restrito (cofre — sócios)</option>
              <option value="confidencial">Confidencial (cofre)</option>
              <option value="segredo_justica">
                Segredo de justiça (cofre)
              </option>
            </select>
          </div>
          <button
            className="btn-primary w-full justify-center"
            disabled={enviando}
            onClick={upload}
          >
            {enviando ? "Enviando..." : "Enviar"}
          </button>
        </div>
      </Modal>

      <Modal
        open={!!classDoc}
        onClose={fecharClass}
        title="Classificar tipo (IA)"
        footer={
          classResult && classResult.disponivel && classResult.tipo_sugerido ? (
            <>
              <button className="btn-ghost" onClick={fecharClass}>
                Cancelar
              </button>
              <button
                className="btn-primary"
                disabled={aplicando}
                onClick={aplicarTipo}
              >
                {aplicando ? "Aplicando..." : "Aplicar tipo sugerido"}
              </button>
            </>
          ) : (
            <button className="btn-ghost" onClick={fecharClass}>
              Fechar
            </button>
          )
        }
      >
        {classDoc && (
          <p className="mb-4 text-sm text-slate-500">
            Documento:{" "}
            <span className="font-medium text-navy">{classDoc.titulo}</span>
          </p>
        )}

        {classLoading || !classResult ? (
          <div className="py-8">
            <Spinner />
            <p className="mt-3 text-center text-xs text-slate-400">
              Analisando o texto do documento…
            </p>
          </div>
        ) : !classResult.disponivel || !classResult.tipo_sugerido ? (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
            Classificação por IA indisponível.
            {classResult.justificativa && (
              <span className="mt-1 block text-xs text-amber-700">
                {classResult.justificativa}
              </span>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-xs uppercase text-slate-400">
                Tipo sugerido
              </div>
              <div className="mt-1 flex items-center gap-2">
                <span className="text-lg font-semibold capitalize text-navy">
                  {String(classResult.tipo_sugerido).replace(/_/g, " ")}
                </span>
                {classResult.confianca && (
                  <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-600">
                    {CONF_LABEL[classResult.confianca] ?? classResult.confianca}
                  </span>
                )}
              </div>
              {classResult.tipo_atual && (
                <div className="mt-1 text-xs text-slate-400">
                  Tipo atual:{" "}
                  <span className="capitalize">
                    {String(classResult.tipo_atual).replace(/_/g, " ")}
                  </span>
                </div>
              )}
            </div>

            {classResult.justificativa && (
              <div>
                <div className="mb-1 text-xs uppercase text-slate-400">
                  Justificativa
                </div>
                <p className="text-sm text-slate-600">
                  {classResult.justificativa}
                </p>
              </div>
            )}

            {classResult.alternativas.length > 0 && (
              <div>
                <div className="mb-1 text-xs uppercase text-slate-400">
                  Alternativas
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {classResult.alternativas.map((a) => (
                    <span
                      key={a.tipo_key}
                      className="rounded-full border border-slate-200 px-2.5 py-0.5 text-xs text-slate-600"
                      title={a.tipo_key}
                    >
                      {a.nome}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <p className="text-xs text-slate-400">
              {classResult.aviso ||
                "Sugestão gerada por IA — confirmação humana obrigatória."}
            </p>
          </div>
        )}
      </Modal>
    </div>
  );
}
