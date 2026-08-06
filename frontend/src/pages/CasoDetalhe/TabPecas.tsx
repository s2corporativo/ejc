// ── Aba Peças do caso — NOVA (Tela C, Bloco 3) ───────────────────────────────
// Fecha o caminho até o protocolo dentro do caso: lista as peças do caso,
// cria a peça mínima (a REDAÇÃO continua no módulo /pecas, deep-link ?caso=),
// baixa o PDF de leitura da minuta e executa o ato único de conferência e
// assinatura (POST /legal-docs/{id}/conferir-e-assinar).
//
// HITL É INEGOCIÁVEL: o modal de conferência reproduz EXATAMENTE o fluxo do
// módulo Peças (Pecas.tsx, aprovarPeca) — observações de revisão obrigatórias
// antes de habilitar a assinatura, texto de responsabilidade técnica, nenhuma
// chamada sem confirmação explícita. Duplicação temporária com /pecas aceita
// pelo titular (Decisões de 2026-08-02, item 2).
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { FileDown, FolderOpen, Plus, ShieldCheck } from "lucide-react";
import api from "../../lib/api";
import type { LegalDoc } from "../../types";
import { toast } from "../../components/Toast";
import { Empty, Modal, StatusBadge } from "../../components/UI";
import { detalheErro } from "../../utils/erro";

// Mesmos valores do enum PecaTipo do backend (app/models/legal_doc.py) — não
// inventar tipos aqui: o backend devolve 422 para valor fora do enum.
const TIPOS_PECA = [
  "peticao_inicial",
  "contestacao",
  "recurso",
  "contrarrazoes",
  "parecer",
  "contrato",
  "procuracao",
  "notificacao_extrajudicial",
  "defesa_ambiental",
  "outro",
];

// Espelha STATUS_POS_APROVACAO de Pecas.tsx: peça já assinada baixa o PDF de
// protocolo (/pdf, com gates); antes disso, o PDF de LEITURA (/pdf-minuta).
const STATUS_POS_APROVACAO = new Set(["aprovada", "final", "protocolada"]);

// responseType blob: erros 4xx/5xx chegam como Blob JSON — extrai o `detail`
// legível para o toast (mesmo helper de Pecas.tsx).
async function blobErrorDetail(e: any): Promise<string | undefined> {
  let detail = e.response?.data?.detail;
  if (!detail && e.response?.data instanceof Blob) {
    try {
      detail = JSON.parse(await e.response.data.text())?.detail;
    } catch {
      /* corpo não-JSON — usa mensagem padrão do chamador */
    }
  }
  return typeof detail === "object" && detail !== null
    ? (detail.mensagem ?? JSON.stringify(detail).slice(0, 200))
    : detail;
}

