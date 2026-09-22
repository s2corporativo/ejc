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
import { useEffect, useState } from "react";
import { useLocation } from "react-router";
import Markdown from "../components/Markdown";
import api from "../lib/api";
import { PageHeader, Spinner } from "../components/UI";
import { mensagemErroIA, ROTULO_IA_NAO_ATIVADA } from "../lib/iaErro";
import { MENSAGEM_IA_NAO_ATIVADA, useIaStatus } from "../lib/iaStatus";

type Tool = "pesquisa" | "resumir" | "traduzir" | "minuta" | "manus" | "especialista";
type ProviderIA = "auto" | "groq" | "maritaca" | "anthropic" | "ollama";

const PROVIDERS: Array<{ value: ProviderIA; label: string; desc: string }> = [
  { value: "auto", label: "Automático", desc: "Groq no cotidiano; Maritaca em leitura, análise e pesquisa." },
  { value: "groq", label: "Groq", desc: "Tarefas corriqueiras e rápidas." },
  { value: "maritaca", label: "Maritaca", desc: "Leitura, análise, raciocínio e pesquisa jurídica." },
  { value: "anthropic", label: "Claude", desc: "Somente quando solicitado explicitamente." },
  { value: "ollama", label: "Local", desc: "IA local quando habilitada; indicado para sigilo reforçado." },
];

// Instrução do próprio usuário (não é system prompt): a capacidade `conversar`
// responde a pergunta; aqui a pergunta é "explique isto ao cliente".
const PREFIXO_TRADUZIR =
  "Explique o andamento processual abaixo em linguagem simples e acolhedora " +
  "para o cliente leigo, sem jargão jurídico e sem prometer resultado.\n\n";

// capacidade → limites do backend. `minuta` compõe tema + fatos em UMA
// mensagem, então o contador vale para o texto composto.
const LIMITES: Record<Tool, { min: number; max: number; capacidade: string }> = {
  pesquisa: { min: 3, max: 12000, capacidade: "conversar" },
  resumir: { min: 20, max: 200000, capacidade: "resumir" },
  traduzir: {
    min: 3,
    max: 12000 - PREFIXO_TRADUZIR.length,
    capacidade: "conversar",
  },
  minuta: { min: 5, max: 12000, capacidade: "redigir" },
  manus: { min: 30, max: 16000, capacidade: "manus" },
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
    key: "manus",
    label: "Raciocínio profundo",
    icon: "🧭",
    desc: "Manus em modo explícito para análise jurídica profunda e crítica. O conteúdo sai pseudonimizado e o resultado é sempre rascunho.",
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
  const [provider, setProvider] = useState<ProviderIA>("auto");
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
  const [manusHandle, setManusHandle] = useState<string | null>(null);

  const limite = LIMITES[tool];

  const trocar = (t: Tool) => {
    setTool(t);
    setRes(null);
    setErro("");
    setManusHandle(null);
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
      if (tool === "manus") {
        ({ data } = await api.post("/manus/deep-reasoning", {
          texto,
          area: area || undefined,
        }));
        setRes(data);
        setManusHandle(data?.handle || null);
        return;
      }
      if (tool === "pesquisa")
        ({ data } = await api.post("/ia/conversar", {
          texto,
          area: "pesquisa_juridica",
          provider,
        }));
      else if (tool === "resumir")
        ({ data } = await api.post("/ia/resumir", { texto, provider }));
      else if (tool === "traduzir")
        ({ data } = await api.post("/ia/conversar", {
          mensagem: PREFIXO_TRADUZIR + texto,
          provider,
        }));
      else if (tool === "especialista")
        ({ data } = await api.post("/ia/analisar", { texto, perfil, provider }));
      else
        ({ data } = await api.post("/ia/redigir", {
          texto: mensagemMinuta(),
          area: area || undefined,
          opcoes: { tipo_peca: tipoPeca },
          provider,
        }));
      setRes(data);
    } catch (e: any) {
      setErro(mensagemErroIA(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!manusHandle) return;
    let cancelado = false;
    let timer: number | undefined;

    const consultar = async () => {
      try {
        const { data } = await api.get(
          `/manus/deep-reasoning/${encodeURIComponent(manusHandle)}`,
        );
        if (cancelado) return;
        setRes(data);
        if (["completed", "error", "waiting"].includes(data?.status)) {
          setManusHandle(null);
          return;
        }
        timer = window.setTimeout(consultar, 4000);
      } catch (e: any) {
        if (cancelado) return;
        setErro(mensagemErroIA(e));
        setManusHandle(null);
      }
    };

    timer = window.setTimeout(consultar, 3000);
    return () => {
      cancelado = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [manusHandle]);

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
      {tool !== "manus" && (
      <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
        <label className="label">Motor de IA</label>
        <div className="mt-2 flex flex-wrap gap-2">
          {PROVIDERS.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => setProvider(p.value)}
              title={p.desc}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                provider === p.value
                  ? "border-ai-600 bg-ai-600 text-white"
                  : "border-slate-200 bg-white text-slate-600 hover:border-ai-300"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-slate-500">
          {PROVIDERS.find((p) => p.value === provider)?.desc}
        </p>
      </div>
      )}

      {tool === "manus" && (
        <div className="mb-4 rounded-lg border border-ai-200 bg-ai-50/40 p-3 text-sm text-slate-700">
          <span className="font-semibold">Motor: Manus — Raciocínio Profundo.</span>{" "}
          Uso somente por seleção explícita; sem fallback automático. Conteúdo enviado ao provider externo passa por pseudonimização LGPD.
        </div>
      )}

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
              {tool === "manus" && (
                <div className="mb-3">
                  <label className="label">Área jurídica (opcional)</label>
                  <input
                    value={area}
                    onChange={(e) => setArea(e.target.value)}
                    maxLength={100}
                    placeholder="Ex.: cível, empresarial, ambiental…"
                    className="input w-full"
                  />
                </div>
              )}
              <textarea
                rows={10}
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                maxLength={limite.max}
                placeholder={
                  tool === "pesquisa"
                    ? "Sua pergunta jurídica…"
                    : tool === "manus"
                      ? "Descreva o caso ou questão para raciocínio profundo…"
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
              {res.provider === "manus" && res.status === "running" && (
                <p className="text-sm text-ai-700" data-testid="manus-status">
                  Manus está executando o raciocínio profundo. O resultado aparecerá aqui quando concluir.
                </p>
              )}
              {(res.provider || res.modelo) && (
                <div
                  data-testid="motor-ia-usado"
                  className="flex flex-wrap items-center gap-2 text-xs text-slate-500"
                >
                  <span className="font-semibold text-slate-600">Motor usado:</span>
                  <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-1">
                    {res.provider || "provider não informado"}
                    {res.modelo ? ` · ${res.modelo}` : ""}
                  </span>
                  {res.fallback_ativado && (
                    <span className="text-warn-700">fallback registrado</span>
                  )}
                </div>
              )}
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
