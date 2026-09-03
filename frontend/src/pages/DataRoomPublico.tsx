import { useEffect, useState } from "react";
import { useParams } from "react-router";

interface ArquivoPublico {
  arquivo_id: string;
  nome?: string | null;
  download_url: string;
}

interface ManifestoPublico {
  data_room: { nome: string };
  arquivos: ArquivoPublico[];
  acesso_numero: number;
  expira_em?: string | null;
  grant_expira_em?: string | null;
}

function mensagemErro(status: number, payload: any): string {
  const detail = payload?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (status === 404) return "Link inválido ou revogado.";
  if (status === 410) return "Este compartilhamento expirou ou não está mais disponível.";
  if (status === 403) return "Este compartilhamento não está mais disponível para acesso.";
  return "Não foi possível abrir o compartilhamento.";
}

export default function DataRoomPublico() {
  const { token } = useParams();
  const [manifesto, setManifesto] = useState<ManifestoPublico | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const carregar = async () => {
      setLoading(true);
      setErro(null);
      setManifesto(null);
      if (!token) {
        setErro("Link inválido.");
        setLoading(false);
        return;
      }
      try {
        const response = await fetch(
          `/api/data-rooms/acesso/${encodeURIComponent(token)}/manifesto`,
          {
            method: "GET",
            credentials: "same-origin",
            headers: { Accept: "application/json" },
            cache: "no-store",
            signal: controller.signal,
          },
        );
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw Object.assign(new Error("manifesto indisponível"), {
            status: response.status,
            payload,
          });
        }
        setManifesto(payload as ManifestoPublico);
      } catch (error: any) {
        if (error?.name === "AbortError") return;
        setErro(mensagemErro(Number(error?.status || 0), error?.payload));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void carregar();
    return () => controller.abort();
  }, [token]);

  return (
    <main className="min-h-screen bg-canvas px-4 py-10">
      <div className="mx-auto max-w-3xl">
        <header className="mb-6 text-center">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            De Paula Teixeira Advogados
          </div>
          <h1 className="mt-2 text-2xl font-semibold text-slate-900">
            Data Room seguro
          </h1>
          <p className="mt-2 text-sm text-slate-500">
            Acesso temporário aos documentos publicados para este compartilhamento.
          </p>
        </header>

        {loading ? (
          <div className="card p-10 text-center text-sm text-slate-500" role="status">
            Carregando compartilhamento…
          </div>
        ) : erro ? (
          <div className="card border border-red-200 p-6 text-center" role="alert">
            <h2 className="font-medium text-red-800">Acesso indisponível</h2>
            <p className="mt-2 text-sm text-red-700">{erro}</p>
          </div>
        ) : manifesto ? (
          <section className="card p-5 sm:p-6">
            <div className="border-b border-slate-100 pb-4">
              <h2 className="text-lg font-semibold text-slate-900">
                {manifesto.data_room?.nome || "Documentos compartilhados"}
              </h2>
              {manifesto.expira_em && (
                <p className="mt-1 text-xs text-slate-500">
                  Compartilhamento com validade limitada.
                </p>
              )}
            </div>

            <div className="mt-4 space-y-2">
              {manifesto.arquivos.map((arquivo) => (
                <div
                  key={arquivo.arquivo_id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 p-3"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-slate-800">
                      {arquivo.nome || "Documento"}
                    </p>
                  </div>
                  <a
                    href={arquivo.download_url}
                    referrerPolicy="no-referrer"
                    className="btn-primary text-xs"
                  >
                    Baixar
                  </a>
                </div>
              ))}
              {manifesto.arquivos.length === 0 && (
                <div className="py-8 text-center text-sm text-slate-500">
                  Nenhum documento está disponível neste compartilhamento.
                </div>
              )}
            </div>

            <p className="mt-5 text-xs leading-relaxed text-slate-400">
              O acesso e os downloads são registrados para fins de segurança e
              rastreabilidade. Não compartilhe este link com terceiros não autorizados.
            </p>
          </section>
        ) : null}
      </div>
    </main>
  );
}
