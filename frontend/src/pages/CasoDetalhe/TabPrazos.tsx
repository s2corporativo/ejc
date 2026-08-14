// ── Aba Prazos do caso — VISUALIZAÇÃO somente leitura (Fase 2 / QA) ────────────
// DECISÃO DE UNIFICAÇÃO: a Agenda (/atividades) é a fonte ÚNICA de escrita de
// prazos e atividades. Esta aba apenas visualiza os prazos do caso e direciona
// para "Gerenciar na Agenda" (com o caso já pré-filtrado), eliminando o
// formulário inline duplicado que competia com a Central de Atividades.
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { CalendarClock } from "lucide-react";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { Empty, fmtDate } from "../../components/UI";
import { Button } from "../../components/UI";

export default function TabPrazos({ caseId }: { caseId: string }) {
  const [prazos, setPrazos] = useState<any[]>([]);

  const carregar = useCallback(() => {
    api
      .get(`/deadlines/?case_id=${caseId}&status=`)
      .then((r) => setPrazos(asList(r.data)))
      .catch(() => setPrazos([]));
  }, [caseId]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  return (
    <div className="space-y-4">
      {/* Direcionamento à fonte única de escrita */}
      <div className="card flex items-center justify-between gap-3 p-4">
        <p className="text-sm text-slate-600">
          Os prazos deste caso são gerenciados na{" "}
          <strong>Central de Atividades</strong> (Agenda).
        </p>
        <Link
          to={`/atividades?view=calendario&tipo=prazo&caso=${caseId}`}
          className="btn-primary inline-flex h-9 items-center gap-2 text-[13px] px-4"
        >
          <CalendarClock className="h-4 w-4" />
          Gerenciar na Agenda
        </Link>
      </div>

      {/* Lista existente — leitura */}
      <h2 className="font-semibold">Prazos ({prazos.length})</h2>
      <div className="space-y-2">
        {prazos.map((d, i) => (
          <div
            key={d.id || i}
            className="card p-3 flex justify-between items-center text-sm"
          >
            <span className="text-gray-800">{d.titulo}</span>
            <span
              className={`font-medium text-xs ${
                (d.dias_restantes ?? 1) <= 0
                  ? "text-danger-600 dark:text-danger-300"
                  : (d.dias_restantes ?? 99) <= 7
                    ? "text-warn-700 dark:text-warn-300"
                    : "text-gray-500"
              }`}
            >
              {fmtDate(d.data_prazo)}
            </span>
          </div>
        ))}
        {prazos.length === 0 && <Empty message="Nenhum prazo cadastrado" />}
      </div>
    </div>
  );
}
