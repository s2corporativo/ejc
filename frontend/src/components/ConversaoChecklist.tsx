import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, XCircle, RefreshCw, Scale } from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";
import { Alert, Badge, Button, Modal, Skeleton } from "./UI";

/**
 * ConversaoChecklist — checklist bloqueante (#R8) de conversão
 * extrajudicial → judicial.
 *
 * Ao abrir: GET /cases/{id}/converter-judicial/checklist (8 verificações
 * {key, titulo, ok, detalhe}). O botão "Converter em processo" só habilita
 * com pronto=true; se o POST retornar 422, re-renderiza os pendentes
 * devolvidos pelo backend; 409 → toast informativo.
 */

interface ChecklistItem {
  key: string;
  titulo: string;
  ok: boolean;
  detalhe: string;
}

interface ChecklistResponse {
  itens: ChecklistItem[];
  pronto: boolean;
}

function msgErro(e: unknown, fallback: string): string {
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

export default function ConversaoChecklist({
  caseId,
  open,
  onClose,
  onSuccess,
}: {
  caseId: string;
  open: boolean;
  onClose: () => void;
  /** Chamado após conversão bem-sucedida (ex.: navegar para a aba Processos). */
  onSuccess?: () => void;
}) {
  const [itens, setItens] = useState<ChecklistItem[]>([]);
  const [pronto, setPronto] = useState(false);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState("");
  const [convertendo, setConvertendo] = useState(false);
  const [bloqueio, setBloqueio] = useState("");

  const carregar = useCallback(async () => {
    setLoading(true);
    setErro("");
    setBloqueio("");
    try {
      const { data } = await api.get<ChecklistResponse>(
        `/cases/${caseId}/converter-judicial/checklist`,
      );
      setItens(data.itens);
      setPronto(data.pronto);
    } catch (e) {
      setItens([]);
      setPronto(false);
      setErro(msgErro(e, "Falha ao verificar o checklist de conversão."));
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    if (open) carregar();
  }, [open, carregar]);

  const converter = async () => {
    setConvertendo(true);
    setBloqueio("");
    try {
      await api.post(`/cases/${caseId}/converter-judicial`);
      toast.success("Caso judicializado — processo criado.");
      onClose();
      onSuccess?.();
    } catch (e) {
      const status = (e as { response?: { status?: number } })?.response
        ?.status;
      if (status === 409) {
        toast.info(msgErro(e, "Este caso já possui um processo judicial."));
        onClose();
      } else if (status === 422) {
        const detail = (
          e as {
            response?: {
              data?: { detail?: { mensagem?: string; pendentes?: ChecklistItem[] } };
            };
          }
        )?.response?.data?.detail;
        const pendentes = Array.isArray(detail?.pendentes)
          ? detail.pendentes
          : [];
        setBloqueio(detail?.mensagem || "Conversão bloqueada — itens pendentes");
        // Re-renderiza com os pendentes devolvidos pelo backend
        setItens((prev) =>
          prev.length
            ? prev.map((i) => pendentes.find((p) => p.key === i.key) ?? i)
            : pendentes,
        );
        setPronto(false);
      } else {
        toast.error(msgErro(e, "Falha ao converter o caso em judicial."));
      }
    } finally {
      setConvertendo(false);
    }
  };

  const okCount = itens.filter((i) => i.ok).length;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Converter em processo judicial"
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            variant="secondary"
            onClick={carregar}
            disabled={loading || convertendo}
            icon={
              <RefreshCw
                className={`h-4 w-4 ${loading ? "animate-spin" : ""}`}
              />
            }
          >
            Reverificar
          </Button>
          <Button
            variant="primary"
            onClick={converter}
            disabled={!pronto || loading || convertendo}
            icon={<Scale className="h-4 w-4" />}
          >
            {convertendo ? "Convertendo..." : "Converter em processo"}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <p className="text-sm text-slate-500">
          A conversão cria um processo judicial dentro deste mesmo caso (sem
          duplicá-lo) e exige que todas as verificações abaixo estejam
          concluídas.
        </p>

        {erro && (
          <Alert variant="danger" title="Erro">
            {erro}
          </Alert>
        )}
        {bloqueio && (
          <Alert variant="danger" title="Conversão bloqueada">
            {bloqueio}
          </Alert>
        )}

        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-12" />
            ))}
          </div>
        ) : itens.length === 0 && !erro ? (
          <p className="text-sm text-slate-400">Nenhum registro encontrado</p>
        ) : (
          <>
            {itens.length > 0 && (
              <div className="flex items-center gap-2">
                <Badge tone={pronto ? "green" : "amber"}>
                  {okCount} de {itens.length} verificações ok
                </Badge>
                {pronto && (
                  <span className="text-caption text-success-700">
                    Pronto para converter.
                  </span>
                )}
              </div>
            )}
            <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
              {itens.map((item) => (
                <li key={item.key} className="flex items-start gap-3 px-4 py-3">
                  {item.ok ? (
                    <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success-600" />
                  ) : (
                    <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-danger-600" />
                  )}
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-800">
                      {item.titulo}
                    </p>
                    <p
                      className={`mt-0.5 text-xs ${
                        item.ok ? "text-slate-500" : "text-danger-700"
                      }`}
                    >
                      {item.detalhe}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </Modal>
  );
}
