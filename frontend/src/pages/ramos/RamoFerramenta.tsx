import { useEffect, useState } from "react";
import { Link } from "react-router";
import { Calculator, TrendingUp } from "lucide-react";
import api from "../../lib/api";
import {
  AVISO_FERRAMENTA_NAO_HOMOLOGADA,
  mensagemErroFerramenta,
} from "../../lib/iaErro";
import { useCaseContext } from "../../stores/caseContext";
import { Spinner, fmtMoney } from "../../components/UI";
import RodapeRegra, { METADADOS_REGRA } from "../../components/RodapeRegra";
import type { FerramentaConfig } from "./ramosConfig";
import {
  camposVisiveis,
  chavesObsoletas,
  paramsVisiveis,
} from "./camposCondicionais";
import {
  linhasDoResultado,
  rodapeDoResultado,
  provenienciaDoResultado,
} from "./demonstrativo";

function rotulo(v: string) {
  return v.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function TaxasBacenView({
  taxas,
  aviso,
}: {
  taxas: Record<string, any>;
  aviso?: string;
}) {
  const labels: Record<string, string> = {
    selic_meta_aa: "SELIC Meta",
    cdi_diario: "CDI diário",
    tr_mensal: "TR mensal",
    ipca_15_mensal: "IPCA-15",
  };
  return (
    <div>
      <div className="grid grid-cols-2 gap-2 mb-2">
        {Object.entries(taxas).map(([chave, item]: [string, any]) => (
          <div
            key={chave}
            className="bg-white rounded p-2 border border-gold-100 text-center"
          >
            <div className="text-[10px] text-slate-500 uppercase tracking-wide">
              {labels[chave] || chave}
            </div>
            {item?.valor != null ? (
              <>
                <div className="text-lg font-bold text-navy">
                  {Number(item.valor).toFixed(4)}%
                </div>
                <div className="text-[10px] text-slate-400">{item?.data}</div>
              </>
            ) : (
              <div className="text-xs text-danger-500">indisponível</div>
            )}
          </div>
        ))}
      </div>
      {aviso && (
        <div className="text-[11px] text-slate-500 italic">{aviso}</div>
      )}
    </div>
  );
}

function VerbaRescisView({ data }: { data: any }) {
  const verbas = data.verbas as Record<string, number>;
  const total = data.total_bruto_estimado as number;
  const labels: Record<string, string> = {
    saldo_salario: "Saldo de salário",
    aviso_previo: "Aviso prévio",
    decimo_terceiro_proporcional: "13° proporcional",
    ferias_proporcionais_mais_um_terco: "Férias + 1/3",
    fgts_rescisorio_8pct: "FGTS (8% rescisório)",
    multa_fgts: "Multa FGTS",
  };
  return (
    <div>
      <div className="text-[11px] font-semibold text-gold-700 uppercase mb-2">
        Verbas rescisórias — minuta, revisão obrigatória
      </div>
      <div className="space-y-1 mb-3">
        {Object.entries(verbas).map(([k, v]) => (
          <div key={k} className="flex justify-between text-xs">
            <span className="text-slate-600">{labels[k] || rotulo(k)}</span>
            <span className="font-medium text-navy">{fmtMoney(v)}</span>
          </div>
        ))}
        <div className="flex justify-between text-sm font-bold text-navy border-t border-gold-300 pt-1 mt-1">
          <span>Total bruto estimado</span>
          <span>{fmtMoney(total)}</span>
        </div>
      </div>
      <div className="text-[10px] text-slate-400 space-y-0.5">
        <div>
          Tempo de contrato: {data.dados_contrato?.tempo_contrato_anos} anos
        </div>
        <div>
          Aviso prévio: {data.dados_contrato?.dias_aviso_previo} dias (Lei
          12.506/11)
        </div>
      </div>
      {data.aviso && (
        <div className="text-[11px] text-slate-500 italic mt-2 pt-2 border-t border-gold-200">
          {data.aviso}
        </div>
      )}
    </div>
  );
}

function ResultadoView({ data }: { data: any }) {
  if (data === null || data === undefined) return null;
  if (Array.isArray(data)) {
    return (
      <ul className="space-y-1">
        {data.map((item, i) => (
          <li key={i} className="text-xs text-navy">
            {typeof item === "object" ? (
              <ResultadoView data={item} />
            ) : (
              String(item)
            )}
          </li>
        ))}
      </ul>
    );
  }
  if (typeof data === "object") {
    return (
      <div className="space-y-1">
        {Object.entries(data).map(([k, v]) => {
          if (k === "homologada" || k === "aviso_homologacao") return null;
          if (METADADOS_REGRA.includes(k)) return null;
          if (v === null || v === undefined) return null;
          if (k === "aviso") {
            return (
              <div
                key={k}
                className="text-[11px] text-slate-500 italic mt-2 pt-2 border-t border-gold-200"
              >
                {String(v)}
              </div>
            );
          }
          const label = rotulo(k);
          if (typeof v === "object") {
            return (
              <div key={k} className="mt-1">
                <div className="text-xs font-semibold text-navy">{label}:</div>
                <div className="pl-3">
                  <ResultadoView data={v} />
                </div>
              </div>
            );
          }
          return (
            <div key={k} className="flex justify-between gap-2 text-xs">
              <span className="text-slate-500">{label}</span>
              <span className="font-medium text-navy text-right">
                {typeof v === "boolean" ? (v ? "✓ Sim" : "✗ Não") : String(v)}
              </span>
            </div>
          );
        })}
      </div>
    );
  }
  return <span className="text-xs">{String(data)}</span>;
}

export default function RamoFerramenta({ f }: { f: FerramentaConfig }) {
  const [vals, setVals] = useState<Record<string, any>>(() => {
    const init: Record<string, any> = {};
    f.campos.forEach((c) => {
      if (c.default !== undefined) init[c.nome] = c.default;
    });
    return init;
  });
  const [res, setRes] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [gerandoDoc, setGerandoDoc] = useState(false);
  const [docMsg, setDocMsg] = useState<string | null>(null);
  const [docLink, setDocLink] = useState<string | null>(null);
  const casoAtivo = useCaseContext((state) => state.caso);

  const naoHomologada = f.homologada === false;
  const bloqueadaParaDocumento = naoHomologada || res?.homologada === false;
  const motivoBloqueio = `Bloqueado: ${AVISO_FERRAMENTA_NAO_HOMOLOGADA}`;
  const visiveis = camposVisiveis(f.campos, vals);

  useEffect(() => {
    const obsoletas = chavesObsoletas(f.campos, vals);
    if (obsoletas.length === 0) return;
    setVals((atuais) => {
      const copia = { ...atuais };
      obsoletas.forEach((nome) => delete copia[nome]);
      return copia;
    });
  }, [f.campos, vals]);

  const calcular = async () => {
    setLoading(true);
    setErro(null);
    setRes(null);
    try {
      const r = await api.get(f.endpoint, {
        params: paramsVisiveis(f.campos, vals),
      });
      setRes(r.data);
    } catch (e: any) {
      setErro(mensagemErroFerramenta(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (f.autoLoad) void calcular();
    // `f.id` identifica a ferramenta; recalcular por edição dos campos geraria
    // requisições automáticas indevidas.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [f.id]);

  const gerarDemonstrativo = async () => {
    if (!res) return;
    if (bloqueadaParaDocumento) {
      setDocMsg(motivoBloqueio);
      return;
    }
    setGerandoDoc(true);
    setDocMsg(null);
    setDocLink(null);
    const proveniencia = provenienciaDoResultado(res);
    if (!proveniencia) {
      setDocMsg(
        "Não foi possível salvar o demonstrativo: a resposta não trouxe fontes, vigência e versão da regra necessárias para a proveniência do cálculo.",
      );
      setGerandoDoc(false);
      return;
    }
    try {
      await api.post("/pecas/demonstrativo", {
        titulo: f.titulo,
        base_legal: f.baseLegal,
        linhas: linhasDoResultado(res),
        rodape: rodapeDoResultado(res) || undefined,
        case_id: casoAtivo?.id || undefined,
        ferramenta: f.endpoint,
        fontes: proveniencia.fontes,
        vigencia_regra: proveniencia.vigencia_regra,
        versao_regra: proveniencia.versao_regra,
      });
      setDocMsg(
        casoAtivo
          ? `✓ Salvo em Peças > Rascunhos, vinculado ao caso "${casoAtivo.titulo}".`
          : "✓ Salvo em Peças > Rascunhos (sem vínculo a caso).",
      );
      setDocLink(casoAtivo ? `/pecas?caso=${casoAtivo.id}` : "/pecas");
    } catch (e: any) {
      setDocMsg(
        mensagemErroFerramenta(e, "Falha ao salvar o demonstrativo em Peças."),
      );
    } finally {
      setGerandoDoc(false);
    }
  };

  const IconeCalc = f.id === "taxas-bacen" ? TrendingUp : Calculator;

  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-1">
        <IconeCalc size={15} className="text-gold-600" />
        <h3 className="font-serif font-semibold text-navy text-sm">
          {f.titulo}
        </h3>
        {naoHomologada && (
          <span
            className="text-[10px] font-semibold text-warn-800 bg-warn-100 border border-warn-300 px-1.5 py-0.5 rounded-full whitespace-nowrap"
            title={motivoBloqueio}
          >
            ⚠️ Não homologada
          </span>
        )}
        {f.autoLoad && res && (
          <span className="ml-auto text-[10px] text-green-600 font-medium bg-green-50 px-1.5 py-0.5 rounded">
            ● ao vivo
          </span>
        )}
      </div>

      <p className="text-xs text-slate-500 mb-3">
        {f.descricao} · <span className="text-gold-700">{f.baseLegal}</span>
        {naoHomologada && (
          <span className="inline-block ml-1 px-1.5 py-0.5 rounded bg-warn-50 text-warn-700 text-[10px] font-medium align-middle">
            ⚠ regra em revisão — não homologada
          </span>
        )}
      </p>

      {naoHomologada && (
        <div className="mb-3 p-2 rounded-lg bg-warn-50 border border-warn-200 text-xs text-warn-800">
          ⚠️ {AVISO_FERRAMENTA_NAO_HOMOLOGADA}
        </div>
      )}

      {visiveis.length > 0 && (
        <div className="grid grid-cols-2 gap-2">
          {visiveis.map((c) => (
            <div
              key={c.nome}
              className={c.tipo === "select" ? "col-span-2 sm:col-span-1" : ""}
            >
              <label className="label text-xs">{c.label}</label>
              {c.tipo === "select" ? (
                <select
                  className="input text-sm"
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
                  className="input text-sm"
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

      {(!f.autoLoad || visiveis.length > 0) && (
        <button
          className="btn-gold text-sm mt-3"
          disabled={loading}
          onClick={calcular}
        >
          {loading
            ? "Calculando..."
            : f.campos.length === 0
              ? "Atualizar"
              : "Calcular"}
        </button>
      )}

      {loading && f.autoLoad && !res && (
        <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
          <Spinner /> Consultando fonte…
        </div>
      )}

      {erro && (
        <div className="mt-3 p-2 rounded bg-danger-50 text-danger-700 text-xs">
          {erro}
        </div>
      )}

      {res && (
        <div className="mt-3 p-3 rounded-lg bg-gold-50 border border-gold-200">
          {!f.autoLoad && (
            <div className="text-[11px] font-semibold text-gold-700 uppercase mb-2">
              Resultado — minuta, revisão obrigatória
            </div>
          )}
          {f.id === "taxas-bacen" && res.taxas ? (
            <TaxasBacenView taxas={res.taxas} aviso={res.aviso} />
          ) : f.id === "verbas-rescisorias" && res.verbas ? (
            <VerbaRescisView data={res} />
          ) : (
            <ResultadoView data={res} />
          )}
          <RodapeRegra data={res} />
          {res.homologada === false && (
            <div className="mt-2 p-2 rounded bg-warn-50 border border-warn-200 text-xs text-warn-800">
              ⚠️ {res.aviso_homologacao || AVISO_FERRAMENTA_NAO_HOMOLOGADA}
            </div>
          )}
          {!f.autoLoad && (
            <div className="mt-3 pt-2 border-t border-gold-200 flex flex-wrap items-center gap-2">
              <button
                className="btn-ghost text-xs disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={gerandoDoc || bloqueadaParaDocumento}
                title={bloqueadaParaDocumento ? motivoBloqueio : undefined}
                onClick={gerarDemonstrativo}
              >
                {gerandoDoc ? "Gerando..." : "📄 Gerar demonstrativo"}
              </button>
              {bloqueadaParaDocumento && (
                <span className="text-[11px] text-warn-700">
                  Demonstrativo e minuta bloqueados — ferramenta em revisão
                  jurídica.
                </span>
              )}
              {docMsg && (
                <span
                  className={`text-xs ${bloqueadaParaDocumento ? "text-warn-700" : "text-green-700"}`}
                >
                  {docMsg}{" "}
                  {docLink && (
                    <Link
                      to={docLink}
                      className="font-medium underline underline-offset-2 hover:text-green-800"
                    >
                      Abrir Peças
                    </Link>
                  )}
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
