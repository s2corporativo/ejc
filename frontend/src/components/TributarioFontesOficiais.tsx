import { ExternalLink, Landmark, ShieldAlert } from "lucide-react";
import {
  FONTES_TRIBUTARIAS_OFICIAIS,
  type FonteTributariaOficial,
  type StatusFonteTributaria,
  type TipoFonteTributaria,
} from "../lib/tributarioFontesOficiais";

const TIPO_LABEL: Record<TipoFonteTributaria, string> = {
  portal: "Portal oficial",
  servico_autenticado: "Serviço autenticado",
  legislacao: "Legislação / contencioso",
  nfse: "NFS-e",
  dados_abertos: "Dados abertos",
  tribunal: "Tribunal",
};

const STATUS_LABEL: Record<StatusFonteTributaria, string> = {
  verificada: "Verificada",
  integracao_ejc: "Integração EJC",
  parcial: "Verificação parcial",
};

function FonteCard({ fonte }: { fonte: FonteTributariaOficial }) {
  const conteudo = (
    <>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-navy">{fonte.nome}</p>
          <p className="mt-1 text-[11px] text-slate-400">
            {fonte.municipio || fonte.esfera} · {TIPO_LABEL[fonte.tipo]}
          </p>
        </div>
        {fonte.url ? (
          <ExternalLink size={14} className="shrink-0 text-slate-400" />
        ) : (
          <ShieldAlert size={14} className="shrink-0 text-warn-600" />
        )}
      </div>
      <p className="mt-2 text-[11px] leading-4 text-slate-500">
        {fonte.observacao}
      </p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <span className="rounded-full border border-slate-200 px-2 py-0.5 text-[10px] text-slate-500">
          {STATUS_LABEL[fonte.status]}
        </span>
        <span className="rounded-full border border-slate-200 px-2 py-0.5 text-[10px] text-slate-500">
          {fonte.apiPublica
            ? "API/dados públicos verificados"
            : "Não classificada como API pública"}
        </span>
      </div>
    </>
  );

  const classe =
    "rounded-xl border p-3 transition " +
    (fonte.status === "parcial"
      ? "border-warn-200 bg-warn-50/40"
      : "border-slate-200 hover:border-gold-300 hover:bg-gold-50/20");

  if (!fonte.url) {
    return (
      <div
        className={classe}
        title="Acesso externo não habilitado até nova verificação"
      >
        {conteudo}
      </div>
    );
  }

  return (
    <a
      href={fonte.url}
      target="_blank"
      rel="noopener noreferrer"
      className={classe}
    >
      {conteudo}
    </a>
  );
}

export default function TributarioFontesOficiais() {
  const gerais = FONTES_TRIBUTARIAS_OFICIAIS.filter(
    (fonte) => fonte.esfera !== "Municipal",
  );
  const municipais = FONTES_TRIBUTARIAS_OFICIAIS.filter(
    (fonte) => fonte.esfera === "Municipal",
  );

  return (
    <section className="card p-4">
      <div className="flex items-start gap-3">
        <Landmark size={18} className="mt-0.5 shrink-0 text-gold-600" />
        <div>
          <h2 className="font-serif font-semibold text-navy">
            Fontes oficiais
          </h2>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            Catálogo verificado em 06/09/2026. Portal, DTE, NFS-e ou sistema
            autenticado não é tratado como API pública. Integração automática só
            é indicada quando existe contrato técnico verificável e governança
            própria no EJC.
          </p>
        </div>
      </div>

      <h3 className="mt-4 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        Federal, estadual, nacional e judicial
      </h3>
      <div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {gerais.map((fonte) => (
          <FonteCard key={fonte.id} fonte={fonte} />
        ))}
      </div>

      <h3 className="mt-5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        Municípios prioritários
      </h3>
      <div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {municipais.map((fonte) => (
          <FonteCard key={fonte.id} fonte={fonte} />
        ))}
      </div>

      <p className="mt-3 text-[11px] leading-4 text-slate-500">
        São Joaquim de Bicas permanece sem atalho operacional porque a fonte
        municipal atual não foi localizada com segurança. O EJC registra a
        existência oficial da área do contribuinte, mas mantém automação e link
        desabilitados até nova validação.
      </p>
    </section>
  );
}
