import { useEffect, useState, useRef } from "react";
import { Upload, Download, Search, Lock } from "lucide-react";
import api from "../lib/api";
import { PageHeader, Modal, Empty, Spinner, fmtDate } from "../components/UI";
import { DocumentosStats } from "../components/Dashboards";

export default function Documentos() {
  const [data, setData] = useState<any>(null);
  const [search, setSearch] = useState("");
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState<any>({ confidencialidade: "normal" });
  const fileRef = useRef<HTMLInputElement>(null);
  const [enviando, setEnviando] = useState(false);

  const load = () =>
    api
      .get("/documents/", {
        params: { search: search || undefined, page_size: 50 },
      })
      .then((r) => setData(r.data));
  useEffect(() => {
    load();
  }, []);
  useEffect(() => {
    const t = setTimeout(load, 350);
    return () => clearTimeout(t);
  }, [search]);

  const upload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file || !form.titulo) {
      alert("Arquivo e título obrigatórios");
      return;
    }
    setEnviando(true);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("titulo", form.titulo);
    fd.append("confidencialidade", form.confidencialidade);
    if (form.tipo) fd.append("tipo", form.tipo);
    try {
      await api.post("/documents/upload", fd);
      setModal(false);
      setForm({ confidencialidade: "normal" });
      load();
    } catch (e: any) {
      alert(e.response?.data?.detail || "Erro no upload");
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

  const confIcon = (c: string) =>
    ["restrito", "confidencial", "segredo_justica"].includes(c) ? (
      <Lock size={13} className="text-red-500" />
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

      {!data ? (
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
                <th className="px-4 py-3">Confidencialidade</th>
                <th className="px-4 py-3">Tamanho</th>
                <th className="px-4 py-3">Enviado em</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.data.map((d: any) => (
                <tr key={d.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium text-navy flex items-center gap-1.5">
                    {confIcon(d.confidencialidade)} {d.titulo}
                  </td>
                  <td className="px-4 py-3 text-slate-500 text-xs">
                    {d.filename}
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
                    <button
                      className="btn-ghost px-2 py-1"
                      onClick={() => baixar(d.id, d.filename)}
                    >
                      <Download size={15} />
                    </button>
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
    </div>
  );
}
