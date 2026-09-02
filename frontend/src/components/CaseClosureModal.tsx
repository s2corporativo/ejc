import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";
import { Alert, Modal, Spinner } from "./UI";

export interface FechamentoItem {
  codigo: string;
  tipo: string;
  id: string | number;
  titulo: string;
  descricao: string;
  destino: string;
}

export interface DiagnosticoFechamento {
  case_id: string;
  pode_encerrar: boolean;
  requer_confirmacao_alertas: boolean;
  bloqueios: FechamentoItem[];
  alertas: FechamentoItem[];
  resumo: {
    prazos_ativos: number;
    prazos_nao_confirmados: number;
    tarefas_abertas: number;
    financeiro_pendente: number;
    pecas_nao_protocoladas: number;
    proxima_acao_pendente: boolean;
  };
}

const RESULTADOS = [
  ["exito", "Êxito"],
  ["exito_parcial", "Êxito parcial"],
  ["acordo", "Acordo"],
  ["derrota", "Derrota / improcedência"],
  ["desistencia", "Desistência"],
  ["arquivado", "Arquivamento sem julgamento"],
] as const;

function detalheErro(e: unknown, fallback: string): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response
    ?.data?.detail;
  if (typeof detail === "string") return detail;
  if (
    detail &&
    typeof detail === "object" &&
    typeof (detail as { mensagem?: unknown }).mensagem === "string"
  ) {
    return (detail as { mensagem: string }).mensagem;
  }
  return fallback;
}

export function fechamentoPodeProsseguir(
  diagnostico: DiagnosticoFechamento | null,
  confirmouAlertas: boolean,
): boolean {
  if (!diagnostico || diagnostico.bloqueios.length > 0) return false;
  if (diagnostico.alertas.length > 0 && !confirmouAlertas) return false;
  return true;
}

