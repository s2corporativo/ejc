// ── src/pages/AssistenteIA.tsx ───────────────────────────────────────────────
// Assistente de IA do escritório sobre as PORTAS CANÔNICAS por capacidade
// (item I1, 03/09/2026): /ia/conversar, /ia/resumir, /ia/redigir e /ia/analisar.
// Antes cada ferramenta chamava um endpoint diferente (/ai/pesquisar,
// /ai/resumir-texto, /ai/traduzir-andamento, /ai/gerar-minuta,
// /ia-especializada/{perfil}) e a qualidade da resposta dependia da porta.
//
// Os limites de caracteres abaixo são os MESMOS do backend
// (`schemas/ai.py::LIMITES_CAPACIDADE`): limite que só existe no servidor vira
// 422 depois de a pessoa escrever a peça inteira (achado E6).
import { useState } from "react";
import { useLocation } from "react-router";
import Markdown from "../components/Markdown";
import api from "../lib/api";
import { PageHeader, Spinner } from "../components/UI";
import { mensagemErroIA, ROTULO_IA_NAO_ATIVADA } from "../lib/iaErro";
import { MENSAGEM_IA_NAO_ATIVADA, useIaStatus } from "../lib/iaStatus";

type Tool = "pesquisa" | "resumir" | "traduzir" | "minuta" | "especialista";

// Instrução do próprio usuário (não é system prompt): a capacidade `conversar`
// responde a pergunta; aqui a pergunta é "explique isto ao cliente".
const PREFIXO_TRADUZIR =
  "Explique o andamento processual abaixo em linguagem simples e acolhedora " +
  "para o cliente leigo, sem jargão jurídico e sem prometer resultado.\n\n";

// capacidade → limites do backend. `minuta` compõe tema + fatos em UMA
// mensagem, então o contador vale para o texto composto.
const LIMITES: Record<Tool, { min: number; max: number; capacidade: string }> =
  {
    pesquisa: { min: 3, max: 12000, capacidade: "conversar" },
    resumir: { min: 20, max: 200000, capacidade: "resumir" },
    traduzir: {
      min: 3,
      max: 12000 - PREFIXO_TRADUZIR.length,
      capacidade: "conversar",
    },
    minuta: { min: 5, max: 12000, capacidade: "redigir" },
    especialista: { min: 30, max: 200000, capacidade: "analisar" },
  };

const MAX_TEMA = 2000;
const MAX_FATOS = LIMITES.minuta.max - MAX_TEMA - 200; // folga do cabeçalho

