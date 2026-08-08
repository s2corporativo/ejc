// ── Radar — uma porta, dois modos (Onda 2 da refatoração) ────────────────────
//
// O EJC tinha duas telas sobre a MESMA matéria: "Radar de Compliance"
// (`/compliance/radar`) e "Radar Regulatório" (`/radar-regulatorio`). Não eram
// assuntos diferentes — o feed de compliance já consolida Diário Oficial,
// monitoramento regulatório e autos ambientais, e o regulatório é o DIGEST
// agregado da mesma matéria-prima. Duas entradas de menu para a mesma pergunta
// ("o que apareceu que me afeta?") é atrito, não escolha.
//
// Aqui viram DOIS MODOS de uma tela só:
//   • Feed    — itens priorizados por risco (crítico → baixo), com filtros.
//   • Digest  — o mesmo material agregado por fonte e palavra-chave no período.
//
// Os dois componentes originais foram PRESERVADOS e são renderizados embutidos
// (sem o cabeçalho próprio). Nada de reescrever 429 linhas já testadas só para
// unificar a porta de entrada — o risco não pagaria o ganho.
import { useSearchParams } from "react-router";
import { Bell, ShieldAlert } from "lucide-react";

import { PageHeader } from "../components/UI";
import RadarCompliance from "./RadarCompliance";
import RadarRegulatorio from "./RadarRegulatorio";

const MODOS = [
  {
    id: "feed",
    label: "Feed por risco",
    icon: ShieldAlert,
    descricao:
      "Itens priorizados por risco (crítico → baixo), com filtro por fonte e data.",
  },
  {
    id: "digest",
    label: "Digest do período",
    icon: Bell,
    descricao:
      "O mesmo material agregado por fonte e palavra-chave na janela escolhida.",
  },
] as const;

type ModoId = (typeof MODOS)[number]["id"];

const MODO_PADRAO: ModoId = "feed";

function ehModo(valor: string | null): valor is ModoId {
  return MODOS.some((m) => m.id === valor);
}

export default function Radar() {
  const [searchParams, setSearchParams] = useSearchParams();
  const bruto = searchParams.get("modo");
  // Modo desconhecido cai no padrão em vez de renderizar tela vazia — o link
  // legado `/compliance/radar` chega aqui sem `?modo=`.
  const modo: ModoId = ehModo(bruto) ? bruto : MODO_PADRAO;

  const trocarModo = (novo: ModoId) => {
    const proximos = new URLSearchParams(searchParams);
    proximos.set("modo", novo);
    // replace: alternar modo não deve encher o histórico do navegador.
    setSearchParams(proximos, { replace: true });
  };

  const ativo = MODOS.find((m) => m.id === modo) ?? MODOS[0];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Inteligência"
        title="Radar"
        subtitle="O que apareceu no Diário Oficial, no monitoramento regulatório e nos autos ambientais que afeta o escritório."
      />

      <div
        role="tablist"
        aria-label="Modo de visualização do radar"
        className="flex flex-wrap gap-2"
      >
        {MODOS.map((m) => {
          const Icone = m.icon;
          const selecionado = m.id === modo;
          return (
            <button
              key={m.id}
              type="button"
              role="tab"
              aria-selected={selecionado}
              onClick={() => trocarModo(m.id)}
              className={`flex items-center gap-2 rounded-xl border px-4 py-2 text-sm font-medium transition-colors ${
                selecionado
                  ? "border-bronze bg-bronze-50 text-bronze-deep"
                  : "border-slate-200 text-slate-600 hover:border-bronze-pale hover:text-bronze-deep"
              }`}
            >
              <Icone className="h-4 w-4" />
              {m.label}
            </button>
          );
        })}
      </div>

      <p className="text-sm text-slate-500">{ativo.descricao}</p>

      {modo === "feed" ? (
        <RadarCompliance embutido />
      ) : (
        <RadarRegulatorio embutido />
      )}
    </div>
  );
}
