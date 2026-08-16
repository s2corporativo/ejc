import { useCallback, useEffect, useMemo, useState } from "react";
import { FileCheck2, Send, Signature } from "lucide-react";

import { toast } from "../../components/Toast";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { useAuth } from "../../stores/auth";

const PAPEIS_SOLICITACAO = new Set([
  "superadmin",
  "admin",
  "socio",
  "advogado",
]);

const PAPEIS_ASSINATURA = new Set([
  "superadmin",
  "admin",
  "socio",
  "advogado",
]);

type DocumentoContextual = {
  id?: string | null;
  titulo?: string | null;
  filename?: string | null;
  nome_arquivo?: string | null;
  confidencialidade?: string | { value?: string } | null;
};

type SolicitacaoResumo = {
  id?: string;
  status?: string;
};

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

function tituloDocumento(doc: DocumentoContextual): string {
  return doc.titulo || doc.filename || doc.nome_arquivo || "Documento";
}

function confidencialidadeNormal(doc: DocumentoContextual): boolean {
  const valor =
    typeof doc.confidencialidade === "string"
      ? doc.confidencialidade
      : doc.confidencialidade?.value;
  // Listagens antigas nem sempre expõem o campo. O backend continua sendo a
  // autoridade e recusa qualquer documento não elegível para o Portal.
  return !valor || valor === "normal";
}

