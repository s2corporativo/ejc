import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import {
  ArrowLeft,
  BookOpen,
  Briefcase,
  Calculator,
  ExternalLink,
  FileSearch,
  FolderOpen,
  Library,
  Plus,
  Sparkles,
  Wrench,
} from "lucide-react";
import Markdown from "../../components/Markdown";
import { toast } from "../../components/Toast";
import {
  Empty,
  Modal,
  PageHeader,
  Spinner,
  StatusBadge,
} from "../../components/UI";
import RodapeRegra, { METADADOS_REGRA } from "../../components/RodapeRegra";
import api from "../../lib/api";
import {
  AVISO_FERRAMENTA_NAO_HOMOLOGADA,
  mensagemErroFerramenta,
  mensagemErroIA,
} from "../../lib/iaErro";
import { useCaseContext } from "../../stores/caseContext";
import type { Case } from "../../types";
import GuiaBancario from "../../components/GuiaBancario";
import AnaliseExtratos from "../../components/AnaliseExtratos";
import BancarioForense from "../../components/BancarioForense";
import GuiaTransito from "../../components/GuiaTransito";
import GuiaTrabalhista from "../../components/GuiaTrabalhista";
import LiquidacaoTrabalhista from "../../components/LiquidacaoTrabalhista";
import GuiaTributario from "../../components/GuiaTributario";
import TributarioFiscal from "../../components/TributarioFiscal";
import GuiaPrevidenciario from "../../components/GuiaPrevidenciario";
import PrevidenciarioSimulacao from "../../components/PrevidenciarioSimulacao";
import GuiaAmbiental from "../../components/GuiaAmbiental";
import AmbientalAutos from "../../components/AmbientalAutos";
import AmbientalEstrategia from "../../components/AmbientalEstrategia";
import GuiaCivil from "../../components/GuiaCivil";
import GuiaPenal from "../../components/GuiaPenal";
import GuiaConsumidor from "../../components/GuiaConsumidor";
import GuiaImobiliario from "../../components/GuiaImobiliario";
import GuiaFamilia from "../../components/GuiaFamilia";
import GuiaAdministrativo from "../../components/GuiaAdministrativo";
import GuiaEmpresarial from "../../components/GuiaEmpresarial";
import SociedadesCliente from "../../components/SociedadesCliente";
import LgpdRegistros from "../../components/LgpdRegistros";
import GuiaLgpd from "../../components/GuiaLgpd";
import {
  camposVisiveis,
  chavesObsoletas,
  paramsVisiveis,
} from "./camposCondicionais";
import {
  linhasDoResultado,
  provenienciaDoResultado,
  rodapeDoResultado,
} from "./demonstrativo";
import { RAMOS, type FerramentaConfig, type RamoConfig } from "./ramosConfig";
import {
  abasDoWorkspace,
  casosDaAreaPath,
  ferramentasDoWorkspace,
  importacaoDaAreaPath,
  novoCasoPath,
  subareasDoWorkspace,
  subtituloDoWorkspace,
  tituloDoWorkspace,
  type WorkspaceTabId,
} from "./areasWorkspace";

const ROTULO_ABA: Record<WorkspaceTabId, string> = {
  "visao-geral": "Visão geral",
  casos: "Casos",
  ferramentas: "Ferramentas",
  analise: "IA & Análise",
  referencias: "Referências",
};

const ICONE_ABA: Record<WorkspaceTabId, typeof Briefcase> = {
  "visao-geral": Briefcase,
  casos: FolderOpen,
  ferramentas: Wrench,
  analise: Sparkles,
  referencias: Library,
};

function rotulo(valor: string) {
  return valor
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letra) => letra.toUpperCase());
}

