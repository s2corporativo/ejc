// ── Ficha viva da tese ────────────────────────────────────────────────────────
// Superfície do §5 do Legal Drafting 2.0 sobre a ficha CANÔNICA do Banco de
// Teses. Mostra as três coisas que a extensão do backend passou a guardar e que
// nenhuma tela expunha:
//
//   1. CONFIANÇA MEDIDA — e não `taxa_sucesso` crua. Uma ficha 1-de-1 mostraria
//      "100% de êxito" na listagem: número verdadeiro, conclusão falsa, e é por
//      ele que um advogado escolhe a tese da peça. O backend rotula a amostra;
//      aqui a UI mostra o rótulo com o mesmo peso visual do número.
//   2. LASTRO — quantos elementos da ficha têm fonte REAL e verificada. Sem
//      isso, uma ficha com 12 fontes não verificadas e outra com 2 verificadas
//      parecem igualmente sólidas.
//   3. HISTÓRICO — o que mudou na ficha, quando e por quê. É o que permite
//      explicar em outubro a peça protocolada em março.
//
// Carga preguiçosa: só busca quando a tese é selecionada, e cada painel falha
// isoladamente — o Banco de Teses não pode quebrar porque o histórico não veio.
import { useEffect, useState } from "react";
import { BookMarked, History, ShieldCheck, TriangleAlert } from "lucide-react";
import api from "../lib/api";
import { Badge, Card, Empty, Spinner } from "../components/UI";

type Confianca = {
  rotulo: "alta" | "media" | "baixa" | "amostra_insuficiente";
  taxa_sucesso: number | null;
  casos_decididos: number;
  vezes_venceu: number;
  vezes_perdeu: number;
  amostra_minima: number;
  explicacao: string;
  revisao?: {
    precisa_revisao: boolean;
    gatilho_largo: boolean;
    total_overrides: number;
    por_motivo: Record<string, number>;
    recomendacoes: string[];
  };
};

type Cobertura = {
  total: number;
  verificadas: number;
  nao_verificadas: number;
  elementos_cobertos: string[];
  elementos_sem_fonte: string[];
};

type Fonte = {
  id: string;
  elemento: string;
  referencia: string;
  trecho: string;
  fonte_url?: string | null;
  status_verificacao: string;
};

type Versao = {
  id: string;
  versao: number;
  resumo_mudanca?: string | null;
  criado_em?: string | null;
  mudou?: Record<string, { de: unknown; para: unknown }> | null;
};

const ROTULO_CONFIANCA: Record<Confianca["rotulo"], { texto: string; tone: "green" | "amber" | "red" | "slate" }> = {
  alta: { texto: "Confiança alta", tone: "green" },
  media: { texto: "Confiança média", tone: "amber" },
  baixa: { texto: "Confiança baixa", tone: "red" },
  amostra_insuficiente: { texto: "Amostra insuficiente", tone: "slate" },
};

function dataCurta(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("pt-BR");
}

