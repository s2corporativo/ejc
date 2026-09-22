// ── Aba Intimações do caso — VISUALIZAÇÃO somente leitura (Onda 4 / §10) ──────
// DECISÃO DE UNIFICAÇÃO (mesma da aba Prazos): a Central de Atividades
// (/atividades) é a fonte ÚNICA de tratamento de intimações DJEN (processar,
// aceitar/recusar prazo sugerido). Esta aba apenas visualiza as comunicações
// DJEN vinculadas ao caso e direciona para a Agenda pré-filtrada
// (?tipo=intimacao&caso=) — nenhuma ação de escrita duplicada aqui.
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { BellRing, RefreshCw } from "lucide-react";
import api from "../../lib/api";
import { Button, Empty, fmtDate } from "../../components/UI";

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

/** Teto de páginas buscadas (100/página) — proteção contra listas absurdas. */
const MAX_PAGINAS = 5;
const PAGE_SIZE = 100;

export default function TabIntimacoes({ caseId }: { caseId: string }) {
  const [intimacoes, setIntimacoes] = useState<Intimacao[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  // Guarda de corrida: resposta de um caseId antigo nunca sobrescreve a aba.
  const caseIdRef = useRef(caseId);
  caseIdRef.current = caseId;

  const carregar = useCallback(() => {
    const alvo = caseId;
    let cancelado = false;
    setErro(null);
    api
      .get(`/intimacoes/`, {
        params: {
          case_id: alvo,
          apenas_pendentes: false,
          page: 1,
          page_size: PAGE_SIZE,
        },
      })
      .then(async (r) => {
        const linhas: Intimacao[] = r.data?.data ?? [];
        const tot: number = r.data?.total ?? linhas.length;
        // Paginação: busca as demais páginas até esgotar o total (teto MAX_PAGINAS).
        const paginas = Math.min(Math.ceil(tot / PAGE_SIZE), MAX_PAGINAS);
        for (let p = 2; p <= paginas; p++) {
          const rp = await api.get(`/intimacoes/`, {
            params: {
              case_id: alvo,
              apenas_pendentes: false,
              page: p,
              page_size: PAGE_SIZE,
            },
          });
          linhas.push(...(rp.data?.data ?? []));
        }
        if (cancelado || caseIdRef.current !== alvo) return;
        setIntimacoes(
          // Guarda em profundidade: se o backend antigo ignorar o filtro
          // case_id, a exibição segue honestamente escopada ao caso.
          linhas.filter((x) => x.case_id === alvo),
        );
        setTotal(tot);
      })
      .catch((e) => {
        if (cancelado || caseIdRef.current !== alvo) return;
        setIntimacoes([]);
        setTotal(null);
        setErro(
          e?.response?.status
            ? `Falha ao carregar (HTTP ${e.response.status})`
            : "Falha ao carregar intimações",
        );
      });
    return () => {
      cancelado = true;
    };
  }, [caseId]);

  useEffect(() => carregar(), [carregar]);

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

      {erro && (
        <div className="card flex items-center justify-between gap-3 border border-danger-200 bg-danger-50 p-4 dark:border-danger-800 dark:bg-danger-950/40">
          <p className="text-sm text-danger-700 dark:text-danger-300">
            {erro} — a lista vazia não significa ausência de intimações.
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

      <h2 className="font-semibold">
        Intimações ({total ?? intimacoes.length}
        {total != null && total > MAX_PAGINAS * PAGE_SIZE
          ? ` — exibindo as ${MAX_PAGINAS * PAGE_SIZE} mais recentes`
          : ""}
        )
      </h2>
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
        {!erro && intimacoes.length === 0 && (
          <Empty message="Nenhuma intimação DJEN vinculada a este caso" />
        )}
      </div>
    </div>
  );
}
