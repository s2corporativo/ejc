import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import {
  AlertTriangle,
  BookOpen,
  Briefcase,
  Calculator,
  ExternalLink,
  FileSearch,
  Landmark,
  Receipt,
  Scale,
} from "lucide-react";
import { Empty, PageHeader, Spinner, StatusBadge } from "../components/UI";
import api from "../lib/api";
import type { Case } from "../types";

const STATUS_FECHADOS = new Set(["encerrado", "arquivado"]);

const FONTES_OFICIAIS = [
  {
    nome: "Receita Federal — Serviços",
    esfera: "Federal",
    url: "https://www.gov.br/receitafederal/pt-br/servicos",
  },
  {
    nome: "PGFN — REGULARIZE",
    esfera: "Federal",
    url: "https://www.regularize.pgfn.gov.br/",
  },
  {
    nome: "CARF",
    esfera: "Federal",
    url: "https://www.gov.br/carf/pt-br",
  },
  {
    nome: "SEF/MG",
    esfera: "Minas Gerais",
    url: "https://www.fazenda.mg.gov.br/",
  },
  {
    nome: "SIARE/MG",
    esfera: "Minas Gerais",
    url: "https://www2.fazenda.mg.gov.br/sol/",
  },
  {
    nome: "TRF6",
    esfera: "Justiça Federal — MG",
    url: "https://portal.trf6.jus.br/",
  },
  {
    nome: "Fazenda — Betim",
    esfera: "Municipal",
    url: "https://www.betim.mg.gov.br/portal/secretarias/14/secretaria-municipal-de-fazenda/",
  },
  {
    nome: "Receita Municipal — Contagem",
    esfera: "Municipal",
    url: "https://receita.contagem.mg.gov.br/",
  },
  {
    nome: "Fazenda — Belo Horizonte",
    esfera: "Municipal",
    url: "https://fazenda.pbh.gov.br/",
  },
  {
    nome: "NFS-e Nacional",
    esfera: "Nacional",
    url: "https://www.nfse.gov.br/EmissorNacional/",
  },
] as const;

export function casoTributarioAtivo(caso: Pick<Case, "status">): boolean {
  return !STATUS_FECHADOS.has(caso.status);
}

export function filtrarCasosTributarios(
  casos: Case[],
  clientId?: string | null,
): Case[] {
  return casos.filter(
    (caso) =>
      caso.area === "tributario" &&
      (!clientId || String(caso.client_id) === String(clientId)),
  );
}

export function resumoCarteiraTributaria(casos: Case[]) {
  return {
    total: casos.length,
    ativos: casos.filter(casoTributarioAtivo).length,
    altaPrioridade: casos.filter(
      (caso) => caso.prioridade === "alta" || caso.prioridade === "urgente",
    ).length,
    altoRisco: casos.filter(
      (caso) => caso.risco === "alto" || caso.risco_nivel === "alto",
    ).length,
  };
}

