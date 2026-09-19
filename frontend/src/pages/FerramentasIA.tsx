import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  FileText,
  Mic,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
} from "lucide-react";
import Markdown from "../components/Markdown";
import CaseFilterChip from "../components/CaseFilterChip";
import { PageHeader, Spinner } from "../components/UI";
import { useCasoFiltro } from "../contexts/useCasoFiltro";
import {
  executarSkill,
  executarSkillDocumento,
  listarSkills,
  transcreverMidia,
  type Skill,
  type SkillExecuteResponse,
} from "../services/ai";
import { mensagemErroIA } from "../lib/iaErro";
import { ROTULO_AREA } from "../lib/taxonomia";

/** Skill exige caso e não há caso selecionado → bloqueia a execução. */
export function bloqueadaSemCaso(
  skill: Pick<Skill, "requires_case"> | undefined,
  casoId: string | null | undefined,
): boolean {
  return Boolean(skill?.requires_case) && !casoId;
}

// Rótulos das áreas canônicas vêm do backend (types/gerado.ts via
// lib/taxonomia); o catálogo de skills usa ainda alguns agrupamentos próprios
// (civel, estrategia, provas, operacional…) que não são CaseArea — ficam aqui
// até o catálogo ser normalizado para AREAS_CANONICAS.
const AREA_LABEL: Record<string, string> = {
  ...ROTULO_AREA,
  civel: "Cível e processual",
  estrategia: "Estratégia processual",
  familia: "Família e sucessões",
  financeiro: "Financeiro",
  juridico: "Jurídico",
  operacional: "Operacional",
  penal: "Penal",
  provas: "Provas e audiência",
};

type FuncionalGrupo = "analisar" | "produzir" | "revisar" | "preparar";

const FUNCIONAL_LABELS: Record<
  FuncionalGrupo,
  { label: string; icon: string }
> = {
  analisar: { label: "Analisar", icon: "🔍" },
  produzir: { label: "Produzir", icon: "✍️" },
  revisar: { label: "Revisar", icon: "📋" },
  preparar: { label: "Preparar", icon: "📦" },
};

const MEDIA_EXTENSIONS = [
  ".flac",
  ".mp3",
  ".mp4",
  ".mpeg",
  ".mpga",
  ".m4a",
  ".ogg",
  ".wav",
  ".webm",
];

function isMedia(file: File | null) {
  const nome = (file?.name || "").toLowerCase();
  return MEDIA_EXTENSIONS.some((ext) => nome.endsWith(ext));
}

function detailErro(error: unknown): string {
  return mensagemErroIA(error, "Falha ao executar a ferramenta.");
}