export default function CaseDocumentActions({
  caseId,
  docs,
}: {
  caseId: string;
  docs: DocumentoContextual[];
}) {
  const user = useAuth((state) => state.user);
  const role = user?.role || "";
  const podeSolicitar = PAPEIS_SOLICITACAO.has(role);
  const podeAssinar = PAPEIS_ASSINATURA.has(role);

  const [clientId, setClientId] = useState<string | null>(null);
  const [carregandoContexto, setCarregandoContexto] = useState(false);
  const [solicitacoes, setSolicitacoes] = useState<SolicitacaoResumo[]>([]);
  const [formAberto, setFormAberto] = useState(false);
  const [nomeItem, setNomeItem] = useState("");
  const [descricaoItem, setDescricaoItem] = useState("");
  const [mensagem, setMensagem] = useState("");
  const [enviandoSolicitacao, setEnviandoSolicitacao] = useState(false);
  const [assinandoDocId, setAssinandoDocId] = useState<string | null>(null);

  const carregarContexto = useCallback(async () => {
    if (!podeSolicitar && !podeAssinar) return;
    setCarregandoContexto(true);
    try {
      const [casoResult, solicitacoesResult] = await Promise.allSettled([
        api.get(`/cases/${caseId}`),
        podeSolicitar
          ? api.get(`/casos/${caseId}/solicitacoes-documentos`)
          : Promise.resolve({ data: { data: [] } }),
      ]);

      if (casoResult.status === "fulfilled") {
        const id = casoResult.value.data?.client_id;
        setClientId(typeof id === "string" && id ? id : null);
      } else {
        setClientId(null);
      }

      if (solicitacoesResult.status === "fulfilled") {
        setSolicitacoes(
          asList(solicitacoesResult.value.data) as SolicitacaoResumo[],
        );
      } else {
        setSolicitacoes([]);
      }
    } finally {
      setCarregandoContexto(false);
    }
  }, [caseId, podeAssinar, podeSolicitar]);

  useEffect(() => {
    void carregarContexto();
  }, [carregarContexto]);

  const docsAssinaveis = useMemo(
    () => docs.filter((doc) => Boolean(doc.id) && confidencialidadeNormal(doc)),
    [docs],
  );

  const enviarSolicitacao = async () => {
    const nome = nomeItem.trim();
    if (!nome) {
      toast.error("Informe qual documento deve ser enviado pelo cliente.");
      return;
    }

    setEnviandoSolicitacao(true);
    try {
      await api.post(`/casos/${caseId}/solicitacoes-documentos`, {
        itens: [
          {
            nome,
            descricao: descricaoItem.trim() || undefined,
          },
        ],
        mensagem: mensagem.trim() || undefined,
      });
      toast.success("Solicitação de documento enviada ao cliente.");
      setNomeItem("");
      setDescricaoItem("");
      setMensagem("");
      setFormAberto(false);
      try {
        const response = await api.get(
          `/casos/${caseId}/solicitacoes-documentos`,
        );
        setSolicitacoes(asList(response.data) as SolicitacaoResumo[]);
      } catch {
        // A criação já foi confirmada; falha na atualização visual não deve
        // induzir reenvio e eventual duplicidade da solicitação.
      }
    } catch (error) {
      toast.error(
        detalheErro(error, "Não foi possível solicitar o documento ao cliente."),
      );
    } finally {
      setEnviandoSolicitacao(false);
    }
  };

  const solicitarAssinatura = async (doc: DocumentoContextual) => {
    if (!doc.id || !clientId) return;
    setAssinandoDocId(doc.id);
    try {
      await api.post("/signatures/", {
        document_id: doc.id,
        client_id: clientId,
      });
      toast.success("Solicitação de assinatura enviada ao cliente.");
    } catch (error) {
      toast.error(
        detalheErro(error, "Não foi possível solicitar a assinatura."),
      );
    } finally {
      setAssinandoDocId(null);
    }
  };

  if (!podeSolicitar && !podeAssinar) return null;

  return (
    <section className="card space-y-3 p-4" aria-label="Ações com o cliente">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">
            Ações com o cliente
          </h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Use o contexto deste caso para solicitar documentos ou assinatura,
            sem recadastrar cliente e vínculo.
          </p>
        </div>
        {podeSolicitar && (
          <button
            type="button"
            className="btn-secondary inline-flex items-center gap-2 text-xs"
            onClick={() => setFormAberto((value) => !value)}
            aria-expanded={formAberto}
          >
            <Send className="h-3.5 w-3.5" aria-hidden="true" />
            Solicitar ao cliente
          </button>
        )}
      </div>

      {podeSolicitar && solicitacoes.length > 0 && !formAberto && (
        <p className="flex items-center gap-1.5 text-xs text-slate-500">
          <FileCheck2 className="h-3.5 w-3.5" aria-hidden="true" />
          {solicitacoes.length} solicitação(ões) já registrada(s) neste caso.
        </p>
      )}

      {podeSolicitar && formAberto && (
        <div className="grid gap-3 rounded-xl border border-slate-200 bg-slate-50/60 p-3">
          <label className="grid gap-1 text-xs font-medium text-slate-700">
            Documento solicitado
            <input
              className="input w-full text-sm"
              value={nomeItem}
              maxLength={255}
              onChange={(event) => setNomeItem(event.target.value)}
              placeholder="Ex.: comprovante de residência atualizado"
            />
          </label>
          <label className="grid gap-1 text-xs font-medium text-slate-700">
            Orientação do item (opcional)
            <input
              className="input w-full text-sm"
              value={descricaoItem}
              maxLength={2000}
              onChange={(event) => setDescricaoItem(event.target.value)}
              placeholder="Ex.: documento emitido nos últimos 90 dias"
            />
          </label>
          <label className="grid gap-1 text-xs font-medium text-slate-700">
            Mensagem ao cliente (opcional)
            <textarea
              className="input min-h-20 w-full resize-y text-sm"
              value={mensagem}
              maxLength={4000}
              onChange={(event) => setMensagem(event.target.value)}
              placeholder="Orientação geral sobre o envio"
            />
          </label>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              className="btn-secondary text-xs"
              onClick={() => setFormAberto(false)}
              disabled={enviandoSolicitacao}
            >
              Cancelar
            </button>
            <button
              type="button"
              className="btn-primary text-xs"
              onClick={() => void enviarSolicitacao()}
              disabled={!nomeItem.trim() || enviandoSolicitacao}
            >
              {enviandoSolicitacao ? "Enviando…" : "Enviar solicitação"}
            </button>
          </div>
        </div>
      )}

      {podeAssinar && docsAssinaveis.length > 0 && (
        <div className="border-t border-slate-100 pt-3">
          <p className="mb-2 text-xs font-medium text-slate-600">
            Assinatura eletrônica
          </p>
          <div className="flex flex-wrap gap-2">
            {docsAssinaveis.map((doc) => {
              const id = doc.id as string;
              const titulo = tituloDocumento(doc);
              const enviando = assinandoDocId === id;
              return (
                <button
                  key={id}
                  type="button"
                  className="btn-secondary inline-flex items-center gap-2 text-xs"
                  aria-label={`Solicitar assinatura — ${titulo}`}
                  title={`Solicitar assinatura de ${titulo}`}
                  onClick={() => void solicitarAssinatura(doc)}
                  disabled={!clientId || carregandoContexto || enviando}
                >
                  <Signature className="h-3.5 w-3.5" aria-hidden="true" />
                  {enviando ? "Solicitando…" : "Solicitar assinatura"}
                  {docsAssinaveis.length > 1 && (
                    <span className="max-w-44 truncate text-slate-500">
                      · {titulo}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
          {!clientId && !carregandoContexto && (
            <p className="mt-2 text-xs text-amber-700">
              Cliente do caso não disponível; confira o vínculo antes de pedir
              assinatura.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
