import { useEffect, useState } from "react";
import {
  PenLine,
  CheckCircle2,
  ShieldCheck,
  Clock,
  FileText,
} from "lucide-react";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { toast } from "../../components/Toast";
import { EmptyState, Modal } from "../../components/UI";
import { useAuth } from "../../stores/auth";

interface Signatario {
  nome?: string | null;
  email?: string | null;
  papel?: string | null;
  assinado?: boolean;
}

interface AssinaturaRow {
  id: string;
  documento: string;
  status: string;
  hash: string;
  mimetype?: string | null;
  preview_disponivel?: boolean;
  documento_visualizado_em?: string | null;
  created_at?: string | null;
  assinado_em?: string | null;
  signatarios?: Signatario[];
}

interface Comprovante {
  documento: string;
  assinado_em?: string | null;
  hash: string;
  hashCompleto: boolean;
  signatario?: string | null;
}

interface PreviewState {
  id: string;
  documento: string;
  url: string;
  mime: string;
}

const fmtDataHora = (d?: string | null) =>
  d ? new Date(d).toLocaleString("pt-BR") : "—";

async function detalheRespostaBlob(data: unknown): Promise<string | null> {
  if (!(data instanceof Blob)) return null;
  try {
    const texto = await data.text();
    if (!texto) return null;
    try {
      const json = JSON.parse(texto) as { detail?: unknown };
      return typeof json.detail === "string" ? json.detail : texto;
    } catch {
      return texto;
    }
  } catch {
    return null;
  }
}

function mimeRenderizavel(mime: string): boolean {
  const mt = mime.split(";", 1)[0].trim().toLowerCase();
  return (
    mt === "application/pdf" ||
    mt === "text/plain" ||
    ["image/jpeg", "image/png", "image/gif", "image/webp"].includes(mt)
  );
}

