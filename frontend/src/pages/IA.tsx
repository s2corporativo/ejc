import { useEffect, useState } from "react";
import Markdown from "../components/Markdown";
import { Sparkles, FileText, History, Eye, ShieldCheck } from "lucide-react";
import api from "../lib/api";
import { PageHeader, Spinner, fmtDate, StatusBadge } from "../components/UI";

const AREAS = ["civil", "trabalhista", "consumidor", "familia", "ambiental", "criminal", "previdenciario", "empresarial", "tributario"];

type Tab = "analise" | "resumo" | "validacao" | "logs";

export default function IA() {
  const [tab, setTab] = useState<Tab>("analise");
  const [fatos, setFatos] = useState("");
  const [area, setArea] = useState("civil");
  const [nomes, setNomes] = useState("");
  const [docTexto, setDocTexto] = useState("");
  const [rascunhoValidacao, setRascunhoValidacao] = useState("");
  const [tipoDocumento, setTipoDocumento] = useState("contestacao");
  const [rito, setRito] = useState("");
  const [fase, setFase] = useState("pre_protocolo");
  const [documentosValidacao, setDocumentosValidacao] = useState("");
  const [nivelValidacao, setNivelValidacao] = useState("alto");
  const [resp, setResp] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<any[]>([]);
  const [caseId, setCaseId] = useState("");
  const [casos, setCasos] = useState<any[]>([]);
  const [dossie, setDossie] = useState<string | null>(null);
  const [loadingDossie, setLoadingDossie] = useState(false);

  useEffect(() => {
    if (tab === "logs") api.get("/ai/logs", { params: { page_size: 30 } }).then((r) => setLogs(r.data.data));
  }, [tab]);

  useEffect(() => {
    api.get("/cases/", { params: { page_size: 100 } }).then((r) => setCasos(r.data.data)).catch(() => setCasos([]));
  }, []);

  const verDossie = async () => {
    if (!caseId) return;
    setLoadingDossie(true);
    setDossie(null);
    try {
      const { data } = await api.get(`/ai/dossie/${caseId}`);
      setDossie(data.texto);
    } catch (e: any) {
      setDossie("Erro ao carregar dossiê: " + (e.response?.data?.detail || "falha"));
    } finally {
      setLoadingDossie(false);
    }
  };

  const analisar = async () => {
    setLoading(true); setResp(null);
    try {
      const { data } = await api.post("/ai/analisar-caso", {
        descricao_fatos: fatos,
        area,
        nomes_proteger: nomes.split(",").map((n) => n.trim()).filter(Boolean),
        case_id: caseId || undefined,
      });
      setResp(data);
    } catch (e: any) { setResp({ erro: e.response?.data?.detail || "Falha" }); }
    finally { setLoading(false); }
  };

  const resumir = async () => {
    setLoading(true); setResp(null);
    try {
      const { data } = await api.post("/ai/resumir-documento", { texto: docTexto, case_id: caseId || undefined });
      setResp(data);
    } catch (e: any) { setResp({ erro: e.response?.data?.detail || "Falha" }); }
    finally { setLoading(false); }
  };

  const validarRascunho = async () => {
    setLoading(true); setResp(null);
    try {
      const { data } = await api.post("/validador-juridico/validar", {
        rascunho: rascunhoValidacao,
        tipo_documento: tipoDocumento,
        area,
        rito: rito || undefined,
        fase: fase || undefined,
        case_id: caseId || undefined,
        nivel_inteligencia: nivelValidacao,
        documentos: documentosValidacao.split("\n").map((d) => d.trim()).filter(Boolean),
      });
      setResp(data);
    } catch (e: any) { setResp({ erro: e.response?.data?.detail || "Falha" }); }
    finally { setLoading(false); }
  };

  const marcarHitl = async (id: string, status: string) => {
    await api.patch(`/ai/logs/${id}/hitl`, { status });
    api.get("/ai/logs", { params: { page_size: 30 } }).then((r) => setLogs(r.data.data));
  };

  const tabs = [
    { k: "analise", label: "Análise de caso", icon: Sparkles },
    { k: "resumo", label: "Resumo", icon: FileText },
    { k: "validacao", label: "Validação jurídica", icon: ShieldCheck },
    { k: "logs", label: "Histórico / HITL", icon: History },
  ] as const;

  return (
    <div>
      <PageHeader title="IA Jurídica" subtitle="RAG semântico · dados sanitizados · rascunhos com revisão humana obrigatória" />

      <div className="flex flex-wrap gap-2 mb-5">
        {tabs.map(({ k, label, icon: Icon }) => (
          <button key={k} onClick={() => { setTab(k); setResp(null); }} className={`btn ${tab === k ? "bg-navy text-white" : "bg-white border border-slate-200 text-slate-600"}`}>
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>

      {(tab === "analise" || tab === "validacao" || tab === "resumo") && (
        <div className="rounded-lg bg-gold-50 border border-gold-200 p-3 mb-4">
          <label className="label">Caso vinculado (opcional)</label>
          <div className="flex gap-2">
            <select className="input flex-1" value={caseId} onChange={(e) => { setCaseId(e.target.value); setDossie(null); }}>
              <option value="">Nenhum caso vinculado</option>
              {casos.map((c) => <option key={c.id} value={c.id}>{c.numero_interno} — {c.titulo}</option>)}
            </select>
            <button className="btn bg-white border border-gold-300 text-gold-700" disabled={!caseId || loadingDossie} onClick={verDossie}>
              <Eye size={15} /> {loadingDossie ? "..." : "Ver dossiê"}
            </button>
          </div>
          {dossie && <details open className="mt-3"><summary className="cursor-pointer text-xs font-medium text-navy">Contexto do dossiê</summary><Markdown source={dossie} className="mt-2 text-xs bg-white border border-slate-200 rounded p-3 max-h-72 overflow-y-auto" /></details>}
        </div>
      )}

      {tab === "analise" && (
        <div className="card p-5 space-y-4">
          <div className="grid sm:grid-cols-2 gap-4">
            <div><label className="label">Área jurídica</label><select className="input" value={area} onChange={(e) => setArea(e.target.value)}>{AREAS.map((a) => <option key={a} value={a}>{a}</option>)}</select></div>
            <div><label className="label">Nomes a proteger (vírgula)</label><input className="input" value={nomes} onChange={(e) => setNomes(e.target.value)} /></div>
          </div>
          <div><label className="label">Fatos do caso</label><textarea className="input min-h-[160px]" value={fatos} onChange={(e) => setFatos(e.target.value)} /></div>
          <button className="btn-gold" disabled={loading || fatos.length < 30} onClick={analisar}><Sparkles size={15} /> {loading ? "Analisando..." : "Sugerir teses"}</button>
        </div>
      )}

      {tab === "resumo" && (
        <div className="card p-5 space-y-4">
          <div><label className="label">Texto do documento</label><textarea className="input min-h-[200px]" value={docTexto} onChange={(e) => setDocTexto(e.target.value)} /></div>
          <button className="btn-gold" disabled={loading || docTexto.length < 50} onClick={resumir}><FileText size={15} /> {loading ? "Resumindo..." : "Resumir"}</button>
        </div>
      )}

      {tab === "validacao" && (
        <div className="card p-5 space-y-4">
          <div className="grid lg:grid-cols-4 sm:grid-cols-2 gap-4">
            <div><label className="label">Tipo</label><select className="input" value={tipoDocumento} onChange={(e) => setTipoDocumento(e.target.value)}><option value="contestacao">Contestação</option><option value="peticao_inicial">Petição inicial</option><option value="recurso">Recurso</option><option value="contrato">Contrato</option><option value="parecer">Parecer</option><option value="outro">Outro</option></select></div>
            <div><label className="label">Área</label><select className="input" value={area} onChange={(e) => setArea(e.target.value)}>{AREAS.map((a) => <option key={a} value={a}>{a}</option>)}</select></div>
            <div><label className="label">Rito</label><input className="input" placeholder="comum, JEC, CLT" value={rito} onChange={(e) => setRito(e.target.value)} /></div>
            <div><label className="label">Nível</label><select className="input" value={nivelValidacao} onChange={(e) => setNivelValidacao(e.target.value)}><option value="alto">Alto</option><option value="maximo">Máximo</option><option value="padrao">Padrão</option></select></div>
          </div>
          <div><label className="label">Fase</label><input className="input" value={fase} onChange={(e) => setFase(e.target.value)} /></div>
          <div><label className="label">Documentos/provas disponíveis (um por linha)</label><textarea className="input min-h-[90px]" value={documentosValidacao} onChange={(e) => setDocumentosValidacao(e.target.value)} /></div>
          <div><label className="label">Rascunho jurídico para validação</label><textarea className="input min-h-[260px]" value={rascunhoValidacao} onChange={(e) => setRascunhoValidacao(e.target.value)} /></div>
          <button className="btn-gold" disabled={loading || rascunhoValidacao.length < 100} onClick={validarRascunho}><ShieldCheck size={15} /> {loading ? "Validando..." : "Validar antes de finalizar"}</button>
        </div>
      )}

      {tab === "logs" && (
        <div className="space-y-2">
          {logs.map((l) => (
            <div key={l.id} className="card p-4">
              <div className="flex flex-wrap items-center gap-3 mb-2"><span className="text-xs font-semibold text-navy uppercase">{l.tipo_uso.replace(/_/g, " ")}</span><StatusBadge value={l.status_hitl} />{l.pii_removida && <span className="badge bg-success-100 text-success-700">PII removida</span>}<span className="text-xs text-slate-400 ml-auto">{fmtDate(l.created_at)}</span></div>
              {l.resposta && <details className="text-sm text-slate-600"><summary className="cursor-pointer text-navy text-xs font-medium">Ver resposta</summary><Markdown source={l.resposta} className="mt-2 text-xs" /></details>}
              {l.status_hitl === "gerado" && <div className="flex gap-2 mt-2"><button className="btn-ghost text-xs px-2 py-1" onClick={() => marcarHitl(l.id, "revisado")}>Marcar revisado</button><button className="btn-ghost text-xs px-2 py-1 text-success-700" onClick={() => marcarHitl(l.id, "aplicado")}>Aplicado</button><button className="btn-ghost text-xs px-2 py-1 text-danger-600" onClick={() => marcarHitl(l.id, "descartado")}>Descartar</button></div>}
            </div>
          ))}
          {logs.length === 0 && <div className="card p-8 text-center text-sm text-slate-400">Nenhum uso de IA registrado</div>}
        </div>
      )}

      {loading && <Spinner />}
      {resp?.erro && <div className="mt-4 p-3 rounded-lg bg-danger-50 text-danger-700 text-sm">{resp.erro}</div>}
      {resp?.resposta && (
        <div className="mt-5 card p-5">
          <div className="mb-3 p-3 rounded-lg bg-warn-50 text-warn-800 text-xs font-medium">
            {resp.aviso}{resp.veredito ? ` · Veredito: ${resp.veredito}` : ""}{resp.score_confianca !== undefined ? ` · Score: ${resp.score_confianca}/100` : ""}{resp.fontes_usadas !== undefined ? ` · Fontes: ${resp.fontes_usadas}` : ""}
          </div>
          {resp.metricas && <div className="grid sm:grid-cols-3 gap-3 mb-4 text-xs"><div className="rounded border border-slate-200 p-3"><b>Artigos</b><br />{resp.metricas.artigos_detectados?.length || 0}</div><div className="rounded border border-slate-200 p-3"><b>Jurisprudência pendente</b><br />{resp.metricas.jurisprudencia_pendente_verificacao?.length || 0}</div><div className="rounded border border-slate-200 p-3"><b>Provas indicadas</b><br />{resp.metricas.indicadores_prova?.length || 0}</div></div>}
          <Markdown source={resp.resposta} className="text-sm text-slate-700" />
        </div>
      )}
    </div>
  );
}