export default function TabPecas({ caseId }: { caseId: string }) {
  const [pecas, setPecas] = useState<LegalDoc[]>([]);
  const [modalNova, setModalNova] = useState(false);
  const [form, setForm] = useState({
    titulo: "",
    tipo_peca: "peticao_inicial",
    conteudo: "",
  });
  const [salvando, setSalvando] = useState(false);
  // Conferência e assinatura (HITL) — mesmo estado/fluxo de Pecas.tsx.
  const [aprovacao, setAprovacao] = useState<{
    doc: LegalDoc;
    observacoes: string;
  } | null>(null);
  const [aprovando, setAprovando] = useState(false);

  const carregar = useCallback(() => {
    api
      .get("/legal-docs/", { params: { case_id: caseId, page_size: 50 } })
      .then((r) => setPecas(r.data?.data ?? []))
      .catch(() => {
        setPecas([]);
        toast.error("Falha ao carregar as peças do caso");
      });
  }, [caseId]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const criarPeca = async () => {
    if (!form.titulo.trim()) {
      toast.error("Informe o título da peça.");
      return;
    }
    setSalvando(true);
    try {
      await api.post("/legal-docs/", {
        titulo: form.titulo.trim(),
        tipo_peca: form.tipo_peca,
        conteudo: form.conteudo,
        case_id: caseId,
      });
      setModalNova(false);
      setForm({ titulo: "", tipo_peca: "peticao_inicial", conteudo: "" });
      toast.success(
        "Peça criada como rascunho — a redação continua no módulo Peças.",
      );
      carregar();
    } catch (e: unknown) {
      toast.error(detalheErro(e, "Erro ao criar a peça"));
    } finally {
      setSalvando(false);
    }
  };

  // Um só ato no backend (POST /conferir-e-assinar): valida juridicamente se
  // preciso, registra a revisão HITL e assina — tudo numa transação. As
  // observações são obrigatórias no modal (mesma exigência do módulo Peças).
  const conferirEAssinar = async () => {
    if (!aprovacao) return;
    const observacoes = aprovacao.observacoes.trim();
    if (!observacoes) return;
    setAprovando(true);
    try {
      await api.post(`/legal-docs/${aprovacao.doc.id}/conferir-e-assinar`, {
        observacoes,
      });
      setAprovacao(null);
      toast.success("Peça conferida e assinada com revisão humana registrada");
      carregar();
    } catch (e: unknown) {
      toast.error(detalheErro(e, "Falha ao conferir e assinar a peça"));
    } finally {
      setAprovando(false);
    }
  };

  // Minuta baixa o PDF de LEITURA (/pdf-minuta, sem gate de protocolo) — o
  // advogado precisa ler antes de assinar. Assinada segue no /pdf (com gates).
  const baixarPdf = async (doc: LegalDoc) => {
    const aprovada = STATUS_POS_APROVACAO.has(doc.status);
    try {
      const r = aprovada
        ? await api.get(`/legal-docs/${doc.id}/pdf`, { responseType: "blob" })
        : await api.get(`/legal-docs/${doc.id}/pdf-minuta`, {
            responseType: "blob",
          });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = aprovada ? `${doc.titulo}.pdf` : `${doc.titulo}-minuta.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      toast.error((await blobErrorDetail(e)) || "Falha ao gerar o PDF.");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-semibold">Peças do caso ({pecas.length})</h2>
          <p className="text-xs text-gray-400">
            Criação e assinatura acontecem aqui; a redação completa (editor, IA,
            templates) continua no módulo Peças.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to={`/pecas?caso=${caseId}`}
            className="btn-secondary text-xs flex items-center gap-1"
          >
            <FolderOpen size={14} /> Abrir no módulo Peças
          </Link>
          <button
            onClick={() => setModalNova(true)}
            className="btn-primary text-xs flex items-center gap-1"
          >
            <Plus size={14} /> Nova peça
          </button>
        </div>
      </div>

      <div className="space-y-2">
        {pecas.map((p) => {
          const assinada = STATUS_POS_APROVACAO.has(p.status);
          return (
            <div key={p.id} className="card p-3 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <span className="font-medium text-gray-800">{p.titulo}</span>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {p.tipo_peca.replace(/_/g, " ")} · v{p.versao}
                    {p.ai_generated ? " · gerada com IA" : ""}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2 shrink-0">
                  <StatusBadge value={p.status} />
                  {assinada ? (
                    <button
                      onClick={() => void baixarPdf(p)}
                      className="btn-secondary text-xs flex items-center gap-1"
                      title="PDF de protocolo (com gates de validação)"
                    >
                      <FileDown size={14} /> Baixar PDF
                    </button>
                  ) : (
                    <>
                      <button
                        onClick={() => void baixarPdf(p)}
                        className="btn-secondary text-xs flex items-center gap-1"
                        title="PDF de leitura, marcado como minuta"
                      >
                        <FileDown size={14} /> Baixar PDF da minuta
                      </button>
                      <button
                        onClick={() =>
                          setAprovacao({ doc: p, observacoes: "" })
                        }
                        className="btn-primary text-xs flex items-center gap-1"
                      >
                        <ShieldCheck size={14} /> Conferir e assinar
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          );
        })}
        {pecas.length === 0 && (
          <Empty message="Nenhuma peça neste caso. Crie a primeira acima." />
        )}
      </div>

      {/* Nova peça — mínimo para nascer vinculada ao caso */}
      <Modal
        open={modalNova}
        onClose={() => setModalNova(false)}
        title="Nova peça neste caso"
      >
        <div className="space-y-3">
          <div>
            <label className="label">Título</label>
            <input
              className="input w-full text-sm"
              value={form.titulo}
              maxLength={255}
              onChange={(e) => setForm({ ...form, titulo: e.target.value })}
              placeholder="Ex.: Petição inicial — ação de cobrança"
            />
          </div>
          <div>
            <label className="label">Tipo</label>
            <select
              className="input w-full text-sm"
              value={form.tipo_peca}
              onChange={(e) => setForm({ ...form, tipo_peca: e.target.value })}
            >
              {TIPOS_PECA.map((t) => (
                <option key={t} value={t}>
                  {t.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Conteúdo inicial (opcional)</label>
            <textarea
              className="input w-full min-h-[100px] text-sm"
              value={form.conteudo}
              onChange={(e) => setForm({ ...form, conteudo: e.target.value })}
              placeholder="Rascunho inicial — a redação completa continua no módulo Peças."
            />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <button className="btn-ghost" onClick={() => setModalNova(false)}>
              Cancelar
            </button>
            <button
              className="btn-primary"
              disabled={salvando || !form.titulo.trim()}
              onClick={() => void criarPeca()}
            >
              {salvando ? "Criando…" : "Criar peça"}
            </button>
          </div>
        </div>
      </Modal>

      {/* Conferência e assinatura (HITL) — MESMO fluxo do módulo Peças:
          observações obrigatórias, responsabilidade técnica explícita,
          cancelar/fechar NÃO move a peça. */}
      <Modal
        open={!!aprovacao}
        onClose={() => setAprovacao(null)}
        title="Conferir e assinar peça"
      >
        <p className="text-sm text-slate-600 mb-3">
          Você está prestes a conferir e assinar a peça{" "}
          <strong>{aprovacao?.doc.titulo}</strong>
          {aprovacao?.doc.ai_generated ? ", gerada com auxílio de IA" : ""}. A
          revisão humana é obrigatória: descreva as observações da sua análise.
          Ao assinar, você assume a responsabilidade técnica pelo conteúdo.
        </p>
        <textarea
          className="input min-h-[120px]"
          placeholder="Observações da revisão (obrigatório)"
          value={aprovacao?.observacoes || ""}
          onChange={(e) =>
            aprovacao &&
            setAprovacao({ ...aprovacao, observacoes: e.target.value })
          }
        />
        <div className="flex justify-end gap-2 mt-4">
          <button className="btn-ghost" onClick={() => setAprovacao(null)}>
            Cancelar
          </button>
          <button
            className="btn-primary"
            disabled={aprovando || !aprovacao?.observacoes.trim()}
            onClick={() => void conferirEAssinar()}
          >
            <ShieldCheck size={15} />{" "}
            {aprovando ? "Assinando..." : "Conferir e assinar"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
