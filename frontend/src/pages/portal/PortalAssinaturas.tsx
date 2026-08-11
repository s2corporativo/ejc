import { useEffect, useState } from "react";
import {
  PenLine,
  CheckCircle2,
  ShieldCheck,
  Clock,
  FileText,
  Eye,
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

interface Comprovante {
  documento: string;
  assinado_em?: string | null;
  hash: string;
  hashCompleto: boolean;
  signatario?: string | null;
}

const fmtDataHora = (d?: string | null) =>
  d ? new Date(d).toLocaleString("pt-BR") : "—";

// responseType blob: erros 4xx/5xx chegam como Blob JSON — extrai o `detail`
// legível para o toast (mesmo padrão de Pecas.tsx/TabPecas.tsx; achado do
// review Codex em PR #1076 — sem isto, 404/410 do endpoint viravam sempre a
// mensagem genérica de retry, escondendo a causa real).
async function blobErrorDetail(e: any): Promise<string | undefined> {
  let detail = e.response?.data?.detail;
  if (!detail && e.response?.data instanceof Blob) {
    try {
      detail = JSON.parse(await e.response.data.text())?.detail;
    } catch {
      /* corpo não-JSON — usa mensagem padrão do chamador */
    }
  }
  return typeof detail === "object" && detail !== null
    ? (detail.mensagem ?? JSON.stringify(detail).slice(0, 200))
    : detail;
}

export default function PortalAssinaturas() {
  const { user } = useAuth();
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [comprovante, setComprovante] = useState<Comprovante | null>(null);
  const [signing, setSigning] = useState<string | null>(null);
  const [visualizando, setVisualizando] = useState<string | null>(null);
  // Documentos que o cliente já abriu nesta sessão — condição mínima para
  // liberar o botão Assinar (achado ASS-00: antes o cliente confirmava "li e
  // concordo" sem nenhum jeito de ler o conteúdo).
  const [visualizados, setVisualizados] = useState<Set<string>>(new Set());

  const load = () => {
    setLoading(true);
    api
      .get("/signatures/")
      .then((r) => setRows(asList(r.data)))
      .finally(() => setLoading(false));
  };
  useEffect(() => {
    load();
  }, []);

  const verDocumento = async (s: any) => {
    setVisualizando(s.id);
    // Abre a aba SINCRONAMENTE dentro do clique — Safari (e outros
    // bloqueadores de pop-up) recusa window.open() disparado depois de um
    // await (achado do review Codex em PR #1076: o "Assinar" liberava mesmo
    // quando a aba nunca abriu, porque o catch nunca disparava). Sem
    // noopener/noreferrer aqui de propósito: o destino é conteúdo blob: da
    // MESMA origem gerado por nós, não um link externo — o risco que essas
    // flags mitigam (reverse tabnabbing via window.opener) não se aplica, e
    // precisamos da referência para navegar a aba depois do fetch.
    const aba = window.open("", "_blank");
    if (!aba) {
      toast.error(
        "Não foi possível abrir uma nova aba — verifique o bloqueador de pop-ups do navegador.",
      );
      setVisualizando(null);
      return;
    }
    try {
      const r = await api.get(`/signatures/${s.id}/documento`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(r.data as Blob);
      aba.location.href = url;
      // Revoga o object URL depois que a aba carrega o conteúdo — GED aceita
      // upload de até 50MB; sem revogar, abrir vários documentos retém
      // centenas de MB até a aba do portal recarregar (achado do review).
      const liberar = () => URL.revokeObjectURL(url);
      aba.addEventListener("load", liberar, { once: true });
      // Fallback: nem todo navegador propaga o `load` de forma confiável p/
      // conteúdo embutido (ex.: visualizador de PDF nativo) — libera de
      // qualquer forma depois de um tempo generoso, sem correr com o render.
      window.setTimeout(liberar, 60_000);
      setVisualizados((prev) => new Set(prev).add(s.id));
    } catch (e: any) {
      aba.close();
      toast.error(
        (await blobErrorDetail(e)) ||
          "Não foi possível abrir o documento. Tente novamente.",
      );
    } finally {
      setVisualizando(null);
    }
  };

  const assinar = async (s: any) => {
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
  const verComprovante = (s: any) => {
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
            {pendentes.map((s) => (
              <div
                key={s.id}
                className="px-5 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4"
              >
                <div className="flex items-start gap-3 min-w-0">
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
                  </div>
                </div>
                {/* flex-wrap: em telas estreitas (320-375px) os dois botões
                    quebram linha em vez de estourar o card (achado do review
                    Codex em PR #1076). */}
                <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap sm:flex-shrink-0">
                  <button
                    onClick={() => verDocumento(s)}
                    disabled={visualizando === s.id}
                    className="btn-secondary text-sm px-3 py-2"
                    title="Abrir o documento antes de assinar"
                  >
                    <Eye className="w-3.5 h-3.5" />
                    {visualizando === s.id ? "Abrindo…" : "Ver documento"}
                  </button>
                  <button
                    onClick={() => assinar(s)}
                    disabled={signing === s.id || !visualizados.has(s.id)}
                    title={
                      visualizados.has(s.id)
                        ? undefined
                        : "Abra o documento antes de assinar"
                    }
                    className="btn-primary text-sm px-4 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <PenLine className="w-3.5 h-3.5" />
                    {signing === s.id ? "Assinando…" : "Assinar"}
                  </button>
                </div>
              </div>
            ))}
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
