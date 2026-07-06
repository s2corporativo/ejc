import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import api from "../lib/api";
import { asList } from "../lib/list";
import { toast } from "../components/Toast";
import { PageHeader, Spinner, Badge } from "../components/UI";
import type {
  DiarioOficialKeyword as Keyword,
  DiarioOficialAlerta as Alerta,
} from "../types";
import {
  Bell,
  Trash2,
  Plus,
  ExternalLink,
  CheckCheck,
  Link2,
  Newspaper,
} from "lucide-react";

/** Vinculação feita automaticamente pelo backend (marcada na observação/texto). */
const isVinculacaoAutomatica = (a: Alerta): boolean =>
  Boolean(a.case_id) &&
  /vincula[çc][ãa]o autom[áa]tica/i.test(
    `${a.observacao ?? ""} ${a.trecho ?? ""}`,
  );

type FiltroAlerta = "todos" | "nao-lidos";

export default function DiarioOficial() {
  const [keywords, setKeywords] = useState<Keyword[]>([]);
  const [alertas, setAlertas] = useState<Alerta[]>([]);
  const [naoLidosCount, setNaoLidosCount] = useState(0);
  const [filtro, setFiltro] = useState<FiltroAlerta>("nao-lidos");
  const [novaKeyword, setNovaKeyword] = useState("");
  const [loadingAlertas, setLoadingAlertas] = useState(true);
  const [loadingKeywords, setLoadingKeywords] = useState(true);
  const [addingKeyword, setAddingKeyword] = useState(false);
  const [marcandoLido, setMarcandoLido] = useState<string | null>(null);

  const fetchNaoLidosCount = useCallback(async () => {
    try {
      const res = await api.get("/diario-oficial/alertas/nao-lidos/count");
      setNaoLidosCount(res.data?.nao_lidos ?? 0);
    } catch {}
  }, []);

  const fetchAlertas = useCallback(async () => {
    setLoadingAlertas(true);
    try {
      const params: Record<string, string | number> = { limite: 50 };
      if (filtro === "nao-lidos") params.lido = "false";
      const res = await api.get("/diario-oficial/alertas", { params });
      setAlertas(asList<Alerta>(res.data));
    } catch {
      setAlertas([]);
    } finally {
      setLoadingAlertas(false);
    }
  }, [filtro]);

  const fetchKeywords = useCallback(async () => {
    setLoadingKeywords(true);
    try {
      const res = await api.get("/diario-oficial/keywords");
      setKeywords(asList<Keyword>(res.data));
    } catch {
      setKeywords([]);
    } finally {
      setLoadingKeywords(false);
    }
  }, []);

  useEffect(() => {
    fetchAlertas();
    fetchNaoLidosCount();
  }, [fetchAlertas, fetchNaoLidosCount]);

  useEffect(() => {
    fetchKeywords();
  }, [fetchKeywords]);

  const marcarLido = async (id: string) => {
    setMarcandoLido(id);
    try {
      await api.patch(`/diario-oficial/alertas/${id}/marcar-lido`);
      setAlertas((prev) =>
        prev.map((a) => (a.id === id ? { ...a, lido: true } : a)),
      );
      setNaoLidosCount((c) => Math.max(0, c - 1));
      if (filtro === "nao-lidos") {
        setAlertas((prev) => prev.filter((a) => a.id !== id));
      }
    } finally {
      setMarcandoLido(null);
    }
  };

  const adicionarKeyword = async (e: React.FormEvent) => {
    e.preventDefault();
    const kw = novaKeyword.trim();
    if (!kw) return;
    setAddingKeyword(true);
    try {
      const res = await api.post("/diario-oficial/keywords", { keyword: kw });
      setKeywords((prev) => [...prev, res.data]);
      setNovaKeyword("");
    } finally {
      setAddingKeyword(false);
    }
  };

  const removerKeyword = async (id: string) => {
    if (!confirm("Remover esta palavra-chave do monitoramento?")) return;
    try {
      await api.delete(`/diario-oficial/keywords/${id}`);
      setKeywords((prev) => prev.filter((k) => k.id !== id));
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao remover palavra-chave");
    }
  };

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-8">
      <PageHeader
        title="Diário Oficial"
        subtitle={
          naoLidosCount > 0
            ? `${naoLidosCount} alerta(s) não lido(s)`
            : "Monitoramento de publicações"
        }
      />

      {/* ALERTAS */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-800 flex items-center gap-2">
            <Bell className="w-4 h-4 text-primary-600" />
            Alertas
          </h2>
          <div className="flex gap-1 rounded-lg border border-gray-200 p-1 bg-gray-50">
            {(["nao-lidos", "todos"] as FiltroAlerta[]).map((f) => (
              <button
                key={f}
                onClick={() => setFiltro(f)}
                className={`px-3 py-1 rounded-md text-sm font-medium transition-colors ${
                  filtro === f
                    ? "bg-white shadow text-primary-700"
                    : "text-gray-500 hover:text-gray-700"
                }`}
              >
                {f === "nao-lidos" ? "Não lidos" : "Todos"}
              </button>
            ))}
          </div>
        </div>

        {loadingAlertas ? (
          <div className="flex justify-center py-12">
            <Spinner />
          </div>
        ) : alertas.length === 0 ? (
          <div className="text-center py-16 bg-gray-50 rounded-xl border border-dashed border-gray-200">
            <Bell className="w-10 h-10 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500 font-medium">
              Nenhum alerta encontrado
            </p>
            <p className="text-gray-400 text-sm mt-1">
              {filtro === "nao-lidos"
                ? "Todos os alertas foram lidos."
                : "Configure palavras-chave para monitorar o Diário Oficial."}
            </p>
          </div>
        ) : (
          <ul className="space-y-3">
            {alertas.map((alerta) => (
              <li
                key={alerta.id}
                className={`rounded-xl border p-4 transition-colors ${
                  alerta.lido
                    ? "border-gray-100 bg-white"
                    : "border-primary-100 bg-primary-50/40"
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 mb-1">
                      <span className="inline-flex items-center rounded-full bg-primary-100 text-primary-700 text-xs font-semibold px-2 py-0.5">
                        {alerta.keyword}
                      </span>
                      <span className="text-xs text-gray-400">
                        {formatDate(alerta.data_publicacao)}
                      </span>
                      <span className="text-xs text-gray-400">
                        · {alerta.fonte}
                      </span>
                      {alerta.case_id ? (
                        <Link
                          to={`/casos/${alerta.case_id}`}
                          title="Abrir o caso vinculado"
                        >
                          <Badge tone="green" className="gap-1">
                            <Link2 className="h-3 w-3" />
                            Vinculado ao caso
                          </Badge>
                        </Link>
                      ) : (
                        <Badge tone="slate">sem caso</Badge>
                      )}
                      {isVinculacaoAutomatica(alerta) && (
                        <span className="text-[11px] text-warn-700">
                          vinculação automática — confira
                        </span>
                      )}
                    </div>
                    <p className="font-medium text-gray-800 text-sm leading-snug mb-1 truncate">
                      {alerta.titulo}
                    </p>
                    <p className="text-gray-500 text-sm line-clamp-2">
                      {alerta.trecho}
                    </p>
                  </div>
                  <div className="flex flex-col gap-2 flex-shrink-0">
                    <a
                      href={alerta.fonte}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-primary-600 hover:text-primary-800 font-medium"
                    >
                      <ExternalLink className="w-3 h-3" />
                      DOU
                    </a>
                    {!alerta.lido && (
                      <button
                        onClick={() => marcarLido(alerta.id)}
                        disabled={marcandoLido === alerta.id}
                        className="inline-flex items-center gap-1 text-xs text-green-700 hover:text-green-900 font-medium disabled:opacity-50"
                      >
                        {marcandoLido === alerta.id ? (
                          <Spinner />
                        ) : (
                          <CheckCheck className="w-3 h-3" />
                        )}
                        Lido
                      </button>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* PALAVRAS-CHAVE */}
      <section>
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          Palavras-chave monitoradas
        </h2>

        <form onSubmit={adicionarKeyword} className="flex gap-2 mb-4">
          <input
            type="text"
            value={novaKeyword}
            onChange={(e) => setNovaKeyword(e.target.value)}
            placeholder="Ex: S2 Estratégia, CNPJ 32.491.468..."
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
          <button
            type="submit"
            disabled={addingKeyword || !novaKeyword.trim()}
            className="btn-primary"
          >
            {addingKeyword ? <Spinner /> : <Plus className="w-4 h-4" />}
            Adicionar
          </button>
        </form>

        {loadingKeywords ? (
          <div className="flex justify-center py-6">
            <Spinner />
          </div>
        ) : keywords.length === 0 ? (
          <p className="text-gray-400 text-sm text-center py-6">
            Nenhuma palavra-chave cadastrada.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {keywords.map((kw) => (
              <span
                key={kw.id}
                className="inline-flex items-center gap-1.5 rounded-full bg-gray-100 text-gray-700 text-sm px-3 py-1.5 font-medium"
              >
                {kw.keyword}
                <button
                  onClick={() => removerKeyword(kw.id)}
                  className="text-gray-400 hover:text-danger-600 transition-colors"
                  aria-label={`Remover ${kw.keyword}`}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </span>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
