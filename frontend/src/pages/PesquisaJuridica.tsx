import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  ExternalLink,
  FileCheck2,
  Search,
  ShieldCheck,
} from "lucide-react";
import { Empty, PageHeader, Spinner } from "../components/UI";
import { mensagemErroHttp } from "../lib/iaErro";
import {
  pesquisarFontesJuridicas,
  verificarCitacoesJuridicas,
  type FontePesquisaJuridica,
  type VerificacaoCitacoesResponse,
} from "../services/legalResearch";

function fonteEhUrl(value?: string | null): boolean {
  return Boolean(value && /^https?:\/\//i.test(value));
}

function percentual(item: FontePesquisaJuridica): string | null {
  const raw =
    typeof item.similarity === "number"
      ? item.similarity
      : typeof item.score === "number"
        ? item.score
        : null;
  if (raw == null) return null;
  const normalizado = raw <= 1 ? raw * 100 : raw;
  return normalizado >= 0 && normalizado <= 100
    ? normalizado.toFixed(0) + "%"
    : null;
}

function statusCitacao(status: string) {
  if (status === "verificada")
    return { label: "Verificada", classe: "bg-success-50 text-success-700" };
  if (status === "identificada")
    return { label: "Identificada", classe: "bg-primary-50 text-primary-700" };
  if (status === "possivelmente_desatualizada")
    return {
      label: "Possivelmente desatualizada",
      classe: "bg-warn-50 text-warn-700",
    };
  if (status === "generica")
    return { label: "Genérica", classe: "bg-warn-50 text-warn-700" };
  return { label: "Suspeita", classe: "bg-danger-50 text-danger-700" };
}

export default function PesquisaJuridica() {
  const [query, setQuery] = useState("");
  const [resultados, setResultados] = useState<FontePesquisaJuridica[] | null>(
    null,
  );
  const [modo, setModo] = useState("");
  const [pipeline, setPipeline] = useState("");
  const [carregando, setCarregando] = useState(false);
  const [erroPesquisa, setErroPesquisa] = useState<string | null>(null);

  const [textoCitacoes, setTextoCitacoes] = useState("");
  const [consultarDatajud, setConsultarDatajud] = useState(false);
  const [verificacao, setVerificacao] =
    useState<VerificacaoCitacoesResponse | null>(null);
  const [validando, setValidando] = useState(false);
  const [erroCitacoes, setErroCitacoes] = useState<string | null>(null);

  const pesquisar = async () => {
    const termo = query.trim();
    if (termo.length < 3) {
      setErroPesquisa("Informe ao menos 3 caracteres para pesquisar.");
      return;
    }
    setCarregando(true);
    setErroPesquisa(null);
    setResultados(null);
    try {
      const data = await pesquisarFontesJuridicas(termo, 10);
      setResultados(data.resultados);
      setModo(data.modo);
      setPipeline(data.pipeline);
    } catch (error) {
      setErroPesquisa(
        mensagemErroHttp(error, "Não foi possível consultar a base jurídica."),
      );
    } finally {
      setCarregando(false);
    }
  };

  const validarCitacoes = async () => {
    const texto = textoCitacoes.trim();
    if (!texto) {
      setErroCitacoes(
        "Cole o trecho jurídico que contém as citações a conferir.",
      );
      return;
    }
    setValidando(true);
    setErroCitacoes(null);
    setVerificacao(null);
    try {
      setVerificacao(await verificarCitacoesJuridicas(texto, consultarDatajud));
    } catch (error) {
      setErroCitacoes(
        mensagemErroHttp(error, "Não foi possível verificar as citações."),
      );
    } finally {
      setValidando(false);
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Conhecimento jurídico"
        title="Pesquisa e validação de fontes"
        subtitle="Pesquise somente no corpus jurídico governado do EJC e confira citações antes do uso profissional."
      />

      <div className="rounded-xl border border-ai-100 bg-ai-50/60 p-4 text-sm text-ai-900">
        <div className="flex items-start gap-2">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            A busca respeita vigência, aprovação, quarentena e escopo do RAG.
            Resultado recuperado não equivale a precedente aplicável: confira a
            fonte oficial e a aderência ao caso concreto.
          </p>
        </div>
      </div>

      <section className="card p-5" data-testid="pesquisa-fontes">
        <div className="mb-4 flex items-center gap-2">
          <Database className="h-5 w-5 text-ai-600" />
          <div>
            <h2 className="font-semibold text-navy">
              Pesquisar fontes governadas
            </h2>
            <p className="text-xs text-slate-500">
              Legislação, jurisprudência, súmulas, doutrina e demais documentos
              aprovados para recuperação pela IA.
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <Search
              size={16}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
            />
            <input
              className="input w-full pl-9"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void pesquisar();
              }}
              placeholder="Ex.: negativação indevida dano moral STJ"
              aria-label="Consulta jurídica"
            />
          </div>
          <button
            className="btn btn-primary gap-2"
            onClick={() => void pesquisar()}
            disabled={carregando}
          >
            {carregando ? <Spinner /> : <Search size={15} />}
            Pesquisar
          </button>
        </div>

        {erroPesquisa && (
          <p role="alert" className="mt-3 text-sm text-danger-600">
            {erroPesquisa}
          </p>
        )}

        {resultados && (
          <div className="mt-4 space-y-3">
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
              <span>{resultados.length} fonte(s) recuperada(s)</span>
              {modo && <span>· modo: {modo}</span>}
              {pipeline && <span>· pipeline: {pipeline}</span>}
            </div>

            {resultados.length === 0 ? (
              <Empty message="Nenhuma fonte governada encontrada para esta consulta." />
            ) : (
              resultados.map((item, index) => {
                const score = percentual(item);
                return (
                  <article
                    key={item.chunk_id || item.doc_id || index}
                    className="rounded-xl border border-slate-200 p-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <h3 className="font-semibold text-navy">
                          {item.titulo || "Fonte jurídica"}
                        </h3>
                        <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-slate-500">
                          {item.categoria && <span>{item.categoria}</span>}
                          {item.tribunal && <span>· {item.tribunal}</span>}
                          {item.confianca && (
                            <span>· confiança: {item.confianca}</span>
                          )}
                          {item.autoridade?.label && (
                            <span>· autoridade: {item.autoridade.label}</span>
                          )}
                        </div>
                      </div>
                      {score && (
                        <span className="rounded-full bg-success-50 px-2 py-1 text-[10px] font-bold text-success-700">
                          {score} relevância
                        </span>
                      )}
                    </div>

                    {item.conteudo && (
                      <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-slate-600">
                        {item.conteudo.slice(0, 1200)}
                        {item.conteudo.length > 1200 ? "…" : ""}
                      </p>
                    )}

                    {item.fonte && (
                      <div className="mt-3 text-xs text-slate-500">
                        <span className="font-semibold">Fonte: </span>
                        {fonteEhUrl(item.fonte) ? (
                          <a
                            href={item.fonte}
                            target="_blank"
                            rel="noreferrer noopener"
                            className="inline-flex items-center gap-1 text-ai-700 underline underline-offset-2"
                          >
                            Abrir fonte registrada <ExternalLink size={11} />
                          </a>
                        ) : (
                          <span>{item.fonte}</span>
                        )}
                      </div>
                    )}
                  </article>
                );
              })
            )}
          </div>
        )}
      </section>

      <section className="card p-5" data-testid="validacao-citacoes">
        <div className="mb-4 flex items-center gap-2">
          <FileCheck2 className="h-5 w-5 text-ai-600" />
          <div>
            <h2 className="font-semibold text-navy">Verificar citações</h2>
            <p className="text-xs text-slate-500">
              Validação determinística anti-alucinação. A consulta ao DataJud é
              opcional e limitada pelo backend.
            </p>
          </div>
        </div>

        <textarea
          className="input min-h-[150px] resize-y"
          value={textoCitacoes}
          onChange={(event) => setTextoCitacoes(event.target.value)}
          maxLength={200000}
          placeholder="Cole aqui o trecho com números de processos, recursos, súmulas ou artigos de lei."
        />
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <label className="flex items-center gap-2 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={consultarDatajud}
              onChange={(event) => setConsultarDatajud(event.target.checked)}
            />
            Confirmar números CNJ também no DataJud quando disponível
          </label>
          <button
            className="btn btn-primary gap-2"
            onClick={() => void validarCitacoes()}
            disabled={validando}
          >
            {validando ? <Spinner /> : <FileCheck2 size={15} />}
            Verificar citações
          </button>
        </div>

        {erroCitacoes && (
          <p role="alert" className="mt-3 text-sm text-danger-600">
            {erroCitacoes}
          </p>
        )}

        {verificacao && (
          <div className="mt-4 space-y-3">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <div className="rounded-xl bg-slate-50 p-3">
                <p className="text-[10px] uppercase text-slate-400">Citações</p>
                <p className="text-xl font-bold text-navy">
                  {verificacao.total}
                </p>
              </div>
              <div className="rounded-xl bg-success-50 p-3">
                <p className="text-[10px] uppercase text-success-600">
                  Verificadas
                </p>
                <p className="text-xl font-bold text-success-700">
                  {verificacao.confirmadas}
                </p>
              </div>
              <div className="rounded-xl bg-warn-50 p-3">
                <p className="text-[10px] uppercase text-warn-600">
                  Não confirmadas
                </p>
                <p className="text-xl font-bold text-warn-700">
                  {verificacao.nao_encontradas}
                </p>
              </div>
              <div className="rounded-xl bg-ai-50 p-3">
                <p className="text-[10px] uppercase text-ai-600">
                  Confiabilidade
                </p>
                <p className="text-xl font-bold text-ai-800">
                  {verificacao.score == null ? "—" : verificacao.score + "%"}
                </p>
              </div>
            </div>

            {verificacao.avisos?.map((aviso, index) => (
              <div
                key={index}
                className="flex items-start gap-2 rounded-lg border border-warn-200 bg-warn-50 p-3 text-xs text-warn-800"
              >
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                <span>{aviso}</span>
              </div>
            ))}

            <div className="space-y-2">
              {verificacao.citacoes.map((citacao, index) => {
                const badge = statusCitacao(citacao.status);
                return (
                  <div
                    key={citacao.numero || citacao.citacao || index}
                    className="rounded-xl border border-slate-200 p-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        {citacao.status === "verificada" ? (
                          <CheckCircle2
                            size={15}
                            className="text-success-600"
                          />
                        ) : (
                          <AlertTriangle size={15} className="text-warn-600" />
                        )}
                        <span className="font-semibold text-navy">
                          {citacao.citacao}
                        </span>
                      </div>
                      <span
                        className={
                          "rounded-full px-2 py-1 text-[10px] font-bold " +
                          badge.classe
                        }
                      >
                        {badge.label}
                      </span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-500">
                      <span>tipo: {citacao.tipo}</span>
                      {citacao.tribunal && <span>· {citacao.tribunal}</span>}
                      {citacao.orgao && <span>· {citacao.orgao}</span>}
                      {citacao.data && <span>· {citacao.data}</span>}
                    </div>
                    {citacao.aviso && (
                      <p className="mt-2 text-xs leading-relaxed text-slate-600">
                        {citacao.aviso}
                      </p>
                    )}
                    {citacao.fonte_verificacao && (
                      <p className="mt-2 text-xs text-slate-500">
                        <span className="font-semibold">
                          Fonte de verificação:{" "}
                        </span>
                        {citacao.fonte_verificacao}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
