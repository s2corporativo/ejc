// ── Aba Documentos do caso — upload e vínculo embutidos (Tela C, Bloco 3.2) ──
import { useCallback, useEffect, useRef, useState } from "react";
import { FileUp, Link2, Search } from "lucide-react";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { toast } from "../../components/Toast";
import { Empty } from "../../components/UI";
import { useAuth } from "../../stores/auth";

const PAPEIS_VINCULO_DOCUMENTAL = new Set([
  "superadmin",
  "admin",
  "socio",
  "advogado",
  "advogado_auxiliar",
  "estagiario",
]);

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

function formatarDataDocumento(value?: string | null): string | null {
  if (!value) return null;
  const data = new Date(value);
  if (Number.isNaN(data.getTime())) return null;
  return data.toLocaleDateString("pt-BR");
}

const TIPOS_DOCUMENTO = [
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

export default function TabDocumentos({ caseId }: { caseId: string }) {
  const user = useAuth((state) => state.user);
  const podeVincularDocumento = PAPEIS_VINCULO_DOCUMENTAL.has(user?.role || "");
  const [docs, setDocs] = useState<any[]>([]);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [titulo, setTitulo] = useState("");
  const [tipo, setTipo] = useState("outro");
  const [enviando, setEnviando] = useState(false);
  const [arrastando, setArrastando] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const [buscaVinculo, setBuscaVinculo] = useState("");
  const [resultadosVinculo, setResultadosVinculo] = useState<
    DocumentoCandidato[]
  >([]);
  const [totalVinculo, setTotalVinculo] = useState(0);
  const [buscandoVinculo, setBuscandoVinculo] = useState(false);
  const [erroBuscaVinculo, setErroBuscaVinculo] = useState<string | null>(null);
  const [tentativaBusca, setTentativaBusca] = useState(0);
  const [vinculandoId, setVinculandoId] = useState<string | null>(null);
  const buscaSeq = useRef(0);

  const carregar = useCallback(() => {
    api
      .get(`/documents/?case_id=${caseId}`)
      .then((r) => setDocs(asList(r.data)))
      .catch(() => setDocs([]));
  }, [caseId]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  useEffect(() => {
    const termo = buscaVinculo.trim();
    const seq = ++buscaSeq.current;
    let ativo = true;

    // Resultados pertencem ao par caseId+termo. Limpar imediatamente impede
    // que um botão de contexto anterior seja acionado durante debounce/rede.
    setResultadosVinculo([]);
    setTotalVinculo(0);
    setErroBuscaVinculo(null);

    if (!podeVincularDocumento || !termo) {
      setBuscandoVinculo(false);
      return () => {
        ativo = false;
      };
    }

    setBuscandoVinculo(true);
    const timer = window.setTimeout(async () => {
      try {
        const r = await api.get(`/cases/${caseId}/documentos/candidatos`, {
          params: { search: termo, page: 1, page_size: 20 },
        });
        if (!ativo || seq !== buscaSeq.current) return;
        setResultadosVinculo(asList(r.data) as DocumentoCandidato[]);
        setTotalVinculo(Number(r.data?.total || 0));
      } catch (error) {
        if (!ativo || seq !== buscaSeq.current) return;
        setErroBuscaVinculo(
          detalheErro(error, "Não foi possível buscar documentos disponíveis."),
        );
      } finally {
        if (ativo && seq === buscaSeq.current) setBuscandoVinculo(false);
      }
    }, 400);

    return () => {
      ativo = false;
      window.clearTimeout(timer);
    };
  }, [buscaVinculo, caseId, tentativaBusca, podeVincularDocumento]);

  const vincular = async (docId: string) => {
    if (!podeVincularDocumento) return;
    setVinculandoId(docId);
    try {
      await api.post(`/cases/${caseId}/documentos/${docId}/vincular`);
      toast.success("Documento vinculado ao caso.");
      setBuscaVinculo("");
      setResultadosVinculo([]);
      setTotalVinculo(0);
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

      {podeVincularDocumento && (
        <div className="card p-4 space-y-3">
          <h3 className="text-sm font-semibold text-slate-700">
            Vincular documento já cadastrado
          </h3>
          <p className="text-xs text-slate-500">
            Apenas documentos ainda sem caso podem ser vinculados. Documentos
            que já integram outro caso permanecem preservados no contexto de
            origem.
          </p>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              className="input w-full pl-9 text-sm"
              value={buscaVinculo}
              onChange={(e) => setBuscaVinculo(e.target.value)}
              placeholder="Buscar documento por título ou arquivo…"
            />
          </div>
          {buscandoVinculo && (
            <p className="text-xs text-slate-400">Buscando…</p>
          )}
          {!buscandoVinculo && erroBuscaVinculo && (
            <div className="flex items-center justify-between gap-3 rounded-lg border border-red-100 bg-red-50 p-2 text-xs text-red-700">
              <span>{erroBuscaVinculo}</span>
              <button
                type="button"
                className="font-medium underline"
                onClick={() => setTentativaBusca((v) => v + 1)}
              >
                Tentar novamente
              </button>
            </div>
          )}
          {!buscandoVinculo &&
            !erroBuscaVinculo &&
            buscaVinculo.trim() &&
            resultadosVinculo.length === 0 && (
              <p className="text-xs text-slate-400">
                Nenhum documento disponível para vínculo.
              </p>
            )}
          {resultadosVinculo.length > 0 && (
            <div className="space-y-1">
              {resultadosVinculo.map((d) => {
                const jaVinculado = Boolean(d.case_id);
                const dataDocumento = formatarDataDocumento(d.created_at);
                return (
                  <div
                    key={d.id}
                    className="flex items-center justify-between gap-2 rounded-lg border border-slate-100 p-2 text-sm"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-medium text-slate-800">
                        {d.titulo || d.filename || "Documento"}
                      </p>
                      <p className="truncate text-xs text-slate-500">
                        {[d.filename, dataDocumento, d.confidencialidade]
                          .filter(Boolean)
                          .join(" • ")}
                      </p>
                      {jaVinculado && (
                        <p className="text-xs text-amber-600">
                          Já vinculado a outro caso — a evidência original não
                          pode ser movida.
                        </p>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => void vincular(d.id)}
                      disabled={jaVinculado || vinculandoId === d.id}
                      className="btn-secondary flex shrink-0 items-center gap-1 text-xs disabled:opacity-50"
                    >
                      <Link2 className="h-3.5 w-3.5" />
                      {jaVinculado
                        ? "Indisponível"
                        : vinculandoId === d.id
                          ? "Vinculando…"
                          : "Vincular"}
                    </button>
                  </div>
                );
              })}
              {totalVinculo > resultadosVinculo.length && (
                <p className="pt-1 text-xs text-slate-400">
                  {totalVinculo} documentos correspondem à busca. Refine o termo
                  para localizar outros resultados.
                </p>
              )}
            </div>
          )}
        </div>
      )}

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
