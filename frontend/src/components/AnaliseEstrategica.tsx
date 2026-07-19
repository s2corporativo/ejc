import React, { useState } from "react";
import {
  Brain,
  Target,
  AlertTriangle,
  Scale,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  Clock,
  Zap,
  Shield,
  Swords,
  Flag,
  Users,
  BookOpen,
  BarChart3,
} from "lucide-react";
import api from "../lib/api";
import { mensagemErroIA, ROTULO_IA_NAO_ATIVADA } from "../lib/iaErro";
import { useIaStatus } from "../lib/iaStatus";
import { Button } from "./UI";

interface Parte {
  nome: string;
  polo: string;
  tipo: string;
  qualificacao: string;
}

interface Tese {
  titulo: string;
  fundamento_legal: string;
  jurisprudencia: string;
  aplicabilidade: string;
  forca: "alta" | "media" | "baixa";
}

interface Risco {
  descricao: string;
  probabilidade: "alta" | "media" | "baixa";
  impacto: "alto" | "medio" | "baixo";
  mitigacao: string;
}

interface ProximoPasso {
  prazo: string;
  acao: string;
  prioridade: "alta" | "media" | "baixa";
}

interface Analise {
  partes?: Parte[];
  ramo?: string;
  subramo?: string;
  sumario_fatos?: string;
  pontos_fortes?: string[];
  pontos_fracos?: string[];
  estrategia?: {
    cenario_agressivo?: {
      descricao: string;
      vantagem: string;
      risco: string;
      acoes: string[];
    };
    cenario_moderado?: {
      descricao: string;
      vantagem: string;
      risco: string;
      acoes: string[];
    };
    cenario_defensivo?: {
      descricao: string;
      vantagem: string;
      risco: string;
      acoes: string[];
    };
    recomendacao?: string;
    justificativa_recomendacao?: string;
  };
  teses_campeas?: Tese[];
  riscos?: Risco[];
  jurimetria?: {
    chance_sucesso_percent?: number;
    tempo_estimado_meses?: number;
    faixa_valor_min?: number;
    faixa_valor_max?: number;
    base_estimativa?: string;
    observacao?: string;
  };
  proximos_passos?: ProximoPasso[];
  alertas?: string[];
  observacoes_finais?: string;
  erro?: string;
}

const forcaCor: Record<string, string> = {
  alta: "bg-green-100 text-green-800 border-green-200",
  media: "bg-yellow-100 text-yellow-800 border-yellow-200",
  baixa: "bg-danger-100 text-danger-800 border-danger-200",
};

const probCor: Record<string, string> = {
  alta: "text-danger-600",
  media: "text-yellow-600",
  baixa: "text-green-600",
};

const cenarioIcon: Record<string, React.ReactNode> = {
  agressivo: <Swords className="w-4 h-4" />,
  moderado: <Target className="w-4 h-4" />,
  defensivo: <Shield className="w-4 h-4" />,
};

const cenarioCor: Record<string, string> = {
  agressivo: "border-danger-200 bg-danger-50",
  moderado: "border-primary-200 bg-primary-50",
  defensivo: "border-green-200 bg-green-50",
};

function Secao({
  titulo,
  icon,
  children,
}: {
  titulo: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  const [aberta, setAberta] = useState(true);
  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => setAberta(!aberta)}
        className="w-full flex items-center justify-between px-5 py-3.5 bg-white hover:bg-slate-50 transition-colors text-left"
      >
        <span className="flex items-center gap-2.5 font-semibold text-slate-800 text-sm">
          {icon}
          {titulo}
        </span>
        {aberta ? (
          <ChevronUp className="w-4 h-4 text-slate-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-slate-400" />
        )}
      </button>
      {aberta && (
        <div className="px-5 pb-5 pt-1 bg-white border-t border-slate-100">
          {children}
        </div>
      )}
    </div>
  );
}

