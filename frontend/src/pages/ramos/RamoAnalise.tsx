import { useEffect, useRef, useState } from "react";
import Markdown from "../../components/Markdown";
import api from "../../lib/api";
import { mensagemErroIA } from "../../lib/iaErro";
import type { Case } from "../../types";

const ANALISE_TITULO: Record<string, string> = {
  bancario: "🏦 Análise de Contrato Bancário",
  consumidor: "🛒 Análise de Contrato/Documento (Consumidor)",
  trabalhista: "🦺 Análise de Documento Trabalhista",
  empresarial: "🏢 Análise de Contrato Empresarial",
  tributario: "📊 Análise de Auto/Documento Tributário",
  ambiental: "🌿 Análise de Auto Ambiental",
  digital_lgpd: "💻 Análise de Contrato Digital/LGPD",
};

const ANALISE_PLACEHOLDER: Record<string, string> = {
  bancario: "…ou cole aqui o texto do contrato bancário",
  consumidor:
    "…ou cole aqui o texto do contrato ou documento de consumo (fatura, cobrança, termo de adesão)",
  trabalhista:
    "…ou cole aqui o texto do documento trabalhista (contrato, rescisão, holerite)",
  empresarial: "…ou cole aqui o texto do contrato empresarial",
  tributario:
    "…ou cole aqui o texto do auto de infração ou documento tributário",
  ambiental: "…ou cole aqui o texto do auto de infração ambiental",
  digital_lgpd:
    "…ou cole aqui o texto do contrato digital ou documento de dados (LGPD)",
};

const TIPOS_PECA_MINUTA = [
  "petição inicial",
  "contestação",
  "réplica",
  "recurso",
  "defesa administrativa",
  "notificação extrajudicial",
  "parecer",
];

export function ComparadorBacen() {
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
  const acima = res && !Number.isNaN(t) && media != null ? t > media : null;
  const diff =
    res && !Number.isNaN(t) && media != null
      ? ((t - media) / media) * 100
      : null;

  return (
    <div className="card p-4 border-l-4 border-primary-500">
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
      {erro && <p className="text-xs text-danger-600 mt-2">{erro}</p>}
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
              className={`rounded-lg p-3 text-sm font-medium ${
                acima
                  ? "bg-danger-50 text-danger-700"
                  : "bg-success-50 text-success-700"
              }`}
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
          <p className="text-[11px] text-warn-700">
            ⚠ Indicador de apoio. A média do BACEN não define abusividade
            automaticamente — análise do advogado é necessária.
          </p>
        </div>
      )}
    </div>
  );
}

export function AnaliseDocumentoArea({
  area,
  casos,
}: {
  area: string;
  casos: Case[];
}) {
  const [casoSel, setCasoSel] = useState("");
  const [tipoPeca, setTipoPeca] = useState("");
  const [acao, setAcao] = useState("");
  const [minuta, setMinuta] = useState("");
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
      setErro(mensagemErroIA(e, "Não foi possível analisar o documento."));
    } finally {
      setLoading(false);
    }
  };

  const riscoCor = (risco: string) =>
    risco === "alto"
      ? "bg-danger-100 text-danger-700"
      : risco === "medio"
        ? "bg-warn-100 text-warn-700"
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
    if (!tipoPeca) {
      setAcao("Selecione o tipo de peça antes de gerar a minuta.");
      return;
    }
    setAcao("Gerando minuta…");
    setMinuta("");
    try {
      const { data } = await api.post("/ai/gerar-minuta", {
        tema: "Ação revisional/defesa com base na análise do documento",
        tipo_peca: tipoPeca,
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
      setAcao(mensagemErroIA(e, "Não foi possível gerar a minuta."));
    }
  };

  return (
    <div
      id="analise-documento"
      className="card p-4 border-l-4 border-success-500 scroll-mt-4"
    >
      <h2 className="font-serif font-semibold text-navy mb-1 flex items-center gap-2">
        {ANALISE_TITULO[area] || "📄 Análise de Documento"}
      </h2>
      <p className="text-xs text-slate-500 mb-3">
        Lê o documento (PDF ou texto) e aponta riscos e cláusulas questionáveis
        conforme a área — como apoio, sempre com revisão do advogado.
      </p>
      <div className="flex flex-wrap gap-2 mb-2">
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void analisar(f);
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
          onClick={() => void analisar()}
          disabled={loading}
          className="btn-secondary text-sm"
        >
          {loading ? "Analisando…" : "Analisar texto colado"}
        </button>
      </div>
      <textarea
        className="input w-full text-xs font-mono"
        rows={4}
        placeholder={
          ANALISE_PLACEHOLDER[area] || "…ou cole aqui o texto do documento"
        }
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
      />
      {erro && <p className="text-xs text-danger-600 mt-2">{erro}</p>}
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
            <p className="text-xs text-success-700 bg-success-50 rounded-lg p-2">
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
            <select
              className="input text-xs min-w-[150px]"
              value={tipoPeca}
              onChange={(e) => setTipoPeca(e.target.value)}
              title="Tipo de peça (escolha do advogado — obrigatório)"
            >
              <option value="">Tipo de peça…</option>
              {TIPOS_PECA_MINUTA.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <button
              onClick={gerarMinuta}
              disabled={!tipoPeca}
              className="btn-gold text-xs disabled:opacity-50"
            >
              ✍️ Gerar minuta
            </button>
          </div>
          {acao && <p className="text-xs text-slate-500">{acao}</p>}
          {minuta && (
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs font-semibold text-slate-500 uppercase mb-1">
                Minuta (rascunho — revisão obrigatória)
              </p>
              <Markdown
                source={minuta}
                className="text-xs text-slate-700 leading-relaxed max-h-72 overflow-y-auto"
              />
            </div>
          )}
          {res._aviso && (
            <p className="text-[11px] text-warn-700 border-t border-warn-100 pt-2">
              ⚠ {res._aviso}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