const TOOLS: { key: Tool; label: string; icon: string; desc: string }[] = [
  {
    key: "pesquisa",
    label: "Pesquisa",
    icon: "🔎",
    desc: "Pergunte e a IA responde; quando houver documentos ingeridos, usa a base do escritório (RAG).",
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
    desc: "Gere um rascunho de peça (usa a jurisprudência interna quando disponível).",
  },
  {
    key: "especialista",
    label: "Especialistas",
    icon: "🧠",
    desc: "5 perfis especializados (Comercial, Atendimento, Jurídica, Financeira, Societária) — usam a base do escritório quando há documentos ingeridos.",
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
  const { disponivel: iaDisponivel, mensagem: iaMensagem } = useIaStatus();
  const location = useLocation();
  const navigationState = location.state as { perguntaRapida?: string } | null;
  const [tool, setTool] = useState<Tool>("pesquisa");
  const [perfil, setPerfil] = useState("juridica");
  // A pergunta rápida chega pelo state interno do React Router, sem ser
  // exposta na URL. O conteúdo não é enviado automaticamente: o profissional
  // ainda revisa e confirma explicitamente o envio dentro da ferramenta de IA.
  const [texto, setTexto] = useState(
    () => navigationState?.perguntaRapida || "",
  );
  const [tema, setTema] = useState("");
  const [tipoPeca, setTipoPeca] = useState("petição inicial");
  const [area, setArea] = useState("");
  const [fatos, setFatos] = useState("");
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState<any>(null);
  const [erro, setErro] = useState("");

  const limite = LIMITES[tool];

  const trocar = (t: Tool) => {
    setTool(t);
    setRes(null);
    setErro("");
  };

  const mensagemMinuta = () =>
    `Tipo de peça: ${tipoPeca}\nÁrea: ${area || "geral"}\nTema/pedido: ${tema}` +
    (fatos.trim() ? `\n\nFatos: ${fatos}` : "");

  // Quantos caracteres serão de fato enviados nesta ferramenta.
  const usados = tool === "minuta" ? mensagemMinuta().length : texto.length;

  const executar = async () => {
    setLoading(true);
    setRes(null);
    setErro("");
    try {
      let data;
      if (tool === "pesquisa")
        ({ data } = await api.post("/ia/conversar", {
          texto,
          area: "pesquisa_juridica",
        }));
      else if (tool === "resumir")
        ({ data } = await api.post("/ia/resumir", { texto }));
      else if (tool === "traduzir")
        ({ data } = await api.post("/ia/conversar", {
          mensagem: PREFIXO_TRADUZIR + texto,
        }));
      else if (tool === "especialista")
        ({ data } = await api.post("/ia/analisar", { texto, perfil }));
      else
        ({ data } = await api.post("/ia/redigir", {
          texto: mensagemMinuta(),
          area: area || undefined,
          opcoes: { tipo_peca: tipoPeca },
        }));
      setRes(data);
    } catch (e: any) {
      setErro(mensagemErroIA(e));
    } finally {
      setLoading(false);
    }
  };

  const podeEnviar =
    tool === "minuta"
      ? tema.trim().length > 4 && usados <= limite.max
      : texto.trim().length >= limite.min && usados <= limite.max;
  const t = TOOLS.find((x) => x.key === tool)!;

  // Conteúdo canônico com queda para o contrato antigo — a tela não pode
  // depender de qual porta respondeu.
  const conteudo = res ? (res.conteudo ?? res.resposta ?? "") : "";
  const fontes = res ? (res.fontes_rag ?? res.fontes ?? []) : [];
  const avisoHitl = res ? (res.aviso_hitl ?? res.aviso ?? "") : "";
  const alertas: string[] = res?.alertas ?? [];

  const contador = (
    <p
      data-testid="contador-caracteres"
      className={`mt-1 text-xs ${usados > limite.max ? "text-danger-600" : "text-slate-400"}`}
    >
      {usados} / {limite.max} caracteres
      {usados > limite.max ? " — acima do limite desta ferramenta" : ""}
    </p>
  );

  return (
    <div>
      <PageHeader
        eyebrow="Inteligência"
        title="Assistente IA"
        subtitle="Pesquisa, resumo, tradução e minutas — sempre como rascunho (revisão humana / OAB)"
      />

      {!iaDisponivel && (
        <div className="mb-4 rounded-lg border border-warn-200 bg-warn-50 px-4 py-3 text-sm text-warn-800">
          {iaMensagem || MENSAGEM_IA_NAO_ATIVADA}
        </div>
      )}

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
                    maxLength={120}
                    className="input w-full"
                  />
                </div>
                <div>
                  <label className="label">Área</label>
                  <input
                    value={area}
                    onChange={(e) => setArea(e.target.value)}
                    placeholder="cível, trabalhista…"
                    maxLength={60}
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
                  maxLength={MAX_TEMA}
                  className="input w-full"
                />
              </div>
              <div>
                <label className="label">Fatos (opcional)</label>
                <textarea
                  rows={5}
                  value={fatos}
                  onChange={(e) => setFatos(e.target.value)}
                  maxLength={MAX_FATOS}
                  className="input w-full"
                />
              </div>
              {contador}
            </div>
          ) : (
            <>
              <textarea
                rows={10}
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                maxLength={limite.max}
                placeholder={
                  tool === "pesquisa"
                    ? "Sua pergunta jurídica…"
                    : "Cole o texto aqui…"
                }
                className="input w-full"
              />
              {contador}
            </>
          )}
          <button
            onClick={executar}
            disabled={loading || !podeEnviar || !iaDisponivel}
            title={iaDisponivel ? undefined : ROTULO_IA_NAO_ATIVADA}
            className="btn-primary mt-3"
          >
            {!iaDisponivel
              ? "IA não ativada"
              : loading
                ? "Processando…"
                : `${t.icon} Executar`}
          </button>
        </div>

        <div className="card p-5 min-h-[16rem]">
          <h3 className="font-semibold text-ink mb-3">Resultado</h3>
          {loading && (
            <div className="flex justify-center py-10">
              <Spinner />
            </div>
          )}
          {erro && <p className="text-sm text-danger-600">{erro}</p>}
          {!loading && !res && !erro && (
            <p className="text-sm text-slate-400">O resultado aparece aqui.</p>
          )}
          {res && (
            <div className="space-y-3">
              <Markdown
                source={conteudo}
                className="text-sm text-slate-700 leading-relaxed"
              />
              {fontes.length > 0 && (
                <div
                  data-testid="fontes-rag"
                  className="pt-2 border-t border-bronze-pale"
                >
                  <p className="text-xs font-semibold text-slate-500 mb-1">
                    Fontes consultadas
                  </p>
                  <ul className="text-xs text-slate-500 space-y-0.5">
                    {fontes.map((f: any, i: number) => (
                      <li key={i}>• {f.titulo || f.categoria || f.fonte}</li>
                    ))}
                  </ul>
                </div>
              )}
              {alertas.length > 0 && (
                <ul
                  data-testid="alertas-ia"
                  className="text-xs text-warn-700 space-y-0.5"
                >
                  {alertas.map((a, i) => (
                    <li key={i}>⚠️ {a}</li>
                  ))}
                </ul>
              )}
              {avisoHitl && (
                <p
                  data-testid="aviso-hitl"
                  className="text-xs text-warn-600 border-t border-bronze-pale pt-2"
                >
                  {avisoHitl}
                </p>
              )}
              <button
                onClick={() => navigator.clipboard?.writeText(conteudo)}
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