export default function AnaliseEstrategica({
  caseId,
  onClose,
}: {
  caseId: string;
  onClose?: () => void;
}) {
  const [analise, setAnalise] = useState<Analise | null>(null);
  const [loading, setLoading] = useState(false);
  const [textDoc, setTextDoc] = useState("");
  const [mostrarInput, setMostrarInput] = useState(false);
  const { disponivel: iaDisponivel } = useIaStatus();

  async function executarAnalise() {
    setLoading(true);
    try {
      const res = await api.post(`/cases/${caseId}/analisar`, {
        texto_documento: textDoc,
      });
      setAnalise(res.data);
    } catch (e: any) {
      setAnalise({
        erro: mensagemErroIA(
          e,
          "Não foi possível analisar o caso. Verifique os dados cadastrados ou procure o administrador.",
        ),
      });
    } finally {
      setLoading(false);
    }
  }

  const fmtBRL = (v?: number) =>
    v ? v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" }) : "-";

  const rec = analise?.estrategia?.recomendacao || "moderado";

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-ai-600 flex items-center justify-center">
            <Brain className="w-5 h-5 text-white" />
          </div>
          <div>
            <h3 className="font-bold text-slate-800 text-base">
              Análise Estratégica IA
            </h3>
            <p className="text-xs text-slate-500">
              Advogado sênior virtual • 20 anos de experiência
            </p>
          </div>
        </div>
        {analise && (
          <button
            onClick={() => setAnalise(null)}
            className="text-xs text-slate-500 hover:text-slate-700 underline"
          >
            Nova análise
          </button>
        )}
      </div>

      {!analise && (
        <div className="space-y-3">
          <button
            onClick={() => setMostrarInput(!mostrarInput)}
            className="text-sm text-ai-600 hover:text-ai-800 flex items-center gap-1"
          >
            {mostrarInput ? (
              <ChevronUp className="w-3 h-3" />
            ) : (
              <ChevronDown className="w-3 h-3" />
            )}
            {mostrarInput
              ? "Ocultar"
              : "Adicionar texto de documento (opcional)"}
          </button>
          {mostrarInput && (
            <textarea
              value={textDoc}
              onChange={(e) => setTextDoc(e.target.value)}
              placeholder="Cole aqui o texto extraído de uma petição, contrato, documento oficial..."
              className="input h-28 resize-none"
            />
          )}
          <span
            className="block"
            title={iaDisponivel ? undefined : ROTULO_IA_NAO_ATIVADA}
          >
            <Button
              variant="ai"
              onClick={executarAnalise}
              disabled={loading || !iaDisponivel}
              className="w-full py-3 rounded-xl shadow-md"
            >
              {!iaDisponivel ? (
                "IA não ativada — procure o administrador"
              ) : loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Analisando caso...
                </>
              ) : (
                <>
                  <Zap className="w-4 h-4" />
                  Executar Análise Estratégica
                </>
              )}
            </Button>
          </span>
          <p className="text-xs text-slate-400 text-center">
            A IA analisará todos os dados do caso e produzirá um parecer
            estratégico completo
          </p>
        </div>
      )}

      {analise?.erro && (
        <div className="bg-danger-50 border border-danger-200 rounded-xl p-4 text-sm text-danger-700">
          {analise.erro}
        </div>
      )}

      {analise && !analise.erro && (
        <div className="space-y-3">
          {/* Alertas */}
          {analise.alertas && analise.alertas.length > 0 && (
            <div className="bg-warn-50 border border-warn-200 rounded-xl p-4">
              <div className="flex items-center gap-2 font-semibold text-warn-800 text-sm mb-2">
                <AlertTriangle className="w-4 h-4" /> Alertas
              </div>
              <ul className="space-y-1">
                {analise.alertas.map((a, i) => (
                  <li
                    key={i}
                    className="text-sm text-warn-700 flex items-start gap-2"
                  >
                    <span className="mt-0.5 text-warn-500">•</span>
                    {a}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Ramo + Partes */}
          <Secao
            titulo="Ramo e Partes"
            icon={<Scale className="w-4 h-4 text-ai-500" />}
          >
            {analise.ramo && (
              <div className="flex items-center gap-2 mb-3">
                <span className="bg-ai-100 text-ai-800 text-xs font-semibold px-3 py-1 rounded-full">
                  {analise.ramo}
                </span>
                {analise.subramo && (
                  <span className="bg-slate-100 text-slate-700 text-xs px-3 py-1 rounded-full">
                    {analise.subramo}
                  </span>
                )}
              </div>
            )}
            {analise.partes && analise.partes.length > 0 && (
              <div className="space-y-2">
                {analise.partes.map((p, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-3 p-3 bg-slate-50 rounded-lg border border-slate-100"
                  >
                    <Users className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
                    <div>
                      <span
                        className={`text-xs font-semibold px-2 py-0.5 rounded mr-2 ${
                          p.polo === "ativo"
                            ? "bg-primary-100 text-primary-700"
                            : p.polo === "passivo"
                              ? "bg-danger-100 text-danger-700"
                              : "bg-slate-100 text-slate-600"
                        }`}
                      >
                        {p.polo?.toUpperCase()}
                      </span>
                      <span className="font-medium text-sm text-slate-800">
                        {p.nome}
                      </span>
                      {p.tipo && (
                        <span className="text-xs text-slate-500 ml-2">
                          ({p.tipo})
                        </span>
                      )}
                      {p.qualificacao && (
                        <p className="text-xs text-slate-500 mt-0.5">
                          {p.qualificacao}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Secao>

          {/* Fatos + Pontos */}
          <Secao
            titulo="Fatos e Análise Inicial"
            icon={<BookOpen className="w-4 h-4 text-primary-500" />}
          >
            {analise.sumario_fatos && (
              <p className="text-sm text-slate-700 leading-relaxed mb-4 p-3 bg-slate-50 rounded-lg border-l-4 border-primary-400">
                {analise.sumario_fatos}
              </p>
            )}
            <div className="grid grid-cols-2 gap-3">
              {analise.pontos_fortes && analise.pontos_fortes.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-green-700 mb-2 flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Pontos Fortes
                  </p>
                  <ul className="space-y-1.5">
                    {analise.pontos_fortes.map((p, i) => (
                      <li
                        key={i}
                        className="text-xs text-slate-700 bg-green-50 rounded p-2 border border-green-100 leading-relaxed"
                      >
                        {p}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {analise.pontos_fracos && analise.pontos_fracos.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-danger-700 mb-2 flex items-center gap-1">
                    <AlertTriangle className="w-3.5 h-3.5" /> Pontos Fracos
                  </p>
                  <ul className="space-y-1.5">
                    {analise.pontos_fracos.map((p, i) => (
                      <li
                        key={i}
                        className="text-xs text-slate-700 bg-danger-50 rounded p-2 border border-danger-100 leading-relaxed"
                      >
                        {p}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </Secao>

          {/* Estratégia */}
          {analise.estrategia && (
            <Secao
              titulo="Estratégia (3 Cenários)"
              icon={<Target className="w-4 h-4 text-ai-500" />}
            >
              {analise.estrategia.recomendacao && (
                <div className="mb-3 p-3 bg-ai-50 border border-ai-200 rounded-lg">
                  <p className="text-xs font-semibold text-ai-700 mb-1">
                    ✦ Recomendação: cenário{" "}
                    {analise.estrategia.recomendacao?.toUpperCase()}
                  </p>
                  <p className="text-xs text-ai-800">
                    {analise.estrategia.justificativa_recomendacao}
                  </p>
                </div>
              )}
              <div className="space-y-2">
                {(["agressivo", "moderado", "defensivo"] as const).map((c) => {
                  const dados = analise.estrategia?.[
                    `cenario_${c}` as keyof typeof analise.estrategia
                  ] as any;
                  if (!dados) return null;
                  const isRec = rec === c;
                  return (
                    <div
                      key={c}
                      className={`rounded-xl border-2 p-4 transition-all ${isRec ? "border-ai-300 bg-ai-50 shadow-sm" : cenarioCor[c]}`}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        {cenarioIcon[c]}
                        <span
                          className={`text-sm font-bold capitalize ${isRec ? "text-ai-800" : "text-slate-800"}`}
                        >
                          {c} {isRec && "⭐"}
                        </span>
                      </div>
                      <p className="text-xs text-slate-700 mb-2">
                        {dados.descricao}
                      </p>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div className="bg-white bg-opacity-60 rounded p-2">
                          <span className="font-semibold text-green-700">
                            ✓{" "}
                          </span>
                          {dados.vantagem}
                        </div>
                        <div className="bg-white bg-opacity-60 rounded p-2">
                          <span className="font-semibold text-danger-600">
                            ⚠{" "}
                          </span>
                          {dados.risco}
                        </div>
                      </div>
                      {dados.acoes && dados.acoes.length > 0 && (
                        <ul className="mt-2 space-y-1">
                          {dados.acoes.map((a: string, i: number) => (
                            <li
                              key={i}
                              className="text-xs text-slate-600 flex items-start gap-1.5"
                            >
                              <span className="text-ai-400 mt-0.5">→</span>
                              {a}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  );
                })}
              </div>
            </Secao>
          )}

          {/* Teses Campeãs */}
          {analise.teses_campeas && analise.teses_campeas.length > 0 && (
            <Secao
              titulo="Teses Campeãs"
              icon={<BookOpen className="w-4 h-4 text-success-500" />}
            >
              <div className="space-y-3">
                {analise.teses_campeas.map((t, i) => (
                  <div
                    key={i}
                    className="card p-4 border-success-200 hover:border-success-200"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <h4 className="font-semibold text-slate-800 text-sm pr-2">
                        {t.titulo}
                      </h4>
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full border font-medium shrink-0 ${forcaCor[t.forca]}`}
                      >
                        {t.forca?.toUpperCase()}
                      </span>
                    </div>
                    <p className="text-xs text-ai-700 font-medium mb-1">
                      ⚖ {t.fundamento_legal}
                    </p>
                    <p className="text-xs text-slate-500 mb-2 italic">
                      {t.jurisprudencia}
                    </p>
                    <p className="text-xs text-slate-700 bg-white rounded-lg p-2 border border-success-100">
                      {t.aplicabilidade}
                    </p>
                  </div>
                ))}
              </div>
            </Secao>
          )}

          {/* Jurimetria */}
          {analise.jurimetria && (
            <Secao
              titulo="Jurimetria"
              icon={<BarChart3 className="w-4 h-4 text-primary-500" />}
            >
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-primary-50 rounded-xl p-4 border border-primary-100 text-center">
                  <div className="text-xl font-bold text-primary-600 mb-1">
                    {analise.jurimetria.chance_sucesso_percent ?? "—"}%
                  </div>
                  <div className="text-xs text-slate-500">Chance de Êxito</div>
                  <div className="mt-2 h-2 bg-primary-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary-500 rounded-full"
                      style={{
                        width: `${analise.jurimetria.chance_sucesso_percent ?? 0}%`,
                      }}
                    />
                  </div>
                </div>
                <div className="bg-ai-50 rounded-xl p-4 border border-ai-100 text-center">
                  <div className="text-xl font-bold text-ai-600 mb-1">
                    {analise.jurimetria.tempo_estimado_meses ?? "—"}
                  </div>
                  <div className="text-xs text-slate-500">Meses estimados</div>
                  <div className="text-xs text-slate-400 mt-1">
                    duração do processo
                  </div>
                </div>
              </div>
              <div className="bg-success-50 border border-success-200 rounded-xl p-4 text-center mb-3">
                <div className="text-xs text-slate-500 mb-1">
                  Faixa de Valor Estimado
                </div>
                <div className="text-lg font-bold text-success-700">
                  {fmtBRL(analise.jurimetria.faixa_valor_min)} —{" "}
                  {fmtBRL(analise.jurimetria.faixa_valor_max)}
                </div>
              </div>
              {analise.jurimetria.base_estimativa && (
                <p className="text-xs text-slate-500 italic mb-1">
                  Base: {analise.jurimetria.base_estimativa}
                </p>
              )}
              {analise.jurimetria.observacao && (
                <p className="text-xs text-slate-600">
                  {analise.jurimetria.observacao}
                </p>
              )}
            </Secao>
          )}

          {/* Matriz de Riscos */}
          {analise.riscos && analise.riscos.length > 0 && (
            <Secao
              titulo="Matriz de Riscos"
              icon={<AlertTriangle className="w-4 h-4 text-orange-500" />}
            >
              <div className="space-y-2">
                {analise.riscos.map((r, i) => (
                  <div
                    key={i}
                    className="card p-4"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <p className="text-sm font-medium text-slate-800 pr-2">
                        {r.descricao}
                      </p>
                      <div className="flex gap-1.5 shrink-0">
                        <span
                          className={`text-xs font-semibold ${probCor[r.probabilidade]}`}
                        >
                          P:{r.probabilidade?.toUpperCase()}
                        </span>
                        <span className="text-slate-300">•</span>
                        <span
                          className={`text-xs font-semibold ${probCor[r.impacto]}`}
                        >
                          I:{r.impacto?.toUpperCase()}
                        </span>
                      </div>
                    </div>
                    <div className="text-xs text-slate-600 bg-slate-50 rounded p-2 border border-slate-100">
                      <span className="font-medium text-slate-700">
                        Mitigação:{" "}
                      </span>
                      {r.mitigacao}
                    </div>
                  </div>
                ))}
              </div>
            </Secao>
          )}

          {/* Próximos Passos */}
          {analise.proximos_passos && analise.proximos_passos.length > 0 && (
            <Secao
              titulo="Próximos Passos"
              icon={<Clock className="w-4 h-4 text-teal-500" />}
            >
              <div className="space-y-2">
                {analise.proximos_passos
                  .sort((a, b) => {
                    const order: Record<string, number> = {
                      alta: 0,
                      media: 1,
                      baixa: 2,
                    };
                    return (
                      (order[a.prioridade] ?? 2) - (order[b.prioridade] ?? 2)
                    );
                  })
                  .map((p, i) => (
                    <div
                      key={i}
                      className="card flex items-start gap-3 p-3"
                    >
                      <div
                        className={`text-xs font-bold px-2 py-1 rounded-lg shrink-0 ${
                          p.prioridade === "alta"
                            ? "bg-danger-100 text-danger-700"
                            : p.prioridade === "media"
                              ? "bg-yellow-100 text-yellow-700"
                              : "bg-green-100 text-green-700"
                        }`}
                      >
                        {p.prazo}
                      </div>
                      <div>
                        <p className="text-sm text-slate-800">{p.acao}</p>
                      </div>
                    </div>
                  ))}
              </div>
            </Secao>
          )}

          {/* Observações Finais */}
          {analise.observacoes_finais && (
            <div className="bg-slate-900 rounded-xl p-4 text-white">
              <div className="flex items-center gap-2 mb-3">
                <Flag className="w-4 h-4 text-yellow-400" />
                <span className="font-semibold text-sm">
                  Parecer do Advogado Sênior
                </span>
              </div>
              <p className="text-sm text-slate-200 leading-relaxed">
                {analise.observacoes_finais}
              </p>
            </div>
          )}

          <p className="text-center text-xs text-slate-400">
            Análise gerada por IA • Revisar antes de usar em procedimentos
            jurídicos oficiais
          </p>
        </div>
      )}
    </div>
  );
}
