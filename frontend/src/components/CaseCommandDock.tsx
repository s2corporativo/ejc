import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import {
  FileUp,
  Gavel,
  LayoutGrid,
  Scale,
  Trash2,
  X,
} from "lucide-react";
import api from "../lib/api";
import { CASE_NAV_SECTIONS } from "../config/caseNav";
import { useAreas } from "../lib/areas";
import { caminhoAbaCaso } from "../lib/caseContext";
import { toast } from "./Toast";
import { Badge, Button, EmptyState, Modal } from "./UI";

type View = "menu" | "upload" | "areas" | null;

type CaseAreaLink = {
  area: string;
  principal?: boolean;
};

function detalheErro(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (
    detail &&
    typeof detail === "object" &&
    typeof (detail as { mensagem?: unknown }).mensagem === "string"
  ) {
    return (detail as { mensagem: string }).mensagem;
  }
  return fallback;
}

export default function CaseCommandDock({ caseId }: { caseId: string }) {
  const navigate = useNavigate();
  const taxonomia = useAreas();
  const [view, setView] = useState<View>(null);
  const [areas, setAreas] = useState<CaseAreaLink[]>([]);
  const [areaNova, setAreaNova] = useState("");
  const [areasLoading, setAreasLoading] = useState(false);
  const [salvandoArea, setSalvandoArea] = useState(false);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [titulo, setTitulo] = useState("");
  const [tipo, setTipo] = useState("outro");
  const [enviando, setEnviando] = useState(false);

  const labels = useMemo(
    () => new Map(taxonomia.map((area) => [area.slug, area.nome])),
    [taxonomia],
  );

  const areasDisponiveis = useMemo(
    () =>
      taxonomia.filter(
        (item) => !areas.some((vinculo) => vinculo.area === item.slug),
      ),
    [areas, taxonomia],
  );

  const carregarAreas = async () => {
    setAreasLoading(true);
    try {
      const { data } = await api.get(`/cases/${caseId}/areas`);
      setAreas(Array.isArray(data?.areas) ? data.areas : []);
    } catch (error) {
      toast.error(
        detalheErro(error, "Não foi possível carregar as áreas do caso."),
      );
      setAreas([]);
    } finally {
      setAreasLoading(false);
    }
  };

  useEffect(() => {
    if (view === "areas") void carregarAreas();
  }, [view, caseId]);

  const abrirDestino = (destino: string) => {
    setView(null);
    navigate(destino);
  };

  const adicionarArea = async () => {
    if (!areaNova) return;
    setSalvandoArea(true);
    try {
      await api.post(`/cases/${caseId}/areas`, { area: areaNova });
      toast.success("Área relacionada ao caso.");
      setAreaNova("");
      await carregarAreas();
    } catch (error) {
      toast.error(detalheErro(error, "Não foi possível adicionar a área."));
    } finally {
      setSalvandoArea(false);
    }
  };

  const removerArea = async (area: CaseAreaLink) => {
    if (area.principal) {
      toast.error("A área principal não pode ser removida por esta ação.");
      return;
    }
    if (
      !window.confirm(`Remover a área ${labels.get(area.area) || area.area}?`)
    ) {
      return;
    }
    try {
      await api.delete(`/cases/${caseId}/areas/${area.area}`);
      toast.success("Área removida do caso.");
      await carregarAreas();
    } catch (error) {
      toast.error(detalheErro(error, "Não foi possível remover a área."));
    }
  };

  const limparUpload = () => {
    setArquivo(null);
    setTitulo("");
    setTipo("outro");
  };

  const enviarDocumento = async () => {
    if (!arquivo) {
      toast.error("Selecione um documento para anexar ao caso.");
      return;
    }
    setEnviando(true);
    try {
      const body = new FormData();
      body.append("file", arquivo);
      body.append("titulo", titulo.trim() || arquivo.name);
      body.append("tipo", tipo);
      body.append("case_id", caseId);
      await api.post("/documents/upload", body, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success("Documento anexado ao caso.");
      limparUpload();
      setView(null);
    } catch (error) {
      toast.error(
        detalheErro(error, "Não foi possível anexar o documento ao caso."),
      );
    } finally {
      setEnviando(false);
    }
  };

  const fechar = () => {
    if (enviando || salvandoArea) return;
    setView(null);
    limparUpload();
    setAreaNova("");
  };

  // Modo simples: somente as quatro superfícies usadas no trabalho diário.
  // Estratégia/IA continua disponível logo abaixo como recurso avançado; nada
  // é removido nem escondido de deep-links existentes.
  const actions = CASE_NAV_SECTIONS.filter((secao) =>
    ["resumo", "timeline", "documentos", "financeiro"].includes(secao.tab),
  ).map((secao) => ({
    label: secao.label,
    description: secao.descricao,
    icon: secao.icon,
    to: caminhoAbaCaso(caseId, secao.tab),
  }));
  const estrategia = CASE_NAV_SECTIONS.find((secao) => secao.tab === "teses");

  return (
    <>
      <button
        type="button"
        onClick={() => setView("menu")}
        className="fixed bottom-6 right-6 z-30 inline-flex items-center gap-2 rounded-xl bg-primary-700 px-4 py-3 text-sm font-semibold text-white shadow-md transition hover:bg-primary-800 focus:outline-none focus:ring-2 focus:ring-primary-400 focus:ring-offset-2"
        aria-label="Abrir ações rápidas do caso"
      >
        <Gavel className="h-4 w-4" />
        Ações do caso
      </button>

      <Modal open={view !== null} onClose={fechar} title="Trabalhar neste caso">
        {view === "menu" && (
          <div className="space-y-5">
            <div className="rounded-xl bg-primary-50 p-4 text-sm text-primary-900 ring-1 ring-inset ring-primary-100">
              <div className="flex items-center gap-2 font-semibold">
                <LayoutGrid className="h-4 w-4" /> Ações rápidas
              </div>
              <p className="mt-1 text-primary-700">
                Escolha o que precisa fazer agora. Recursos especializados continuam disponíveis no workspace completo.
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              {actions.map(({ label, description, icon: Icon, to }) => (
                <button
                  key={label}
                  type="button"
                  onClick={() => abrirDestino(to)}
                  className="flex items-start gap-3 rounded-xl bg-slate-900/[0.04] p-4 text-left transition hover:bg-slate-900/[0.08]"
                >
                  <span className="rounded-lg bg-white p-2 text-primary-700 shadow-sm">
                    <Icon className="h-4 w-4" />
                  </span>
                  <span>
                    <span className="block text-sm font-semibold text-slate-900">
                      {label}
                    </span>
                    <span className="mt-1 block text-xs leading-5 text-slate-500">
                      {description}
                    </span>
                  </span>
                </button>
              ))}
            </div>

            <div className="grid gap-2 sm:grid-cols-2">
              <Button
                variant="secondary"
                onClick={() => setView("areas")}
                icon={<Scale className="h-4 w-4" />}
              >
                Áreas do caso
              </Button>
              <Button
                variant="primary"
                onClick={() => setView("upload")}
                icon={<FileUp className="h-4 w-4" />}
              >
                Anexar documento
              </Button>
            </div>

            {estrategia && (
              <button
                type="button"
                onClick={() => abrirDestino(caminhoAbaCaso(caseId, estrategia.tab))}
                className="flex w-full items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-left transition hover:border-primary-200 hover:bg-primary-50/40"
              >
                <span>
                  <span className="block text-sm font-semibold text-slate-900">
                    Estratégia & IA
                  </span>
                  <span className="mt-0.5 block text-xs text-slate-500">
                    Teses, riscos, jurisprudência, dossiê e ferramentas jurídicas.
                  </span>
                </span>
                <estrategia.icon className="h-4 w-4 shrink-0 text-primary-700" />
              </button>
            )}
          </div>
        )}

        {view === "areas" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="font-semibold text-slate-900">
                  Áreas de atuação do caso
                </h3>
                <p className="mt-1 text-sm text-slate-500">
                  Taxonomia canônica do EJC, alimentada por GET /areas.
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setView("menu")}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            {areasLoading ? (
              <p className="py-6 text-center text-sm text-slate-500">
                Carregando áreas…
              </p>
            ) : areas.length === 0 ? (
              <EmptyState
                icon={Scale}
                title="Nenhuma área relacionada"
                message="Adicione uma área jurídica abaixo."
              />
            ) : (
              <div className="flex flex-wrap gap-2">
                {areas.map((area) => (
                  <span
                    key={area.area}
                    className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1.5 text-xs text-slate-700"
                  >
                    {area.principal && <Badge tone="ouro">Principal</Badge>}
                    {labels.get(area.area) || area.area.split("_").join(" ")}
                    {!area.principal && (
                      <button
                        type="button"
                        onClick={() => void removerArea(area)}
                        className="text-slate-400 hover:text-danger-600"
                        aria-label={`Remover área ${labels.get(area.area) || area.area}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </span>
                ))}
              </div>
            )}

            <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
              <select
                className="input w-full"
                value={areaNova}
                onChange={(event) => setAreaNova(event.target.value)}
                aria-label="Adicionar área relacionada"
              >
                <option value="">Selecione uma área relacionada</option>
                {areasDisponiveis.map((area) => (
                  <option key={area.slug} value={area.slug}>
                    {area.nome}
                  </option>
                ))}
              </select>
              <Button
                variant="primary"
                onClick={() => void adicionarArea()}
                disabled={!areaNova || salvandoArea}
              >
                {salvandoArea ? "Adicionando…" : "Adicionar"}
              </Button>
            </div>
          </div>
        )}

        {view === "upload" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="font-semibold text-slate-900">
                  Anexar documento ao caso
                </h3>
                <p className="mt-1 text-sm text-slate-500">
                  O backend valida extensão, conteúdo, permissão e vínculo ao caso.
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setView("menu")}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div>
              <label
                htmlFor={`case-dock-file-${caseId}`}
                className="mb-1 block text-sm font-medium text-slate-700"
              >
                Arquivo
              </label>
              <input
                id={`case-dock-file-${caseId}`}
                type="file"
                accept=".pdf,.docx,.doc,.jpg,.jpeg,.png,.xlsx,.xls,.txt,.xml"
                className="input w-full"
                onChange={(event) => {
                  const next = event.target.files?.[0] ?? null;
                  setArquivo(next);
                  if (next && !titulo) setTitulo(next.name);
                }}
              />
              <p className="mt-1 text-xs text-slate-500">
                PDF, DOCX, DOC, JPG, PNG, XLSX, XLS, TXT e XML. DOC e XLS são armazenados sem indexação de texto.
              </p>
            </div>

            <div>
              <label
                htmlFor={`case-dock-title-${caseId}`}
                className="mb-1 block text-sm font-medium text-slate-700"
              >
                Título
              </label>
              <input
                id={`case-dock-title-${caseId}`}
                className="input w-full"
                value={titulo}
                maxLength={255}
                onChange={(event) => setTitulo(event.target.value)}
                placeholder="Identificação do documento"
              />
            </div>

            <div>
              <label
                htmlFor={`case-dock-type-${caseId}`}
                className="mb-1 block text-sm font-medium text-slate-700"
              >
                Tipo
              </label>
              <select
                id={`case-dock-type-${caseId}`}
                className="input w-full"
                value={tipo}
                onChange={(event) => setTipo(event.target.value)}
              >
                <option value="outro">Outro</option>
                <option value="peticao">Petição</option>
                <option value="decisao">Decisão</option>
                <option value="contrato">Contrato</option>
                <option value="procuracao">Procuração</option>
                <option value="prova">Prova</option>
              </select>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button
                variant="secondary"
                onClick={() => setView("menu")}
                disabled={enviando}
              >
                Voltar
              </Button>
              <Button
                variant="primary"
                onClick={() => void enviarDocumento()}
                disabled={!arquivo || enviando}
                icon={<FileUp className="h-4 w-4" />}
              >
                {enviando ? "Anexando…" : "Anexar documento"}
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}