export default function FerramentasIA() {
  const { casoFiltro, casoFiltroNome, removerFiltro } = useCasoFiltro();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [sel, setSel] = useState("");
  const [texto, setTexto] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busca, setBusca] = useState("");
  const [area, setArea] = useState("todas");
  const [grupo, setGrupo] = useState<FuncionalGrupo | "todos">("todos");
  const [usarRag, setUsarRag] = useState(true);
  const [confirmacaoMidia, setConfirmacaoMidia] = useState(false);
  const [baseLegalMidia, setBaseLegalMidia] = useState("");
  const [loading, setLoading] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [res, setRes] = useState<SkillExecuteResponse | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    listarSkills()
      .then((arr) => {
        setSkills(arr);
        if (arr.length) setSel(arr[0].name);
      })
      .catch(() => setErro("Falha ao carregar as ferramentas de IA."))
      .finally(() => setCarregando(false));
  }, []);

  const areas = useMemo(
    () => Array.from(new Set(skills.map((skill) => skill.area))).sort(),
    [skills],
  );

  const skillsFiltradas = useMemo(() => {
    const termo = busca.trim().toLocaleLowerCase("pt-BR");
    return skills.filter((skill) => {
      if (area !== "todas" && skill.area !== area) return false;
      if (grupo !== "todos" && skill.functional_group !== grupo) return false;
      if (!termo) return true;
      return `${skill.display_name} ${skill.description || ""}`
        .toLocaleLowerCase("pt-BR")
        .includes(termo);
    });
  }, [area, busca, skills, grupo]);

  const skillAtual = skills.find((skill) => skill.name === sel);
  const arquivoMidia = isMedia(file);
  const semCaso = bloqueadaSemCaso(skillAtual, casoFiltro);

  const escolherArquivo = (novo: File | null) => {
    setFile(novo);
    setConfirmacaoMidia(false);
    setBaseLegalMidia("");
    setRes(null);
    setErro(null);
  };

  const executar = async () => {
    if (!sel) return;
    if (semCaso) {
      setErro(
        "Esta ferramenta trabalha sobre um caso: abra-a a partir do caso (Casos → Ferramentas) ou selecione um caso antes de executar.",
      );
      return;
    }
    if (!file && texto.trim().length < 5) {
      setErro("Informe um texto ou anexe um documento/mídia.");
      return;
    }
    if (arquivoMidia && (!confirmacaoMidia || !baseLegalMidia)) {
      setErro(
        "Registre a base legal e confirme o processamento externo da mídia.",
      );
      return;
    }

    setLoading(true);
    setErro(null);
    setRes(null);
    try {
      let data: SkillExecuteResponse;
      if (file) {
        const fd = new FormData();
        fd.append("skill_name", sel);
        fd.append("file", file);
        fd.append("usar_rag", String(usarRag));
        if (casoFiltro) fd.append("case_id", casoFiltro);
        if (texto.trim()) fd.append("instrucoes", texto.trim());

        if (arquivoMidia) {
          fd.append("confirmar_envio_externo", String(confirmacaoMidia));
          fd.append("base_legal_registrada", baseLegalMidia);
          fd.append("idioma", "pt");
          data = await transcreverMidia(fd);
        } else {
          data = await executarSkillDocumento(fd);
        }
      } else {
        data = await executarSkill({
          skill_name: sel,
          query: texto.trim(),
          case_id: casoFiltro,
          usar_rag: usarRag,
        });
      }
      setRes(data);
    } catch (error: any) {
      setErro(detailErro(error));
    } finally {
      setLoading(false);
    }
  };

  if (carregando) {
    return (
      <div className="flex justify-center py-20">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Ferramentas"
        title="Ferramentas de IA"
        subtitle={`${skills.length} fluxos especializados no catálogo existente. Dentro de cada caso, o EJC recomenda apenas as ações adequadas à aba e ao contexto.`}
      />

      {casoFiltro && (
        <CaseFilterChip nome={casoFiltroNome} onRemove={removerFiltro} />
      )}

      <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
        <aside className="card h-fit p-4 lg:sticky lg:top-4">
          <div className="relative">
            <Search
              size={15}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
            />
            <input
              className="input w-full pl-9"
              value={busca}
              onChange={(event) => setBusca(event.target.value)}
              placeholder="Buscar fluxo jurídico…"
              aria-label="Buscar ferramenta"
            />
          </div>

          <div className="mt-3 flex gap-1 rounded-lg bg-slate-100 p-1">
            {(
              [
                ["todos", "Todos"],
                ...Object.entries(FUNCIONAL_LABELS).map(
                  ([k, v]) => [k, `${v.icon} ${v.label}`] as const,
                ),
              ] as const
            ).map(([val, lbl]) => (
              <button
                key={val}
                type="button"
                onClick={() => setGrupo(val as FuncionalGrupo | "todos")}
                className={`flex-1 rounded-md px-2 py-1.5 text-[11px] font-medium transition-colors ${
                  grupo === val
                    ? "bg-white text-slate-900 shadow-sm"
                    : "text-slate-500 hover:text-slate-700"
                }`}
              >
                {lbl}
              </button>
            ))}
          </div>

          <select
            className="input mt-2 w-full"
            value={area}
            onChange={(event) => setArea(event.target.value)}
            aria-label="Filtrar por área"
          >
            <option value="todas">Todas as áreas</option>
            {areas.map((item) => (
              <option key={item} value={item}>
                {AREA_LABEL[item] || item}
              </option>
            ))}
          </select>

          <div className="mt-3 max-h-[580px] space-y-2 overflow-y-auto pr-1">
            {skillsFiltradas.map((skill) => (
              <button
                type="button"
                key={skill.name}
                onClick={() => {
                  setSel(skill.name);
                  setRes(null);
                  setErro(null);
                }}
                className={`w-full rounded-lg border p-3 text-left transition-colors ${
                  sel === skill.name
                    ? "border-primary-400 bg-primary-50"
                    : "border-slate-200 bg-white hover:border-primary-200 hover:bg-slate-50"
                }`}
              >
                <span className="block text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                  {FUNCIONAL_LABELS[classificarGrupo(skill)].icon}{" "}
                  {FUNCIONAL_LABELS[classificarGrupo(skill)].label} ·{" "}
                  {AREA_LABEL[skill.area] || skill.area}
                </span>
                <span className="mt-0.5 block text-sm font-semibold text-slate-800">
                  {skill.display_name}
                </span>
                {skill.description && (
                  <span className="mt-1 block text-xs leading-relaxed text-slate-500">
                    {skill.description}
                  </span>
                )}
              </button>
            ))}
            {!skillsFiltradas.length && (
              <p className="py-8 text-center text-xs text-slate-500">
                Nenhum fluxo encontrado.
              </p>
            )}
          </div>
        </aside>

        <main className="card space-y-4 p-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-semibold text-slate-900">
                {skillAtual?.display_name || "Selecione um fluxo"}
              </h2>
              {skillAtual?.oab_restricted && (
                <span className="rounded-full bg-bronze-50 px-2 py-1 text-[10px] font-semibold text-bronze-700">
                  Restrito à equipe jurídica
                </span>
              )}
              {skillAtual?.requires_human_review && (
                <span
                  className="rounded-full bg-warn-50 px-2 py-1 text-[10px] font-semibold text-warn-800"
                  title="O resultado é rascunho: exige revisão do advogado antes de qualquer uso."
                >
                  Revisão humana obrigatória
                </span>
              )}
              {skillAtual?.requires_case && (
                <span
                  className={`rounded-full px-2 py-1 text-[10px] font-semibold ${
                    semCaso
                      ? "bg-danger-50 text-danger-700"
                      : "bg-primary-50 text-primary-700"
                  }`}
                >
                  {semCaso ? "Exige um caso selecionado" : "Vinculada ao caso"}
                </span>
              )}
            </div>
            {semCaso && (
              <p
                role="alert"
                className="mt-2 rounded-lg border border-danger-200 bg-danger-50 p-2 text-xs text-danger-700"
              >
                Esta ferramenta usa documentos e prazos de um caso. Abra-a a
                partir do caso ou selecione um caso para liberar a execução.
              </p>
            )}
            <p className="mt-1 text-xs text-slate-500">
              A IA primeiro verifica suficiência, lacunas, competência, prazo,
              prova e fontes; a minuta integral só deve ser usada após revisão.
            </p>
          </div>

          <div>
            <label className="label">
              Fatos e instruções {file && "adicionais (opcional)"}
            </label>
            <textarea
              rows={file ? 4 : 10}
              className="input w-full"
              value={texto}
              onChange={(event) => setTexto(event.target.value)}
              placeholder={
                file
                  ? "Informe objetivo, posição do cliente, datas ou pontos que exigem atenção…"
                  : "Relate os fatos e indique o objetivo. Não presuma dados que não constam dos documentos."
              }
            />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <label className="btn-secondary inline-flex cursor-pointer items-center gap-1 text-sm">
              {arquivoMidia ? <Mic size={15} /> : <Upload size={15} />}
              {file ? "Trocar arquivo" : "Anexar documento ou mídia"}
              <input
                type="file"
                className="hidden"
                accept=".pdf,.docx,.png,.jpg,.jpeg,.tiff,.webp,.txt,.flac,.mp3,.mp4,.mpeg,.mpga,.m4a,.ogg,.wav,.webm"
                onChange={(event) =>
                  escolherArquivo(event.target.files?.[0] || null)
                }
              />
            </label>
            {file && (
              <span className="inline-flex max-w-full items-center gap-1 text-xs text-slate-600">
                {arquivoMidia ? <Mic size={13} /> : <FileText size={13} />}
                <span className="max-w-[280px] truncate">{file.name}</span>
                <button
                  type="button"
                  className="ml-1 text-danger-600 hover:underline"
                  onClick={() => escolherArquivo(null)}
                >
                  remover
                </button>
              </span>
            )}
          </div>

          <label className="flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={usarRag}
              onChange={(event) => setUsarRag(event.target.checked)}
            />
            <span>
              Consultar a base interna aprovada e os documentos do caso antes da
              resposta.
            </span>
          </label>

          {arquivoMidia && (
            <div className="space-y-2 rounded-lg border border-warn-200 bg-warn-50 p-3 text-xs text-warn-800">
              <label className="block">
                <span className="mb-1 block font-semibold">
                  Base legal registrada para esta operação
                </span>
                <select
                  className="input w-full bg-white"
                  value={baseLegalMidia}
                  onChange={(event) => setBaseLegalMidia(event.target.value)}
                >
                  <option value="">
                    Selecione após avaliação do responsável
                  </option>
                  <option value="exercicio_regular_direitos">
                    Exercício regular de direitos
                  </option>
                  <option value="execucao_contrato">
                    Execução de contrato/serviço jurídico
                  </option>
                  <option value="obrigacao_legal_regulatoria">
                    Obrigação legal ou regulatória
                  </option>
                  <option value="consentimento">
                    Consentimento válido e documentado
                  </option>
                  <option value="outra_documentada">
                    Outra base documentada
                  </option>
                </select>
              </label>
              <label className="flex items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={confirmacaoMidia}
                  onChange={(event) =>
                    setConfirmacaoMidia(event.target.checked)
                  }
                />
                <span>
                  Confirmo que a base escolhida foi avaliada, que o uso da
                  gravação é autorizado para esta finalidade e que compreendo o
                  envio ao Groq. O recurso só funciona com ZDR e DPA previamente
                  validados pelo escritório.
                </span>
              </label>
            </div>
          )}

          <div className="flex justify-end">
            <button
              type="button"
              className="btn-primary inline-flex items-center gap-1 text-sm"
              disabled={
                loading ||
                !sel ||
                semCaso ||
                (arquivoMidia && (!confirmacaoMidia || !baseLegalMidia))
              }
              onClick={executar}
            >
              <Sparkles size={15} />
              {loading ? "Processando…" : "Executar com triagem"}
            </button>
          </div>

          {erro && (
            <div className="rounded bg-danger-50 p-3 text-xs text-danger-700">
              {erro}
            </div>
          )}

          {res && (
            <section className="rounded-lg border border-bronze-200 bg-bronze-50/40 p-4">
              <div className="mb-3 flex items-start gap-2 text-[11px] font-semibold uppercase text-bronze-700">
                <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                <span>
                  {res.aviso ||
                    "Conferir fatos, documentos, prazos, valores e fontes antes do uso externo."}
                </span>
              </div>

              {res.aviso_privacidade && (
                <div className="mb-3 flex items-start gap-2 rounded border border-primary-200 bg-primary-50 p-2 text-xs text-primary-800">
                  <ShieldCheck size={14} className="mt-0.5 shrink-0" />
                  <span>{res.aviso_privacidade}</span>
                </div>
              )}

              <Markdown
                source={res.conteudo}
                className="text-sm leading-relaxed text-slate-800"
              />

              {res.transcricao && (
                <details className="mt-4 rounded border border-slate-200 bg-white p-3">
                  <summary className="cursor-pointer text-xs font-semibold text-slate-700">
                    Conferir transcrição técnica
                  </summary>
                  <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap text-xs leading-relaxed text-slate-600">
                    {res.transcricao}
                  </pre>
                </details>
              )}

              <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 border-t border-bronze-200 pt-2 text-[11px] text-slate-500">
                <span>{res.skill}</span>
                <span>{res.engine}</span>
                <span>{res.tokens_usados} tokens</span>
                {res.processamento && (
                  <span>
                    {res.processamento.modo} · {res.processamento.blocos}{" "}
                    bloco(s) · sem truncamento
                  </span>
                )}
              </div>
            </section>
          )}
        </main>
      </div>
    </div>
  );
}
