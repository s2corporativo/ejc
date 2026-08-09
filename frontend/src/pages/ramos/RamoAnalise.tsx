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

export function modalidadeSelecionada(
  modalidades: any[],
  indice: string,
): any | undefined {
  if (indice === "") return undefined;
  const numero = Number(indice);
  if (!Number.isInteger(numero) || numero < 0) return undefined;
  return modalidades[numero];
}

export function ComparadorBacen() {
  const [modalidades, setModalidades] = useState<any[]>([]);
  const [periodo, setPeriodo] = useState("");
  const [indice, setIndice] = useState("");
  const [taxa, setTaxa] = useState("");
  const [resultado, setResultado] = useState<any>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    api
      .get("/analise-bancaria/modalidades")
      .then((resposta) => {
        setModalidades(resposta.data?.modalidades ?? []);
        setPeriodo(resposta.data?.periodo ?? "");
      })
      .catch(() => {
        setModalidades([]);
        setPeriodo("");
        setErro(
          "Não foi possível carregar as modalidades do BACEN. Tente novamente mais tarde.",
        );
      });
  }, []);

  const alterarModalidade = (novoIndice: string) => {
    setIndice(novoIndice);
    setResultado(null);
    setErro("");
  };

  const comparar = async () => {
    const selecionada = modalidadeSelecionada(modalidades, indice);
    if (!selecionada) {
      setErro("Selecione a modalidade.");
      return;
    }
    setCarregando(true);
    setErro("");
    setResultado(null);
    try {
      const resposta = await api.get("/analise-bancaria/taxa-media", {
        params: {
          modalidade: selecionada.modalidade,
          segmento: selecionada.segmento,
          periodo,
        },
      });
      setResultado(resposta.data);
    } catch (e: any) {
      setErro(e.response?.data?.detail || "Falha ao consultar o BACEN.");
    } finally {
      setCarregando(false);
    }
  };

  const taxaContrato = parseFloat((taxa || "").replace(",", "."));
  const media = resultado?.ao_mes?.media;
  const acima =
    resultado && !Number.isNaN(taxaContrato) && media != null
      ? taxaContrato > media
      : null;
  const diferencaPercentual =
    resultado && !Number.isNaN(taxaContrato) && media != null && media !== 0
      ? ((taxaContrato - media) / media) * 100
      : null;

  return (
    <div className="card p-4 border-l-4 border-primary-500">
      <h2 className="font-serif font-semibold text-navy mb-1">
        📈 Comparador de Juros (BACEN)
      </h2>
      <p className="text-xs text-slate-500 mb-3">
        Compara a taxa do contrato com a média de mercado retornada pela consulta
        ao Banco Central, por modalidade e período.
      </p>
      <div className="grid sm:grid-cols-3 gap-2 items-end">
        <div className="sm:col-span-2">
          <label className="label">Modalidade</label>
          <select
            className="input w-full text-sm"
            value={indice}
            onChange={(e) => alterarModalidade(e.target.value)}
          >
            <option value="">Selecione…</option>
            {modalidades.map((modalidade, i) => (
              <option key={i} value={i}>
                {(modalidade.segmento || "").includes("FÍSICA") ? "PF" : "PJ"} ·{" "}
                {modalidade.modalidade}
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
        disabled={carregando}
        className="btn-gold text-sm mt-2"
      >
        {carregando ? "Consultando BACEN…" : "Comparar"}
      </button>
      {erro && <p className="text-xs text-danger-600 mt-2">{erro}</p>}
      {resultado && (
        <div className="mt-3 space-y-2 text-sm">
          <p className="text-xs text-slate-500">
            Mercado em {resultado.periodo} · {resultado.instituicoes} instituições
            · fonte de dados: BACEN
          </p>
          <div className="grid grid-cols-3 gap-2 text-center">
            {[
              ["Mínima", resultado.ao_mes?.min],
              ["Média", resultado.ao_mes?.media],
              ["Máxima", resultado.ao_mes?.max],
            ].map(([rotuloTaxa, valor]: any) => (
              <div key={rotuloTaxa} className="bg-slate-50 rounded-lg p-2">
                <p className="text-[11px] text-slate-500">
                  {rotuloTaxa} (% a.m.)
                </p>
                <p className="font-bold text-slate-800">{valor}%</p>
              </div>
            ))}
          </div>
          {acima !== null && diferencaPercentual !== null && (
            <div
              className={`rounded-lg p-3 text-sm font-medium ${
                acima
                  ? "bg-danger-50 text-danger-700"
                  : "bg-success-50 text-success-700"
              }`}
            >
              A taxa informada de <b>{taxaContrato.toFixed(2)}% a.m.</b> está{" "}
              <b>
                {Math.abs(diferencaPercentual).toFixed(0)}% {acima ? "ACIMA" : "abaixo"}
              </b>{" "}
              da média retornada para a modalidade e período consultados.
            </div>
          )}
          <p className="text-[11px] text-warn-700">
            ⚠ Comparação estatística de apoio. O resultado não conclui, por si
            só, abusividade, validade contratual ou direito à revisão; a análise
            jurídica e fática pelo advogado permanece obrigatória.
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
  const [casoSelecionado, setCasoSelecionado] = useState("");
  const [tipoPeca, setTipoPeca] = useState("");
  const [acao, setAcao] = useState("");
  const [minuta, setMinuta] = useState("");
  const [texto, setTexto] = useState("");
  const [analisando, setAnalisando] = useState(false);
  const [salvandoCaso, setSalvandoCaso] = useState(false);
  const [resultado, setResultado] = useState<any>(null);
  const [erro, setErro] = useState("");
  const arquivoRef = useRef<HTMLInputElement>(null);
  const salvandoCasoRef = useRef(false);

  const analisar = async (arquivo?: File) => {
    setAnalisando(true);
    setErro("");
    setResultado(null);
    try {
      const formulario = new FormData();
      formulario.append("area", area);
      if (arquivo) formulario.append("file", arquivo);
      else if (texto.trim().length >= 120) formulario.append("texto", texto);
      else {
        setErro("Cole o texto (mín. 120 caracteres) ou envie um PDF.");
        return;
      }
      const resposta = await api.post("/analise-bancaria/contrato", formulario, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResultado(resposta.data);
    } catch (e: any) {
      setErro(mensagemErroIA(e, "Não foi possível analisar o documento."));
    } finally {
      setAnalisando(false);
    }
  };

  const riscoCor = (risco: string) =>
    risco === "alto"
      ? "bg-danger-100 text-danger-700"
      : risco === "medio"
        ? "bg-warn-100 text-warn-700"
        : "bg-slate-100 text-slate-600";

  const resumoTexto = () => {
    if (!resultado) return "";
    const clausulas = (resultado.clausulas_questionaveis ?? [])
      .map((item: any) => `- [${item.risco}] ${item.clausula}`)
      .join("\n");
    const tarifas = (resultado.tarifas_encargos ?? [])
      .map((item: any) => `- [${item.risco}] ${item.item}: ${item.motivo}`)
      .join("\n");
    return `ANÁLISE (${area}) — ${resultado.resumo || ""}\n\nTarifas/encargos:\n${tarifas}\n\nCláusulas questionáveis:\n${clausulas}\n\n${resultado.proxima_acao || ""}`;
  };

  const salvarNoCaso = async () => {
    if (salvandoCasoRef.current) return;
    if (!casoSelecionado) {
      setAcao("Selecione um caso.");
      return;
    }
    salvandoCasoRef.current = true;
    setSalvandoCaso(true);
    setAcao("");
    try {
      await api.post(`/cases/${casoSelecionado}/movimentos`, {
        tipo: "nota",
        descricao: resumoTexto().slice(0, 4000),
      });
      setAcao("✓ Análise salva no histórico do caso.");
    } catch {
      setAcao("Falha ao salvar.");
    } finally {
      salvandoCasoRef.current = false;
      setSalvandoCaso(false);
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
          ref={arquivoRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => {
            const arquivo = e.target.files?.[0];
            if (arquivo) void analisar(arquivo);
          }}
        />
        <button
          onClick={() => arquivoRef.current?.click()}
          disabled={analisando}
          className="btn-gold text-sm"
        >
          📄 Enviar PDF
        </button>
        <button
          onClick={() => void analisar()}
          disabled={analisando}
          className="btn-secondary text-sm"
        >
          {analisando ? "Analisando…" : "Analisar texto colado"}
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
      {resultado && (
        <div className="mt-4 space-y-3 text-sm">
          {resultado.resumo && (
            <p className="text-slate-700">{resultado.resumo}</p>
          )}
          {resultado.juros && (
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs font-semibold text-slate-500 uppercase">
                Juros
              </p>
              <p className="text-slate-700">
                Taxa:{" "}
                <b>{resultado.juros.taxa_identificada || "não identificada"}</b>{" "}
                · Capitalização: {resultado.juros.capitalizacao}
              </p>
              {resultado.juros.observacao && (
                <p className="text-xs text-slate-500 mt-1">
                  {resultado.juros.observacao}
                </p>
              )}
            </div>
          )}
          {(resultado.tarifas_encargos ?? []).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase mb-1">
                Tarifas / encargos
              </p>
              {resultado.tarifas_encargos.map((tarifa: any, i: number) => (
                <div
                  key={i}
                  className="flex items-start gap-2 py-1 text-xs border-b border-slate-50"
                >
                  <span
                    className={`px-1.5 py-0.5 rounded-full font-medium ${riscoCor(tarifa.risco)}`}
                  >
                    {tarifa.risco}
                  </span>
                  <span className="text-slate-700">
                    <b>{tarifa.item}</b> — {tarifa.motivo}
                  </span>
                </div>
              ))}
            </div>
          )}
          {(resultado.clausulas_questionaveis ?? []).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase mb-1">
                Cláusulas questionáveis
              </p>
              {resultado.clausulas_questionaveis.map(
                (clausula: any, i: number) => (
                  <div
                    key={i}
                    className="py-1.5 text-xs border-b border-slate-50"
                  >
                    <span
                      className={`px-1.5 py-0.5 rounded-full font-medium ${riscoCor(clausula.risco)}`}
                    >
                      {clausula.risco}
                    </span>
                    <span className="text-slate-700 ml-2">
                      {clausula.clausula}
                    </span>
                    {clausula.fundamento && (
                      <span className="text-slate-400 block mt-0.5">
                        Fundamento: {clausula.fundamento}
                      </span>
                    )}
                  </div>
                ),
              )}
            </div>
          )}
          {(resultado.pontos_de_atencao ?? []).length > 0 && (
            <ul className="list-disc list-inside text-xs text-slate-600 space-y-0.5">
              {resultado.pontos_de_atencao.map((ponto: string, i: number) => (
                <li key={i}>{ponto}</li>
              ))}
            </ul>
          )}
          {resultado.proxima_acao && (
            <p className="text-xs text-success-700 bg-success-50 rounded-lg p-2">
              ➡ {resultado.proxima_acao}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-100">
            <select
              className="input text-xs flex-1 min-w-[160px]"
              value={casoSelecionado}
              onChange={(e) => setCasoSelecionado(e.target.value)}
            >
              <option value="">Vincular a um caso…</option>
              {casos.map((caso) => (
                <option key={caso.id} value={caso.id}>
                  {caso.numero_interno} — {caso.titulo}
                </option>
              ))}
            </select>
            <button
              onClick={salvarNoCaso}
              disabled={salvandoCaso}
              className="btn-secondary text-xs disabled:opacity-50"
            >
              {salvandoCaso ? "Salvando…" : "💾 Salvar no caso"}
            </button>
            <select
              className="input text-xs min-w-[150px]"
              value={tipoPeca}
              onChange={(e) => setTipoPeca(e.target.value)}
              title="Tipo de peça (escolha do advogado — obrigatório)"
            >
              <option value="">Tipo de peça…</option>
              {TIPOS_PECA_MINUTA.map((tipo) => (
                <option key={tipo} value={tipo}>
                  {tipo}
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
          {resultado._aviso && (
            <p className="text-[11px] text-warn-700 border-t border-warn-100 pt-2">
              ⚠ {resultado._aviso}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
