import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import {
  BookOpen,
  Brain,
  Briefcase,
  Building2,
  Car,
  Folder,
  FolderOpen,
  HardHat,
  Landmark,
  Leaf,
  Lock,
  Plus,
  Receipt,
  Scale,
  Users,
  Wrench,
  Banknote,
} from "lucide-react";
import api from "../../lib/api";
import type { Case } from "../../types";
import { Empty, PageHeader, Spinner, StatusBadge } from "../../components/UI";
import { useAuth } from "../../stores/auth";
import { ROLES } from "../../config/moduleRegistry";
import type { RamoConfig } from "./ramosConfig";
import { configWorkspaceDaArea } from "./areasWorkspace";
import {
  abasDoWorkspace,
  areasDoWorkspace,
  possuiRegistroEspecializado,
  relacoesDoWorkspace,
  subtituloDoWorkspace,
  tituloDoWorkspace,
  type WorkspaceTabId,
} from "./ramoWorkspace";
import RamoFerramenta from "./RamoFerramenta";
import { AnaliseDocumentoArea, ComparadorBacen } from "./RamoAnalise";
import FichaEspecializada from "./FichaEspecializada";
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

const ICONES: Record<string, typeof Scale> = {
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

function rotulo(v: string) {
  return v.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function carregarListaResposta(data: any): any[] {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.data)) return data.data;
  return [];
}

function ResumoWorkspace({
  cfg,
  casos,
  registros,
}: {
  cfg: RamoConfig;
  casos: Case[];
  registros: any[] | null;
}) {
  const relacoes = relacoesDoWorkspace(cfg);
  const ferramentasUnicas =
    cfg.ferramentas.length +
    Number(Boolean(cfg.comparadorBacen)) +
    Number(Boolean(cfg.liquidacaoTrabalhista)) +
    Number(Boolean(cfg.tributarioFiscal)) +
    Number(Boolean(cfg.previdenciarioSimulacao)) +
    Number(Boolean(cfg.autosAmbientais)) +
    Number(Boolean(cfg.ambientalEstrategia)) +
    Number(Boolean(cfg.sociedadesCliente)) +
    Number(Boolean(cfg.lgpdRegistros));
  const cards = [
    {
      label: "Casos canônicos",
      value: casos.length,
      descricao: "Fonte única: cadastro central de Casos do EJC.",
      icon: Briefcase,
    },
    {
      label: "Ferramentas",
      value: ferramentasUnicas,
      descricao:
        "Calculadoras e rotinas operacionais disponíveis neste núcleo.",
      icon: Wrench,
    },
    {
      label: "Especialidades relacionadas",
      value: relacoes.length,
      descricao: "Relação visual; nenhuma reclassificação automática.",
      icon: Scale,
    },
    {
      label: "Registros especializados",
      value: registros?.length ?? 0,
      descricao: cfg.externo
        ? "Este núcleo usa apenas registros canônicos do EJC."
        : "Dados auxiliares vinculados a um caso canônico.",
      icon: FolderOpen,
    },
  ];

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map(({ label, value, descricao, icon: Icon }) => (
        <div key={label} className="card p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                {label}
              </p>
              <p className="mt-1 text-2xl font-semibold text-navy">{value}</p>
            </div>
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-slate-50 text-slate-600">
              <Icon size={17} />
            </div>
          </div>
          <p className="mt-2 text-xs leading-5 text-slate-500">{descricao}</p>
        </div>
      ))}
    </div>
  );
}

