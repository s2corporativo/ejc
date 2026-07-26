import React, { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { toast } from "../../components/Toast";
import Markdown from "../../components/Markdown";
import api from "../../lib/api";
import {
  AVISO_FERRAMENTA_NAO_HOMOLOGADA,
  mensagemErroFerramenta,
} from "../../lib/iaErro";
import AnaliseEstrategica from "../../components/AnaliseEstrategica";
import { Spinner } from "../../components/UI";
import type { Case } from "../../types";
import { RAMOS } from "../ramos/ramosConfig";
import type { FerramentaConfig } from "../ramos/ramosConfig";

const AREA_PARA_RAMO: Record<string, string[]> = {
  empresarial: ["empresarial"],
  civil: ["civel", "bancario"],
  criminal: ["penal"],
  trabalhista: ["trabalhista"],
  tributario: ["administrativo"],
  ambiental: ["administrativo"],
  consumidor: ["civel"],
  familia: ["civel"],
  previdenciario: [],
};

function MiniFerramentaCalc({ f }: { f: FerramentaConfig }) {
  function rotulo(v: string) {
    return v.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }
  const [vals, setVals] = React.useState<Record<string, any>>(() => {
    const init: Record<string, any> = {};
    f.campos.forEach((c) => {
      if (c.default !== undefined) init[c.nome] = c.default;
    });
    return init;
  });
  const [res, setRes] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(false);
  const [erro, setErro] = React.useState<string | null>(null);

  const calcular = async () => {
    setLoading(true);
    setErro(null);
    setRes(null);
    try {
      const r = await api.get(f.endpoint, { params: vals });
      setRes(r.data);
    } catch (e: any) {
      // 503 "ferramenta_nao_homologada" vira mensagem controlada — nunca
      // erro genérico nem `detail` objeto renderizado cru.
      setErro(mensagemErroFerramenta(e));
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    if (f.autoLoad) calcular();
  }, [f.id]); // eslint-disable-line

  return (
    <div className="card p-3">
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-xs font-semibold text-navy">{f.titulo}</span>
        {f.homologada === false && (
          <span
            className="text-[10px] font-semibold text-warn-800 bg-warn-100 border border-warn-300 px-1.5 rounded-full whitespace-nowrap"
            title={AVISO_FERRAMENTA_NAO_HOMOLOGADA}
          >
            ⚠️ Não homologada
          </span>
        )}
        {f.autoLoad && res && (
          <span className="text-[10px] text-green-600 bg-green-50 px-1 rounded">
            ● ao vivo
          </span>
        )}
      </div>
      <p className="text-[11px] text-slate-400 mb-2">{f.baseLegal}</p>
      {f.campos.length > 0 && (
        <div className="grid grid-cols-2 gap-1.5 mb-2">
          {f.campos.map((c) => (
            <div key={c.nome}>
              <label className="text-[10px] text-slate-500 block mb-0.5">
                {c.label}
              </label>
              {c.tipo === "select" ? (
                <select
                  className="input text-xs py-1"
                  value={vals[c.nome] ?? ""}
                  onChange={(e) =>
                    setVals({ ...vals, [c.nome]: e.target.value })
                  }
                >
                  <option value="">—</option>
                  {c.opcoes?.map((o) => (
                    <option key={o} value={o}>
                      {rotulo(o)}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className="input text-xs py-1"
                  type={c.tipo}
                  step={c.tipo === "number" ? "0.01" : undefined}
                  value={vals[c.nome] ?? ""}
                  onChange={(e) =>
                    setVals({ ...vals, [c.nome]: e.target.value })
                  }
                />
              )}
            </div>
          ))}
        </div>
      )}
      {(!f.autoLoad || f.campos.length > 0) && (
        <button
          className="btn-gold text-xs py-1 px-3 mt-1"
          disabled={loading}
          onClick={calcular}
        >
          {loading ? "..." : f.campos.length === 0 ? "Atualizar" : "Calcular"}
        </button>
      )}
      {erro && <p className="text-xs text-danger-600 mt-2">{erro}</p>}
      {res && (
        <div className="mt-2 p-2 bg-gold-50 rounded text-[11px] space-y-0.5 border border-gold-200">
          {res.homologada === false && (
            <p className="text-warn-800 font-medium">
              ⚠️{" "}
              {res.aviso_homologacao || AVISO_FERRAMENTA_NAO_HOMOLOGADA}
            </p>
          )}
          {typeof res === "object" &&
            Object.entries(res as Record<string, any>).map(([k, v]) => {
              // Exibidos no aviso dedicado de homologação — não na tabela.
              if (k === "homologada" || k === "aviso_homologacao") return null;
              if (k === "aviso")
                return (
                  <p
                    key={k}
                    className="text-slate-400 italic pt-1 mt-1 border-t border-gold-200"
                  >
                    {String(v)}
                  </p>
                );
              if (typeof v === "object" && v !== null) return null;
              return (
                <div key={k} className="flex justify-between gap-1">
                  <span className="text-slate-500">{rotulo(k)}</span>
                  <span className="font-medium text-navy text-right">
                    {typeof v === "boolean"
                      ? v
                        ? "✓ Sim"
                        : "✗ Não"
                      : String(v)}
                  </span>
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
}

function AnaliseContratoIA({ caseId }: { caseId: string }) {
  const [texto, setTexto] = React.useState("");
  const [tipo, setTipo] = React.useState("prestacao_servicos");
  const [resultado, setResultado] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(false);
  const [tab, setTab] = React.useState<"analise" | "comparar">("analise");
  const [texto2, setTexto2] = React.useState("");
  const [compResult, setCompResult] = React.useState<any>(null);
  const [compLoading, setCompLoading] = React.useState(false);

  const analisar = async () => {
    if (texto.trim().length < 100) {
      toast.error("Cole pelo menos 100 caracteres do contrato");
      return;
    }
    setLoading(true);
    setResultado(null);
    try {
      const { data } = await api.post("/ai/analisar-contrato", {
        texto_contrato: texto,
        tipo_contrato: tipo,
        case_id: caseId,
      });
      setResultado(data);
    } catch (e: any) {
      setResultado({ erro: e.response?.data?.detail || "Falha" });
    } finally {
      setLoading(false);
    }
  };

  const comparar = async () => {
    if (texto.trim().length < 50 || texto2.trim().length < 50) {
      toast.error("Cole os dois contratos para comparar");
      return;
    }
    setCompLoading(true);
    setCompResult(null);
    try {
      // Prompt de comparação montado no servidor (modo "comparacao") —
      // o cliente envia apenas os dois textos brutos.
      const { data } = await api.post("/ai/analisar-contrato", {
        texto_contrato: texto,
        texto_contrato_2: texto2,
        modo: "comparacao",
        tipo_contrato: tipo,
        case_id: caseId,
      });
      setCompResult(data);
    } catch (e: any) {
      setCompResult({ erro: e.response?.data?.detail || "Falha" });
    } finally {
      setCompLoading(false);
    }
  };

  const TIPOS = [
    "prestacao_servicos",
    "compra_venda",
    "locacao",
    "parceria_empresarial",
    "honorarios_advocaticios",
    "financiamento",
    "franquia",
    "trabalho_autonomo",
    "sigiloso_nda",
    "fornecimento",
    "empreitada",
    "licenca_uso",
    "outro",
  ];

  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-3">
        <Sparkles size={16} className="text-gold-600" />
        <h3 className="font-serif font-semibold text-navy text-sm">
          Análise de Contrato com IA
        </h3>
        <span className="text-[10px] bg-warn-100 text-warn-700 px-2 py-0.5 rounded-full font-medium">
          MINUTA · revisão obrigatória
        </span>
      </div>

      {/* Sub-tabs */}
      <div className="flex gap-1 mb-3 border-b border-gray-100">
        {(["analise", "comparar"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`text-xs px-3 py-1.5 font-medium border-b-2 -mb-px transition-colors ${
              tab === t
                ? "border-gold-500 text-gold-700"
                : "border-transparent text-slate-400 hover:text-slate-600"
            }`}
          >
            {t === "analise" ? "Analisar contrato" : "Comparar versões"}
          </button>
        ))}
      </div>

      <div className="mb-3">
        <label className="text-[11px] text-slate-500 mb-1 block">
          Tipo de contrato
        </label>
        <select
          className="input text-sm"
          value={tipo}
          onChange={(e) => setTipo(e.target.value)}
        >
          {TIPOS.map((t) => (
            <option key={t} value={t}>
              {t.replace(/_/g, " ").replace(/\w/g, (c) => c.toUpperCase())}
            </option>
          ))}
        </select>
      </div>

      {tab === "analise" ? (
        <>
          <textarea
            className="input text-sm font-mono"
            rows={8}
            placeholder="Cole aqui o texto completo do contrato para análise..."
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
          />
          <div className="flex items-center justify-between mt-2">
            <span className="text-[11px] text-slate-400">
              {texto.length} chars
            </span>
            <button
              className="btn-gold text-sm"
              disabled={loading}
              onClick={analisar}
            >
              {loading ? (
                <>
                  <Spinner /> Analisando...
                </>
              ) : (
                "🔍 Identificar brechas e riscos"
              )}
            </button>
          </div>
          {resultado && <ResultadoContratoIA data={resultado} />}
        </>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] font-semibold text-slate-600 mb-1 block">
                Contrato A (original / atual)
              </label>
              <textarea
                className="input text-xs font-mono"
                rows={7}
                placeholder="Cole o Contrato A..."
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
              />
            </div>
            <div>
              <label className="text-[11px] font-semibold text-slate-600 mb-1 block">
                Contrato B (proposta / nova versão)
              </label>
              <textarea
                className="input text-xs font-mono"
                rows={7}
                placeholder="Cole o Contrato B..."
                value={texto2}
                onChange={(e) => setTexto2(e.target.value)}
              />
            </div>
          </div>
          <div className="flex justify-end mt-2">
            <button
              className="btn-gold text-sm"
              disabled={compLoading}
              onClick={comparar}
            >
              {compLoading ? (
                <>
                  <Spinner /> Comparando...
                </>
              ) : (
                "⚖️ Comparar contratos"
              )}
            </button>
          </div>
          {compResult && <ResultadoContratoIA data={compResult} />}
        </>
      )}
    </div>
  );
}

function ResultadoContratoIA({ data }: { data: any }) {
  if (data.erro)
    return (
      <div className="mt-3 p-3 bg-danger-50 text-danger-700 text-xs rounded">
        {data.erro}
      </div>
    );
  return (
    <div className="mt-3 border border-gold-200 rounded-lg bg-gold-50 p-4">
      <Markdown
        source={data.resposta}
        className="prose prose-sm max-w-none text-navy text-xs leading-relaxed"
      />
      {data.fontes?.length > 0 && (
        <div className="mt-3 pt-3 border-t border-gold-200">
          <p className="text-[10px] font-semibold text-gold-700 uppercase mb-1">
            Fontes utilizadas
          </p>
          <div className="flex flex-wrap gap-1">
            {data.fontes.map((f: any, i: number) => (
              <span
                key={i}
                className="text-[10px] bg-white border border-gold-200 px-1.5 py-0.5 rounded text-slate-600"
              >
                {f.titulo?.slice(0, 50)}
              </span>
            ))}
          </div>
        </div>
      )}
      {(data.aviso || data.aviso_hitl) && (
        <p className="text-[11px] text-warn-700 mt-2 italic">
          {data.aviso || data.aviso_hitl}
        </p>
      )}
    </div>
  );
}

export default function TabFerramentas({ caso }: { caso: Case }) {
  const slugs = AREA_PARA_RAMO[caso.area] ?? [];
  const configs = slugs.map((s) => RAMOS[s]).filter(Boolean);
  const [ramoAtivo, setRamoAtivo] = React.useState(slugs[0] ?? "");
  const cfg = configs.find((c) => c.slug === ramoAtivo) ?? configs[0];

  // Agrupar ferramentas por grupo
  const grupos = cfg
    ? (() => {
        const g: Record<string, FerramentaConfig[]> = {};
        cfg.ferramentas.forEach((f) => {
          const key = f.grupo ?? "Calculadoras";
          if (!g[key]) g[key] = [];
          g[key].push(f);
        });
        return g;
      })()
    : {};

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-navy-50 border border-navy-100 rounded-xl p-4">
        <h2 className="font-serif font-bold text-navy text-sm mb-0.5">
          Ferramentas para este caso
        </h2>
        <p className="text-xs text-slate-500">
          Calculadoras e análises IA filtradas pela área{" "}
          <strong>{caso.area}</strong>. Todos os resultados são minutas —
          revisão obrigatória.
        </p>
      </div>

      {/* Ramo sub-tabs (se houver mais de um) */}
      {configs.length > 1 && (
        <div className="flex gap-1 border-b border-gray-200">
          {configs.map((c) => (
            <button
              key={c.slug}
              onClick={() => setRamoAtivo(c.slug)}
              className={`text-xs px-3 py-2 font-medium border-b-2 -mb-px whitespace-nowrap transition-colors ${
                ramoAtivo === c.slug
                  ? "border-gold-500 text-gold-700"
                  : "border-transparent text-slate-400 hover:text-slate-600"
              }`}
            >
              {c.titulo.replace("Direito ", "")}
            </button>
          ))}
        </div>
      )}

      {/* Calculadoras agrupadas */}
      {cfg ? (
        Object.entries(grupos).map(([grupo, ferrs]) => (
          <div key={grupo}>
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
              {grupo}
            </h3>
            <div className="grid md:grid-cols-2 gap-3">
              {ferrs.map((f) => (
                <MiniFerramentaCalc key={f.id} f={f} />
              ))}
            </div>
          </div>
        ))
      ) : (
        <div className="text-center py-8 text-slate-400 text-sm">
          Nenhuma ferramenta específica para a área <strong>{caso.area}</strong>
          .
          <br />
          Acesse Ramos no menu lateral para as calculadoras gerais.
        </div>
      )}

      {/* Análise Estratégica IA — sempre disponível */}
      <AnaliseEstrategica caseId={caso.id} />

      {/* Análise de Contrato IA — sempre disponível */}
      <AnaliseContratoIA caseId={caso.id} />
    </div>
  );
}
