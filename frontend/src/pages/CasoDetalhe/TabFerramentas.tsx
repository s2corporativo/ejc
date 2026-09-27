import React, { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { toast } from "../../components/Toast";
import Markdown from "../../components/Markdown";
import api from "../../lib/api";
import {
  AVISO_FERRAMENTA_NAO_HOMOLOGADA,
  mensagemErroFerramenta,
} from "../../lib/iaErro";
import RodapeRegra, { METADADOS_REGRA } from "../../components/RodapeRegra";
import AnaliseEstrategica from "../../components/AnaliseEstrategica";
import IaDefensivaCaso from "./IaDefensivaCaso";
import { Spinner } from "../../components/UI";
import type { Case } from "../../types";
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
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-navy-50 border border-navy-100 rounded-xl p-4">
        <h2 className="font-serif font-bold text-navy text-sm mb-0.5">
          Inteligência para este caso
        </h2>
        <p className="text-xs text-slate-500">
          Análises e controles do núcleo de inteligência no contexto da área{" "}
          <strong>{caso.area}</strong>. Todos os resultados são minutas —
          revisão obrigatória.
        </p>
      </div>

      {/* Análise Estratégica IA — sempre disponível */}
      <AnaliseEstrategica caseId={caso.id} />

      {/* Análise de Contrato IA — sempre disponível */}
      <AnaliseContratoIA caseId={caso.id} />
      {/* IA Defensiva (Fase 3 / QA): antes aba própria "iaDefensiva" — agora
          embutida aqui, pois é ferramenta de trabalho estratégica do caso.
          Mantém HITL, histórico de revisões e trilha de auditoria. */}
      <IaDefensivaCaso caso={caso} />
    </div>
  );
}
