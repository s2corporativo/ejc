// ── Aba Tarefas do caso — VISUALIZAÇÃO somente leitura (Onda 4 / §10) ─────────
// DECISÃO DE UNIFICAÇÃO (mesma da aba Prazos): a Central de Atividades
// (/atividades) é a fonte ÚNICA de escrita de tarefas. Esta aba apenas
// visualiza as tarefas do caso e direciona para a Agenda pré-filtrada
// (?tipo=tarefa&caso=) — nenhum formulário ou PATCH duplicado aqui.
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { ListChecks } from "lucide-react";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { Empty, fmtDate } from "../../components/UI";

const ROTULO_STATUS: Record<string, string> = {
  a_fazer: "A fazer",
  fazendo: "Fazendo",
  concluida: "Concluída",
};

export default function TabTarefas({ caseId }: { caseId: string }) {
  const [tarefas, setTarefas] = useState<any[]>([]);

  const carregar = useCallback(() => {
    api
      .get(`/tasks/`, { params: { case_id: caseId } })
      .then((r) => setTarefas(asList(r.data)))
      .catch(() => setTarefas([]));
  }, [caseId]);

  useEffect(() => {
    carregar();
  }, [carregar]);

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
        {tarefas.length === 0 && <Empty message="Nenhuma tarefa deste caso" />}
      </div>
    </div>
  );
}