export default function CaseClosureModal({
  caseId,
  open,
  onClose,
  onClosed,
}: {
  caseId: string;
  open: boolean;
  onClose: () => void;
  onClosed: () => void;
}) {
  const [diagnostico, setDiagnostico] = useState<DiagnosticoFechamento | null>(
    null,
  );
  const [carregando, setCarregando] = useState(false);
  const [encerrando, setEncerrando] = useState(false);
  const [confirmouAlertas, setConfirmouAlertas] = useState(false);
  const [form, setForm] = useState({
    resultado: "exito",
    motivo_resultado: "",
    provas_determinantes: "",
    licoes_aprendidas: "",
    alimentar_rag: true,
  });

  useEffect(() => {
    if (!open) return;
    let cancelado = false;
    setCarregando(true);
    setConfirmouAlertas(false);
    setDiagnostico(null);
    api
      .get(`/cases/${caseId}/fechamento/diagnostico`)
      .then(({ data }) => {
        if (!cancelado) setDiagnostico(data as DiagnosticoFechamento);
      })
      .catch((e) => {
        if (!cancelado) {
          toast.error(
            detalheErro(e, "Não foi possível verificar o fechamento do caso."),
          );
          onClose();
        }
      })
      .finally(() => {
        if (!cancelado) setCarregando(false);
      });
    return () => {
      cancelado = true;
    };
  }, [caseId, onClose, open]);

  const camposValidos = useMemo(
    () =>
      form.motivo_resultado.trim().length >= 20 &&
      form.provas_determinantes.trim().length >= 10 &&
      form.licoes_aprendidas.trim().length >= 20,
    [form],
  );

  const podeConfirmar =
    fechamentoPodeProsseguir(diagnostico, confirmouAlertas) && camposValidos;

  const encerrar = async () => {
    if (!podeConfirmar) return;
    setEncerrando(true);
    try {
      await api.post(`/cases/${caseId}/encerrar`, {
        ...form,
        confirmar_alertas: confirmouAlertas,
      });
      toast.success(
        "Caso encerrado. O pós-mortem foi registrado e o conhecimento institucional atualizado.",
      );
      onClosed();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      if (
        e?.response?.status === 409 &&
        detail &&
        typeof detail === "object" &&
        Array.isArray(detail.bloqueios) &&
        Array.isArray(detail.alertas)
      ) {
        setDiagnostico(detail as DiagnosticoFechamento);
        setConfirmouAlertas(false);
      }
      toast.error(detalheErro(e, "Falha ao encerrar o caso."));
    } finally {
      setEncerrando(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={encerrando ? () => {} : onClose}
      title="Encerrar caso — fechamento inteligente"
    >
      {carregando || !diagnostico ? (
        <div className="flex min-h-40 flex-col items-center justify-center gap-3 text-sm text-slate-500">
          <Spinner />
          Verificando prazos, tarefas, peças e pendências financeiras…
        </div>
      ) : (
        <div className="space-y-4">
          <p className="text-xs leading-5 text-slate-500">
            O EJC verifica pendências antes do pós-mortem. Prazo ativo bloqueia
            o encerramento; os demais alertas precisam ser revisados e
            confirmados expressamente pelo advogado.
          </p>

          {diagnostico.bloqueios.length > 0 ? (
            <Alert variant="danger" title="Bloqueios impedem o encerramento">
              <div className="mt-2 space-y-2">
                {diagnostico.bloqueios.map((item) => (
                  <div
                    key={`${item.codigo}-${item.id}`}
                    className="flex gap-2 text-xs"
                  >
                    <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
                    <div>
                      <p className="font-semibold">{item.titulo}</p>
                      <p>{item.descricao}</p>
                      <Link
                        className="font-medium underline"
                        to={item.destino}
                        onClick={onClose}
                      >
                        Resolver antes de encerrar
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            </Alert>
          ) : diagnostico.alertas.length === 0 ? (
            <Alert variant="success" title="Checklist operacional concluído">
              <span className="inline-flex items-center gap-1">
                <CheckCircle2 className="h-4 w-4" /> Nenhuma pendência
                operacional relevante foi encontrada.
              </span>
            </Alert>
          ) : (
            <Alert variant="warning" title="Pendências para revisão humana">
              <div className="mt-2 space-y-2">
                {diagnostico.alertas.map((item) => (
                  <div
                    key={`${item.codigo}-${item.id}`}
                    className="flex gap-2 text-xs"
                  >
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    <div>
                      <p className="font-semibold">{item.titulo}</p>
                      <p>{item.descricao}</p>
                      <Link
                        className="font-medium underline"
                        to={item.destino}
                        onClick={onClose}
                      >
                        Conferir no caso
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
              <label className="mt-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-white/60 p-2 text-xs">
                <input
                  className="mt-0.5"
                  type="checkbox"
                  checked={confirmouAlertas}
                  onChange={(e) => setConfirmouAlertas(e.target.checked)}
                />
                <span>
                  Revisei as pendências acima e confirmo conscientemente o
                  encerramento mesmo com esses itens ainda registrados.
                </span>
              </label>
            </Alert>
          )}

          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-lg bg-slate-50 p-2">
              Prazos ativos: <b>{diagnostico.resumo.prazos_ativos}</b>
            </div>
            <div className="rounded-lg bg-slate-50 p-2">
              Tarefas abertas: <b>{diagnostico.resumo.tarefas_abertas}</b>
            </div>
            <div className="rounded-lg bg-slate-50 p-2">
              Financeiro pendente: <b>{diagnostico.resumo.financeiro_pendente}</b>
            </div>
            <div className="rounded-lg bg-slate-50 p-2">
              Peças não protocoladas:{" "}
              <b>{diagnostico.resumo.pecas_nao_protocoladas}</b>
            </div>
          </div>

          <div>
            <label className="label">Resultado</label>
            <select
              className="input w-full"
              value={form.resultado}
              onChange={(e) => setForm({ ...form, resultado: e.target.value })}
              disabled={diagnostico.bloqueios.length > 0}
            >
              {RESULTADOS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Motivo do resultado</label>
            <textarea
              rows={2}
              className="input w-full"
              value={form.motivo_resultado}
              onChange={(e) =>
                setForm({ ...form, motivo_resultado: e.target.value })
              }
              disabled={diagnostico.bloqueios.length > 0}
              placeholder="Mínimo 20 caracteres: fundamentos aceitos/rejeitados e razão do desfecho."
            />
          </div>
          <div>
            <label className="label">Provas determinantes</label>
            <textarea
              rows={2}
              className="input w-full"
              value={form.provas_determinantes}
              onChange={(e) =>
                setForm({ ...form, provas_determinantes: e.target.value })
              }
              disabled={diagnostico.bloqueios.length > 0}
              placeholder="Mínimo 10 caracteres."
            />
          </div>
          <div>
            <label className="label">Lições aprendidas</label>
            <textarea
              rows={2}
              className="input w-full"
              value={form.licoes_aprendidas}
              onChange={(e) =>
                setForm({ ...form, licoes_aprendidas: e.target.value })
              }
              disabled={diagnostico.bloqueios.length > 0}
              placeholder="Mínimo 20 caracteres."
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={form.alimentar_rag}
              disabled={diagnostico.bloqueios.length > 0}
              onChange={(e) =>
                setForm({ ...form, alimentar_rag: e.target.checked })
              }
            />
            Alimentar a base institucional com o pós-mortem revisado
          </label>

          {!camposValidos && diagnostico.bloqueios.length === 0 && (
            <p className="text-xs text-slate-500">
              Complete o pós-mortem: motivo e lições com pelo menos 20
              caracteres, e provas determinantes com pelo menos 10.
            </p>
          )}

          <button
            type="button"
            onClick={() => void encerrar()}
            disabled={!podeConfirmar || encerrando}
            className="btn-primary w-full disabled:cursor-not-allowed disabled:opacity-50"
          >
            {encerrando ? "Encerrando…" : "Confirmar encerramento"}
          </button>
        </div>
      )}
    </Modal>
  );
}