function ResultadoView({ data }: { data: unknown }) {
  if (data === null || data === undefined) return null;
  if (Array.isArray(data)) {
    return (
      <ul className="space-y-1 pl-4">
        {data.map((item, index) => (
          <li
            key={index}
            className="text-xs text-slate-700 dark:text-slate-200"
          >
            {typeof item === "object" && item !== null ? (
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
      <div className="space-y-1.5">
        {Object.entries(data as Record<string, unknown>).map(
          ([chave, valor]) => {
            if (
              chave === "homologada" ||
              chave === "aviso_homologacao" ||
              METADADOS_REGRA.includes(chave) ||
              valor === null ||
              valor === undefined
            ) {
              return null;
            }
            if (typeof valor === "object") {
              return (
                <div
                  key={chave}
                  className="rounded-lg bg-slate-50/70 p-2 dark:bg-white/[0.03]"
                >
                  <div className="mb-1 text-xs font-semibold text-slate-700 dark:text-slate-200">
                    {rotulo(chave)}
                  </div>
                  <ResultadoView data={valor} />
                </div>
              );
            }
            return (
              <div key={chave} className="flex justify-between gap-4 text-xs">
                <span className="text-slate-500">{rotulo(chave)}</span>
                <span className="text-right font-medium text-slate-800 dark:text-slate-100">
                  {typeof valor === "boolean"
                    ? valor
                      ? "Sim"
                      : "Não"
                    : String(valor)}
                </span>
              </div>
            );
          },
        )}
      </div>
    );
  }
  return <span className="text-xs">{String(data)}</span>;
}

function FerramentaWorkspace({ ferramenta }: { ferramenta: FerramentaConfig }) {
  const [valores, setValores] = useState<Record<string, string | number>>(
    () => {
      const iniciais: Record<string, string | number> = {};
      ferramenta.campos.forEach((campo) => {
        if (campo.default !== undefined) iniciais[campo.nome] = campo.default;
      });
      return iniciais;
    },
  );
  const [resultado, setResultado] = useState<Record<string, unknown> | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [gerando, setGerando] = useState(false);
  const [mensagemDocumento, setMensagemDocumento] = useState<string | null>(
    null,
  );
  const [linkDocumento, setLinkDocumento] = useState<string | null>(null);
  const casoAtivo = useCaseContext((state) => state.caso);

  const visiveis = camposVisiveis(ferramenta.campos, valores);
  const bloqueada =
    ferramenta.homologada === false || resultado?.homologada === false;

  useEffect(() => {
    const obsoletas = chavesObsoletas(ferramenta.campos, valores);
    if (!obsoletas.length) return;
    setValores((atuais) => {
      const copia = { ...atuais };
      obsoletas.forEach((nome) => delete copia[nome]);
      return copia;
    });
  }, [ferramenta.campos, valores]);

  const calcular = async () => {
    setLoading(true);
    setErro(null);
    setResultado(null);
    setMensagemDocumento(null);
    setLinkDocumento(null);
    try {
      const resposta = await api.get(ferramenta.endpoint, {
        params: paramsVisiveis(ferramenta.campos, valores),
      });
      setResultado(resposta.data);
    } catch (error: unknown) {
      setErro(mensagemErroFerramenta(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (ferramenta.autoLoad) void calcular();
    // A identidade da ferramenta controla o carregamento automático.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ferramenta.id]);

  const gerarDemonstrativo = async () => {
    if (!resultado || bloqueada) {
      setMensagemDocumento(
        bloqueada
          ? `Bloqueado: ${AVISO_FERRAMENTA_NAO_HOMOLOGADA}`
          : "Calcule antes de gerar o demonstrativo.",
      );
      return;
    }
    const proveniencia = provenienciaDoResultado(resultado);
    if (!proveniencia) {
      setMensagemDocumento(
        "Não foi possível salvar: faltam fontes, vigência ou versão da regra na resposta.",
      );
      return;
    }
    setGerando(true);
    setMensagemDocumento(null);
    try {
      await api.post("/pecas/demonstrativo", {
        titulo: ferramenta.titulo,
        base_legal: ferramenta.baseLegal,
        linhas: linhasDoResultado(resultado),
        rodape: rodapeDoResultado(resultado) || undefined,
        case_id: casoAtivo?.id || undefined,
        ferramenta: ferramenta.endpoint,
        fontes: proveniencia.fontes,
        vigencia_regra: proveniencia.vigencia_regra,
        versao_regra: proveniencia.versao_regra,
      });
      const link = casoAtivo ? `/pecas?caso=${casoAtivo.id}` : "/pecas";
      setLinkDocumento(link);
      setMensagemDocumento(
        casoAtivo
          ? `Salvo em Peças > Rascunhos, vinculado ao caso “${casoAtivo.titulo}”.`
          : "Salvo em Peças > Rascunhos, sem vínculo com caso.",
      );
    } catch (error: unknown) {
      setMensagemDocumento(
        mensagemErroFerramenta(
          error,
          "Falha ao salvar o demonstrativo em Peças.",
        ),
      );
    } finally {
      setGerando(false);
    }
  };

  return (
    <section
      id={`ferramenta-${ferramenta.id}`}
      className="scroll-mt-28 rounded-2xl border border-black/[0.06] bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/[0.03]"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Calculator className="h-4 w-4 text-ouro-profundo" />
            <h3 className="text-sm font-bold text-slate-950 dark:text-white">
              {ferramenta.titulo}
            </h3>
          </div>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            {ferramenta.descricao}
          </p>
          <p className="mt-1 text-[11px] font-medium text-ouro-profundo">
            {ferramenta.baseLegal}
          </p>
        </div>
        {ferramenta.homologada === false && (
          <span className="rounded-full bg-warn-50 px-2 py-1 text-[10px] font-semibold text-warn-700">
            Em revisão jurídica
          </span>
        )}
      </div>

      {visiveis.length > 0 && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {visiveis.map((campo) => (
            <label
              key={campo.nome}
              className="text-xs text-slate-600 dark:text-slate-300"
            >
              <span className="mb-1 block font-medium">{campo.label}</span>
              {campo.tipo === "select" ? (
                <select
                  className="input w-full text-sm"
                  value={valores[campo.nome] ?? ""}
                  onChange={(event) =>
                    setValores({ ...valores, [campo.nome]: event.target.value })
                  }
                >
                  <option value="">Selecione…</option>
                  {campo.opcoes?.map((opcao) => (
                    <option key={opcao} value={opcao}>
                      {rotulo(opcao)}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className="input w-full text-sm"
                  type={campo.tipo}
                  step={campo.tipo === "number" ? "0.01" : undefined}
                  value={valores[campo.nome] ?? ""}
                  onChange={(event) =>
                    setValores({ ...valores, [campo.nome]: event.target.value })
                  }
                />
              )}
            </label>
          ))}
        </div>
      )}

      {(!ferramenta.autoLoad || visiveis.length > 0) && (
        <button
          className="btn-gold mt-3 text-sm"
          disabled={loading}
          onClick={calcular}
        >
          {loading
            ? "Calculando…"
            : ferramenta.campos.length
              ? "Calcular"
              : "Atualizar"}
        </button>
      )}

      {erro && <p className="mt-3 text-xs text-danger-600">{erro}</p>}
      {resultado && (
        <div className="mt-4 rounded-xl border border-black/[0.05] bg-slate-50/70 p-3 dark:border-white/10 dark:bg-white/[0.02]">
          <div className="mb-2 flex items-center justify-between gap-3">
            <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">
              Resultado de apoio — revisão humana obrigatória
            </span>
          </div>
          <ResultadoView data={resultado} />
          <RodapeRegra data={resultado} />
          {resultado.homologada === false && (
            <p className="mt-2 rounded-lg bg-warn-50 p-2 text-xs text-warn-700">
              {String(
                resultado.aviso_homologacao || AVISO_FERRAMENTA_NAO_HOMOLOGADA,
              )}
            </p>
          )}
          {!ferramenta.autoLoad && (
            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-black/[0.05] pt-3 dark:border-white/10">
              <button
                className="btn-secondary text-xs"
                disabled={gerando || bloqueada}
                onClick={gerarDemonstrativo}
              >
                {gerando ? "Salvando…" : "Gerar demonstrativo"}
              </button>
              {mensagemDocumento && (
                <span className="text-xs text-slate-500">
                  {mensagemDocumento}{" "}
                  {linkDocumento && (
                    <Link
                      className="font-semibold text-ouro-profundo underline"
                      to={linkDocumento}
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
    </section>
  );
}

const TITULO_ANALISE: Record<string, string> = {
  bancario: "Análise de contrato bancário",
  consumidor: "Análise de documento de consumo",
  trabalhista: "Análise de documento trabalhista",
  empresarial: "Análise de contrato empresarial",
  tributario: "Análise de auto ou documento tributário",
  ambiental: "Análise de auto ambiental",
  digital_lgpd: "Análise de contrato digital / LGPD",
};

const TIPOS_PECA = [
  "petição inicial",
  "contestação",
  "réplica",
  "recurso",
  "defesa administrativa",
  "notificação extrajudicial",
  "parecer",
];

function AnaliseDocumento({ area, casos }: { area: string; casos: Case[] }) {
  const [texto, setTexto] = useState("");
  const [resultado, setResultado] = useState<Record<string, unknown> | null>(
    null,
  );
  const [erro, setErro] = useState("");
  const [loading, setLoading] = useState(false);
  const [casoSelecionado, setCasoSelecionado] = useState("");
  const [tipoPeca, setTipoPeca] = useState("");
  const [acao, setAcao] = useState("");
  const [minuta, setMinuta] = useState("");
  const arquivoRef = useRef<HTMLInputElement>(null);

  const analisar = async (arquivo?: File) => {
    if (!arquivo && texto.trim().length < 120) {
      setErro("Cole ao menos 120 caracteres ou envie um PDF.");
      return;
    }
    setLoading(true);
    setErro("");
    setResultado(null);
    try {
      const formulario = new FormData();
      formulario.append("area", area);
      if (arquivo) formulario.append("file", arquivo);
      else formulario.append("texto", texto);
      const resposta = await api.post(
        "/analise-bancaria/contrato",
        formulario,
        {
          headers: { "Content-Type": "multipart/form-data" },
        },
      );
      setResultado(resposta.data);
    } catch (error: unknown) {
      setErro(mensagemErroIA(error, "Não foi possível analisar o documento."));
    } finally {
      setLoading(false);
    }
  };

  const resumo = () => {
    if (!resultado) return "";
    const principal =
      typeof resultado.resumo === "string" ? resultado.resumo : "";
    return `${principal}\n\n${JSON.stringify(resultado, null, 2)}`.slice(
      0,
      4000,
    );
  };

  const salvarNoCaso = async () => {
    if (!casoSelecionado) {
      setAcao("Selecione o caso em que a análise será registrada.");
      return;
    }
    try {
      await api.post(`/cases/${casoSelecionado}/movimentos`, {
        tipo: "nota",
        descricao: resumo(),
      });
      setAcao("Análise registrada na timeline do caso.");
    } catch {
      setAcao("Não foi possível registrar a análise no caso.");
    }
  };

  const gerarMinuta = async () => {
    if (!tipoPeca || !resultado) return;
    setAcao("Gerando minuta…");
    setMinuta("");
    try {
      const resposta = await api.post("/ai/gerar-minuta", {
        tema: "Minuta baseada na análise documental",
        tipo_peca: tipoPeca,
        area,
        fatos: resumo().slice(0, 3000),
      });
      setMinuta(
        resposta.data.minuta ||
          resposta.data.texto ||
          resposta.data.resposta ||
          "",
      );
      setAcao("");
    } catch (error: unknown) {
      setAcao(mensagemErroIA(error, "Não foi possível gerar a minuta."));
    }
  };

  return (
    <section className="rounded-2xl border border-black/[0.06] bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]">
      <div className="flex items-start gap-3">
        <div className="grid h-9 w-9 place-items-center rounded-lg bg-success-50 text-success-700">
          <FileSearch className="h-4 w-4" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-slate-950 dark:text-white">
            {TITULO_ANALISE[area] || "Análise de documento"}
          </h3>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            Apoio por IA com revisão obrigatória do advogado. A conclusão não
            substitui conferência dos autos e das fontes.
          </p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <input
          ref={arquivoRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(event) => {
            const arquivo = event.target.files?.[0];
            if (arquivo) void analisar(arquivo);
          }}
        />
        <button
          className="btn-gold text-sm"
          onClick={() => arquivoRef.current?.click()}
        >
          Enviar PDF
        </button>
        <button
          className="btn-secondary text-sm"
          disabled={loading}
          onClick={() => void analisar()}
        >
          {loading ? "Analisando…" : "Analisar texto"}
        </button>
      </div>
      <textarea
        className="input mt-2 w-full text-sm"
        rows={6}
        value={texto}
        onChange={(event) => setTexto(event.target.value)}
        placeholder="Cole aqui o texto do documento…"
      />
      {erro && <p className="mt-2 text-xs text-danger-600">{erro}</p>}

      {resultado && (
        <div className="mt-4 space-y-3 rounded-xl bg-slate-50/70 p-3 dark:bg-white/[0.02]">
          <ResultadoView data={resultado} />
          <div className="grid gap-2 border-t border-black/[0.05] pt-3 dark:border-white/10 md:grid-cols-[1fr_auto_auto]">
            <select
              className="input text-xs"
              value={casoSelecionado}
              onChange={(event) => setCasoSelecionado(event.target.value)}
            >
              <option value="">Vincular a um caso…</option>
              {casos.map((caso) => (
                <option key={caso.id} value={caso.id}>
                  {caso.numero_interno} — {caso.titulo}
                </option>
              ))}
            </select>
            <button className="btn-secondary text-xs" onClick={salvarNoCaso}>
              Salvar no caso
            </button>
            <select
              className="input text-xs"
              value={tipoPeca}
              onChange={(event) => setTipoPeca(event.target.value)}
            >
              <option value="">Tipo de peça…</option>
              {TIPOS_PECA.map((tipo) => (
                <option key={tipo} value={tipo}>
                  {tipo}
                </option>
              ))}
            </select>
          </div>
          <button
            className="btn-gold text-xs disabled:opacity-50"
            disabled={!tipoPeca}
            onClick={gerarMinuta}
          >
            Gerar minuta a partir da análise
          </button>
          {acao && <p className="text-xs text-slate-500">{acao}</p>}
          {minuta && (
            <div className="rounded-xl border border-black/[0.05] bg-white p-3 dark:border-white/10 dark:bg-white/[0.03]">
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                Minuta — rascunho para revisão humana
              </p>
              <Markdown
                source={minuta}
                className="max-h-96 overflow-y-auto text-sm"
              />
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function ComparadorBacen() {
  const [modalidades, setModalidades] = useState<Array<Record<string, string>>>(
    [],
  );
  const [periodo, setPeriodo] = useState("");
  const [indice, setIndice] = useState("");
  const [taxa, setTaxa] = useState("");
  const [resultado, setResultado] = useState<Record<string, unknown> | null>(
    null,
  );
  const [erro, setErro] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api
      .get("/analise-bancaria/modalidades")
      .then((resposta) => {
        setModalidades(resposta.data?.modalidades ?? []);
        setPeriodo(resposta.data?.periodo ?? "");
      })
      .catch(() => undefined);
  }, []);

  const comparar = async () => {
    const modalidade = modalidades[Number(indice)];
    if (!modalidade) {
      setErro("Selecione a modalidade.");
      return;
    }
    setLoading(true);
    setErro("");
    try {
      const resposta = await api.get("/analise-bancaria/taxa-media", {
        params: {
          modalidade: modalidade.modalidade,
          segmento: modalidade.segmento,
          periodo,
        },
      });
      setResultado({
        ...resposta.data,
        taxa_informada_percentual_mes: taxa || undefined,
      });
    } catch (error: unknown) {
      setErro(
        mensagemErroFerramenta(error, "Falha ao consultar a média do BACEN."),
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="rounded-2xl border border-black/[0.06] bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]">
      <div className="flex items-center gap-2">
        <Calculator className="h-4 w-4 text-ouro-profundo" />
        <h3 className="text-sm font-bold text-slate-950 dark:text-white">
          Comparador de Juros — BACEN
        </h3>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        Compara a taxa informada com a referência de mercado. Diferença de taxa
        é indício de análise, não conclusão automática de abusividade.
      </p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <select
          className="input"
          value={indice}
          onChange={(event) => setIndice(event.target.value)}
        >
          <option value="">Modalidade…</option>
          {modalidades.map((modalidade, index) => (
            <option key={`${modalidade.modalidade}:${index}`} value={index}>
              {modalidade.segmento} · {modalidade.modalidade}
            </option>
          ))}
        </select>
        <input
          className="input"
          value={taxa}
          onChange={(event) => setTaxa(event.target.value)}
          placeholder="Taxa do contrato (% a.m.)"
        />
      </div>
      <button
        className="btn-gold mt-3 text-sm"
        disabled={loading}
        onClick={comparar}
      >
        {loading ? "Consultando…" : "Comparar"}
      </button>
      {erro && <p className="mt-2 text-xs text-danger-600">{erro}</p>}
      {resultado && (
        <div className="mt-3 rounded-xl bg-slate-50 p-3 dark:bg-white/[0.03]">
          <ResultadoView data={resultado} />
          <p className="mt-2 text-[11px] text-warn-700">
            Indicador de apoio. A conclusão jurídica exige análise individual do
            contrato e das circunstâncias do caso.
          </p>
        </div>
      )}
    </section>
  );
}

function CasosWorkspace({
  casos,
  area,
}: {
  casos: Case[] | null;
  area: string;
}) {
  if (casos === null) return <Spinner />;
  if (!casos.length) {
    return (
      <Empty message="Nenhum caso encontrado nesta área. Use “Novo caso” para iniciar um cadastro com a área pré-selecionada." />
    );
  }
  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Link className="btn-secondary text-sm" to={casosDaAreaPath(area)}>
          Abrir lista completa em Casos
        </Link>
      </div>
      {casos.map((caso) => (
        <Link
          key={caso.id}
          to={`/casos/${caso.id}`}
          className="flex flex-col gap-3 rounded-2xl border border-black/[0.06] bg-white p-4 transition hover:border-ouro/40 hover:shadow-sm dark:border-white/10 dark:bg-white/[0.03] sm:flex-row sm:items-center"
        >
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
              {caso.numero_interno || "Caso"}
            </p>
            <h3 className="mt-1 truncate text-sm font-bold text-slate-950 dark:text-white">
              {caso.titulo}
            </h3>
          </div>
          {caso.status && <StatusBadge value={String(caso.status)} />}
        </Link>
      ))}
    </div>
  );
}

function EstatisticasWorkspace({ casos }: { casos: Case[] | null }) {
  const total = casos?.length ?? 0;
  const ativos =
    casos?.filter(
      (caso) => !["encerrado", "arquivado"].includes(String(caso.status)),
    ).length ?? 0;
  const producao =
    casos?.filter((caso) => String(caso.status) === "em_producao").length ?? 0;
  const protocolados =
    casos?.filter((caso) => String(caso.status) === "protocolado").length ?? 0;
  const itens = [
    ["Casos", total],
    ["Ativos", ativos],
    ["Em produção", producao],
    ["Protocolados", protocolados],
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {itens.map(([rotuloItem, valor]) => (
        <div
          key={String(rotuloItem)}
          className="rounded-2xl border border-black/[0.05] bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]"
        >
          <p className="text-xs text-slate-500">{rotuloItem}</p>
          <p className="mt-1 text-2xl font-bold text-slate-950 dark:text-white">
            {valor}
          </p>
        </div>
      ))}
    </div>
  );
}

export default function RamoBase() {
  const { slug } = useParams<{ slug: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const cfg: RamoConfig | undefined = slug ? RAMOS[slug] : undefined;
  const [casos, setCasos] = useState<Case[] | null>(null);
  const [registrosEspecializados, setRegistrosEspecializados] = useState<
    unknown[] | null
  >(null);
  const [modalRegistro, setModalRegistro] = useState(false);
  const [formularioRegistro, setFormularioRegistro] = useState<
    Record<string, unknown>
  >({});
  const [salvandoRegistro, setSalvandoRegistro] = useState(false);

  const abas = useMemo(() => (cfg ? abasDoWorkspace(cfg) : []), [cfg]);
  const abaSolicitada = searchParams.get("tab") as WorkspaceTabId | null;
  const abaAtiva =
    abaSolicitada && abas.includes(abaSolicitada)
      ? abaSolicitada
      : "visao-geral";

  useEffect(() => {
    if (!cfg) return;
    setCasos(null);
    setFormularioRegistro({});
    const areas = [cfg.areaCaso, ...(cfg.areasLegadas ?? [])];
    Promise.all(
      areas.map((area) =>
        api
          .get("/cases/", { params: { area, page_size: 100 } })
          .then((resposta) => (resposta.data.data ?? []) as Case[])
          .catch(() => [] as Case[]),
      ),
    )
      .then((listas) => {
        const unicos = new Map<string, Case>();
        listas.flat().forEach((caso) => unicos.set(caso.id, caso));
        setCasos([...unicos.values()]);
      })
      .catch(() => setCasos([]));

    if (cfg.externo) {
      setRegistrosEspecializados([]);
    } else {
      setRegistrosEspecializados(null);
      api
        .get(cfg.endpoint)
        .then((resposta) =>
          setRegistrosEspecializados(resposta.data.data ?? []),
        )
        .catch(() => setRegistrosEspecializados([]));
    }
  }, [cfg, slug]);

  useEffect(() => {
    const ferramenta = searchParams.get("ferramenta");
    if (abaAtiva !== "ferramentas" || !ferramenta) return;
    const id = window.requestAnimationFrame(() => {
      document
        .getElementById(`ferramenta-${ferramenta}`)
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    return () => window.cancelAnimationFrame(id);
  }, [abaAtiva, searchParams]);

  if (!cfg) return <Empty message="Área de atuação não encontrada" />;

  const ferramentas = ferramentasDoWorkspace(cfg);
  const subareas = subareasDoWorkspace(cfg);

  const mudarAba = (aba: WorkspaceTabId) => {
    const proximo = new URLSearchParams(searchParams);
    proximo.set("tab", aba);
    proximo.delete("ferramenta");
    setSearchParams(proximo, { replace: true });
  };

  const registrarEspecializado = async () => {
    if (!formularioRegistro.case_id) {
      toast.error("Selecione o caso que receberá os dados especializados.");
      return;
    }
    const obrigatorio = cfg.campos.find(
      (campo) => campo.obrigatorio && !formularioRegistro[campo.nome],
    );
    if (obrigatorio) {
      toast.error(`Campo obrigatório: ${obrigatorio.label}`);
      return;
    }
    setSalvandoRegistro(true);
    try {
      await api.post(cfg.endpoint, formularioRegistro);
      const resposta = await api.get(cfg.endpoint);
      setRegistrosEspecializados(resposta.data.data ?? []);
      setModalRegistro(false);
      setFormularioRegistro({});
      toast.success("Dados especializados registrados no caso.");
    } catch (error: unknown) {
      toast.error(
        mensagemErroFerramenta(
          error,
          "Não foi possível registrar os dados especializados.",
        ),
      );
    } finally {
      setSalvandoRegistro(false);
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-5 px-6 py-6">
      <PageHeader
        eyebrow="Workspace jurídico"
        title={tituloDoWorkspace(cfg)}
        subtitle={subtituloDoWorkspace(cfg)}
        actions={
          <>
            <Link
              className="btn-secondary flex items-center gap-1"
              to="/areas-de-atuacao"
            >
              <ArrowLeft className="h-4 w-4" /> Áreas
            </Link>
            <Link className="btn-secondary" to={casosDaAreaPath(cfg.areaCaso)}>
              Ver em Casos
            </Link>
            <Link
              className="btn-gold flex items-center gap-1"
              to={novoCasoPath(cfg.areaCaso)}
            >
              <Plus className="h-4 w-4" /> Novo caso
            </Link>
          </>
        }
      />

      <nav
        className="flex gap-1 overflow-x-auto rounded-2xl border border-black/[0.06] bg-white p-1.5 dark:border-white/10 dark:bg-white/[0.03]"
        aria-label="Seções do workspace"
      >
        {abas.map((aba) => {
          const Icone = ICONE_ABA[aba];
          const ativa = aba === abaAtiva;
          return (
            <button
              key={aba}
              type="button"
              onClick={() => mudarAba(aba)}
              className={`flex min-w-max items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium transition ${
                ativa
                  ? "bg-slate-950 text-white shadow-sm dark:bg-white dark:text-slate-950"
                  : "text-slate-500 hover:bg-black/[0.04] hover:text-slate-900 dark:text-slate-300 dark:hover:bg-white/[0.06] dark:hover:text-white"
              }`}
              aria-current={ativa ? "page" : undefined}
            >
              <Icone className="h-4 w-4" /> {ROTULO_ABA[aba]}
            </button>
          );
        })}
      </nav>

      {abaAtiva === "visao-geral" && (
        <div className="space-y-5">
          <EstatisticasWorkspace casos={casos} />

          <section className="grid gap-3 md:grid-cols-3">
            <Link
              to={casosDaAreaPath(cfg.areaCaso)}
              className="rounded-2xl border border-black/[0.06] bg-white p-4 transition hover:border-ouro/40 dark:border-white/10 dark:bg-white/[0.03]"
            >
              <FolderOpen className="h-5 w-5 text-ouro-profundo" />
              <h3 className="mt-3 text-sm font-bold text-slate-950 dark:text-white">
                Trabalhar casos
              </h3>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                Abra a carteira completa já filtrada por esta área.
              </p>
            </Link>
            <Link
              to={importacaoDaAreaPath(cfg.areaCaso)}
              className="rounded-2xl border border-black/[0.06] bg-white p-4 transition hover:border-ouro/40 dark:border-white/10 dark:bg-white/[0.03]"
            >
              <FileSearch className="h-5 w-5 text-ouro-profundo" />
              <h3 className="mt-3 text-sm font-bold text-slate-950 dark:text-white">
                Importar documento
              </h3>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                Inicie um caso pela leitura documental com a área
                pré-selecionada.
              </p>
            </Link>
            {abas.includes("ferramentas") ? (
              <button
                type="button"
                onClick={() => mudarAba("ferramentas")}
                className="rounded-2xl border border-black/[0.06] bg-white p-4 text-left transition hover:border-ouro/40 dark:border-white/10 dark:bg-white/[0.03]"
              >
                <Wrench className="h-5 w-5 text-ouro-profundo" />
                <h3 className="mt-3 text-sm font-bold text-slate-950 dark:text-white">
                  Abrir ferramentas
                </h3>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  Cálculos, simuladores e utilitários próprios desta matéria.
                </p>
              </button>
            ) : (
              <Link
                to="/pecas"
                className="rounded-2xl border border-black/[0.06] bg-white p-4 transition hover:border-ouro/40 dark:border-white/10 dark:bg-white/[0.03]"
              >
                <BookOpen className="h-5 w-5 text-ouro-profundo" />
                <h3 className="mt-3 text-sm font-bold text-slate-950 dark:text-white">
                  Peças
                </h3>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  Acesse a produção jurídica do escritório.
                </p>
              </Link>
            )}
          </section>

          {!cfg.externo && (
            <section className="rounded-2xl border border-black/[0.06] bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-sm font-bold text-slate-950 dark:text-white">
                    Dados especializados
                  </h3>
                  <p className="mt-1 text-xs text-slate-500">
                    Registro complementar vinculado a um caso existente. Não
                    cria um segundo caso.
                  </p>
                </div>
                <button
                  className="btn-secondary text-sm"
                  onClick={() => setModalRegistro(true)}
                >
                  Registrar dados especializados
                </button>
              </div>
              {registrosEspecializados === null ? (
                <div className="mt-3">
                  <Spinner />
                </div>
              ) : registrosEspecializados.length > 0 ? (
                <p className="mt-3 text-xs text-slate-500">
                  {registrosEspecializados.length} registro(s) especializado(s)
                  nesta área.
                </p>
              ) : (
                <p className="mt-3 text-xs text-slate-400">
                  Nenhum registro complementar criado.
                </p>
              )}
            </section>
          )}
        </div>
      )}

      {abaAtiva === "casos" && (
        <CasosWorkspace casos={casos} area={cfg.areaCaso} />
      )}

      {abaAtiva === "ferramentas" && (
        <div className="space-y-4">
          {cfg.comparadorBacen && <ComparadorBacen />}
          {cfg.bancarioForense && <BancarioForense />}
          {cfg.liquidacaoTrabalhista && <LiquidacaoTrabalhista />}
          {cfg.tributarioFiscal && <TributarioFiscal />}
          {cfg.previdenciarioSimulacao && <PrevidenciarioSimulacao />}
          {cfg.autosAmbientais && <AmbientalAutos casos={casos ?? []} />}
          {cfg.ambientalEstrategia && <AmbientalEstrategia />}
          {cfg.sociedadesCliente && <SociedadesCliente />}
          {cfg.lgpdRegistros && <LgpdRegistros />}

          {ferramentas.length > 0 ? (
            <div className="grid gap-4 lg:grid-cols-2">
              {ferramentas.map((ferramenta) => (
                <FerramentaWorkspace
                  key={ferramenta.id}
                  ferramenta={ferramenta}
                />
              ))}
            </div>
          ) : (
            !(
              cfg.comparadorBacen ||
              cfg.bancarioForense ||
              cfg.liquidacaoTrabalhista ||
              cfg.tributarioFiscal ||
              cfg.previdenciarioSimulacao ||
              cfg.autosAmbientais ||
              cfg.ambientalEstrategia ||
              cfg.sociedadesCliente ||
              cfg.lgpdRegistros
            ) && (
              <Empty message="Nenhuma ferramenta específica cadastrada para esta área." />
            )
          )}
        </div>
      )}

      {abaAtiva === "analise" && (
        <div className="space-y-4">
          {cfg.analiseDocumento && (
            <AnaliseDocumento
              area={cfg.analiseArea || cfg.areaCaso}
              casos={casos ?? []}
            />
          )}
          {cfg.analiseExtratos && <AnaliseExtratos />}
        </div>
      )}

      {abaAtiva === "referencias" && (
        <div className="space-y-4">
          {subareas.length > 0 && (
            <section className="rounded-2xl border border-black/[0.06] bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]">
              <h3 className="text-sm font-bold text-slate-950 dark:text-white">
                Escopo da área
              </h3>
              <p className="mt-1 text-xs text-slate-500">
                Subáreas para orientação e pesquisa. A classificação do caso
                continua sendo confirmada pelo advogado.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {subareas.map((subarea) => (
                  <span
                    key={subarea}
                    className="rounded-full bg-slate-100 px-3 py-1.5 text-xs text-slate-600 dark:bg-white/[0.06] dark:text-slate-300"
                  >
                    {subarea}
                  </span>
                ))}
              </div>
            </section>
          )}

          {cfg.guiaBancario && <GuiaBancario />}
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
          {cfg.guiaEmpresarial && <GuiaEmpresarial />}
          {cfg.guiaLgpd && <GuiaLgpd />}

          {(cfg.ferramentasExternas?.length ?? 0) > 0 && (
            <section className="rounded-2xl border border-black/[0.06] bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]">
              <h3 className="text-sm font-bold text-slate-950 dark:text-white">
                Fontes e serviços externos
              </h3>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {cfg.ferramentasExternas?.map((item) => (
                  <a
                    key={`${item.nome}:${item.url}`}
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-start justify-between gap-3 rounded-xl border border-black/[0.05] p-3 transition hover:border-ouro/40 dark:border-white/10"
                  >
                    <div>
                      <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                        {item.nome}
                      </p>
                      <p className="mt-1 text-xs leading-5 text-slate-500">
                        {item.descricao}
                      </p>
                    </div>
                    <ExternalLink className="h-4 w-4 shrink-0 text-slate-400" />
                  </a>
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      <Modal
        open={modalRegistro}
        onClose={() => setModalRegistro(false)}
        title={`Registrar dados especializados — ${tituloDoWorkspace(cfg)}`}
        wide
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label className="label">Caso vinculado *</label>
            <select
              className="input"
              value={String(formularioRegistro.case_id ?? "")}
              onChange={(event) =>
                setFormularioRegistro({
                  ...formularioRegistro,
                  case_id: event.target.value,
                })
              }
            >
              <option value="">Selecione o caso…</option>
              {(casos ?? []).map((caso) => (
                <option key={caso.id} value={caso.id}>
                  {caso.numero_interno} — {caso.titulo}
                </option>
              ))}
            </select>
            {!casos?.length && (
              <p className="mt-1 text-xs text-warn-600">
                Primeiro crie um caso nesta área pelo botão “Novo caso”.
              </p>
            )}
          </div>
          {cfg.campos.map((campo) => (
            <div
              key={campo.nome}
              className={campo.col === 2 ? "sm:col-span-2" : ""}
            >
              <label className="label">
                {campo.label}
                {campo.obrigatorio ? " *" : ""}
              </label>
              {campo.tipo === "select" ? (
                <select
                  className="input"
                  value={String(formularioRegistro[campo.nome] ?? "")}
                  onChange={(event) =>
                    setFormularioRegistro({
                      ...formularioRegistro,
                      [campo.nome]: event.target.value,
                    })
                  }
                >
                  <option value="">Selecione…</option>
                  {campo.opcoes?.map((opcao) => (
                    <option key={opcao} value={opcao}>
                      {rotulo(opcao)}
                    </option>
                  ))}
                </select>
              ) : campo.tipo === "textarea" ? (
                <textarea
                  className="input"
                  rows={3}
                  value={String(formularioRegistro[campo.nome] ?? "")}
                  placeholder={campo.placeholder}
                  onChange={(event) =>
                    setFormularioRegistro({
                      ...formularioRegistro,
                      [campo.nome]: event.target.value,
                    })
                  }
                />
              ) : campo.tipo === "checkbox" ? (
                <label className="mt-1 flex items-center gap-2 text-sm text-slate-600">
                  <input
                    type="checkbox"
                    checked={Boolean(formularioRegistro[campo.nome])}
                    onChange={(event) =>
                      setFormularioRegistro({
                        ...formularioRegistro,
                        [campo.nome]: event.target.checked,
                      })
                    }
                  />
                  {campo.ajuda || "Sim"}
                </label>
              ) : (
                <input
                  className="input"
                  type={campo.tipo}
                  step={campo.tipo === "number" ? "0.01" : undefined}
                  value={String(formularioRegistro[campo.nome] ?? "")}
                  placeholder={campo.placeholder}
                  onChange={(event) =>
                    setFormularioRegistro({
                      ...formularioRegistro,
                      [campo.nome]: event.target.value,
                    })
                  }
                />
              )}
              {campo.ajuda && campo.tipo !== "checkbox" && (
                <p className="mt-1 text-xs text-slate-400">{campo.ajuda}</p>
              )}
            </div>
          ))}
        </div>
        <div className="mt-5 flex justify-end">
          <button
            className="btn-primary"
            disabled={salvandoRegistro}
            onClick={registrarEspecializado}
          >
            {salvandoRegistro ? "Salvando…" : "Registrar ficha especializada"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
