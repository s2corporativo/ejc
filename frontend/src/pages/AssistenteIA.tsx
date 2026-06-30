import { useState } from "react";
import Markdown from "../components/Markdown";
import api from "../lib/api";
import { PageHeader, Spinner } from "../components/UI";

type Tool = "pesquisa" | "resumir" | "traduzir" | "minuta" | "especialista";
const TOOLS: { key: Tool; label: string; icon: string; desc: string }[] = [
  {
    key: "pesquisa",
    label: "Pesquisa",
    icon: "🔎",
    desc: "Pergunte e a IA responde com base no conhecimento do escritório (RAG).",
  },
  {
    key: "resumir",
    label: "Resumir",
    icon: "📄",
    desc: "Cole uma peça/decisão longa e receba os pontos-chave.",
  },
  {
    key: "traduzir",
    label: "Traduzir p/ cliente",
    icon: "💬",
    desc: "Transforme um andamento técnico em linguagem simples para o cliente.",
  },
  {
    key: "minuta",
    label: "Minuta",
    icon: "✍️",
    desc: "Gere um rascunho de peça com apoio da jurisprudência interna.",
  },
  {
    key: "especialista",
    label: "Especialistas",
    icon: "🧠",
    desc: "5 IAs especializadas (Comercial, Atendimento, Jurídica, Financeira, Societária) sobre a mesma base.",
  },
];
const PERFIS = [
  { id: "comercial", label: "Comercial" },
  { id: "atendimento", label: "Atendimento" },
  { id: "juridica", label: "Jurídica" },
  { id: "financeira", label: "Financeira" },
  { id: "societaria", label: "Societária" },
];

export default function AssistenteIA() {
  const [tool, setTool] = useState<Tool>("pesquisa");
  const [perfil, setPerfil] = useState("juridica");
  const [texto, setTexto] = useState("");
  const [tema, setTema] = useState("");
  const [tipoPeca, setTipoPeca] = useState("petição inicial");
  const [area, setArea] = useState("");
  const [fatos, setFatos] = useState("");
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState<any>(null);
  const [erro, setErro] = useState("");

  const trocar = (t: Tool) => {
    setTool(t);
    setRes(null);
    setErro("");
  };

  const executar = async () => {
    setLoading(true);
    setRes(null);
    setErro("");
    try {
      let data;
      if (tool === "pesquisa")
        ({ data } = await api.post("/ai/pesquisar", { pergunta: texto }));
      else if (tool === "resumir")
        ({ data } = await api.post("/ai/resumir-texto", { texto }));
      else if (tool === "traduzir")
        ({ data } = await api.post("/ai/traduzir-andamento", { texto }));
      else if (tool === "especialista")
        ({ data } = await api.post(`/ia-especializada/${perfil}`, {
          pergunta: texto,
        }));
      else
        ({ data } = await api.post("/ai/gerar-minuta", {
          tema,
          tipo_peca: tipoPeca,
          area,
          fatos,
        }));
      setRes(data);
    } catch (e: any) {
      setErro(
        e.response?.data?.detail ||
          "Falha na IA. A IA pode estar desabilitada (.env).",
      );
    } finally {
      setLoading(false);
    }
  };

  const podeEnviar =
    tool === "minuta" ? tema.trim().length > 4 : texto.trim().length > 4;
  // especialista usa o campo "texto" como pergunta
  const t = TOOLS.find((x) => x.key === tool)!;

  return (
    <div>
      <PageHeader
        eyebrow="Inteligência"
        title="Assistente IA"
        subtitle="Pesquisa, resumo, tradução e minutas — sempre como rascunho (revisão humana / OAB)"
      />

      <div className="flex flex-wrap gap-2 mb-5">
        {TOOLS.map((x) => (
          <button
            key={x.key}
            onClick={() => trocar(x.key)}
            className={`px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
              tool === x.key
                ? "bg-navy text-white border-navy"
                : "bg-white border-bronze-pale text-navy-700 hover:border-bronze"
            }`}
          >
            <span className="mr-1">{x.icon}</span>
            {x.label}
          </button>
        ))}
      </div>
      {tool === "especialista" && (
        <div className="mb-3 flex items-center gap-2">
          <span className="text-sm text-slate-500">Perfil:</span>
          {PERFIS.map((pf) => (
            <button
              key={pf.id}
              onClick={() => setPerfil(pf.id)}
              className={`px-3 py-1 rounded-full text-xs font-medium border ${perfil === pf.id ? "bg-bronze text-white border-bronze" : "bg-white border-slate-200 text-slate-600"}`}
            >
              {pf.label}
            </button>
          ))}
        </div>
      )}

      <div className="grid lg:grid-cols-2 gap-5">
        <div className="card p-5">
          <p className="text-xs text-slate-400 mb-3">{t.desc}</p>
          {tool === "minuta" ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label">Tipo de peça</label>
                  <input
                    value={tipoPeca}
                    onChange={(e) => setTipoPeca(e.target.value)}
                    className="input w-full"
                  />
                </div>
                <div>
                  <label className="label">Área</label>
                  <input
                    value={area}
                    onChange={(e) => setArea(e.target.value)}
                    placeholder="cível, trabalhista…"
                    className="input w-full"
                  />
                </div>
              </div>
              <div>
                <label className="label">Tema / pedido *</label>
                <input
                  value={tema}
                  onChange={(e) => setTema(e.target.value)}
                  placeholder="Ex.: indenização por dano moral por negativação indevida"
                  className="input w-full"
                />
              </div>
              <div>
                <label className="label">Fatos (opcional)</label>
                <textarea
                  rows={5}
                  value={fatos}
                  onChange={(e) => setFatos(e.target.value)}
                  className="input w-full"
                />
              </div>
            </div>
          ) : (
            <textarea
              rows={10}
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              placeholder={
                tool === "pesquisa"
                  ? "Sua pergunta jurídica…"
                  : "Cole o texto aqui…"
              }
              className="input w-full"
            />
          )}
          <button
            onClick={executar}
            disabled={loading || !podeEnviar}
            className="btn-primary mt-3"
          >
            {loading ? "Processando…" : `${t.icon} Executar`}
          </button>
        </div>

        <div className="card p-5 min-h-[16rem]">
          <h3 className="font-semibold text-ink mb-3">Resultado</h3>
          {loading && (
            <div className="flex justify-center py-10">
              <Spinner />
            </div>
          )}
          {erro && <p className="text-sm text-red-600">{erro}</p>}
          {!loading && !res && !erro && (
            <p className="text-sm text-slate-400">O resultado aparece aqui.</p>
          )}
          {res && (
            <div className="space-y-3">
              <Markdown source={res.resposta} className="text-sm text-slate-700 leading-relaxed" />
              {res.fontes?.length > 0 && (
                <div className="pt-2 border-t border-bronze-pale">
                  <p className="text-xs font-semibold text-slate-500 mb-1">
                    Fontes consultadas
                  </p>
                  <ul className="text-xs text-slate-500 space-y-0.5">
                    {res.fontes.map((f: any, i: number) => (
                      <li key={i}>• {f.titulo || f.categoria}</li>
                    ))}
                  </ul>
                </div>
              )}
              {res.aviso && (
                <p className="text-xs text-amber-600 border-t border-bronze-pale pt-2">
                  {res.aviso}
                </p>
              )}
              <button
                onClick={() => navigator.clipboard?.writeText(res.resposta)}
                className="btn-outline text-xs"
              >
                Copiar
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
