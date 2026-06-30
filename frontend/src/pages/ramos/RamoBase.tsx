// ── src/pages/ramos/RamoBase.tsx ─────────────────────────────────────────────
// Página genérica de ramo especializado. Renderiza qualquer um dos 6 ramos a
// partir de ramosConfig.ts. Três blocos: ferramentas (calculadoras com resultado
// ao vivo), formulário de criação e listagem dos casos do ramo.
//
// Todas as calculadoras devolvem MINUTAS (HITL) — o resultado exibe o aviso.
import { useEffect, useMemo, useState, useRef } from "react";
import Markdown from "../../components/Markdown";
import { useParams, Link } from "react-router-dom";
import {
  Plus,
  Calculator,
  Building2,
  Scale,
  Lock,
  HardHat,
  Landmark,
  Banknote,
  Folder,
  Receipt,
  Leaf,
  TrendingUp,
  Users,
  Car,
} from "lucide-react";
import api from "../../lib/api";
import type { Case } from "../../types";
import {
  PageHeader,
  StatusBadge,
  Modal,
  Empty,
  Spinner,
} from "../../components/UI";
import { RAMOS, type RamoConfig, type FerramentaConfig } from "./ramosConfig";
import GuiaBancario from "../../components/GuiaBancario";
import AnaliseExtratos from "../../components/AnaliseExtratos";
import GuiaTransito from "../../components/GuiaTransito";
import GuiaTrabalhista from "../../components/GuiaTrabalhista";
import GuiaTributario from "../../components/GuiaTributario";
import GuiaPrevidenciario from "../../components/GuiaPrevidenciario";
import GuiaAmbiental from "../../components/GuiaAmbiental";
import GuiaCivil from "../../components/GuiaCivil";
import GuiaPenal from "../../components/GuiaPenal";
import GuiaConsumidor from "../../components/GuiaConsumidor";
import GuiaImobiliario from "../../components/GuiaImobiliario";
import GuiaFamilia from "../../components/GuiaFamilia";
import GuiaAdministrativo from "../../components/GuiaAdministrativo";
import GuiaLicitacoes from "../../components/GuiaLicitacoes";
import { RamoStats } from "../../components/Dashboards";

// Mapa de ícones por nome (evita importar a lib inteira)
const ICONES: Record<string, any> = {
  Building2,
  Scale,
  Lock,
  HardHat,
  Landmark,
  Banknote,
  Folder,
  Receipt,
  Leaf,
  Users,
  Car,
};

// Tailwind purga classes dinâmicas; mapa estático garante que as cores existam no build
const COR_BORDA: Record<string, string> = {
  amber: "border-amber-500",
  blue: "border-blue-500",
  red: "border-red-500",
  green: "border-green-500",
  slate: "border-slate-500",
  yellow: "border-yellow-500",
};

