import { useEffect, useState } from "react";
import { toast } from "../components/Toast";
import {
  BrainCircuit,
  Database,
  FileCheck2,
  Gavel,
  ListChecks,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import api from "../lib/api";
import { PageHeader, Spinner, fmtDate } from "../components/UI";

type Tab =
  | "visao"
  | "curadoria"
  | "mgjec"
  | "prompts"
  | "fontes"
  | "guardrails";

function Kpi({
  label,
  value,
  hint,
}: {
  label: string;
  value: any;
  hint?: string;
}) {
  return (
    <div className="card p-4">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="text-2xl font-serif text-navy mt-1">{value ?? "—"}</div>
      {hint && <div className="text-xs text-slate-500 mt-1">{hint}</div>}
    </div>
  );
}

export default function GovernancaIA() {
  const [tab, setTab] = useState<Tab>("visao");
  const [dash, setDash] = useState<any>(null);
  const [docs, setDocs] = useState<any[]>([]);
  const [prompts, setPrompts] = useState<any[]>([]);
  const [fontes, setFontes] = useState<any[]>([]);
  const [guard, setGuard] = useState<any>(null);
  const [mgjec, setMgjec] = useState<any[]>([]);
  const [geometria, setGeometria] = useState<any>(null);
  const [jurisForm, setJurisForm] = useState({
    titulo: "",
    ementa: "",
    tese_extraida: "",
    numero_processo: "",
    fonte_url: "",
    area: "consumidor",
    rito: "JEC",
    tipo_fonte: "turma_recursal",
  });
  const [loading, setLoading] = useState(true);
  const [salvando, setSalvando] = useState<string | null>(null);
  const [urlImportacao, setUrlImportacao] = useState("");
  const [previewExtracao, setPreviewExtracao] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const [d, c, p, f, g, mg, geo] = await Promise.allSettled([
        api.get("/ia-governanca/dashboard"),
        api.get("/ia-governanca/rag-curadoria", { params: { page_size: 30 } }),
        api.get("/ia-governanca/prompts"),
        api.get("/ia-governanca/fontes"),
        api.get("/ia-governanca/guardrails"),
        api.get("/ia-governanca/jurisprudencia-mg", { params: { limite: 30 } }),
        api.get("/ia-governanca/jurisprudencia-mg/geometria"),
      ]);
      if (d.status === "fulfilled") setDash(d.value.data);
      if (c.status === "fulfilled") setDocs(c.value.data.data);
      if (p.status === "fulfilled") setPrompts(p.value.data.data);
      if (f.status === "fulfilled") setFontes(f.value.data.data);
      if (g.status === "fulfilled") setGuard(g.value.data);
      if (mg.status === "fulfilled") setMgjec(mg.value.data.data);
      if (geo.status === "fulfilled") setGeometria(geo.value.data);

      const falhas = [d, c, p, f, g, mg, geo].filter(
        (r) => r.status === "rejected",
      ).length;
      if (falhas > 0) {
        toast.error(
          `Falha ao carregar ${falhas} de 7 painéis de governança de IA. Alguns dados podem estar desatualizados.`,
        );
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const atualizarCuradoria = async (
    doc: any,
    confidence_level: string,
    rag_status = "aprovado",
  ) => {
    setSalvando(doc.id);
    try {
      await api.patch(`/ia-governanca/rag-curadoria/${doc.id}`, {
        confidence_level,
        rag_status,
      });
      await load();
    } finally {
      setSalvando(null);
    }
  };

  const extrairUrlJurisprudencia = async () => {
    if (!urlImportacao) return;
    setSalvando("extrair-url");
    setPreviewExtracao("");
    try {
      const { data } = await api.post(
        "/ia-governanca/jurisprudencia-mg/extrair-url",
        {
          url: urlImportacao,
          tipo_fonte: jurisForm.tipo_fonte,
          area: jurisForm.area,
          rito: jurisForm.rito,
        },
      );
      setJurisForm({
        ...jurisForm,
        ...data.data,
        tese_extraida: data.data.tese_extraida || jurisForm.tese_extraida,
        area: data.data.area || jurisForm.area,
        rito: data.data.rito || jurisForm.rito,
      });
      setPreviewExtracao(data.texto_extraido_preview || "");
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao extrair URL oficial");
    } finally {
      setSalvando(null);
    }
  };

  const importarJurisprudencia = async () => {
    setSalvando("mgjec");
    try {
      await api.post("/ia-governanca/jurisprudencia-mg", {
        ...jurisForm,
        aprovar_para_rag: true,
      });
      setJurisForm({
        titulo: "",
        ementa: "",
        tese_extraida: "",
        numero_processo: "",
        fonte_url: "",
        area: "consumidor",
        rito: "JEC",
        tipo_fonte: "turma_recursal",
      });
      await load();
    } finally {
      setSalvando(null);
    }
  };

  if (loading)
    return (
      <div className="py-20 flex justify-center">
        <Spinner />
      </div>
    );

  const tabs = [
    { k: "visao", label: "Visão geral", icon: BrainCircuit },
    { k: "curadoria", label: "Curadoria RAG", icon: Database },
    { k: "mgjec", label: "MG/JEC", icon: Gavel },
    { k: "prompts", label: "Prompts", icon: SlidersHorizontal },
    { k: "fontes", label: "Fontes", icon: FileCheck2 },
    { k: "guardrails", label: "Guardrails", icon: ShieldCheck },
  ] as const;

  return (
    <div>
      <PageHeader
        eyebrow="Governança"
        title="Governança da IA"
        subtitle="Curadoria, prompts, HITL, fontes e controles de risco da inteligência jurídica"
      />

      <div className="flex flex-wrap gap-2 mb-5">
        {tabs.map(({ k, label, icon: Icon }) => (
          <button
            key={k}
            className={`btn ${tab === k ? "bg-navy text-white" : "bg-white border border-slate-200 text-slate-600"}`}
            onClick={() => setTab(k)}
          >
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>

      {tab === "visao" && (
        <div className="space-y-5">
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Kpi
              label="Chamadas IA"
              value={dash?.ia?.total_chamadas}
              hint="período 30 dias"
            />
            <Kpi
              label="HITL revisado/aplicado"
              value={
                dash?.ia?.taxa_hitl_pct != null
                  ? `${dash.ia.taxa_hitl_pct}%`
                  : "—"
              }
            />
            <Kpi
              label="Score médio validações"
              value={dash?.ia?.score_medio_validacoes}
            />
            <Kpi label="Docs RAG" value={dash?.rag?.documentos} />
          </div>
          <div className="grid lg:grid-cols-3 gap-4">
            <Box title="RAG por confiança" data={dash?.rag?.por_confianca} />
            <Box title="HITL por status" data={dash?.ia?.por_status} />
            <Box title="Fontes por status" data={dash?.fontes?.por_status} />
          </div>
          <div className="card p-4 border-l-4 border-l-warn-500">
            <h3 className="font-semibold text-ink mb-2">Pontos de atenção</h3>
            <p className="text-sm text-slate-600">
              Peças finais sem validação revisada:{" "}
              <b>{dash?.guardrails?.pecas_finais_sem_validacao_revisada}</b>.
              Score mínimo de peça:{" "}
              <b>{dash?.guardrails?.score_minimo_peca}/100</b>.
            </p>
          </div>
        </div>
      )}

      {tab === "curadoria" && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">Documento</th>
                <th className="px-4 py-3">Categoria</th>
                <th className="px-4 py-3">Chunks</th>
                <th className="px-4 py-3">Confiança</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Ação</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {docs.map((d) => (
                <tr key={d.id}>
                  <td className="px-4 py-3">
                    <div className="font-medium text-navy">{d.titulo}</div>
                    <div className="text-xs text-slate-400 truncate max-w-md">
                      {d.fonte}
                    </div>
                  </td>
                  <td className="px-4 py-3">{d.categoria}</td>
                  <td className="px-4 py-3">{d.chunks}</td>
                  <td className="px-4 py-3">
                    <Badge value={d.confidence_level} />
                  </td>
                  <td className="px-4 py-3">{d.rag_status}</td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1">
                      <button
                        className="btn-ghost px-2 py-1 text-xs text-success-700"
                        disabled={salvando === d.id}
                        onClick={() =>
                          atualizarCuradoria(d, "alta", "aprovado")
                        }
                      >
                        Alta
                      </button>
                      <button
                        className="btn-ghost px-2 py-1 text-xs"
                        disabled={salvando === d.id}
                        onClick={() =>
                          atualizarCuradoria(d, "media", "aprovado")
                        }
                      >
                        Média
                      </button>
                      <button
                        className="btn-ghost px-2 py-1 text-xs text-warn-700"
                        disabled={salvando === d.id}
                        onClick={() =>
                          atualizarCuradoria(d, "baixa", "pendente")
                        }
                      >
                        Baixa
                      </button>
                      <button
                        className="btn-ghost px-2 py-1 text-xs text-danger-700"
                        disabled={salvando === d.id}
                        onClick={() =>
                          atualizarCuradoria(d, "bloqueado", "recusado")
                        }
                      >
                        Bloquear
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "mgjec" && (
        <div className="space-y-5">
          <div className="grid lg:grid-cols-[1.05fr_.95fr] gap-4">
            <div className="card p-4">
              <h3 className="font-semibold text-ink mb-2">Geometria MG/JEC</h3>
              <p className="text-sm text-slate-600 mb-3">
                Base separada por colecao, metadados e fonte oficial.
                Jurisprudencia sem fonte validada fica pendente e nao deve ser
                citada como confirmada.
              </p>
              <div className="flex flex-wrap gap-2">
                {geometria?.colecoes?.map((c: string) => (
                  <span
                    key={c}
                    className="badge bg-warn-50 text-warn-800 ring-1 ring-warn-200"
                  >
                    {c}
                  </span>
                ))}
              </div>
            </div>
            <div className="card p-4">
              <h3 className="font-semibold text-ink mb-3">
                Importar decisao TJMG/JEC
              </h3>
              <div className="mb-3 grid gap-2 rounded-xl border border-warn-200 bg-warn-50/50 p-3">
                <div className="text-xs font-semibold uppercase text-warn-800">
                  Importador assistido por URL oficial
                </div>
                <div className="flex gap-2">
                  <input
                    className="input"
                    placeholder="Cole URL oficial TJMG/CNJ/STJ/FONAJE"
                    value={urlImportacao}
                    onChange={(e) => setUrlImportacao(e.target.value)}
                  />
                  <button
                    className="btn-secondary shrink-0"
                    disabled={salvando === "extrair-url" || !urlImportacao}
                    onClick={extrairUrlJurisprudencia}
                  >
                    Extrair
                  </button>
                </div>
                {previewExtracao && (
                  <div className="max-h-28 overflow-auto rounded-lg bg-white p-2 text-xs text-slate-500">
                    {previewExtracao}
                  </div>
                )}
              </div>
              <div className="grid gap-2">
                <input
                  className="input"
                  placeholder="Titulo / tese curta"
                  value={jurisForm.titulo}
                  onChange={(e) =>
                    setJurisForm({ ...jurisForm, titulo: e.target.value })
                  }
                />
                <div className="grid sm:grid-cols-2 gap-2">
                  <input
                    className="input"
                    placeholder="Numero do processo"
                    value={jurisForm.numero_processo}
                    onChange={(e) =>
                      setJurisForm({
                        ...jurisForm,
                        numero_processo: e.target.value,
                      })
                    }
                  />
                  <input
                    className="input"
                    placeholder="Area"
                    value={jurisForm.area}
                    onChange={(e) =>
                      setJurisForm({ ...jurisForm, area: e.target.value })
                    }
                  />
                </div>
                <div className="grid sm:grid-cols-2 gap-2">
                  <select
                    className="input"
                    value={jurisForm.tipo_fonte}
                    onChange={(e) =>
                      setJurisForm({ ...jurisForm, tipo_fonte: e.target.value })
                    }
                  >
                    <option value="turma_recursal">Turma Recursal</option>
                    <option value="sentenca_jec">Sentenca JEC</option>
                    <option value="acordao">Acordao TJMG</option>
                    <option value="fonaje">FONAJE</option>
                    <option value="stj">STJ</option>
                    <option value="datajud">DataJud</option>
                  </select>
                  <input
                    className="input"
                    placeholder="Rito"
                    value={jurisForm.rito}
                    onChange={(e) =>
                      setJurisForm({ ...jurisForm, rito: e.target.value })
                    }
                  />
                </div>
                <input
                  className="input"
                  placeholder="URL oficial TJMG/CNJ/STJ/FONAJE"
                  value={jurisForm.fonte_url}
                  onChange={(e) =>
                    setJurisForm({ ...jurisForm, fonte_url: e.target.value })
                  }
                />
                <textarea
                  className="input min-h-24"
                  placeholder="Ementa ou trecho integral da decisao"
                  value={jurisForm.ementa}
                  onChange={(e) =>
                    setJurisForm({ ...jurisForm, ementa: e.target.value })
                  }
                />
                <textarea
                  className="input min-h-20"
                  placeholder="Tese extraida / uso estrategico"
                  value={jurisForm.tese_extraida}
                  onChange={(e) =>
                    setJurisForm({
                      ...jurisForm,
                      tese_extraida: e.target.value,
                    })
                  }
                />
                <button
                  className="btn-primary"
                  disabled={
                    salvando === "mgjec" ||
                    jurisForm.titulo.length < 5 ||
                    jurisForm.ementa.length < 50
                  }
                  onClick={importarJurisprudencia}
                >
                  Salvar na base MG/JEC
                </button>
              </div>
            </div>
          </div>
          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase text-slate-400">
                <tr>
                  <th className="px-4 py-3">Decisao</th>
                  <th className="px-4 py-3">Colecao</th>
                  <th className="px-4 py-3">Rito</th>
                  <th className="px-4 py-3">Fonte</th>
                  <th className="px-4 py-3">Confianca</th>
                  <th className="px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {mgjec.map((j) => (
                  <tr key={j.id}>
                    <td className="px-4 py-3">
                      <div className="font-medium text-navy">{j.titulo}</div>
                      <div className="text-xs text-slate-400">
                        {j.numero_processo || "sem numero"} ·{" "}
                        {j.orgao_julgador || "orgao nao informado"}
                      </div>
                    </td>
                    <td className="px-4 py-3">{j.colecao}</td>
                    <td className="px-4 py-3">{j.rito || "—"}</td>
                    <td className="px-4 py-3">
                      {j.fonte_validada ? (
                        <span className="badge bg-success-100 text-success-700">
                          validada
                        </span>
                      ) : (
                        <span className="badge bg-warn-100 text-warn-700">
                          verificar
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <Badge value={j.confidence_level} />
                    </td>
                    <td className="px-4 py-3">{j.rag_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === "prompts" && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">Prompt</th>
                <th className="px-4 py-3">Categoria</th>
                <th className="px-4 py-3">Versão</th>
                <th className="px-4 py-3">Execuções</th>
                <th className="px-4 py-3">Avaliação</th>
                <th className="px-4 py-3">Atualizado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {prompts.map((p) => (
                <tr key={p.id}>
                  <td className="px-4 py-3 font-medium text-navy">
                    {p.titulo}
                  </td>
                  <td className="px-4 py-3">{p.categoria}</td>
                  <td className="px-4 py-3">v{p.versao}</td>
                  <td className="px-4 py-3">{p.vezes_executado}</td>
                  <td className="px-4 py-3">{p.avaliacao_media ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-400">
                    {fmtDate(p.updated_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "fontes" && (
        <div className="grid lg:grid-cols-2 gap-4">
          {fontes.map((f) => (
            <div key={f.slug} className="card p-4">
              <div className="flex justify-between gap-3">
                <div>
                  <h3 className="font-semibold text-navy">{f.slug}</h3>
                  <p className="text-sm text-slate-500">{f.descricao}</p>
                </div>
                <span
                  className={`badge ${f.ultimo_status === "sucesso" ? "bg-success-100 text-success-700" : "bg-warn-100 text-warn-700"}`}
                >
                  {f.ultimo_status || "sem execução"}
                </span>
              </div>
              <div className="mt-3 text-xs text-slate-500">
                Categoria: {f.categoria_rag || "—"} · Total: {f.registros_total}{" "}
                · Novos: {f.registros_novos}
              </div>
              <div className="text-xs text-slate-400 mt-1">
                Última execução: {fmtDate(f.ultima_execucao)}
              </div>
              {f.ultimo_erro && (
                <div className="mt-2 text-xs text-danger-600">
                  {f.ultimo_erro}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === "guardrails" && (
        <div className="space-y-4">
          <div className="grid sm:grid-cols-3 gap-4">
            <Kpi label="Peças" value={guard?.metricas?.pecas_total} />
            <Kpi
              label="Peças IA sem revisão"
              value={guard?.metricas?.pecas_ia_sem_revisao}
            />
            <Kpi
              label="Logs IA pendentes"
              value={guard?.metricas?.ai_logs_pendentes_hitl}
            />
          </div>
          <div className="card p-4">
            <h3 className="font-semibold text-ink mb-3 flex items-center gap-2">
              <ListChecks size={18} /> Regras ativas
            </h3>
            <div className="space-y-2">
              {guard?.regras_ativas?.map((r: string) => (
                <div key={r} className="flex gap-2 text-sm text-slate-700">
                  <ShieldCheck size={15} className="text-success-600 mt-0.5" />{" "}
                  {r}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Box({ title, data }: { title: string; data: any }) {
  return (
    <div className="card p-4">
      <h3 className="font-semibold text-ink mb-2">{title}</h3>
      {Object.entries(data || {}).map(([k, v]) => (
        <div
          key={k}
          className="flex justify-between text-sm py-1 border-b border-slate-100 last:border-0"
        >
          <span className="text-slate-600">{k}</span>
          <span className="font-semibold text-navy">{v as any}</span>
        </div>
      ))}
    </div>
  );
}

function Badge({ value }: { value: string }) {
  const map: Record<string, string> = {
    alta: "bg-success-100 text-success-700",
    media: "bg-primary-100 text-primary-700",
    baixa: "bg-warn-100 text-warn-700",
    bloqueado: "bg-danger-100 text-danger-700",
  };
  return (
    <span className={`badge ${map[value] || "bg-slate-100 text-slate-600"}`}>
      {value}
    </span>
  );
}
