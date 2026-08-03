// ── Aba Documentos do caso — upload embutido (Tela C, Bloco 3) ───────────────
// A aba age EM LUGAR: a zona de arrastar/selecionar + título + tipo enviam
// direto para POST /documents/upload (multipart, mesmo contrato já validado do
// CaseCommandDock.enviarDocumento) — sem navegar para /documentos.
// A lista existente permanece; após o upload ela é recarregada.
import { useCallback, useEffect, useRef, useState } from "react";
import { FileUp } from "lucide-react";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { toast } from "../../components/Toast";
import { Empty } from "../../components/UI";
import { detalheErro } from "../../utils/erro";

// Mesmo padrão de download já validado (GET /documents/:id/download, blob).
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
    toast.error("Não foi possível baixar o documento.");
  }
}

const TIPOS_DOCUMENTO = [
  { value: "outro", label: "Outro" },
  { value: "peticao", label: "Petição" },
  { value: "decisao", label: "Decisão" },
  { value: "contrato", label: "Contrato" },
  { value: "procuracao", label: "Procuração" },
  { value: "prova", label: "Prova" },
];

export default function TabDocumentos({ caseId }: { caseId: string }) {
  const [docs, setDocs] = useState<any[]>([]);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [titulo, setTitulo] = useState("");
  const [tipo, setTipo] = useState("outro");
  const [enviando, setEnviando] = useState(false);
  const [arrastando, setArrastando] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const carregar = useCallback(() => {
    api
      .get(`/documents/?case_id=${caseId}`)
      .then((r) => setDocs(asList(r.data)))
      .catch(() => setDocs([]));
  }, [caseId]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const selecionarArquivo = (file: File | null) => {
    setArquivo(file);
    if (file && !titulo) setTitulo(file.name);
  };

  const enviar = async () => {
    if (!arquivo) {
      toast.error("Selecione um documento para anexar ao caso.");
      return;
    }
    setEnviando(true);
    try {
      const body = new FormData();
      body.append("file", arquivo);
      body.append("titulo", titulo.trim() || arquivo.name);
      body.append("tipo", tipo);
      body.append("case_id", caseId);
      await api.post("/documents/upload", body, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success("Documento anexado ao caso.");
      setArquivo(null);
      setTitulo("");
      setTipo("outro");
      if (inputRef.current) inputRef.current.value = "";
      carregar();
    } catch (error) {
      toast.error(
        detalheErro(error, "Não foi possível anexar o documento ao caso."),
      );
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Upload embutido — a ação acontece dentro do caso */}
      <div className="card p-4 space-y-3">
        <h3 className="text-sm font-semibold text-slate-700">
          Anexar documento ao caso
        </h3>
        <div
          role="button"
          tabIndex={0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setArrastando(true);
          }}
          onDragLeave={() => setArrastando(false)}
          onDrop={(e) => {
            e.preventDefault();
            setArrastando(false);
            selecionarArquivo(e.dataTransfer.files?.[0] ?? null);
          }}
          className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-6 text-center transition-all duration-150 ${
            arrastando
              ? "border-primary-500 bg-primary-50 shadow-card"
              : "border-slate-200 hover:border-primary-300 hover:bg-slate-50 hover:shadow-soft"
          }`}
        >
          <FileUp className="h-6 w-6 text-primary-600" />
          {arquivo ? (
            <p className="text-sm font-medium text-slate-800">{arquivo.name}</p>
          ) : (
            <p className="text-sm text-slate-600">
              Arraste um arquivo aqui ou clique para selecionar
            </p>
          )}
          <p className="text-xs text-slate-400">
            PDF, DOCX, DOC, JPG, PNG, XLSX, XLS, TXT e XML.
          </p>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.docx,.doc,.jpg,.jpeg,.png,.xlsx,.xls,.txt,.xml"
            className="hidden"
            onChange={(e) => selecionarArquivo(e.target.files?.[0] ?? null)}
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto]">
          <input
            className="input w-full text-sm"
            value={titulo}
            maxLength={255}
            onChange={(e) => setTitulo(e.target.value)}
            placeholder="Título do documento"
          />
          <select
            className="input text-sm"
            value={tipo}
            onChange={(e) => setTipo(e.target.value)}
            aria-label="Tipo do documento"
          >
            {TIPOS_DOCUMENTO.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => void enviar()}
            disabled={!arquivo || enviando}
            className="btn-primary text-sm disabled:opacity-50"
          >
            {enviando ? "Anexando…" : "Anexar documento"}
          </button>
        </div>
      </div>

      {/* Lista existente — clique baixa o arquivo */}
      <h2 className="font-semibold">Documentos ({docs.length})</h2>
      <div className="space-y-2">
        {docs.map((d, i) => (
          <div
            key={d.id || i}
            className="card p-3 flex justify-between items-center text-sm cursor-pointer transition-colors duration-150 hover:bg-slate-50"
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
        ))}
        {docs.length === 0 && (
          <Empty message="Nenhum documento vinculado a este caso" />
        )}
      </div>
    </div>
  );
}
