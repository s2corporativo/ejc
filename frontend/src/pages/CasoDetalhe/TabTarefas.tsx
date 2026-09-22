// ── Aba Tarefas do caso — VISUALIZAÇÃO somente leitura (Onda 4 / §10) ─────────
// DECISÃO DE UNIFICAÇÃO (mesma da aba Prazos): a Central de Atividades
// (/atividades) é a fonte ÚNICA de escrita de tarefas. Esta aba apenas
// visualiza as tarefas do caso e direciona para a Agenda pré-filtrada
// (?tipo=tarefa&caso=) — nenhum formulário ou PATCH duplicado aqui.
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { ListChecks, RefreshCw } from "lucide-react";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { Button, Empty, fmtDate } from "../../components/UI";

const ROTULO_STATUS: Record<string, string> = {
  a_fazer: "A fazer",
  fazendo: "Fazendo",
  concluida: "Concluída",
};

export default function TabTarefas({ caseId }: { caseId: string }) {
  const [tarefas, setTarefas] = useState<any[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  // Guarda de corrida: resposta de um caseId antigo nunca sobrescreve a aba.
  const caseIdRef = useRef(caseId);
  caseIdRef.current = caseId;

  const carregar = useCallback(() => {
    const alvo = caseId;
    let cancelado = false;
    setErro(null);
    api
      .get(`/tasks/`, { params: { case_id: alvo } })
      .then((r) => {
        if (cancelado || caseIdRef.current !== alvo) return;
        setTarefas(asList(r.data));
      })
      .catch((e) => {
        if (cancelado || caseIdRef.current !== alvo) return;
        setTarefas([]);
        setErro(
          e?.response?.status
            ? `Falha ao carregar (HTTP ${e.response.status})`
            : "Falha ao carregar tarefas",
        );
      });
    return () => {
      cancelado = true;
    };
  }, [caseId]);

  useEffect(() => carregar(), [carregar]);

  return (
    <div className="space-y-4">
      {/* Direcionamento à fonte única de escrita */}
      <div className="card flex items-center justify-between gap-3 p-4">
        <p className="text-sm text-slate-600">
          As tarefas deste caso são gerenciadas na{" "}
          <strong>Central de Atividades</strong> (Agenda).
        </p>
        <Link
          to={`/atividades?tipo=tarefa&caso=${caseId}`}
          className="btn-primary inline-flex h-9 items-center gap-2 text-[13px] px-4"
        >
          <ListChecks className="h-4 w-4" />
          Gerenciar na Agenda
        </Link>
      </div>

      {erro && (
        <div className="card flex items-center justify-between gap-3 border border-danger-200 bg-danger-50 p-4 dark:border-danger-800 dark:bg-danger-950/40">
          <p className="text-sm text-danger-700 dark:text-danger-300">
            {erro} — a lista vazia não significa ausência de tarefas.
          </p>
          <Button
            variant="secondary"
            className="h-9"
            onClick={() => carregar()}
          >
            <RefreshCw className="h-4 w-4" />
            Tentar novamente
          </Button>
        </div>
      )}

      <h2 className="font-semibold">Tarefas ({tarefas.length})</h2>
      <div className="space-y-2">
        {tarefas.map((t, i) => (
          <div
            key={t.id || i}
            className="card p-3 flex justify-between items-center text-sm gap-3"
          >
            <div className="min-w-0">
              <span className="text-gray-800 block truncate">{t.titulo}</span>
              {t.data_limite && (
                <span className="text-gray-400 text-xs">
                  Limite: {fmtDate(t.data_limite)}
                </span>
              )}
            </div>
            <span
              className={`font-medium text-xs whitespace-nowrap ${
                t.status === "concluida"
                  ? "text-emerald-600 dark:text-emerald-300"
                  : t.status === "fazendo"
                    ? "text-warn-700 dark:text-warn-300"
                    : "text-gray-500"
              }`}
            >
              {ROTULO_STATUS[t.status] ?? t.status}
            </span>
          </div>
        ))}
        {!erro && tarefas.length === 0 && (
          <Empty message="Nenhuma tarefa deste caso" />
        )}
      </div>
    </div>
  );
}