export default function PortalAssinaturas() {
  const { user } = useAuth();
  const [rows, setRows] = useState<AssinaturaRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [comprovante, setComprovante] = useState<Comprovante | null>(null);
  const [signing, setSigning] = useState<string | null>(null);
  const [viewing, setViewing] = useState<Set<string>>(() => new Set());
  const [visualizados, setVisualizados] = useState<Set<string>>(
    () => new Set(),
  );
  const [preview, setPreview] = useState<PreviewState | null>(null);
  const [confirmandoPreview, setConfirmandoPreview] = useState<string | null>(
    null,
  );

  const load = () => {
    setLoading(true);
    api
      .get("/signatures/")
      .then((r) => {
        const lista = asList(r.data) as AssinaturaRow[];
        setRows(lista);
        // A fonte canônica é o servidor. O Set fica apenas para refletir
        // imediatamente confirmações feitas nesta montagem da página.
        setVisualizados((atuais) => {
          const proximo = new Set(atuais);
          lista.forEach((item) => {
            if (item.documento_visualizado_em) proximo.add(item.id);
          });
          return proximo;
        });
      })
      .finally(() => setLoading(false));
  };
  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    return () => {
      if (preview?.url) URL.revokeObjectURL(preview.url);
    };
  }, [preview?.url]);

  const alterarViewing = (id: string, ativo: boolean) => {
    setViewing((atuais) => {
      const proximo = new Set(atuais);
      if (ativo) proximo.add(id);
      else proximo.delete(id);
      return proximo;
    });
  };

  const fecharPreview = () => {
    if (preview?.url) URL.revokeObjectURL(preview.url);
    setPreview(null);
  };

  const visualizarDocumento = async (s: AssinaturaRow) => {
    if (s.preview_disponivel === false) {
      toast.error(
        "Este formato não pode ser visualizado com segurança no Portal. Solicite ao escritório uma versão PDF para assinatura.",
      );
      return;
    }

    alterarViewing(s.id, true);
    try {
      const resposta = await api.get(`/signatures/${s.id}/documento`, {
        responseType: "blob",
        // 403 esperado desta superfície é tratado aqui para exibir o detalhe
        // real do backend sem duplicar o toast genérico do interceptor global.
        validateStatus: (status) =>
          (status >= 200 && status < 300) ||
          [403, 404, 410, 415].includes(status),
      });
      if (resposta.status < 200 || resposta.status >= 300) {
        const detalhe = await detalheRespostaBlob(resposta.data);
        toast.error(
          detalhe ||
            "Não foi possível abrir o documento. A assinatura continua bloqueada.",
        );
        return;
      }

      const blob = resposta.data as Blob;
      const mime = (blob.type || s.mimetype || "").toLowerCase();
      if (!mimeRenderizavel(mime)) {
        toast.error(
          "O navegador não consegue exibir este formato com segurança. Solicite uma versão PDF para assinatura.",
        );
        return;
      }

      if (preview?.url) URL.revokeObjectURL(preview.url);
      const url = URL.createObjectURL(blob);
      setPreview({ id: s.id, documento: s.documento, url, mime });
    } catch {
      toast.error(
        "Não foi possível abrir o documento. A assinatura continua bloqueada.",
      );
    } finally {
      alterarViewing(s.id, false);
    }
  };

  const confirmarVisualizacao = async (sigId: string) => {
    if (visualizados.has(sigId) || confirmandoPreview === sigId) return;
    setConfirmandoPreview(sigId);
    try {
      const { data } = await api.post(
        `/signatures/${sigId}/documento-visualizado`,
      );
      const timestamp =
        data?.documento_visualizado_em ?? new Date().toISOString();
      setVisualizados((atuais) => {
        const proximo = new Set(atuais);
        proximo.add(sigId);
        return proximo;
      });
      setRows((atuais) =>
        atuais.map((item) =>
          item.id === sigId
            ? { ...item, documento_visualizado_em: timestamp }
            : item,
        ),
      );
    } catch (e: any) {
      toast.error(
        e?.response?.data?.detail ||
          "Não foi possível confirmar a visualização. A assinatura continua bloqueada.",
      );
    } finally {
      setConfirmandoPreview(null);
    }
  };

  const assinar = async (s: AssinaturaRow) => {
    const foiVisualizado =
      Boolean(s.documento_visualizado_em) || visualizados.has(s.id);
    if (!foiVisualizado) {
      toast.error("Abra e leia o documento antes de assinar.");
      return;
    }
    if (
      !confirm(
        "Ao confirmar, você declara que LEU e CONCORDA com o documento.\n" +
          "Serão registrados: identificação, data/hora, IP e hash do arquivo.",
      )
    )
      return;
    setSigning(s.id);
    try {
      const { data } = await api.post(`/signatures/${s.id}/assinar`);
      toast.success("Documento assinado com sucesso.");
      setComprovante({
        documento: s.documento,
        assinado_em: data.comprovante?.assinado_em,
        hash: data.comprovante?.hash_documento ?? s.hash,
        hashCompleto: Boolean(data.comprovante?.hash_documento),
        signatario: user?.full_name ?? user?.email,
      });
      load();
    } catch (e: any) {
      toast.error(
        e?.response?.data?.detail ||
          "Não foi possível registrar sua assinatura. O documento NÃO foi assinado. Tente novamente.",
      );
    } finally {
      setSigning(null);
    }
  };

  // Comprovante de um item já assinado: usa os dados reais da listagem
  // (hash retornado abreviado pelo backend + data/hora + signatário).
  const verComprovante = (s: AssinaturaRow) => {
    const sig: Signatario | undefined = (s.signatarios ?? []).find(
      (x: Signatario) => x.assinado,
    );
    setComprovante({
      documento: s.documento,
      assinado_em: s.assinado_em,
      hash: s.hash,
      hashCompleto: false,
      signatario: sig ? `${sig.nome ?? ""} (${sig.email ?? ""})` : null,
    });
  };

  const pendentes = rows.filter((r) => r.status === "pendente");
  const assinados = rows.filter((r) => r.status !== "pendente");

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-800">Assinaturas</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          {pendentes.length > 0
            ? `${pendentes.length} documento${pendentes.length > 1 ? "s" : ""} aguardando sua assinatura`
            : "Todos os documentos foram assinados"}
        </p>
      </div>

      <Modal
        open={preview !== null}
        onClose={fecharPreview}
        title={
          preview ? `Visualizar: ${preview.documento}` : "Visualizar documento"
        }
      >
        {preview && (
          <div className="space-y-3">
            <div className="rounded-lg border border-slate-200 overflow-hidden bg-slate-50 min-h-[55vh]">
              {preview.mime.startsWith("image/") ? (
                <img
                  src={preview.url}
                  alt={preview.documento}
                  className="max-h-[70vh] w-full object-contain"
                  onLoad={() => confirmarVisualizacao(preview.id)}
                />
              ) : (
                <iframe
                  src={preview.url}
                  title={preview.documento}
                  className="w-full h-[65vh] bg-white"
                  onLoad={() => confirmarVisualizacao(preview.id)}
                />
              )}
            </div>
            <p className="text-xs text-slate-500">
              {confirmandoPreview === preview.id
                ? "Confirmando visualização…"
                : visualizados.has(preview.id)
                  ? "Visualização confirmada. Após a leitura, feche esta janela para assinar."
                  : "A assinatura só será liberada quando o documento terminar de carregar."}
            </p>
          </div>
        )}
      </Modal>

      {/* Comprovante (assinatura recém-feita ou consulta de item assinado) */}
      <Modal
        open={comprovante !== null}
        onClose={() => setComprovante(null)}
        title="Comprovante de assinatura"
      >
        {comprovante && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-success-600">
              <ShieldCheck className="w-5 h-5 flex-shrink-0" />
              <p className="text-sm font-semibold">
                Assinatura registrada eletronicamente
              </p>
            </div>
            <div className="text-sm space-y-2">
              <div>
                <p className="text-xs text-slate-400">Documento</p>
                <p className="text-slate-800 font-medium">
                  {comprovante.documento}
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-400">Data e hora</p>
                <p className="text-slate-800">
                  {fmtDataHora(comprovante.assinado_em)}
                </p>
              </div>
              {comprovante.signatario && (
                <div>
                  <p className="text-xs text-slate-400">Signatário</p>
                  <p className="text-slate-800">{comprovante.signatario}</p>
                </div>
              )}
              <div>
                <p className="text-xs text-slate-400">
                  Hash SHA-256 do arquivo
                  {comprovante.hashCompleto ? "" : " (prefixo)"}
                </p>
                <p className="font-mono text-xs text-slate-700 break-all">
                  {comprovante.hash}
                </p>
              </div>
            </div>
            <p className="text-xs text-slate-400">
              Assinatura eletrônica nos termos da MP 2.200-2/2001, art. 10, §2º.
              A trilha completa (identificação, IP e hash) fica registrada no
              escritório.
            </p>
          </div>
        )}
      </Modal>

      {/* Pendentes */}
      {pendentes.length > 0 && (
        <div className="card overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
            <Clock className="w-4 h-4 text-warn-500" />
            <h2 className="font-semibold text-slate-700">
              Pendentes ({pendentes.length})
            </h2>
          </div>
          <div className="divide-y divide-slate-100">
            {pendentes.map((s) => {
              const foiVisualizado =
                Boolean(s.documento_visualizado_em) || visualizados.has(s.id);
              const abrindo = viewing.has(s.id);
              return (
                <div
                  key={s.id}
                  className="px-5 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4"
                >
                  <div className="flex items-start gap-3 min-w-0 w-full">
                    <div className="w-8 h-8 bg-warn-50 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5">
                      <FileText className="w-4 h-4 text-warn-500" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-800 truncate">
                        {s.documento}
                      </p>
                      {s.created_at && (
                        <p className="text-xs text-slate-400 mt-0.5">
                          Solicitado em {fmtDataHora(s.created_at)}
                        </p>
                      )}
                      <p className="text-xs text-slate-300 font-mono mt-0.5">
                        #{s.hash?.slice(0, 16)}…
                      </p>
                      {!foiVisualizado && s.preview_disponivel !== false && (
                        <p className="text-xs text-warn-600 mt-1">
                          Abra o documento antes de assinar.
                        </p>
                      )}
                      {s.preview_disponivel === false && (
                        <p className="text-xs text-danger-600 mt-1">
                          Formato sem visualização segura. Solicite versão PDF.
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-col sm:flex-row gap-2 w-full sm:w-auto sm:flex-shrink-0">
                    <button
                      type="button"
                      onClick={() => visualizarDocumento(s)}
                      disabled={
                        abrindo ||
                        signing === s.id ||
                        s.preview_disponivel === false
                      }
                      className="btn-secondary text-sm px-3 py-2 w-full sm:w-auto"
                    >
                      <FileText className="w-3.5 h-3.5" />
                      {abrindo
                        ? "Abrindo…"
                        : foiVisualizado
                          ? "Ver novamente"
                          : "Ver documento"}
                    </button>
                    <button
                      type="button"
                      onClick={() => assinar(s)}
                      disabled={!foiVisualizado || signing === s.id || abrindo}
                      title={
                        !foiVisualizado
                          ? "Abra o documento antes de assinar"
                          : undefined
                      }
                      className="btn-primary text-sm px-4 py-2 w-full sm:w-auto"
                    >
                      <PenLine className="w-3.5 h-3.5" />
                      {signing === s.id ? "Assinando…" : "Assinar"}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Assinados */}
      {assinados.length > 0 && (
        <div className="card overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-success-500" />
            <h2 className="font-semibold text-slate-700">
              Assinados ({assinados.length})
            </h2>
          </div>
          <div className="divide-y divide-slate-100">
            {assinados.map((s) => (
              <div
                key={s.id}
                className="px-5 py-4 flex items-center justify-between gap-4"
              >
                <div className="flex items-start gap-3 min-w-0">
                  <div className="w-8 h-8 bg-success-50 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5">
                    <CheckCircle2 className="w-4 h-4 text-success-500" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-800 truncate">
                      {s.documento}
                    </p>
                    {s.assinado_em && (
                      <p className="text-xs text-slate-400 mt-0.5">
                        Assinado em {fmtDataHora(s.assinado_em)}
                      </p>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => verComprovante(s)}
                  className="text-xs font-medium text-success-600 bg-success-50 hover:bg-success-100 px-3 py-1.5 rounded-full flex-shrink-0 inline-flex items-center gap-1.5"
                >
                  <ShieldCheck className="w-3.5 h-3.5" /> Ver comprovante
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && rows.length === 0 && (
        <EmptyState
          icon={PenLine}
          title="Nenhum documento para assinar"
          message="Você está em dia — quando o escritório enviar um documento para assinatura, ele aparecerá aqui."
        />
      )}

      <p className="text-xs text-slate-400">
        Assinatura eletrônica nos termos da MP 2.200-2/2001, art. 10, §2º.
        Registramos identificação autenticada, hash SHA-256, IP e data/hora.
      </p>
    </div>
  );
}
