// ── Aba Intimações do caso — VISUALIZAÇÃO somente leitura (Onda 4 / §10) ──────
// DECISÃO DE UNIFICAÇÃO (mesma da aba Prazos): a Central de Atividades
// (/atividades) é a fonte ÚNICA de tratamento de intimações DJEN (processar,
// aceitar/recusar prazo sugerido). Esta aba apenas visualiza as comunicações
// DJEN vinculadas ao caso e direciona para a Agenda pré-filtrada
// (?tipo=intimacao&caso=) — nenhuma ação de escrita duplicada aqui.
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { BellRing } from "lucide-react";
import api from "../../lib/api";
import { Empty, fmtDate } from "../../components/UI";

interface Intimacao {
  id: string;
  numero_processo: string;
  tribunal: string;
  tipo: string;
  data: string;
  texto: string;
  case_id: string | null;
  processada: boolean;
  prazo_sugerido_status: string;
}

export default function TabIntimacoes({ caseId }: { caseId: string }) {
  const [intimacoes, setIntimacoes] = useState<Intimacao[]>([]);

  const carregar = useCallback(() => {
    api
      .get(`/intimacoes/`, {
        params: { case_id: caseId, apenas_pendentes: false, page_size: 100 },
      })
      .then((r) => {
        const rows: Intimacao[] = r.data?.data ?? [];
        // Guarda em profundidade: se o backend antigo ignorar o filtro
        // case_id, a exibição segue honestamente escopada ao caso.
        setIntimacoes(rows.filter((x) => !x.case_id || x.case_id === caseId));
      })
      .catch(() => setIntimacoes([]));
  }, [caseId]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  return (
    <div className="space-y-4">
      {/* Direcionamento à fonte única de tratamento */}
      <div className="card flex items-center justify-between gap-3 p-4">
        <p className="text-sm text-slate-600">
          O tratamento das intimações (processar, aceitar/recusar prazo) é feito
          na <strong>Central de Atividades</strong> (Agenda).
        </p>
        <Link
          to={`/atividades?tipo=intimacao&caso=${caseId}`}
          className="btn-primary inline-flex h-9 items-center gap-2 text-[13px] px-4"
        >
          <BellRing className="h-4 w-4" />
          Tratar na Agenda
        </Link>
      </div>

      <h2 className="font-semibold">Intimações ({intimacoes.length})</h2>
      <div className="space-y-2">
        {intimacoes.map((x) => (
          <div key={x.id} className="card p-3 text-sm">
            <div className="flex justify-between items-center gap-3">
              <span className="text-gray-800 font-medium">
                {x.tipo || "Intimação"} · {x.tribunal}
              </span>
              <span
                className={`font-medium text-xs whitespace-nowrap ${
                  x.processada
                    ? "text-emerald-600 dark:text-emerald-300"
                    : "text-warn-700 dark:text-warn-300"
                }`}
              >
                {x.processada ? "Tratada" : "Pendente"}
              </span>
            </div>
            <div className="text-xs text-gray-500 mt-1">
              Processo {x.numero_processo} · Disponibilizada em{" "}
              {fmtDate(x.data)}
            </div>
            {x.texto && (
              <p className="text-xs text-gray-600 mt-1 line-clamp-2">
                {x.texto}
              </p>
            )}
          </div>
        ))}
        {intimacoes.length === 0 && (
          <Empty message="Nenhuma intimação DJEN vinculada a este caso" />
        )}
      </div>
    </div>
  );
}
