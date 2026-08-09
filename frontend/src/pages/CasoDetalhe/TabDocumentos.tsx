// ── Aba Documentos do caso — upload e vínculo embutidos (Tela C, Bloco 3.2) ──
// A aba age EM LUGAR: a zona de arrastar/selecionar + título + tipo enviam
// direto para POST /documents/upload (multipart, mesmo contrato já validado do
// CaseCommandDock.enviarDocumento) — sem navegar para /documentos.
// "Vincular documento existente" fecha a outra metade do achado F3.2: antes só
// dava para linkar um documento já cadastrado indo ao módulo /documentos e
// usando a ação em lote "Vincular ao caso" de lá. Busca em GET /documents/
// (já com todo o RBAC/ownership/cofre aplicado no backend) + PATCH
// /documents/{id} com case_id (mesmo endpoint/contrato do módulo).
// A lista existente permanece; após upload ou vínculo ela é recarregada.
import { useCallback, useEffect, useRef, useState } from "react";
import { FileUp, Link2, Search } from "lucide-react";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { toast } from "../../components/Toast";
import { Empty } from "../../components/UI";

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

function detalheErro(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (
    detail &&
    typeof detail === "object" &&
    typeof (detail as { mensagem?: unknown }).mensagem === "string"
  ) {
    return (detail as { mensagem: string }).mensagem;
  }
  return fallback;
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

  const [buscaVinculo, setBuscaVinculo] = useState("");
  const [resultadosVinculo, setResultadosVinculo] = useState<any[]>([]);
  const [buscandoVinculo, setBuscandoVinculo] = useState(false);
  const [vinculandoId, setVinculandoId] = useState<string | null>(null);

  const carregar = useCallback(() => {
    api
      .get(`/documents/?case_id=${caseId}`)
      .then((r) => setDocs(asList(r.data)))
      .catch(() => setDocs([]));
  }, [caseId]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  // Busca debounced de documento existente para vincular — mesma fonte
  // (GET /documents/) e mesmo filtro de acesso do módulo /documentos.
  useEffect(() => {
    const termo = buscaVinculo.trim();
    if (!termo) {
      setResultadosVinculo([]);
      return;
    }
    setBuscandoVinculo(true);
    const id = setTimeout(() => {
      api
        .get("/documents/", { params: { search: termo, page_size: 10 } })
        .then((r) =>
          setResultadosVinculo(
            asList(r.data).filter((d: any) => d.case_id !== caseId),
          ),
        )
        .catch(() => setResultadosVinculo([]))
        .finally(() => setBuscandoVinculo(false));
    }, 400);
    return () => clearTimeout(id);
  }, [buscaVinculo, caseId]);

  const vincular = async (docId: string) => {
    setVinculandoId(docId);
    try {
      await api.patch(`/documents/${docId}`, { case_id: caseId });
      toast.success("Documento vinculado ao caso.");
      setBuscaVinculo("");
      setResultadosVinculo([]);
      carregar();
    } catch (error) {
      toast.error(
        detalheErro(error, "Não foi possível vincular o documento ao caso."),
      );
    } finally {
      setVinculandoId(null);
    }
  };

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

      {/* Vincular documento já cadastrado (GED) — a outra metade do achado
          F3.2: antes só existia como ação em lote no módulo /documentos. */}
      <div className="card p-4 space-y-3">
        <h3 className="text-sm font-semibold text-slate-700">
          Vincular documento já cadastrado
        </h3>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            className="input w-full pl-9 text-sm"
            value={buscaVinculo}
            onChange={(e) => setBuscaVinculo(e.target.value)}
            placeholder="Buscar documento por título…"
          />
        </div>
        {buscandoVinculo && <p className="text-xs text-slate-400">Buscando…</p>}
        {!buscandoVinculo &&
          buscaVinculo.trim() &&
          resultadosVinculo.length === 0 && (
            <p className="text-xs text-slate-400">
              Nenhum documento encontrado fora deste caso.
            </p>
          )}
        {resultadosVinculo.length > 0 && (
          <div className="space-y-1">
            {resultadosVinculo.map((d) => (
              <div
                key={d.id}
                className="flex items-center justify-between gap-2 rounded-lg border border-slate-100 p-2 text-sm"
              >
                <div className="min-w-0">
                  <p className="truncate text-slate-800">
                    {d.titulo || d.filename || d.nome_arquivo}
                  </p>
                  {d.case_id && (
                    <p className="text-xs text-amber-600">
                      Já vinculado a outro caso — vincular aqui move o
                      documento.
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => void vincular(d.id)}
                  disabled={vinculandoId === d.id}
                  className="btn-secondary flex shrink-0 items-center gap-1 text-xs disabled:opacity-50"
                >
                  <Link2 className="h-3.5 w-3.5" />
                  {vinculandoId === d.id ? "Vinculando…" : "Vincular"}
                </button>
              </div>
            ))}
          </div>
        )}
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