function rotulo(v: string) {
  return v.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatBRL(v: number) {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

// ── Bloco de uma ferramenta/calculadora ──────────────────────────────────────
function Ferramenta({ f }: { f: FerramentaConfig }) {
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

  // Converte o resultado da calculadora em um Demonstrativo (LegalDoc rascunho).
  const gerarDemonstrativo = async () => {
    if (!res) return;
    setGerandoDoc(true);
    setDocMsg(null);
    const RODAPE = ["aviso", "base", "observacao", "descricao"];
    const linhas = Object.entries(res)
      .filter(([k, v]) => !RODAPE.includes(k) && v !== null && typeof v !== "object")
      .map(([k, v]) => ({ label: k.replace(/_/g, " "), valor: String(v) }));
    const rodape = [res.observacao, res.descricao].filter(Boolean).join("\n");
    try {
      await api.post("/pecas/demonstrativo", {
        titulo: f.titulo,
        base_legal: f.baseLegal,
        linhas,
        rodape: rodape || undefined,
      });
      setDocMsg("✓ Salvo em Peças (rascunho).");
    } catch (e: any) {
      setDocMsg(e.response?.data?.detail || "Falha ao gerar");
    } finally {
      setGerandoDoc(false);
    }
  };

  const calcular = async () => {
    setLoading(true);
    setErro(null);
    setRes(null);
    try {
      const r = await api.get(f.endpoint, { params: vals });
      setRes(r.data);
    } catch (e: any) {
      setErro(e.response?.data?.detail || "Falha no cálculo");
    } finally {
      setLoading(false);
    }
  };

  // Auto-load para ferramentas sem campos de entrada (ex: taxas-bacen)
  useEffect(() => {
    if (f.autoLoad) calcular();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [f.id]);

  // Ícone especial para taxas ao vivo
  const IconeCalc = f.id === "taxas-bacen" ? TrendingUp : Calculator;

  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-1">
        <IconeCalc size={15} className="text-gold-600" />
        <h3 className="font-serif font-semibold text-navy text-sm">
          {f.titulo}
        </h3>
        {f.autoLoad && res && (
          <span className="ml-auto text-[10px] text-green-600 font-medium bg-green-50 px-1.5 py-0.5 rounded">
            ● ao vivo
          </span>
        )}
      </div>
      <p className="text-xs text-slate-500 mb-3">
        {f.descricao} · <span className="text-gold-700">{f.baseLegal}</span>
      </p>

      {f.campos.length > 0 && (
        <div className="grid grid-cols-2 gap-2">
          {f.campos.map((c) => (
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

      {/* Só mostra botão "Calcular" se não for autoLoad OU se houver campos */}
      {(!f.autoLoad || f.campos.length > 0) && (
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
          <Spinner /> Consultando BCB...
        </div>
      )}

      {erro && (
        <div className="mt-3 p-2 rounded bg-red-50 text-red-700 text-xs">
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
          {/* Render especial para taxas BACEN */}
          {f.id === "taxas-bacen" && res.taxas ? (
            <TaxasBacenView taxas={res.taxas} aviso={res.aviso} />
          ) : f.id === "verbas-rescisorias" && res.verbas ? (
            <VerbaRescisView data={res} />
          ) : (
            <ResultadoView data={res} />
          )}
          {!f.autoLoad && (
            <div className="mt-3 pt-2 border-t border-gold-200 flex flex-wrap items-center gap-2">
              <button
                className="btn-ghost text-xs"
                disabled={gerandoDoc}
                onClick={gerarDemonstrativo}
              >
                {gerandoDoc ? "Gerando..." : "📄 Gerar demonstrativo"}
              </button>
              {docMsg && (
                <span className="text-xs text-green-700">{docMsg}</span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Render especial: Taxas BACEN ──────────────────────────────────────────────
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
            {item.valor != null ? (
              <>
                <div className="text-lg font-bold text-navy">
                  {Number(item.valor).toFixed(4)}%
                </div>
                <div className="text-[10px] text-slate-400">{item.data}</div>
              </>
            ) : (
              <div className="text-xs text-red-500">indisponível</div>
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

// ── Render especial: Verbas Rescisórias ───────────────────────────────────────
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
            <span className="font-medium text-navy">{formatBRL(v)}</span>
          </div>
        ))}
        <div className="flex justify-between text-sm font-bold text-navy border-t border-gold-300 pt-1 mt-1">
          <span>Total bruto estimado</span>
          <span>{formatBRL(total)}</span>
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

// Renderiza o JSON de resultado de forma legível (chave: valor, listas, aninhado).
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
          if (typeof v === "object" && v !== null) {
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

// ── Página principal ──────────────────────────────────────────────────────────
const _ANALISE_TITULO: Record<string, string> = {
  bancario: "🏦 Análise de Contrato Bancário",
  consumidor: "🛒 Análise de Contrato/Documento (Consumidor)",
  trabalhista: "🦺 Análise de Documento Trabalhista",
  empresarial: "🏢 Análise de Contrato Empresarial",
  tributario: "📊 Análise de Auto/Documento Tributário",
  ambiental: "🌿 Análise de Auto Ambiental",
  digital_lgpd: "💻 Análise de Contrato Digital/LGPD",
};
function ComparadorBacen() {
  const [mods, setMods] = useState<any[]>([]);
  const [periodo, setPeriodo] = useState("");
  const [idx, setIdx] = useState("");
  const [taxa, setTaxa] = useState("");
  const [res, setRes] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    api
      .get("/analise-bancaria/modalidades")
      .then((r) => {
        setMods(r.data?.modalidades ?? []);
        setPeriodo(r.data?.periodo ?? "");
      })
      .catch(() => {});
  }, []);

  const comparar = async () => {
    const sel = mods[Number(idx)];
    if (!sel) {
      setErro("Selecione a modalidade.");
      return;
    }
    setLoading(true);
    setErro("");
    setRes(null);
    try {
      const r = await api.get("/analise-bancaria/taxa-media", {
        params: { modalidade: sel.modalidade, segmento: sel.segmento, periodo },
      });
      setRes(r.data);
    } catch (e: any) {
      setErro(e.response?.data?.detail || "Falha ao consultar o BACEN.");
    } finally {
      setLoading(false);
    }
  };

  const t = parseFloat((taxa || "").replace(",", "."));
  const media = res?.ao_mes?.media;
  const acima = res && !isNaN(t) && media != null ? t > media : null;
  const diff =
    res && !isNaN(t) && media != null ? ((t - media) / media) * 100 : null;

  return (
    <div className="card p-4 mb-4 border-l-4 border-blue-500">
      <h2 className="font-serif font-semibold text-navy mb-1">
        📈 Comparador de Juros (BACEN)
      </h2>
      <p className="text-xs text-slate-500 mb-3">
        Compara a taxa do contrato com a média de mercado do Banco Central, por
        modalidade.
      </p>
      <div className="grid sm:grid-cols-3 gap-2 items-end">
        <div className="sm:col-span-2">
          <label className="label">Modalidade</label>
          <select
            className="input w-full text-sm"
            value={idx}
            onChange={(e) => setIdx(e.target.value)}
          >
            <option value="">Selecione…</option>
            {mods.map((m, i) => (
              <option key={i} value={i}>
                {(m.segmento || "").includes("FÍSICA") ? "PF" : "PJ"} ·{" "}
                {m.modalidade}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Taxa do contrato (% a.m.)</label>
          <input
            className="input w-full"
            placeholder="ex: 3,5"
            value={taxa}
            onChange={(e) => setTaxa(e.target.value)}
          />
        </div>
      </div>
      <button
        onClick={comparar}
        disabled={loading}
        className="btn-gold text-sm mt-2"
      >
        {loading ? "Consultando BACEN…" : "Comparar"}
      </button>
      {erro && <p className="text-xs text-red-600 mt-2">{erro}</p>}
      {res && (
        <div className="mt-3 space-y-2 text-sm">
          <p className="text-xs text-slate-500">
            Mercado em {res.periodo} · {res.instituicoes} instituições · fonte:
            BACEN
          </p>
          <div className="grid grid-cols-3 gap-2 text-center">
            {[
              ["Mínima", res.ao_mes?.min],
              ["Média", res.ao_mes?.media],
              ["Máxima", res.ao_mes?.max],
            ].map(([l, v]: any) => (
              <div key={l} className="bg-slate-50 rounded-lg p-2">
                <p className="text-[11px] text-slate-500">{l} (% a.m.)</p>
                <p className="font-bold text-slate-800">{v}%</p>
              </div>
            ))}
          </div>
          {acima !== null && (
            <div
              className={`rounded-lg p-3 text-sm font-medium ${acima ? "bg-red-50 text-red-700" : "bg-emerald-50 text-emerald-700"}`}
            >
              Sua taxa de <b>{t.toFixed(2)}% a.m.</b> está{" "}
              <b>
                {Math.abs(diff!).toFixed(0)}% {acima ? "ACIMA" : "abaixo"}
              </b>{" "}
              da média de mercado.
              {acima &&
                " — possível indício de abusividade (verificar caso a caso)."}
            </div>
          )}
          <p className="text-[11px] text-amber-700">
            ⚠ Indicador de apoio. A média do BACEN não define abusividade
            automaticamente — análise do advogado é necessária.
          </p>
        </div>
      )}
    </div>
  );
}

function AnaliseBancaria({ area, casos }: { area: string; casos: Case[] }) {
  const [casoSel, setCasoSel] = useState("");
  const [acao, setAcao] = useState("");
  const [minuta, setMinuta] = useState<string>("");
  const [texto, setTexto] = useState("");
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState<any>(null);
  const [erro, setErro] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const analisar = async (file?: File) => {
    setLoading(true);
    setErro("");
    setRes(null);
    try {
      const fd = new FormData();
      fd.append("area", area);
      if (file) fd.append("file", file);
      else if (texto.trim().length >= 120) fd.append("texto", texto);
      else {
        setErro("Cole o texto (mín. 120 caracteres) ou envie um PDF.");
        setLoading(false);
        return;
      }
      const r = await api.post("/analise-bancaria/contrato", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setRes(r.data);
    } catch (e: any) {
      setErro(
        e.response?.data?.detail ||
          "Falha na análise (a IA pode estar indisponível).",
      );
    } finally {
      setLoading(false);
    }
  };

  const riscoCor = (r: string) =>
    r === "alto"
      ? "bg-red-100 text-red-700"
      : r === "medio"
        ? "bg-amber-100 text-amber-700"
        : "bg-slate-100 text-slate-600";

  const resumoTexto = () => {
    if (!res) return "";
    const cl = (res.clausulas_questionaveis ?? [])
      .map((x: any) => `- [${x.risco}] ${x.clausula}`)
      .join("\n");
    const tf = (res.tarifas_encargos ?? [])
      .map((x: any) => `- [${x.risco}] ${x.item}: ${x.motivo}`)
      .join("\n");
    return `ANÁLISE (${area}) — ${res.resumo || ""}\n\nTarifas/encargos:\n${tf}\n\nCláusulas questionáveis:\n${cl}\n\n${res.proxima_acao || ""}`;
  };
  const salvarNoCaso = async () => {
    if (!casoSel) {
      setAcao("Selecione um caso.");
      return;
    }
    try {
      await api.post(`/cases/${casoSel}/movimentos`, {
        tipo: "nota",
        descricao: resumoTexto().slice(0, 4000),
      });
      setAcao("✓ Análise salva no histórico do caso.");
    } catch {
      setAcao("Falha ao salvar.");
    }
  };
  const gerarMinuta = async () => {
    setAcao("Gerando minuta…");
    setMinuta("");
    try {
      const { data } = await api.post("/ai/gerar-minuta", {
        tema: "Ação revisional/defesa com base na análise do documento",
        tipo_peca: "petição inicial",
        area,
        fatos: resumoTexto().slice(0, 3000),
      });
      setMinuta(
        data.minuta ||
          data.texto ||
          data.resposta ||
          JSON.stringify(data).slice(0, 2000),
      );
      setAcao("");
    } catch (e: any) {
      setAcao(e.response?.data?.detail || "Falha ao gerar minuta.");
    }
  };

  return (
    <div className="card p-4 mb-4 border-l-4 border-emerald-500">
      <h2 className="font-serif font-semibold text-navy mb-1 flex items-center gap-2">
        {_ANALISE_TITULO[area] || "📄 Análise de Documento"}
      </h2>
      <p className="text-xs text-slate-500 mb-3">
        Lê o contrato (PDF ou texto) e aponta juros, capitalização, tarifas e
        cláusulas questionáveis — como apoio, sempre com revisão do advogado.
      </p>
      <div className="flex flex-wrap gap-2 mb-2">
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) analisar(f);
          }}
        />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={loading}
          className="btn-gold text-sm"
        >
          📄 Enviar PDF
        </button>
        <button
          onClick={() => analisar()}
          disabled={loading}
          className="btn-secondary text-sm"
        >
          {loading ? "Analisando…" : "Analisar texto colado"}
        </button>
      </div>
      <textarea
        className="input w-full text-xs font-mono"
        rows={4}
        placeholder="…ou cole aqui o texto do contrato bancário"
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
      />
      {erro && <p className="text-xs text-red-600 mt-2">{erro}</p>}
      {res && (
        <div className="mt-4 space-y-3 text-sm">
          {res.resumo && <p className="text-slate-700">{res.resumo}</p>}
          {res.juros && (
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs font-semibold text-slate-500 uppercase">
                Juros
              </p>
              <p className="text-slate-700">
                Taxa: <b>{res.juros.taxa_identificada || "não identificada"}</b>{" "}
                · Capitalização: {res.juros.capitalizacao}
              </p>
              {res.juros.observacao && (
                <p className="text-xs text-slate-500 mt-1">
                  {res.juros.observacao}
                </p>
              )}
            </div>
          )}
          {(res.tarifas_encargos ?? []).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase mb-1">
                Tarifas / encargos
              </p>
              {res.tarifas_encargos.map((t: any, i: number) => (
                <div
                  key={i}
                  className="flex items-start gap-2 py-1 text-xs border-b border-slate-50"
                >
                  <span
                    className={`px-1.5 py-0.5 rounded-full font-medium ${riscoCor(t.risco)}`}
                  >
                    {t.risco}
                  </span>
                  <span className="text-slate-700">
                    <b>{t.item}</b> — {t.motivo}
                  </span>
                </div>
              ))}
            </div>
          )}
          {(res.clausulas_questionaveis ?? []).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase mb-1">
                Cláusulas questionáveis
              </p>
              {res.clausulas_questionaveis.map((cq: any, i: number) => (
                <div
                  key={i}
                  className="py-1.5 text-xs border-b border-slate-50"
                >
                  <span
                    className={`px-1.5 py-0.5 rounded-full font-medium ${riscoCor(cq.risco)}`}
                  >
                    {cq.risco}
                  </span>
                  <span className="text-slate-700 ml-2">{cq.clausula}</span>
                  {cq.fundamento && (
                    <span className="text-slate-400 block mt-0.5">
                      Fundamento: {cq.fundamento}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
          {(res.pontos_de_atencao ?? []).length > 0 && (
            <ul className="list-disc list-inside text-xs text-slate-600 space-y-0.5">
              {res.pontos_de_atencao.map((p: string, i: number) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          )}
          {res.proxima_acao && (
            <p className="text-xs text-emerald-700 bg-emerald-50 rounded-lg p-2">
              ➡ {res.proxima_acao}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-100">
            <select
              className="input text-xs flex-1 min-w-[160px]"
              value={casoSel}
              onChange={(e) => setCasoSel(e.target.value)}
            >
              <option value="">Vincular a um caso…</option>
              {casos.map((c) => (
                <option key={c.id} value={c.id}>
                  {(c as any).numero_interno} — {c.titulo}
                </option>
              ))}
            </select>
            <button onClick={salvarNoCaso} className="btn-secondary text-xs">
              💾 Salvar no caso
            </button>
            <button onClick={gerarMinuta} className="btn-gold text-xs">
              ✍️ Gerar minuta
            </button>
          </div>
          {acao && <p className="text-xs text-slate-500">{acao}</p>}
          {minuta && (
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs font-semibold text-slate-500 uppercase mb-1">
                Minuta (rascunho — revisão obrigatória)
              </p>
              <Markdown source={minuta} className="text-xs text-slate-700 leading-relaxed max-h-72 overflow-y-auto" />
            </div>
          )}
          {res._aviso && (
            <p className="text-[11px] text-amber-700 border-t border-amber-100 pt-2">
              ⚠ {res._aviso}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default function RamoBase() {
  const { slug } = useParams<{ slug: string }>();
  const cfg: RamoConfig | undefined = slug ? RAMOS[slug] : undefined;

  const [lista, setLista] = useState<any[] | null>(null);
  const [casos, setCasos] = useState<Case[]>([]);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState<any>({});
  const [salvando, setSalvando] = useState(false);

  const Icone = useMemo(() => {
    if (!cfg) return Folder;
    return ICONES[cfg.icone] || Folder;
  }, [cfg]);

  const load = () => {
    if (!cfg) return;
    if (cfg.externo) {
      setLista([]);
      return;
    }
    api
      .get(cfg.endpoint)
      .then((r) => setLista(r.data.data || []))
      .catch(() => setLista([]));
  };

  useEffect(() => {
    if (!cfg) return;
    setLista(null);
    setForm({});
    load();
    api
      .get("/cases/", { params: { area: cfg.areaCaso, page_size: 100 } })
      .then((r) => setCasos(r.data.data))
      .catch(() => setCasos([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug]);

  if (!cfg) return <Empty message="Ramo não encontrado" />;

  const salvar = async () => {
    if (!form.case_id) {
      alert("Selecione o caso vinculado");
      return;
    }
    const obrig = cfg.campos.find((c) => c.obrigatorio && !form[c.nome]);
    if (obrig) {
      alert(`Campo obrigatório: ${obrig.label}`);
      return;
    }
    setSalvando(true);
    try {
      await api.post(cfg.endpoint, form);
      setModal(false);
      setForm({});
      load();
    } catch (e: any) {
      alert(e.response?.data?.detail || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Ramos especializados"
        title={cfg.titulo}
        subtitle={cfg.subtitulo}
        actions={
          cfg.externo ? (
            <Link to={`/casos`} className="btn-gold flex items-center gap-1">
              <Plus size={16} /> Novo caso
            </Link>
          ) : (
            <button className="btn-gold" onClick={() => setModal(true)}>
              <Plus size={16} /> Novo caso
            </button>
          )
        }
      />

      <RamoStats
        casos={casos}
        lista={lista}
        cor={cfg.cor}
        area={cfg.areaCaso}
      />

      {cfg.comparadorBacen && <ComparadorBacen />}
      {cfg.analiseDocumento && (
        <AnaliseBancaria area={cfg.areaCaso} casos={casos} />
      )}
      {cfg.guiaBancario && <GuiaBancario />}
      {cfg.analiseExtratos && <AnaliseExtratos />}
      {cfg.guiaTransito && <GuiaTransito />}
      {cfg.guiaTrabalhista && <GuiaTrabalhista />}
      {cfg.guiaTributario && <GuiaTributario />}
      {cfg.guiaPrevidenciario && <GuiaPrevidenciario />}
      {cfg.guiaAmbiental && <GuiaAmbiental />}
      {cfg.guiaCivil && <GuiaCivil />}
      {cfg.guiaPenal && <GuiaPenal />}
      {cfg.guiaConsumidor && <GuiaConsumidor />}
      {cfg.guiaImobiliario && <GuiaImobiliario />}
      {cfg.guiaFamilia && <GuiaFamilia />}
      {cfg.guiaAdministrativo && <GuiaAdministrativo />}
      {cfg.guiaLicitacoes && <GuiaLicitacoes />}

      {/* Áreas de atuação (subáreas) */}
      {cfg.subareas && cfg.subareas.length > 0 && (
        <div className="card p-4 mb-4">
          <h2 className="font-serif font-semibold text-navy mb-3 flex items-center gap-2">
            <Icone size={16} className="text-gold-600" /> Áreas de atuação
          </h2>
          <div className="flex flex-wrap gap-2">
            {cfg.subareas.map((sa) => (
              <span
                key={sa}
                className="text-xs px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 border border-slate-200"
              >
                {sa}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Ferramentas públicas externas */}
      {cfg.ferramentasExternas && cfg.ferramentasExternas.length > 0 && (
        <div className="card p-4 mb-4">
          <h2 className="font-serif font-semibold text-navy mb-3">
            Ferramentas públicas
          </h2>
          <div className="grid sm:grid-cols-2 gap-2">
            {cfg.ferramentasExternas.map((fe) => (
              <a
                key={fe.url}
                href={fe.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-start gap-2 p-2.5 rounded-lg border border-slate-200 hover:border-gold-400 hover:bg-gold-50/30 transition-colors group"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-navy group-hover:text-gold-700">
                    {fe.nome} ↗
                  </p>
                  <p className="text-xs text-slate-400">{fe.descricao}</p>
                </div>
              </a>
            ))}
          </div>
        </div>
      )}

      {/* Ferramentas / calculadoras */}
      {cfg.ferramentas.length > 0 && (
        <div className="grid md:grid-cols-2 gap-3 mb-6">
          {cfg.ferramentas.map((f) => (
            <Ferramenta key={f.id} f={f} />
          ))}
        </div>
      )}

      {/* Listagem */}
      <h2 className="font-serif font-semibold text-navy mb-3 flex items-center gap-2">
        <Icone size={18} className="text-gold-600" /> Casos registrados
      </h2>
      {lista === null ? (
        <Spinner />
      ) : lista.length === 0 ? (
        <Empty message="Nenhum caso especializado registrado neste ramo" />
      ) : (
        <div className="space-y-2">
          {lista.map((item) => (
            <div
              key={item.id}
              className={`card p-4 flex flex-wrap items-center gap-4 border-l-4 ${COR_BORDA[cfg.cor] || "border-slate-500"}`}
            >
              <div className="flex-1 min-w-[200px]">
                <div className="font-medium text-navy">
                  {rotulo(String(item[cfg.campoTitulo] || "—"))}
                </div>
                <div className="text-xs text-slate-400">
                  {item.instituicao_financeira ||
                    item.orgao_autuador ||
                    item.cnpj_empresa ||
                    item.cargo ||
                    item.competencia ||
                    "—"}
                </div>
              </div>
              {item[cfg.campoStatus] && (
                <StatusBadge value={String(item[cfg.campoStatus])} />
              )}
            </div>
          ))}
        </div>
      )}

      {/* Modal de criação */}
      <Modal
        open={modal}
        onClose={() => setModal(false)}
        title={`Novo caso — ${cfg.titulo}`}
        wide
      >
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2">
            <label className="label">Caso vinculado *</label>
            <select
              className="input"
              value={form.case_id || ""}
              onChange={(e) => setForm({ ...form, case_id: e.target.value })}
            >
              <option value="">Selecione o caso...</option>
              {casos.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.numero_interno} — {c.titulo}
                </option>
              ))}
            </select>
            {casos.length === 0 && (
              <p className="text-xs text-amber-600 mt-1">
                Crie antes um caso com área "{cfg.areaCaso}"
              </p>
            )}
          </div>
          {cfg.campos.map((c) => (
            <div key={c.nome} className={c.col === 2 ? "sm:col-span-2" : ""}>
              <label className="label">
                {c.label}
                {c.obrigatorio && " *"}
              </label>
              {c.tipo === "select" ? (
                <select
                  className="input"
                  value={form[c.nome] || ""}
                  onChange={(e) =>
                    setForm({ ...form, [c.nome]: e.target.value })
                  }
                >
                  <option value="">Selecione...</option>
                  {c.opcoes?.map((o) => (
                    <option key={o} value={o}>
                      {rotulo(o)}
                    </option>
                  ))}
                </select>
              ) : c.tipo === "textarea" ? (
                <textarea
                  className="input"
                  rows={3}
                  value={form[c.nome] || ""}
                  placeholder={c.placeholder}
                  onChange={(e) =>
                    setForm({ ...form, [c.nome]: e.target.value })
                  }
                />
              ) : c.tipo === "checkbox" ? (
                <label className="flex items-center gap-2 mt-1 text-sm">
                  <input
                    type="checkbox"
                    checked={!!form[c.nome]}
                    onChange={(e) =>
                      setForm({ ...form, [c.nome]: e.target.checked })
                    }
                  />
                  <span className="text-slate-600">{c.ajuda || "Sim"}</span>
                </label>
              ) : (
                <input
                  className="input"
                  type={c.tipo}
                  step={c.tipo === "number" ? "0.01" : undefined}
                  placeholder={c.placeholder}
                  value={form[c.nome] || ""}
                  onChange={(e) =>
                    setForm({ ...form, [c.nome]: e.target.value })
                  }
                />
              )}
              {c.ajuda && c.tipo !== "checkbox" && (
                <p className="text-xs text-slate-400 mt-1">{c.ajuda}</p>
              )}
            </div>
          ))}
        </div>
        <div className="flex justify-end mt-5">
          <button className="btn-primary" disabled={salvando} onClick={salvar}>
            {salvando ? "Salvando..." : "Registrar caso"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