function rotulo(value?: string | null) {
  return (value || "—")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export default function TributarioWorkspace() {
  const [searchParams] = useSearchParams();
  const clientId = searchParams.get("client_id");
  const [casos, setCasos] = useState<Case[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState(false);
  const [truncado, setTruncado] = useState(false);

  useEffect(() => {
    let ativo = true;
    setLoading(true);
    setErro(false);
    setTruncado(false);

    api
      .get("/cases/", { params: { area: "tributario", page_size: 500 } })
      .then((resposta) => {
        if (!ativo) return;
        const data = Array.isArray(resposta.data)
          ? resposta.data
          : Array.isArray(resposta.data?.data)
            ? resposta.data.data
            : [];
        const total = Number(resposta.data?.total);
        setTruncado(Number.isFinite(total) && total > data.length);
        setCasos(filtrarCasosTributarios(data as Case[], clientId));
      })
      .catch(() => {
        if (!ativo) return;
        setCasos([]);
        setTruncado(false);
        setErro(true);
      })
      .finally(() => {
        if (ativo) setLoading(false);
      });

    return () => {
      ativo = false;
    };
  }, [clientId]);

  const resumo = useMemo(() => resumoCarteiraTributaria(casos), [casos]);
  const recentes = useMemo(
    () =>
      [...casos]
        .sort(
          (a, b) =>
            new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
        )
        .slice(0, 8),
    [casos],
  );

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Inteligência Tributária"
        title="Tributário"
        subtitle={
          clientId
            ? "Visão tributária filtrada pelo cliente selecionado."
            : "Carteira tributária, contencioso, créditos potenciais, planejamento e reforma tributária."
        }
        actions={
          <div className="flex flex-wrap gap-2">
            <Link to="/areas-de-atuacao/tributario" className="btn-gold text-sm">
              Abrir núcleo técnico
            </Link>
            <Link to="/entrada" className="btn-secondary text-sm">
              Novo caso
            </Link>
          </div>
        }
      />

      {truncado && (
        <section className="rounded-xl border border-warn-200 bg-warn-50 p-4 text-xs leading-5 text-warn-900">
          <strong>Visão parcial:</strong> existem mais de 500 casos tributários acessíveis para este perfil. Os indicadores abaixo refletem apenas os registros carregados. Use o núcleo técnico/lista geral de Casos para consulta exaustiva.
        </section>
      )}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          {
            label: truncado ? "Casos carregados" : "Casos tributários",
            value: resumo.total,
            icon: Briefcase,
            descricao: truncado
              ? "Amostra limitada ao teto de 500 registros da consulta."
              : "Fonte única: cadastro central de Casos do EJC.",
          },
          {
            label: "Em andamento",
            value: resumo.ativos,
            icon: Receipt,
            descricao: "Casos não encerrados nem arquivados.",
          },
          {
            label: "Alta prioridade",
            value: resumo.altaPrioridade,
            icon: AlertTriangle,
            descricao: "Prioridade alta ou urgente no caso canônico.",
          },
          {
            label: "Alto risco",
            value: resumo.altoRisco,
            icon: Scale,
            descricao: "Classificação de risco registrada no caso.",
          },
        ].map(({ label, value, icon: Icon, descricao }) => (
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
      </section>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {[
          {
            title: "Diagnóstico e contencioso",
            descricao:
              "Autos, prescrição/decadência, parcelamento, Simples e demais ferramentas homologadas.",
            icon: Calculator,
            to: "/areas-de-atuacao/tributario",
          },
          {
            title: "Créditos potenciais",
            descricao:
              "Análise fiscal por XML/NF-e como pré-auditoria, sempre sujeita a validação profissional.",
            icon: FileSearch,
            to: "/areas-de-atuacao/tributario",
          },
          {
            title: "Pesquisa e jurisprudência",
            descricao:
              "Use a pesquisa jurídica canônica, com fontes e contexto do EJC.",
            icon: Landmark,
            to: "/inteligencia",
          },
          {
            title: "Banco de teses",
            descricao:
              "Teses tributárias permanecem no repositório central do escritório, sem duplicação.",
            icon: BookOpen,
            to: "/teses",
          },
        ].map(({ title, descricao, icon: Icon, to }) => (
          <Link
            key={title}
            to={to}
            className="card p-4 transition hover:border-gold-300 hover:bg-gold-50/20"
          >
            <div className="flex items-center gap-2">
              <Icon size={17} className="text-gold-600" />
              <h2 className="font-serif font-semibold text-navy">{title}</h2>
            </div>
            <p className="mt-2 text-xs leading-5 text-slate-500">{descricao}</p>
          </Link>
        ))}
      </section>

      <section className="card p-4">
        <div className="flex items-start gap-3">
          <Landmark size={18} className="mt-0.5 shrink-0 text-gold-600" />
          <div>
            <h2 className="font-serif font-semibold text-navy">Fontes oficiais</h2>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              Atalhos externos verificados. Abrir um portal não significa que exista API pública ou integração automática no EJC. A PGFN Dados Abertos é integração própria já existente; os demais links abaixo são acessos oficiais de consulta/serviço.
            </p>
          </div>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
          {FONTES_OFICIAIS.map((fonte) => (
            <a
              key={fonte.url}
              href={fonte.url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-xl border border-slate-200 p-3 transition hover:border-gold-300 hover:bg-gold-50/20"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-medium text-navy">{fonte.nome}</p>
                  <p className="mt-1 text-[11px] text-slate-400">{fonte.esfera}</p>
                </div>
                <ExternalLink size={14} className="shrink-0 text-slate-400" />
              </div>
            </a>
          ))}
        </div>
      </section>

      <section className="card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
          <div>
            <h2 className="font-serif font-semibold text-navy">
              Carteira tributária recente
            </h2>
            <p className="text-xs text-slate-500">
              O painel apenas consolida casos já existentes; não cria registro tributário paralelo.
            </p>
          </div>
          <Link to="/areas-de-atuacao/tributario" className="btn-secondary text-xs">
            Ver núcleo completo
          </Link>
        </div>

        {loading ? (
          <div className="p-6">
            <Spinner />
          </div>
        ) : erro ? (
          <div className="p-6">
            <Empty message="Não foi possível carregar a carteira tributária. O cadastro central de Casos permanece disponível." />
          </div>
        ) : recentes.length === 0 ? (
          <div className="p-6">
            <Empty message="Nenhum caso tributário encontrado para esta visão." />
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {recentes.map((caso) => (
              <div key={caso.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <Link to={`/casos/${caso.id}`} className="min-w-[220px] flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium text-navy">{caso.titulo}</p>
                    <StatusBadge value={caso.status} />
                  </div>
                  <p className="mt-1 text-xs text-slate-400">
                    {caso.numero_interno || "Sem número interno"} · {rotulo(caso.fase)} · Prioridade {rotulo(caso.prioridade)}
                  </p>
                </Link>
                <div className="flex gap-2">
                  <Link to={`/clientes/${caso.client_id}?tab=casos`} className="btn-secondary text-xs">
                    Cliente
                  </Link>
                  <Link to={`/casos/${caso.id}`} className="btn-secondary text-xs">
                    Abrir caso
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-xl border border-warn-200 bg-warn-50 p-4 text-xs leading-5 text-warn-900">
        <strong>Gate profissional:</strong> indicação de crédito, decadência, prescrição, prazo, regime ou impacto da reforma tributária é apoio técnico. Nenhum valor ou tese deve ser tratado como recuperável, devido ou definitivo sem conferência documental, normativa e revisão humana.
      </section>
    </div>
  );
}
