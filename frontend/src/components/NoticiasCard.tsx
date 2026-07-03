// ── src/components/NoticiasCard.tsx ──────────────────────────────────────────
// Card de Notícias Jurídicas no dashboard. Consome /api/noticias (ConJur+JOTA),
// filtra por ramo (client-side), resume por IA sob demanda e permite salvar a
// notícia como conhecimento interno (RAG). Copyright-safe: só manchete+resumo+link.
import { useEffect, useMemo, useState } from "react";
import {
  Newspaper,
  ExternalLink,
  Sparkles,
  BookmarkPlus,
  Check,
  RefreshCw,
} from "lucide-react";
import api from "../lib/api";

type Noticia = {
  titulo: string;
  link: string;
  data?: string;
  resumo?: string;
  fonte?: string;
};

// Filtro por ramo — casa palavras-chave no título+resumo (sem custo de backend)
const RAMOS: { k: string; label: string; termos: string[] }[] = [
  { k: "todos", label: "Todos", termos: [] },
  {
    k: "trabalhista",
    label: "Trabalhista",
    termos: ["trabalh", "clt", "tst", "emprego", "sindical", "rescis"],
  },
  {
    k: "tributario",
    label: "Tributário",
    termos: [
      "tribut",
      "imposto",
      "fiscal",
      "icms",
      "iss",
      "receita",
      "carf",
      "pgfn",
    ],
  },
  {
    k: "civel",
    label: "Cível",
    termos: [
      "cível",
      "civil",
      "consumidor",
      "cdc",
      "contrato",
      "indeniz",
      "dano",
    ],
  },
  {
    k: "penal",
    label: "Penal",
    termos: ["penal", "crime", "criminal", "stf", "prisão", "habeas"],
  },
  {
    k: "empresarial",
    label: "Empresarial",
    termos: ["empres", "societ", "falência", "recuperação", "cvm"],
  },
  {
    k: "ambiental",
    label: "Ambiental",
    termos: ["ambient", "ibama", "licenc", "desmat"],
  },
  {
    k: "digital",
    label: "Digital/LGPD",
    termos: ["lgpd", "dado", "digital", "anpd", "internet"],
  },
];

export default function NoticiasCard() {
  const [itens, setItens] = useState<Noticia[]>([]);
  const [loading, setLoading] = useState(true);
  const [ramo, setRamo] = useState("todos");
  const [resumos, setResumos] = useState<Record<number, string>>({});
  const [resumindo, setResumindo] = useState<number | null>(null);
  const [salvos, setSalvos] = useState<Record<number, boolean>>({});

  const load = (forcar = false) => {
    setLoading(true);
    api
      .get(`/noticias?limit=30${forcar ? "&forcar=true" : ""}`)
      .then((r) => setItens(r.data?.itens ?? []))
      .catch(() => setItens([]))
      .finally(() => setLoading(false));
  };
  useEffect(() => {
    load();
  }, []);

  const filtradas = useMemo(() => {
    const cfg = RAMOS.find((r) => r.k === ramo);
    if (!cfg || !cfg.termos.length) return itens;
    return itens.filter((n) => {
      const t = `${n.titulo} ${n.resumo ?? ""}`.toLowerCase();
      return cfg.termos.some((term) => t.includes(term));
    });
  }, [itens, ramo]);

  const resumir = async (i: number, n: Noticia) => {
    setResumindo(i);
    try {
      const txt = `${n.titulo}. ${n.resumo ?? ""}`.slice(0, 4000);
      const { data } = await api.post("/ai/resumir-texto", { texto: txt });
      setResumos((p) => ({
        ...p,
        [i]: data.resumo || data.resposta || data.texto || "—",
      }));
    } catch (e: any) {
      setResumos((p) => ({
        ...p,
        [i]:
          e.response?.status === 503 ? "IA desabilitada." : "Falha ao resumir.",
      }));
    } finally {
      setResumindo(null);
    }
  };

  const salvar = async (i: number, n: Noticia) => {
    try {
      await api.post("/rag/ingest", {
        titulo: `[Notícia] ${n.titulo}`.slice(0, 200),
        categoria: "noticia_juridica",
        conteudo: `${n.titulo}\n\n${n.resumo ?? ""}\n\nFonte: ${n.fonte ?? ""} — ${n.link}`,
        fonte: n.fonte || "Notícia jurídica",
      });
      setSalvos((p) => ({ ...p, [i]: true }));
    } catch {
      /* silencioso */
    }
  };

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-navy-900 flex items-center gap-2">
          <Newspaper size={15} className="text-bronze" /> Notícias jurídicas
        </h3>
        <button
          onClick={() => load(true)}
          className="text-slate-400 hover:text-bronze"
          title="Atualizar"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* Filtro por ramo */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        {RAMOS.map((r) => (
          <button
            key={r.k}
            onClick={() => setRamo(r.k)}
            className={`text-[11px] px-2 py-0.5 rounded-full border transition-colors ${
              ramo === r.k
                ? "bg-navy text-white border-navy"
                : "bg-white text-slate-500 border-bronze-pale hover:border-bronze"
            }`}
          >
            {r.label}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-sm text-slate-400 py-6 text-center">
          Carregando notícias…
        </p>
      ) : filtradas.length === 0 ? (
        <p className="text-sm text-slate-400 py-6 text-center">
          Sem notícias para este ramo.
        </p>
      ) : (
        <div className="space-y-2.5 max-h-[420px] overflow-y-auto pr-1">
          {filtradas.slice(0, 15).map((n, i) => (
            <div
              key={i}
              className="border-b border-bronze-50 pb-2.5 last:border-0"
            >
              <div className="flex items-start gap-2">
                <a
                  href={n.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-1 text-sm text-navy-800 hover:text-bronze leading-snug group"
                >
                  {n.titulo}
                  <ExternalLink
                    size={11}
                    className="inline ml-1 text-slate-300 group-hover:text-bronze"
                  />
                </a>
              </div>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-bronze-50 text-bronze-deep">
                  {n.fonte}
                </span>
                <button
                  onClick={() => resumir(i, n)}
                  disabled={resumindo === i}
                  className="text-[11px] text-slate-500 hover:text-bronze flex items-center gap-1"
                >
                  <Sparkles size={11} />{" "}
                  {resumindo === i ? "Resumindo…" : "Resumo IA"}
                </button>
                <button
                  onClick={() => salvar(i, n)}
                  disabled={salvos[i]}
                  className="text-[11px] text-slate-500 hover:text-success-600 flex items-center gap-1"
                >
                  {salvos[i] ? (
                    <>
                      <Check size={11} className="text-success-600" /> Salvo
                    </>
                  ) : (
                    <>
                      <BookmarkPlus size={11} /> Salvar
                    </>
                  )}
                </button>
              </div>
              {resumos[i] && (
                <p className="text-xs text-slate-600 bg-bronze-50/40 rounded-lg p-2 mt-1.5 whitespace-pre-wrap leading-relaxed">
                  {resumos[i]}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
      <p className="text-[10px] text-slate-400 mt-3 pt-2 border-t border-bronze-50">
        Manchetes de ConJur e JOTA · resumo por IA (revisão recomendada) ·
        "Salvar" envia ao acervo interno (RAG).
      </p>
    </div>
  );
}