function RelacoesVisuais({ cfg }: { cfg: RamoConfig }) {
  const relacoes = relacoesDoWorkspace(cfg);
  if (relacoes.length === 0) return null;
  return (
    <section className="card p-4">
      <div className="flex items-center gap-2">
        <Scale size={16} className="text-gold-600" />
        <h2 className="font-serif font-semibold text-navy">
          Especialidades relacionadas
        </h2>
      </div>
      <p className="mt-1 text-xs leading-5 text-slate-500">
        Esta organização é apenas de navegação. Cada classificação continua com
        seu próprio slug e significado jurídico no cadastro do caso.
      </p>
      <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {relacoes.map((relacao) => {
          const inner = (
            <>
              <p className="text-sm font-semibold text-navy">{relacao.label}</p>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                {relacao.descricao}
              </p>
            </>
          );
          return relacao.workspace ? (
            <Link
              key={relacao.slug}
              to={relacao.workspace}
              className="rounded-xl border border-slate-200 p-3 transition hover:border-gold-300 hover:bg-gold-50/30"
            >
              {inner}
            </Link>
          ) : (
            <div
              key={relacao.slug}
              className="rounded-xl border border-slate-200 p-3"
            >
              {inner}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function RegistrosEspecializados({
  cfg,
  registros,
}: {
  cfg: RamoConfig;
  registros: any[] | null;
}) {
  if (cfg.externo) return null;
  if (registros === null) {
    return (
      <section className="card p-4">
        <Spinner />
      </section>
    );
  }
  if (registros.length === 0) return null;
  return (
    <section className="card p-4">
      <div className="flex items-center gap-2">
        <FolderOpen size={16} className="text-gold-600" />
        <h2 className="font-serif font-semibold text-navy">
          Registros especializados vinculados
        </h2>
      </div>
      <p className="mt-1 text-xs leading-5 text-slate-500">
        Estes registros são fichas auxiliares do núcleo. Eles não são casos
        independentes e não substituem o cadastro central de Casos.
      </p>
      <div className="mt-3 space-y-2">
        {registros.slice(0, 8).map((item) => (
          <div
            key={item.id}
            className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-100 p-3"
          >
            <div className="min-w-[180px] flex-1">
              <p className="text-sm font-medium text-navy">
                {rotulo(
                  String(item[cfg.campoTitulo] || "Registro especializado"),
                )}
              </p>
              <p className="text-xs text-slate-400">
                {item.instituicao_financeira ||
                  item.orgao_autuador ||
                  item.cnpj_empresa ||
                  item.cargo ||
                  item.competencia ||
                  "Vinculado ao caso canônico"}
              </p>
            </div>
            {item[cfg.campoStatus] && (
              <StatusBadge value={String(item[cfg.campoStatus])} />
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function CasosDoRamo({
  casos,
  loading,
  erro,
}: {
  casos: Case[];
  loading: boolean;
  erro: boolean;
}) {
  if (loading) return <Spinner />;
  if (erro && casos.length === 0) {
    return (
      <Empty message="Não foi possível carregar os casos deste núcleo. Tente novamente pela lista geral de Casos." />
    );
  }
  if (casos.length === 0) {
    return (
      <Empty message="Nenhum caso canônico registrado nesta área. Use Novo caso para abrir o cadastro central do EJC." />
    );
  }
  return (
    <div className="space-y-2">
      {casos.map((caso) => (
        <Link
          key={caso.id}
          to={`/casos/${caso.id}`}
          className="card flex flex-wrap items-center gap-4 p-4 transition hover:border-gold-300"
        >
          <div className="min-w-[220px] flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-medium text-navy">{caso.titulo}</p>
              <StatusBadge value={caso.status} />
            </div>
            <p className="mt-1 text-xs text-slate-400">
              {caso.numero_interno || "Sem número interno"} ·{" "}
              {rotulo(caso.area)}
              {caso.fase ? ` · ${rotulo(caso.fase)}` : ""}
            </p>
          </div>
          <div className="text-xs text-slate-500">
            Prioridade: {rotulo(caso.prioridade || "media")}
          </div>
        </Link>
      ))}
    </div>
  );
}

function FerramentasDoRamo({ cfg, casos }: { cfg: RamoConfig; casos: Case[] }) {
  const ferramentas = cfg.ferramentas;
  const grupos = new Map<string, typeof ferramentas>();
  for (const ferramenta of ferramentas) {
    const grupo = ferramenta.grupo || "Ferramentas do núcleo";
    grupos.set(grupo, [...(grupos.get(grupo) ?? []), ferramenta]);
  }

  return (
    <div className="space-y-5">
      {cfg.comparadorBacen && <ComparadorBacen />}
      {cfg.liquidacaoTrabalhista && <LiquidacaoTrabalhista />}
      {cfg.tributarioFiscal && <TributarioFiscal />}
      {cfg.previdenciarioSimulacao && <PrevidenciarioSimulacao />}
      {cfg.autosAmbientais && <AmbientalAutos casos={casos} />}
      {cfg.ambientalEstrategia && <AmbientalEstrategia />}
      {cfg.sociedadesCliente && <SociedadesCliente />}
      {cfg.lgpdRegistros && <LgpdRegistros />}

      {[...grupos.entries()].map(([grupo, itens]) => (
        <section key={grupo} className="space-y-3">
          <div>
            <h2 className="font-serif font-semibold text-navy">{grupo}</h2>
            <p className="text-xs text-slate-500">
              Resultados são apoio técnico e permanecem sujeitos aos gates de
              homologação e revisão já existentes.
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {itens.map((f) => (
              <RamoFerramenta key={`${f.endpoint}:${f.id}`} f={f} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function AnalisesDoRamo({ cfg, casos }: { cfg: RamoConfig; casos: Case[] }) {
  return (
    <div className="space-y-4">
      <div className="card flex items-start gap-3 p-4">
        <Brain size={18} className="mt-0.5 shrink-0 text-gold-600" />
        <div>
          <h2 className="font-serif font-semibold text-navy">IA & Análise</h2>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            O conteúdo produzido aqui é apoio ao advogado. Nenhuma análise ou
            minuta é promovida automaticamente a decisão jurídica final.
          </p>
        </div>
      </div>
      {cfg.analiseDocumento && (
        <AnaliseDocumentoArea
          area={cfg.analiseArea || cfg.areaCaso}
          casos={casos}
        />
      )}
      {cfg.analiseExtratos && <AnaliseExtratos />}
      {cfg.bancarioForense && <BancarioForense />}
    </div>
  );
}

function ReferenciasDoRamo({ cfg }: { cfg: RamoConfig }) {
  const linksExternos = [
    ...new Map(
      (cfg.ferramentasExternas ?? []).map((item) => [item.url, item]),
    ).values(),
  ];

  return (
    <div className="space-y-4">
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

      {(cfg.subareas?.length ?? 0) > 0 && (
        <section className="card p-4">
          <div className="flex items-center gap-2">
            <BookOpen size={16} className="text-gold-600" />
            <h2 className="font-serif font-semibold text-navy">
              Assuntos e subáreas
            </h2>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {cfg.subareas?.map((subarea) => (
              <span
                key={subarea}
                className="rounded-full bg-slate-900/[0.05] px-2.5 py-1 text-xs text-slate-600 dark:bg-white/[0.07] dark:text-slate-300"
              >
                {subarea}
              </span>
            ))}
          </div>
        </section>
      )}

      {linksExternos.length > 0 && (
        <section className="card p-4">
          <h2 className="font-serif font-semibold text-navy">
            Consultas públicas externas
          </h2>
          <p className="mt-1 text-xs text-slate-500">
            Atalhos contextuais. O EJC não considera a consulta externa como
            validação jurídica automática.
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {linksExternos.map((fe) => (
              <a
                key={fe.url}
                href={fe.url}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-xl border border-slate-200 p-3 transition hover:border-gold-300 hover:bg-gold-50/30"
              >
                <p className="text-sm font-medium text-navy">{fe.nome} ↗</p>
                <p className="mt-1 text-xs text-slate-400">{fe.descricao}</p>
              </a>
            ))}
          </div>
        </section>
      )}

      <section className="card p-4">
        <h2 className="font-serif font-semibold text-navy">Peças e modelos</h2>
        <p className="mt-1 text-xs leading-5 text-slate-500">
          Peças continuam no repositório canônico do EJC para manter versão,
          revisão humana, vínculo ao caso e trilha de auditoria em um só lugar.
        </p>
        <Link to="/pecas" className="btn-secondary mt-3 inline-flex text-sm">
          Abrir Peças
        </Link>
      </section>
    </div>
  );
}

export default function RamoBase() {
  const { slug } = useParams<{ slug: string }>();
  const cfg: RamoConfig | undefined = slug
    ? configWorkspaceDaArea(slug)
    : undefined;
  const role = useAuth((state) => state.user?.role);
  const podeAcessarArea = Boolean(
    role && (ROLES.juridico as readonly string[]).includes(role),
  );
  const podeCriarCaso = Boolean(
    podeAcessarArea &&
      role &&
      (ROLES.clientes as readonly string[]).includes(role),
  );
  const [aba, setAba] = useState<WorkspaceTabId>("visao");
  const [casos, setCasos] = useState<Case[]>([]);
  const [casosLoading, setCasosLoading] = useState(true);
  const [casosErro, setCasosErro] = useState(false);
  const [registros, setRegistros] = useState<any[] | null>(null);

  const Icone = useMemo(() => {
    if (!cfg) return Folder;
    return ICONES[cfg.icone] || Folder;
  }, [cfg]);
  const abas = useMemo(() => (cfg ? abasDoWorkspace(cfg) : []), [cfg]);

  const recarregarRegistros = () => {
    if (!cfg || !podeAcessarArea || !possuiRegistroEspecializado(cfg)) return;
    setRegistros(null);
    api
      .get(cfg.endpoint)
      .then((resposta) => setRegistros(carregarListaResposta(resposta.data)))
      .catch(() => setRegistros([]));
  };

  useEffect(() => {
    if (!cfg || !podeAcessarArea) return;
    let ativo = true;
    setAba("visao");
    setCasos([]);
    setCasosLoading(true);
    setCasosErro(false);
    setRegistros(possuiRegistroEspecializado(cfg) ? null : []);

    const areas = areasDoWorkspace(cfg);
    Promise.all(
      areas.map(async (area) => {
        try {
          const resposta = await api.get("/cases/", {
            params: { area, page_size: 100 },
          });
          return {
            ok: true,
            casos: carregarListaResposta(resposta.data) as Case[],
          };
        } catch {
          return { ok: false, casos: [] as Case[] };
        }
      }),
    ).then((resultados) => {
      if (!ativo) return;
      const porId = new Map<string, Case>();
      resultados
        .flatMap((item) => item.casos)
        .forEach((caso) => porId.set(caso.id, caso));
      setCasos(
        [...porId.values()].sort(
          (a, b) =>
            new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
        ),
      );
      setCasosErro(
        resultados.length > 0 && resultados.every((item) => !item.ok),
      );
      setCasosLoading(false);
    });

    if (possuiRegistroEspecializado(cfg)) {
      api
        .get(cfg.endpoint)
        .then((resposta) => {
          if (ativo) setRegistros(carregarListaResposta(resposta.data));
        })
        .catch(() => {
          if (ativo) setRegistros([]);
        });
    }

    return () => {
      ativo = false;
    };
  }, [cfg, podeAcessarArea]);

  if (!cfg) return <Empty message="Área de atuação não encontrada" />;
  if (!podeAcessarArea) {
    return <Empty message="Acesso restrito à equipe jurídica." />;
  }

  const relacoes = relacoesDoWorkspace(cfg);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Centro de Especialidades Jurídicas"
        title={tituloDoWorkspace(cfg)}
        subtitle={subtituloDoWorkspace(cfg)}
        actions={
          <div className="flex flex-wrap gap-2">
            <Link to="/areas-de-atuacao" className="btn-secondary text-sm">
              Todas as áreas
            </Link>
            {podeCriarCaso && (
              <Link
                to="/casos/novo"
                className="btn-gold flex items-center gap-1 text-sm"
              >
                <Plus size={16} /> Novo caso
              </Link>
            )}
          </div>
        }
      />

      <div className="rounded-2xl border border-slate-200 bg-white p-2 shadow-sm dark:border-white/10 dark:bg-white/[0.03]">
        <div
          className="flex gap-1 overflow-x-auto"
          role="tablist"
          aria-label="Navegação do núcleo jurídico"
        >
          {abas.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={aba === item.id}
              onClick={() => setAba(item.id)}
              className={`whitespace-nowrap rounded-xl px-3 py-2 text-sm font-medium transition ${
                aba === item.id
                  ? "bg-slate-900 text-white dark:bg-white dark:text-slate-950"
                  : "text-slate-500 hover:bg-slate-50 hover:text-slate-900 dark:hover:bg-white/[0.06] dark:hover:text-white"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {aba === "visao" && (
        <div className="space-y-4">
          <ResumoWorkspace cfg={cfg} casos={casos} registros={registros} />
          <section className="card p-4">
            <div className="flex items-start gap-3">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-gold-50 text-gold-700">
                <Icone size={18} />
              </div>
              <div>
                <h2 className="font-serif font-semibold text-navy">
                  Como usar este núcleo
                </h2>
                <p className="mt-1 text-sm leading-6 text-slate-600">
                  O caso é sempre o registro principal. As abas disponíveis
                  neste workspace mostram somente capacidades efetivamente
                  implementadas para a área, além do acesso central a casos,
                  peças e referências.
                </p>
                {cfg.externo && (
                  <p className="mt-2 text-xs text-slate-500">
                    Este núcleo não possui tabela paralela própria: a fonte de
                    verdade é exclusivamente o cadastro canônico de Casos.
                  </p>
                )}
              </div>
            </div>
          </section>
          {relacoes.length > 0 && <RelacoesVisuais cfg={cfg} />}
          <FichaEspecializada
            cfg={cfg}
            casos={casos}
            onSaved={recarregarRegistros}
          />
          <RegistrosEspecializados cfg={cfg} registros={registros} />
        </div>
      )}

      {aba === "casos" && (
        <section className="space-y-3">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="font-serif text-lg font-semibold text-navy">
                Casos desta área
              </h2>
              <p className="text-xs text-slate-500">
                Lista canônica por {areasDoWorkspace(cfg).join(" + ")} —
                registros legados são unidos apenas para leitura, sem
                reclassificação.
              </p>
            </div>
            <Link to="/casos" className="btn-secondary text-sm">
              Abrir lista geral
            </Link>
          </div>
          <CasosDoRamo casos={casos} loading={casosLoading} erro={casosErro} />
        </section>
      )}

      {aba === "ferramentas" && <FerramentasDoRamo cfg={cfg} casos={casos} />}
      {aba === "analise" && <AnalisesDoRamo cfg={cfg} casos={casos} />}
      {aba === "referencias" && <ReferenciasDoRamo cfg={cfg} />}
    </div>
  );
}
