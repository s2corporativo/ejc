import { useState } from "react";
import { Link } from "react-router-dom";
import { BookOpen, Library, Brain, ChevronRight } from "lucide-react";
import api from "../lib/api";
import { PageHeader, Spinner } from "../components/UI";
import { ConhecimentoStats } from "../components/Dashboards";
import { asList } from "../lib/list";

const CATEGORIAS = [
  {
    to: "/conhecimento",
    label: "Base de Conhecimento",
    desc: "Leis, súmulas e doutrina indexadas para RAG",
    icon: BookOpen,
  },
  {
    to: "/biblioteca",
    label: "Biblioteca de Estratégias",
    desc: "Teses e peças de referência do escritório",
    icon: Library,
  },
  {
    to: "/memoria",
    label: "Memória Institucional",
    desc: "Casos, resultados e lições aprendidas",
    icon: Brain,
  },
] as const;

// Busca unificada: agrega RAG semântico + teses + jurisprudência interna + memória institucional.
// Não cria tabela própria — é uma camada de busca sobre o conhecimento que já existe.
export default function KnowledgeHub() {
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [res, setRes] = useState<{
    rag: any[];
    teses: any[];
    juris: any[];
    memoria: any[];
  }>({ rag: [], teses: [], juris: [], memoria: [] });

  const buscar = async () => {
    if (q.trim().length < 3) return;
    setLoading(true);
    setSearched(true);
    const [rag, teses, juris, mem] = await Promise.allSettled([
      api.get(`/rag/buscar?q=${encodeURIComponent(q)}&limite=8`),
      api.get(`/teses?busca=${encodeURIComponent(q)}&per_page=8`),
      api.get(`/jurisprudencias?busca=${encodeURIComponent(q)}&per_page=8`),
      api.get(`/memoria-institucional?q=${encodeURIComponent(q)}&limit=8`),
    ]);
    setRes({
      rag: rag.status === "fulfilled" ? (rag.value.data?.resultados ?? []) : [],
      teses:
        teses.status === "fulfilled"
          ? asList(teses.value.data)
          : [],
      juris:
        juris.status === "fulfilled" ? asList(juris.value.data) : [],
      memoria: mem.status === "fulfilled" ? asList(mem.value.data) : [],
    });
    setLoading(false);
  };

  const total =
    res.rag.length + res.teses.length + res.juris.length + res.memoria.length;

  const Bloco = ({ titulo, cor, children, n }: any) => (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-2">
        <span className={`w-2 h-2 rounded-full ${cor}`} />
        <h3 className="font-semibold text-sm">{titulo}</h3>
        <span className="text-xs text-gray-400">({n})</span>
      </div>
      {n === 0 ? (
        <p className="text-gray-400 text-xs">Nenhum resultado</p>
      ) : (
        <div className="space-y-2">{children}</div>
      )}
    </div>
  );

  return (
    <div>
      <PageHeader
        title="Knowledge Hub"
        subtitle="Busca unificada em todo o conhecimento jurídico do escritório: base RAG, teses, jurisprudência interna e memória institucional"
      />

      <ConhecimentoStats />

      <div className="mb-6">
        <h2 className="text-sm font-semibold text-slate-700 mb-3">Categorias</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {CATEGORIAS.map(({ to, label, desc, icon: Icon }) => (
            <Link
              key={to}
              to={to}
              className="card p-4 flex items-start gap-3 transition-all hover:border-primary-300 hover:shadow-sm"
            >
              <span className="rounded-xl bg-primary-50 p-2.5 text-primary-600 ring-1 ring-inset ring-primary-100">
                <Icon className="h-5 w-5" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1 text-sm font-semibold text-slate-800">
                  {label}
                  <ChevronRight className="h-3.5 w-3.5 text-slate-400" />
                </div>
                <p className="mt-0.5 text-xs text-slate-500">{desc}</p>
              </div>
            </Link>
          ))}
        </div>
      </div>

      <div className="flex gap-2 mb-6 max-w-2xl">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && buscar()}
          placeholder="Buscar tese, jurisprudência, conceito… (mín. 3 letras)"
          className="input flex-1"
        />
        <button
          onClick={buscar}
          disabled={loading || q.trim().length < 3}
          className="btn-primary"
        >
          {loading ? "Buscando…" : "🔍 Buscar"}
        </button>
      </div>

      {loading && (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      )}

      {!loading && searched && (
        <>
          <p className="text-sm text-gray-500 mb-3">
            {total} resultado(s) para “{q}”
          </p>
          <div className="grid lg:grid-cols-2 gap-4">
            <Bloco
              titulo="Base RAG (leis, súmulas, doutrina)"
              cor="bg-ai-500"
              n={res.rag.length}
            >
              {res.rag.map((r, i) => (
                <div key={i} className="text-sm border-b border-gray-100 pb-2">
                  <div className="flex justify-between">
                    <span className="text-xs bg-ai-100 text-ai-700 px-2 rounded">
                      {r.categoria}
                    </span>
                    {r.score != null && (
                      <span className="text-xs text-gray-400">
                        {Math.round(r.score * 100)}%
                      </span>
                    )}
                  </div>
                  <p className="text-gray-700 text-xs mt-1">
                    {(r.conteudo ?? r.titulo ?? "").slice(0, 200)}…
                  </p>
                </div>
              ))}
            </Bloco>
            <Bloco
              titulo="Teses do escritório"
              cor="bg-primary-500"
              n={res.teses.length}
            >
              {res.teses.map((t: any, i: number) => (
                <div key={i} className="text-sm border-b border-gray-100 pb-2">
                  <p className="font-medium text-gray-800">{t.titulo}</p>
                  <p className="text-gray-500 text-xs">
                    {t.area_juridica}{" "}
                    {t.taxa_sucesso != null &&
                      `· ${Math.round((t.taxa_sucesso || 0) * 100)}% sucesso`}
                  </p>
                </div>
              ))}
            </Bloco>
            <Bloco
              titulo="Jurisprudência interna"
              cor="bg-green-500"
              n={res.juris.length}
            >
              {res.juris.map((j: any, i: number) => (
                <div key={i} className="text-sm border-b border-gray-100 pb-2">
                  <p className="font-medium text-gray-800">{j.titulo}</p>
                  <p className="text-gray-500 text-xs">
                    {j.tribunal} {j.ementa && `· ${j.ementa.slice(0, 80)}…`}
                  </p>
                </div>
              ))}
            </Bloco>
            <Bloco
              titulo="Memória institucional"
              cor="bg-warn-500"
              n={res.memoria.length}
            >
              {res.memoria.map((m: any, i: number) => (
                <div key={i} className="text-sm border-b border-gray-100 pb-2">
                  <p className="font-medium text-gray-800">{m.titulo}</p>
                  <p className="text-gray-500 text-xs">
                    {m.tipo} {m.resultado && `· ${m.resultado}`}
                  </p>
                </div>
              ))}
            </Bloco>
          </div>
        </>
      )}

      {!searched && (
        <p className="text-center text-gray-400 text-sm py-12">
          Digite um termo para buscar em todas as fontes de conhecimento ao
          mesmo tempo.
        </p>
      )}
    </div>
  );
}
