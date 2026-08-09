import { useEffect, useState } from "react";
import {
  CheckCircle2,
  Clock,
  FileText,
  PenLine,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { toast } from "../../components/Toast";
import { EmptyState, Modal } from "../../components/UI";
import { useAuth } from "../../stores/auth";

interface Signatario {
  id?: string;
  nome?: string | null;
  email?: string | null;
  papel?: string | null;
  status?: string | null;
  assinado?: boolean;
  assinado_em?: string | null;
}

interface AssinaturaRow {
  id: string;
  documento: string;
  status: string;
  meu_status?: string | null;
  hash?: string;
  hash_completo?: string | null;
  assinado_em?: string | null;
  created_at?: string | null;
  signatarios?: Signatario[];
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

export default function PortalAssinaturas() {
  const { user } = useAuth();
  const [rows, setRows] = useState<AssinaturaRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [comprovante, setComprovante] = useState<Comprovante | null>(null);
  const [signing, setSigning] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    api
      .get("/signatures/")
      .then((r) => setRows(asList<AssinaturaRow>(r.data)))
      .catch(() => toast.error("Não foi possível carregar as assinaturas."))
      .finally(() => setLoading(false));
  };
  useEffect(() => {
    load();
  }, []);

  const assinar = async (s: AssinaturaRow) => {
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
      toast.success(data.detail || "Sua assinatura foi registrada.");
      setComprovante({
        documento: s.documento,
        assinado_em: data.comprovante?.assinado_em,
        hash: data.comprovante?.hash_documento ?? s.hash ?? "",
        hashCompleto: Boolean(data.comprovante?.hash_documento),
        signatario: user?.full_name ?? user?.email,
      });
      load();
    } catch (e: any) {
      toast.error(
        e?.response?.data?.detail ||
          "Não foi possível registrar sua assinatura. O documento NÃO foi assinado.",
      );
    } finally {
      setSigning(null);
    }
  };

  const recusar = async (s: AssinaturaRow) => {
    if (
      !confirm(
        "Recusar encerrará esta solicitação de assinatura. Confirme somente se você não concorda com o documento.",
      )
    )
      return;
    setRejecting(s.id);
    try {
      await api.post(`/signatures/${s.id}/recusar`);
      toast.success(
        "Assinatura recusada. O escritório poderá enviar uma nova versão.",
      );
      load();
    } catch (e: any) {
      toast.error(
        e?.response?.data?.detail || "Não foi possível recusar a assinatura.",
      );
    } finally {
      setRejecting(null);
    }
  };

  const verComprovante = (s: AssinaturaRow) => {
    const sig =
      (s.signatarios ?? []).find(
        (x) =>
          x.status === "assinado" &&
          (x.email ?? "").toLowerCase() === (user?.email ?? "").toLowerCase(),
      ) ?? (s.signatarios ?? []).find((x) => x.status === "assinado");
    setComprovante({
      documento: s.documento,
      assinado_em: sig?.assinado_em ?? s.assinado_em,
      hash: s.hash_completo || s.hash || "",
      hashCompleto: Boolean(s.hash_completo),
      signatario: sig ? `${sig.nome ?? ""} (${sig.email ?? ""})` : null,
    });
  };

  const pendentesMinhas = rows.filter(
    (r) => r.status === "pendente" && r.meu_status === "pendente",
  );
  const aguardandoOutros = rows.filter(
    (r) => r.status === "pendente" && r.meu_status === "assinado",
  );
  const concluidas = rows.filter((r) => r.status === "assinado");
  const encerradas = rows.filter((r) => r.status === "cancelado");

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-800">Assinaturas</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          {pendentesMinhas.length > 0
            ? `${pendentesMinhas.length} documento${pendentesMinhas.length > 1 ? "s" : ""} aguardando sua assinatura`
            : aguardandoOutros.length > 0
              ? "Você já assinou; há documentos aguardando outros signatários"
              : "Nenhuma assinatura sua pendente"}
        </p>
      </div>

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
              A trilha probatória completa fica registrada no escritório por
              signatário. A conclusão global depende da assinatura de todos os
              signatários exigidos na solicitação.
            </p>
          </div>
        )}
      </Modal>

      {pendentesMinhas.length > 0 && (
        <div className="card overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
            <Clock className="w-4 h-4 text-warn-500" />
            <h2 className="font-semibold text-slate-700">
              Aguardando você ({pendentesMinhas.length})
            </h2>
          </div>
          <div className="divide-y divide-slate-100">
            {pendentesMinhas.map((s) => (
              <div
                key={s.id}
                className="px-5 py-4 flex items-center justify-between gap-4"
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
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 justify-end">
                  <button
                    onClick={() => void recusar(s)}
                    disabled={rejecting === s.id || signing === s.id}
                    className="btn-secondary text-sm px-3 py-2 text-danger-700"
                  >
                    <XCircle className="w-3.5 h-3.5" />
                    {rejecting === s.id ? "Recusando…" : "Recusar"}
                  </button>
                  <button
                    onClick={() => void assinar(s)}
                    disabled={signing === s.id || rejecting === s.id}
                    className="btn-primary text-sm px-4 py-2"
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

      {aguardandoOutros.length > 0 && (
        <div className="card overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
            <Clock className="w-4 h-4 text-primary-500" />
            <h2 className="font-semibold text-slate-700">
              Aguardando outros signatários
            </h2>
          </div>
          <div className="divide-y divide-slate-100">
            {aguardandoOutros.map((s) => (
              <div
                key={s.id}
                className="px-5 py-4 flex items-center justify-between gap-4"
              >
                <div>
                  <p className="text-sm font-medium text-slate-800">
                    {s.documento}
                  </p>
                  <p className="text-xs text-success-600 mt-1">
                    Sua assinatura já foi registrada.
                  </p>
                </div>
                <button
                  onClick={() => verComprovante(s)}
                  className="btn-secondary text-xs"
                >
                  <ShieldCheck className="w-3.5 h-3.5" /> Ver sua evidência
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {concluidas.length > 0 && (
        <div className="card overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-success-500" />
            <h2 className="font-semibold text-slate-700">
              Concluídas ({concluidas.length})
            </h2>
          </div>
          <div className="divide-y divide-slate-100">
            {concluidas.map((s) => (
              <div
                key={s.id}
                className="px-5 py-4 flex items-center justify-between gap-4"
              >
                <div>
                  <p className="text-sm font-medium text-slate-800">
                    {s.documento}
                  </p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Todos os signatários concluíram a solicitação.
                  </p>
                </div>
                <button
                  onClick={() => verComprovante(s)}
                  className="text-xs font-medium text-success-600 bg-success-50 hover:bg-success-100 px-3 py-1.5 rounded-full inline-flex items-center gap-1.5"
                >
                  <ShieldCheck className="w-3.5 h-3.5" /> Ver comprovante
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {encerradas.length > 0 && (
        <div className="card p-4 text-sm text-slate-500">
          {encerradas.length} solicitação(ões) encerrada(s) ou recusada(s).
        </div>
      )}

      {!loading && rows.length === 0 && (
        <EmptyState
          icon={PenLine}
          title="Nenhum documento para assinar"
          message="Quando o escritório enviar um documento, ele aparecerá aqui."
        />
      )}

      <p className="text-xs text-slate-400">
        Registramos identificação autenticada, hash SHA-256, IP e data/hora por
        signatário. O hash é revalidado no momento do aceite.
      </p>
    </div>
  );
}