export default function FichaVivaPanel({ teseId }: { teseId: string }) {
  const [confianca, setConfianca] = useState<Confianca | null>(null);
  const [cobertura, setCobertura] = useState<Cobertura | null>(null);
  const [fontes, setFontes] = useState<Fonte[]>([]);
  const [versoes, setVersoes] = useState<Versao[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [falhou, setFalhou] = useState(false);

  useEffect(() => {
    let ativo = true;
    setCarregando(true);
    setFalhou(false);
    Promise.allSettled([
      api.get<Confianca>(`/teses/${teseId}/confianca`),
      api.get<{ cobertura: Cobertura; fontes: Fonte[] }>(`/teses/${teseId}/fontes`),
      api.get<{ versoes: Versao[] }>(`/teses/${teseId}/versoes`, { params: { limite: 10 } }),
    ]).then((r) => {
      if (!ativo) return;
      // `allSettled` de propósito: o histórico não vir não pode esconder a
      // confiança, que é o dado que muda a decisão do advogado.
      setConfianca(r[0].status === "fulfilled" ? r[0].value.data : null);
      setCobertura(r[1].status === "fulfilled" ? r[1].value.data.cobertura : null);
      setFontes(r[1].status === "fulfilled" ? r[1].value.data.fontes : []);
      setVersoes(r[2].status === "fulfilled" ? (r[2].value.data.versoes ?? []) : []);
      setFalhou(r.every((x) => x.status === "rejected"));
      setCarregando(false);
    });
    return () => {
      ativo = false;
    };
  }, [teseId]);

  if (carregando) {
    return (
      <Card>
        <Spinner />
      </Card>
    );
  }

  if (falhou) {
    return (
      <Card>
        <Empty
          titulo="Ficha viva indisponível"
          descricao="Não foi possível carregar histórico, fontes e confiança desta tese."
        />
      </Card>
    );
  }

  const rot = confianca ? ROTULO_CONFIANCA[confianca.rotulo] : null;

  return (
    <Card>
      <div className="mb-3 flex items-center gap-2">
        <BookMarked className="h-4 w-4 text-bronze" />
        <p className="eyebrow">Ficha viva</p>
      </div>

      {/* ── Confiança MEDIDA ─────────────────────────────────────────────── */}
      {confianca && rot && (
        <div className="mb-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={rot.tone}>{rot.texto}</Badge>
            {confianca.taxa_sucesso !== null && (
              <span className="text-sm font-medium text-navy-900">
                {Math.round(confianca.taxa_sucesso * 100)}% de êxito
              </span>
            )}
            <span className="text-[11px] text-slate-500">
              {confianca.explicacao}
            </span>
          </div>

          {confianca.rotulo === "amostra_insuficiente" &&
            confianca.casos_decididos > 0 && (
              <p className="mt-1.5 text-[11px] text-slate-500">
                A taxa acima é verdadeira, mas {confianca.casos_decididos} caso(s)
                decidido(s) não sustentam conclusão sobre a ficha — o piso é{" "}
                {confianca.amostra_minima}.
              </p>
            )}

          {confianca.revisao?.recomendacoes?.length ? (
            <ul className="mt-2 space-y-1 rounded border border-orange-200 bg-orange-50/60 p-2">
              {confianca.revisao.recomendacoes.map((r) => (
                <li
                  key={r}
                  className="flex items-start gap-1.5 text-[11px] text-orange-800"
                >
                  <TriangleAlert className="mt-0.5 h-3 w-3 shrink-0" />
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      )}

      {/* ── Lastro ───────────────────────────────────────────────────────── */}
      {cobertura && (
        <div className="mb-4 border-t border-bronze-pale/50 pt-3">
          <div className="mb-2 flex items-center gap-2">
            <ShieldCheck className="h-3.5 w-3.5 text-bronze" />
            <p className="eyebrow">Lastro das afirmações</p>
            <Badge tone={cobertura.verificadas > 0 ? "green" : "slate"}>
              {cobertura.verificadas}/{cobertura.total} verificada(s)
            </Badge>
          </div>

          {cobertura.total === 0 ? (
            <p className="text-[11px] text-slate-500">
              Nenhum elemento desta ficha tem fonte registrada — fundamentação e
              jurisprudência são texto livre, sem verificação.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {fontes.slice(0, 6).map((f) => (
                <li key={f.id} className="text-[11px]">
                  <span className="flex flex-wrap items-center gap-1.5">
                    <Badge
                      tone={f.status_verificacao === "verificada" ? "green" : "slate"}
                    >
                      {f.elemento}
                    </Badge>
                    {f.fonte_url ? (
                      <a
                        href={f.fonte_url}
                        target="_blank"
                        rel="noreferrer"
                        className="font-medium text-navy-900 hover:text-bronze hover:underline"
                      >
                        {f.referencia}
                      </a>
                    ) : (
                      <span className="font-medium text-navy-900">
                        {f.referencia}
                      </span>
                    )}
                  </span>
                  <span className="mt-0.5 block truncate text-slate-500">
                    {f.trecho}
                  </span>
                </li>
              ))}
              {fontes.length > 6 && (
                <li className="text-[11px] text-slate-400">
                  +{fontes.length - 6} outra(s) fonte(s)
                </li>
              )}
            </ul>
          )}

          {cobertura.elementos_sem_fonte.length > 0 && (
            <p className="mt-2 text-[11px] text-slate-500">
              Sem fonte: {cobertura.elementos_sem_fonte.join(", ")}
            </p>
          )}
        </div>
      )}

      {/* ── Histórico ────────────────────────────────────────────────────── */}
      <div className="border-t border-bronze-pale/50 pt-3">
        <div className="mb-2 flex items-center gap-2">
          <History className="h-3.5 w-3.5 text-bronze" />
          <p className="eyebrow">O que mudou nesta ficha</p>
        </div>

        {versoes.length === 0 ? (
          <p className="text-[11px] text-slate-500">
            Sem histórico registrado — esta ficha não foi alterada desde que o
            versionamento passou a valer.
          </p>
        ) : (
          <ul className="space-y-2">
            {versoes.map((v) => (
              <li key={v.id} className="text-[11px]">
                <span className="flex flex-wrap items-center gap-1.5">
                  <Badge tone="slate">v{v.versao}</Badge>
                  <span className="text-slate-500">{dataCurta(v.criado_em)}</span>
                  {v.resumo_mudanca && (
                    <span className="text-navy-900">{v.resumo_mudanca}</span>
                  )}
                </span>
                {v.mudou && Object.keys(v.mudou).length > 0 && (
                  <span className="mt-0.5 block text-slate-500">
                    Campos alterados: {Object.keys(v.mudou).join(", ")}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
