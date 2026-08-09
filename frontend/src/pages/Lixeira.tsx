import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, RotateCcw, Trash2 } from "lucide-react";
import api from "../lib/api";
import { toast } from "../components/Toast";
import { ErrorState, PageHeader } from "../components/UI";

const ENTIDADES = [
  ["clients", "Clientes"],
  ["cases", "Casos"],
  ["deadlines", "Prazos"],
  ["documents", "Documentos"],
  ["legal_docs", "Peças"],
  ["fees", "Honorários"],
  ["tasks", "Tarefas"],
  ["procuracoes", "Procurações"],
  ["environmental_cases", "Ambiental"],
] as const;

interface ItemLixeira {
  id: string;
  rotulo: string;
  excluido_em: string;
}

interface PaginaLixeira {
  data: ItemLixeira[];
  total: number;
  page: number;
  page_size: number;
}

const PAGE_SIZE = 30;

export default function Lixeira() {
  const [ent, setEnt] = useState("clients");
  const [rows, setRows] = useState<ItemLixeira[]>([]);
  const [error, setError] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(PAGE_SIZE);
  const [restaurando, setRestaurando] = useState<string | null>(null);

  const load = () => {
    setError(false);
    return api
      .get("/trash/", {
        params: { entidade: ent, page, page_size: PAGE_SIZE },
      })
      .then((r) => {
        const payload = r.data as Partial<PaginaLixeira>;
        setRows(Array.isArray(payload.data) ? payload.data : []);
        setTotal(Number(payload.total ?? 0));
        setPageSize(Number(payload.page_size ?? PAGE_SIZE));
      })
      .catch(() => setError(true));
  };

  useEffect(() => {
    void load();
  }, [ent, page]);

  const selecionarEntidade = (id: string) => {
    setEnt(id);
    setPage(1);
  };

  const restaurar = async (id: string) => {
    setRestaurando(id);
    try {
      const { data } = await api.post(`/trash/${ent}/${id}/restaurar`);
      toast.success(data?.detail || "Registro restaurado.");
      if (rows.length === 1 && page > 1) {
        setPage((atual) => atual - 1);
      } else {
        await load();
      }
    } catch (e: any) {
      toast.error(
        e?.response?.data?.detail ||
          "Não foi possível restaurar o registro. Verifique as dependências e tente novamente.",
      );
    } finally {
      setRestaurando(null);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / Math.max(pageSize, 1)));

  return (
    <div>
      <PageHeader title="Lixeira" />
      <div className="flex gap-2 flex-wrap mb-4">
        {ENTIDADES.map(([id, label]) => (
          <button
            key={id}
            onClick={() => selecionarEntidade(id)}
            className={`px-3 py-1.5 rounded-lg text-sm ${
              ent === id
                ? "bg-navy text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="card divide-y divide-slate-100">
        {error && (
          <div className="p-4">
            <ErrorState
              message="Não foi possível carregar a lixeira. Tente novamente."
              onRetry={() => void load()}
            />
          </div>
        )}
        {!error && rows.length === 0 && (
          <div className="p-10 text-center text-slate-400">
            <Trash2 className="mx-auto mb-2" /> Lixeira vazia
          </div>
        )}
        {!error &&
          rows.map((row) => (
            <div
              key={row.id}
              className="p-4 flex items-center justify-between gap-3"
            >
              <div>
                <div className="text-sm font-medium">{row.rotulo}</div>
                <div className="text-xs text-slate-400">
                  Excluído em{" "}
                  {new Date(row.excluido_em).toLocaleString("pt-BR")}
                </div>
              </div>
              <button
                className="btn-primary text-xs"
                onClick={() => void restaurar(row.id)}
                disabled={restaurando === row.id}
              >
                <RotateCcw size={13} />
                {restaurando === row.id ? "Restaurando…" : "Restaurar"}
              </button>
            </div>
          ))}
      </div>

      {!error && total > 0 && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
          <span>
            {total} registro(s) excluído(s) · página {page} de {totalPages}
          </span>
          <div className="flex items-center gap-2">
            <button
              className="btn-secondary px-2 py-1 text-xs"
              disabled={page <= 1}
              onClick={() => setPage((atual) => Math.max(1, atual - 1))}
            >
              <ChevronLeft size={14} /> Anterior
            </button>
            <button
              className="btn-secondary px-2 py-1 text-xs"
              disabled={page >= totalPages}
              onClick={() =>
                setPage((atual) => Math.min(totalPages, atual + 1))
              }
            >
              Próxima <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
