import React from "react";
import { ShieldCheck, Copy, RefreshCw } from "lucide-react";
import api from "../../lib/api";
import { toast } from "../../components/Toast";
import Markdown from "../../components/Markdown";
import { Spinner, Empty, fmtDate } from "../../components/UI";
import type { Case } from "../../types";
import { detalheErro } from "../../utils/erro";

export default function IaDefensivaCaso({ caso }: { caso: Case }) {
  const [etapa, setEtapa] = React.useState("fluxo_completo");
  const [rito, setRito] = React.useState("comum");
  const [area, setArea] = React.useState(caso.area || "civil");
  const [nivelInteligencia, setNivelInteligencia] = React.useState("alto");
  const [peticao, setPeticao] = React.useState(caso.descricao_fatos || "");
  const [docsAutor, setDocsAutor] = React.useState("");
  const [docsDefesa, setDocsDefesa] = React.useState("");
  const [analises, setAnalises] = React.useState("");
  const [resultado, setResultado] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(false);
  const [historico, setHistorico] = React.useState<any[]>([]);
  const [histLoading, setHistLoading] = React.useState(false);
  const [histSelecionado, setHistSelecionado] = React.useState<string | null>(
    null,
  );

  const etapas = [
    ["fluxo_completo", "Fluxo completo"],
    ["analise_inicial", "1. Analise da inicial"],
    ["fragilidades", "2. Fragilidades"],
    ["teses_defensivas", "3. Teses defensivas"],
    ["provas_comparativas", "4. Provas comparativas"],
    ["esqueleto_contestacao", "5. Esqueleto da contestacao"],
    ["redigir_contestacao", "6. Redigir contestacao"],
    ["jec_triagem_minuta", "AcioneJus JEC"],
  ];

  const linhas = (txt: string) =>
    txt
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);

  const carregarHistorico = async () => {
    setHistLoading(true);
    try {
      const { data } = await api.get(`/ia-defensiva/historico/${caso.id}`);
      setHistorico(data.data || []);
    } catch {
      setHistorico([]);
    } finally {
      setHistLoading(false);
    }
  };

  React.useEffect(() => {
    carregarHistorico();
  }, [caso.id]);

  const atualizarStatus = async (logId: string, status: string) => {
    try {
      await api.patch(`/ia-defensiva/historico/${logId}/status`, { status });
      toast.error(`Status atualizado para ${status}.`);
      await carregarHistorico();
    } catch (e: unknown) {
      toast.error(detalheErro(e, "Falha ao atualizar status"));
    }
  };

  const abrirHistorico = (item: any) => {
    setResultado({
      resposta: item.resposta,
      aviso: "Resultado historico da IA Defensiva. Revisao humana obrigatoria.",
    });
    setHistSelecionado(item.id);
  };

  const executar = async () => {
    if (peticao.trim().length < 50) {
      toast.error(
        "Cole a peticao inicial, relato ou base factual com ao menos 50 caracteres.",
      );
      return;
    }
    setLoading(true);
    setResultado(null);
    try {
      const { data } = await api.post("/ia-defensiva/analisar", {
        etapa,
        peticao_inicial: peticao,
        rito,
        area,
        nivel_inteligencia: nivelInteligencia,
        documentos_autor: linhas(docsAutor),
        documentos_defesa: linhas(docsDefesa),
        analises_anteriores: analises || undefined,
        case_id: caso.id,
        momento: "detalhe_caso",
        dados_formais: {
          numero_processo:
            (caso as any).numero_processo ||
            (caso as any).processo_principal?.numero_cnj ||
            "",
          titulo_caso: caso.titulo,
          cliente:
            (caso as any).cliente_nome || (caso as any).client_name || "",
          parte_contraria: caso.parte_contraria || "",
          valor_causa: caso.valor_causa ?? "",
        },
      });
      setResultado(data);
    } catch (e: unknown) {
      setResultado({
        erro: detalheErro(e, "Falha ao executar IA defensiva"),
      });
    } finally {
      setLoading(false);
    }
  };

  const statusClass = (status: string) => {
    const map: Record<string, string> = {
      gerado: "bg-warn-50 text-warn-700 ring-warn-200",
      revisado: "bg-primary-50 text-primary-700 ring-primary-200",
      aplicado: "bg-success-50 text-success-700 ring-success-200",
      descartado: "bg-slate-100 text-slate-500 ring-slate-200",
    };
    return map[status] || "bg-slate-100 text-slate-600 ring-slate-200";
  };

  const etapaResumo = (texto?: string) => {
    const t = texto || "";
    const match = t.match(/^#\s+([^\n]+)/m);
    return match?.[1]?.replace(/_/g, " ") || "IA Defensiva";
  };

  const copiar = async () => {
    const texto = resultado?.resposta || "";
    if (!texto) return;
    await navigator.clipboard.writeText(texto);
    toast.success("Resultado copiado para a area de transferencia.");
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-ai-100 bg-ai-50/70 p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <ShieldCheck size={18} className="text-ai-700" />
              <h2 className="text-sm font-semibold text-slate-950">
                IA Defensiva do Caso
              </h2>
            </div>
            <p className="mt-1 max-w-3xl text-xs leading-relaxed text-slate-600">
              Analisa peticao inicial, fragilidades, provas, teses e estrutura
              contestacao com modo de alta inteligencia juridica. Todo resultado
              e rascunho interno sujeito a revisao humana obrigatoria.
            </p>
          </div>
          <span className="rounded-full bg-white px-3 py-1 text-[11px] font-semibold text-ai-700 ring-1 ring-ai-100">
            Nivel {nivelInteligencia}
          </span>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]">
        <div className="space-y-3 card p-4">
          <div className="grid gap-3 md:grid-cols-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                Inteligencia
              </label>
              <select
                className="input text-sm"
                value={nivelInteligencia}
                onChange={(e) => setNivelInteligencia(e.target.value)}
              >
                <option value="padrao">Padrao</option>
                <option value="alto">Alto</option>
                <option value="maximo">Maximo</option>
              </select>
              <p className="mt-1 text-[10px] text-slate-400">
                Alto usa raciocinio estrategico. Maximo prioriza profundidade e
                autocritica.
              </p>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                Etapa
              </label>
              <select
                className="input text-sm"
                value={etapa}
                onChange={(e) => setEtapa(e.target.value)}
              >
                {etapas.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                Rito
              </label>
              <select
                className="input text-sm"
                value={rito}
                onChange={(e) => setRito(e.target.value)}
              >
                {["comum", "sumario", "JEC", "CLT", "penal", "outro"].map(
                  (r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ),
                )}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                Area
              </label>
              <input
                className="input text-sm"
                value={area}
                onChange={(e) => setArea(e.target.value)}
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">
              Peticao inicial, relato ou base factual
            </label>
            <textarea
              className="input min-h-[260px] text-sm leading-relaxed"
              value={peticao}
              onChange={(e) => setPeticao(e.target.value)}
              placeholder="Cole aqui a peticao inicial completa ou o relato base do caso..."
            />
            <div className="mt-1 text-right text-[11px] text-slate-400">
              {peticao.length} caracteres
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                Documentos do autor
              </label>
              <textarea
                className="input min-h-[110px] text-xs"
                value={docsAutor}
                onChange={(e) => setDocsAutor(e.target.value)}
                placeholder="Um documento por linha"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                Documentos da defesa
              </label>
              <textarea
                className="input min-h-[110px] text-xs"
                value={docsDefesa}
                onChange={(e) => setDocsDefesa(e.target.value)}
                placeholder="Um documento por linha"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">
              Analises anteriores ou observacoes
            </label>
            <textarea
              className="input min-h-[90px] text-xs"
              value={analises}
              onChange={(e) => setAnalises(e.target.value)}
              placeholder="Opcional: cole analises anteriores, estrategia ja definida ou pontos de atencao"
            />
          </div>

          <button
            className="btn-primary w-full justify-center"
            disabled={loading}
            onClick={executar}
          >
            {loading ? (
              <>
                <Spinner /> Executando analise...
              </>
            ) : (
              <>
                <ShieldCheck size={16} /> Executar IA Defensiva
              </>
            )}
          </button>
        </div>

        <div className="card p-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold text-slate-950">
                Resultado
              </h3>
              <p className="text-xs text-slate-500">
                Rascunho interno para revisao do advogado responsavel.
              </p>
            </div>
            {resultado?.resposta && (
              <button className="btn-secondary h-9 text-xs" onClick={copiar}>
                <Copy size={14} /> Copiar
              </button>
            )}
          </div>

          {!resultado && !loading && (
            <div className="flex min-h-[420px] items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50 text-center text-sm text-slate-400">
              Preencha os dados e execute a analise defensiva.
            </div>
          )}
          {loading && (
            <div className="flex min-h-[420px] items-center justify-center gap-2 rounded-lg bg-slate-50 text-sm text-slate-500">
              <Spinner /> Processando estrategia defensiva...
            </div>
          )}
          {resultado?.erro && (
            <div className="rounded-lg border border-danger-200 bg-danger-50 p-3 text-sm text-danger-700">
              {resultado.erro}
            </div>
          )}
          {resultado?.resposta && (
            <div className="max-h-[720px] overflow-auto rounded-lg border border-ai-100 bg-ai-50/30 p-4">
              <Markdown
                source={resultado.resposta}
                className="text-sm leading-7 text-slate-800"
              />
              {resultado.aviso && (
                <p className="mt-4 border-t border-ai-100 pt-3 text-xs font-medium text-ai-700">
                  {resultado.aviso}
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="card p-4">
        <div className="mb-3 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <h3 className="text-sm font-semibold text-slate-950">
              Historico e revisao humana
            </h3>
            <p className="text-xs text-slate-500">
              Cada execucao fica vinculada ao caso e pode ser marcada como
              revisada, aplicada ou descartada.
            </p>
          </div>
          <button
            className="btn-secondary h-9 text-xs"
            onClick={carregarHistorico}
            disabled={histLoading}
          >
            {histLoading ? <Spinner /> : <RefreshCw size={14} />} Atualizar
          </button>
        </div>
        {historico.length === 0 ? (
          <Empty message="Nenhuma analise defensiva registrada para este caso." />
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {historico.map((item) => (
              <div
                key={item.id}
                className={`rounded-lg border p-3 text-xs ${histSelecionado === item.id ? "border-ai-300 bg-ai-50" : "border-slate-200 bg-white"}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <button
                    className="text-left font-semibold text-slate-800 hover:text-ai-700"
                    onClick={() => abrirHistorico(item)}
                  >
                    {etapaResumo(item.resposta)}
                  </button>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 font-semibold ring-1 ${statusClass(item.status_hitl)}`}
                  >
                    {item.status_hitl}
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-slate-400">
                  {item.created_at ? fmtDate(item.created_at) : "sem data"} ·{" "}
                  {item.modelo || "modelo"}
                </p>
                <p className="mt-2 line-clamp-3 text-slate-500">
                  {(item.resposta || "").replace(/[#*_]/g, " ").slice(0, 220)}
                </p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  <button
                    className="rounded-md border border-primary-200 px-2 py-1 text-primary-700 hover:bg-primary-50"
                    onClick={() => atualizarStatus(item.id, "revisado")}
                  >
                    Revisado
                  </button>
                  <button
                    className="rounded-md border border-success-200 px-2 py-1 text-success-700 hover:bg-success-50"
                    onClick={() => atualizarStatus(item.id, "aplicado")}
                  >
                    Aplicado
                  </button>
                  <button
                    className="btn-ghost rounded-md px-2 py-1 text-xs text-slate-500"
                    onClick={() => atualizarStatus(item.id, "descartado")}
                  >
                    Descartar
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
